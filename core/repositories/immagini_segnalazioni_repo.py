"""
core/repositories/immagini_segnalazioni_repo.py
===============================================
Segnalazioni dei post di Lemmy di `/immagini post`: una per persona e per post; da 3 persone diverse in su
il post è bloccato. Tabella: core/migrations/0576_immagini_segnalazioni.sql.
Funzioni coperte: SPEC §16 (FUN-053, FUN-055)
"""

from __future__ import annotations

import asyncpg

SOGLIA_BLOCCO = 3


class ImmaginiSegnalazioniRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def segnala(self, post_key: str, user_id: int, guild_id: int) -> int:
        """Registra la segnalazione (una sola per persona) e dice quante persone hanno segnalato il post."""
        return await self._pool.fetchval(
            "WITH nuova AS (INSERT INTO immagini_segnalazioni (post_key, user_id, guild_id) VALUES ($1, $2, $3) "
            "ON CONFLICT DO NOTHING RETURNING 1) "
            "SELECT COUNT(*)::int + (SELECT COUNT(*)::int FROM nuova) FROM immagini_segnalazioni WHERE post_key = $1",
            post_key, user_id, guild_id,
        )

    async def bloccati(self, chiavi: list[str]) -> set[str]:
        righe = await self._pool.fetch(
            "SELECT post_key FROM immagini_segnalazioni WHERE post_key = ANY($1::text[]) "
            "GROUP BY post_key HAVING COUNT(*) >= $2",
            chiavi, SOGLIA_BLOCCO,
        )
        return {r["post_key"] for r in righe}


def _get_pool():
    from core.database import db

    return db.pool


immagini_segnalazioni_repo = ImmaginiSegnalazioniRepository(pool_provider=_get_pool)
