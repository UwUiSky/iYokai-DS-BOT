"""
core/repositories/autorisposte_globali_repo.py
==============================================
Risposte automatiche dell'owner (valgono in ogni server, massimo 20) e la scelta di ogni server di spegnerle.
Tabelle: core/migrations/0556_risposte_regex_globali.sql.
Funzioni coperte: catalogo #128 UTL-055 (D69, B18)
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from core.autoresponder_logic import MAX_GLOBALI


@dataclass(frozen=True)
class RispostaGlobale:
    id: int
    innesco: str
    risposta: str


class AutorisposteGlobaliRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def elenco(self) -> list[RispostaGlobale]:
        righe = await self._pool.fetch("SELECT id, innesco, risposta FROM autorisposte_globali ORDER BY id")
        return [RispostaGlobale(**dict(r)) for r in righe]

    async def aggiungi(self, innesco: str, risposta: str, creata_da: int) -> str:
        """«ok», «esiste» o «pieno». Tetto e scrittura nella stessa query."""
        async with self._pool.acquire() as con, con.transaction():
            await con.execute("SELECT pg_advisory_xact_lock(5518)")
            if await con.fetchval("SELECT count(*) FROM autorisposte_globali") >= MAX_GLOBALI:
                return "pieno"
            fatta = await con.fetchval(
                "INSERT INTO autorisposte_globali (innesco, risposta, creata_da) VALUES ($1,$2,$3) "
                "ON CONFLICT (lower(innesco)) DO NOTHING RETURNING id", innesco, risposta, creata_da)
            return "ok" if fatta else "esiste"

    async def togli(self, numero: int) -> bool:
        return (await self._pool.execute("DELETE FROM autorisposte_globali WHERE id = $1", numero)).endswith(" 1")

    async def spente_nel_server(self, guild_id: int) -> bool:
        return bool(await self._pool.fetchval("SELECT globali_spente FROM autorisposte_server WHERE guild_id = $1", guild_id))

    async def imposta_spente(self, guild_id: int, spente: bool) -> None:
        await self._pool.execute(
            "INSERT INTO autorisposte_server (guild_id, globali_spente) VALUES ($1,$2) "
            "ON CONFLICT (guild_id) DO UPDATE SET globali_spente = $2", guild_id, spente)


def _get_pool():
    from core.database import db

    return db.pool


autorisposte_globali_repo = AutorisposteGlobaliRepository(pool_provider=_get_pool)
