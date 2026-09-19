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
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from discord.ext import commands, tasks

logger = logging.getLogger("iyokai.scheduler")

# Firma di un handler: riceve guild_id, user_id, e il payload salvato
# al momento della pianificazione (dati specifici dell'azione, es.
# {"reason": "..."} per un tempban).
ActionHandler = Callable[[int, int, dict], Awaitable[None]]


class Scheduler:
    """
    Un'unica istanza condivisa (vedi `scheduler` in fondo al file).
    Gli handler si registrano per action_type; il loop periodico li
    invoca quando un'azione di quel tipo scade.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, ActionHandler] = {}
        self._loop_task: tasks.Loop | None = None

    def register_handler(self, action_type: str, handler: ActionHandler) -> None:
        """
        Registra la funzione da chiamare quando un'azione di questo
        tipo scade. Un solo handler per action_type: se un cog
        prova a registrarne due con lo stesso nome, è un errore di
        programmazione e va segnalato subito, non ignorato.
        """
        if action_type in self._handlers:
            raise ValueError(
                f"Handler già registrato per action_type='{action_type}'"
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
            WHERE user_id = $1 AND action_type = $2 AND executed = FALSE
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
        """
        Interrogazione periodica: trova le azioni scadute e non
        ancora eseguite, le esegue, le marca come eseguite.

        FOR UPDATE SKIP LOCKED: se in futuro ci fosse più di un
        processo che esegue questo loop (non è il caso oggi, un solo
        processo iYokai Main), questo evita che due processi
        eseguano la stessa azione due volte.
        """
        from core.database import db

        async with db.pool.acquire() as conn:
            async with conn.transaction():
                rows = await conn.fetch(
                    """
                    SELECT id, guild_id, user_id, action_type, payload
                    FROM scheduled_actions
                    WHERE execute_at <= now() AND executed = FALSE
                    ORDER BY execute_at
                    LIMIT 50
                    FOR UPDATE SKIP LOCKED
                    """
                )

                for row in rows:
                    handler = self._handlers.get(row["action_type"])
                    if handler is None:
                        logger.warning(
                            "Nessun handler registrato per action_type='%s' "
                            "(scheduled_actions.id=%s) — azione saltata, "
                            "resta 'da eseguire'.",
                            row["action_type"],
                            row["id"],
                        )
                        continue

                    payload = json.loads(row["payload"]) if row["payload"] else {}
                    try:
                        await handler(row["guild_id"], row["user_id"], payload)
                    except Exception:
                        logger.exception(
                            "Errore eseguendo l'azione pianificata id=%s "
                            "(action_type='%s'). Verrà ritentata al giro "
                            "successivo.",
                            row["id"],
                            row["action_type"],
                        )
                        # Non marchiamo come eseguita: un errore
                        # temporaneo (es. Discord irraggiungibile un
                        # istante) non deve far perdere per sempre
                        # l'azione pianificata.
                        continue

                    await conn.execute(
                        "UPDATE scheduled_actions SET executed = TRUE, "
                        "executed_at = now() WHERE id = $1",
                        row["id"],
                    )

    def start(self, bot: commands.Bot) -> None:
        """
        Avvia il loop periodico. Chiamato una volta sola da main.py
        dopo che bot e database sono pronti.
        """
        if self._loop_task is not None:
            return  # già avviato, non farlo due volte

        @tasks.loop(seconds=30)
        async def _loop():
            await self._run_due_actions()

        @_loop.before_loop
        async def _before():
            await bot.wait_until_ready()

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
