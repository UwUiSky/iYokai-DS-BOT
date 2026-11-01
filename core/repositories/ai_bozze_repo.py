"""
core/repositories/ai_bozze_repo.py
==================================
Bozze di codice dell'AI per le richieste di comandi approvate: quali mancano, salvataggio, conteggio del giorno.
Funzioni coperte: SPEC §25.100 (AI-R-107)
"""

from __future__ import annotations

import asyncpg

from core.ai_bozza_logic import Richiesta


class AiBozzeRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def da_preparare(self, limite: int = 3) -> list[Richiesta]:
        """Richieste approvate dall'owner che non hanno ancora una bozza (le più vecchie prima)."""
        righe = await self._pool.fetch(
            "SELECT r.id, r.command_name, r.description, r.example FROM custom_command_requests r "
            "LEFT JOIN ai_bozze b ON b.request_id = r.id WHERE r.status = 'approved' AND b.request_id IS NULL "
            "ORDER BY r.id LIMIT $1", limite,
        )
        return [Richiesta(r["id"], r["command_name"], r["description"], r["example"]) for r in righe]

    async def fatte_oggi(self) -> int:
        return int(await self._pool.fetchval("SELECT count(*) FROM ai_bozze WHERE creato_il > now() - interval '1 day'"))

    async def salva(self, request_id: int, stato: str, bozza: str = "", pr_url: str | None = None, errore: str | None = None) -> None:
        await self._pool.execute(
            "INSERT INTO ai_bozze (request_id, stato, bozza, pr_url, errore) VALUES ($1, $2, $3, $4, $5) "
            "ON CONFLICT (request_id) DO UPDATE SET stato = EXCLUDED.stato, bozza = EXCLUDED.bozza, "
            "pr_url = EXCLUDED.pr_url, errore = EXCLUDED.errore",
            request_id, stato, bozza, pr_url, errore,
        )


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


ai_bozze_repo = AiBozzeRepository(pool_provider=_get_pool)
