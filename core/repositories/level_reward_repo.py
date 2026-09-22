"""
core/repositories/level_reward_repo.py
==========================================
Ruoli-premio per livello raggiunto (SPEC.md §15.13). Cumulativo, non
esclusivo: un utente che sale di livello riceve OGNI ruolo-premio
configurato fino al suo nuovo livello che non ha già — non solo
quello più alto. Coerente con l'aspettativa comune di questo tipo di
funzione (i "badge" più vecchi restano, non vengono tolti quando se
ne sblocca uno nuovo).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class LevelReward:
    id: int
    guild_id: int
    level_threshold: int
    role_id: int
    created_at: datetime


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS level_reward_roles (
            id               SERIAL PRIMARY KEY,
            guild_id         BIGINT NOT NULL,
            level_threshold  INTEGER NOT NULL,
            role_id          BIGINT NOT NULL,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (guild_id, level_threshold)
        );

        CREATE INDEX IF NOT EXISTS idx_level_reward_roles_guild
            ON level_reward_roles (guild_id, level_threshold);
        """
    )


class LevelRewardRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    def _row_to_reward(self, row) -> LevelReward:
        return LevelReward(
            id=row["id"],
            guild_id=row["guild_id"],
            level_threshold=row["level_threshold"],
            role_id=row["role_id"],
            created_at=row["created_at"],
        )

    async def add_reward(self, guild_id: int, level_threshold: int, role_id: int) -> int:
        """
        Un solo ruolo-premio per livello per server (UNIQUE
        guild_id+level_threshold) — se il livello era già
        configurato, sostituisce il ruolo invece di crearne un
        secondo, per evitare configurazioni ambigue ("livello 10 dà
        sia il ruolo X che il ruolo Y" non ha un senso univoco).
        """
        row = await self._pool.fetchrow(
            """
            INSERT INTO level_reward_roles (guild_id, level_threshold, role_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, level_threshold) DO UPDATE
                SET role_id = EXCLUDED.role_id
            RETURNING id
            """,
            guild_id,
            level_threshold,
            role_id,
        )
        return row["id"]

    async def remove_reward(self, reward_id: int, guild_id: int) -> bool:
        result = await self._pool.execute(
            "DELETE FROM level_reward_roles WHERE id = $1 AND guild_id = $2",
            reward_id,
            guild_id,
        )
        return result.endswith(" 1")

    async def list_rewards(self, guild_id: int) -> list[LevelReward]:
        rows = await self._pool.fetch(
            "SELECT * FROM level_reward_roles WHERE guild_id = $1 ORDER BY level_threshold",
            guild_id,
        )
        return [self._row_to_reward(r) for r in rows]

    async def get_rewards_up_to_level(self, guild_id: int, level: int) -> list[LevelReward]:
        """Tutti i ruoli-premio con soglia <= level — CUMULATIVO,
        non solo quello più alto (vedi nota in cima al file)."""
        rows = await self._pool.fetch(
            """
            SELECT * FROM level_reward_roles
            WHERE guild_id = $1 AND level_threshold <= $2
            ORDER BY level_threshold
            """,
            guild_id,
            level,
        )
        return [self._row_to_reward(r) for r in rows]


def _get_pool():
    from core.database import db
    return db.pool


level_reward_repo = LevelRewardRepository(pool_provider=_get_pool)
