"""
core/repositories/user_language_repo.py
=======================================
Lingua personale di un utente (tabella `user_language`, migrazione 0130, NF-06).
Una riga per utente; la cancellazione e l'esportazione passano dal registro dei dati.
"""

from __future__ import annotations

import asyncpg


class UserLanguageRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def get(self, user_id: int) -> str | None:
        return await self._pool.fetchval("SELECT language FROM user_language WHERE user_id = $1", user_id)

    async def set(self, user_id: int, language: str) -> None:
        await self._pool.execute(
            """
            INSERT INTO user_language (user_id, language) VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET language = EXCLUDED.language, updated_at = now()
            """,
            user_id,
            language,
        )

    async def clear(self, user_id: int) -> bool:
        esito = await self._pool.execute("DELETE FROM user_language WHERE user_id = $1", user_id)
        return esito.endswith(" 1")


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


user_language_repo = UserLanguageRepository(pool_provider=_get_pool)
