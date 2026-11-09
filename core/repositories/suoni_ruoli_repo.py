"""
core/repositories/suoni_ruoli_repo.py
=====================================
Ruoli consentiti o vietati per ogni suono della soundboard (massimo 20 per suono, controllo e scrittura sotto
lo stesso blocco). Tabella: core/migrations/0577_suoni_ruoli_smash.sql.
Funzioni coperte: SPEC §23 (FUN-076; B11 di #131)
"""

from __future__ import annotations

import asyncpg

from core.suoni_ruoli_logic import MAX_RUOLI_PER_SUONO


class SuoniRuoliRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def imposta(self, guild_id: int, suono: str, ruolo_id: int, modo: str) -> str:
        """'ok' (aggiunto o cambiato) oppure 'tetto' (il suono ha già 20 ruoli e questo è nuovo)."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(7141, $1::int)", guild_id % 2_000_000_000)
            gia = await conn.fetchval(
                "SELECT 1 FROM suoni_ruoli WHERE guild_id = $1 AND suono = $2 AND ruolo_id = $3", guild_id, suono, ruolo_id
            )
            if not gia:
                totale = await conn.fetchval("SELECT count(*) FROM suoni_ruoli WHERE guild_id = $1 AND suono = $2", guild_id, suono)
                if totale >= MAX_RUOLI_PER_SUONO:
                    return "tetto"
            await conn.execute(
                "INSERT INTO suoni_ruoli (guild_id, suono, ruolo_id, modo) VALUES ($1, $2, $3, $4) "
                "ON CONFLICT (guild_id, suono, ruolo_id) DO UPDATE SET modo = EXCLUDED.modo",
                guild_id, suono, ruolo_id, modo,
            )
            return "ok"

    async def togli(self, guild_id: int, suono: str, ruolo_id: int) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM suoni_ruoli WHERE guild_id = $1 AND suono = $2 AND ruolo_id = $3", guild_id, suono, ruolo_id
        )
        return esito.endswith(" 1")

    async def togli_ruolo(self, guild_id: int, ruolo_id: int) -> None:
        """Il ruolo è stato cancellato dal server: via da tutti i suoni."""
        await self._pool.execute("DELETE FROM suoni_ruoli WHERE guild_id = $1 AND ruolo_id = $2", guild_id, ruolo_id)

    async def regole(self, guild_id: int, suono: str) -> list[tuple[int, str]]:
        righe = await self._pool.fetch(
            "SELECT ruolo_id, modo FROM suoni_ruoli WHERE guild_id = $1 AND suono = $2 ORDER BY ruolo_id", guild_id, suono
        )
        return [(r["ruolo_id"], r["modo"]) for r in righe]


def _get_pool():
    from core.database import db

    return db.pool


suoni_ruoli_repo = SuoniRuoliRepository(pool_provider=_get_pool)
