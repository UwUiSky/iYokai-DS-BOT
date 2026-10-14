"""
core/repositories/web_panel_session_repo.py
===========================================
Sessioni del pannello web (tabella `web_panel_sessions`, migrazione 0150).
Si salva solo l'impronta del token del cookie. Le righe scadute le toglie
il lavoro giornaliero (`core/data_registry.py`, scadenza su `expires_at`).
Funzioni coperte: SPEC §24.1 (NF-20, issue #91)
"""

from __future__ import annotations

from datetime import datetime

import asyncpg


class WebPanelSessionRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def crea(self, token_hash: str, user_id: int, expires_at: datetime) -> None:
        await self._pool.execute(
            "INSERT INTO web_panel_sessions (token_hash, user_id, expires_at) VALUES ($1, $2, $3)",
            token_hash, user_id, expires_at,
        )

    async def utente_della_sessione(self, token_hash: str) -> int | None:
        """L'utente della sessione, solo se non è scaduta."""
        return await self._pool.fetchval(
            "SELECT user_id FROM web_panel_sessions WHERE token_hash = $1 AND expires_at > now()",
            token_hash,
        )

    async def elimina(self, token_hash: str) -> None:
        await self._pool.execute("DELETE FROM web_panel_sessions WHERE token_hash = $1", token_hash)


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


web_panel_session_repo = WebPanelSessionRepository(pool_provider=_get_pool)
