"""
core/repositories/web_panel_pubblico_repo.py
============================================
Cosa un server rende pubblico dal pannello web (tabella `web_panel_pubblico`, migrazione 0751): statistiche,
indirizzo breve della classifica, impronta della chiave API.
Funzioni coperte: SPEC §24.8 (STA-012, LIV-062, STA-061; issue #130, #124)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class Pubblico:
    stat_pubbliche: bool = False
    stat_membri: bool = False
    classifica_slug: str | None = None
    api_prefisso: str | None = None
    api_creata_il: datetime | None = None


class WebPanelPubblicoRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def leggi(self, guild_id: int) -> Pubblico:
        r = await self._pool.fetchrow(
            "SELECT stat_pubbliche, stat_membri, classifica_slug, api_prefisso, api_creata_il "
            "FROM web_panel_pubblico WHERE guild_id = $1",
            guild_id,
        )
        return Pubblico() if r is None else Pubblico(**dict(r))

    async def imposta_statistiche(self, guild_id: int, pubbliche: bool, membri: bool) -> None:
        await self._pool.execute(
            "INSERT INTO web_panel_pubblico (guild_id, stat_pubbliche, stat_membri) VALUES ($1, $2, $3) "
            "ON CONFLICT (guild_id) DO UPDATE SET stat_pubbliche = $2, stat_membri = $3, aggiornato_il = now()",
            guild_id, pubbliche, membri,
        )

    async def imposta_slug(self, guild_id: int, slug: str | None) -> bool:
        """False se l'indirizzo è già di un altro server (indice unico: nessuna corsa possibile)."""
        try:
            await self._pool.execute(
                "INSERT INTO web_panel_pubblico (guild_id, classifica_slug) VALUES ($1, $2) "
                "ON CONFLICT (guild_id) DO UPDATE SET classifica_slug = $2, aggiornato_il = now()",
                guild_id, slug,
            )
        except asyncpg.UniqueViolationError:
            return False
        return True

    async def guild_da_slug(self, slug: str) -> int | None:
        return await self._pool.fetchval("SELECT guild_id FROM web_panel_pubblico WHERE classifica_slug = $1", slug)

    async def imposta_chiave(self, guild_id: int, impronta: str | None, prefisso: str | None, creata_da: int | None) -> None:
        await self._pool.execute(
            "INSERT INTO web_panel_pubblico (guild_id, api_impronta, api_prefisso, api_creata_il, api_creata_da) "
            "VALUES ($1, $2, $3, CASE WHEN $2::text IS NULL THEN NULL ELSE now() END, $4) "
            "ON CONFLICT (guild_id) DO UPDATE SET api_impronta = $2, api_prefisso = $3, "
            "api_creata_il = CASE WHEN $2::text IS NULL THEN NULL ELSE now() END, api_creata_da = $4, aggiornato_il = now()",
            guild_id, impronta, prefisso, creata_da,
        )

    async def guild_da_impronta(self, impronta: str) -> int | None:
        return await self._pool.fetchval("SELECT guild_id FROM web_panel_pubblico WHERE api_impronta = $1", impronta)


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


web_panel_pubblico_repo = WebPanelPubblicoRepository(pool_provider=_get_pool)
