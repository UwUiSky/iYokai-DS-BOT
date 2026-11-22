"""
core/repositories/partite_repo.py
=================================
Partite a più passi con le monete. La puntata si toglie all'apertura (UPDATE condizionata su saldo e pausa)
insieme alla riga della partita; la chiusura cancella la riga e dà la vincita nella stessa transazione, quindi
due clic non pagano due volte. Le partite abbandonate (il bot si è fermato) vengono rimborsate.
Funzioni coperte: ECO-088, ECO-089
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import asyncpg

from core.repositories.leveling_repo import add_coins_in, refund_coins_in, spend_coins_in

DURATA_MASSIMA_SECONDI = 900


class EsitoApertura(str, Enum):
    APERTA = "aperta"
    GIA_APERTA = "gia_aperta"
    PAUSA = "pausa"
    POCHE = "poche"


@dataclass(frozen=True)
class Apertura:
    esito: EsitoApertura
    partita_id: int | None = None


class _Annulla(Exception):
    def __init__(self, esito: EsitoApertura) -> None:
        self.esito = esito


class PartiteRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def apri(self, guild_id: int, user_id: int, gioco: str, puntata: int, attesa_secondi: int) -> Apertura:
        if puntata <= 0 or attesa_secondi < 0:
            raise ValueError("Puntata o attesa non valide.")
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    return Apertura(EsitoApertura.APERTA, await self._apri_in(conn, guild_id, user_id, gioco, puntata, attesa_secondi))
        except _Annulla as e:
            return Apertura(e.esito)

    @staticmethod
    async def _apri_in(conn: asyncpg.Connection, guild_id: int, user_id: int, gioco: str, puntata: int, attesa_secondi: int) -> int:
        """Riga della partita e puntata tolta, nella transazione di chi chiama. Annulla con `_Annulla`."""
        pid = await conn.fetchval(
            "INSERT INTO economia_partite_aperte (guild_id, user_id, gioco, puntata, scade_at) "
            "VALUES ($1, $2, $3, $4, now() + make_interval(secs => $5)) ON CONFLICT DO NOTHING RETURNING id",
            guild_id, user_id, gioco, puntata, float(DURATA_MASSIMA_SECONDI),
        )
        if pid is None:
            raise _Annulla(EsitoApertura.GIA_APERTA)
        toccato = await conn.fetchval(
            "UPDATE leveling_totals SET coins_total = coins_total - $3, ultima_partita_at = NOW() "
            "WHERE guild_id = $1 AND user_id = $2 AND coins_total >= $3 "
            "AND (ultima_partita_at IS NULL OR ultima_partita_at <= NOW() - make_interval(secs => $4)) RETURNING 1",
            guild_id, user_id, puntata, float(attesa_secondi),
        )
        if toccato is None:
            pausa = await conn.fetchval(
                "SELECT ultima_partita_at > NOW() - make_interval(secs => $3) FROM leveling_totals "
                "WHERE guild_id = $1 AND user_id = $2", guild_id, user_id, float(attesa_secondi),
            )
            raise _Annulla(EsitoApertura.PAUSA if pausa else EsitoApertura.POCHE)
        return pid

    async def apri_gruppo(
        self, guild_id: int, utenti: list[int], gioco: str, puntata: int, attesa_secondi: int
    ) -> tuple[EsitoApertura, int | None]:
        """
        Giochi a più giocatori (ECO-091...): la puntata si toglie a TUTTI in una sola transazione, in ordine di ID.
        Se uno non può (pochi soldi, pausa, già in una partita) non si toglie niente a nessuno e si dice chi è.
        """
        if puntata <= 0 or attesa_secondi < 0 or not utenti or len(set(utenti)) != len(utenti):
            raise ValueError("Puntata, attesa o giocatori non validi.")
        chi = None
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    for u in sorted(utenti):
                        chi = u
                        await self._apri_in(conn, guild_id, u, gioco, puntata, attesa_secondi)
            return EsitoApertura.APERTA, None
        except _Annulla as e:
            return e.esito, chi

    async def chiudi_gruppo(self, guild_id: int, gioco: str, restituzioni: dict[int, int]) -> dict[int, int]:
        """
        Chiude le partite di tutti i giocatori nella stessa transazione e paga `restituzioni` (0 = persa).
        Chi non ha più la riga (già rimborsato) non riceve niente. Restituisce quanto è stato pagato a ciascuno.
        """
        if any(v < 0 for v in restituzioni.values()):
            raise ValueError("Restituzione negativa.")
        pagati: dict[int, int] = {}
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for u in sorted(restituzioni):
                    riga = await conn.fetchval(
                        "DELETE FROM economia_partite_aperte WHERE guild_id = $1 AND user_id = $2 AND gioco = $3 RETURNING id",
                        guild_id, u, gioco,
                    )
                    if riga is None:
                        continue
                    if restituzioni[u] > 0:
                        await add_coins_in(conn, guild_id, u, restituzioni[u], classifica=False, motivo=gioco)
                    pagati[u] = restituzioni[u]
        return pagati

    async def rimborsa_gioco(self, prefisso: str, limite: int = 500) -> int:
        """All'avvio: le partite a più giocatori stanno in memoria, quindi una riga rimasta è abbandonata. Puntata intera indietro."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                righe = await conn.fetch(
                    "DELETE FROM economia_partite_aperte WHERE id IN (SELECT id FROM economia_partite_aperte "
                    "WHERE gioco LIKE $1 || '%' ORDER BY id LIMIT $2 FOR UPDATE SKIP LOCKED) RETURNING guild_id, user_id, puntata",
                    prefisso, limite,
                )
                for r in righe:
                    await refund_coins_in(conn, r["guild_id"], r["user_id"], r["puntata"])
                return len(righe)

    async def raddoppia(self, partita_id: int, guild_id: int, user_id: int) -> bool:
        """Toglie una seconda puntata e raddoppia quella della partita, insieme. False se i soldi non bastano o la partita non c'è."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                puntata = await conn.fetchval(
                    "SELECT puntata FROM economia_partite_aperte WHERE id = $1 AND guild_id = $2 AND user_id = $3 FOR UPDATE",
                    partita_id, guild_id, user_id,
                )
                if puntata is None or not await spend_coins_in(conn, guild_id, user_id, puntata):
                    return False
                await conn.execute("UPDATE economia_partite_aperte SET puntata = puntata * 2 WHERE id = $1", partita_id)
                return True

    async def chiudi(self, partita_id: int, guild_id: int, user_id: int, restituzione: int) -> tuple[int, int] | None:
        """
        Chiude la partita e dà `restituzione` (0 = persa). Restituisce (puntata finale, saldo) o None se era già chiusa:
        la riga si cancella una volta sola, quindi il pagamento avviene una volta sola.
        """
        if restituzione < 0:
            raise ValueError("Restituzione negativa.")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                puntata = await conn.fetchval(
                    "DELETE FROM economia_partite_aperte WHERE id = $1 AND guild_id = $2 AND user_id = $3 RETURNING puntata",
                    partita_id, guild_id, user_id,
                )
                if puntata is None:
                    return None
                if restituzione > 0:
                    saldo = await add_coins_in(conn, guild_id, user_id, restituzione, classifica=False)
                else:
                    saldo = await conn.fetchval(
                        "SELECT coins_total FROM leveling_totals WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
                    )
                return puntata, saldo

    async def rimborsa_scadute(self, limite: int = 100) -> int:
        """Puntata restituita (intera) per le partite abbandonate. Restituisce quante."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                righe = await conn.fetch(
                    "DELETE FROM economia_partite_aperte WHERE id IN (SELECT id FROM economia_partite_aperte "
                    "WHERE scade_at <= now() ORDER BY id LIMIT $1 FOR UPDATE SKIP LOCKED) RETURNING guild_id, user_id, puntata",
                    limite,
                )
                for r in righe:
                    await refund_coins_in(conn, r["guild_id"], r["user_id"], r["puntata"])
                return len(righe)


def _get_pool():
    from core.database import db

    return db.pool


partite_repo = PartiteRepository(pool_provider=_get_pool)
