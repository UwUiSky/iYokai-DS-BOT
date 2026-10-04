"""
core/scheduler.py
====================
Scheduler generico per azioni differite: tempban, unmute automatico,
in futuro anche boost temporanei o promemoria. Backed dal database,
non dalla memoria del processo — questo è il punto importante:

Perché non basta asyncio.sleep() + un task in background
------------------------------------------------------------
Se pianifichi uno sblocco con `asyncio.create_task` e un
`asyncio.sleep(durata)`, quel timer VIVE SOLO finché il processo
resta acceso. Se il bot si riavvia (deploy, crash, restart del
server) tutti i timer in corso spariscono nel nulla: un tempban di
7 giorni pianificato ieri, dopo un riavvio, non scade mai da solo.

Come funziona invece questo scheduler
-----------------------------------------
Ogni azione differita è una RIGA nella tabella `scheduled_actions`,
con un `execute_at` (quando va eseguita) e un `action_type` (cosa
fare). Un task periodico (`tasks.loop`) interroga il database ogni
30 secondi: "quali azioni sono scadute e non ancora eseguite?" e le
esegue. Se il bot si riavvia, alla ripartenza il primo controllo
trova comunque le azioni scadute nel frattempo e le esegue subito.

Ogni cog che ha bisogno di un'azione differita:
1. REGISTRA un handler per il proprio action_type, una volta sola,
   nel proprio setup() — vedi register_handler() più sotto.
2. Quando serve pianificare, chiama scheduler.schedule(...).
Non deve mai occuparsi lui stesso di timer o task in background.

Se manca l'handler o l'handler solleva, l'azione viene riprovata con
un'attesa crescente (ATTESE_RIPROVA) e solo dopo MAX_TENTATIVI viene
abbandonata con il motivo in `failed_reason`. Ogni azione gira nella
propria transazione.
Funzioni coperte: REVIEW.md BUG-8, BUG-27 (issue #13, #56).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from discord.ext import commands, tasks

from core.bot_ready import attendi_bot_pronto

logger = logging.getLogger("iyokai.scheduler")

# Firma di un handler: riceve guild_id, user_id, e il payload salvato
# al momento della pianificazione (dati specifici dell'azione, es.
# {"reason": "..."} per un tempban).
ActionHandler = Callable[[int, int, dict], Awaitable[None]]

# Quante azioni al massimo in un giro del loop.
AZIONI_PER_GIRO = 50

# Attesa dopo il 1°, 2°, 3°… tentativo fallito; l'ultima vale anche per
# i successivi. Con 8 tentativi un'azione viene riprovata per circa 20 ore.
ATTESE_RIPROVA = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=30),
    timedelta(hours=2),
    timedelta(hours=6),
)
MAX_TENTATIVI = 8

# Pausa dopo un giro fallito (database irraggiungibile): raddoppia a ogni
# errore di fila, fino a questo massimo.
PAUSA_BASE_ERRORE_SECONDI = 30
PAUSA_MASSIMA_ERRORE_SECONDI = 600


def attesa_prima_di_riprovare(tentativi: int) -> timedelta:
    """Attesa dopo il tentativo fallito numero `tentativi` (1, 2, 3…)."""
    return ATTESE_RIPROVA[min(tentativi, len(ATTESE_RIPROVA)) - 1]


class Scheduler:
    """
    Un'unica istanza condivisa (vedi `scheduler` in fondo al file).
    Gli handler si registrano per action_type; il loop periodico li
    invoca quando un'azione di quel tipo scade.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, ActionHandler] = {}
        self._loop_task: tasks.Loop | None = None
        self._errori_di_fila = 0

    def register_handler(self, action_type: str, handler: ActionHandler) -> None:
        """
        Registra la funzione da chiamare quando un'azione di questo
        tipo scade.

        Se un altro action_type è già registrato con un handler di
        una classe/metodo DIVERSO, è un errore di programmazione vero
        e va segnalato subito. Se invece lo stesso action_type viene
        ri-registrato con un handler dello STESSO metodo (stesso
        __qualname__, es. "ReminderCog.handle_reminder_fire") è un
        reload legittimo — /owner cog-reload richiama setup() (e
        quindi register_handler()) sullo stesso cog una seconda
        volta, con un NUOVO oggetto bound method che punta alla
        nuova istanza del cog (quella vecchia, distrutta dal reload,
        non deve restare agganciata). Stesso identico problema già
        trovato e corretto in core/premium.py — non ipotizzato,
        verificato con un test reale su un cog vero.
        """
        esistente = self._handlers.get(action_type)
        if esistente is not None and esistente.__qualname__ != handler.__qualname__:
            raise ValueError(
                f"Handler già registrato per action_type='{action_type}' "
                f"da un metodo diverso ({esistente.__qualname__})."
            )
        self._handlers[action_type] = handler

    async def schedule(
        self,
        guild_id: int,
        user_id: int,
        action_type: str,
        execute_at: datetime,
        payload: dict | None = None,
    ) -> int:
        """
        Pianifica una nuova azione differita. Restituisce l'id della
        riga creata, utile se il chiamante vuole poterla annullare
        in seguito (vedi cancel()).
        """
        from core.database import db

        row = await db.pool.fetchrow(
            """
            INSERT INTO scheduled_actions
                (guild_id, user_id, action_type, execute_at, payload)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            RETURNING id
            """,
            guild_id,
            user_id,
            action_type,
            execute_at,
            json.dumps(payload or {}),
        )
        return row["id"]

    async def cancel(self, action_id: int) -> None:
        """
        Annulla un'azione pianificata prima che scada (es. un admin
        fa /unban manuale prima che scada il tempban automatico:
        l'azione pianificata va cancellata per non eseguire un
        secondo unban ridondante più avanti).
        """
        from core.database import db

        await db.pool.execute(
            "DELETE FROM scheduled_actions WHERE id = $1 AND executed = FALSE",
            action_id,
        )

    async def list_pending_for_user(
        self, user_id: int, action_type: str, limit: int = 25
    ) -> list[dict]:
        """
        Elenca le azioni pianificate non ancora eseguite per un
        utente e un tipo specifico — es. /reminders list. A
        differenza di _run_due_actions() (che gira nel loop periodico
        e prende QUALUNQUE azione scaduta, per eseguirla), questa è
        una lettura su richiesta per mostrare all'utente cosa ha
        ancora in sospeso, scaduto o no.
        """
        from core.database import db

        rows = await db.pool.fetch(
            """
            SELECT id, guild_id, execute_at, payload FROM scheduled_actions
            WHERE user_id = $1 AND action_type = $2 AND executed = FALSE AND failed_reason IS NULL
            ORDER BY execute_at
            LIMIT $3
            """,
            user_id,
            action_type,
            limit,
        )
        return [
            {
                "id": row["id"],
                "guild_id": row["guild_id"],
                "execute_at": row["execute_at"],
                "payload": json.loads(row["payload"]) if row["payload"] else {},
            }
            for row in rows
        ]

    async def list_pending_for_guild(
        self, guild_id: int, action_type: str, limit: int = 25
    ) -> list[dict]:
        """
        Come list_pending_for_user(), ma filtrata per SERVER invece
        che per utente — per funzionalità admin dove non conta chi
        ha pianificato l'azione, conta a quale server appartiene
        (es. /schedule-message list, dove qualunque admin deve poter
        vedere tutti i messaggi programmati del proprio server, non
        solo quelli creati da sé stesso).
        """
        from core.database import db

        rows = await db.pool.fetch(
            """
            SELECT id, user_id, execute_at, payload FROM scheduled_actions
            WHERE guild_id = $1 AND action_type = $2 AND executed = FALSE AND failed_reason IS NULL
            ORDER BY execute_at
            LIMIT $3
            """,
            guild_id,
            action_type,
            limit,
        )
        return [
            {
                "id": row["id"],
                "user_id": row["user_id"],
                "execute_at": row["execute_at"],
                "payload": json.loads(row["payload"]) if row["payload"] else {},
            }
            for row in rows
        ]

    async def get_pending_action(self, action_id: int) -> dict | None:
        """
        Legge una singola azione pianificata per id — usata da
        /reminders cancel per verificare che l'azione esista, che
        appartenga davvero a chi sta cercando di cancellarla, e che
        non sia già stata eseguita, PRIMA di cancellarla.
        """
        from core.database import db

        row = await db.pool.fetchrow(
            "SELECT id, guild_id, user_id, action_type, payload, executed "
            "FROM scheduled_actions WHERE id = $1",
            action_id,
        )
        if row is None:
            return None
        return {
            "id": row["id"],
            "guild_id": row["guild_id"],
            "user_id": row["user_id"],
            "action_type": row["action_type"],
            "payload": json.loads(row["payload"]) if row["payload"] else {},
            "executed": row["executed"],
        }

    async def _run_due_actions(self) -> None:
        """Esegue le azioni scadute, al massimo AZIONI_PER_GIRO per giro."""
        for _ in range(AZIONI_PER_GIRO):
            if not await self._esegui_prossima_azione():
                return

    async def _esegui_prossima_azione(self) -> bool:
        """
        Prende UNA azione scaduta e la esegue nella propria transazione:
        un errore del database su un'azione non annulla i flag
        "eseguita" già scritti per le precedenti. Restituisce False se
        non c'è più nulla da fare.

        FOR UPDATE SKIP LOCKED: se un giorno ci fossero due processi,
        non eseguirebbero la stessa azione due volte.
        """
        from core.database import db

        async with db.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT id, guild_id, user_id, action_type, payload, attempts
                    FROM scheduled_actions
                    WHERE execute_at <= now()
                      AND (next_attempt_at IS NULL OR next_attempt_at <= now())
                      AND executed = FALSE AND failed_reason IS NULL
                    ORDER BY COALESCE(next_attempt_at, execute_at)
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                    """
                )
                if row is None:
                    return False

                errore = await self._chiama_handler(row)
                if errore is None:
                    await conn.execute(
                        "UPDATE scheduled_actions SET executed = TRUE, "
                        "executed_at = now() WHERE id = $1",
                        row["id"],
                    )
                else:
                    await self._registra_tentativo_fallito(conn, row, errore)
        return True

    async def _chiama_handler(self, row) -> str | None:
        """Restituisce None se l'azione è riuscita, altrimenti il motivo."""
        handler = self._handlers.get(row["action_type"])
        if handler is None:
            # Può essere un cog che non si è caricato a questo avvio:
            # si riprova, non si butta via l'azione (BUG-27).
            return f"nessun handler registrato per action_type='{row['action_type']}'"

        payload = json.loads(row["payload"]) if row["payload"] else {}
        try:
            await handler(row["guild_id"], row["user_id"], payload)
        except Exception as exc:  # CancelledError non è Exception: esce
            logger.exception(
                "Errore eseguendo l'azione pianificata id=%s (action_type='%s').",
                row["id"],
                row["action_type"],
            )
            return f"{type(exc).__name__}: {exc}"
        return None

    async def _registra_tentativo_fallito(self, conn, row, errore: str) -> None:
        """Rimanda l'azione con attesa crescente, o la abbandona al massimo dei tentativi."""
        tentativi = row["attempts"] + 1
        if tentativi >= MAX_TENTATIVI:
            logger.error(
                "Azione pianificata id=%s (action_type='%s') abbandonata dopo %d tentativi: %s",
                row["id"],
                row["action_type"],
                tentativi,
                errore,
            )
            await conn.execute(
                "UPDATE scheduled_actions SET attempts = $2, failed_reason = $3 WHERE id = $1",
                row["id"],
                tentativi,
                errore,
            )
            return

        attesa = attesa_prima_di_riprovare(tentativi)
        logger.warning(
            "Azione pianificata id=%s (action_type='%s') non riuscita (tentativo %d di %d): %s. "
            "Riprovo tra %s.",
            row["id"],
            row["action_type"],
            tentativi,
            MAX_TENTATIVI,
            errore,
            attesa,
        )
        await conn.execute(
            "UPDATE scheduled_actions SET attempts = $2, next_attempt_at = now() + $3 "
            "WHERE id = $1",
            row["id"],
            tentativi,
            attesa,
        )

    async def _giro(self) -> None:
        """
        BUG-8: un errore qui dentro (es. database irraggiungibile) non
        deve uscire dal loop — tasks.loop si ferma per sempre alla prima
        eccezione non gestita. Dopo un errore si aspetta prima del giro
        successivo, sempre di più se gli errori continuano.
        """
        try:
            await self._run_due_actions()
        except Exception:
            self._errori_di_fila += 1
            raddoppi = min(self._errori_di_fila, 10)
            pausa = min(PAUSA_BASE_ERRORE_SECONDI * 2**raddoppi, PAUSA_MASSIMA_ERRORE_SECONDI)
            logger.exception("Errore nel giro dello scheduler: riprovo tra %d secondi.", pausa)
            await asyncio.sleep(pausa)
        else:
            self._errori_di_fila = 0

    def start(self, bot: commands.Bot) -> None:
        """
        Avvia il loop periodico. Chiamato una volta sola da main.py
        dopo che bot e database sono pronti.
        """
        if self._loop_task is not None:
            return  # già avviato, non farlo due volte

        @tasks.loop(seconds=30)
        async def _loop():
            await self._giro()

        @_loop.before_loop
        async def _before():
            await attendi_bot_pronto(bot)

        self._loop_task = _loop
        _loop.start()
        logger.info("Scheduler avviato (controllo ogni 30 secondi).")


async def run_migrations(pool) -> None:
    """Chiamato da core/database.py in sequenza con le altre migration."""
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduled_actions (
            id          SERIAL PRIMARY KEY,
            guild_id    BIGINT NOT NULL,
            user_id     BIGINT NOT NULL,
            action_type TEXT NOT NULL,
            payload     JSONB NOT NULL DEFAULT '{}'::jsonb,
            execute_at  TIMESTAMPTZ NOT NULL,
            executed    BOOLEAN NOT NULL DEFAULT FALSE,
            executed_at TIMESTAMPTZ,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        -- Indice sulla query che il loop esegue ogni 30 secondi:
        -- senza, su una tabella grande diventerebbe una scansione
        -- completa ad ogni giro.
        CREATE INDEX IF NOT EXISTS idx_scheduled_actions_due
            ON scheduled_actions (execute_at)
            WHERE executed = FALSE;
        """
    )


def in_seconds(seconds: int) -> datetime:
    """Scorciatoia: 'adesso + N secondi', in UTC (Discord vuole sempre UTC)."""
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


# Istanza unica, condivisa da tutto il progetto.
scheduler = Scheduler()
