"""
core/repositories/guild_chest_repo.py
=========================================
Cassa del server: una tesoreria del server intero, distinta da quella
di ogni clan. Entrano i coin tolti dal decadimento settimanale dei
saldi personali e da quello mensile delle tesorerie dei clan; escono
per i premi evento e per lo sblocco del premium. Ogni movimento resta
scritto nello storico.
Funzioni coperte: SPEC §15.15
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg

REASON_WEEKLY_PERSONAL_DECAY = "weekly_personal_decay"
REASON_MONTHLY_CLAN_DECAY = "monthly_clan_decay"
REASON_PREMIUM_PURCHASE = "premium_purchase"
REASON_EVENT_LOBBY_PRIZE = "event_lobby_prize"
REASON_EVENT_WINNER_PRIZE = "event_winner_prize"


@dataclass(frozen=True)
class GuildChestLedgerEntry:
    id: int
    guild_id: int
    amount: int
    reason: str
    created_at: datetime


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS guild_chest (
            guild_id   BIGINT PRIMARY KEY,
            balance    BIGINT NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS guild_chest_ledger (
            id         SERIAL PRIMARY KEY,
            guild_id   BIGINT NOT NULL,
            amount     BIGINT NOT NULL,
            reason     TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_guild_chest_ledger_guild
            ON guild_chest_ledger (guild_id, created_at);
        """
    )


async def spend_in(
    conn: asyncpg.Connection, guild_id: int, amount: int, reason: str
) -> bool:
    """
    Toglie coin dalla cassa su una connessione già aperta, così chi
    chiama può mettere l'addebito e ciò che si compra nella stessa
    transazione. Il controllo del saldo sta dentro la UPDATE: mai un
    saldo negativo. False (senza scrivere nulla) se il saldo non basta.
    """
    if amount <= 0:
        raise ValueError("L'importo da spendere dalla cassa deve essere positivo.")

    saldo = await conn.fetchval(
        """
        UPDATE guild_chest SET balance = balance - $2, updated_at = now()
        WHERE guild_id = $1 AND balance >= $2
        RETURNING balance
        """,
        guild_id,
        amount,
    )
    if saldo is None:
        return False
    await conn.execute(
        "INSERT INTO guild_chest_ledger (guild_id, amount, reason) VALUES ($1, $2, $3)",
        guild_id,
        -amount,
        reason,
    )
    return True


class GuildChestRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def get_balance(self, guild_id: int) -> int:
        return (
            await self._pool.fetchval(
                "SELECT balance FROM guild_chest WHERE guild_id = $1", guild_id
            )
            or 0
        )

    async def deposit(self, guild_id: int, amount: int, reason: str) -> int:
        """
        Accredita coin nella cassa del server e registra il
        movimento nel ledger, atomicamente. Nessun prelievo qui
        dentro (vedi docstring del modulo) — solo depositi, quindi
        amount deve essere positivo: un decadimento a delta zero non
        deve nemmeno chiamare questo metodo (i chiamanti lo saltano
        già, come per il ledger di tesoreria di clan). Restituisce il
        nuovo saldo della cassa.
        """
        if amount <= 0:
            raise ValueError("L'importo da depositare in cassa deve essere positivo.")

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    INSERT INTO guild_chest (guild_id, balance)
                    VALUES ($1, $2)
                    ON CONFLICT (guild_id) DO UPDATE
                        SET balance = guild_chest.balance + $2,
                            updated_at = now()
                    RETURNING balance
                    """,
                    guild_id,
                    amount,
                )
                await conn.execute(
                    """
                    INSERT INTO guild_chest_ledger (guild_id, amount, reason)
                    VALUES ($1, $2, $3)
                    """,
                    guild_id,
                    amount,
                    reason,
                )
                return row["balance"]

    async def spend(self, guild_id: int, amount: int, reason: str) -> bool:
        """
        Sottrae coin dalla cassa solo se il saldo basta e scrive il
        movimento, in una transazione. Restituisce False (senza
        scrivere nulla) se il saldo non basta.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                return await spend_in(conn, guild_id, amount, reason)

    async def list_ledger(
        self, guild_id: int, limit: int = 20
    ) -> list[GuildChestLedgerEntry]:
        rows = await self._pool.fetch(
            """
            SELECT id, guild_id, amount, reason, created_at
            FROM guild_chest_ledger
            WHERE guild_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            guild_id,
            limit,
        )
        return [
            GuildChestLedgerEntry(
                id=r["id"],
                guild_id=r["guild_id"],
                amount=r["amount"],
                reason=r["reason"],
                created_at=r["created_at"],
            )
            for r in rows
        ]


def _get_pool():
    from core.database import db
    return db.pool


guild_chest_repo = GuildChestRepository(pool_provider=_get_pool)
