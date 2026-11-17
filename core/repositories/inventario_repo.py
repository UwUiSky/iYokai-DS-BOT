"""
core/repositories/inventario_repo.py
====================================
Inventario degli oggetti del negozio: elenco, uso, regalo, rivendita e azzeramento. Ogni
movimento di oggetti è un UPDATE condizionato (`quantita > 0`) nella stessa transazione
dell'effetto collegato (monete, oggetto all'altro): mai «leggi, controlla, scrivi».
Funzioni coperte: ECO-058, ECO-059, ECO-070, ECO-071, ECO-072, ECO-086
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import asyncpg

from core.leveling_logic import prezzo_rivendita
from core.repositories.leveling_repo import add_coins_in


class Esito(str, Enum):
    FATTO = "fatto"
    NON_HAI = "non_hai"
    NON_REGALABILE = "non_regalabile"
    NIENTE_DA_PAGARE = "niente_da_pagare"


@dataclass(frozen=True)
class VoceInventario:
    item_id: int
    nome: str
    quantita: int
    prezzo: int


@dataclass(frozen=True)
class Rivendita:
    esito: Esito
    monete: int = 0
    saldo: int = 0


_TOGLI_UNO = (
    "UPDATE economia_inventario SET quantita = quantita - 1 "
    "WHERE guild_id = $1 AND user_id = $2 AND item_id = $3 AND quantita > 0 RETURNING quantita"
)
_METTI_UNO = (
    "INSERT INTO economia_inventario (guild_id, user_id, item_id, quantita) VALUES ($1, $2, $3, 1) "
    "ON CONFLICT (guild_id, user_id, item_id) DO UPDATE SET quantita = economia_inventario.quantita + 1"
)
_PULISCI = "DELETE FROM economia_inventario WHERE guild_id = $1 AND user_id = $2 AND item_id = $3 AND quantita <= 0"


class InventarioRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def lista(self, guild_id: int, user_id: int, limite: int = 25) -> list[VoceInventario]:
        """ECO-058: gli oggetti posseduti (al massimo `limite`, 25 di base: un menu o un embed)."""
        righe = await self._pool.fetch(
            "SELECT i.item_id, s.name, i.quantita, s.price FROM economia_inventario i "
            "JOIN shop_items s ON s.id = i.item_id AND s.guild_id = i.guild_id "
            "WHERE i.guild_id = $1 AND i.user_id = $2 ORDER BY s.name LIMIT $3",
            guild_id, user_id, min(max(1, limite), 25),
        )
        return [VoceInventario(r["item_id"], r["name"], r["quantita"], r["price"]) for r in righe]

    async def usa(self, guild_id: int, user_id: int, item_id: int) -> bool:
        """ECO-059: consuma un pezzo. False (senza scrivere) se non lo si ha."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                resta = await conn.fetchval(_TOGLI_UNO, guild_id, user_id, item_id)
                if resta is None:
                    return False
                await conn.execute(_PULISCI, guild_id, user_id, item_id)
                return True

    async def regala(self, guild_id: int, da: int, a: int, item_id: int) -> Esito:
        """
        ECO-070/071: un pezzo da `da` ad `a`, in una transazione, con le due righe bloccate in
        ordine di ID (A→B e B→A insieme non si bloccano a vicenda). Mai a se stessi.
        """
        if da == a:
            raise ValueError("Non si regala a se stessi.")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                regalabile = await conn.fetchval(
                    "SELECT regalabile FROM shop_items WHERE id = $1 AND guild_id = $2", item_id, guild_id
                )
                if regalabile is None:
                    return Esito.NON_HAI
                if not regalabile:
                    return Esito.NON_REGALABILE
                await conn.execute(
                    "SELECT 1 FROM economia_inventario WHERE guild_id = $1 AND item_id = $2 "
                    "AND user_id = ANY($3::bigint[]) ORDER BY user_id FOR UPDATE",
                    guild_id, item_id, [da, a],
                )
                if await conn.fetchval(_TOGLI_UNO, guild_id, da, item_id) is None:
                    return Esito.NON_HAI
                await conn.execute(_PULISCI, guild_id, da, item_id)
                await conn.execute(_METTI_UNO, guild_id, a, item_id)
                return Esito.FATTO

    async def vendi(self, guild_id: int, user_id: int, item_id: int) -> Rivendita:
        """
        ECO-072: rivende un pezzo per metà del prezzo di oggi. Pezzo tolto e monete date nella
        stessa transazione; senza pezzo nessuna moneta nasce. Non conta nella classifica.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                prezzo = await conn.fetchval(
                    "SELECT price FROM shop_items WHERE id = $1 AND guild_id = $2 FOR SHARE", item_id, guild_id
                )
                if prezzo is None:
                    return Rivendita(Esito.NON_HAI)
                monete = prezzo_rivendita(prezzo)
                if monete <= 0:
                    return Rivendita(Esito.NIENTE_DA_PAGARE)
                if await conn.fetchval(_TOGLI_UNO, guild_id, user_id, item_id) is None:
                    return Rivendita(Esito.NON_HAI)
                await conn.execute(_PULISCI, guild_id, user_id, item_id)
                saldo = await add_coins_in(conn, guild_id, user_id, monete, classifica=False)
                return Rivendita(Esito.FATTO, monete, saldo)

    async def azzera_server(self, guild_id: int) -> int:
        """ECO-086: svuota tutti gli inventari del server. Restituisce le righe tolte."""
        esito = await self._pool.execute("DELETE FROM economia_inventario WHERE guild_id = $1", guild_id)
        return int(esito.split()[-1])


def _get_pool():
    from core.database import db

    return db.pool


inventario_repo = InventarioRepository(pool_provider=_get_pool)
