"""
core/repositories/cache_esterna_repo.py
=======================================
Cache comune (`cache_esterna`) delle risposte dei servizi esterni: PokéAPI, AniList, Scryfall, osu!, Fortnite.
Una riga per chiave; si legge solo se non è scaduta. Tabella: core/migrations/0575_cache_esterna.sql.
Funzioni coperte: SPEC §16 (B9 di #131: FUN-066..070, 073)
"""

from __future__ import annotations

import json

import asyncpg


class CacheEsternaRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def leggi(self, chiave: str) -> dict | None:
        testo = await self._pool.fetchval("SELECT risposta::text FROM cache_esterna WHERE chiave = $1 AND scade > now()", chiave)
        return json.loads(testo) if testo else None

    async def salva(self, chiave: str, risposta: dict, secondi: int) -> None:
        await self._pool.execute(
            "INSERT INTO cache_esterna (chiave, risposta, scade) VALUES ($1, $2::jsonb, now() + make_interval(secs => $3)) "
            "ON CONFLICT (chiave) DO UPDATE SET risposta = EXCLUDED.risposta, scade = EXCLUDED.scade",
            chiave, json.dumps(risposta), float(secondi),
        )


def _get_pool():
    from core.database import db

    return db.pool


cache_esterna_repo = CacheEsternaRepository(pool_provider=_get_pool)
