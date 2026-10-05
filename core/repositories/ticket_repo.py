"""
core/repositories/ticket_repo.py
===================================
Persistenza dei ticket di supporto: numerazione atomica per-server
(stesso schema di moderation_repo.py — contatore con UPSERT in
transazione), stato (aperto/chiuso), chi lo ha preso in carico,
priorità.
"""

# DA FARE (issue #62, fase F1): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §6 (Ticket).
# DA FARE (issue #84, fase F9): NF-13, Ticket: modulo, più pannelli,
#   chiusura automatica, voto. Vedi
#   revisione/02-piano/NUOVE_FUNZIONI.md.

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
    category_label: str | None = None
    first_response_at: datetime | None = None
    force_closed: bool = False


@dataclass(frozen=True)
class TicketCategory:
    id: int
    guild_id: int
    label: str
    category_id: int
    emoji: str | None


@dataclass(frozen=True)
class OperatorStats:
    """SPEC.md §13.12 — statistiche per singolo operatore."""

    claimed_count: int
    closed_count: int
    avg_response_seconds: float | None


@dataclass(frozen=True)
class GuildTicketStats:
    """SPEC.md §13.12 — statistiche complessive del server."""

    total_count: int
    open_count: int
    closed_count: int
    avg_response_seconds: float | None


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

        -- ADD COLUMN IF NOT EXISTS (idempotente): tickets esisteva
        -- già senza queste colonne — SPEC.md §13.2 (categoria
        -- scelta dal select menu, se configurato), §13.9 (force
        -- close distinto da close normale) e §13.12 (tempo di prima
        -- risposta, per le statistiche per operatore).
        ALTER TABLE tickets ADD COLUMN IF NOT EXISTS category_label TEXT;
        ALTER TABLE tickets ADD COLUMN IF NOT EXISTS first_response_at TIMESTAMPTZ;
        ALTER TABLE tickets ADD COLUMN IF NOT EXISTS force_closed BOOLEAN NOT NULL DEFAULT FALSE;

        -- SPEC.md §13.2: categorie di ticket configurabili, mostrate
        -- come select menu nel pannello quando ne esiste almeno una
        -- per il server (altrimenti resta il bottone unico storico).
        CREATE TABLE IF NOT EXISTS ticket_categories (
            id          SERIAL PRIMARY KEY,
            guild_id    BIGINT NOT NULL,
            label       TEXT NOT NULL,
            category_id BIGINT NOT NULL,
            emoji       TEXT,
            UNIQUE (guild_id, label)
        );
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

    async def create_ticket(
        self,
        guild_id: int,
        user_id: int,
        channel_id: int,
        category_label: str | None = None,
    ) -> int:
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
                    INSERT INTO tickets (guild_id, ticket_number, channel_id, user_id, category_label)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    guild_id,
                    ticket_number,
                    channel_id,
                    user_id,
                    category_label,
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

    async def close_ticket(self, channel_id: int, closed_by: int, force: bool = False) -> bool:
        """
        SPEC.md §13.9: `force` distingue una force-close (staff, che
        bypassa i controlli di appartenenza fatti nel cog) da una
        close normale, solo per le statistiche — il comportamento di
        chiusura sul DB è identico, cambia solo il flag registrato.
        """
        result = await self._pool.execute(
            """
            UPDATE tickets
            SET status = 'closed', closed_at = now(), closed_by = $2, force_closed = $3
            WHERE channel_id = $1 AND status = 'open'
            """,
            channel_id,
            closed_by,
            force,
        )
        return result.endswith(" 1")

    async def close_ticket_of_deleted_channel(self, channel_id: int) -> bool:
        """
        Chiude il ticket aperto di un canale che non esiste più
        (cancellato a mano). `closed_by` resta vuoto: non sappiamo chi
        ha cancellato il canale, e non deve contare nelle statistiche
        di nessun operatore.
        """
        result = await self._pool.execute(
            """
            UPDATE tickets
            SET status = 'closed', closed_at = now()
            WHERE channel_id = $1 AND status = 'open'
            """,
            channel_id,
        )
        return result.endswith(" 1")

    async def record_first_response(self, channel_id: int, at: datetime) -> bool:
        """
        SPEC.md §13.12: registra SOLO la prima risposta (il
        WHERE ... IS NULL impedisce che un messaggio successivo la
        sovrascriva) — è quello che rende la metrica "tempo di prima
        risposta" e non "tempo dell'ultimo messaggio".
        """
        result = await self._pool.execute(
            """
            UPDATE tickets SET first_response_at = $2
            WHERE channel_id = $1 AND first_response_at IS NULL
            """,
            channel_id,
            at,
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

    # ================================================================
    # Categorie ticket (SPEC.md §13.2)
    # ================================================================
    async def add_category(
        self, guild_id: int, label: str, category_id: int, emoji: str | None = None
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO ticket_categories (guild_id, label, category_id, emoji)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, label) DO UPDATE
                SET category_id = EXCLUDED.category_id, emoji = EXCLUDED.emoji
            """,
            guild_id,
            label,
            category_id,
            emoji,
        )

    async def remove_category(self, guild_id: int, label: str) -> bool:
        result = await self._pool.execute(
            "DELETE FROM ticket_categories WHERE guild_id = $1 AND label = $2",
            guild_id,
            label,
        )
        return result.endswith(" 1")

    async def list_categories(self, guild_id: int) -> list[TicketCategory]:
        rows = await self._pool.fetch(
            "SELECT * FROM ticket_categories WHERE guild_id = $1 ORDER BY label",
            guild_id,
        )
        return [
            TicketCategory(
                id=row["id"],
                guild_id=row["guild_id"],
                label=row["label"],
                category_id=row["category_id"],
                emoji=row["emoji"],
            )
            for row in rows
        ]

    # ================================================================
    # Statistiche (SPEC.md §13.12)
    # ================================================================
    async def get_operator_stats(self, guild_id: int, operator_id: int) -> OperatorStats:
        claimed_count = await self._pool.fetchval(
            "SELECT count(*) FROM tickets WHERE guild_id = $1 AND claimed_by = $2",
            guild_id,
            operator_id,
        )
        closed_count = await self._pool.fetchval(
            "SELECT count(*) FROM tickets WHERE guild_id = $1 AND closed_by = $2",
            guild_id,
            operator_id,
        )
        avg_seconds = await self._pool.fetchval(
            """
            SELECT extract(epoch FROM avg(first_response_at - created_at))
            FROM tickets
            WHERE guild_id = $1 AND claimed_by = $2 AND first_response_at IS NOT NULL
            """,
            guild_id,
            operator_id,
        )
        return OperatorStats(
            claimed_count=claimed_count,
            closed_count=closed_count,
            avg_response_seconds=float(avg_seconds) if avg_seconds is not None else None,
        )

    async def get_guild_stats(self, guild_id: int) -> GuildTicketStats:
        row = await self._pool.fetchrow(
            """
            SELECT
                count(*) AS total_count,
                count(*) FILTER (WHERE status = 'open') AS open_count,
                count(*) FILTER (WHERE status = 'closed') AS closed_count,
                extract(epoch FROM (
                    avg(first_response_at - created_at)
                        FILTER (WHERE first_response_at IS NOT NULL)
                )) AS avg_seconds
            FROM tickets
            WHERE guild_id = $1
            """,
            guild_id,
        )
        return GuildTicketStats(
            total_count=row["total_count"],
            open_count=row["open_count"],
            closed_count=row["closed_count"],
            avg_response_seconds=float(row["avg_seconds"]) if row["avg_seconds"] is not None else None,
        )


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
        category_label=row["category_label"],
        first_response_at=row["first_response_at"],
        force_closed=row["force_closed"],
    )


def _get_pool():
    from core.database import db
    return db.pool


ticket_repo = TicketRepository(pool_provider=_get_pool)
