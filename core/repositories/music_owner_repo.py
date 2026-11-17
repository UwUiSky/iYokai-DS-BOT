"""
core/repositories/music_owner_repo.py
=====================================
Tabelle music_sources_override (fonti accese o spente dall'owner) e music_global_banned_words
(parole vietate in tutto il bot): impostazioni globali del bot, non di un server.
Funzioni coperte: SPEC §9 (catalogo MUS-011, MUS-063)
"""

from __future__ import annotations

import asyncpg

from core.music_owner_logic import MAX_PAROLE_GLOBALI


class MusicOwnerRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def override_fonti(self) -> dict[str, bool]:
        righe = await self._pool.fetch("SELECT source, enabled FROM music_sources_override")
        return {r["source"]: r["enabled"] for r in righe}

    async def imposta_fonte(self, fonte: str, acceso: bool, owner_id: int) -> None:
        await self._pool.execute(
            """
            INSERT INTO music_sources_override (source, enabled, changed_by) VALUES ($1, $2, $3)
            ON CONFLICT (source) DO UPDATE SET enabled = $2, changed_by = $3, changed_at = now()
            """,
            fonte, acceso, owner_id,
        )

    async def togli_override(self, fonte: str) -> bool:
        esito = await self._pool.execute("DELETE FROM music_sources_override WHERE source = $1", fonte)
        return esito.endswith(" 1")

    async def parole(self) -> list[str]:
        righe = await self._pool.fetch("SELECT word FROM music_global_banned_words ORDER BY word")
        return [r["word"] for r in righe]

    async def aggiungi_parola(self, parola: str, owner_id: int) -> str:
        """«ok», «gia» o «pieno» (al massimo MAX_PAROLE_GLOBALI)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(7170003)")
                if await conn.fetchval("SELECT 1 FROM music_global_banned_words WHERE word = $1", parola):
                    return "gia"
                if await conn.fetchval("SELECT count(*) FROM music_global_banned_words") >= MAX_PAROLE_GLOBALI:
                    return "pieno"
                await conn.execute(
                    "INSERT INTO music_global_banned_words (word, added_by) VALUES ($1, $2)", parola, owner_id
                )
                return "ok"

    async def togli_parola(self, parola: str) -> bool:
        esito = await self._pool.execute("DELETE FROM music_global_banned_words WHERE word = $1", parola)
        return esito.endswith(" 1")


def _get_pool():
    from core.database import db
    return db.pool


music_owner_repo = MusicOwnerRepository(pool_provider=_get_pool)
