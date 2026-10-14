"""
core/repositories/premium_code_repo.py
======================================
Codici premium (tabella `premium_codes`, migrazione 0132, CFG-038). Si salva solo l'impronta del codice.
Funzioni coperte: SPEC §3, catalogo #122
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg


@dataclass(frozen=True)
class CodicePremium:
    module_name: str | None  # None = tutti i moduli premium
    duration_days: int


class PremiumCodeRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def crea(self, code_hash: str, hint: str, module_name: str | None, duration_days: int, created_by: int) -> None:
        await self._pool.execute(
            """
            INSERT INTO premium_codes (code_hash, code_hint, module_name, duration_days, created_by)
            VALUES ($1, $2, $3, $4, $5)
            """,
            code_hash, hint, module_name, duration_days, created_by,
        )

    async def riscatta(self, code_hash: str, user_id: int, guild_id: int) -> CodicePremium | None:
        """Prenota il codice in un colpo solo (due persone insieme: vince una). None se non esiste o è già usato."""
        riga = await self._pool.fetchrow(
            """
            UPDATE premium_codes SET redeemed_by = $2, redeemed_guild_id = $3, redeemed_at = now()
            WHERE code_hash = $1 AND redeemed_at IS NULL
            RETURNING module_name, duration_days
            """,
            code_hash, user_id, guild_id,
        )
        return None if riga is None else CodicePremium(riga["module_name"], riga["duration_days"])

    async def annulla_riscatto(self, code_hash: str) -> None:
        """Rimette il codice a disposizione se lo sblocco non è riuscito."""
        await self._pool.execute(
            "UPDATE premium_codes SET redeemed_by = NULL, redeemed_guild_id = NULL, redeemed_at = NULL WHERE code_hash = $1",
            code_hash,
        )


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


premium_code_repo = PremiumCodeRepository(pool_provider=_get_pool)
