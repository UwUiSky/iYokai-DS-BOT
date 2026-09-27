"""
core/repositories/global_ban_repo.py
========================================
Persistenza del "ban globale" (SPEC.md §7.3) — solo un log di
propagazione, non una tabella di configurazione: l'opt-in per
server usa l'infrastruttura già esistente (`db.is_module_active_for_
guild`/`set_module_active_for_guild` su `guild_config`), stesso
meccanismo di attivazione modulo di ogni altro modulo del bot. Una
tabella di configurazione dedicata sarebbe stata un secondo
interruttore per dire la stessa cosa — complessità non richiesta.

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

        CREATE INDEX IF NOT EXISTS idx_global_ban_log_source
            ON global_ban_log (source_guild_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_global_ban_log_target
            ON global_ban_log (target_guild_id, created_at DESC);
        """
    )


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
