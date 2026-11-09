"""
core/repositories/suoni_ruoli_repo.py
=====================================
Ruoli consentiti o vietati per ogni suono della soundboard (massimo 20 per suono, controllo e scrittura sotto
lo stesso blocco). Tabella: core/migrations/0577_suoni_ruoli_smash.sql.
Funzioni coperte: SPEC §23 (FUN-076; B11 di #131)
"""

from __future__ import annotations

import asyncpg

from core.suoni_ruoli_logic import MAX_RUOLI_PER_SUONO, RUOLO_BLOCCO


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
            prima = await conn.fetchval(
                "SELECT modo FROM suoni_ruoli WHERE guild_id = $1 AND suono = $2 AND ruolo_id = $3", guild_id, suono, ruolo_id
            )
            if prima is None:
                totale = await conn.fetchval(
                    "SELECT count(*) FROM suoni_ruoli WHERE guild_id = $1 AND suono = $2 AND ruolo_id <> $3", guild_id, suono, RUOLO_BLOCCO)
                if totale >= MAX_RUOLI_PER_SUONO:
                    return "tetto"
            await conn.execute(
                "INSERT INTO suoni_ruoli (guild_id, suono, ruolo_id, modo) VALUES ($1, $2, $3, $4) "
                "ON CONFLICT (guild_id, suono, ruolo_id) DO UPDATE SET modo = EXCLUDED.modo",
                guild_id, suono, ruolo_id, modo,
            )
            if modo == "consenti":
                await conn.execute(
                    "DELETE FROM suoni_ruoli WHERE guild_id = $1 AND suono = $2 AND ruolo_id = $3", guild_id, suono, RUOLO_BLOCCO)
            return "ok"

    async def togli(self, guild_id: int, suono: str, ruolo_id: int) -> bool:
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(7141, $1::int)", guild_id % 2_000_000_000)
            tolto = await conn.fetchval(
                "DELETE FROM suoni_ruoli WHERE guild_id = $1 AND suono = $2 AND ruolo_id = $3 AND ruolo_id <> $4 RETURNING modo",
                guild_id, suono, ruolo_id, RUOLO_BLOCCO)
            if tolto == "consenti":
                await self._blocca_se_serve(conn, guild_id, suono)
            return tolto is not None

    async def togli_ruolo(self, guild_id: int, ruolo_id: int) -> None:
        """Il ruolo è stato cancellato dal server: via da tutti i suoni (chi restava senza «consenti» resta bloccato)."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(7141, $1::int)", guild_id % 2_000_000_000)
            righe = await conn.fetch(
                "DELETE FROM suoni_ruoli WHERE guild_id = $1 AND ruolo_id = $2 AND ruolo_id <> $3 RETURNING suono, modo",
                guild_id, ruolo_id, RUOLO_BLOCCO)
            for r in righe:
                if r["modo"] == "consenti":
                    await self._blocca_se_serve(conn, guild_id, r["suono"])

    @staticmethod
    async def _blocca_se_serve(conn, guild_id: int, suono: str) -> None:
        """Se al suono non resta nessun ruolo «consenti», mette la riga di blocco."""
        resta = await conn.fetchval(
            "SELECT 1 FROM suoni_ruoli WHERE guild_id = $1 AND suono = $2 AND modo = 'consenti' LIMIT 1", guild_id, suono)
        if not resta:
            await conn.execute(
                "INSERT INTO suoni_ruoli (guild_id, suono, ruolo_id, modo) VALUES ($1, $2, $3, 'consenti') ON CONFLICT DO NOTHING",
                guild_id, suono, RUOLO_BLOCCO)

    async def regole(self, guild_id: int, suono: str) -> list[tuple[int, str]]:
        righe = await self._pool.fetch(
            "SELECT ruolo_id, modo FROM suoni_ruoli WHERE guild_id = $1 AND suono = $2 ORDER BY ruolo_id", guild_id, suono
        )
        return [(r["ruolo_id"], r["modo"]) for r in righe]


def _get_pool():
    from core.database import db

    return db.pool


suoni_ruoli_repo = SuoniRuoliRepository(pool_provider=_get_pool)
