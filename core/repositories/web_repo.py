"""
core/repositories/web_repo.py
=============================
Cache delle città (Nominatim) e impostazioni del gruppo /web per server.
Tabelle: core/migrations/0540_web_servizi.sql.
Funzioni coperte: catalogo #128 UTL-213, 208 (D69, B2)
"""

from __future__ import annotations

import asyncpg

GIORNI_CACHE_LUOGHI = 90


class WebRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def luogo(self, testo: str) -> tuple[float, float, str] | None:
        riga = await self._pool.fetchrow(
            "SELECT lat, lon, nome FROM web_luoghi_cache WHERE testo = $1 "
            "AND creato_il > now() - make_interval(days => $2)",
            testo, GIORNI_CACHE_LUOGHI,
        )
        return (riga["lat"], riga["lon"], riga["nome"]) if riga else None

    async def salva_luogo(self, testo: str, lat: float, lon: float, nome: str) -> None:
        await self._pool.execute(
            "INSERT INTO web_luoghi_cache (testo, lat, lon, nome) VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (testo) DO UPDATE SET lat = $2, lon = $3, nome = $4, creato_il = now()",
            testo, lat, lon, nome,
        )

    async def accorcia_attivo(self, guild_id: int) -> bool:
        riga = await self._pool.fetchval("SELECT accorcia_attivo FROM web_impostazioni WHERE guild_id = $1", guild_id)
        return bool(riga)


def _get_pool():
    from core.database import db

    return db.pool


web_repo = WebRepository(pool_provider=_get_pool)
