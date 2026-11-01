"""
core/repositories/staff_carico_repo.py
======================================
Quanto lavoro ha fatto ogni persona dello staff in un periodo: casi aperti, appelli decisi,
ticket presi in carico (con tempo di risposta, riaperti, voto), sanzioni annullate in appello e
ore di lavoro. Solo letture.
Funzioni coperte: SPEC §23.17 (NF-41, D50)
"""

from __future__ import annotations

import asyncpg

from core.staff_rischio_logic import CaricoStaff


class StaffCaricoRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def carico(self, guild_id: int, giorni: int, escludi: tuple[int, ...] = ()) -> list[CaricoStaff]:
        """Un elemento per persona con almeno un'attività. `escludi`: i bot (la scala automatica)."""
        righe = await self._pool.fetch(
            """
            WITH casi AS (
                SELECT moderator_id AS staff, count(*) AS n FROM moderation_cases
                WHERE guild_id = $1 AND created_at >= now() - make_interval(days => $2)
                GROUP BY moderator_id
            ), appelli AS (
                SELECT deciso_da AS staff, count(*) AS n FROM ban_appelli
                WHERE guild_id = $1 AND deciso_da IS NOT NULL AND deciso_il >= now() - make_interval(days => $2)
                GROUP BY deciso_da
            ), annullati AS (
                SELECT c.moderator_id AS staff, count(*) AS n
                FROM ban_appelli a JOIN moderation_cases c
                  ON c.guild_id = a.guild_id AND c.case_number = a.case_number
                WHERE a.guild_id = $1 AND a.stato = 'accettato'
                  AND a.deciso_il >= now() - make_interval(days => $2)
                GROUP BY c.moderator_id
            ), ticket AS (
                SELECT claimed_by AS staff, count(*) AS n,
                       sum(riaperto_volte) AS riaperti,
                       extract(epoch FROM avg(first_response_at - created_at)) AS risposta,
                       avg(rating) AS voto
                FROM tickets
                WHERE guild_id = $1 AND claimed_by IS NOT NULL AND created_at >= now() - make_interval(days => $2)
                GROUP BY claimed_by
            ), persone AS (
                SELECT staff FROM casi UNION SELECT staff FROM appelli UNION SELECT staff FROM ticket
            )
            SELECT p.staff, COALESCE(c.n, 0) AS casi, COALESCE(a.n, 0) AS appelli, COALESCE(t.n, 0) AS ticket,
                   COALESCE(t.riaperti, 0) AS riaperti, COALESCE(x.n, 0) AS annullati,
                   t.risposta, t.voto
            FROM persone p
            LEFT JOIN casi c ON c.staff = p.staff
            LEFT JOIN appelli a ON a.staff = p.staff
            LEFT JOIN annullati x ON x.staff = p.staff
            LEFT JOIN ticket t ON t.staff = p.staff
            WHERE p.staff <> 0 AND NOT (p.staff = ANY($3::bigint[]))
            """,
            guild_id, giorni, list(escludi),
        )
        return [
            CaricoStaff(
                r["staff"], r["casi"], r["appelli"], r["ticket"], int(r["riaperti"]), r["annullati"],
                float(r["risposta"]) if r["risposta"] is not None else None,
                round(float(r["voto"]), 1) if r["voto"] is not None else None,
            )
            for r in righe
        ]

    async def ore_attivita(self, guild_id: int, giorni: int, escludi: tuple[int, ...] = ()) -> dict[int, list[int]]:
        """Per ogni persona dello staff, quante azioni ha fatto in ciascuna ora UTC (casi e prime risposte)."""
        righe = await self._pool.fetch(
            """
            SELECT staff, ora, count(*) AS n FROM (
                SELECT moderator_id AS staff, extract(hour FROM created_at AT TIME ZONE 'UTC')::int AS ora
                FROM moderation_cases
                WHERE guild_id = $1 AND created_at >= now() - make_interval(days => $2)
                UNION ALL
                SELECT claimed_by, extract(hour FROM first_response_at AT TIME ZONE 'UTC')::int
                FROM tickets
                WHERE guild_id = $1 AND claimed_by IS NOT NULL AND first_response_at IS NOT NULL
                  AND first_response_at >= now() - make_interval(days => $2)
                UNION ALL
                SELECT deciso_da, extract(hour FROM deciso_il AT TIME ZONE 'UTC')::int
                FROM ban_appelli
                WHERE guild_id = $1 AND deciso_da IS NOT NULL
                  AND deciso_il >= now() - make_interval(days => $2)
            ) a
            WHERE staff <> 0 AND NOT (staff = ANY($3::bigint[]))
            GROUP BY staff, ora
            """,
            guild_id, giorni, list(escludi),
        )
        ore: dict[int, list[int]] = {}
        for r in righe:
            ore.setdefault(r["staff"], [0] * 24)[r["ora"]] = r["n"]
        return ore

    async def segnali_utente(self, guild_id: int, user_id: int) -> tuple[int, int, int, int, int]:
        """(warn attivi, timeout 90 giorni, kick, ban o tempban, spam trap) dai casi di moderazione."""
        riga = await self._pool.fetchrow(
            """
            SELECT
                count(*) FILTER (WHERE action_type = 'warn' AND active) AS warn,
                count(*) FILTER (WHERE action_type = 'timeout' AND created_at >= now() - interval '90 days') AS timeout,
                count(*) FILTER (WHERE action_type IN ('kick', 'spam_trap_kick')) AS kick,
                count(*) FILTER (WHERE action_type IN ('ban', 'tempban', 'softban', 'spam_trap_ban')) AS ban,
                count(*) FILTER (WHERE action_type LIKE 'spam_trap%') AS trappola
            FROM moderation_cases WHERE guild_id = $1 AND user_id = $2
            """,
            guild_id, user_id,
        )
        return riga["warn"], riga["timeout"], riga["kick"], riga["ban"], riga["trappola"]

    async def doppi_di(self, guild_id: int, user_id: int) -> list[str]:
        """I livelli dei doppi trovati dalla verifica web (stesso server) per questo membro."""
        righe = await self._pool.fetch(
            "SELECT livello FROM verify_doppi WHERE guild_id = $1 AND (user_id = $2 OR altro_user_id = $2)",
            guild_id, user_id,
        )
        return [r["livello"] for r in righe]


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


staff_carico_repo = StaffCaricoRepository(pool_provider=_get_pool)
