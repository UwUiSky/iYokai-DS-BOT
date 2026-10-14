"""
core/repositories/invite_stats_repo.py
======================================
Chi ha invitato chi (NF-27). Tabella: core/migrations/0089_invite_stats.sql.
Funzioni coperte: SPEC §23 (NF-27)
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

RIGHE_CLASSIFICA = 10


@dataclass(frozen=True)
class InviteStats:
    totale: int
    presenti: int


class InviteStatsRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def record_join(self, guild_id: int, user_id: int, inviter_id: int, code: str) -> None:
        """Una riga per membro: se rientra con un altro invito la riga si aggiorna."""
        await self._pool.execute(
            """
            INSERT INTO invite_joins (guild_id, user_id, inviter_id, code) VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, user_id) DO UPDATE
                SET inviter_id = EXCLUDED.inviter_id, code = EXCLUDED.code,
                    joined_at = now(), left_at = NULL
            """,
            guild_id, user_id, inviter_id, code,
        )

    async def mark_left(self, guild_id: int, user_id: int) -> None:
        await self._pool.execute(
            "UPDATE invite_joins SET left_at = now() WHERE guild_id = $1 AND user_id = $2 AND left_at IS NULL",
            guild_id, user_id,
        )

    async def stats_for(self, guild_id: int, inviter_id: int) -> InviteStats:
        r = await self._pool.fetchrow(
            "SELECT count(*) AS totale, count(*) FILTER (WHERE left_at IS NULL) AS presenti "
            "FROM invite_joins WHERE guild_id = $1 AND inviter_id = $2",
            guild_id, inviter_id,
        )
        return InviteStats(totale=r["totale"], presenti=r["presenti"])

    async def top(self, guild_id: int, limite: int = RIGHE_CLASSIFICA) -> list[tuple[int, InviteStats]]:
        righe = await self._pool.fetch(
            """
            SELECT inviter_id, count(*) AS totale, count(*) FILTER (WHERE left_at IS NULL) AS presenti
            FROM invite_joins WHERE guild_id = $1
            GROUP BY inviter_id ORDER BY presenti DESC, totale DESC, inviter_id LIMIT $2
            """,
            guild_id, min(limite, RIGHE_CLASSIFICA),
        )
        return [(r["inviter_id"], InviteStats(r["totale"], r["presenti"])) for r in righe]


def _get_pool():
    from core.database import db
    return db.pool


invite_stats_repo = InviteStatsRepository(pool_provider=_get_pool)
