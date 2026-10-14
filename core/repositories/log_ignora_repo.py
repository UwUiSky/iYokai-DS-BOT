"""
core/repositories/log_ignora_repo.py
====================================
Cosa il log dei messaggi ignora (canali, utenti, ruoli, prefissi, espressioni) per ogni server.
Funzioni coperte: SPEC §8.16 (NF-02)
"""

from __future__ import annotations

import time

import asyncpg

from core.message_log_logic import GENERI_IGNORA, REGEX_MAX_PER_SERVER, Ignorati


# Ogni cancellazione o modifica di messaggio chiede l'elenco: si tiene in memoria
# per poco e si butta a ogni scrittura (un solo processo del bot).
CACHE_SECONDI = 30


class LogIgnoraRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider
        self._cache: dict[int, tuple[float, Ignorati]] = {}
        self._orologio = time.monotonic

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def aggiungi(self, guild_id: int, genere: str, valore: str, massimo: int) -> bool:
        """False se il server ha già `massimo` voci (la voce già presente conta come fatta)."""
        assert genere in GENERI_IGNORA
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Serializza gli inserimenti dello stesso server: il tetto vale anche in parallelo.
                await conn.execute("SELECT pg_advisory_xact_lock($1)", guild_id)
                esiste = await conn.fetchval(
                    "SELECT 1 FROM log_ignora WHERE guild_id=$1 AND genere=$2 AND valore=$3",
                    guild_id, genere, valore,
                )
                if esiste:
                    return True
                totale = await conn.fetchval(
                    "SELECT count(*) FROM log_ignora WHERE guild_id=$1", guild_id
                )
                if totale >= massimo:
                    return False
                if genere == "regex":
                    # Ogni espressione gira su ogni messaggio: poche, e non tra le 200 voci generiche.
                    espressioni = await conn.fetchval(
                        "SELECT count(*) FROM log_ignora WHERE guild_id=$1 AND genere='regex'", guild_id
                    )
                    if espressioni >= REGEX_MAX_PER_SERVER:
                        return False
                await conn.execute(
                    "INSERT INTO log_ignora (guild_id, genere, valore) VALUES ($1,$2,$3)",
                    guild_id, genere, valore,
                )
        self._cache.pop(guild_id, None)
        return True

    async def rimuovi(self, guild_id: int, genere: str, valore: str) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM log_ignora WHERE guild_id=$1 AND genere=$2 AND valore=$3",
            guild_id, genere, valore,
        )
        self._cache.pop(guild_id, None)
        return esito.endswith(" 1")

    async def carica(self, guild_id: int) -> Ignorati:
        voce = self._cache.get(guild_id)
        if voce is not None and voce[0] > self._orologio():
            return voce[1]
        ignorati = await self._leggi(guild_id)
        if len(self._cache) > 5000:
            self._cache.clear()
        self._cache[guild_id] = (self._orologio() + CACHE_SECONDI, ignorati)
        return ignorati

    async def _leggi(self, guild_id: int) -> Ignorati:
        righe = await self._pool.fetch(
            "SELECT genere, valore FROM log_ignora WHERE guild_id=$1 ORDER BY genere, valore",
            guild_id,
        )
        return Ignorati(
            canali=frozenset(int(r["valore"]) for r in righe if r["genere"] == "canale"),
            utenti=frozenset(int(r["valore"]) for r in righe if r["genere"] == "utente"),
            prefissi=tuple(r["valore"] for r in righe if r["genere"] == "prefisso"),
            ruoli=frozenset(int(r["valore"]) for r in righe if r["genere"] == "ruolo"),
            regex=tuple(r["valore"] for r in righe if r["genere"] == "regex"),
        )


def _get_pool():
    from core.database import db
    return db.pool


log_ignora_repo = LogIgnoraRepository(pool_provider=_get_pool)
