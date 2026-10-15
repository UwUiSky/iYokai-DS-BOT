"""
core/repositories/log_eventi_repo.py
====================================
Interruttori dei singoli eventi di log spenti per ogni server (LOG-017).
Ogni evento lo chiede prima di scrivere: si tiene in memoria e si butta
a ogni modifica (un solo processo del bot).
Funzioni coperte: SPEC §8.19 (LOG-017)
"""

from __future__ import annotations

import asyncpg

from core.bounded_cache import BoundedCache
from core.log_eventi_logic import INTERRUTTORI, acceso


class LogEventiRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider
        self._cache: BoundedCache[int, frozenset[str]] = BoundedCache(5000)

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def spenti(self, guild_id: int) -> frozenset[str]:
        noti = self._cache.get(guild_id)
        if noti is not None:
            return noti
        righe = await self._pool.fetch(
            "SELECT interruttore FROM log_eventi_spenti WHERE guild_id=$1", guild_id
        )
        noti = frozenset(r["interruttore"] for r in righe if r["interruttore"] in INTERRUTTORI)
        self._cache.set(guild_id, noti)
        return noti

    async def evento_acceso(self, guild_id: int, evento: str) -> bool:
        return acceso(evento, await self.spenti(guild_id))

    async def imposta(self, guild_id: int, spenti: frozenset[str]) -> None:
        """Sostituisce gli interruttori spenti del server."""
        assert spenti <= frozenset(INTERRUTTORI)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM log_eventi_spenti WHERE guild_id=$1", guild_id)
                await conn.executemany(
                    "INSERT INTO log_eventi_spenti (guild_id, interruttore) VALUES ($1, $2)",
                    [(guild_id, chiave) for chiave in sorted(spenti)],
                )
        self._cache.delete(guild_id)


def _get_pool():
    from core.database import db
    return db.pool


log_eventi_repo = LogEventiRepository(pool_provider=_get_pool)
