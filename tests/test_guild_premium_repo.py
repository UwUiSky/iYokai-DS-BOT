"""
tests/test_guild_premium_repo.py
====================================
Test di GuildPremiumRepository contro PostgreSQL reale (SPEC.md
§15.15 — sblocco premium via cassa: quali tier sono già stati
comprati, e per quanto tempo il server ha premium attivo).
"""

from datetime import datetime, timedelta, timezone

import pytest

from core.repositories.guild_premium_repo import GuildPremiumRepository

ORA = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def repo(clean_db):
    return GuildPremiumRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_nessun_tier_acquistato_di_default(repo):
    assert await repo.purchased_tiers(100) == set()
    assert await repo.is_tier_purchased(100, 1) is False


@pytest.mark.asyncio
async def test_stato_di_default_non_e_attivo(repo):
    stato = await repo.get_status(100)
    assert stato.premium_until is None
    assert stato.is_active(ORA) is False


@pytest.mark.asyncio
async def test_record_purchase_marca_il_tier_come_acquistato(repo):
    await repo.record_purchase(100, tier=1, cost_paid=500_000, now=ORA)

    assert await repo.is_tier_purchased(100, 1) is True
    assert 1 in await repo.purchased_tiers(100)


@pytest.mark.asyncio
async def test_record_purchase_estende_premium_until_di_un_mese(repo):
    nuova_scadenza = await repo.record_purchase(100, tier=1, cost_paid=500_000, now=ORA)

    assert nuova_scadenza == ORA + timedelta(days=30)
    stato = await repo.get_status(100)
    assert stato.premium_until == nuova_scadenza
    assert stato.is_active(ORA) is True


@pytest.mark.asyncio
async def test_acquisti_successivi_si_accumulano_invece_di_accavallarsi(repo):
    await repo.record_purchase(100, tier=1, cost_paid=500_000, now=ORA)
    # Secondo acquisto fatto lo stesso giorno (tier diverso): deve
    # aggiungersi ai 30 giorni già accreditati, non ripartire da ORA.
    nuova_scadenza = await repo.record_purchase(100, tier=2, cost_paid=5_000_000, now=ORA)

    assert nuova_scadenza == ORA + timedelta(days=60)


@pytest.mark.asyncio
async def test_acquisto_dopo_la_scadenza_riparte_da_ora(repo):
    await repo.record_purchase(100, tier=1, cost_paid=500_000, now=ORA)
    molto_dopo = ORA + timedelta(days=365)  # ben oltre i 30 giorni comprati

    nuova_scadenza = await repo.record_purchase(
        100, tier=2, cost_paid=5_000_000, now=molto_dopo
    )

    assert nuova_scadenza == molto_dopo + timedelta(days=30)


@pytest.mark.asyncio
async def test_acquisto_duplicato_dello_stesso_tier_solleva_errore(repo):
    await repo.record_purchase(100, tier=1, cost_paid=500_000, now=ORA)
    with pytest.raises(Exception):
        await repo.record_purchase(100, tier=1, cost_paid=500_000, now=ORA)


@pytest.mark.asyncio
async def test_server_diversi_non_si_mischiano(repo):
    await repo.record_purchase(100, tier=1, cost_paid=500_000, now=ORA)

    assert await repo.is_tier_purchased(200, 1) is False
    assert (await repo.get_status(200)).premium_until is None
