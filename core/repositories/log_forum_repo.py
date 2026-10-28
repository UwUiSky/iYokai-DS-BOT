"""
core/repositories/log_forum_repo.py
===================================
Tabelle log_forum_viste (forum scelto per canali o casi) e log_forum_post
(il post di ogni canale o caso).
Funzioni coperte: SPEC §8.17
"""

from __future__ import annotations

import asyncpg


class LogForumRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def imposta_forum(self, guild_id: int, dimensione: str, forum_id: int) -> None:
        """Sceglie il forum della dimensione. Cambiare forum scorda i post del vecchio."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO log_forum_viste (guild_id, dimensione, forum_id)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (guild_id, dimensione) DO UPDATE
                        SET forum_id = EXCLUDED.forum_id, updated_at = now()
                    """,
                    guild_id, dimensione, forum_id,
                )
                await conn.execute(
                    "DELETE FROM log_forum_post WHERE guild_id = $1 AND dimensione = $2",
                    guild_id, dimensione,
                )

    async def togli_forum(self, guild_id: int, dimensione: str) -> bool:
        """Spegne la vista. I post già creati restano su Discord, il bot li dimentica."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                esito = await conn.execute(
                    "DELETE FROM log_forum_viste WHERE guild_id = $1 AND dimensione = $2",
                    guild_id, dimensione,
                )
                await conn.execute(
                    "DELETE FROM log_forum_post WHERE guild_id = $1 AND dimensione = $2",
                    guild_id, dimensione,
                )
        return esito.endswith(" 1")

    async def forum_del_server(self, guild_id: int) -> dict[str, int]:
        """Dimensione -> forum, per i soli forum scelti dal server."""
        righe = await self._pool.fetch(
            "SELECT dimensione, forum_id FROM log_forum_viste WHERE guild_id = $1", guild_id
        )
        return {r["dimensione"]: r["forum_id"] for r in righe}

    async def post_di(self, guild_id: int, dimensione: str, chiave: int) -> int | None:
        return await self._pool.fetchval(
            "SELECT thread_id FROM log_forum_post WHERE guild_id = $1 AND dimensione = $2 AND chiave = $3",
            guild_id, dimensione, chiave,
        )

    async def salva_post(self, guild_id: int, dimensione: str, chiave: int, thread_id: int) -> None:
        await self._pool.execute(
            """
            INSERT INTO log_forum_post (guild_id, dimensione, chiave, thread_id)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, dimensione, chiave) DO UPDATE SET thread_id = EXCLUDED.thread_id
            """,
            guild_id, dimensione, chiave, thread_id,
        )

    async def dimentica_post(self, guild_id: int, dimensione: str, chiave: int) -> None:
        await self._pool.execute(
            "DELETE FROM log_forum_post WHERE guild_id = $1 AND dimensione = $2 AND chiave = $3",
            guild_id, dimensione, chiave,
        )

    async def conta_post(self, guild_id: int, dimensione: str) -> int:
        return await self._pool.fetchval(
            "SELECT count(*) FROM log_forum_post WHERE guild_id = $1 AND dimensione = $2",
            guild_id, dimensione,
        )
