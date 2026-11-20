"""
core/repositories/music_jukebox_repo.py
=======================================
Addebito e rimborso del jukebox (MUS-065). L'addebito e' una scrittura condizionata (`spend_coins_in`: toglie
solo se il saldo basta) nella stessa transazione del versamento alla cassa del server. Il rimborso rimette le
monete a chi le ha spese e le toglie dalla cassa, senza mai portarla sotto zero.
Funzioni coperte: SPEC §9 (catalogo MUS-065)
"""

from __future__ import annotations

import asyncpg

from core.repositories.guild_chest_repo import deposit_in
from core.repositories.leveling_repo import add_coins_in, spend_coins_in

REASON_JUKEBOX = "music_jukebox"
REASON_JUKEBOX_RIMBORSO = "music_jukebox_rimborso"


class MusicJukeboxRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def addebita(self, guild_id: int, user_id: int, prezzo: int) -> bool:
        """True se le monete sono passate dall'utente alla cassa; False (senza scrivere) se il saldo non basta."""
        if prezzo <= 0:
            raise ValueError("Il prezzo del jukebox deve essere positivo.")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                if not await spend_coins_in(conn, guild_id, user_id, prezzo):
                    return False
                await deposit_in(conn, guild_id, prezzo, REASON_JUKEBOX)
                return True

    async def rimborsa(self, guild_id: int, user_id: int, prezzo: int) -> None:
        """Rimette `prezzo` all'utente. La cassa rende quanto ha ancora (al massimo `prezzo`)."""
        if prezzo <= 0:
            raise ValueError("Il rimborso del jukebox deve essere positivo.")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                reso = await conn.fetchval(
                    """
                    UPDATE guild_chest c SET balance = c.balance - LEAST(c.balance, $2), updated_at = now()
                    FROM (SELECT balance FROM guild_chest WHERE guild_id = $1 FOR UPDATE) v
                    WHERE c.guild_id = $1
                    RETURNING v.balance - c.balance
                    """,
                    guild_id, prezzo,
                )
                if reso:
                    await conn.execute(
                        "INSERT INTO guild_chest_ledger (guild_id, amount, reason) VALUES ($1, $2, $3)",
                        guild_id, -reso, REASON_JUKEBOX_RIMBORSO,
                    )
                await add_coins_in(conn, guild_id, user_id, prezzo, classifica=False)


def _get_pool():
    from core.database import db
    return db.pool


music_jukebox_repo = MusicJukeboxRepository(pool_provider=_get_pool)
