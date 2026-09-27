"""
tests/test_module_subscription_repo.py
==========================================
Test di ModuleSubscriptionRepository contro PostgreSQL reale.
"""

from datetime import datetime, timedelta, timezone

import pytest

from core.repositories.module_subscription_repo import ModuleSubscriptionRepository

ORA = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def repo(clean_db):
    return ModuleSubscriptionRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_grant_prima_volta_imposta_la_scadenza(repo):
    scadenza = await repo.grant(100, "spam_trap", duration_days=30, now=ORA)

    assert scadenza == ORA + timedelta(days=30)
    assert await repo.is_active(100, "spam_trap", now=ORA) is True


@pytest.mark.asyncio
async def test_grant_rinnovo_si_accumula_dalla_scadenza_attuale(repo):
    """Un rinnovo concesso PRIMA della scadenza non deve sprecare i
    giorni restanti — stesso pattern di GuildPremiumRepository."""
    await repo.grant(100, "spam_trap", duration_days=30, now=ORA)

    seconda_concessione = ORA + timedelta(days=10)  # ancora 20 giorni residui
    nuova_scadenza = await repo.grant(100, "spam_trap", duration_days=30, now=seconda_concessione)

    assert nuova_scadenza == ORA + timedelta(days=60)


@pytest.mark.asyncio
async def test_grant_dopo_la_scadenza_riparte_da_ora(repo):
    await repo.grant(100, "spam_trap", duration_days=30, now=ORA)

    dopo_la_scadenza = ORA + timedelta(days=40)  # scaduto da 10 giorni
    nuova_scadenza = await repo.grant(100, "spam_trap", duration_days=30, now=dopo_la_scadenza)

    assert nuova_scadenza == dopo_la_scadenza + timedelta(days=30)


@pytest.mark.asyncio
async def test_is_active_falso_prima_di_qualunque_concessione(repo):
    assert await repo.is_active(100, "spam_trap", now=ORA) is False


@pytest.mark.asyncio
async def test_is_active_falso_dopo_la_scadenza(repo):
    await repo.grant(100, "spam_trap", duration_days=30, now=ORA)

    assert await repo.is_active(100, "spam_trap", now=ORA + timedelta(days=31)) is False


@pytest.mark.asyncio
async def test_scoped_per_modulo_non_per_intero_server(repo):
    await repo.grant(100, "spam_trap", duration_days=30, now=ORA)

    assert await repo.is_active(100, "automod", now=ORA) is False


@pytest.mark.asyncio
async def test_revoke(repo):
    await repo.grant(100, "spam_trap", duration_days=30, now=ORA)

    assert await repo.revoke(100, "spam_trap") is True
    assert await repo.is_active(100, "spam_trap", now=ORA) is False


@pytest.mark.asyncio
async def test_revoke_inesistente_restituisce_false(repo):
    assert await repo.revoke(100, "spam_trap") is False


@pytest.mark.asyncio
async def test_list_for_guild(repo):
    await repo.grant(100, "spam_trap", duration_days=30, now=ORA)
    await repo.grant(100, "automod", duration_days=365, now=ORA)
    await repo.grant(200, "spam_trap", duration_days=30, now=ORA)  # altro server

    abbonamenti = await repo.list_for_guild(100)

    assert {s.module_name for s in abbonamenti} == {"spam_trap", "automod"}
