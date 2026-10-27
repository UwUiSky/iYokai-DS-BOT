"""
core/repositories/invite_stats_repo.py
======================================
Chi ha invitato chi (NF-27), con il tipo di link usato e lo storico di un membro.
Tabella: core/migrations/0089_invite_stats.sql (+ 0380).
Funzioni coperte: SPEC §23 (NF-27, link personali r10)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg

RIGHE_CLASSIFICA = 10
RIGHE_STORICO = 15


@dataclass(frozen=True)
class InviteStats:
    totale: int
    presenti: int


@dataclass(frozen=True)
class IngressoInvitato:
    user_id: int
    joined_at: datetime
    left_at: datetime | None
    kind: str


@dataclass(frozen=True)
class IngressoDi:
    inviter_id: int | None
    code: str | None
    kind: str
    joined_at: datetime
    left_at: datetime | None


class InviteStatsRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def record_join(
        self, guild_id: int, user_id: int, inviter_id: int | None, code: str | None, kind: str = "normale"
    ) -> None:
        """Una riga per membro: se rientra con un altro invito la riga si aggiorna."""
        await self._pool.execute(
            """
            INSERT INTO invite_joins (guild_id, user_id, inviter_id, code, kind) VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (guild_id, user_id) DO UPDATE
                SET inviter_id = EXCLUDED.inviter_id, code = EXCLUDED.code, kind = EXCLUDED.kind,
                    joined_at = now(), left_at = NULL
            """,
            guild_id, user_id, inviter_id, code, kind,
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
            FROM invite_joins WHERE guild_id = $1 AND inviter_id > 0
            GROUP BY inviter_id ORDER BY presenti DESC, totale DESC, inviter_id LIMIT $2
            """,
            guild_id, min(limite, RIGHE_CLASSIFICA),
        )
        return [(r["inviter_id"], InviteStats(r["totale"], r["presenti"])) for r in righe]

    async def ingresso_di(self, guild_id: int, user_id: int) -> IngressoDi | None:
        """Da chi (e con quale tipo di link) è stato invitato un membro."""
        r = await self._pool.fetchrow(
            "SELECT inviter_id, code, kind, joined_at, left_at FROM invite_joins WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id,
        )
        return None if r is None else IngressoDi(r["inviter_id"], r["code"], r["kind"], r["joined_at"], r["left_at"])

    async def invitati_da(
        self, guild_id: int, inviter_id: int, limite: int = RIGHE_STORICO
    ) -> list[IngressoInvitato]:
        """Gli ultimi ingressi portati da un membro (i più recenti prima)."""
        righe = await self._pool.fetch(
            "SELECT user_id, joined_at, left_at, kind FROM invite_joins WHERE guild_id = $1 AND inviter_id = $2 "
            "ORDER BY joined_at DESC LIMIT $3",
            guild_id, inviter_id, min(limite, 50),
        )
        return [IngressoInvitato(r["user_id"], r["joined_at"], r["left_at"], r["kind"]) for r in righe]

    async def per_tipo(self, guild_id: int) -> dict[str, int]:
        """Quanti ingressi per tipo di link, nel server."""
        righe = await self._pool.fetch(
            "SELECT kind, count(*) AS n FROM invite_joins WHERE guild_id = $1 GROUP BY kind", guild_id
        )
        return {r["kind"]: r["n"] for r in righe}

    async def ultimi_ingressi(self, guild_id: int, limite: int = RIGHE_STORICO) -> list[tuple[int, IngressoDi]]:
        """Gli ultimi ingressi registrati nel server (per la pagina dell'admin)."""
        righe = await self._pool.fetch(
            "SELECT user_id, inviter_id, code, kind, joined_at, left_at FROM invite_joins WHERE guild_id = $1 "
            "ORDER BY joined_at DESC LIMIT $2",
            guild_id, min(limite, 50),
        )
        return [
            (r["user_id"], IngressoDi(r["inviter_id"], r["code"], r["kind"], r["joined_at"], r["left_at"]))
            for r in righe
        ]


def _get_pool():
    from core.database import db
    return db.pool


invite_stats_repo = InviteStatsRepository(pool_provider=_get_pool)
