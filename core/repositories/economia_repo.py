"""
core/repositories/economia_repo.py
==================================
Archivio delle regole dell'economia che non stanno in `leveling_repo`: saldo di partenza,
premi settimanale e mensile, monete a tutti i membri di un ruolo, azzeramento del server,
statistiche. Ogni movimento di monete è una scrittura sola o una transazione con le righe
bloccate: mai «leggi, controlla, scrivi».
Funzioni coperte: ECO-002, ECO-008, ECO-010, ECO-012, ECO-014, ECO-026
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import asyncpg

from core.repositories.leveling_repo import (
    add_coins_in,
    somma_con_tetto_sql,
    valore_nuovo_con_tetto_sql,
)

# ECO-010: tetto ai membri toccati da un solo comando (una transazione non deve durare minuti).
MAX_MEMBRI_PER_RUOLO = 5000


@dataclass(frozen=True)
class StatisticheEconomia:
    """ECO-008: monete in giro e come sono distribuite."""

    totale: int
    persone: int
    massimo: int
    mediana: int
    quota_primi_10: int  # percentuale delle monete in mano ai 10 più ricchi
    cassa: int


class EconomiaRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def accredito_iniziale(self, guild_id: int, user_id: int, importo: int) -> bool:
        """
        ECO-002: dà il saldo di partenza, una volta sola per persona e per server. La riga
        «già dato» e le monete stanno nella stessa transazione. Non conta nella classifica.
        """
        if importo <= 0:
            return False
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                nuovo = await conn.fetchval(
                    "INSERT INTO economia_accrediti_iniziali (guild_id, user_id) VALUES ($1, $2) "
                    "ON CONFLICT DO NOTHING RETURNING 1",
                    guild_id,
                    user_id,
                )
                if nuovo is None:
                    return False
                await add_coins_in(conn, guild_id, user_id, importo, classifica=False)
                return True

    async def riscuoti_periodico(
        self, guild_id: int, user_id: int, tipo: str, importo: int, attesa_secondi: int, adesso: datetime
    ) -> bool:
        """
        ECO-026: premio settimanale o mensile. La riga dell'ultima riscossione si scrive solo se
        l'attesa è finita (la condizione sta nella stessa istruzione): due clic insieme non pagano due volte.
        """
        if tipo not in ("settimanale", "mensile") or importo <= 0 or attesa_secondi <= 0:
            raise ValueError("Premio periodico non valido.")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                scritto = await conn.fetchval(
                    """
                    INSERT INTO economia_premi_periodici (guild_id, user_id, tipo, ultima_at)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (guild_id, user_id, tipo) DO UPDATE SET ultima_at = $4
                        WHERE economia_premi_periodici.ultima_at <= $5
                    RETURNING 1
                    """,
                    guild_id,
                    user_id,
                    tipo,
                    adesso,
                    adesso - timedelta(seconds=attesa_secondi),
                )
                if scritto is None:
                    return False
                await add_coins_in(conn, guild_id, user_id, importo)
                return True

    async def ultima_riscossione(self, guild_id: int, user_id: int, tipo: str) -> datetime | None:
        return await self._pool.fetchval(
            "SELECT ultima_at FROM economia_premi_periodici WHERE guild_id = $1 AND user_id = $2 AND tipo = $3",
            guild_id,
            user_id,
            tipo,
        )

    async def monete_a_ruolo(self, guild_id: int, user_ids: list[int], importo: int, toglie: bool) -> int:
        """
        ECO-010: aggiunge o toglie `importo` a tutti i `user_ids` in una transazione sola
        (righe bloccate in ordine di ID). Chi toglie non porta nessuno sotto zero. Non conta
        nella classifica. Restituisce quante persone sono state toccate.
        """
        if importo <= 0:
            raise ValueError("L'importo deve essere positivo.")
        ids = sorted(set(user_ids))
        if not ids:
            return 0
        if len(ids) > MAX_MEMBRI_PER_RUOLO:
            raise ValueError(f"Il ruolo ha più di {MAX_MEMBRI_PER_RUOLO} membri.")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT 1 FROM leveling_totals WHERE guild_id = $1 AND user_id = ANY($2::bigint[]) "
                    "ORDER BY user_id FOR UPDATE",
                    guild_id,
                    ids,
                )
                if toglie:
                    esito = await conn.execute(
                        "UPDATE leveling_totals SET coins_total = GREATEST(0, coins_total - $3) "
                        "WHERE guild_id = $1 AND user_id = ANY($2::bigint[]) AND coins_total > 0",
                        guild_id,
                        ids,
                        importo,
                    )
                    return int(esito.split()[-1])
                await conn.execute(
                    f"""
                    INSERT INTO leveling_totals (guild_id, user_id, coins_total)
                    SELECT $1, u, {valore_nuovo_con_tetto_sql(1, 3)} FROM unnest($2::bigint[]) AS u
                    ON CONFLICT (guild_id, user_id) DO UPDATE
                        SET coins_total = {somma_con_tetto_sql("leveling_totals.coins_total", 1, 3)}
                    """,
                    guild_id,
                    ids,
                    importo,
                )
                return len(ids)

    async def azzera_economia(self, guild_id: int) -> int:
        """
        ECO-012: tutti i saldi del server a zero, con le monete del mese e della settimana e le
        riscossioni periodiche (si può riscuotere di nuovo). XP e livelli non si toccano.
        Restituisce quanti saldi erano sopra zero.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                esito = await conn.execute(
                    "UPDATE leveling_totals SET coins_total = 0, last_daily_at = NULL, last_work_at = NULL "
                    "WHERE guild_id = $1 AND (coins_total <> 0 OR last_daily_at IS NOT NULL OR last_work_at IS NOT NULL)",
                    guild_id,
                )
                toccati = int(esito.split()[-1])
                await conn.execute("UPDATE leveling_activity SET coins = 0 WHERE guild_id = $1 AND coins <> 0", guild_id)
                await conn.execute("DELETE FROM economia_premi_periodici WHERE guild_id = $1", guild_id)
                return toccati

    async def cancella_saldo(self, guild_id: int, user_id: int) -> int:
        """ECO-014: chi esce perde il saldo (se il server lo ha scelto). Restituisce le monete tolte."""
        return int(
            await self._pool.fetchval(
                "WITH v AS (SELECT coins_total FROM leveling_totals WHERE guild_id = $1 AND user_id = $2 FOR UPDATE), "
                "u AS (UPDATE leveling_totals SET coins_total = 0 WHERE guild_id = $1 AND user_id = $2) "
                "SELECT COALESCE((SELECT coins_total FROM v), 0)",
                guild_id,
                user_id,
            )
            or 0
        )

    async def statistiche(self, guild_id: int) -> StatisticheEconomia:
        """ECO-008: monete in giro, persone con monete, massimo, mediana, quota dei primi 10, cassa."""
        riga = await self._pool.fetchrow(
            """
            WITH s AS (SELECT coins_total FROM leveling_totals WHERE guild_id = $1 AND coins_total > 0),
            top AS (SELECT COALESCE(SUM(coins_total), 0) AS t FROM
                    (SELECT coins_total FROM s ORDER BY coins_total DESC LIMIT 10) x)
            SELECT COALESCE(SUM(coins_total), 0) AS totale, COUNT(*) AS persone,
                   COALESCE(MAX(coins_total), 0) AS massimo,
                   COALESCE(percentile_disc(0.5) WITHIN GROUP (ORDER BY coins_total), 0) AS mediana,
                   (SELECT t FROM top) AS top10
            FROM s
            """,
            guild_id,
        )
        cassa = await self._pool.fetchval("SELECT balance FROM guild_chest WHERE guild_id = $1", guild_id)
        totale = int(riga["totale"])
        quota = round(int(riga["top10"]) * 100 / totale) if totale else 0
        return StatisticheEconomia(
            totale=totale,
            persone=int(riga["persone"]),
            massimo=int(riga["massimo"]),
            mediana=int(riga["mediana"]),
            quota_primi_10=quota,
            cassa=int(cassa or 0),
        )


def _get_pool():
    from core.database import db

    return db.pool


economia_repo = EconomiaRepository(pool_provider=_get_pool)
