"""
core/repositories/self_role_repo.py
===================================
Ruoli che un membro può prendersi e lasciare da solo (catalogo #123,
RUO-090..093). Tabella: core/migrations/0231_ruoli_scelta.sql.
Funzioni coperte: SPEC §14
"""

from __future__ import annotations

import asyncpg

from core.repositories.tetto_server import tetto_per_server
from core.ruoli_strumenti_logic import MAX_RUOLI_SCELTA


class SelfRoleRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def add(self, guild_id: int, role_id: int, created_by: int) -> bool:
        """Aggiunge un ruolo a scelta. False se il server ne ha già MAX_RUOLI_SCELTA."""
        async with tetto_per_server(self._pool, "self_roles", guild_id) as conn:
            riga = await conn.fetchrow(
                """
                INSERT INTO self_roles (guild_id, role_id, created_by)
                SELECT $1, $2, $3
                WHERE EXISTS (SELECT 1 FROM self_roles WHERE guild_id = $1 AND role_id = $2)
                   OR (SELECT count(*) FROM self_roles WHERE guild_id = $1) < $4
                ON CONFLICT (guild_id, role_id) DO NOTHING
                RETURNING role_id
                """,
                guild_id, role_id, created_by, MAX_RUOLI_SCELTA,
            )
            if riga is not None:
                return True
            return bool(
                await conn.fetchval(
                    "SELECT 1 FROM self_roles WHERE guild_id = $1 AND role_id = $2", guild_id, role_id
                )
            )

    async def remove(self, guild_id: int, role_id: int) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM self_roles WHERE guild_id = $1 AND role_id = $2", guild_id, role_id
        )
        return esito.endswith(" 1")

    async def clear(self, guild_id: int) -> int:
        esito = await self._pool.execute("DELETE FROM self_roles WHERE guild_id = $1", guild_id)
        return int(esito.split()[-1])

    async def list_ids(self, guild_id: int) -> list[int]:
        righe = await self._pool.fetch(
            "SELECT role_id FROM self_roles WHERE guild_id = $1 ORDER BY created_at, role_id", guild_id
        )
        return [r["role_id"] for r in righe]


def _get_pool():
    from core.database import db
    return db.pool


self_role_repo = SelfRoleRepository(pool_provider=_get_pool)
