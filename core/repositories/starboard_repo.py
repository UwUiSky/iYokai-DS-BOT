"""
core/repositories/starboard_repo.py
===================================
Configurazione e messaggi già in bacheca (NF-08). Tabelle:
core/migrations/0081_starboard.sql.
Funzioni coperte: SPEC §22 (NF-08)
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg


@dataclass(frozen=True)
class StarboardConfig:
    guild_id: int
    channel_id: int
    threshold: int
    emoji: str
    enabled: bool
    allow_nsfw: bool
    self_star: bool


@dataclass(frozen=True)
class StarboardPost:
    source_message_id: int
    board_message_id: int | None
    stars: int


class StarboardRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def get_config(self, guild_id: int) -> StarboardConfig | None:
        r = await self._pool.fetchrow(
            "SELECT guild_id, channel_id, threshold, emoji, enabled, allow_nsfw, self_star "
            "FROM starboard_config WHERE guild_id = $1",
            guild_id,
        )
        return None if r is None else StarboardConfig(**dict(r))

    async def set_config(
        self, guild_id: int, channel_id: int, threshold: int, emoji: str,
        *, allow_nsfw: bool | None = None, self_star: bool | None = None,
    ) -> None:
        """None su `allow_nsfw` / `self_star` = lascia il valore che c'è (o il predefinito, falso)."""
        await self._pool.execute(
            """
            INSERT INTO starboard_config (guild_id, channel_id, threshold, emoji, enabled, allow_nsfw, self_star)
            VALUES ($1, $2, $3, $4, TRUE, COALESCE($5, FALSE), COALESCE($6, FALSE))
            ON CONFLICT (guild_id) DO UPDATE
                SET channel_id = EXCLUDED.channel_id, threshold = EXCLUDED.threshold,
                    emoji = EXCLUDED.emoji, enabled = TRUE,
                    allow_nsfw = COALESCE($5, starboard_config.allow_nsfw),
                    self_star = COALESCE($6, starboard_config.self_star)
            """,
            guild_id, channel_id, threshold, emoji, allow_nsfw, self_star,
        )

    async def set_threshold(self, guild_id: int, threshold: int) -> bool:
        esito = await self._pool.execute(
            "UPDATE starboard_config SET threshold = $2 WHERE guild_id = $1", guild_id, threshold
        )
        return esito.endswith(" 1")

    async def disable(self, guild_id: int) -> bool:
        esito = await self._pool.execute(
            "UPDATE starboard_config SET enabled = FALSE WHERE guild_id = $1", guild_id
        )
        return esito.endswith(" 1")

    async def claim_post(self, guild_id: int, channel_id: int, message_id: int, author_id: int) -> bool:
        """Prenota il posto in bacheca per un originale. False se c'è già (pubblicato o in corso)."""
        r = await self._pool.fetchrow(
            """
            INSERT INTO starboard_posts (source_message_id, guild_id, source_channel_id, author_id)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (source_message_id) DO NOTHING
            RETURNING source_message_id
            """,
            message_id, guild_id, channel_id, author_id,
        )
        return r is not None

    async def get_post(self, guild_id: int, message_id: int) -> StarboardPost | None:
        r = await self._pool.fetchrow(
            "SELECT source_message_id, board_message_id, stars FROM starboard_posts "
            "WHERE guild_id = $1 AND source_message_id = $2",
            guild_id, message_id,
        )
        return None if r is None else StarboardPost(**dict(r))

    async def set_board_message(self, guild_id: int, message_id: int, board_message_id: int, stars: int) -> None:
        await self._pool.execute(
            "UPDATE starboard_posts SET board_message_id = $3, stars = $4 "
            "WHERE guild_id = $1 AND source_message_id = $2",
            guild_id, message_id, board_message_id, stars,
        )

    async def release_post(self, guild_id: int, message_id: int) -> None:
        """Invio fallito: toglie la prenotazione se non è ancora stato pubblicato nulla."""
        await self._pool.execute(
            "DELETE FROM starboard_posts WHERE guild_id = $1 AND source_message_id = $2 AND board_message_id IS NULL",
            guild_id, message_id,
        )


def _get_pool():
    from core.database import db
    return db.pool


starboard_repo = StarboardRepository(pool_provider=_get_pool)
