"""
core/repositories/top_settimanale_repo.py
=========================================
Canale della top 10 settimanale e ultima settimana già annunciata (LIV-061). L'ultima settimana annunciata rende
l'annuncio unico anche con riavvii e tick ripetuti.
Funzioni coperte: LIV-061
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfTopSettimanale:
    guild_id: int
    channel_id: int
    ultima_annunciata: str | None


class TopSettimanaleRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self):
        return self._pool_provider()

    async def imposta(self, guild_id: int, channel_id: int, gia_coperta: str) -> None:
        """Alla prima attivazione la settimana appena finita conta come già annunciata: il primo annuncio è quello dopo."""
        await self._pool.execute(
            """
            INSERT INTO top_settimanale_conf (guild_id, channel_id, ultima_annunciata) VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE SET channel_id = EXCLUDED.channel_id
            """,
            guild_id, channel_id, gia_coperta,
        )

    async def togli(self, guild_id: int) -> bool:
        return (await self._pool.execute("DELETE FROM top_settimanale_conf WHERE guild_id = $1", guild_id)).endswith(" 1")

    async def tutte(self) -> list[ConfTopSettimanale]:
        righe = await self._pool.fetch("SELECT guild_id, channel_id, ultima_annunciata FROM top_settimanale_conf")
        return [ConfTopSettimanale(r["guild_id"], r["channel_id"], r["ultima_annunciata"]) for r in righe]

    async def leggi(self, guild_id: int) -> ConfTopSettimanale | None:
        r = await self._pool.fetchrow(
            "SELECT guild_id, channel_id, ultima_annunciata FROM top_settimanale_conf WHERE guild_id = $1", guild_id
        )
        return ConfTopSettimanale(r["guild_id"], r["channel_id"], r["ultima_annunciata"]) if r else None

    async def segna_annunciata(self, guild_id: int, settimana: str) -> None:
        await self._pool.execute(
            "UPDATE top_settimanale_conf SET ultima_annunciata = $2 WHERE guild_id = $1", guild_id, settimana
        )


def _pool():
    from core.database import db

    return db.pool


top_settimanale_repo = TopSettimanaleRepository(pool_provider=_pool)
