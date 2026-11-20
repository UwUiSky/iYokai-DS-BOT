"""
core/repositories/lotteria_repo.py
==================================
Lotteria giornaliera (ECO-118), suo registro (ECO-121) e rimborso di parte delle perdite nette (ECO-117).
Il biglietto si paga e si registra nella stessa transazione; l'estrazione cancella i biglietti del giorno
e paga il vincitore nella stessa transazione, quindi avviene una sola volta; il rimborso sposta il punto di
partenza solo quando è pagato, così non si guadagna mai giocando.
Funzioni coperte: ECO-117, ECO-118, ECO-121
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import date

import asyncpg

from core.repositories.guild_chest_repo import deposit_in
from core.repositories.leveling_repo import add_coins_in, spend_coins_in

MAX_BIGLIETTI_AL_GIORNO = 10
QUOTA_BANCO_PCT = 10  # alla cassa del server
REASON_LOTTERIA = "lotteria"


@dataclass(frozen=True)
class Estrazione:
    guild_id: int
    giorno: date
    vincitore: int
    premio: int
    partecipanti: int


class LotteriaRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def compra(self, guild_id: int, user_id: int, giorno: date, prezzo: int, quanti: int) -> int | None:
        """
        Compra `quanti` biglietti per l'estrazione di fine giornata. Restituisce i biglietti posseduti, o None se
        il saldo non basta o si supererebbe il massimo giornaliero (la condizione sta nella stessa scrittura).
        """
        if prezzo <= 0 or not 1 <= quanti <= MAX_BIGLIETTI_AL_GIORNO:
            raise ValueError("Prezzo o quantità non validi.")
        try:
            return await self._compra(guild_id, user_id, giorno, prezzo, quanti)
        except _Annulla:  # la transazione è annullata: nessun biglietto e nessuna moneta mossa
            return None

    async def _compra(self, guild_id: int, user_id: int, giorno: date, prezzo: int, quanti: int) -> int:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                posseduti = await conn.fetchval(
                    "INSERT INTO economia_lotteria_biglietti (guild_id, giorno, user_id, biglietti, spesa) VALUES ($1, $2, $3, $4, $5) "
                    "ON CONFLICT (guild_id, giorno, user_id) DO UPDATE SET biglietti = economia_lotteria_biglietti.biglietti + $4, "
                    "spesa = economia_lotteria_biglietti.spesa + $5 WHERE economia_lotteria_biglietti.biglietti + $4 <= $6 RETURNING biglietti",
                    guild_id, giorno, user_id, quanti, quanti * prezzo, MAX_BIGLIETTI_AL_GIORNO,
                )
                if posseduti is None or not await spend_coins_in(conn, guild_id, user_id, quanti * prezzo):
                    raise _Annulla()
                return posseduti

    async def miei(self, guild_id: int, user_id: int, giorno: date) -> tuple[int, int]:
        """(i miei biglietti di oggi, tutti i biglietti di oggi)."""
        riga = await self._pool.fetchrow(
            "SELECT COALESCE(SUM(biglietti) FILTER (WHERE user_id = $3), 0) AS miei, COALESCE(SUM(biglietti), 0) AS tutti "
            "FROM economia_lotteria_biglietti WHERE guild_id = $1 AND giorno = $2",
            guild_id, giorno, user_id,
        )
        return int(riga["miei"]), int(riga["tutti"])

    async def estrai(self, guild_id: int, oggi: date) -> list[Estrazione]:
        """Estrae un vincitore per ogni giorno prima di `oggi` con biglietti. Una volta sola per giorno."""
        fatte: list[Estrazione] = []
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1)", guild_id)
                righe = await conn.fetch(
                    "DELETE FROM economia_lotteria_biglietti WHERE guild_id = $1 AND giorno < $2 RETURNING giorno, user_id, biglietti, spesa",
                    guild_id, oggi,
                )
                per_giorno: dict[date, list] = {}
                for r in righe:
                    per_giorno.setdefault(r["giorno"], []).append(r)
                for giorno in sorted(per_giorno):
                    gruppo = per_giorno[giorno]
                    totale_biglietti = sum(r["biglietti"] for r in gruppo)
                    spesa = sum(r["spesa"] for r in gruppo)
                    colpito = secrets.randbelow(totale_biglietti)
                    vincitore = gruppo[0]["user_id"]
                    for r in gruppo:
                        if colpito < r["biglietti"]:
                            vincitore = r["user_id"]
                            break
                        colpito -= r["biglietti"]
                    premio = spesa - spesa * QUOTA_BANCO_PCT // 100
                    if spesa - premio > 0:
                        await deposit_in(conn, guild_id, spesa - premio, REASON_LOTTERIA)
                    await add_coins_in(conn, guild_id, vincitore, premio, classifica=False)
                    await conn.execute(
                        "INSERT INTO economia_lotteria_estrazioni (guild_id, giorno, vincitore, premio, partecipanti) VALUES ($1, $2, $3, $4, $5) "
                        "ON CONFLICT DO NOTHING",
                        guild_id, giorno, vincitore, premio, len(gruppo),
                    )
                    fatte.append(Estrazione(guild_id, giorno, vincitore, premio, len(gruppo)))
        return fatte

    async def registro(self, guild_id: int, limite: int = 10) -> list[asyncpg.Record]:
        return await self._pool.fetch(
            "SELECT giorno, vincitore, premio, partecipanti FROM economia_lotteria_estrazioni WHERE guild_id = $1 "
            "ORDER BY giorno DESC LIMIT $2",
            guild_id, min(max(1, limite), 15),
        )

    async def guild_con_biglietti(self, oggi: date) -> list[int]:
        return [r["guild_id"] for r in await self._pool.fetch(
            "SELECT DISTINCT guild_id FROM economia_lotteria_biglietti WHERE giorno < $1", oggi)]

    # ---------------------------------------------------------------- ECO-117
    async def rimborso(self, guild_id: int, user_id: int, percentuale: int) -> int | None:
        """
        Rimborsa `percentuale`% delle perdite nette dei giochi dall'ultimo rimborso pagato. Restituisce le monete
        date, o None se non c'è niente da rimborsare (le vincite restano segnate: nessun trucco con i tempi).
        """
        if not 0 < percentuale <= 20:
            raise ValueError("Percentuale non valida.")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO economia_rimborsi (guild_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", guild_id, user_id
                )
                base = await conn.fetchval(
                    "SELECT netto_base FROM economia_rimborsi WHERE guild_id = $1 AND user_id = $2 FOR UPDATE", guild_id, user_id
                )
                netto = await conn.fetchval(
                    "SELECT COALESCE(SUM(netto), 0) FROM economia_giochi_stat WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
                )
                perdita = max(0, -(int(netto) - base))
                monete = perdita * percentuale // 100
                if monete <= 0:
                    return None
                await conn.execute(
                    "UPDATE economia_rimborsi SET netto_base = $3 WHERE guild_id = $1 AND user_id = $2", guild_id, user_id, int(netto)
                )
                await add_coins_in(conn, guild_id, user_id, monete, classifica=False)
                return monete


class _Annulla(Exception):
    pass


def _get_pool():
    from core.database import db

    return db.pool


lotteria_repo = LotteriaRepository(pool_provider=_get_pool)
