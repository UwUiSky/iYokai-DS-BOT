"""
core/repositories/music_session_repo.py
===========================================
Tabella music_sessions (SPEC.md §9.2, "logica se bot1 occupato →
bot2"). Persistente, non solo in memoria: se il bot si riavvia con
una sessione musicale attiva, il worker assegnato a un server non
deve cambiare a caso al prossimo /music play — resta lo stesso finché
qualcuno non lo disconnette esplicitamente (rilasciando la riga).
Le righe valgono solo per la vita del processo: all'avvio vengono
svuotate (clear_all, BUG-9), perché i worker ripartono da zero.
Dalla migrazione 0060 (M 8.6) la sessione è per (server, canale vocale):
due canali dello stesso server hanno due bot e due code.
Funzioni coperte: SPEC §9.2, REVIEW.md BUG-9, M 8.6.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class MusicSession:
    guild_id: int
    channel_id: int
    worker_index: int
    assigned_at: datetime


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS music_sessions (
            guild_id      BIGINT NOT NULL,
            channel_id    BIGINT NOT NULL DEFAULT 0,
            worker_index  INTEGER NOT NULL,
            assigned_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (guild_id, channel_id)
        );
        """
    )


class MusicSessionRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def assign_worker(self, guild_id: int, channel_id: int, worker_index: int) -> None:
        await self._pool.execute(
            """
            INSERT INTO music_sessions (guild_id, channel_id, worker_index)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, channel_id) DO UPDATE
                SET worker_index = EXCLUDED.worker_index, assigned_at = now()
            """,
            guild_id,
            channel_id,
            worker_index,
        )

    async def get_worker_for_channel(self, guild_id: int, channel_id: int) -> int | None:
        row = await self._pool.fetchrow(
            "SELECT worker_index FROM music_sessions WHERE guild_id = $1 AND channel_id = $2",
            guild_id,
            channel_id,
        )
        return row["worker_index"] if row is not None else None

    async def guild_has_session(self, guild_id: int) -> bool:
        """Vero se il server ha almeno una sessione (in qualunque canale)."""
        return bool(
            await self._pool.fetchval(
                "SELECT EXISTS (SELECT 1 FROM music_sessions WHERE guild_id = $1)", guild_id
            )
        )

    async def release_session(self, guild_id: int, channel_id: int) -> None:
        await self._pool.execute(
            "DELETE FROM music_sessions WHERE guild_id = $1 AND channel_id = $2",
            guild_id,
            channel_id,
        )

    async def clear_all(self) -> None:
        """
        BUG-9: chiamata all'avvio del processo. I worker musicali girano
        nello stesso processo e dopo un riavvio ripartono da zero (nessun
        player attivo): le righe rimaste dal processo precedente li
        farebbero risultare "occupati" per sempre.
        """
        await self._pool.execute("DELETE FROM music_sessions")

    async def get_occupied_workers(self) -> set[int]:
        """
        Tutti i worker attualmente assegnati a QUALUNQUE server —
        usata insieme a core/music_fleet_logic.find_free_worker() per
        decidere quale istanza è libera per un nuovo /music play.
        """
        rows = await self._pool.fetch("SELECT DISTINCT worker_index FROM music_sessions")
        return {row["worker_index"] for row in rows}


def _get_pool():
    from core.database import db
    return db.pool


music_session_repo = MusicSessionRepository(pool_provider=_get_pool)
