"""
core/repositories/suggestions_config_repo.py
============================================
Opzioni dei suggerimenti per server, con copia in memoria (si riempie dopo una lettura riuscita, si svuota a
ogni scrittura). Tabella: core/migrations/0545_suggerimenti_opzioni.sql.
Funzioni coperte: catalogo #128 UTL-139, 140, 141, 142 (D69, B7)
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from core.bounded_cache import BoundedCache

_CAMPI = ("anonimi", "soglia", "colore", "solo_canale_id", "esito")


@dataclass(frozen=True)
class OpzioniSuggerimenti:
    anonimi: bool = False
    soglia: int = 0
    colore: str | None = None
    solo_canale_id: int | None = None
    esito: str = "modifica"


class SuggestionsConfigRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider
        self._cache: BoundedCache[int, OpzioniSuggerimenti] = BoundedCache(5000)

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def get(self, guild_id: int) -> OpzioniSuggerimenti:
        visto = self._cache.get(guild_id)
        if visto is not None:
            return visto
        r = await self._pool.fetchrow(
            "SELECT anonimi, soglia, colore, solo_canale_id, esito FROM suggestions_config WHERE guild_id = $1", guild_id
        )
        valore = OpzioniSuggerimenti(**{k: r[k] for k in _CAMPI}) if r else OpzioniSuggerimenti()
        self._cache.set(guild_id, valore)
        return valore

    async def imposta(self, guild_id: int, **campi) -> None:
        """Cambia solo i campi passati (anche `colore=None` o `solo_canale_id=None` per toglierli)."""
        if not campi or any(k not in _CAMPI for k in campi):
            raise ValueError("campi non validi")
        nomi = list(campi)
        colonne = ", ".join(nomi)
        segnaposto = ", ".join(f"${i + 2}" for i in range(len(nomi)))
        aggiorna = ", ".join(f"{n} = EXCLUDED.{n}" for n in nomi)
        await self._pool.execute(
            f"INSERT INTO suggestions_config (guild_id, {colonne}) VALUES ($1, {segnaposto}) "
            f"ON CONFLICT (guild_id) DO UPDATE SET {aggiorna}",
            guild_id, *campi.values(),
        )
        self._cache.delete(guild_id)

    async def togli_canale(self, guild_id: int, canale_id: int) -> None:
        """Il canale unico è stato cancellato: i suggerimenti tornano liberi."""
        await self._pool.execute(
            "UPDATE suggestions_config SET solo_canale_id = NULL WHERE guild_id = $1 AND solo_canale_id = $2",
            guild_id, canale_id,
        )
        self._cache.delete(guild_id)


def _get_pool():
    from core.database import db

    return db.pool


suggestions_config_repo = SuggestionsConfigRepository(pool_provider=_get_pool)
