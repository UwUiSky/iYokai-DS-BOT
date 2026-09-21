"""
core/repositories/twitch_subscription_repo.py
==================================================
Persistenza di Twitch live/offline (SPEC.md §10.1, §10.2). Una riga
per streamer sottoscritto — analogo a feed_subscription_repo.py, ma
con lo stato "era live l'ultima volta che ho controllato" invece di
"ultimo ID visto", dato che l'API Twitch non funziona per voci
sequenziali come un feed RSS.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg

DEFAULT_LIVE_MESSAGE_TEMPLATE = "🔴 **{label}** è ora in diretta su Twitch: {title}\nhttps://twitch.tv/{login}"
DEFAULT_OFFLINE_MESSAGE_TEMPLATE = "⚫ **{label}** ha terminato la diretta."


@dataclass(frozen=True)
class TwitchSubscription:
    id: int
    guild_id: int
    channel_id: int
    twitch_login: str
    label: str
    live_message_template: str
    offline_message_template: str
    last_known_live: bool
    created_by: int
    created_at: datetime


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS twitch_subscriptions (
            id                        SERIAL PRIMARY KEY,
            guild_id                  BIGINT NOT NULL,
            channel_id                BIGINT NOT NULL,
            twitch_login              TEXT NOT NULL,
            label                     TEXT NOT NULL,
            live_message_template     TEXT NOT NULL,
            offline_message_template  TEXT NOT NULL,
            last_known_live           BOOLEAN NOT NULL DEFAULT false,
            created_by                BIGINT NOT NULL,
            created_at                TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_twitch_subscriptions_guild
            ON twitch_subscriptions (guild_id);
        """
    )


class TwitchSubscriptionRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    def _row_to_subscription(self, row) -> TwitchSubscription:
        return TwitchSubscription(
            id=row["id"],
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            twitch_login=row["twitch_login"],
            label=row["label"],
            live_message_template=row["live_message_template"],
            offline_message_template=row["offline_message_template"],
            last_known_live=row["last_known_live"],
            created_by=row["created_by"],
            created_at=row["created_at"],
        )

    async def add_subscription(
        self,
        guild_id: int,
        channel_id: int,
        twitch_login: str,
        label: str,
        created_by: int,
        live_message_template: str | None = None,
        offline_message_template: str | None = None,
    ) -> int:
        row = await self._pool.fetchrow(
            """
            INSERT INTO twitch_subscriptions
                (guild_id, channel_id, twitch_login, label,
                 live_message_template, offline_message_template, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
            """,
            guild_id,
            channel_id,
            twitch_login.lower(),
            label,
            live_message_template or DEFAULT_LIVE_MESSAGE_TEMPLATE,
            offline_message_template or DEFAULT_OFFLINE_MESSAGE_TEMPLATE,
            created_by,
        )
        return row["id"]

    async def remove_subscription(self, subscription_id: int, guild_id: int) -> bool:
        result = await self._pool.execute(
            "DELETE FROM twitch_subscriptions WHERE id = $1 AND guild_id = $2",
            subscription_id,
            guild_id,
        )
        return result.endswith(" 1")

    async def list_subscriptions(self, guild_id: int) -> list[TwitchSubscription]:
        rows = await self._pool.fetch(
            "SELECT * FROM twitch_subscriptions WHERE guild_id = $1 ORDER BY created_at",
            guild_id,
        )
        return [self._row_to_subscription(r) for r in rows]

    async def get_all_subscriptions(self) -> list[TwitchSubscription]:
        rows = await self._pool.fetch("SELECT * FROM twitch_subscriptions ORDER BY id")
        return [self._row_to_subscription(r) for r in rows]

    async def update_last_known_live(self, subscription_id: int, is_live: bool) -> None:
        await self._pool.execute(
            "UPDATE twitch_subscriptions SET last_known_live = $2 WHERE id = $1",
            subscription_id,
            is_live,
        )


def _get_pool():
    from core.database import db
    return db.pool


twitch_subscription_repo = TwitchSubscriptionRepository(pool_provider=_get_pool)
