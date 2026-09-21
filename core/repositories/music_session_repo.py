"""
core/repositories/music_session_repo.py
===========================================
Tabella music_sessions (SPEC.md §9.2, "logica se bot1 occupato →
bot2"). Persistente, non solo in memoria: se il bot si riavvia con
una sessione musicale attiva, il worker assegnato a un server non
deve cambiare a caso al prossimo /play — resta lo stesso finché
qualcuno non lo disconnette esplicitamente (rilasciando la riga).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class MusicSession:
    guild_id: int
    worker_index: int
    assigned_at: datetime


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS music_sessions (
            guild_id      BIGINT PRIMARY KEY,
            worker_index  INTEGER NOT NULL,
            assigned_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )


class MusicSessionRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def assign_worker(self, guild_id: int, worker_index: int) -> None:
        await self._pool.execute(
            """
            INSERT INTO music_sessions (guild_id, worker_index)
            VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE
                SET worker_index = EXCLUDED.worker_index, assigned_at = now()
            """,
            guild_id,
            worker_index,
        )

    async def get_worker_for_guild(self, guild_id: int) -> int | None:
        row = await self._pool.fetchrow(
            "SELECT worker_index FROM music_sessions WHERE guild_id = $1", guild_id
        )
        return row["worker_index"] if row is not None else None

    async def release_guild(self, guild_id: int) -> None:
        await self._pool.execute("DELETE FROM music_sessions WHERE guild_id = $1", guild_id)

    async def get_occupied_workers(self) -> set[int]:
        """
        Tutti i worker attualmente assegnati a QUALUNQUE server —
        usata insieme a core/music_fleet_logic.find_free_worker() per
        decidere quale istanza è libera per un nuovo /play.
        """
        rows = await self._pool.fetch("SELECT DISTINCT worker_index FROM music_sessions")
        return {row["worker_index"] for row in rows}


def _get_pool():
    from core.database import db
    return db.pool


music_session_repo = MusicSessionRepository(pool_provider=_get_pool)
