"""
core/repositories/duelli_repo.py
================================
Duelli con posta: le due righe dei saldi si bloccano in ordine di ID nella stessa transazione, si
controlla che ENTRAMBI abbiano la posta e il passaggio perdente -> vincitore è una scrittura sola
(niente monete create o perse, tetto al saldo compreso).
Funzioni coperte: ECO-104, ECO-106
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import asyncpg

from core.duello_logic import POSTA_MASSIMA, POSTA_MINIMA, guadagno_con_tetto


class EsitoPosta(str, Enum):
    FATTO = "fatto"
    SFIDANTE_POCHE = "sfidante_poche"
    SFIDATO_POCHE = "sfidato_poche"


@dataclass(frozen=True)
class Passaggio:
    esito: EsitoPosta
    importo: int = 0


class DuelliRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def regola(self, guild_id: int, sfidante: int, sfidato: int, vince_sfidante: bool, posta: int) -> Passaggio:
        """Chiude un duello già estratto: la posta passa dal perdente al vincitore, se entrambi la hanno ancora."""
        if sfidante == sfidato:
            raise ValueError("Non ci si sfida da soli.")
        if not POSTA_MINIMA <= posta <= POSTA_MASSIMA:
            raise ValueError("Posta non valida.")
        vincitore, perdente = (sfidante, sfidato) if vince_sfidante else (sfidato, sfidante)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                righe = await conn.fetch(
                    "SELECT user_id, coins_total FROM leveling_totals WHERE guild_id = $1 AND user_id = ANY($2::bigint[]) "
                    "ORDER BY user_id FOR UPDATE",
                    guild_id, [sfidante, sfidato],
                )
                cash = {r["user_id"]: r["coins_total"] for r in righe}
                if cash.get(sfidante, 0) < posta:
                    return Passaggio(EsitoPosta.SFIDANTE_POCHE)
                if cash.get(sfidato, 0) < posta:
                    return Passaggio(EsitoPosta.SFIDATO_POCHE)
                tetto = await conn.fetchval(
                    "SELECT NULLIF(tetto_saldo, 0) FROM leveling_settings WHERE guild_id = $1", guild_id
                )
                importo = guadagno_con_tetto(posta, cash[vincitore], tetto)
                if importo > 0:
                    await conn.execute(
                        "UPDATE leveling_totals SET coins_total = coins_total - $3 WHERE guild_id = $1 AND user_id = $2",
                        guild_id, perdente, importo,
                    )
                    await conn.execute(
                        "UPDATE leveling_totals SET coins_total = coins_total + $3 WHERE guild_id = $1 AND user_id = $2",
                        guild_id, vincitore, importo,
                    )
                await conn.execute(
                    "INSERT INTO economia_duelli (guild_id, vincitore, perdente, posta) VALUES ($1, $2, $3, $4)",
                    guild_id, vincitore, perdente, max(1, importo) if importo else posta,
                )
                return Passaggio(EsitoPosta.FATTO, importo)

    async def classifica(self, guild_id: int, limite: int = 10) -> list[asyncpg.Record]:
        """ECO-106: i 10 con più vittorie, con sconfitte e monete vinte."""
        return await self._pool.fetch(
            "SELECT u.user_id, COALESCE(v.n, 0) AS vinti, COALESCE(p.n, 0) AS persi, COALESCE(v.tot, 0) - COALESCE(p.tot, 0) AS netto "
            "FROM (SELECT vincitore AS user_id FROM economia_duelli WHERE guild_id = $1 UNION "
            "      SELECT perdente FROM economia_duelli WHERE guild_id = $1) u "
            "LEFT JOIN (SELECT vincitore, count(*) n, sum(posta) tot FROM economia_duelli WHERE guild_id = $1 GROUP BY vincitore) v ON v.vincitore = u.user_id "
            "LEFT JOIN (SELECT perdente, count(*) n, sum(posta) tot FROM economia_duelli WHERE guild_id = $1 GROUP BY perdente) p ON p.perdente = u.user_id "
            "ORDER BY vinti DESC, netto DESC LIMIT $2",
            guild_id, min(max(1, limite), 10),
        )

    async def storico(self, guild_id: int, user_id: int, limite: int = 10) -> list[asyncpg.Record]:
        """ECO-106: gli ultimi duelli di una persona."""
        return await self._pool.fetch(
            "SELECT vincitore, perdente, posta, giocato_at FROM economia_duelli "
            "WHERE guild_id = $1 AND (vincitore = $2 OR perdente = $2) ORDER BY id DESC LIMIT $3",
            guild_id, user_id, min(max(1, limite), 15),
        )


def _get_pool():
    from core.database import db

    return db.pool


duelli_repo = DuelliRepository(pool_provider=_get_pool)
