"""
core/repositories/suggestion_repo.py
=======================================
Persistenza del Suggestion System (SPEC.md §14.14). Il motivo della
decisione è in core/migrations/0232_suggerimenti_esito.sql.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg

from core.suggestion_logic import APERTI, PENDING


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
    decision_reason: str | None = None


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
            decision_reason=row["decision_reason"],
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
        self,
        suggestion_id: int,
        status: str,
        decided_by: int,
        decided_at: datetime,
        motivo: str | None = None,
    ) -> bool:
        """
        Decide un suggerimento SOLO se è ancora aperto (in attesa o in
        valutazione, M 10.9): con due membri dello staff che cliccano
        insieme ne vince uno, l'altro riceve False. Una sola istruzione,
        nessuna lettura prima.
        """
        riga = await self._pool.fetchrow(
            """
            UPDATE suggestions
            SET status = $2, decided_by = $3, decided_at = $4, decision_reason = $6
            WHERE id = $1 AND status = ANY($5::text[])
            RETURNING id
            """,
            suggestion_id,
            status,
            decided_by,
            decided_at,
            list(APERTI),
            motivo,
        )
        return riga is not None

    async def delete_suggestion(self, suggestion_id: int) -> None:
        """Toglie un suggerimento mai pubblicato (invio fallito)."""
        await self._pool.execute("DELETE FROM suggestions WHERE id = $1", suggestion_id)

    async def list_pending(self, guild_id: int | None = None) -> list[Suggestion]:
        """
        Le suggestion ancora aperte (in attesa o in valutazione) — con guild_id=None, TUTTE
        quelle di ogni server (usata all'avvio del bot per
        ricostruire le View persistenti dei bottoni approva/rifiuta,
        stesso principio già usato per i Role Menu: bot.add_view()
        va richiamato ad ogni avvio per ciascun messaggio esistente).
        """
        if guild_id is None:
            rows = await self._pool.fetch(
                "SELECT * FROM suggestions WHERE status = ANY($1::text[]) AND message_id IS NOT NULL",
                list(APERTI),
            )
        else:
            rows = await self._pool.fetch(
                "SELECT * FROM suggestions WHERE guild_id = $1 AND status = ANY($2::text[])",
                guild_id,
                list(APERTI),
            )
        return [self._row_to_suggestion(r) for r in rows]


def _get_pool():
    from core.database import db
    return db.pool


suggestion_repo = SuggestionRepository(pool_provider=_get_pool)
