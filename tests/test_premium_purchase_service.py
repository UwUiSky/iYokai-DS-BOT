"""
tests/test_premium_purchase_service.py
==========================================
Test di purchase_premium_tier() contro PostgreSQL reale (SPEC.md
§15.15) — verifica l'ORDINE dei controlli (tempo, tier già
acquistato, saldo) e che la cassa non venga mai toccata se un
controllo fallisce prima della spesa.
"""

from datetime import datetime, timedelta, timezone

import pytest

from core.premium_purchase_service import PurchaseOutcome, purchase_premium_tier
from core.repositories.guild_chest_repo import REASON_WEEKLY_PERSONAL_DECAY, guild_chest_repo
from core.repositories.guild_premium_repo import guild_premium_repo

JOIN = datetime(2026, 1, 1, tzinfo=timezone.utc)
DOPO_SEI_MESI = JOIN + timedelta(days=190)  # oltre i 6 mesi civili


@pytest.fixture(autouse=True)
def _collega_pool_di_test(monkeypatch, clean_db):
    import core.database as database_module
    monkeypatch.setattr(database_module.db, "_pool", clean_db)


async def _configura_guild(clean_db, guild_id: int, joined_at: datetime) -> None:
    await clean_db.execute(
        "INSERT INTO guild_config (guild_id, created_at) VALUES ($1, $2)",
        guild_id,
        joined_at,
    )


@pytest.mark.asyncio
async def test_guild_non_configurata_fallisce_senza_toccare_la_cassa(clean_db):
    risultato = await purchase_premium_tier(999, tier=1, member_count=500, now=DOPO_SEI_MESI)

    assert risultato.outcome == PurchaseOutcome.GUILD_NOT_CONFIGURED
    assert await guild_chest_repo.get_balance(999) == 0


@pytest.mark.asyncio
async def test_tier_non_definito_fallisce(clean_db):
    await _configura_guild(clean_db, 100, JOIN)

    risultato = await purchase_premium_tier(100, tier=4, member_count=500, now=DOPO_SEI_MESI)

    assert risultato.outcome == PurchaseOutcome.TIER_NOT_DEFINED


@pytest.mark.asyncio
async def test_tempo_non_ancora_sbloccato_fallisce_senza_toccare_la_cassa(clean_db):
    await _configura_guild(clean_db, 100, JOIN)
    await guild_chest_repo.deposit(100, 10_000_000, REASON_WEEKLY_PERSONAL_DECAY)
    prima_di_sei_mesi = JOIN + timedelta(days=10)

    risultato = await purchase_premium_tier(
        100, tier=1, member_count=500, now=prima_di_sei_mesi
    )

    assert risultato.outcome == PurchaseOutcome.TIME_NOT_UNLOCKED
    assert await guild_chest_repo.get_balance(100) == 10_000_000  # invariata


@pytest.mark.asyncio
async def test_saldo_insufficiente_fallisce_senza_scalare_nulla(clean_db):
    await _configura_guild(clean_db, 100, JOIN)
    await guild_chest_repo.deposit(100, 100_000, REASON_WEEKLY_PERSONAL_DECAY)  # < 500.000

    risultato = await purchase_premium_tier(
        100, tier=1, member_count=500, now=DOPO_SEI_MESI
    )

    assert risultato.outcome == PurchaseOutcome.INSUFFICIENT_FUNDS
    assert risultato.cost == 500_000
    assert await guild_chest_repo.get_balance(100) == 100_000  # invariato


@pytest.mark.asyncio
async def test_acquisto_riuscito_scala_la_cassa_ed_estende_il_premium(clean_db):
    await _configura_guild(clean_db, 100, JOIN)
    await guild_chest_repo.deposit(100, 1_000_000, REASON_WEEKLY_PERSONAL_DECAY)

    risultato = await purchase_premium_tier(
        100, tier=1, member_count=500, now=DOPO_SEI_MESI
    )

    assert risultato.outcome == PurchaseOutcome.SUCCESS
    assert risultato.cost == 500_000
    assert risultato.new_premium_until == DOPO_SEI_MESI + timedelta(days=30)
    assert await guild_chest_repo.get_balance(100) == 500_000  # 1.000.000 - 500.000

    stato = await guild_premium_repo.get_status(100)
    assert stato.is_active(DOPO_SEI_MESI) is True


@pytest.mark.asyncio
async def test_tier_gia_acquistato_fallisce_senza_toccare_la_cassa(clean_db):
    await _configura_guild(clean_db, 100, JOIN)
    await guild_chest_repo.deposit(100, 2_000_000, REASON_WEEKLY_PERSONAL_DECAY)
    await purchase_premium_tier(100, tier=1, member_count=500, now=DOPO_SEI_MESI)
    saldo_dopo_primo_acquisto = await guild_chest_repo.get_balance(100)

    risultato = await purchase_premium_tier(
        100, tier=1, member_count=500, now=DOPO_SEI_MESI
    )

    assert risultato.outcome == PurchaseOutcome.ALREADY_PURCHASED
    assert await guild_chest_repo.get_balance(100) == saldo_dopo_primo_acquisto  # invariato


@pytest.mark.asyncio
async def test_costo_scala_con_la_fascia_membri(clean_db):
    await _configura_guild(clean_db, 100, JOIN)
    await guild_chest_repo.deposit(100, 10_000_000, REASON_WEEKLY_PERSONAL_DECAY)

    risultato = await purchase_premium_tier(
        100, tier=1, member_count=5_000, now=DOPO_SEI_MESI
    )

    assert risultato.outcome == PurchaseOutcome.SUCCESS
    assert risultato.cost == 5_000_000  # fascia 5.000 membri: ×10 sulla base
