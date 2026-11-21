"""
core/repositories/web_panel_avvisi_repo.py
==========================================
Preferenze e avvisi del pannello web (tabelle `web_panel_avvisi_pref` e `web_panel_avvisi`, migrazione 0752).
Funzioni coperte: SPEC §24.8 (CFG-006, issue #122)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg

MAX_AVVISI_PER_PERSONA = 50
MAX_DESTINATARI = 200


@dataclass(frozen=True)
class Avviso:
    id: int
    categoria: str
    testo: str
    creato_il: datetime
    letto: bool


class WebPanelAvvisiRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def preferenze(self, guild_id: int, user_id: int) -> dict[str, str]:
        righe = await self._pool.fetch(
            "SELECT categoria, canale FROM web_panel_avvisi_pref WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
        )
        return {r["categoria"]: r["canale"] for r in righe}

    async def imposta_preferenza(self, guild_id: int, user_id: int, categoria: str, canale: str | None) -> None:
        """`canale` None = spento (si toglie la riga)."""
        if canale is None:
            await self._pool.execute(
                "DELETE FROM web_panel_avvisi_pref WHERE guild_id = $1 AND user_id = $2 AND categoria = $3",
                guild_id, user_id, categoria,
            )
            return
        await self._pool.execute(
            "INSERT INTO web_panel_avvisi_pref (guild_id, user_id, categoria, canale) VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (guild_id, user_id, categoria) DO UPDATE SET canale = EXCLUDED.canale",
            guild_id, user_id, categoria, canale,
        )

    async def destinatari(self, guild_id: int, categoria: str) -> list[tuple[int, str]]:
        righe = await self._pool.fetch(
            "SELECT user_id, canale FROM web_panel_avvisi_pref WHERE guild_id = $1 AND categoria = $2 "
            "ORDER BY user_id LIMIT $3",
            guild_id, categoria, MAX_DESTINATARI,
        )
        return [(r["user_id"], r["canale"]) for r in righe]

    async def aggiungi(self, guild_id: int, user_id: int, categoria: str, testo: str) -> None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO web_panel_avvisi (guild_id, user_id, categoria, testo) VALUES ($1, $2, $3, $4)",
                    guild_id, user_id, categoria, testo,
                )
                await conn.execute(
                    "DELETE FROM web_panel_avvisi WHERE guild_id = $1 AND user_id = $2 AND id NOT IN "
                    "(SELECT id FROM web_panel_avvisi WHERE guild_id = $1 AND user_id = $2 ORDER BY id DESC LIMIT $3)",
                    guild_id, user_id, MAX_AVVISI_PER_PERSONA,
                )

    async def elenco(self, guild_id: int, user_id: int) -> list[Avviso]:
        righe = await self._pool.fetch(
            "SELECT id, categoria, testo, creato_il, letto FROM web_panel_avvisi "
            "WHERE guild_id = $1 AND user_id = $2 ORDER BY id DESC LIMIT $3",
            guild_id, user_id, MAX_AVVISI_PER_PERSONA,
        )
        return [Avviso(**dict(r)) for r in righe]

    async def segna_letti(self, guild_id: int, user_id: int) -> None:
        await self._pool.execute(
            "UPDATE web_panel_avvisi SET letto = TRUE WHERE guild_id = $1 AND user_id = $2 AND NOT letto", guild_id, user_id
        )


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


web_panel_avvisi_repo = WebPanelAvvisiRepository(pool_provider=_get_pool)
