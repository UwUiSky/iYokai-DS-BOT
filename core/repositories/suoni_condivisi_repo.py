"""
core/repositories/suoni_condivisi_repo.py
=========================================
Quali server mettono i loro suoni a disposizione degli altri e quali server usano quelli degli altri (D127, D129).
Tabella: core/migrations/0940_suoni_condivisi.sql.
Funzioni coperte: SPEC §23 (FUN-075)
"""

from __future__ import annotations

import asyncpg


class SuoniCondivisiRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def imposta(self, guild_id: int, condividi: bool | None = None, usa_esterni: bool | None = None) -> tuple[bool, bool]:
        """Scrive solo ciò che è dato (una INSERT con ON CONFLICT) e restituisce (condividi, usa_esterni)."""
        riga = await self._pool.fetchrow(
            "INSERT INTO suoni_condivisione (guild_id, condividi, usa_esterni) "
            "VALUES ($1, COALESCE($2::boolean, FALSE), COALESCE($3::boolean, TRUE)) "
            "ON CONFLICT (guild_id) DO UPDATE SET condividi = COALESCE($2::boolean, suoni_condivisione.condividi), "
            "usa_esterni = COALESCE($3::boolean, suoni_condivisione.usa_esterni), aggiornato = now() "
            "RETURNING condividi, usa_esterni",
            guild_id, condividi, usa_esterni,
        )
        return riga["condividi"], riga["usa_esterni"]

    async def leggi(self, guild_id: int) -> tuple[bool, bool]:
        """(condividi, usa_esterni) con i valori di base se il server non ha scelto."""
        riga = await self._pool.fetchrow("SELECT condividi, usa_esterni FROM suoni_condivisione WHERE guild_id = $1", guild_id)
        return (riga["condividi"], riga["usa_esterni"]) if riga else (False, True)

    async def server_che_condividono(self, guild_ids: list[int]) -> set[int]:
        """Tra i server dati, quelli che hanno scelto di condividere."""
        if not guild_ids:
            return set()
        righe = await self._pool.fetch(
            "SELECT guild_id FROM suoni_condivisione WHERE condividi AND guild_id = ANY($1::bigint[])", guild_ids
        )
        return {r["guild_id"] for r in righe}


def _get_pool():
    from core.database import db

    return db.pool


suoni_condivisi_repo = SuoniCondivisiRepository(pool_provider=_get_pool)
