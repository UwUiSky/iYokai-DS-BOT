"""
core/repositories/global_ban_repo.py
========================================
Persistenza del "ban globale" (SPEC.md §7.3): il log di propagazione e,
per SIC-046, le due direzioni per server ("invia" e "ricevi"). L'adesione
alla rete usa l'infrastruttura già esistente (`db.is_module_active_for_
guild`/`set_module_active_for_guild` su `guild_config`); la tabella
`global_ban_direction` dice solo in quale direzione il server partecipa
(senza riga: in entrambe).

Vedi cogs/security/global_ban.py per il perché questo NON è il ban
globale via fingerprint/alt-detection descritto in SPEC.md §4.3 (che
resta bloccato, correttamente, sulla dipendenza da §4.2 non
costruita), ma una propagazione cross-server dello STESSO account
Discord, con opt-in reciproco esplicito.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class GlobalBanLogEntry:
    source_guild_id: int
    target_guild_id: int
    user_id: int
    reason: str | None
    created_at: datetime


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS global_ban_log (
            id                SERIAL PRIMARY KEY,
            source_guild_id   BIGINT NOT NULL,
            target_guild_id   BIGINT NOT NULL,
            user_id           BIGINT NOT NULL,
            reason            TEXT,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        -- Quando il ban propagato e' stato tolto (appello accolto).
        ALTER TABLE global_ban_log ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ;

        -- SIC-046: il server puo' inviare i propri ban, riceverli, o entrambe.
        CREATE TABLE IF NOT EXISTS global_ban_direction (
            guild_id     BIGINT PRIMARY KEY,
            send_bans    BOOLEAN NOT NULL DEFAULT TRUE,
            receive_bans BOOLEAN NOT NULL DEFAULT TRUE
        );

        CREATE INDEX IF NOT EXISTS idx_global_ban_log_source
            ON global_ban_log (source_guild_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_global_ban_log_target
            ON global_ban_log (target_guild_id, created_at DESC);
        """
    )


# Per quanti giorni si tengono le propagazioni nel registro: abbastanza per
# un appello, non per sempre (sono ID di persone).
GIORNI_REGISTRO = 365


class GlobalBanRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def log_propagation(
        self, source_guild_id: int, target_guild_id: int, user_id: int, reason: str | None
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO global_ban_log (source_guild_id, target_guild_id, user_id, reason)
            VALUES ($1, $2, $3, $4)
            """,
            source_guild_id,
            target_guild_id,
            user_id,
            reason,
        )
        await self._pool.execute(
            "DELETE FROM global_ban_log WHERE created_at < now() - make_interval(days => $1)",
            GIORNI_REGISTRO,
        )

    async def get_direction(self, guild_id: int) -> tuple[bool, bool]:
        """(invia, ricevi) del server; senza riga: entrambe."""
        row = await self._pool.fetchrow(
            "SELECT send_bans, receive_bans FROM global_ban_direction WHERE guild_id = $1", guild_id
        )
        return (True, True) if row is None else (row["send_bans"], row["receive_bans"])

    async def set_direction(self, guild_id: int, *, send: bool, receive: bool) -> None:
        await self._pool.execute(
            """
            INSERT INTO global_ban_direction (guild_id, send_bans, receive_bans)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE
                SET send_bans = EXCLUDED.send_bans, receive_bans = EXCLUDED.receive_bans
            """,
            guild_id, send, receive,
        )

    async def active_propagations(self, source_guild_id: int, user_id: int) -> list[int]:
        """I server in cui il ban di questo utente, partito da qui, e' ancora in piedi."""
        rows = await self._pool.fetch(
            """
            SELECT DISTINCT target_guild_id FROM global_ban_log
            WHERE source_guild_id = $1 AND user_id = $2 AND revoked_at IS NULL
            """,
            source_guild_id, user_id,
        )
        return [r["target_guild_id"] for r in rows]

    async def network_summary(self, user_id: int) -> tuple[int, datetime | None, datetime | None]:
        """
        SIC-044: da quanti server della rete l'utente ha un ban della Spam
        Trap ancora in piedi, e le date del primo e dell'ultimo. Mai i
        nomi dei server.
        """
        row = await self._pool.fetchrow(
            """
            SELECT COUNT(DISTINCT source_guild_id) AS server, MIN(created_at) AS primo, MAX(created_at) AS ultimo
            FROM global_ban_log WHERE user_id = $1 AND revoked_at IS NULL
            """,
            user_id,
        )
        return row["server"], row["primo"], row["ultimo"]

    async def mark_revoked(self, source_guild_id: int, user_id: int) -> None:
        await self._pool.execute(
            """
            UPDATE global_ban_log SET revoked_at = now()
            WHERE source_guild_id = $1 AND user_id = $2 AND revoked_at IS NULL
            """,
            source_guild_id, user_id,
        )

    async def get_recent_outgoing(self, guild_id: int, limit: int = 10) -> list[GlobalBanLogEntry]:
        """Ban che questo server ha INNESCATO (Spam Trap) e propagato
        verso altri server."""
        rows = await self._pool.fetch(
            """
            SELECT source_guild_id, target_guild_id, user_id, reason, created_at
            FROM global_ban_log
            WHERE source_guild_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            guild_id,
            limit,
        )
        return [_row_to_entry(r) for r in rows]

    async def get_recent_incoming(self, guild_id: int, limit: int = 10) -> list[GlobalBanLogEntry]:
        """Ban che questo server ha RICEVUTO da un altro server della
        rete di ban globali."""
        rows = await self._pool.fetch(
            """
            SELECT source_guild_id, target_guild_id, user_id, reason, created_at
            FROM global_ban_log
            WHERE target_guild_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            guild_id,
            limit,
        )
        return [_row_to_entry(r) for r in rows]


def _row_to_entry(row) -> GlobalBanLogEntry:
    return GlobalBanLogEntry(
        source_guild_id=row["source_guild_id"],
        target_guild_id=row["target_guild_id"],
        user_id=row["user_id"],
        reason=row["reason"],
        created_at=row["created_at"],
    )


def _get_pool():
    from core.database import db
    return db.pool


global_ban_repo = GlobalBanRepository(pool_provider=_get_pool)
