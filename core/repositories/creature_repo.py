"""
core/repositories/creature_repo.py
==================================
Creature di fantasia (ECO-101): nascono quando si usa un oggetto del negozio, combattono con una posta in monete.
Evocazione: pezzo consumato e creatura creata nella stessa transazione (con il tetto per persona protetto da un
lucchetto). Scontro: le due creature e i due saldi si bloccano in ordine di ID, si controlla che entrambi abbiano la
posta, il caso si estrae con le forze lette sotto blocco, e posta, forze e storico si scrivono insieme.
Funzioni coperte: ECO-101
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum

import asyncpg

from core import creature_logic as cl
from core.duello_logic import POSTA_MASSIMA, POSTA_MINIMA, guadagno_con_tetto
from core.repositories.inventario_repo import consuma_in


class EsitoEvoca(str, Enum):
    FATTO = "fatto"
    NON_HAI = "non_hai"
    PIENO = "pieno"


class EsitoScontro(str, Enum):
    FATTO = "fatto"
    CREATURA_NON_VALIDA = "creatura_non_valida"
    POCHE_SFIDANTE = "poche_sfidante"
    POCHE_SFIDATO = "poche_sfidato"


@dataclass(frozen=True)
class Evocazione:
    esito: EsitoEvoca
    creatura_id: int | None = None
    specie: int = 0
    forza: int = 0


@dataclass(frozen=True)
class Scontro:
    esito: EsitoScontro
    importo: int = 0
    vince_sfidante: bool = False
    perdente_persa: bool = False
    forza_vincitrice: int = 0
    forza_perdente: int = 0


class CreatureRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def elenco(self, guild_id: int, user_id: int) -> list[asyncpg.Record]:
        """Le creature di una persona, le più forti per prime (al massimo MAX_CREATURE)."""
        return await self._pool.fetch(
            "SELECT id, specie, forza, vittorie, sconfitte FROM economia_creature WHERE guild_id = $1 AND user_id = $2 "
            "ORDER BY forza DESC, id LIMIT $3",
            guild_id, user_id, cl.MAX_CREATURE,
        )

    async def evoca(self, guild_id: int, user_id: int, item_id: int, rng: random.Random) -> Evocazione:
        """
        Usa un pezzo dell'oggetto-creatura e crea la creatura. La specie si legge dall'oggetto, mai da chi chiama.
        Con la scorta piena il pezzo NON si consuma.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                specie = await conn.fetchval(
                    "SELECT azione_valore FROM shop_items WHERE id = $1 AND guild_id = $2 AND azione = 'creatura'", item_id, guild_id
                )
                if specie is None:
                    return Evocazione(EsitoEvoca.NON_HAI)
                await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", f"creature:{guild_id}:{user_id}")
                n = await conn.fetchval("SELECT count(*) FROM economia_creature WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)
                if n >= cl.MAX_CREATURE:
                    return Evocazione(EsitoEvoca.PIENO)
                if not await consuma_in(conn, guild_id, user_id, item_id):
                    return Evocazione(EsitoEvoca.NON_HAI)
                forza = cl.forza_iniziale(rng)
                cid = await conn.fetchval(
                    "INSERT INTO economia_creature (guild_id, user_id, specie, forza) VALUES ($1, $2, $3, $4) RETURNING id",
                    guild_id, user_id, specie, forza,
                )
                return Evocazione(EsitoEvoca.FATTO, cid, specie, forza)

    async def scontra(
        self, guild_id: int, sfidante: int, creatura_sfidante: int, sfidato: int, creatura_sfidato: int, posta: int, rng: random.Random
    ) -> Scontro:
        """Uno scontro già accettato. Tutto in una transazione; senza la posta di entrambi o con una creatura cambiata non scrive."""
        if sfidante == sfidato or creatura_sfidante == creatura_sfidato:
            raise ValueError("Non ci si sfida da soli.")
        if not POSTA_MINIMA <= posta <= POSTA_MASSIMA:
            raise ValueError("Posta non valida.")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                righe = await conn.fetch(
                    "SELECT id, user_id, forza FROM economia_creature WHERE guild_id = $1 AND id = ANY($2::bigint[]) ORDER BY id FOR UPDATE",
                    guild_id, [creatura_sfidante, creatura_sfidato],
                )
                per_id = {r["id"]: r for r in righe}
                a, b = per_id.get(creatura_sfidante), per_id.get(creatura_sfidato)
                if a is None or b is None or a["user_id"] != sfidante or b["user_id"] != sfidato:
                    return Scontro(EsitoScontro.CREATURA_NON_VALIDA)
                saldi = {
                    r["user_id"]: r["coins_total"]
                    for r in await conn.fetch(
                        "SELECT user_id, coins_total FROM leveling_totals WHERE guild_id = $1 AND user_id = ANY($2::bigint[]) "
                        "ORDER BY user_id FOR UPDATE",
                        guild_id, [sfidante, sfidato],
                    )
                }
                if saldi.get(sfidante, 0) < posta:
                    return Scontro(EsitoScontro.POCHE_SFIDANTE)
                if saldi.get(sfidato, 0) < posta:
                    return Scontro(EsitoScontro.POCHE_SFIDATO)
                vince_sfidante = cl.vince_il_primo(a["forza"], b["forza"], rng)
                vinc, perd = (a, b) if vince_sfidante else (b, a)
                tetto = await conn.fetchval("SELECT NULLIF(tetto_saldo, 0) FROM leveling_settings WHERE guild_id = $1", guild_id)
                importo = guadagno_con_tetto(posta, saldi[vinc["user_id"]], tetto)
                if importo > 0:
                    await conn.execute(
                        "UPDATE leveling_totals SET coins_total = coins_total - $3 WHERE guild_id = $1 AND user_id = $2",
                        guild_id, perd["user_id"], importo,
                    )
                    await conn.execute(
                        "UPDATE leveling_totals SET coins_total = coins_total + $3 WHERE guild_id = $1 AND user_id = $2",
                        guild_id, vinc["user_id"], importo,
                    )
                forza_vinc = cl.dopo_vittoria(vinc["forza"])
                forza_perd, fugge = cl.dopo_sconfitta(perd["forza"])
                await conn.execute("UPDATE economia_creature SET forza = $2, vittorie = vittorie + 1 WHERE id = $1", vinc["id"], forza_vinc)
                if fugge:
                    await conn.execute("DELETE FROM economia_creature WHERE id = $1", perd["id"])
                else:
                    await conn.execute("UPDATE economia_creature SET forza = $2, sconfitte = sconfitte + 1 WHERE id = $1", perd["id"], forza_perd)
                await conn.execute(
                    "INSERT INTO economia_lotte_creature (guild_id, vincitore, perdente, creatura_vincitrice, creatura_perdente, posta, persa) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                    guild_id, vinc["user_id"], perd["user_id"], vinc["id"], perd["id"], posta, fugge,
                )
                return Scontro(EsitoScontro.FATTO, importo, vince_sfidante, fugge, forza_vinc, forza_perd)


def _get_pool():
    from core.database import db

    return db.pool


creature_repo = CreatureRepository(pool_provider=_get_pool)
