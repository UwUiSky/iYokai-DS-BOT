"""
core/repositories/guild_premium_repo.py
===========================================
Persistenza dello sblocco premium via cassa di server (SPEC.md
§15.15). Due responsabilità distinte:

- `guild_premium_purchases`: quali tier (1, 2, 3) sono già stati
  acquistati da un server — un tier si compra una volta sola, mai
  due volte (il costo/tempo minimo sono per acquisto, non ricorrenti)
- `guild_premium_status`: il saldo di "premium attivo" del server, come
  una data di scadenza (`premium_until`) — ogni acquisto AGGIUNGE un
  mese a partire dal massimo tra ora e la scadenza attuale, quindi i
  mesi comprati in momenti diversi si accumulano invece di accavallarsi

La logica di prezzo/tempo minimo (SPEC.md §15.14/§15.15) resta in
core/premium_pricing_logic.py — questo file si occupa solo della
persistenza, non decide se un acquisto è ammesso.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg

PREMIUM_MONTH_DAYS = 30


@dataclass(frozen=True)
class GuildPremiumStatus:
    guild_id: int
    premium_until: datetime | None

    def is_active(self, now: datetime) -> bool:
        return self.premium_until is not None and self.premium_until > now


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS guild_premium_purchases (
            guild_id     BIGINT NOT NULL,
            tier         INTEGER NOT NULL,
            cost_paid    BIGINT NOT NULL,
            purchased_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (guild_id, tier)
        );

        CREATE TABLE IF NOT EXISTS guild_premium_status (
            guild_id      BIGINT PRIMARY KEY,
            premium_until TIMESTAMPTZ NOT NULL
        );
        """
    )


class GuildPremiumRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def purchased_tiers(self, guild_id: int) -> set[int]:
        rows = await self._pool.fetch(
            "SELECT tier FROM guild_premium_purchases WHERE guild_id = $1",
            guild_id,
        )
        return {r["tier"] for r in rows}

    async def is_tier_purchased(self, guild_id: int, tier: int) -> bool:
        return await self._pool.fetchval(
            """
            SELECT EXISTS(
                SELECT 1 FROM guild_premium_purchases
                WHERE guild_id = $1 AND tier = $2
            )
            """,
            guild_id,
            tier,
        )

    async def get_status(self, guild_id: int) -> GuildPremiumStatus:
        premium_until = await self._pool.fetchval(
            "SELECT premium_until FROM guild_premium_status WHERE guild_id = $1",
            guild_id,
        )
        return GuildPremiumStatus(guild_id=guild_id, premium_until=premium_until)

    async def record_purchase(
        self, guild_id: int, tier: int, cost_paid: int, now: datetime
    ) -> datetime:
        """
        Registra l'acquisto del tier (fallisce con una violazione di
        chiave se già acquistato — il chiamante deve aver già
        verificato `is_tier_purchased` prima, questo metodo non lo
        rifà per restare atomico in un'unica transazione insieme
        all'estensione della scadenza premium) ed estende
        `premium_until` di un mese a partire dal massimo tra `now` e
        la scadenza attuale — così mesi comprati in momenti diversi
        si accumulano. Restituisce la nuova scadenza.
        """
        from datetime import timedelta

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO guild_premium_purchases (guild_id, tier, cost_paid, purchased_at)
                    VALUES ($1, $2, $3, $4)
                    """,
                    guild_id,
                    tier,
                    cost_paid,
                    now,
                )

                scadenza_attuale = await conn.fetchval(
                    """
                    SELECT premium_until FROM guild_premium_status
                    WHERE guild_id = $1 FOR UPDATE
                    """,
                    guild_id,
                )
                base = max(scadenza_attuale, now) if scadenza_attuale else now
                nuova_scadenza = base + timedelta(days=PREMIUM_MONTH_DAYS)

                await conn.execute(
                    """
                    INSERT INTO guild_premium_status (guild_id, premium_until)
                    VALUES ($1, $2)
                    ON CONFLICT (guild_id) DO UPDATE SET premium_until = $2
                    """,
                    guild_id,
                    nuova_scadenza,
                )
                return nuova_scadenza


def _get_pool():
    from core.database import db
    return db.pool


guild_premium_repo = GuildPremiumRepository(pool_provider=_get_pool)
