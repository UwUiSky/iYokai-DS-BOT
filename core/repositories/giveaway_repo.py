"""
core/repositories/giveaway_repo.py
======================================
Persistenza dei giveaway (SPEC.md §15.5). Le partecipazioni sono
persistite (non in memoria come i drop, core/drop_logic.py) perché
un giveaway dura ore o giorni — deve sopravvivere a un riavvio del
bot, ed è per questo che il pulsante "Partecipa" è una VIEW
PERSISTENTE (custom_id fisso, registrata di nuovo ad ogni avvio in
main.py), non effimera come quella dei drop.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class Giveaway:
    id: int
    guild_id: int
    channel_id: int
    message_id: int | None
    prize: str
    winners_count: int
    min_level: int
    required_role_id: int | None
    ends_at: datetime
    ended: bool
    created_by: int


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS giveaways (
            id                SERIAL PRIMARY KEY,
            guild_id          BIGINT NOT NULL,
            channel_id        BIGINT NOT NULL,
            message_id        BIGINT,
            prize             TEXT NOT NULL,
            winners_count     INTEGER NOT NULL DEFAULT 1,
            min_level         INTEGER NOT NULL DEFAULT 0,
            required_role_id  BIGINT,
            ends_at           TIMESTAMPTZ NOT NULL,
            ended             BOOLEAN NOT NULL DEFAULT false,
            created_by        BIGINT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS giveaway_entries (
            giveaway_id   INTEGER NOT NULL,
            user_id       BIGINT NOT NULL,
            PRIMARY KEY (giveaway_id, user_id)
        );

        CREATE INDEX IF NOT EXISTS idx_giveaways_due
            ON giveaways (ended, ends_at);
        """
    )


class GiveawayRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    def _row_to_giveaway(self, row) -> Giveaway:
        return Giveaway(
            id=row["id"],
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            message_id=row["message_id"],
            prize=row["prize"],
            winners_count=row["winners_count"],
            min_level=row["min_level"],
            required_role_id=row["required_role_id"],
            ends_at=row["ends_at"],
            ended=row["ended"],
            created_by=row["created_by"],
        )

    async def create_giveaway(
        self,
        guild_id: int,
        channel_id: int,
        prize: str,
        winners_count: int,
        min_level: int,
        required_role_id: int | None,
        ends_at: datetime,
        created_by: int,
    ) -> int:
        row = await self._pool.fetchrow(
            """
            INSERT INTO giveaways
                (guild_id, channel_id, prize, winners_count, min_level,
                 required_role_id, ends_at, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
            """,
            guild_id, channel_id, prize, winners_count, min_level,
            required_role_id, ends_at, created_by,
        )
        return row["id"]

    async def set_message_id(self, giveaway_id: int, message_id: int) -> None:
        await self._pool.execute(
            "UPDATE giveaways SET message_id = $2 WHERE id = $1", giveaway_id, message_id
        )

    async def get_giveaway(self, giveaway_id: int) -> Giveaway | None:
        row = await self._pool.fetchrow("SELECT * FROM giveaways WHERE id = $1", giveaway_id)
        return self._row_to_giveaway(row) if row is not None else None

    async def get_due_giveaways(self, now: datetime) -> list[Giveaway]:
        """Giveaway non ancora conclusi la cui scadenza è passata —
        pronti per l'estrazione dei vincitori."""
        rows = await self._pool.fetch(
            "SELECT * FROM giveaways WHERE ended = false AND ends_at <= $1", now
        )
        return [self._row_to_giveaway(r) for r in rows]

    async def get_active_giveaways(self) -> list[Giveaway]:
        """Tutti i giveaway non ancora conclusi, indipendentemente
        dalla scadenza — usata all'avvio del bot per ri-registrare
        le view persistenti dei pulsanti "Partecipa" ancora validi."""
        rows = await self._pool.fetch("SELECT * FROM giveaways WHERE ended = false")
        return [self._row_to_giveaway(r) for r in rows]

    async def mark_ended(self, giveaway_id: int) -> None:
        await self._pool.execute("UPDATE giveaways SET ended = true WHERE id = $1", giveaway_id)

    async def add_entry(self, giveaway_id: int, user_id: int) -> bool:
        """Restituisce True se la partecipazione è nuova, False se
        l'utente aveva già partecipato (nessun errore, nessuna riga
        duplicata — ON CONFLICT DO NOTHING)."""
        result = await self._pool.execute(
            """
            INSERT INTO giveaway_entries (giveaway_id, user_id)
            VALUES ($1, $2)
            ON CONFLICT (giveaway_id, user_id) DO NOTHING
            """,
            giveaway_id,
            user_id,
        )
        return result.endswith(" 1")

    async def has_entered(self, giveaway_id: int, user_id: int) -> bool:
        row = await self._pool.fetchrow(
            "SELECT 1 FROM giveaway_entries WHERE giveaway_id = $1 AND user_id = $2",
            giveaway_id,
            user_id,
        )
        return row is not None

    async def get_entries(self, giveaway_id: int) -> list[int]:
        rows = await self._pool.fetch(
            "SELECT user_id FROM giveaway_entries WHERE giveaway_id = $1", giveaway_id
        )
        return [r["user_id"] for r in rows]

    async def count_entries(self, giveaway_id: int) -> int:
        row = await self._pool.fetchrow(
            "SELECT COUNT(*) AS n FROM giveaway_entries WHERE giveaway_id = $1", giveaway_id
        )
        return row["n"]


def _get_pool():
    from core.database import db
    return db.pool


giveaway_repo = GiveawayRepository(pool_provider=_get_pool)
