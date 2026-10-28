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

from core.music_fleet_logic import TOTAL_WORKERS, find_free_worker

# Chiave del lock che serializza le assegnazioni di worker (tra processi e task).
_LOCK_ASSEGNAZIONE = 7_060_001


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

    async def assign_free_worker(
        self, guild_id: int, channel_id: int, esclusi: set[int], total_workers: int = TOTAL_WORKERS
    ) -> int | None:
        """
        Assegnazione ATOMICA (M 8.6): sotto un advisory lock di transazione legge i
        worker occupati, sceglie il primo libero fuori da `esclusi` e scrive la riga.
        Due /music play insieme non prendono mai lo stesso worker. Se il canale ha
        gia' una sessione, ritorna quella. None se non c'e' nessun worker libero.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1)", _LOCK_ASSEGNAZIONE)
                esistente = await conn.fetchval(
                    "SELECT worker_index FROM music_sessions WHERE guild_id = $1 AND channel_id = $2",
                    guild_id,
                    channel_id,
                )
                if esistente is not None:
                    return esistente
                righe = await conn.fetch("SELECT DISTINCT worker_index FROM music_sessions")
                occupati = {r["worker_index"] for r in righe}
                libero = find_free_worker(occupati | set(esclusi), total_workers)
                if libero is None:
                    return None
                await conn.execute(
                    "INSERT INTO music_sessions (guild_id, channel_id, worker_index) VALUES ($1, $2, $3)",
                    guild_id,
                    channel_id,
                    libero,
                )
                return libero

    async def move_session(self, guild_id: int, da_canale: int, a_canale: int) -> None:
        """Il worker e' stato spostato a mano in un altro canale: la riga lo segue."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                if await conn.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM music_sessions WHERE guild_id=$1 AND channel_id=$2)",
                    guild_id,
                    a_canale,
                ):
                    await conn.execute(
                        "DELETE FROM music_sessions WHERE guild_id=$1 AND channel_id=$2",
                        guild_id,
                        da_canale,
                    )
                else:
                    await conn.execute(
                        "UPDATE music_sessions SET channel_id=$3 WHERE guild_id=$1 AND channel_id=$2",
                        guild_id,
                        da_canale,
                        a_canale,
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


def _get_pool():
    from core.database import db
    return db.pool


music_session_repo = MusicSessionRepository(pool_provider=_get_pool)
