"""
core/repositories/main_radio_repo.py
========================================
Persistenza della radio condivisa (SPEC.md §9.11). Due tabelle:
`main_radio_tracks` (la playlist ordinata, curata dall'utente —
canzoni pubblicate più inediti interlacciati, come richiesto) e
`main_radio_state` (una riga sola, il "riferimento" dell'orologio
condiviso: quale traccia e quando è iniziata — core/main_radio_logic.
compute_current_position() usa questi due dati insieme all'ora
attuale per capire dove dovrebbe essere la riproduzione ora).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg

STATE_ROW_ID = 1  # riga singleton — la radio è UNA sola, condivisa


@dataclass(frozen=True)
class MainRadioTrack:
    id: int
    position: int
    identifier: str
    duration_ms: int
    label: str
    added_by: int
    added_at: datetime


@dataclass(frozen=True)
class MainRadioState:
    track_index: int
    track_started_at: datetime
    is_active: bool


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS main_radio_tracks (
            id            SERIAL PRIMARY KEY,
            position      INTEGER NOT NULL,
            identifier    TEXT NOT NULL,
            duration_ms   INTEGER NOT NULL,
            label         TEXT NOT NULL,
            added_by      BIGINT NOT NULL,
            added_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_main_radio_tracks_position
            ON main_radio_tracks (position);

        CREATE TABLE IF NOT EXISTS main_radio_state (
            id                 INTEGER PRIMARY KEY,
            track_index        INTEGER NOT NULL,
            track_started_at   TIMESTAMPTZ NOT NULL,
            is_active          BOOLEAN NOT NULL DEFAULT false
        );
        """
    )


class MainRadioRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    def _row_to_track(self, row) -> MainRadioTrack:
        return MainRadioTrack(
            id=row["id"],
            position=row["position"],
            identifier=row["identifier"],
            duration_ms=row["duration_ms"],
            label=row["label"],
            added_by=row["added_by"],
            added_at=row["added_at"],
        )

    async def add_track(
        self, identifier: str, duration_ms: int, label: str, added_by: int
    ) -> int:
        """Aggiunge in coda alla playlist — posizione = la più alta
        esistente + 1 (0 se la playlist è ancora vuota)."""
        row = await self._pool.fetchrow(
            """
            INSERT INTO main_radio_tracks (position, identifier, duration_ms, label, added_by)
            VALUES (
                COALESCE((SELECT MAX(position) + 1 FROM main_radio_tracks), 0),
                $1, $2, $3, $4
            )
            RETURNING id
            """,
            identifier,
            duration_ms,
            label,
            added_by,
        )
        return row["id"]

    async def remove_track(self, track_id: int) -> bool:
        result = await self._pool.execute(
            "DELETE FROM main_radio_tracks WHERE id = $1", track_id
        )
        return result.endswith(" 1")

    async def list_tracks(self) -> list[MainRadioTrack]:
        rows = await self._pool.fetch(
            "SELECT * FROM main_radio_tracks ORDER BY position"
        )
        return [self._row_to_track(r) for r in rows]

    async def get_state(self) -> MainRadioState | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM main_radio_state WHERE id = $1", STATE_ROW_ID
        )
        if row is None:
            return None
        return MainRadioState(
            track_index=row["track_index"],
            track_started_at=row["track_started_at"],
            is_active=row["is_active"],
        )

    async def set_state(
        self, track_index: int, track_started_at: datetime, is_active: bool
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO main_radio_state (id, track_index, track_started_at, is_active)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (id) DO UPDATE
                SET track_index = EXCLUDED.track_index,
                    track_started_at = EXCLUDED.track_started_at,
                    is_active = EXCLUDED.is_active
            """,
            STATE_ROW_ID,
            track_index,
            track_started_at,
            is_active,
        )


def _get_pool():
    from core.database import db
    return db.pool


main_radio_repo = MainRadioRepository(pool_provider=_get_pool)
