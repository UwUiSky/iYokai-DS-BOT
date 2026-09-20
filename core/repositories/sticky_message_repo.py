"""
core/repositories/sticky_message_repo.py
============================================
Persistenza degli Sticky Messages (SPEC.md §14.13). Una riga per
canale (non per server: un server può avere sticky diversi in canali
diversi).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class StickyMessage:
    channel_id: int
    guild_id: int
    message_text: str
    last_message_id: int | None
    last_reposted_at: datetime | None


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS sticky_messages (
            channel_id       BIGINT PRIMARY KEY,
            guild_id         BIGINT NOT NULL,
            message_text     TEXT NOT NULL,
            last_message_id  BIGINT,
            last_reposted_at TIMESTAMPTZ
        );

        CREATE INDEX IF NOT EXISTS idx_sticky_messages_guild
            ON sticky_messages (guild_id);
        """
    )


class StickyMessageRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    def _row_to_sticky(self, row) -> StickyMessage:
        return StickyMessage(
            channel_id=row["channel_id"],
            guild_id=row["guild_id"],
            message_text=row["message_text"],
            last_message_id=row["last_message_id"],
            last_reposted_at=row["last_reposted_at"],
        )

    async def set_sticky(self, channel_id: int, guild_id: int, message_text: str) -> None:
        """
        Crea o sostituisce lo sticky di un canale. last_message_id e
        last_reposted_at vengono azzerati: un nuovo testo è
        concettualmente un nuovo sticky, non un aggiornamento del
        vecchio messaggio già pubblicato (verrebbe ripubblicato al
        prossimo messaggio nel canale, non modificato sul posto).
        """
        await self._pool.execute(
            """
            INSERT INTO sticky_messages (channel_id, guild_id, message_text, last_message_id, last_reposted_at)
            VALUES ($1, $2, $3, NULL, NULL)
            ON CONFLICT (channel_id) DO UPDATE
                SET message_text = EXCLUDED.message_text,
                    last_message_id = NULL,
                    last_reposted_at = NULL
            """,
            channel_id,
            guild_id,
            message_text,
        )

    async def get_sticky(self, channel_id: int) -> StickyMessage | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM sticky_messages WHERE channel_id = $1", channel_id
        )
        return self._row_to_sticky(row) if row is not None else None

    async def remove_sticky(self, channel_id: int) -> bool:
        result = await self._pool.execute(
            "DELETE FROM sticky_messages WHERE channel_id = $1", channel_id
        )
        return result.endswith(" 1")

    async def update_repost_state(
        self, channel_id: int, message_id: int, reposted_at: datetime
    ) -> None:
        await self._pool.execute(
            """
            UPDATE sticky_messages
            SET last_message_id = $2, last_reposted_at = $3
            WHERE channel_id = $1
            """,
            channel_id,
            message_id,
            reposted_at,
        )


def _get_pool():
    from core.database import db
    return db.pool


sticky_message_repo = StickyMessageRepository(pool_provider=_get_pool)
