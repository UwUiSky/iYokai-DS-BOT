"""
core/repositories/battaglie_repo.py
===================================
Statistiche delle battaglie a turni (vinte e perse per server e utente). Le due righe di un incontro si
scrivono insieme, in una sola transazione.
Funzioni coperte: FUN-019
"""

from __future__ import annotations

import asyncpg


class BattaglieRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def registra(self, guild_id: int, vincitore_id: int, perdente_id: int) -> None:
        if vincitore_id == perdente_id:
            raise ValueError("Vincitore e perdente coincidono.")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO fun_battaglie_stat (guild_id, user_id, vinte) VALUES ($1, $2, 1) "
                    "ON CONFLICT (guild_id, user_id) DO UPDATE SET vinte = fun_battaglie_stat.vinte + 1",
                    guild_id, vincitore_id,
                )
                await conn.execute(
                    "INSERT INTO fun_battaglie_stat (guild_id, user_id, perse) VALUES ($1, $2, 1) "
                    "ON CONFLICT (guild_id, user_id) DO UPDATE SET perse = fun_battaglie_stat.perse + 1",
                    guild_id, perdente_id,
                )

    async def statistiche(self, guild_id: int, user_id: int) -> tuple[int, int]:
        riga = await self._pool.fetchrow(
            "SELECT vinte, perse FROM fun_battaglie_stat WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
        )
        return (riga["vinte"], riga["perse"]) if riga else (0, 0)

    async def classifica(self, guild_id: int, limite: int = 10) -> list[tuple[int, int, int]]:
        righe = await self._pool.fetch(
            "SELECT user_id, vinte, perse FROM fun_battaglie_stat WHERE guild_id = $1 AND (vinte > 0 OR perse > 0) "
            "ORDER BY vinte DESC, perse ASC, user_id LIMIT $2", guild_id, min(max(limite, 1), 25),
        )
        return [(r["user_id"], r["vinte"], r["perse"]) for r in righe]


def _get_pool():
    from core.database import db

    return db.pool


battaglie_repo = BattaglieRepository(pool_provider=_get_pool)
