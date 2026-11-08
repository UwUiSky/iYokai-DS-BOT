"""
core/repositories/verify_blocchi_repo.py
========================================
L'ultimo blocco di ogni persona in ogni server (tabella `verify_blocchi`, migrazioni 0508 e 0531, D65, D67):
motivo e data, mai l'IP. Serve al ModMail: chi scrive in privato al bot dopo un blocco della verifica, o dopo
essere stato limitato come account rubato, apre un ticket con lo staff di quel server, con il motivo allegato.
Funzioni coperte: SPEC §4.2 (blocchi e ticket, D65), §6.20 (account rubato, D67)
"""

from __future__ import annotations

import asyncpg

ORE_VALIDITA = 24
MOTIVO_MAX = 300
MAX_RECENTI = 25  # quante voci entrano in un menu di Discord


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
            ON CONFLICT (user_id, guild_id) DO UPDATE SET motivo = EXCLUDED.motivo, creato_il = now()
            """,
            user_id, guild_id, motivo[:MOTIVO_MAX],
        )

    async def recenti(self, user_id: int) -> list:
        """(guild_id, motivo) dei blocchi di meno di un giorno fa, dal più recente; al massimo 25."""
        return await self._pool.fetch(
            """
            SELECT guild_id, motivo FROM verify_blocchi
            WHERE user_id = $1 AND creato_il > now() - make_interval(hours => $2)
            ORDER BY creato_il DESC LIMIT $3
            """,
            user_id, ORE_VALIDITA, MAX_RECENTI,
        )

    async def cancella_del_server(self, user_id: int, guild_id: int) -> None:
        """Toglie il blocco di quel server (la persona lì si è verificata, o ha aperto il ticket)."""
        await self._pool.execute("DELETE FROM verify_blocchi WHERE user_id = $1 AND guild_id = $2", user_id, guild_id)


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


verify_blocchi_repo = VerifyBlocchiRepository(pool_provider=_get_pool)
