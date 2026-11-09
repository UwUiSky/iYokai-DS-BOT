"""
core/repositories/tag_inneschi_repo.py
======================================
Inneschi dei tag: al massimo 25 per server (conteggio e scrittura sotto lo stesso blocco), uno solo per tag, tipo e valore.
Tabella: core/migrations/0563_tag_inneschi.sql.
Funzioni coperte: catalogo #128 UTL-047..050, 052, 054 (D69, B27)
"""

from __future__ import annotations

import asyncpg

from core.repositories.tetto_server import tetto_per_server
from core.tag_inneschi_logic import MAX_INNESCHI

_COLONNE = "id, guild_id, tag, tipo, valore, canale_id, escludi, creato_da"


class TagInneschiRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def aggiungi(self, guild_id: int, tag: str, tipo: str, valore: str, canale_id: int | None, escludi: str,
                       creato_da: int) -> tuple[str, int | None]:
        """("ok", id), ("esiste", None) o ("pieno", None)."""
        async with tetto_per_server(self._pool, "tag_inneschi", guild_id) as conn:
            if await conn.fetchval("SELECT count(*) FROM tag_inneschi WHERE guild_id = $1", guild_id) >= MAX_INNESCHI:
                return "pieno", None
            nuovo = await conn.fetchval(
                "INSERT INTO tag_inneschi (guild_id, tag, tipo, valore, canale_id, escludi, creato_da) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7) ON CONFLICT (guild_id, tag, tipo, valore) DO NOTHING RETURNING id",
                guild_id, tag, tipo, valore, canale_id, escludi, creato_da)
        return ("ok", nuovo) if nuovo else ("esiste", None)

    async def elenco(self, guild_id: int) -> list[asyncpg.Record]:
        return await self._pool.fetch(f"SELECT {_COLONNE} FROM tag_inneschi WHERE guild_id = $1 ORDER BY id", guild_id)

    async def per_tipo(self, guild_id: int, tipo: str) -> list[asyncpg.Record]:
        return await self._pool.fetch(f"SELECT {_COLONNE} FROM tag_inneschi WHERE guild_id = $1 AND tipo = $2 ORDER BY id", guild_id, tipo)

    async def prendi(self, guild_id: int, innesco_id: int) -> asyncpg.Record | None:
        return await self._pool.fetchrow(f"SELECT {_COLONNE} FROM tag_inneschi WHERE guild_id = $1 AND id = $2", guild_id, innesco_id)

    async def prendi_per_id(self, innesco_id: int) -> asyncpg.Record | None:
        """Per lo scheduler, che non sa il server: l'azione porta solo l'id."""
        return await self._pool.fetchrow(f"SELECT {_COLONNE} FROM tag_inneschi WHERE id = $1", innesco_id)

    async def bottone(self, guild_id: int, embed: str, posizione: int) -> asyncpg.Record | None:
        return await self._pool.fetchrow(
            f"SELECT {_COLONNE} FROM tag_inneschi WHERE guild_id = $1 AND tipo = 'bottone' AND valore = $2 ORDER BY id LIMIT 1",
            guild_id, f"{embed}:{posizione}")

    async def togli(self, guild_id: int, innesco_id: int) -> bool:
        return await self._pool.execute("DELETE FROM tag_inneschi WHERE guild_id = $1 AND id = $2", guild_id, innesco_id) != "DELETE 0"

    async def togli_per_tag(self, guild_id: int, tag: str) -> int:
        return int((await self._pool.execute("DELETE FROM tag_inneschi WHERE guild_id = $1 AND tag = $2", guild_id, tag)).split()[-1])

    async def togli_per_canale(self, guild_id: int, canale_id: int) -> int:
        return int((await self._pool.execute("DELETE FROM tag_inneschi WHERE guild_id = $1 AND canale_id = $2", guild_id, canale_id)).split()[-1])


def _get_pool():
    from core.database import db

    return db.pool


tag_inneschi_repo = TagInneschiRepository(pool_provider=_get_pool)
