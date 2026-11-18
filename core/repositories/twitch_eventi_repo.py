"""
core/repositories/twitch_eventi_repo.py
=======================================
Eventi Discord creati dal calendario di un canale Twitch (ALR-013): quali avvisi lo vogliono e quali
puntate hanno già il loro evento. Tabelle: core/migrations/0692_twitch_eventi_vod.sql.
Funzioni coperte: SPEC §10.1 (#129 ALR-013)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class AvvisoConEventi:
    sub_id: int
    guild_id: int
    twitch_login: str


class TwitchEventiRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def avvisi_con_eventi(self) -> list[AvvisoConEventi]:
        rows = await self._pool.fetch(
            "SELECT s.id, s.guild_id, s.twitch_login FROM twitch_subscriptions s "
            "JOIN alert_options o ON o.kind = 'TW' AND o.sub_id = s.id AND o.guild_id = s.guild_id "
            "WHERE o.schedule_events ORDER BY s.id"
        )
        return [AvvisoConEventi(r["id"], r["guild_id"], r["twitch_login"]) for r in rows]

    async def segmenti_fatti(self, guild_id: int, sub_id: int) -> set[str]:
        rows = await self._pool.fetch(
            "SELECT segment_id FROM twitch_eventi_creati WHERE guild_id = $1 AND sub_id = $2", guild_id, sub_id
        )
        return {r["segment_id"] for r in rows}

    async def segna(self, guild_id: int, sub_id: int, segment_id: str, event_id: int, inizio: datetime) -> None:
        await self._pool.execute(
            "INSERT INTO twitch_eventi_creati (guild_id, sub_id, segment_id, event_id, start_time) "
            "VALUES ($1, $2, $3, $4, $5) ON CONFLICT DO NOTHING",
            guild_id, sub_id, segment_id, event_id, inizio,
        )

    async def pulisci_vecchi(self) -> None:
        """Le puntate finite da più di un giorno non servono più."""
        await self._pool.execute("DELETE FROM twitch_eventi_creati WHERE start_time < now() - interval '1 day'")


def _get_pool():
    from core.database import db

    return db.pool


twitch_eventi_repo = TwitchEventiRepository(pool_provider=_get_pool)
