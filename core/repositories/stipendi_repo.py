"""
core/repositories/stipendi_repo.py
==================================
Stipendi e tasse per ruolo, monete per messaggio con tetto giornaliero e giro automatico. La riscossione
prende la pausa e muove le monete nella stessa transazione (due clic o il giro automatico e il comando insieme
pagano una volta sola); la tassa non porta mai sotto zero e va alla cassa del server.
Funzioni coperte: ECO-033, ECO-034, ECO-035, ECO-036, ECO-037, ECO-038
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

import asyncpg

from core.repositories.guild_chest_repo import REASON_STIPENDIO_TASSA, deposit_in
from core.repositories.leveling_repo import add_coins_in

MAX_STIPENDI = 10
MAX_CANALI = 25
PAUSA_STIPENDIO = 20 * 3600


class EsitoRiscossione(str, Enum):
    FATTO = "fatto"
    NESSUNO = "nessuno"
    PAUSA = "pausa"


@dataclass(frozen=True)
class Riscossione:
    esito: EsitoRiscossione
    contanti: int = 0
    banca: int = 0
    tassa: int = 0


class StipendiRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def imposta(self, guild_id: int, role_id: int, importo: int, in_banca: bool) -> bool:
        """Imposta lo stipendio di un ruolo (massimo 10 per server). False se il server è pieno."""
        if importo == 0 or abs(importo) > 100_000:
            raise ValueError("Importo non valido.")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1)", guild_id)
                esiste = await conn.fetchval(
                    "SELECT 1 FROM economia_stipendi WHERE guild_id = $1 AND role_id = $2", guild_id, role_id
                )
                if not esiste and await conn.fetchval("SELECT count(*) FROM economia_stipendi WHERE guild_id = $1", guild_id) >= MAX_STIPENDI:
                    return False
                await conn.execute(
                    "INSERT INTO economia_stipendi (guild_id, role_id, importo, in_banca) VALUES ($1, $2, $3, $4) "
                    "ON CONFLICT (guild_id, role_id) DO UPDATE SET importo = $3, in_banca = $4",
                    guild_id, role_id, importo, in_banca,
                )
                return True

    async def rimuovi(self, guild_id: int, role_id: int) -> bool:
        return (await self._pool.execute(
            "DELETE FROM economia_stipendi WHERE guild_id = $1 AND role_id = $2", guild_id, role_id
        )).endswith(" 1")

    async def elenco(self, guild_id: int) -> list[asyncpg.Record]:
        return await self._pool.fetch(
            "SELECT role_id, importo, in_banca FROM economia_stipendi WHERE guild_id = $1 ORDER BY role_id", guild_id
        )

    async def riscuoti(self, guild_id: int, user_id: int, role_ids: list[int], pausa_s: int = PAUSA_STIPENDIO) -> Riscossione:
        """Stipendi e tasse dei ruoli della persona, una volta ogni `pausa_s`."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                voci = await conn.fetch(
                    "SELECT importo, in_banca FROM economia_stipendi WHERE guild_id = $1 AND role_id = ANY($2::bigint[])",
                    guild_id, role_ids,
                )
                if not voci:
                    return Riscossione(EsitoRiscossione.NESSUNO)
                await conn.execute("INSERT INTO leveling_totals (guild_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", guild_id, user_id)
                await conn.fetchval(
                    "SELECT coins_total FROM leveling_totals WHERE guild_id = $1 AND user_id = $2 FOR UPDATE", guild_id, user_id
                )
                preso = await conn.fetchval(
                    "INSERT INTO economia_pause (guild_id, user_id, chiave, ultima_at) VALUES ($1, $2, 'stipendio', now()) "
                    "ON CONFLICT (guild_id, user_id, chiave) DO UPDATE SET ultima_at = now() "
                    "WHERE economia_pause.ultima_at <= now() - make_interval(secs => $3) RETURNING 1",
                    guild_id, user_id, float(pausa_s),
                )
                if preso is None:
                    return Riscossione(EsitoRiscossione.PAUSA)
                contanti = sum(v["importo"] for v in voci if v["importo"] > 0 and not v["in_banca"])
                banca = sum(v["importo"] for v in voci if v["importo"] > 0 and v["in_banca"])
                tassa_dovuta = -sum(v["importo"] for v in voci if v["importo"] < 0)
                if contanti:
                    await add_coins_in(conn, guild_id, user_id, contanti, classifica=False)
                if banca:
                    await conn.execute(
                        "UPDATE leveling_totals SET banca_total = banca_total + $3 WHERE guild_id = $1 AND user_id = $2",
                        guild_id, user_id, banca,
                    )
                tassa = 0
                if tassa_dovuta:
                    tassa = await conn.fetchval(
                        "WITH v AS (SELECT coins_total AS prima FROM leveling_totals WHERE guild_id = $1 AND user_id = $2), "
                        "u AS (UPDATE leveling_totals SET coins_total = coins_total - LEAST(coins_total, $3) "
                        "WHERE guild_id = $1 AND user_id = $2 RETURNING coins_total) "
                        "SELECT (SELECT prima FROM v) - (SELECT coins_total FROM u)",
                        guild_id, user_id, tassa_dovuta,
                    )
                    if tassa > 0:
                        await deposit_in(conn, guild_id, tassa, REASON_STIPENDIO_TASSA)
                return Riscossione(EsitoRiscossione.FATTO, contanti, banca, tassa)

    async def giro_automatico(self, guild_id: int, giorno: date) -> bool:
        """Prende il giro del giorno: vero una volta sola per server e giorno."""
        return await self._pool.fetchval(
            "INSERT INTO economia_stipendi_giro (guild_id, giorno) VALUES ($1, $2) ON CONFLICT DO NOTHING RETURNING TRUE",
            guild_id, giorno,
        ) is True

    # ---------------------------------------------------------------- ECO-033
    async def canali_monete(self, guild_id: int) -> set[int]:
        return {r["channel_id"] for r in await self._pool.fetch(
            "SELECT channel_id FROM economia_canali_monete WHERE guild_id = $1", guild_id)}

    async def aggiungi_canale(self, guild_id: int, channel_id: int) -> bool:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1)", guild_id)
                if await conn.fetchval("SELECT count(*) FROM economia_canali_monete WHERE guild_id = $1", guild_id) >= MAX_CANALI:
                    return False
                await conn.execute(
                    "INSERT INTO economia_canali_monete (guild_id, channel_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", guild_id, channel_id
                )
                return True

    async def togli_canale(self, guild_id: int, channel_id: int) -> None:
        await self._pool.execute(
            "DELETE FROM economia_canali_monete WHERE guild_id = $1 AND channel_id = $2", guild_id, channel_id
        )

    async def monete_messaggio(self, guild_id: int, user_id: int, giorno: date, monete: int, tetto: int) -> int:
        """Dà `monete` per un messaggio se il tetto del giorno non è superato (nella stessa scrittura). 0 se no."""
        if monete <= 0 or tetto <= 0 or monete > tetto:
            return 0
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                dato = await conn.fetchval(
                    "INSERT INTO economia_msg_giorno (guild_id, user_id, giorno, totale) VALUES ($1, $2, $3, $4) "
                    "ON CONFLICT (guild_id, user_id, giorno) DO UPDATE SET totale = economia_msg_giorno.totale + $4 "
                    "WHERE economia_msg_giorno.totale + $4 <= $5 RETURNING 1",
                    guild_id, user_id, giorno, monete, tetto,
                )
                if dato is None:
                    return 0
                await add_coins_in(conn, guild_id, user_id, monete)
                return monete


def _get_pool():
    from core.database import db

    return db.pool


stipendi_repo = StipendiRepository(pool_provider=_get_pool)
