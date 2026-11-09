"""
core/repositories/gif_privacy_repo.py
=====================================
Privacy delle GIF di azione: «blocca tutti» e l'elenco dei bloccati (massimo 25 per utente).
Tabelle: core/migrations/0570_gif_privacy.sql.
Funzioni coperte: SPEC §16 (FUN-137; #131)
"""

from __future__ import annotations

import asyncpg

MAX_BLOCCHI = 25


class GifPrivacyRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def blocca_tutti(self, user_id: int) -> bool:
        return bool(await self._pool.fetchval("SELECT blocca_tutti FROM gif_privacy WHERE user_id = $1", user_id))

    async def imposta_blocca_tutti(self, user_id: int, valore: bool) -> None:
        await self._pool.execute(
            "INSERT INTO gif_privacy (user_id, blocca_tutti) VALUES ($1, $2) "
            "ON CONFLICT (user_id) DO UPDATE SET blocca_tutti = EXCLUDED.blocca_tutti",
            user_id, valore,
        )

    async def e_bloccato(self, bersaglio_id: int, autore_id: int) -> bool:
        """Vero se `bersaglio_id` non vuole azioni da `autore_id` (blocca tutti oppure blocco personale)."""
        return bool(await self._pool.fetchval(
            "SELECT EXISTS (SELECT 1 FROM gif_privacy WHERE user_id = $1 AND blocca_tutti) "
            "OR EXISTS (SELECT 1 FROM gif_blocchi WHERE user_id = $1 AND bloccato_id = $2)",
            bersaglio_id, autore_id,
        ))

    async def blocca(self, user_id: int, bloccato_id: int) -> str:
        """'ok', 'gia' (già in elenco) o 'tetto' (25 blocchi). Il tetto è nella stessa istruzione."""
        inserito = await self._pool.fetchval(
            "INSERT INTO gif_blocchi (user_id, bloccato_id) "
            "SELECT $1, $2 WHERE (SELECT count(*) FROM gif_blocchi WHERE user_id = $1) < $3 "
            "ON CONFLICT DO NOTHING RETURNING 1",
            user_id, bloccato_id, MAX_BLOCCHI,
        )
        if inserito:
            return "ok"
        esiste = await self._pool.fetchval(
            "SELECT 1 FROM gif_blocchi WHERE user_id = $1 AND bloccato_id = $2", user_id, bloccato_id
        )
        return "gia" if esiste else "tetto"

    async def sblocca(self, user_id: int, bloccato_id: int) -> bool:
        riga = await self._pool.fetchval(
            "DELETE FROM gif_blocchi WHERE user_id = $1 AND bloccato_id = $2 RETURNING 1", user_id, bloccato_id
        )
        return bool(riga)

    async def elenco(self, user_id: int) -> list[int]:
        righe = await self._pool.fetch(
            "SELECT bloccato_id FROM gif_blocchi WHERE user_id = $1 ORDER BY creato_il, bloccato_id LIMIT $2",
            user_id, MAX_BLOCCHI,
        )
        return [r["bloccato_id"] for r in righe]


def _get_pool():
    from core.database import db

    return db.pool


gif_privacy_repo = GifPrivacyRepository(pool_provider=_get_pool)
