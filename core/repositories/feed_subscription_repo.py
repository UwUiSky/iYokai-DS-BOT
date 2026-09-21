"""
core/repositories/feed_subscription_repo.py
===============================================
Persistenza di Custom RSS/Alert (SPEC.md §10.3, §10.7, §10.8, §10.9).
Una riga per feed sottoscritto — un server può seguire più feed
(YouTube, Reddit, RSS qualsiasi) contemporaneamente, ognuno con il
proprio canale di destinazione e template di messaggio.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg

DEFAULT_MESSAGE_TEMPLATE = "🔔 Nuovo contenuto da **{label}**: [{title}]({link})"


@dataclass(frozen=True)
class FeedSubscription:
    id: int
    guild_id: int
    channel_id: int
    feed_url: str
    label: str
    message_template: str
    last_seen_entry_id: str | None
    created_by: int
    created_at: datetime


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS feed_subscriptions (
            id                   SERIAL PRIMARY KEY,
            guild_id             BIGINT NOT NULL,
            channel_id           BIGINT NOT NULL,
            feed_url             TEXT NOT NULL,
            label                TEXT NOT NULL,
            message_template     TEXT NOT NULL,
            last_seen_entry_id   TEXT,
            created_by           BIGINT NOT NULL,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_feed_subscriptions_guild
            ON feed_subscriptions (guild_id);
        """
    )


class FeedSubscriptionRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    def _row_to_subscription(self, row) -> FeedSubscription:
        return FeedSubscription(
            id=row["id"],
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            feed_url=row["feed_url"],
            label=row["label"],
            message_template=row["message_template"],
            last_seen_entry_id=row["last_seen_entry_id"],
            created_by=row["created_by"],
            created_at=row["created_at"],
        )

    async def add_subscription(
        self,
        guild_id: int,
        channel_id: int,
        feed_url: str,
        label: str,
        created_by: int,
        message_template: str | None = None,
    ) -> int:
        row = await self._pool.fetchrow(
            """
            INSERT INTO feed_subscriptions
                (guild_id, channel_id, feed_url, label, message_template, created_by)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            guild_id,
            channel_id,
            feed_url,
            label,
            message_template or DEFAULT_MESSAGE_TEMPLATE,
            created_by,
        )
        return row["id"]

    async def remove_subscription(self, subscription_id: int, guild_id: int) -> bool:
        """
        Scoperto per guild_id — un server non deve poter cancellare
        la sottoscrizione di un altro server anche conoscendone l'id
        (gli id sono globali/incrementali, non per-server).
        """
        result = await self._pool.execute(
            "DELETE FROM feed_subscriptions WHERE id = $1 AND guild_id = $2",
            subscription_id,
            guild_id,
        )
        return result.endswith(" 1")

    async def list_subscriptions(self, guild_id: int) -> list[FeedSubscription]:
        rows = await self._pool.fetch(
            "SELECT * FROM feed_subscriptions WHERE guild_id = $1 ORDER BY created_at",
            guild_id,
        )
        return [self._row_to_subscription(r) for r in rows]

    async def get_all_subscriptions(self) -> list[FeedSubscription]:
        """Usata dal ciclo di polling: TUTTI i feed di TUTTI i
        server, non filtrati — il polling gira una volta per l'intero
        bot, non una volta per server."""
        rows = await self._pool.fetch("SELECT * FROM feed_subscriptions ORDER BY id")
        return [self._row_to_subscription(r) for r in rows]

    async def update_last_seen(self, subscription_id: int, entry_id: str) -> None:
        await self._pool.execute(
            "UPDATE feed_subscriptions SET last_seen_entry_id = $2 WHERE id = $1",
            subscription_id,
            entry_id,
        )


def _get_pool():
    from core.database import db
    return db.pool


feed_subscription_repo = FeedSubscriptionRepository(pool_provider=_get_pool)
