"""
core/repositories/moderation_repo.py
=======================================
Tutto l'accesso al database per il modulo di moderazione passa da
qui — coerente con la regola generale (vedi core/database.py): nessun
cog scrive SQL direttamente.

Case system: come funziona la numerazione
--------------------------------------------
Ogni azione di moderazione (warn, kick, ban...) diventa un "caso",
numerato PROGRESSIVAMENTE PER SERVER (il caso #1 del server A non ha
nulla a che fare con il caso #1 del server B — ogni server riparte
da 1). Per farlo in modo sicuro con scritture concorrenti (due
moderatori che bannano due persone nello stesso istante) serve una
tabella contatore con incremento ATOMICO dentro una transazione,
altrimenti due richieste simultanee potrebbero ricevere lo stesso
numero di caso.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import asyncpg


@dataclass(frozen=True)
class ModerationCase:
    case_number: int
    guild_id: int
    user_id: int
    moderator_id: int
    action_type: str
    reason: str | None
    duration_seconds: int | None
    active: bool
    created_at: datetime
    revoked_at: datetime | None
    revoked_by: int | None


@dataclass(frozen=True)
class ModerationNote:
    id: int
    guild_id: int
    user_id: int
    moderator_id: int
    note: str
    created_at: datetime


async def run_migrations(pool: asyncpg.Pool) -> None:
    """Chiamato da core/database.py in sequenza con le altre migration."""
    await pool.execute(
        """
        -- Contatore per-server dei numeri di caso. Una riga per
        -- guild, incrementata atomicamente ad ogni nuovo caso.
        CREATE TABLE IF NOT EXISTS moderation_case_counters (
            guild_id    BIGINT PRIMARY KEY,
            next_number INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS moderation_cases (
            id               SERIAL PRIMARY KEY,
            guild_id         BIGINT NOT NULL,
            case_number      INTEGER NOT NULL,
            user_id          BIGINT NOT NULL,
            moderator_id     BIGINT NOT NULL,
            action_type      TEXT NOT NULL,   -- 'warn','kick','ban','tempban','timeout'...
            reason           TEXT,
            duration_seconds INTEGER,         -- NULL = azione permanente
            active           BOOLEAN NOT NULL DEFAULT TRUE,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            revoked_at       TIMESTAMPTZ,
            revoked_by       BIGINT,
            UNIQUE (guild_id, case_number)
        );

        -- La query più frequente è "storico di un utente in un
        -- server": questo indice la serve direttamente.
        CREATE INDEX IF NOT EXISTS idx_moderation_cases_guild_user
            ON moderation_cases (guild_id, user_id);

        -- SEC-12: trovare i casi ATTIVI di un utente su TUTTI i
        -- server (es. "in quale server ha un ban attivo dello
        -- spam-trap chi mi ha appena scritto in DM") deve essere UNA
        -- query, non un giro su ogni server con cui il bot condivide
        -- una guild — con migliaia di server sarebbe una query per
        -- ogni singolo DM ricevuto.
        CREATE INDEX IF NOT EXISTS idx_moderation_cases_user_type_active
            ON moderation_cases (user_id, action_type)
            WHERE active = TRUE;

        CREATE TABLE IF NOT EXISTS moderation_notes (
            id           SERIAL PRIMARY KEY,
            guild_id     BIGINT NOT NULL,
            user_id      BIGINT NOT NULL,
            moderator_id BIGINT NOT NULL,
            note         TEXT NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_moderation_notes_guild_user
            ON moderation_notes (guild_id, user_id);
        """
    )


class ModerationRepository:
    """
    Un'istanza per pool (di solito una sola, condivisa — vedi
    `moderation_repo` in fondo al file). Non tiene stato proprio:
    ogni metodo apre/usa il pool passato al costruttore.
    """

    def __init__(self, pool_provider) -> None:
        """
        `pool_provider` è una funzione che restituisce il pool
        attuale (es. `lambda: db.pool`), non il pool direttamente:
        così se il pool viene riaperto (raro, ma capita nei test),
        il repository segue sempre quello corrente invece di
        restare agganciato a uno vecchio e chiuso.
        """
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def create_case(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int,
        action_type: str,
        reason: str | None = None,
        duration_seconds: int | None = None,
    ) -> int:
        """
        Crea un nuovo caso, con numerazione atomica. Restituisce il
        case_number assegnato.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # UPSERT del contatore + incremento atomico in una
                # sola query: evita la race condition di un
                # SELECT-poi-UPDATE separato, dove due richieste
                # concorrenti potrebbero leggere lo stesso valore
                # prima che l'una o l'altra scriva l'incremento.
                case_number = await conn.fetchval(
                    """
                    INSERT INTO moderation_case_counters (guild_id, next_number)
                    VALUES ($1, 2)
                    ON CONFLICT (guild_id) DO UPDATE
                        SET next_number = moderation_case_counters.next_number + 1
                    RETURNING next_number - 1
                    """,
                    guild_id,
                )

                await conn.execute(
                    """
                    INSERT INTO moderation_cases
                        (guild_id, case_number, user_id, moderator_id,
                         action_type, reason, duration_seconds)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    guild_id,
                    case_number,
                    user_id,
                    moderator_id,
                    action_type,
                    reason,
                    duration_seconds,
                )

        return case_number

    async def get_case(self, guild_id: int, case_number: int) -> ModerationCase | None:
        row = await self._pool.fetchrow(
            """
            SELECT case_number, guild_id, user_id, moderator_id, action_type,
                   reason, duration_seconds, active, created_at,
                   revoked_at, revoked_by
            FROM moderation_cases
            WHERE guild_id = $1 AND case_number = $2
            """,
            guild_id,
            case_number,
        )
        return _row_to_case(row) if row else None

    async def list_cases_for_user(
        self, guild_id: int, user_id: int, limit: int = 10, action_type: str | None = None
    ) -> list[ModerationCase]:
        rows = await self._pool.fetch(
            """
            SELECT case_number, guild_id, user_id, moderator_id, action_type,
                   reason, duration_seconds, active, created_at,
                   revoked_at, revoked_by
            FROM moderation_cases
            WHERE guild_id = $1 AND user_id = $2
              AND ($4::text IS NULL OR action_type = $4)
            ORDER BY case_number DESC
            LIMIT $3
            """,
            guild_id,
            user_id,
            limit,
            action_type,
        )
        return [_row_to_case(row) for row in rows]

    async def count_active_cases(self, guild_id: int, user_id: int, action_type: str) -> int:
        """Quanti casi attivi di un tipo ha un utente (es. i warn non tolti)."""
        return await self._pool.fetchval(
            "SELECT count(*) FROM moderation_cases "
            "WHERE guild_id = $1 AND user_id = $2 AND action_type = $3 AND active = TRUE",
            guild_id, user_id, action_type,
        )

    async def list_cases_by_moderator(
        self, guild_id: int, moderator_id: int, limit: int = 25, action_type: str | None = None
    ) -> list[ModerationCase]:
        """Casi fatti da un moderatore, dal più recente (MOD-041)."""
        rows = await self._pool.fetch(
            """
            SELECT case_number, guild_id, user_id, moderator_id, action_type,
                   reason, duration_seconds, active, created_at,
                   revoked_at, revoked_by
            FROM moderation_cases
            WHERE guild_id = $1 AND moderator_id = $2
              AND ($4::text IS NULL OR action_type = $4)
            ORDER BY case_number DESC
            LIMIT $3
            """,
            guild_id, moderator_id, limit, action_type,
        )
        return [_row_to_case(row) for row in rows]

    async def moderator_ranking(self, guild_id: int, limit: int = 10) -> list[tuple[int, int]]:
        """(moderatore, numero di azioni), dal più attivo (MOD-039)."""
        rows = await self._pool.fetch(
            """
            SELECT moderator_id, COUNT(*) AS n
            FROM moderation_cases
            WHERE guild_id = $1
            GROUP BY moderator_id
            ORDER BY n DESC, moderator_id
            LIMIT $2
            """,
            guild_id, limit,
        )
        return [(r["moderator_id"], r["n"]) for r in rows]

    async def warn_ranking(self, guild_id: int, limit: int = 10) -> list[tuple[int, int]]:
        """(utente, warn attivi), dal più avvisato (MOD-031)."""
        rows = await self._pool.fetch(
            """
            SELECT user_id, COUNT(*) AS n
            FROM moderation_cases
            WHERE guild_id = $1 AND action_type = 'warn' AND active = TRUE
            GROUP BY user_id
            ORDER BY n DESC, user_id
            LIMIT $2
            """,
            guild_id, limit,
        )
        return [(r["user_id"], r["n"]) for r in rows]

    async def update_case_reason(self, guild_id: int, case_number: int, reason: str) -> bool:
        """Cambia il motivo di un caso (MOD-037). False se il caso non esiste."""
        result = await self._pool.execute(
            "UPDATE moderation_cases SET reason = $3 WHERE guild_id = $1 AND case_number = $2",
            guild_id, case_number, reason,
        )
        return result.endswith(" 1")

    async def delete_case(self, guild_id: int, case_number: int) -> bool:
        """Elimina un caso (MOD-044). La numerazione non si riusa."""
        result = await self._pool.execute(
            "DELETE FROM moderation_cases WHERE guild_id = $1 AND case_number = $2",
            guild_id, case_number,
        )
        return result.endswith(" 1")

    async def get_latest_active_case(
        self, guild_id: int, user_id: int, action_type: str
    ) -> ModerationCase | None:
        """
        Trova l'ultimo caso ATTIVO di un certo tipo per un utente.
        Usato ad esempio da /modban unban per sapere quale caso "ban" (o
        "tempban") revocare quando qualcuno viene sbannato.
        """
        row = await self._pool.fetchrow(
            """
            SELECT case_number, guild_id, user_id, moderator_id, action_type,
                   reason, duration_seconds, active, created_at,
                   revoked_at, revoked_by
            FROM moderation_cases
            WHERE guild_id = $1 AND user_id = $2 AND action_type = $3
              AND active = TRUE
            ORDER BY case_number DESC
            LIMIT 1
            """,
            guild_id,
            user_id,
            action_type,
        )
        return _row_to_case(row) if row else None

    async def get_active_cases_for_user_across_guilds(
        self, user_id: int, action_type: str
    ) -> list[ModerationCase]:
        """
        Come get_latest_active_case, ma su TUTTI i server insieme in
        UNA query (indice idx_moderation_cases_user_type_active) — a
        differenza di quello, qui non serve sapere già in quale
        server cercare. Usato dallo spam-trap per capire, da un
        singolo DM, in quale server (o server) chi scrive ha un ban
        attivo dello spam-trap (SEC-12): senza questo, la stessa
        domanda richiederebbe una query per ogni server con cui il
        bot condivide una guild.
        """
        rows = await self._pool.fetch(
            """
            SELECT case_number, guild_id, user_id, moderator_id, action_type,
                   reason, duration_seconds, active, created_at,
                   revoked_at, revoked_by
            FROM moderation_cases
            WHERE user_id = $1 AND action_type = $2 AND active = TRUE
            ORDER BY case_number DESC
            """,
            user_id,
            action_type,
        )
        return [_row_to_case(row) for row in rows]

    async def revoke_case(
        self, guild_id: int, case_number: int, revoked_by: int
    ) -> bool:
        """
        Marca un caso come non più attivo (es. un ban è stato
        revocato con /modban unban). Restituisce True se una riga è stata
        effettivamente aggiornata, False se il caso non esisteva o
        era già inattivo — così il chiamante distingue "fatto" da
        "non c'era nulla da fare".
        """
        result = await self._pool.execute(
            """
            UPDATE moderation_cases
            SET active = FALSE, revoked_at = now(), revoked_by = $3
            WHERE guild_id = $1 AND case_number = $2 AND active = TRUE
            """,
            guild_id,
            case_number,
            revoked_by,
        )
        # asyncpg restituisce una stringa tipo "UPDATE 1" o "UPDATE 0"
        return result.endswith(" 1")

    async def revoke_active_cases_for_user(
        self, guild_id: int, user_id: int, action_type: str, revoked_by: int
    ) -> int:
        """
        Revoca TUTTI i casi attivi di un certo tipo per un utente in
        un server e restituisce quanti ne ha revocati. Serve quando
        un utente può avere più casi attivi dello stesso tipo (es.
        bannato due volte dallo spam-trap, BUG-24).
        """
        result = await self._pool.execute(
            """
            UPDATE moderation_cases
            SET active = FALSE, revoked_at = now(), revoked_by = $4
            WHERE guild_id = $1 AND user_id = $2 AND action_type = $3
              AND active = TRUE
            """,
            guild_id,
            user_id,
            action_type,
            revoked_by,
        )
        # asyncpg restituisce una stringa tipo "UPDATE 2".
        return int(result.split()[-1])

    async def add_note(
        self, guild_id: int, user_id: int, moderator_id: int, note: str
    ) -> int:
        row = await self._pool.fetchrow(
            """
            INSERT INTO moderation_notes (guild_id, user_id, moderator_id, note)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            guild_id,
            user_id,
            moderator_id,
            note,
        )
        return row["id"]

    async def list_notes_for_user(
        self, guild_id: int, user_id: int, limit: int = 20
    ) -> list[ModerationNote]:
        rows = await self._pool.fetch(
            """
            SELECT id, guild_id, user_id, moderator_id, note, created_at
            FROM moderation_notes
            WHERE guild_id = $1 AND user_id = $2
            ORDER BY created_at DESC, id DESC
            LIMIT $3
            """,
            guild_id,
            user_id,
            limit,
        )
        return [
            ModerationNote(
                id=r["id"],
                guild_id=r["guild_id"],
                user_id=r["user_id"],
                moderator_id=r["moderator_id"],
                note=r["note"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    async def delete_note(self, guild_id: int, note_id: int) -> bool:
        """Toglie una nota (MOD-054). Solo se è di questo server."""
        result = await self._pool.execute(
            "DELETE FROM moderation_notes WHERE guild_id = $1 AND id = $2", guild_id, note_id
        )
        return result.endswith(" 1")

    async def update_note(self, guild_id: int, note_id: int, testo: str) -> bool:
        """Cambia il testo di una nota (MOD-055)."""
        result = await self._pool.execute(
            "UPDATE moderation_notes SET note = $3 WHERE guild_id = $1 AND id = $2",
            guild_id, note_id, testo,
        )
        return result.endswith(" 1")

    async def delete_notes_for_user(self, guild_id: int, user_id: int) -> int:
        """Cancella tutte le note di un membro (MOD-056); quante."""
        result = await self._pool.execute(
            "DELETE FROM moderation_notes WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
        )
        return int(result.split()[-1])

    # ------------------------------------------------------------
    # Appelli contro i ban manuali (NF-30)
    # ------------------------------------------------------------
    async def create_appeal_if_allowed(
        self, guild_id: int, user_id: int, case_number: int | None, testo: str,
        attesa: timedelta,
    ) -> tuple[int | None, datetime | None]:
        """
        Crea l'appello solo se l'ultimo ha più di `attesa`: controllo e scrittura
        sotto lo stesso blocco (tre invii insieme valgono uno).
        Restituisce (id, None) se creato, (None, ora dell'ultimo) se bisogna attendere.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT pg_advisory_xact_lock($1, $2)", guild_id % 2**31, user_id % 2**31
                )
                ultimo = await conn.fetchval(
                    "SELECT MAX(creato_il) FROM ban_appelli WHERE guild_id = $1 AND user_id = $2",
                    guild_id, user_id,
                )
                if ultimo is not None and ultimo + attesa > datetime.now(timezone.utc):
                    return None, ultimo
                appello_id = await conn.fetchval(
                    """
                    INSERT INTO ban_appelli (guild_id, user_id, case_number, testo)
                    VALUES ($1, $2, $3, $4) RETURNING id
                    """,
                    guild_id, user_id, case_number, testo,
                )
                return appello_id, None

    async def close_open_appeals(self, guild_id: int, user_id: int, deciso_da: int) -> int:
        """Un unban chiude gli appelli ancora aperti dell'utente (come accettati)."""
        result = await self._pool.execute(
            """
            UPDATE ban_appelli SET stato = 'accettato', deciso_da = $3, deciso_il = now()
            WHERE guild_id = $1 AND user_id = $2 AND stato = 'aperto'
            """,
            guild_id, user_id, deciso_da,
        )
        return int(result.split()[-1])

    async def delete_appeal(self, appeal_id: int) -> None:
        """Toglie un appello che non è arrivato allo staff (non deve bloccare le 24 ore)."""
        await self._pool.execute("DELETE FROM ban_appelli WHERE id = $1", appeal_id)

    async def get_appeal(self, appeal_id: int) -> dict | None:
        row = await self._pool.fetchrow("SELECT * FROM ban_appelli WHERE id = $1", appeal_id)
        return dict(row) if row else None

    async def decide_appeal(self, appeal_id: int, stato: str, deciso_da: int) -> bool:
        """Chiude un appello ancora aperto; False se era già deciso (due click insieme)."""
        result = await self._pool.execute(
            """
            UPDATE ban_appelli SET stato = $2, deciso_da = $3, deciso_il = now()
            WHERE id = $1 AND stato = 'aperto'
            """,
            appeal_id, stato, deciso_da,
        )
        return result.endswith(" 1")

    async def list_appeals(self, guild_id: int, stato: str | None = None, limit: int = 15) -> list[dict]:
        rows = await self._pool.fetch(
            """
            SELECT * FROM ban_appelli
            WHERE guild_id = $1 AND ($2::text IS NULL OR stato = $2)
            ORDER BY creato_il DESC LIMIT $3
            """,
            guild_id, stato, limit,
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------
    # Ban temporaneo con rientro / isolamento (issue #138)
    # ------------------------------------------------------------
    async def save_tempban_state(
        self,
        guild_id: int,
        user_id: int,
        modo: str,
        ruoli: list[int],
        finisce_il: datetime,
        invito_codice: str | None = None,
        case_number: int | None = None,
        oauth_rientro: bool = False,
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO tempban_stato
                (guild_id, user_id, modo, ruoli, invito_codice, case_number, finisce_il,
                 oauth_rientro)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (guild_id, user_id) DO UPDATE
                SET modo = $3, ruoli = $4, invito_codice = $5, case_number = $6,
                    finisce_il = $7, scaduto = FALSE, oauth_rientro = $8
            """,
            guild_id, user_id, modo, ruoli, invito_codice, case_number, finisce_il,
            oauth_rientro,
        )

    async def set_tempban_state_case(self, guild_id: int, user_id: int, case_number: int) -> None:
        await self._pool.execute(
            "UPDATE tempban_stato SET case_number = $3 WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id, case_number,
        )

    async def cancel_tempban_jobs(self, guild_id: int, user_id: int) -> int:
        """
        Cancella le scadenze automatiche ancora in attesa per l'utente: dopo un
        unban, un appello accettato o un nuovo tempban non devono più scattare.
        """
        result = await self._pool.execute(
            """
            DELETE FROM scheduled_actions
            WHERE guild_id = $1 AND user_id = $2
              AND action_type = 'moderation_tempban_expire' AND executed = FALSE
            """,
            guild_id, user_id,
        )
        return int(result.split()[-1])

    async def get_tempban_state(self, guild_id: int, user_id: int) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM tempban_stato WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id,
        )
        return dict(row) if row else None

    async def mark_tempban_state_expired(self, guild_id: int, user_id: int) -> None:
        """Il ban è finito: al rientro l'utente riprende i ruoli salvati."""
        await self._pool.execute(
            "UPDATE tempban_stato SET scaduto = TRUE WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id,
        )

    async def delete_tempban_state(self, guild_id: int, user_id: int) -> None:
        await self._pool.execute(
            "DELETE FROM tempban_stato WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id,
        )


    # ------------------------------------------------------------
    # Mute con ruolo: a tempo, hardmute, rientro (MOD-014, 015, 021)
    # ------------------------------------------------------------
    async def save_mute_state(
        self,
        guild_id: int,
        user_id: int,
        hard: bool,
        ruoli: list[int],
        case_number: int | None,
        finisce_il: datetime | None,
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO mute_stato (guild_id, user_id, hard, ruoli, case_number, finisce_il)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (guild_id, user_id) DO UPDATE
                SET hard = $3, ruoli = $4, case_number = $5, finisce_il = $6
            """,
            guild_id, user_id, hard, ruoli, case_number, finisce_il,
        )

    async def get_mute_state(self, guild_id: int, user_id: int) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM mute_stato WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id,
        )
        return dict(row) if row else None

    async def delete_mute_state(self, guild_id: int, user_id: int) -> None:
        await self._pool.execute(
            "DELETE FROM mute_stato WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id,
        )

    async def list_mute_states(self, guild_id: int, limit: int = 25) -> list[dict]:
        """I mute in corso del server: prima quelli che finiscono prima, poi i senza fine."""
        rows = await self._pool.fetch(
            "SELECT * FROM mute_stato WHERE guild_id = $1 "
            "ORDER BY finisce_il NULLS LAST, user_id LIMIT $2",
            guild_id, limit,
        )
        return [dict(r) for r in rows]


def _row_to_case(row) -> ModerationCase:
    return ModerationCase(
        case_number=row["case_number"],
        guild_id=row["guild_id"],
        user_id=row["user_id"],
        moderator_id=row["moderator_id"],
        action_type=row["action_type"],
        reason=row["reason"],
        duration_seconds=row["duration_seconds"],
        active=row["active"],
        created_at=row["created_at"],
        revoked_at=row["revoked_at"],
        revoked_by=row["revoked_by"],
    )


def _get_pool():
    """Provider di default: usa il pool del singleton globale db."""
    from core.database import db
    return db.pool


# Istanza condivisa dal resto del progetto, agganciata al pool globale.
moderation_repo = ModerationRepository(pool_provider=_get_pool)
