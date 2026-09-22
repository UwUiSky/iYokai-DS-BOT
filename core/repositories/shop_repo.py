"""
core/repositories/shop_repo.py
==================================
Shop dell'economia leveling (SPEC.md §15.4 — "nessun posto dove
spendere i coin"). Oggetti configurabili per server, un prezzo, un
ruolo OPZIONALE da concedere all'acquisto (un oggetto senza ruolo
resta puramente decorativo/da collezione — un "pozzo" per i coin,
legittimo di per sé in un'economia di questo tipo). Le sottrazioni
di coin passano da LevelingRepository.spend_coins() (atomiche,
mai un saldo negativo) — questo repository si occupa solo del
catalogo e dello storico acquisti.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg


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

    async def record_purchase(self, guild_id: int, user_id: int, item_id: int) -> None:
        await self._pool.execute(
            """
            INSERT INTO shop_purchases (guild_id, user_id, item_id)
            VALUES ($1, $2, $3)
            """,
            guild_id,
            user_id,
            item_id,
        )

    async def has_purchased(self, guild_id: int, user_id: int, item_id: int) -> bool:
        """Usata per gli oggetti a ruolo: evita di far ricomprare
        (e sottrarre coin per) qualcosa che l'utente possiede già —
        chi ha già il ruolo non deve pagarlo una seconda volta."""
        row = await self._pool.fetchrow(
            """
            SELECT 1 FROM shop_purchases
            WHERE guild_id = $1 AND user_id = $2 AND item_id = $3
            """,
            guild_id,
            user_id,
            item_id,
        )
        return row is not None


def _get_pool():
    from core.database import db
    return db.pool


shop_repo = ShopRepository(pool_provider=_get_pool)
