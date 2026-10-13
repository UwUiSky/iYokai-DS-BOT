"""
core/repositories/counting_game_repo.py
=======================================
Gioco del conteggio: un canale per server dove si conta a turno 1, 2, 3...
Ogni messaggio è giudicato sotto il blocco della riga del server, così due
numeri arrivati insieme non passano entrambi.
Funzioni coperte: SPEC §23.16 (NF-40)
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import asyncpg

from core.bounded_cache import BoundedCache
from core.coin_games_logic import valuta_conteggio

# Quanto resta in memoria il canale del conteggio: lo chiede ogni messaggio.
SECONDI_DI_CACHE = 60


@dataclass(frozen=True)
class StatoConteggio:
    guild_id: int
    channel_id: int
    current: int
    last_user_id: int | None
    best: int


@dataclass(frozen=True)
class EsitoConteggio:
    corretto: bool
    numero: int  # il numero accettato, o l'ultimo giusto se hai sbagliato
    record: int


class CountingGameRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider
        self._cache: BoundedCache[int, tuple[float, int | None]] = BoundedCache(max_size=5_000)

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def set_channel(self, guild_id: int, channel_id: int) -> None:
        """Sceglie (o cambia) il canale. Il conteggio riparte da zero, il record resta."""
        await self._pool.execute(
            """
            INSERT INTO counting_games (guild_id, channel_id) VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE
                SET channel_id = EXCLUDED.channel_id, current = 0, last_user_id = NULL
            """,
            guild_id,
            channel_id,
        )
        self._cache.delete(guild_id)

    async def disable(self, guild_id: int) -> bool:
        result = await self._pool.execute("DELETE FROM counting_games WHERE guild_id = $1", guild_id)
        self._cache.delete(guild_id)
        return result.endswith(" 1")

    async def get(self, guild_id: int) -> StatoConteggio | None:
        row = await self._pool.fetchrow("SELECT * FROM counting_games WHERE guild_id = $1", guild_id)
        return StatoConteggio(**dict(row)) if row is not None else None

    async def channel_id(self, guild_id: int) -> int | None:
        """Il canale del conteggio, con una risposta tenuta in memoria per un minuto."""
        voce = self._cache.get(guild_id)
        if voce is not None and time.monotonic() - voce[0] < SECONDI_DI_CACHE:
            return voce[1]
        canale = await self._pool.fetchval(
            "SELECT channel_id FROM counting_games WHERE guild_id = $1", guild_id
        )
        self._cache.set(guild_id, (time.monotonic(), canale))
        return canale

    async def register(
        self, guild_id: int, channel_id: int, user_id: int, numero: int
    ) -> EsitoConteggio | None:
        """
        Giudica un numero scritto nel canale. Giusto (il successivo, da una
        persona diversa dall'ultima): il conteggio avanza. Sbagliato: riparte
        da zero. None se quel server non conta in quel canale.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                riga = await conn.fetchrow(
                    "SELECT current, last_user_id, best FROM counting_games "
                    "WHERE guild_id = $1 AND channel_id = $2 FOR UPDATE",
                    guild_id,
                    channel_id,
                )
                if riga is None:
                    return None
                if valuta_conteggio(riga["current"], riga["last_user_id"], user_id, numero):
                    record = max(riga["best"], numero)
                    await conn.execute(
                        "UPDATE counting_games SET current = $2, last_user_id = $3, best = $4 "
                        "WHERE guild_id = $1",
                        guild_id, numero, user_id, record,
                    )
                    return EsitoConteggio(True, numero, record)
                await conn.execute(
                    "UPDATE counting_games SET current = 0, last_user_id = NULL WHERE guild_id = $1",
                    guild_id,
                )
                return EsitoConteggio(False, riga["current"], riga["best"])


def _get_pool():
    from core.database import db

    return db.pool


counting_game_repo = CountingGameRepository(pool_provider=_get_pool)
