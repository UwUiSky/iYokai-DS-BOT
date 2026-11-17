"""
core/repositories/voice_role_repo.py
====================================
Ruoli vocali: un ruolo per canale vocale (catalogo #123, RUO-044). Tabella: core/migrations/0647_ruoli_vocali.sql.
Funzioni coperte: SPEC §14
"""

from __future__ import annotations

import asyncpg

from core.repositories.tetto_server import tetto_per_server
from core.ruoli_vocali_logic import MAX_RUOLI_VOCALI


class VoiceRoleRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def set(self, guild_id: int, channel_id: int, role_id: int, created_by: int) -> bool:
        """Lega un ruolo a un canale (cambia il ruolo se il canale c'è già). False se il server è al tetto."""
        async with tetto_per_server(self._pool, "voice_roles", guild_id) as conn:
            riga = await conn.fetchrow(
                """
                INSERT INTO voice_roles (guild_id, channel_id, role_id, created_by)
                SELECT $1, $2, $3, $4
                WHERE EXISTS (SELECT 1 FROM voice_roles WHERE guild_id = $1 AND channel_id = $2)
                   OR (SELECT count(*) FROM voice_roles WHERE guild_id = $1) < $5
                ON CONFLICT (guild_id, channel_id) DO UPDATE SET role_id = EXCLUDED.role_id
                RETURNING channel_id
                """,
                guild_id, channel_id, role_id, created_by, MAX_RUOLI_VOCALI,
            )
            return riga is not None

    async def remove(self, guild_id: int, channel_id: int) -> int | None:
        """Scollega il canale; torna il ruolo che aveva, None se non c'era."""
        return await self._pool.fetchval(
            "DELETE FROM voice_roles WHERE guild_id = $1 AND channel_id = $2 RETURNING role_id",
            guild_id, channel_id,
        )

    async def rules(self, guild_id: int) -> dict[int, int]:
        righe = await self._pool.fetch(
            "SELECT channel_id, role_id FROM voice_roles WHERE guild_id = $1 ORDER BY created_at, channel_id",
            guild_id,
        )
        return {r["channel_id"]: r["role_id"] for r in righe}

    async def guild_ids(self) -> list[int]:
        """I server che hanno almeno un ruolo vocale (per la pulizia all'avvio)."""
        return [r["guild_id"] for r in await self._pool.fetch("SELECT DISTINCT guild_id FROM voice_roles")]


def _get_pool():
    from core.database import db
    return db.pool


voice_role_repo = VoiceRoleRepository(pool_provider=_get_pool)
