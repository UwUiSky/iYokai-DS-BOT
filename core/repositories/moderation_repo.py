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
from datetime import datetime

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
        self, guild_id: int, user_id: int, limit: int = 10
    ) -> list[ModerationCase]:
        rows = await self._pool.fetch(
            """
            SELECT case_number, guild_id, user_id, moderator_id, action_type,
                   reason, duration_seconds, active, created_at,
                   revoked_at, revoked_by
            FROM moderation_cases
            WHERE guild_id = $1 AND user_id = $2
            ORDER BY case_number DESC
            LIMIT $3
            """,
            guild_id,
            user_id,
            limit,
        )
        return [_row_to_case(row) for row in rows]

    async def get_latest_active_case(
        self, guild_id: int, user_id: int, action_type: str
    ) -> ModerationCase | None:
        """
        Trova l'ultimo caso ATTIVO di un certo tipo per un utente.
        Usato ad esempio da /unban per sapere quale caso "ban" (o
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

    async def revoke_case(
        self, guild_id: int, case_number: int, revoked_by: int
    ) -> bool:
        """
        Marca un caso come non più attivo (es. un ban è stato
        revocato con /unban). Restituisce True se una riga è stata
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
            ORDER BY created_at DESC
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
