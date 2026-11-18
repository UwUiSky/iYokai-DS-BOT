"""
core/repositories/picarto_subscription_repo.py
===========================================
Iscrizioni Picarto (ALR-008). Tabella: core/migrations/0691_picarto.sql.
Stesso schema di kick_subscription_repo.py, con il tetto per server.
Funzioni coperte: SPEC §10.13 (#129 ALR-008)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg

DEFAULT_LIVE_MESSAGE_TEMPLATE = "🟢 **{label}** è ora in diretta su Picarto: {title}\nhttps://picarto.tv/{login}"
DEFAULT_OFFLINE_MESSAGE_TEMPLATE = "⚫ **{label}** ha terminato la diretta."


@dataclass(frozen=True)
class PicartoSubscription:
    id: int
    guild_id: int
    channel_id: int
    picarto_name: str
    label: str
    live_message_template: str
    offline_message_template: str
    last_known_live: bool
    created_by: int
    created_at: datetime


class PicartoSubscriptionRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    @staticmethod
    def _riga(r) -> PicartoSubscription:
        return PicartoSubscription(
            id=r["id"], guild_id=r["guild_id"], channel_id=r["channel_id"], picarto_name=r["picarto_name"],
            label=r["label"], live_message_template=r["live_message_template"],
            offline_message_template=r["offline_message_template"], last_known_live=r["last_known_live"],
            created_by=r["created_by"], created_at=r["created_at"],
        )

    async def add_subscription(
        self, guild_id: int, channel_id: int, picarto_name: str, label: str, created_by: int,
        live_message_template: str | None = None, offline_message_template: str | None = None,
        max_per_guild: int | None = None,
    ) -> int | None:
        """None = tetto per server raggiunto (conteggio e scrittura atomici)."""
        sql = """
            INSERT INTO picarto_subscriptions (guild_id, channel_id, picarto_name, label,
                live_message_template, offline_message_template, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id
        """
        args = (guild_id, channel_id, picarto_name.lower(), label,
                live_message_template or DEFAULT_LIVE_MESSAGE_TEMPLATE,
                offline_message_template or DEFAULT_OFFLINE_MESSAGE_TEMPLATE, created_by)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                if max_per_guild is not None:
                    await conn.execute(
                        "SELECT pg_advisory_xact_lock(hashtext('picarto_subscriptions'), $1)",
                        guild_id % 2_147_483_647,
                    )
                    n = await conn.fetchval("SELECT count(*) FROM picarto_subscriptions WHERE guild_id = $1", guild_id)
                    if n >= max_per_guild:
                        return None
                return (await conn.fetchrow(sql, *args))["id"]

    async def remove_subscription(self, subscription_id: int, guild_id: int) -> bool:
        r = await self._pool.execute(
            "DELETE FROM picarto_subscriptions WHERE id = $1 AND guild_id = $2", subscription_id, guild_id
        )
        return r.endswith(" 1")

    async def list_subscriptions(self, guild_id: int) -> list[PicartoSubscription]:
        rows = await self._pool.fetch("SELECT * FROM picarto_subscriptions WHERE guild_id = $1 ORDER BY created_at", guild_id)
        return [self._riga(r) for r in rows]

    async def get_all_subscriptions(self) -> list[PicartoSubscription]:
        return [self._riga(r) for r in await self._pool.fetch("SELECT * FROM picarto_subscriptions ORDER BY id")]

    async def update_last_known_live(self, subscription_id: int, is_live: bool) -> None:
        await self._pool.execute(
            "UPDATE picarto_subscriptions SET last_known_live = $2 WHERE id = $1", subscription_id, is_live
        )


def _get_pool():
    from core.database import db

    return db.pool


picarto_subscription_repo = PicartoSubscriptionRepository(pool_provider=_get_pool)
