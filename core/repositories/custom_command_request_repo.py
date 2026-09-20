"""
core/repositories/custom_command_request_repo.py
=====================================================
Persistenza del sistema di RICHIESTA Custom Commands (SPEC.md §14.8
— distinto dal Suggestion System di §14.14: questo va SEMPRE al
server principale dello sviluppatore, indipendentemente da quale
server il membro lo invii, quello va al server del membro stesso).

Riusa core/suggestion_logic.py per lo stato (pending/approved/
rejected) — stessa identica macchina a stati, applicata a un tipo
diverso di richiesta, non ha senso duplicarla.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg

from core.suggestion_logic import PENDING


@dataclass(frozen=True)
class CustomCommandRequest:
    id: int
    requester_guild_id: int
    requester_guild_name: str
    user_id: int
    username_snapshot: str
    command_name: str
    description: str
    example: str
    status: str
    message_id: int | None
    decided_by: int | None
    decided_at: datetime | None
    created_at: datetime


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS custom_command_requests (
            id                    SERIAL PRIMARY KEY,
            requester_guild_id    BIGINT NOT NULL,
            requester_guild_name  TEXT NOT NULL,
            user_id               BIGINT NOT NULL,
            username_snapshot     TEXT NOT NULL,
            command_name          TEXT NOT NULL,
            description           TEXT NOT NULL,
            example               TEXT NOT NULL,
            status                TEXT NOT NULL DEFAULT 'pending',
            message_id            BIGINT,
            decided_by            BIGINT,
            decided_at            TIMESTAMPTZ,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )


class CustomCommandRequestRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    def _row_to_request(self, row) -> CustomCommandRequest:
        return CustomCommandRequest(
            id=row["id"],
            requester_guild_id=row["requester_guild_id"],
            requester_guild_name=row["requester_guild_name"],
            user_id=row["user_id"],
            username_snapshot=row["username_snapshot"],
            command_name=row["command_name"],
            description=row["description"],
            example=row["example"],
            status=row["status"],
            message_id=row["message_id"],
            decided_by=row["decided_by"],
            decided_at=row["decided_at"],
            created_at=row["created_at"],
        )

    async def create_request(
        self,
        requester_guild_id: int,
        requester_guild_name: str,
        user_id: int,
        username_snapshot: str,
        command_name: str,
        description: str,
        example: str,
    ) -> int:
        row = await self._pool.fetchrow(
            """
            INSERT INTO custom_command_requests
                (requester_guild_id, requester_guild_name, user_id, username_snapshot,
                 command_name, description, example, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
            """,
            requester_guild_id,
            requester_guild_name,
            user_id,
            username_snapshot,
            command_name,
            description,
            example,
            PENDING,
        )
        return row["id"]

    async def set_message_id(self, request_id: int, message_id: int) -> None:
        await self._pool.execute(
            "UPDATE custom_command_requests SET message_id = $2 WHERE id = $1",
            request_id,
            message_id,
        )

    async def get_request(self, request_id: int) -> CustomCommandRequest | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM custom_command_requests WHERE id = $1", request_id
        )
        return self._row_to_request(row) if row is not None else None

    async def set_status(
        self, request_id: int, status: str, decided_by: int, decided_at: datetime
    ) -> None:
        await self._pool.execute(
            """
            UPDATE custom_command_requests
            SET status = $2, decided_by = $3, decided_at = $4
            WHERE id = $1
            """,
            request_id,
            status,
            decided_by,
            decided_at,
        )

    async def list_pending(self) -> list[CustomCommandRequest]:
        """
        Usata all'avvio del bot per ricostruire le View persistenti
        dei bottoni approva/rifiuta — stesso principio già usato per
        i Role Menu e le Suggestion.
        """
        rows = await self._pool.fetch(
            "SELECT * FROM custom_command_requests WHERE status = $1 AND message_id IS NOT NULL",
            PENDING,
        )
        return [self._row_to_request(r) for r in rows]


def _get_pool():
    from core.database import db
    return db.pool


custom_command_request_repo = CustomCommandRequestRepository(pool_provider=_get_pool)
