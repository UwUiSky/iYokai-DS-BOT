"""
core/repositories/messaggi_auto_repo.py
=======================================
Automatismi sui messaggi per server (citazioni, correzione link, pubblicazione annunci) con una copia in
memoria: si riempie solo dopo una lettura riuscita e si svuota a ogni scrittura.
Tabella: core/migrations/0541_messaggi_auto.sql.
Funzioni coperte: catalogo #128 UTL-071, 072, 112 (D69, B3)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import asyncpg

from core.bounded_cache import BoundedCache
from core.messaggi_auto_logic import MAX_CANALI_PUBBLICA


@dataclass(frozen=True)
class MessaggiAuto:
    citazioni: bool = False
    correzioni: tuple[str, ...] = ()
    pubblica_canali: tuple[int, ...] = ()


class MessaggiAutoRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider
        self._cache: BoundedCache[int, MessaggiAuto] = BoundedCache(5000)

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def get(self, guild_id: int) -> MessaggiAuto:
        """Se la lettura fallisce l'errore sale: una copia vuota non deve passare per quella vera."""
        visto = self._cache.get(guild_id)
        if visto is not None:
            return visto
        riga = await self._pool.fetchrow(
            "SELECT citazioni, correzioni, pubblica_canali FROM messaggi_auto WHERE guild_id = $1", guild_id
        )
        valore = MessaggiAuto(riga["citazioni"], tuple(riga["correzioni"]), tuple(riga["pubblica_canali"])) if riga else MessaggiAuto()
        self._cache.set(guild_id, valore)
        return valore

    async def _scrivi(self, sql: str, *args) -> bool:
        riga = await self._pool.fetchrow(sql, *args)
        self._cache.delete(args[0])
        return riga is not None

    async def imposta_citazioni(self, guild_id: int, attivo: bool) -> None:
        await self._scrivi(
            "INSERT INTO messaggi_auto (guild_id, citazioni) VALUES ($1, $2) "
            "ON CONFLICT (guild_id) DO UPDATE SET citazioni = $2 RETURNING guild_id",
            guild_id, attivo,
        )

    async def alterna_correzione(self, guild_id: int, voce: str) -> bool:
        """Accende o spegne una correzione. Ritorna True se ora è accesa."""
        riga = await self._pool.fetchrow(
            """
            INSERT INTO messaggi_auto (guild_id, correzioni) VALUES ($1, ARRAY[$2::text])
            ON CONFLICT (guild_id) DO UPDATE SET correzioni = CASE
                WHEN $2::text = ANY(messaggi_auto.correzioni) THEN array_remove(messaggi_auto.correzioni, $2::text)
                ELSE array_append(messaggi_auto.correzioni, $2::text) END
            RETURNING $2::text = ANY(correzioni) AS acceso
            """,
            guild_id, voce,
        )
        self._cache.delete(guild_id)
        return bool(riga["acceso"])

    async def spegni_correzioni(self, guild_id: int) -> None:
        await self._scrivi("UPDATE messaggi_auto SET correzioni = '{}' WHERE guild_id = $1 RETURNING guild_id", guild_id)

    async def aggiungi_canale_pubblica(self, guild_id: int, canale_id: int) -> bool:
        """False se ce ne sono già 25 (e questo non c'è)."""
        riga = await self._pool.fetchrow(
            """
            INSERT INTO messaggi_auto (guild_id, pubblica_canali) VALUES ($1, ARRAY[$2::bigint])
            ON CONFLICT (guild_id) DO UPDATE SET pubblica_canali = CASE
                WHEN $2::bigint = ANY(messaggi_auto.pubblica_canali) THEN messaggi_auto.pubblica_canali
                ELSE array_append(messaggi_auto.pubblica_canali, $2::bigint) END
            WHERE $2::bigint = ANY(messaggi_auto.pubblica_canali) OR cardinality(messaggi_auto.pubblica_canali) < $3
            RETURNING guild_id
            """,
            guild_id, canale_id, MAX_CANALI_PUBBLICA,
        )
        self._cache.delete(guild_id)
        return riga is not None

    async def togli_canale_pubblica(self, guild_id: int, canale_id: int) -> bool:
        """True se il canale c'era."""
        riga = await self._pool.fetchrow(
            "UPDATE messaggi_auto SET pubblica_canali = array_remove(pubblica_canali, $2::bigint) "
            "WHERE guild_id = $1 AND $2::bigint = ANY(pubblica_canali) RETURNING guild_id",
            guild_id, canale_id,
        )
        self._cache.delete(guild_id)
        return riga is not None


def _get_pool():
    from core.database import db

    return db.pool


messaggi_auto_repo = MessaggiAutoRepository(pool_provider=_get_pool)
