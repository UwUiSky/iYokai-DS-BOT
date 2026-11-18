"""
core/repositories/log_personalizza_repo.py
==========================================
Le rotte (un canale per evento, LOG-016) e i formati (un testo per evento, LOG-026) dei log di ogni server.
Ogni log le chiede prima di scrivere: si tengono in memoria e si buttano a ogni modifica (un solo processo).
Funzioni coperte: SPEC §8.20 (LOG-016, LOG-026)
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from core.bounded_cache import BoundedCache
from core.log_eventi_logic import INTERRUTTORI
from core.log_personalizza_logic import FORMATI_DATA, FORMATO_MAX


@dataclass(frozen=True)
class Personalizzazioni:
    rotte: dict[str, int]
    formati: dict[str, tuple[str, str]]  # interruttore -> (testo, formato_data)


class LogPersonalizzaRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider
        self._cache: BoundedCache[int, Personalizzazioni] = BoundedCache(5000)
        self._versione = 0  # una lettura partita prima di una modifica non rimette in cache il vecchio

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def carica(self, guild_id: int) -> Personalizzazioni:
        noto = self._cache.get(guild_id)
        if noto is not None:
            return noto
        versione = self._versione
        rotte = await self._pool.fetch("SELECT interruttore, channel_id FROM log_rotte WHERE guild_id=$1", guild_id)
        formati = await self._pool.fetch(
            "SELECT interruttore, testo, formato_data FROM log_formati WHERE guild_id=$1", guild_id
        )
        letto = Personalizzazioni(
            rotte={r["interruttore"]: r["channel_id"] for r in rotte if r["interruttore"] in INTERRUTTORI},
            formati={
                r["interruttore"]: (r["testo"], r["formato_data"]) for r in formati if r["interruttore"] in INTERRUTTORI
            },
        )
        if versione == self._versione:
            self._cache.set(guild_id, letto)
        return letto

    def _cambiata(self, guild_id: int) -> None:
        self._versione += 1
        self._cache.delete(guild_id)

    async def imposta_rotta(self, guild_id: int, interruttore: str, channel_id: int) -> None:
        if interruttore not in INTERRUTTORI:
            raise ValueError(f"interruttore sconosciuto: {interruttore}")
        await self._pool.execute(
            "INSERT INTO log_rotte (guild_id, interruttore, channel_id) VALUES ($1, $2, $3) "
            "ON CONFLICT (guild_id, interruttore) DO UPDATE SET channel_id = EXCLUDED.channel_id",
            guild_id, interruttore, channel_id,
        )
        self._cambiata(guild_id)

    async def togli_rotta(self, guild_id: int, interruttore: str) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM log_rotte WHERE guild_id=$1 AND interruttore=$2", guild_id, interruttore
        )
        self._cambiata(guild_id)
        return esito.endswith(" 1")

    async def imposta_formato(self, guild_id: int, interruttore: str, testo: str, formato_data: str) -> None:
        if interruttore not in INTERRUTTORI:
            raise ValueError(f"interruttore sconosciuto: {interruttore}")
        if formato_data not in FORMATI_DATA:
            raise ValueError(f"formato di data sconosciuto: {formato_data}")
        if not 1 <= len(testo) <= FORMATO_MAX:
            raise ValueError("testo del formato troppo corto o troppo lungo")
        await self._pool.execute(
            "INSERT INTO log_formati (guild_id, interruttore, testo, formato_data) VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (guild_id, interruttore) DO UPDATE SET testo = EXCLUDED.testo, "
            "formato_data = EXCLUDED.formato_data",
            guild_id, interruttore, testo, formato_data,
        )
        self._cambiata(guild_id)

    async def togli_formato(self, guild_id: int, interruttore: str) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM log_formati WHERE guild_id=$1 AND interruttore=$2", guild_id, interruttore
        )
        self._cambiata(guild_id)
        return esito.endswith(" 1")


def _get_pool():
    from core.database import db
    return db.pool


log_personalizza_repo = LogPersonalizzaRepository(pool_provider=_get_pool)
