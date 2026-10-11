"""
core/repositories/log_ignora_repo.py
====================================
Cosa il log dei messaggi ignora (canali, utenti, prefissi) per ogni server.
Funzioni coperte: SPEC §8.16 (NF-02)
"""

from __future__ import annotations

import asyncpg

from core.message_log_logic import GENERI_IGNORA, Ignorati


class LogIgnoraRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

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
                await conn.execute(
                    "INSERT INTO log_ignora (guild_id, genere, valore) VALUES ($1,$2,$3)",
                    guild_id, genere, valore,
                )
                return True

    async def rimuovi(self, guild_id: int, genere: str, valore: str) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM log_ignora WHERE guild_id=$1 AND genere=$2 AND valore=$3",
            guild_id, genere, valore,
        )
        return esito.endswith(" 1")

    async def carica(self, guild_id: int) -> Ignorati:
        righe = await self._pool.fetch(
            "SELECT genere, valore FROM log_ignora WHERE guild_id=$1 ORDER BY genere, valore",
            guild_id,
        )
        return Ignorati(
            canali=frozenset(int(r["valore"]) for r in righe if r["genere"] == "canale"),
            utenti=frozenset(int(r["valore"]) for r in righe if r["genere"] == "utente"),
            prefissi=tuple(r["valore"] for r in righe if r["genere"] == "prefisso"),
        )


def _get_pool():
    from core.database import db
    return db.pool


log_ignora_repo = LogIgnoraRepository(pool_provider=_get_pool)
