"""
core/repositories/leveling_ruoli_classifica_repo.py
===================================================
I ruoli di classifica di un server: uno per fascia (primo, primi 3, primi 10).
Funzioni coperte: SPEC §15 (LIV-044, 045; catalogo #124)
"""

from __future__ import annotations

import asyncpg

from core.database import db
from core.leveling_ruoli_classifica_logic import FASCE


class LevelingRuoliClassificaRepository:
    def __init__(self, pool_provider=lambda: db.pool) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def imposta(self, guild_id: int, fascia: int, role_id: int) -> None:
        if fascia not in FASCE:
            raise ValueError(f"Fascia sconosciuta: {fascia}")
        await self._pool.execute(
            "INSERT INTO leveling_ruoli_classifica (guild_id, fascia, role_id) VALUES ($1, $2, $3) "
            "ON CONFLICT (guild_id, fascia) DO UPDATE SET role_id = EXCLUDED.role_id",
            guild_id, fascia, role_id,
        )

    async def togli(self, guild_id: int, fascia: int) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM leveling_ruoli_classifica WHERE guild_id = $1 AND fascia = $2", guild_id, fascia
        )
        return esito != "DELETE 0"

    async def elenco(self, guild_id: int) -> dict[int, int]:
        """{fascia: ruolo}"""
        righe = await self._pool.fetch(
            "SELECT fascia, role_id FROM leveling_ruoli_classifica WHERE guild_id = $1", guild_id
        )
        return {r["fascia"]: r["role_id"] for r in righe}

    async def server_con_ruoli(self) -> list[int]:
        return [r["guild_id"] for r in await self._pool.fetch(
            "SELECT DISTINCT guild_id FROM leveling_ruoli_classifica ORDER BY guild_id"
        )]


leveling_ruoli_classifica_repo = LevelingRuoliClassificaRepository()
