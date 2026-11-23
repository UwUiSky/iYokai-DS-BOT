"""
core/repositories/gif_preferenze_repo.py
========================================
Preferenze delle GIF di ogni persona: una riga sola, scritta solo se ha scelto qualcosa; si cancella con «azzera».
Tabella: core/migrations/0920_gif_preferenze.sql.
Funzioni coperte: SPEC §16 (FUN-138; D124)
"""

from __future__ import annotations

import asyncpg

from core.gif_preferenze_logic import GENERI, MAX_PREFERITI, TIPI, Preferenze, preferenze_da_riga


class GifPreferenzeRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def leggi(self, user_id: int) -> Preferenze:
        riga = await self._pool.fetchrow(
            "SELECT genere, tipo, personaggi FROM gif_preferenze WHERE user_id = $1", user_id
        )
        return preferenze_da_riga(riga)

    async def salva(self, user_id: int, p: Preferenze) -> None:
        if p.genere not in GENERI or p.tipo not in TIPI or len(p.personaggi) > MAX_PREFERITI:
            raise ValueError("Preferenze delle GIF non valide.")
        if p.vuote:
            await self.azzera(user_id)
            return
        await self._pool.execute(
            "INSERT INTO gif_preferenze (user_id, genere, tipo, personaggi) VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (user_id) DO UPDATE SET genere = EXCLUDED.genere, tipo = EXCLUDED.tipo, "
            "personaggi = EXCLUDED.personaggi, aggiornato_il = now()",
            user_id, p.genere, p.tipo, list(p.personaggi),
        )

    async def azzera(self, user_id: int) -> bool:
        return bool(await self._pool.fetchval("DELETE FROM gif_preferenze WHERE user_id = $1 RETURNING 1", user_id))


def _get_pool():
    from core.database import db

    return db.pool


gif_preferenze_repo = GifPreferenzeRepository(pool_provider=_get_pool)
