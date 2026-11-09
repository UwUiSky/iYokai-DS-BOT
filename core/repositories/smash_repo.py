"""
core/repositories/smash_repo.py
===============================
Voti settimanali di «Smash or pass»: uno a testa per personaggio e settimana (la prima scelta resta).
Tabella: core/migrations/0577_suoni_ruoli_smash.sql.
Funzioni coperte: SPEC §16 (FUN-021; B11 di #131)
"""

from __future__ import annotations

import asyncpg


class SmashRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def vota(self, guild_id: int, settimana: str, personaggio: str, user_id: int, scelta: str) -> bool:
        """Vero se è il primo voto di questa persona su questo personaggio nella settimana."""
        riga = await self._pool.fetchval(
            "INSERT INTO smash_voti (guild_id, settimana, personaggio, user_id, scelta) VALUES ($1, $2, $3, $4, $5) "
            "ON CONFLICT DO NOTHING RETURNING 1",
            guild_id, settimana, personaggio, user_id, scelta,
        )
        return riga is not None

    async def conteggio(self, guild_id: int, settimana: str, personaggio: str) -> tuple[int, int]:
        """(smash, pass) del server per il personaggio in quella settimana."""
        r = await self._pool.fetchrow(
            "SELECT count(*) FILTER (WHERE scelta = 'smash')::int AS s, count(*) FILTER (WHERE scelta = 'pass')::int AS p "
            "FROM smash_voti WHERE guild_id = $1 AND settimana = $2 AND personaggio = $3",
            guild_id, settimana, personaggio,
        )
        return r["s"], r["p"]


def _get_pool():
    from core.database import db

    return db.pool


smash_repo = SmashRepository(pool_provider=_get_pool)
