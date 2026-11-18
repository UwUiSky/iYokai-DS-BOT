"""
core/repositories/lasciti_repo.py
=================================
Monete lasciate in un canale (ECO-052). Il saldo di chi lascia scende nella stessa transazione
che scrive la riga; chi prende lo fa con un UPDATE condizionato (`preso_da IS NULL`) insieme
all'accredito; se nessuno prende, le monete tornano a chi le ha lasciate (una volta sola).
Funzioni coperte: ECO-052
"""

from __future__ import annotations

import asyncpg

from core.repositories.leveling_repo import add_coins_in, refund_coins_in, spend_coins_in

MAX_LASCITO = 1_000_000
DURATA_SECONDI = 300


class LascitiRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def lascia(self, guild_id: int, user_id: int, importo: int) -> int | None:
        """Toglie `importo` a chi lascia e scrive il lascito. Restituisce l'id, o None se il saldo non basta."""
        if not 1 <= importo <= MAX_LASCITO:
            raise ValueError("Importo non valido.")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                if not await spend_coins_in(conn, guild_id, user_id, importo):
                    return None
                return await conn.fetchval(
                    "INSERT INTO economia_lasciti (guild_id, user_id, importo, scade_at) "
                    "VALUES ($1, $2, $3, now() + make_interval(secs => $4)) RETURNING id",
                    guild_id, user_id, importo, float(DURATA_SECONDI),
                )

    async def prendi(self, lascito_id: int, guild_id: int, chi: int) -> int | None:
        """Chi clicca per primo prende le monete (non quelle che ha lasciato lui). None se non si può."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                importo = await conn.fetchval(
                    "UPDATE economia_lasciti SET preso_da = $3 WHERE id = $1 AND guild_id = $2 "
                    "AND preso_da IS NULL AND NOT rimborsato AND scade_at > now() AND user_id <> $3 "
                    "RETURNING importo",
                    lascito_id, guild_id, chi,
                )
                if importo is None:
                    return None
                await add_coins_in(conn, guild_id, chi, importo, classifica=False)
                return importo

    async def rimborsa_scaduti(self, limite: int = 100) -> int:
        """Rimette le monete a chi le ha lasciate se nessuno le ha prese. Restituisce quanti lasciti."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                righe = await conn.fetch(
                    "UPDATE economia_lasciti SET rimborsato = TRUE WHERE id IN ("
                    "SELECT id FROM economia_lasciti WHERE preso_da IS NULL AND NOT rimborsato AND scade_at <= now() "
                    "ORDER BY id LIMIT $1 FOR UPDATE SKIP LOCKED) RETURNING guild_id, user_id, importo",
                    limite,
                )
                for r in righe:
                    await refund_coins_in(conn, r["guild_id"], r["user_id"], r["importo"])
                return len(righe)


def _get_pool():
    from core.database import db

    return db.pool


lasciti_repo = LascitiRepository(pool_provider=_get_pool)
