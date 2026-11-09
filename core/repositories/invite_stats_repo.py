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
    finti: int = 0
    bonus: int = 0

    @property
    def punti(self) -> int:
        return self.presenti + self.bonus


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
        self, guild_id: int, user_id: int, inviter_id: int | None, code: str | None, kind: str = "normale",
        finto: bool = False,
    ) -> None:
        """Una riga per membro: se rientra con un altro invito la riga si aggiorna."""
        await self._pool.execute(
            """
            INSERT INTO invite_joins (guild_id, user_id, inviter_id, code, kind, finto) VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (guild_id, user_id) DO UPDATE
                SET inviter_id = EXCLUDED.inviter_id, code = EXCLUDED.code, kind = EXCLUDED.kind,
                    finto = EXCLUDED.finto, joined_at = now(), left_at = NULL
            """,
            guild_id, user_id, inviter_id, code, kind, finto,
        )

    async def e_rientro(self, guild_id: int, user_id: int) -> bool:
        """Il membro era già entrato in passato (c'è la sua riga)."""
        return await self._pool.fetchval(
            "SELECT EXISTS (SELECT 1 FROM invite_joins WHERE guild_id = $1 AND user_id = $2)", guild_id, user_id
        )

    async def mark_left(self, guild_id: int, user_id: int) -> None:
        await self._pool.execute(
            "UPDATE invite_joins SET left_at = now(), usciti = usciti + 1 WHERE guild_id = $1 AND user_id = $2 AND left_at IS NULL",
            guild_id, user_id,
        )

    async def usciti_di(self, guild_id: int, user_id: int) -> int:
        """Quante volte il membro è uscito dal server (e quindi è rientrato)."""
        return await self._pool.fetchval(
            "SELECT COALESCE((SELECT usciti FROM invite_joins WHERE guild_id = $1 AND user_id = $2), 0)", guild_id, user_id
        )

    async def conteggio_per_codice(self, guild_id: int) -> dict[str, int]:
        """Quanti ingressi registrati per ogni codice (per confrontarli con gli usi di Discord)."""
        righe = await self._pool.fetch(
            "SELECT code, count(*) AS n FROM invite_joins WHERE guild_id = $1 AND code IS NOT NULL GROUP BY code", guild_id
        )
        return {r["code"]: r["n"] for r in righe}

    async def azzera(self, guild_id: int) -> tuple[int, int]:
        """Cancella lo storico degli ingressi e i bonus del server. Ritorna (ingressi, bonus) cancellati."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                ingressi = int((await conn.execute("DELETE FROM invite_joins WHERE guild_id = $1", guild_id)).split()[-1])
                bonus = int((await conn.execute("DELETE FROM inviti_bonus WHERE guild_id = $1", guild_id)).split()[-1])
        return ingressi, bonus

    async def righe_per_esportare(self, guild_id: int, limite: int = 200_000) -> list[dict]:
        righe = await self._pool.fetch(
            "SELECT user_id, inviter_id, code, kind, finto, usciti, joined_at, left_at FROM invite_joins "
            "WHERE guild_id = $1 ORDER BY joined_at LIMIT $2",
            guild_id, limite,
        )
        return [dict(r) for r in righe]

    async def statistiche_server(self, guild_id: int, giorni: int = 7) -> dict[str, int]:
        """Ingressi contati, ancora nel server e «attivi»: con almeno un giorno di attività da `giorni` giorni dopo l'ingresso."""
        r = await self._pool.fetchrow(
            """
            SELECT count(*) FILTER (WHERE NOT j.finto) AS ingressi,
                   count(*) FILTER (WHERE NOT j.finto AND j.left_at IS NULL) AS presenti,
                   count(*) FILTER (WHERE NOT j.finto AND j.left_at IS NULL AND EXISTS (
                       SELECT 1 FROM activity_member_daily a WHERE a.guild_id = j.guild_id AND a.user_id = j.user_id
                       AND a.day >= (j.joined_at AT TIME ZONE 'UTC')::date + $2::int AND (a.messages > 0 OR a.voice_seconds > 0)
                   )) AS attivi
            FROM invite_joins j WHERE j.guild_id = $1
            """,
            guild_id, giorni,
        )
        return dict(r)

    async def stats_for(self, guild_id: int, inviter_id: int) -> InviteStats:
        r = await self._pool.fetchrow(
            "SELECT count(*) FILTER (WHERE NOT finto) AS totale, "
            "count(*) FILTER (WHERE left_at IS NULL AND NOT finto) AS presenti, "
            "count(*) FILTER (WHERE finto) AS finti, "
            "COALESCE((SELECT quanti FROM inviti_bonus WHERE guild_id = $1 AND user_id = $2), 0) AS bonus "
            "FROM invite_joins WHERE guild_id = $1 AND inviter_id = $2",
            guild_id, inviter_id,
        )
        return InviteStats(totale=r["totale"], presenti=r["presenti"], finti=r["finti"], bonus=r["bonus"])

    async def top(
        self, guild_id: int, limite: int = RIGHE_CLASSIFICA, *, tetto: int = RIGHE_CLASSIFICA
    ) -> list[tuple[int, InviteStats]]:
        """Classifica per punti (presenti + bonus). Chi ha solo bonus compare. `limite` al massimo `tetto` (100 per chi filtra gli esclusi)."""
        righe = await self._pool.fetch(
            """
            WITH j AS (
                SELECT inviter_id AS uid, count(*) FILTER (WHERE NOT finto) AS totale,
                       count(*) FILTER (WHERE left_at IS NULL AND NOT finto) AS presenti,
                       count(*) FILTER (WHERE finto) AS finti
                FROM invite_joins WHERE guild_id = $1 AND inviter_id > 0 GROUP BY inviter_id
            )
            SELECT COALESCE(j.uid, b.user_id) AS uid, COALESCE(j.totale, 0) AS totale, COALESCE(j.presenti, 0) AS presenti,
                   COALESCE(j.finti, 0) AS finti, COALESCE(b.quanti, 0) AS bonus
            FROM j FULL JOIN (SELECT user_id, quanti FROM inviti_bonus WHERE guild_id = $1) b ON b.user_id = j.uid
            ORDER BY COALESCE(j.presenti, 0) + COALESCE(b.quanti, 0) DESC, COALESCE(j.totale, 0) DESC, 1 LIMIT $2
            """,
            guild_id, min(limite, tetto, 100),
        )
        return [(r["uid"], InviteStats(r["totale"], r["presenti"], r["finti"], r["bonus"])) for r in righe]

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
