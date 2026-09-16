"""
core/repositories/ticket_repo.py
===================================
Persistenza dei ticket di supporto: numerazione atomica per-server
(stesso schema di moderation_repo.py — contatore con UPSERT in
transazione), stato (aperto/chiuso), chi lo ha preso in carico,
priorità.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class Ticket:
    id: int
    guild_id: int
    ticket_number: int
    channel_id: int
    user_id: int
    claimed_by: int | None
    status: str  # "open" | "closed"
    priority: str  # "normal" | "high" | "urgent"
    created_at: datetime
    closed_at: datetime | None
    closed_by: int | None


VALID_PRIORITIES = ("normal", "high", "urgent")


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS ticket_counters (
            guild_id    BIGINT PRIMARY KEY,
            next_number INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS tickets (
            id            SERIAL PRIMARY KEY,
            guild_id      BIGINT NOT NULL,
            ticket_number INTEGER NOT NULL,
            channel_id    BIGINT NOT NULL UNIQUE,
            user_id       BIGINT NOT NULL,
            claimed_by    BIGINT,
            status        TEXT NOT NULL DEFAULT 'open',
            priority      TEXT NOT NULL DEFAULT 'normal',
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            closed_at     TIMESTAMPTZ,
            closed_by     BIGINT,
            UNIQUE (guild_id, ticket_number)
        );

        CREATE INDEX IF NOT EXISTS idx_tickets_guild_user_status
            ON tickets (guild_id, user_id, status);
        """
    )


class TicketRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def count_open_tickets_for_user(self, guild_id: int, user_id: int) -> int:
        """
        Usato per impedire a un utente di aprire più ticket
        contemporaneamente — un buon guardrail di base che evita
        spam involontario di canali.
        """
        return await self._pool.fetchval(
            """
            SELECT count(*) FROM tickets
            WHERE guild_id = $1 AND user_id = $2 AND status = 'open'
            """,
            guild_id,
            user_id,
        )

    async def create_ticket(self, guild_id: int, user_id: int, channel_id: int) -> int:
        """
        Crea un nuovo ticket con numerazione atomica (stesso pattern
        di ModerationRepository.create_case — vedi quel file per il
        motivo dell'UPSERT in transazione invece di
        SELECT-poi-UPDATE). Restituisce il numero assegnato.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                ticket_number = await conn.fetchval(
                    """
                    INSERT INTO ticket_counters (guild_id, next_number)
                    VALUES ($1, 2)
                    ON CONFLICT (guild_id) DO UPDATE
                        SET next_number = ticket_counters.next_number + 1
                    RETURNING next_number - 1
                    """,
                    guild_id,
                )
                await conn.execute(
                    """
                    INSERT INTO tickets (guild_id, ticket_number, channel_id, user_id)
                    VALUES ($1, $2, $3, $4)
                    """,
                    guild_id,
                    ticket_number,
                    channel_id,
                    user_id,
                )
        return ticket_number

    async def get_ticket_by_channel(self, channel_id: int) -> Ticket | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM tickets WHERE channel_id = $1", channel_id
        )
        return _row_to_ticket(row) if row else None

    async def claim_ticket(self, channel_id: int, staff_id: int) -> bool:
        result = await self._pool.execute(
            """
            UPDATE tickets SET claimed_by = $2
            WHERE channel_id = $1 AND status = 'open'
            """,
            channel_id,
            staff_id,
        )
        return result.endswith(" 1")

    async def close_ticket(self, channel_id: int, closed_by: int) -> bool:
        result = await self._pool.execute(
            """
            UPDATE tickets
            SET status = 'closed', closed_at = now(), closed_by = $2
            WHERE channel_id = $1 AND status = 'open'
            """,
            channel_id,
            closed_by,
        )
        return result.endswith(" 1")

    async def set_priority(self, channel_id: int, priority: str) -> bool:
        if priority not in VALID_PRIORITIES:
            raise ValueError(
                f"Priorità non valida: '{priority}'. Valori ammessi: {VALID_PRIORITIES}"
            )
        result = await self._pool.execute(
            "UPDATE tickets SET priority = $2 WHERE channel_id = $1 AND status = 'open'",
            channel_id,
            priority,
        )
        return result.endswith(" 1")


def _row_to_ticket(row) -> Ticket:
    return Ticket(
        id=row["id"],
        guild_id=row["guild_id"],
        ticket_number=row["ticket_number"],
        channel_id=row["channel_id"],
        user_id=row["user_id"],
        claimed_by=row["claimed_by"],
        status=row["status"],
        priority=row["priority"],
        created_at=row["created_at"],
        closed_at=row["closed_at"],
        closed_by=row["closed_by"],
    )


def _get_pool():
    from core.database import db
    return db.pool


ticket_repo = TicketRepository(pool_provider=_get_pool)
