"""
core/repositories/blacklist_repo.py
======================================
Blacklist globale (SPEC.md §17.4 utenti, §17.5 server). Cache su
entrambi i controlli (BoundedCache, stesso principio già usato per
is_module_active_for_guild) — is_user_blacklisted()/
is_guild_blacklisted() girano su OGNI interazione del bot intero
(vedi core/blacklist_tree.py), non solo per un modulo specifico:
senza cache sarebbe una query su ogni singolo comando, ogni singolo
server, sempre.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg

from core.bounded_cache import BoundedCache


@dataclass(frozen=True)
class BlacklistEntry:
    id: int
    reason: str | None
    added_by: int
    added_at: datetime


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS user_blacklist (
            user_id    BIGINT PRIMARY KEY,
            reason     TEXT,
            added_by   BIGINT NOT NULL,
            added_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS guild_blacklist (
            guild_id   BIGINT PRIMARY KEY,
            reason     TEXT,
            added_by   BIGINT NOT NULL,
            added_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )


class BlacklistRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider
        self._user_cache: BoundedCache[int, bool] = BoundedCache(max_size=50_000)
        self._guild_cache: BoundedCache[int, bool] = BoundedCache(max_size=10_000)

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ================================================================
    # Utenti
    # ================================================================
    async def add_user(self, user_id: int, reason: str | None, added_by: int) -> None:
        await self._pool.execute(
            """
            INSERT INTO user_blacklist (user_id, reason, added_by)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE
                SET reason = EXCLUDED.reason, added_by = EXCLUDED.added_by, added_at = now()
            """,
            user_id,
            reason,
            added_by,
        )
        self._user_cache.delete(user_id)

    async def remove_user(self, user_id: int) -> bool:
        result = await self._pool.execute(
            "DELETE FROM user_blacklist WHERE user_id = $1", user_id
        )
        self._user_cache.delete(user_id)
        return result.endswith(" 1")

    async def is_user_blacklisted(self, user_id: int) -> bool:
        cached = self._user_cache.get(user_id)
        if cached is not None:
            return cached

        row = await self._pool.fetchrow(
            "SELECT 1 FROM user_blacklist WHERE user_id = $1", user_id
        )
        risultato = row is not None
        self._user_cache.set(user_id, risultato)
        return risultato

    async def list_users(self, limit: int = 100) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT * FROM user_blacklist ORDER BY added_at DESC LIMIT $1", limit
        )
        return [dict(r) for r in rows]

    # ================================================================
    # Server
    # ================================================================
    async def add_guild(self, guild_id: int, reason: str | None, added_by: int) -> None:
        await self._pool.execute(
            """
            INSERT INTO guild_blacklist (guild_id, reason, added_by)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE
                SET reason = EXCLUDED.reason, added_by = EXCLUDED.added_by, added_at = now()
            """,
            guild_id,
            reason,
            added_by,
        )
        self._guild_cache.delete(guild_id)

    async def remove_guild(self, guild_id: int) -> bool:
        result = await self._pool.execute(
            "DELETE FROM guild_blacklist WHERE guild_id = $1", guild_id
        )
        self._guild_cache.delete(guild_id)
        return result.endswith(" 1")

    async def is_guild_blacklisted(self, guild_id: int) -> bool:
        cached = self._guild_cache.get(guild_id)
        if cached is not None:
            return cached

        row = await self._pool.fetchrow(
            "SELECT 1 FROM guild_blacklist WHERE guild_id = $1", guild_id
        )
        risultato = row is not None
        self._guild_cache.set(guild_id, risultato)
        return risultato

    async def list_guilds(self, limit: int = 100) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT * FROM guild_blacklist ORDER BY added_at DESC LIMIT $1", limit
        )
        return [dict(r) for r in rows]


def _get_pool():
    from core.database import db
    return db.pool


blacklist_repo = BlacklistRepository(pool_provider=_get_pool)
