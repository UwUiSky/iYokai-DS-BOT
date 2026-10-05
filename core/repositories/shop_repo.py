"""
core/repositories/shop_repo.py
==================================
Shop dell'economia: catalogo degli oggetti per server (prezzo, ruolo
facoltativo) e acquisti. L'acquisto toglie i coin e registra la riga
nella stessa transazione; un oggetto a ruolo si compra una volta sola
per utente (indice unico, migrazione 0015).
Funzioni coperte: SPEC §15.4
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import asyncpg

from core.repositories.leveling_repo import refund_coins_in, spend_coins_in


@dataclass(frozen=True)
class ShopItem:
    id: int
    guild_id: int
    name: str
    price: int
    role_id: int | None
    description: str | None


@dataclass(frozen=True)
class Purchase:
    id: int
    guild_id: int
    user_id: int
    item_id: int
    purchased_at: datetime


class EsitoAcquisto(str, Enum):
    RIUSCITO = "riuscito"
    GIA_ACQUISTATO = "gia_acquistato"
    SALDO_INSUFFICIENTE = "saldo_insufficiente"


@dataclass(frozen=True)
class Acquisto:
    esito: EsitoAcquisto
    purchase_id: int | None = None


class _SaldoInsufficiente(Exception):
    """Interna a buy_item: annulla la transazione dell'acquisto."""


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS shop_items (
            id            SERIAL PRIMARY KEY,
            guild_id      BIGINT NOT NULL,
            name          TEXT NOT NULL,
            price         INTEGER NOT NULL,
            role_id       BIGINT,
            description   TEXT
        );

        CREATE TABLE IF NOT EXISTS shop_purchases (
            id             SERIAL PRIMARY KEY,
            guild_id       BIGINT NOT NULL,
            user_id        BIGINT NOT NULL,
            item_id        INTEGER NOT NULL,
            purchased_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_shop_items_guild ON shop_items (guild_id);
        CREATE INDEX IF NOT EXISTS idx_shop_purchases_user
            ON shop_purchases (guild_id, user_id, item_id);
        """
    )


class ShopRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    def _row_to_item(self, row) -> ShopItem:
        return ShopItem(
            id=row["id"],
            guild_id=row["guild_id"],
            name=row["name"],
            price=row["price"],
            role_id=row["role_id"],
            description=row["description"],
        )

    async def add_item(
        self,
        guild_id: int,
        name: str,
        price: int,
        role_id: int | None = None,
        description: str | None = None,
    ) -> int:
        row = await self._pool.fetchrow(
            """
            INSERT INTO shop_items (guild_id, name, price, role_id, description)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            guild_id,
            name,
            price,
            role_id,
            description,
        )
        return row["id"]

    async def remove_item(self, item_id: int, guild_id: int) -> bool:
        result = await self._pool.execute(
            "DELETE FROM shop_items WHERE id = $1 AND guild_id = $2", item_id, guild_id
        )
        return result.endswith(" 1")

    async def list_items(self, guild_id: int) -> list[ShopItem]:
        rows = await self._pool.fetch(
            "SELECT * FROM shop_items WHERE guild_id = $1 ORDER BY price", guild_id
        )
        return [self._row_to_item(r) for r in rows]

    async def get_item(self, item_id: int, guild_id: int) -> ShopItem | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM shop_items WHERE id = $1 AND guild_id = $2", item_id, guild_id
        )
        return self._row_to_item(row) if row is not None else None

    async def buy_item(self, guild_id: int, user_id: int, item: ShopItem) -> Acquisto:
        """
        Registra l'acquisto e toglie i coin in UNA transazione (BUG-14).
        Un oggetto a ruolo già comprato non si ricompra: lo decide
        l'indice unico, non una lettura fatta prima. Se il saldo non
        basta non resta scritto nulla.
        """
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    purchase_id = await conn.fetchval(
                        """
                        INSERT INTO shop_purchases (guild_id, user_id, item_id, role_id)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (guild_id, user_id, item_id) WHERE role_id IS NOT NULL
                            DO NOTHING
                        RETURNING id
                        """,
                        guild_id,
                        user_id,
                        item.id,
                        item.role_id,
                    )
                    if purchase_id is None:
                        return Acquisto(EsitoAcquisto.GIA_ACQUISTATO)
                    if not await spend_coins_in(conn, guild_id, user_id, item.price):
                        raise _SaldoInsufficiente
                    return Acquisto(EsitoAcquisto.RIUSCITO, purchase_id)
        except _SaldoInsufficiente:
            return Acquisto(EsitoAcquisto.SALDO_INSUFFICIENTE)

    async def refund_purchase(
        self, purchase_id: int, guild_id: int, user_id: int, price: int
    ) -> bool:
        """
        Annulla un acquisto appena fatto (il ruolo non è stato dato):
        cancella la riga e restituisce i coin nella stessa transazione.
        Chiamarla due volte rimborsa una volta sola.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                cancellato = await conn.fetchval(
                    "DELETE FROM shop_purchases WHERE id = $1 RETURNING id", purchase_id
                )
                if cancellato is None:
                    return False
                await refund_coins_in(conn, guild_id, user_id, price)
                return True


def _get_pool():
    from core.database import db
    return db.pool


shop_repo = ShopRepository(pool_provider=_get_pool)
