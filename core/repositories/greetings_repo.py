"""
core/repositories/greetings_repo.py
======================================
Persistenza di Welcome / Goodbye / Boost messages (SPEC.md
§14.4-14.6). Una sola tabella, tutti e tre i tipi di messaggio
insieme — sono impostazioni dello stesso "pannello" concettuale per
un admin, non serve separarle in tabelle diverse.
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from core.greetings_logic import (
    DEFAULT_BOOST_TEMPLATE,
    DEFAULT_GOODBYE_TEMPLATE,
    DEFAULT_WELCOME_TEMPLATE,
)


@dataclass(frozen=True)
class GreetingsConfig:
    guild_id: int
    welcome_enabled: bool
    welcome_channel_id: int | None
    welcome_message: str
    welcome_dm: bool
    goodbye_enabled: bool
    goodbye_channel_id: int | None
    goodbye_message: str
    boost_enabled: bool
    boost_channel_id: int | None
    boost_message: str


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS greetings_config (
            guild_id           BIGINT PRIMARY KEY,
            welcome_enabled    BOOLEAN NOT NULL DEFAULT FALSE,
            welcome_channel_id BIGINT,
            welcome_message    TEXT NOT NULL DEFAULT '',
            welcome_dm         BOOLEAN NOT NULL DEFAULT FALSE,
            goodbye_enabled    BOOLEAN NOT NULL DEFAULT FALSE,
            goodbye_channel_id BIGINT,
            goodbye_message    TEXT NOT NULL DEFAULT '',
            boost_enabled      BOOLEAN NOT NULL DEFAULT FALSE,
            boost_channel_id   BIGINT,
            boost_message      TEXT NOT NULL DEFAULT ''
        );
        """
    )


class GreetingsRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def get_config(self, guild_id: int) -> GreetingsConfig:
        row = await self._pool.fetchrow(
            "SELECT * FROM greetings_config WHERE guild_id = $1", guild_id
        )
        if row is None:
            return GreetingsConfig(
                guild_id=guild_id,
                welcome_enabled=False,
                welcome_channel_id=None,
                welcome_message=DEFAULT_WELCOME_TEMPLATE,
                welcome_dm=False,
                goodbye_enabled=False,
                goodbye_channel_id=None,
                goodbye_message=DEFAULT_GOODBYE_TEMPLATE,
                boost_enabled=False,
                boost_channel_id=None,
                boost_message=DEFAULT_BOOST_TEMPLATE,
            )
        return GreetingsConfig(
            guild_id=row["guild_id"],
            welcome_enabled=row["welcome_enabled"],
            welcome_channel_id=row["welcome_channel_id"],
            welcome_message=row["welcome_message"] or DEFAULT_WELCOME_TEMPLATE,
            welcome_dm=row["welcome_dm"],
            goodbye_enabled=row["goodbye_enabled"],
            goodbye_channel_id=row["goodbye_channel_id"],
            goodbye_message=row["goodbye_message"] or DEFAULT_GOODBYE_TEMPLATE,
            boost_enabled=row["boost_enabled"],
            boost_channel_id=row["boost_channel_id"],
            boost_message=row["boost_message"] or DEFAULT_BOOST_TEMPLATE,
        )

    async def set_welcome(
        self, guild_id: int, enabled: bool, channel_id: int, message: str, dm: bool
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO greetings_config (guild_id, welcome_enabled, welcome_channel_id, welcome_message, welcome_dm)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (guild_id) DO UPDATE
                SET welcome_enabled = EXCLUDED.welcome_enabled,
                    welcome_channel_id = EXCLUDED.welcome_channel_id,
                    welcome_message = EXCLUDED.welcome_message,
                    welcome_dm = EXCLUDED.welcome_dm
            """,
            guild_id,
            enabled,
            channel_id,
            message,
            dm,
        )

    async def set_goodbye(
        self, guild_id: int, enabled: bool, channel_id: int, message: str
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO greetings_config (guild_id, goodbye_enabled, goodbye_channel_id, goodbye_message)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id) DO UPDATE
                SET goodbye_enabled = EXCLUDED.goodbye_enabled,
                    goodbye_channel_id = EXCLUDED.goodbye_channel_id,
                    goodbye_message = EXCLUDED.goodbye_message
            """,
            guild_id,
            enabled,
            channel_id,
            message,
        )

    async def set_boost(
        self, guild_id: int, enabled: bool, channel_id: int, message: str
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO greetings_config (guild_id, boost_enabled, boost_channel_id, boost_message)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id) DO UPDATE
                SET boost_enabled = EXCLUDED.boost_enabled,
                    boost_channel_id = EXCLUDED.boost_channel_id,
                    boost_message = EXCLUDED.boost_message
            """,
            guild_id,
            enabled,
            channel_id,
            message,
        )


def _get_pool():
    from core.database import db
    return db.pool


greetings_repo = GreetingsRepository(pool_provider=_get_pool)
