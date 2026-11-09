"""
core/repositories/battitura_repo.py
===================================
Testi di battitura scritti dal server (`battitura_testi`). Il tetto per server è controllato dentro la transazione
con un blocco per server. Tabella: core/migrations/0574_battitura_testi.sql.
Funzioni coperte: SPEC §16 (FUN-012; #131)
"""

from __future__ import annotations

import asyncpg

from core.gruppo_logic import TETTO_TESTI_SERVER


class BattituraRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def aggiungi(self, guild_id: int, autore_id: int, testo: str, tetto: int = TETTO_TESTI_SERVER) -> int | None:
        """L'id del testo nuovo, None se il server ha già `tetto` testi (blocco per server, poi controllo e scrittura)."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(7132, $1::int)", guild_id % 2_000_000_000)
            return await conn.fetchval(
                "INSERT INTO battitura_testi (guild_id, testo, autore_id) "
                "SELECT $1, $2, $3 WHERE (SELECT count(*) FROM battitura_testi WHERE guild_id = $1) < $4 RETURNING id",
                guild_id, testo, autore_id, tetto,
            )

    async def elenco(self, guild_id: int) -> list[tuple[int, str]]:
        righe = await self._pool.fetch(
            "SELECT id, testo FROM battitura_testi WHERE guild_id = $1 ORDER BY id LIMIT 500", guild_id
        )
        return [(r["id"], r["testo"]) for r in righe]

    async def rimuovi(self, guild_id: int, testo_id: int) -> bool:
        esito = await self._pool.execute("DELETE FROM battitura_testi WHERE guild_id = $1 AND id = $2", guild_id, testo_id)
        return esito.endswith(" 1")


def _get_pool():
    from core.database import db

    return db.pool


battitura_repo = BattituraRepository(pool_provider=_get_pool)
