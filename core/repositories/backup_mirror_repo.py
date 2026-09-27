"""
core/repositories/backup_mirror_repo.py
==========================================
Persistenza della mappa "canale del server main -> webhook del server
backup" usata dal mirroring in tempo reale (SPEC.md §11.9). Una riga
per canale del main: quando arriva un messaggio in quel canale, il
mirror worker guarda qui l'URL del webhook a cui inoltrarlo.

Quando un nuovo backup viene creato (job completato) per lo stesso
main, le righe precedenti vanno sostituite: il vecchio server di
backup normalmente non esiste più (o non è più quello giusto), quindi
prima di salvare la nuova mappa il chiamante cancella quella vecchia
per lo stesso main_guild_id con delete_for_main_guild().
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg


@dataclass(frozen=True)
class MirrorWebhook:
    main_channel_id: int
    main_guild_id: int
    backup_guild_id: int
    webhook_url: str


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS backup_mirror_webhooks (
            main_channel_id BIGINT PRIMARY KEY,
            main_guild_id   BIGINT NOT NULL,
            backup_guild_id BIGINT NOT NULL,
            webhook_url     TEXT NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_backup_mirror_webhooks_main_guild
            ON backup_mirror_webhooks (main_guild_id);
        """
    )


class BackupMirrorRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    def _row_to_webhook(self, row) -> MirrorWebhook:
        return MirrorWebhook(
            main_channel_id=row["main_channel_id"],
            main_guild_id=row["main_guild_id"],
            backup_guild_id=row["backup_guild_id"],
            webhook_url=row["webhook_url"],
        )

    async def save_mapping(
        self, main_guild_id: int, backup_guild_id: int, channel_webhook_map: dict[int, str]
    ) -> None:
        """
        Sostituisce INTERAMENTE la mappa per questo main_guild_id —
        cancella prima le righe vecchie (webhook del backup
        precedente, ormai inutilizzabili) e poi inserisce quelle
        nuove, nella stessa transazione.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM backup_mirror_webhooks WHERE main_guild_id = $1",
                    main_guild_id,
                )
                if channel_webhook_map:
                    await conn.executemany(
                        """
                        INSERT INTO backup_mirror_webhooks
                            (main_channel_id, main_guild_id, backup_guild_id, webhook_url)
                        VALUES ($1, $2, $3, $4)
                        """,
                        [
                            (canale_id, main_guild_id, backup_guild_id, url)
                            for canale_id, url in channel_webhook_map.items()
                        ],
                    )

    async def get_webhook_url(self, main_channel_id: int) -> str | None:
        row = await self._pool.fetchrow(
            "SELECT webhook_url FROM backup_mirror_webhooks WHERE main_channel_id = $1",
            main_channel_id,
        )
        return row["webhook_url"] if row is not None else None

    async def delete_for_main_guild(self, main_guild_id: int) -> None:
        await self._pool.execute(
            "DELETE FROM backup_mirror_webhooks WHERE main_guild_id = $1", main_guild_id
        )


def _get_pool():
    from core.database import db
    return db.pool


backup_mirror_repo = BackupMirrorRepository(pool_provider=_get_pool)
