"""
core/repositories/voice_temp_repo.py
=======================================
Persistenza per i vocali temporanei:
- configurazione per server (canale generatore, categoria di
  destinazione)
- canali temporanei attivi, con il loro proprietario (per i comandi
  di gestione — rename/limit/lock/kick — vedi
  core/voice_temp_logic.py per chi può usarli)
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg


@dataclass(frozen=True)
class VoiceTempConfig:
    guild_id: int
    generator_channel_id: int | None
    category_id: int | None


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS voice_temp_config (
            guild_id             BIGINT PRIMARY KEY,
            generator_channel_id BIGINT,
            category_id          BIGINT
        );

        CREATE TABLE IF NOT EXISTS voice_temp_channels (
            channel_id BIGINT PRIMARY KEY,
            guild_id   BIGINT NOT NULL,
            owner_id   BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )


class VoiceTempRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def get_config(self, guild_id: int) -> VoiceTempConfig:
        row = await self._pool.fetchrow(
            "SELECT generator_channel_id, category_id FROM voice_temp_config WHERE guild_id = $1",
            guild_id,
        )
        if row is None:
            return VoiceTempConfig(guild_id=guild_id, generator_channel_id=None, category_id=None)
        return VoiceTempConfig(
            guild_id=guild_id,
            generator_channel_id=row["generator_channel_id"],
            category_id=row["category_id"],
        )

    async def set_config(
        self, guild_id: int, generator_channel_id: int, category_id: int
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO voice_temp_config (guild_id, generator_channel_id, category_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE
                SET generator_channel_id = EXCLUDED.generator_channel_id,
                    category_id = EXCLUDED.category_id
            """,
            guild_id,
            generator_channel_id,
            category_id,
        )

    async def register_channel(self, channel_id: int, guild_id: int, owner_id: int) -> None:
        await self._pool.execute(
            """
            INSERT INTO voice_temp_channels (channel_id, guild_id, owner_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (channel_id) DO UPDATE SET owner_id = EXCLUDED.owner_id
            """,
            channel_id,
            guild_id,
            owner_id,
        )

    async def get_owner(self, channel_id: int) -> int | None:
        """
        Restituisce il proprietario del canale, oppure None se questo
        channel_id non è (o non è più) un canale temporaneo tracciato
        — usato anche come test "è un nostro canale?" prima di agire.
        """
        return await self._pool.fetchval(
            "SELECT owner_id FROM voice_temp_channels WHERE channel_id = $1",
            channel_id,
        )

    async def set_owner(self, channel_id: int, new_owner_id: int) -> bool:
        result = await self._pool.execute(
            "UPDATE voice_temp_channels SET owner_id = $2 WHERE channel_id = $1",
            channel_id,
            new_owner_id,
        )
        return result.endswith(" 1")

    async def unregister_channel(self, channel_id: int) -> None:
        await self._pool.execute(
            "DELETE FROM voice_temp_channels WHERE channel_id = $1", channel_id
        )


def _get_pool():
    from core.database import db
    return db.pool


voice_temp_repo = VoiceTempRepository(pool_provider=_get_pool)
