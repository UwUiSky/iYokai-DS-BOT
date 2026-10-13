"""
core/repositories/counter_repo.py
=================================
Canali contatore (NF-16). Tabella: core/migrations/0087_counters.sql.
Funzioni coperte: SPEC §23 (NF-16)
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from core.repositories.tetto_server import tetto_per_server

from core.counter_logic import MAX_CONTATORI


@dataclass(frozen=True)
class Counter:
    id: int
    guild_id: int
    channel_id: int
    kind: str
    label: str
    target: int | None
    last_value: int | None


_COLONNE = "id, guild_id, channel_id, kind, label, target, last_value"


class CounterRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def create(
        self, guild_id: int, channel_id: int, kind: str, label: str, target: int | None, created_by: int
    ) -> str:
        """"ok", "esiste" (canale già usato) o "pieno" (tetto per server)."""
        async with tetto_per_server(self._pool, "counters", guild_id) as conn:
            riga = await conn.fetchrow(
                """
                INSERT INTO counters (guild_id, channel_id, kind, label, target, created_by)
                SELECT $1, $2, $3, $4, $5, $6
                WHERE (SELECT count(*) FROM counters WHERE guild_id = $1) < $7
                ON CONFLICT (guild_id, channel_id) DO NOTHING
                RETURNING id
                """,
                guild_id, channel_id, kind, label, target, created_by, MAX_CONTATORI,
            )
            if riga is not None:
                return "ok"
            esiste = await conn.fetchval(
                "SELECT 1 FROM counters WHERE guild_id = $1 AND channel_id = $2", guild_id, channel_id
            )
            return "esiste" if esiste else "pieno"

    async def list_for_guild(self, guild_id: int) -> list[Counter]:
        righe = await self._pool.fetch(f"SELECT {_COLONNE} FROM counters WHERE guild_id = $1 ORDER BY id", guild_id)
        return [Counter(**dict(r)) for r in righe]

    async def list_all(self) -> list[Counter]:
        righe = await self._pool.fetch(f"SELECT {_COLONNE} FROM counters ORDER BY guild_id, id")
        return [Counter(**dict(r)) for r in righe]

    async def delete(self, guild_id: int, counter_id: int) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM counters WHERE guild_id = $1 AND id = $2", guild_id, counter_id
        )
        return esito.endswith(" 1")

    async def delete_by_channel(self, channel_id: int) -> None:
        await self._pool.execute("DELETE FROM counters WHERE channel_id = $1", channel_id)

    async def set_last_value(self, counter_id: int, value: int) -> None:
        await self._pool.execute("UPDATE counters SET last_value = $2 WHERE id = $1", counter_id, value)


def _get_pool():
    from core.database import db
    return db.pool


counter_repo = CounterRepository(pool_provider=_get_pool)
