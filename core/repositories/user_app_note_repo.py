"""
core/repositories/user_app_note_repo.py
=======================================
Note e liste personali di iYokai App (tabella `user_app_notes`, migrazione 0360, SPEC B.4).
Una riga per voce; la cancellazione e l'esportazione passano dal registro dei dati.
"""

from __future__ import annotations

import asyncpg

MAX_VOCI_PER_UTENTE = 100


class UserAppNoteRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def aggiungi(self, user_id: int, lista: str, testo: str, massimo: int = MAX_VOCI_PER_UTENTE) -> int | None:
        """Il numero della voce nuova, o None se l'utente ha già `massimo` voci. Due richieste insieme non superano il tetto."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1)", user_id)
                presenti = await conn.fetchval("SELECT count(*) FROM user_app_notes WHERE user_id = $1", user_id)
                if presenti >= massimo:
                    return None
                return await conn.fetchval(
                    "INSERT INTO user_app_notes (user_id, lista, testo) VALUES ($1, $2, $3) RETURNING id",
                    user_id, lista, testo,
                )

    async def elenco(self, user_id: int, lista: str, limite: int = 25) -> list[asyncpg.Record]:
        return await self._pool.fetch(
            "SELECT id, testo FROM user_app_notes WHERE user_id = $1 AND lista = $2 ORDER BY id LIMIT $3",
            user_id, lista, limite,
        )

    async def liste(self, user_id: int) -> list[asyncpg.Record]:
        """Le liste dell'utente con quante voci hanno (la lista vuota sono le note)."""
        return await self._pool.fetch(
            "SELECT lista, count(*) AS voci FROM user_app_notes WHERE user_id = $1 GROUP BY lista ORDER BY lista",
            user_id,
        )

    async def rimuovi(self, user_id: int, numero: int) -> bool:
        """Toglie la voce solo se è dell'utente."""
        esito = await self._pool.execute("DELETE FROM user_app_notes WHERE id = $1 AND user_id = $2", numero, user_id)
        return esito.endswith(" 1")


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


user_app_note_repo = UserAppNoteRepository(pool_provider=_get_pool)
