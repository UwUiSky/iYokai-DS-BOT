"""
core/repositories/verify_blocchi_repo.py
========================================
L'ultimo blocco della verifica di ogni persona (tabella `verify_blocchi`, migrazione 0508, D65): server e
motivo, mai l'IP. Serve al ModMail: chi scrive in privato al bot dopo un blocco apre un ticket con lo staff
del server dove voleva entrare, con il motivo già allegato.
Funzioni coperte: SPEC §4.2 (blocchi e ticket, D65)
"""

from __future__ import annotations

import asyncpg

ORE_VALIDITA = 24
MOTIVO_MAX = 300


class VerifyBlocchiRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def registra(self, user_id: int, guild_id: int, motivo: str) -> None:
        await self._pool.execute(
            """
            INSERT INTO verify_blocchi (user_id, guild_id, motivo) VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE SET guild_id = EXCLUDED.guild_id, motivo = EXCLUDED.motivo, creato_il = now()
            """,
            user_id, guild_id, motivo[:MOTIVO_MAX],
        )

    async def recente(self, user_id: int):
        """(guild_id, motivo) dell'ultimo blocco, se di meno di un giorno fa."""
        return await self._pool.fetchrow(
            "SELECT guild_id, motivo FROM verify_blocchi WHERE user_id = $1 AND creato_il > now() - make_interval(hours => $2)",
            user_id, ORE_VALIDITA,
        )

    async def cancella(self, user_id: int) -> None:
        await self._pool.execute("DELETE FROM verify_blocchi WHERE user_id = $1", user_id)


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


verify_blocchi_repo = VerifyBlocchiRepository(pool_provider=_get_pool)
