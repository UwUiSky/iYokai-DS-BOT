"""
core/repositories/suggestion_repo.py
=======================================
Persistenza del Suggestion System (SPEC.md §14.14).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg

from core.suggestion_logic import PENDING


@dataclass(frozen=True)
class Suggestion:
    id: int
    guild_id: int
    channel_id: int
    message_id: int | None
    user_id: int
    suggestion_text: str
    status: str
    decided_by: int | None
    decided_at: datetime | None
    created_at: datetime


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS suggestions (
            id               SERIAL PRIMARY KEY,
            guild_id         BIGINT NOT NULL,
            channel_id       BIGINT NOT NULL,
            message_id       BIGINT,
            user_id          BIGINT NOT NULL,
            suggestion_text  TEXT NOT NULL,
            status           TEXT NOT NULL DEFAULT 'pending',
            decided_by       BIGINT,
            decided_at       TIMESTAMPTZ,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_suggestions_guild_status
            ON suggestions (guild_id, status);
        """
    )


class SuggestionRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    def _row_to_suggestion(self, row) -> Suggestion:
        return Suggestion(
            id=row["id"],
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            message_id=row["message_id"],
            user_id=row["user_id"],
            suggestion_text=row["suggestion_text"],
            status=row["status"],
            decided_by=row["decided_by"],
            decided_at=row["decided_at"],
            created_at=row["created_at"],
        )

    async def create_suggestion(
        self, guild_id: int, channel_id: int, user_id: int, suggestion_text: str
    ) -> int:
        row = await self._pool.fetchrow(
            """
            INSERT INTO suggestions (guild_id, channel_id, user_id, suggestion_text, status)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            guild_id,
            channel_id,
            user_id,
            suggestion_text,
            PENDING,
        )
        return row["id"]

    async def set_message_id(self, suggestion_id: int, message_id: int) -> None:
        await self._pool.execute(
            "UPDATE suggestions SET message_id = $2 WHERE id = $1",
            suggestion_id,
            message_id,
        )

    async def get_suggestion(self, suggestion_id: int) -> Suggestion | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM suggestions WHERE id = $1", suggestion_id
        )
        return self._row_to_suggestion(row) if row is not None else None

    async def set_status(
        self, suggestion_id: int, status: str, decided_by: int, decided_at: datetime
    ) -> None:
        await self._pool.execute(
            """
            UPDATE suggestions
            SET status = $2, decided_by = $3, decided_at = $4
            WHERE id = $1
            """,
            suggestion_id,
            status,
            decided_by,
            decided_at,
        )

    async def list_pending(self, guild_id: int | None = None) -> list[Suggestion]:
        """
        Le suggestion ancora in attesa — con guild_id=None, TUTTE
        quelle di ogni server (usata all'avvio del bot per
        ricostruire le View persistenti dei bottoni approva/rifiuta,
        stesso principio già usato per i Role Menu: bot.add_view()
        va richiamato ad ogni avvio per ciascun messaggio esistente).
        """
        if guild_id is None:
            rows = await self._pool.fetch(
                "SELECT * FROM suggestions WHERE status = $1 AND message_id IS NOT NULL",
                PENDING,
            )
        else:
            rows = await self._pool.fetch(
                "SELECT * FROM suggestions WHERE guild_id = $1 AND status = $2",
                guild_id,
                PENDING,
            )
        return [self._row_to_suggestion(r) for r in rows]


def _get_pool():
    from core.database import db
    return db.pool


suggestion_repo = SuggestionRepository(pool_provider=_get_pool)
