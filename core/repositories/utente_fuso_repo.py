"""
core/repositories/utente_fuso_repo.py
=====================================
Il fuso orario che un utente ha scelto con `/utility lingua fuso:` (serve al menu «Orari nel mio fuso»).
Tabella: core/migrations/0544_compleanni_orari.sql.
Funzioni coperte: catalogo #128 UTL-104 (D69, B6)
"""

from __future__ import annotations

import asyncpg


class UtenteFusoRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def get(self, user_id: int) -> str | None:
        return await self._pool.fetchval("SELECT fuso FROM utente_fuso WHERE user_id = $1", user_id)

    async def set(self, user_id: int, fuso: str) -> None:
        await self._pool.execute(
            "INSERT INTO utente_fuso (user_id, fuso) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET fuso = $2",
            user_id, fuso,
        )

    async def remove(self, user_id: int) -> bool:
        return (await self._pool.execute("DELETE FROM utente_fuso WHERE user_id = $1", user_id)).endswith(" 1")


def _get_pool():
    from core.database import db

    return db.pool


utente_fuso_repo = UtenteFusoRepository(pool_provider=_get_pool)
