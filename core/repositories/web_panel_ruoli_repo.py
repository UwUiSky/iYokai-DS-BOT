"""
core/repositories/web_panel_ruoli_repo.py
=========================================
Ruoli del pannello web per server (tabella `web_panel_ruoli`, migrazione 0750): chi li ha legge o scrive nel
pannello senza essere admin di Discord.
Funzioni coperte: SPEC §24.8 (CFG-002, issue #122)
"""

from __future__ import annotations

import asyncpg


class WebPanelRuoliRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def leggi(self, guild_id: int) -> dict[str, frozenset[int]]:
        righe = await self._pool.fetch("SELECT role_id, livello FROM web_panel_ruoli WHERE guild_id = $1", guild_id)
        return {
            livello: frozenset(r["role_id"] for r in righe if r["livello"] == livello)
            for livello in ("lettura", "scrittura")
        }

    async def sostituisci(self, guild_id: int, livello: str, ruoli: list[int], impostato_da: int | None) -> None:
        """I ruoli di un livello diventano esattamente `ruoli` (un ruolo passa da un livello all'altro)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(750, $1)", guild_id % 2_000_000_000)
                await conn.execute("DELETE FROM web_panel_ruoli WHERE guild_id = $1 AND livello = $2", guild_id, livello)
                for ruolo in ruoli:
                    await conn.execute(
                        "INSERT INTO web_panel_ruoli (guild_id, role_id, livello, impostato_da) VALUES ($1, $2, $3, $4) "
                        "ON CONFLICT (guild_id, role_id) DO UPDATE SET livello = EXCLUDED.livello, "
                        "impostato_da = EXCLUDED.impostato_da, impostato_il = now()",
                        guild_id, ruolo, livello, impostato_da,
                    )


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


web_panel_ruoli_repo = WebPanelRuoliRepository(pool_provider=_get_pool)
