"""
core/repositories/ai_staff_repo.py
==================================
Ricerca nel registro eventi del server con filtri già pronti (persone, tipi, periodo). Solo lettura.
Funzioni coperte: SPEC §25.44 (AI-R-047)
"""

from __future__ import annotations

from datetime import datetime

import asyncpg


def _pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


class AiStaffRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def cerca_eventi(
        self, guild_id: int, utenti: list[int], prefissi: list[str], dal: datetime, limite: int = 30
    ) -> list[dict]:
        """Gli eventi più recenti del server che toccano una delle persone (come autore o bersaglio) e uno dei tipi."""
        righe = await self._pool.fetch(
            """
            SELECT created_at, event_type, actor_id, target_user_id, channel_id FROM event_log
            WHERE guild_id = $1 AND created_at >= $2
              AND (cardinality($3::bigint[]) = 0 OR actor_id = ANY($3) OR target_user_id = ANY($3))
              AND (cardinality($4::text[]) = 0 OR event_type LIKE ANY($4))
            ORDER BY created_at DESC LIMIT $5
            """,
            guild_id, dal, utenti, prefissi, limite,
        )
        return [dict(r) for r in righe]


ai_staff_repo = AiStaffRepository(pool_provider=_pool)
