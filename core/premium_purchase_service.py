"""
core/premium_purchase_service.py
====================================
Orchestrazione dell'acquisto di un tier premium via cassa di server
(SPEC.md §15.15) — l'unico punto che combina insieme:

- la data di join del bot nel server (core.database.db, doppio
  cancello temporale)
- il prezzo/tempo minimo per tier (core.premium_pricing_logic, pura)
- la spesa dalla cassa (core.repositories.guild_chest_repo)
- la registrazione dell'acquisto + estensione della scadenza premium
  (core.repositories.guild_premium_repo)

Ogni controllo è fatto QUI, in un ordine preciso, PRIMA di spendere
qualunque coin: se un controllo fallisce non viene toccata la cassa.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from core.premium_pricing_logic import (
    MAX_DEFINED_TIER,
    is_tier_time_unlocked,
    premium_tier_cost,
)
from core.repositories.guild_chest_repo import (
    REASON_PREMIUM_PURCHASE,
    guild_chest_repo,
)
from core.repositories.guild_premium_repo import guild_premium_repo


class PurchaseOutcome(str, Enum):
    SUCCESS = "success"
    GUILD_NOT_CONFIGURED = "guild_not_configured"
    TIER_NOT_DEFINED = "tier_not_defined"
    ALREADY_PURCHASED = "already_purchased"
    TIME_NOT_UNLOCKED = "time_not_unlocked"
    INSUFFICIENT_FUNDS = "insufficient_funds"


@dataclass(frozen=True)
class PurchaseResult:
    outcome: PurchaseOutcome
    tier: int
    cost: int | None = None
    new_premium_until: datetime | None = None


async def purchase_premium_tier(
    guild_id: int,
    tier: int,
    member_count: int,
    now: datetime | None = None,
) -> PurchaseResult:
    adesso = now or datetime.now(timezone.utc)

    if tier < 1 or tier > MAX_DEFINED_TIER:
        return PurchaseResult(outcome=PurchaseOutcome.TIER_NOT_DEFINED, tier=tier)

    from core.database import db  # import locale per evitare cicli

    join_at = await db.get_guild_joined_at(guild_id)
    if join_at is None:
        return PurchaseResult(outcome=PurchaseOutcome.GUILD_NOT_CONFIGURED, tier=tier)

    if await guild_premium_repo.is_tier_purchased(guild_id, tier):
        return PurchaseResult(outcome=PurchaseOutcome.ALREADY_PURCHASED, tier=tier)

    if not is_tier_time_unlocked(tier, join_at, adesso):
        return PurchaseResult(outcome=PurchaseOutcome.TIME_NOT_UNLOCKED, tier=tier)

    costo = premium_tier_cost(tier, member_count)

    speso = await guild_chest_repo.spend(guild_id, costo, REASON_PREMIUM_PURCHASE)
    if not speso:
        return PurchaseResult(
            outcome=PurchaseOutcome.INSUFFICIENT_FUNDS, tier=tier, cost=costo
        )

    nuova_scadenza = await guild_premium_repo.record_purchase(
        guild_id, tier, costo, adesso
    )
    return PurchaseResult(
        outcome=PurchaseOutcome.SUCCESS,
        tier=tier,
        cost=costo,
        new_premium_until=nuova_scadenza,
    )
