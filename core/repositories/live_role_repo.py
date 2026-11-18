"""
core/repositories/live_role_repo.py
===================================
Le regole del ruolo «in diretta» di un server (ALR-042..048): ruolo, filtri, esclusi, eccezioni e annuncio.
Tabelle: core/migrations/0693_ruolo_live_regole.sql. Tetto di 5 regole per server e di 25 voci per regola,
controllati nella stessa transazione della scrittura. Funzioni coperte: SPEC §10.13 (#129 ALR-042..048)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import asyncpg

MAX_REGOLE = 5
MAX_VOCI = 25
TIPI = ("escluso_ruolo", "escluso_membro", "eccezione")
_CAMPI = ("only_role_id", "keywords", "games", "announce_channel_id", "announce_template", "announce_gap_minutes")


@dataclass(frozen=True)
class RegolaLive:
    id: int
    guild_id: int
    role_id: int
    only_role_id: int | None = None
    keywords: str = ""
    games: str = ""
    announce_channel_id: int | None = None
    announce_template: str = ""
    announce_gap_minutes: int = 360
    esclusi_ruoli: frozenset[int] = field(default_factory=frozenset)
    esclusi_membri: frozenset[int] = field(default_factory=frozenset)
    eccezioni: frozenset[int] = field(default_factory=frozenset)


class LiveRoleRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def regole(self, guild_id: int) -> list[RegolaLive]:
        rows = await self._pool.fetch("SELECT * FROM live_role_regole WHERE guild_id = $1 ORDER BY id", guild_id)
        voci = await self._pool.fetch("SELECT regola_id, tipo, target_id FROM live_role_voci WHERE guild_id = $1", guild_id)
        per_regola: dict[int, dict[str, set[int]]] = {}
        for v in voci:
            per_regola.setdefault(v["regola_id"], {t: set() for t in TIPI})[v["tipo"]].add(v["target_id"])
        risultato = []
        for r in rows:
            v = per_regola.get(r["id"], {t: set() for t in TIPI})
            risultato.append(RegolaLive(
                id=r["id"], guild_id=r["guild_id"], role_id=r["role_id"], only_role_id=r["only_role_id"],
                keywords=r["keywords"], games=r["games"], announce_channel_id=r["announce_channel_id"],
                announce_template=r["announce_template"], announce_gap_minutes=r["announce_gap_minutes"],
                esclusi_ruoli=frozenset(v["escluso_ruolo"]), esclusi_membri=frozenset(v["escluso_membro"]),
                eccezioni=frozenset(v["eccezione"]),
            ))
        return risultato

    async def server_con_regole(self) -> list[int]:
        return [r["guild_id"] for r in await self._pool.fetch("SELECT DISTINCT guild_id FROM live_role_regole")]

    async def aggiungi(self, guild_id: int, role_id: int, created_by: int, only_role_id: int | None = None) -> int | None:
        """None = tetto di regole raggiunto (conteggio e scrittura insieme)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtext('live_role_regole'), $1)", guild_id % 2_147_483_647)
                if await conn.fetchval("SELECT count(*) FROM live_role_regole WHERE guild_id = $1", guild_id) >= MAX_REGOLE:
                    return None
                return await conn.fetchval(
                    "INSERT INTO live_role_regole (guild_id, role_id, only_role_id, created_by) VALUES ($1, $2, $3, $4) RETURNING id",
                    guild_id, role_id, only_role_id, created_by,
                )

    async def rimuovi(self, guild_id: int, regola_id: int) -> bool:
        r = await self._pool.execute("DELETE FROM live_role_regole WHERE id = $1 AND guild_id = $2", regola_id, guild_id)
        return r.endswith(" 1")

    async def imposta(self, guild_id: int, regola_id: int, **campi) -> bool:
        sconosciuti = set(campi) - set(_CAMPI)
        if sconosciuti:
            raise ValueError(f"Campi non validi: {sorted(sconosciuti)}")
        if not campi:
            return True
        assegna = ", ".join(f"{c} = ${i + 3}" for i, c in enumerate(campi))
        r = await self._pool.execute(
            f"UPDATE live_role_regole SET {assegna} WHERE id = $1 AND guild_id = $2", regola_id, guild_id, *campi.values()
        )
        return r.endswith(" 1")

    async def voce(self, guild_id: int, regola_id: int, tipo: str, target_id: int, aggiungi: bool) -> str:
        """«ok», «manca» (regola inesistente) o «pieno» (25 voci di quel tipo)."""
        if tipo not in TIPI:
            raise ValueError(tipo)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                if not await conn.fetchval("SELECT 1 FROM live_role_regole WHERE id = $1 AND guild_id = $2 FOR UPDATE", regola_id, guild_id):
                    return "manca"
                if not aggiungi:
                    await conn.execute(
                        "DELETE FROM live_role_voci WHERE regola_id = $1 AND tipo = $2 AND target_id = $3", regola_id, tipo, target_id
                    )
                    return "ok"
                if await conn.fetchval("SELECT count(*) FROM live_role_voci WHERE regola_id = $1 AND tipo = $2", regola_id, tipo) >= MAX_VOCI:
                    return "pieno"
                await conn.execute(
                    "INSERT INTO live_role_voci (regola_id, guild_id, tipo, target_id) VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING",
                    regola_id, guild_id, tipo, target_id,
                )
                return "ok"


def _get_pool():
    from core.database import db

    return db.pool


live_role_repo = LiveRoleRepository(pool_provider=_get_pool)
