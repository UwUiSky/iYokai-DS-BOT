"""
core/repositories/event_log_repo.py
======================================
Log eventi unificato (BACKLOG.md §3 "Logging strutturato"). Un
evento salvato UNA VOLTA, consultabile da più angolazioni (membro,
canale, ruolo, case di moderazione, tempo) — invece di canali
Discord con embed "usa e getta" che spariscono se il canale viene
cancellato o il log scrolla via.

Decisione presa nell'analisi (BACKLOG.md §3): niente proiezione su
Forum Discord per membri/messaggi (alta cardinalità — un server da
50.000 membri creerebbe 50.000 thread potenziali, e un raid da
centinaia di join farebbe esplodere il rate limit proprio quando il
logging serve di più). Solo DB + comando di ricerca. La proiezione
Forum per canali/case (bassa cardinalità) resta un'estensione futura
separata, non costruita qui.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class EventLogEntry:
    id: int
    guild_id: int
    event_type: str
    actor_id: int | None
    target_user_id: int | None
    channel_id: int | None
    role_id: int | None
    case_number: int | None
    details: dict | None
    created_at: datetime


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS event_log (
            id              SERIAL PRIMARY KEY,
            guild_id        BIGINT NOT NULL,
            event_type      TEXT NOT NULL,
            actor_id        BIGINT,
            target_user_id  BIGINT,
            channel_id      BIGINT,
            role_id         BIGINT,
            case_number     INTEGER,
            details         TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        -- Un indice per ciascuna "angolazione" di consultazione
        -- dichiarata nell'analisi: membro, canale, ruolo, tempo
        -- generale. Il case di moderazione è già indicizzato
        -- altrove (moderation_cases), qui basta poterlo filtrare
        -- velocemente quando serve incrociare i due.
        CREATE INDEX IF NOT EXISTS idx_event_log_guild_user
            ON event_log (guild_id, target_user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_event_log_guild_channel
            ON event_log (guild_id, channel_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_event_log_guild_role
            ON event_log (guild_id, role_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_event_log_guild_time
            ON event_log (guild_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_event_log_guild_case
            ON event_log (guild_id, case_number);

        -- Per la pulizia periodica (retention): trovare le righe più
        -- vecchie di una soglia senza scansionare tutta la tabella.
        CREATE INDEX IF NOT EXISTS idx_event_log_created_at
            ON event_log (created_at);
        """
    )


class EventLogRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    def _row_to_entry(self, row) -> EventLogEntry:
        return EventLogEntry(
            id=row["id"],
            guild_id=row["guild_id"],
            event_type=row["event_type"],
            actor_id=row["actor_id"],
            target_user_id=row["target_user_id"],
            channel_id=row["channel_id"],
            role_id=row["role_id"],
            case_number=row["case_number"],
            details=json.loads(row["details"]) if row["details"] is not None else None,
            created_at=row["created_at"],
        )

    async def log_event(
        self,
        guild_id: int,
        event_type: str,
        actor_id: int | None = None,
        target_user_id: int | None = None,
        channel_id: int | None = None,
        role_id: int | None = None,
        case_number: int | None = None,
        details: dict | None = None,
    ) -> int:
        row = await self._pool.fetchrow(
            """
            INSERT INTO event_log
                (guild_id, event_type, actor_id, target_user_id,
                 channel_id, role_id, case_number, details)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
            """,
            guild_id,
            event_type,
            actor_id,
            target_user_id,
            channel_id,
            role_id,
            case_number,
            json.dumps(details) if details is not None else None,
        )
        return row["id"]

    async def get_events_by_user(
        self, guild_id: int, user_id: int, limit: int = 25
    ) -> list[EventLogEntry]:
        rows = await self._pool.fetch(
            """
            SELECT * FROM event_log
            WHERE guild_id = $1 AND target_user_id = $2
            ORDER BY created_at DESC LIMIT $3
            """,
            guild_id,
            user_id,
            limit,
        )
        return [self._row_to_entry(r) for r in rows]

    async def get_events_by_channel(
        self, guild_id: int, channel_id: int, limit: int = 25
    ) -> list[EventLogEntry]:
        rows = await self._pool.fetch(
            """
            SELECT * FROM event_log
            WHERE guild_id = $1 AND channel_id = $2
            ORDER BY created_at DESC LIMIT $3
            """,
            guild_id,
            channel_id,
            limit,
        )
        return [self._row_to_entry(r) for r in rows]

    async def get_recent_events(
        self, guild_id: int, limit: int = 25
    ) -> list[EventLogEntry]:
        rows = await self._pool.fetch(
            """
            SELECT * FROM event_log
            WHERE guild_id = $1
            ORDER BY created_at DESC LIMIT $2
            """,
            guild_id,
            limit,
        )
        return [self._row_to_entry(r) for r in rows]

    async def get_events_by_type_since(
        self, guild_id: int, event_type: str, since: datetime
    ) -> list[EventLogEntry]:
        """
        Tutti gli eventi di un tipo specifico da una data in poi,
        senza limite di conteggio — pensata per Server Stats
        (SPEC.md §14.18), che deve vedere OGNI join/leave nella
        finestra richiesta per calcolare la crescita giornaliera, non
        solo gli ultimi N in assoluto come get_recent_events().
        """
        rows = await self._pool.fetch(
            """
            SELECT * FROM event_log
            WHERE guild_id = $1 AND event_type = $2 AND created_at >= $3
            ORDER BY created_at
            """,
            guild_id,
            event_type,
            since,
        )
        return [self._row_to_entry(r) for r in rows]

    async def export_events(
        self, guild_id: int, since: datetime | None = None
    ) -> list[EventLogEntry]:
        """
        Tutti gli eventi di un server (opzionalmente da una data in
        poi), senza limite — pensato per l'export completo (valore
        legale: risposta a una richiesta di accesso GDPR), non per
        una lettura interattiva.
        """
        if since is not None:
            rows = await self._pool.fetch(
                "SELECT * FROM event_log WHERE guild_id = $1 AND created_at >= $2 "
                "ORDER BY created_at",
                guild_id,
                since,
            )
        else:
            rows = await self._pool.fetch(
                "SELECT * FROM event_log WHERE guild_id = $1 ORDER BY created_at",
                guild_id,
            )
        return [self._row_to_entry(r) for r in rows]

    async def prune_old_events(self, older_than: datetime) -> int:
        """
        Elimina globalmente, SENZA distinzione di server — usata solo
        nei test o in una pulizia manuale una tantum. La retention
        periodica reale (core/event_log_retention.py) usa
        prune_old_events_for_guild(), perché la soglia cambia da
        server a server (Free 30gg, Premium 180gg) — non si può
        applicare la stessa soglia a tutti con questa funzione.
        """
        result = await self._pool.execute(
            "DELETE FROM event_log WHERE created_at < $1", older_than
        )
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0

    async def prune_old_events_for_guild(self, guild_id: int, older_than: datetime) -> int:
        result = await self._pool.execute(
            "DELETE FROM event_log WHERE guild_id = $1 AND created_at < $2",
            guild_id,
            older_than,
        )
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0


def _get_pool():
    from core.database import db
    return db.pool


event_log_repo = EventLogRepository(pool_provider=_get_pool)
