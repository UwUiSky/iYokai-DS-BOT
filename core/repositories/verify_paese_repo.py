"""
core/repositories/verify_paese_repo.py
======================================
Paese dell'account di chi si verifica dalla pagina web (tabella `verify_paese`, migrazione 0490, D53).
Solo il codice ISO del paese e la lingua del client: mai l'IP, mai la città.
Funzioni coperte: SPEC §4.2 (paese, D53)
"""

from __future__ import annotations

import asyncpg


class VerifyPaeseRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def salva_lingua(self, guild_id: int, user_id: int, lingua: str | None) -> None:
        """La lingua del client, quando il membro preme il bottone (prima della pagina web)."""
        if not lingua:
            return
        await self._pool.execute(
            """
            INSERT INTO verify_paese (guild_id, user_id, lingua) VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET lingua = EXCLUDED.lingua
            """,
            guild_id, user_id, lingua[:16],
        )

    async def registra(self, guild_id: int, user_id: int, paese: str, lingua: str | None, stato: str) -> None:
        await self._pool.execute(
            """
            INSERT INTO verify_paese (guild_id, user_id, paese, lingua, stato) VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (guild_id, user_id) DO UPDATE
            SET paese = EXCLUDED.paese, stato = EXCLUDED.stato, creato_il = now(),
                lingua = COALESCE(EXCLUDED.lingua, verify_paese.lingua)
            """,
            guild_id, user_id, paese, lingua[:16] if lingua else None, stato,
        )

    async def leggi(self, guild_id: int, user_id: int):
        return await self._pool.fetchrow(
            "SELECT paese, lingua, stato, creato_il FROM verify_paese WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id,
        )

    async def conta_da_fuori(self, guild_id: int, paesi: frozenset[str], minuti: int, escludi_utente: int) -> int:
        """Verifiche degli ultimi `minuti` da un paese che non è tra i `paesi` del server."""
        return await self._pool.fetchval(
            """
            SELECT count(*) FROM verify_paese
            WHERE guild_id = $1 AND user_id <> $2 AND paese IS NOT NULL
              AND NOT (paese = ANY($3::text[]))
              AND creato_il > now() - make_interval(mins => $4)
            """,
            guild_id, escludi_utente, sorted(paesi), minuti,
        )

    async def decidi(self, guild_id: int, user_id: int, stato: str) -> bool:
        """Approva o rifiuta chi è in attesa. False se non lo era più (già deciso)."""
        risultato = await self._pool.execute(
            "UPDATE verify_paese SET stato = $3 WHERE guild_id = $1 AND user_id = $2 AND stato = 'attesa'",
            guild_id, user_id, stato,
        )
        return risultato.endswith(" 1")


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


verify_paese_repo = VerifyPaeseRepository(pool_provider=_get_pool)
