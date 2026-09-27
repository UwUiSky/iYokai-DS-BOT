"""
core/repositories/backup_user_snapshot_repo.py
===================================================
Persistenza dello snapshot settimanale utenti (SPEC.md §11.10) — chi
era verificato e presente (non bannato/kickato) nel main al momento
dell'ultimo scatto. Usato dal restore massivo (§11.11): quando serve
ripristinare gli utenti su un nuovo server, si parte da QUESTA lista,
non dai membri attuali del vecchio main (che potrebbe non esistere
più al momento del restore).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class SnapshotEntry:
    main_guild_id: int
    user_id: int
    username: str
    avatar_url: str | None
    snapshotted_at: datetime


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS backup_user_snapshots (
            main_guild_id  BIGINT NOT NULL,
            user_id        BIGINT NOT NULL,
            username       TEXT NOT NULL,
            avatar_url     TEXT,
            snapshotted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (main_guild_id, user_id)
        );

        CREATE INDEX IF NOT EXISTS idx_backup_user_snapshots_main_guild
            ON backup_user_snapshots (main_guild_id);
        """
    )


class BackupUserSnapshotRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    def _row_to_entry(self, row) -> SnapshotEntry:
        return SnapshotEntry(
            main_guild_id=row["main_guild_id"],
            user_id=row["user_id"],
            username=row["username"],
            avatar_url=row["avatar_url"],
            snapshotted_at=row["snapshotted_at"],
        )

    async def save_snapshot(
        self, main_guild_id: int, members: list[tuple[int, str, str | None]]
    ) -> None:
        """
        Sostituisce INTERAMENTE lo snapshot di un main — ogni scatto
        settimanale è una fotografia dello stato ATTUALE, non un
        accumulo: chi non è più eleggibile (uscito, perso il ruolo
        verificato) non deve restare nello snapshot vecchio.

        members: lista di (user_id, username, avatar_url).
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM backup_user_snapshots WHERE main_guild_id = $1",
                    main_guild_id,
                )
                if members:
                    await conn.executemany(
                        """
                        INSERT INTO backup_user_snapshots
                            (main_guild_id, user_id, username, avatar_url)
                        VALUES ($1, $2, $3, $4)
                        """,
                        [
                            (main_guild_id, user_id, username, avatar_url)
                            for user_id, username, avatar_url in members
                        ],
                    )

    async def get_snapshot(self, main_guild_id: int) -> list[SnapshotEntry]:
        rows = await self._pool.fetch(
            "SELECT * FROM backup_user_snapshots WHERE main_guild_id = $1 ORDER BY user_id",
            main_guild_id,
        )
        return [self._row_to_entry(r) for r in rows]

    async def get_snapshot_count(self, main_guild_id: int) -> int:
        return await self._pool.fetchval(
            "SELECT count(*) FROM backup_user_snapshots WHERE main_guild_id = $1",
            main_guild_id,
        )

    async def delete_for_main_guild(self, main_guild_id: int) -> None:
        await self._pool.execute(
            "DELETE FROM backup_user_snapshots WHERE main_guild_id = $1", main_guild_id
        )


def _get_pool():
    from core.database import db
    return db.pool


backup_user_snapshot_repo = BackupUserSnapshotRepository(pool_provider=_get_pool)
