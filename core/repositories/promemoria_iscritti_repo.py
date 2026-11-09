"""
core/repositories/promemoria_iscritti_repo.py
=============================================
Chi si è iscritto a un promemoria pubblico con «Ricordalo anche a me» (massimo 25 per promemoria).
Tabella: core/migrations/0544_compleanni_orari.sql. Una serie = il promemoria e le sue ripetizioni.
Funzioni coperte: catalogo #128 UTL-100 (D69, B6)
"""

from __future__ import annotations

import asyncpg

MAX_ISCRITTI = 25


class PromemoriaIscrittiRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def iscrivi(self, serie: str, guild_id: int, user_id: int) -> str:
        """"ok", "gia" (già iscritto) o "pieno" (25)."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", serie)
            if await conn.fetchval("SELECT 1 FROM promemoria_iscritti WHERE serie = $1 AND user_id = $2", serie, user_id):
                return "gia"
            if await conn.fetchval("SELECT count(*) FROM promemoria_iscritti WHERE serie = $1", serie) >= MAX_ISCRITTI:
                return "pieno"
            await conn.execute(
                "INSERT INTO promemoria_iscritti (serie, guild_id, user_id) VALUES ($1, $2, $3)", serie, guild_id, user_id
            )
            return "ok"

    async def iscritti(self, serie: str) -> list[int]:
        righe = await self._pool.fetch("SELECT user_id FROM promemoria_iscritti WHERE serie = $1 ORDER BY creato_il", serie)
        return [r["user_id"] for r in righe]

    async def cancella_serie(self, serie: str) -> None:
        await self._pool.execute("DELETE FROM promemoria_iscritti WHERE serie = $1", serie)

    async def serie_attiva(self, serie: str, action_type: str) -> bool:
        """Il promemoria è ancora in coda? (dopo lo scatto un'iscrizione non servirebbe a niente)"""
        return bool(await self._pool.fetchval(
            "SELECT 1 FROM scheduled_actions WHERE action_type = $2 AND executed = FALSE AND payload->>'serie' = $1 LIMIT 1",
            serie, action_type,
        ))


def _get_pool():
    from core.database import db

    return db.pool


promemoria_iscritti_repo = PromemoriaIscrittiRepository(pool_provider=_get_pool)
