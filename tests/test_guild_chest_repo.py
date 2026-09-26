"""
tests/test_guild_chest_repo.py
==================================
Test di GuildChestRepository contro PostgreSQL reale (SPEC.md
§15.15 — cassa di server alimentata dai decadimenti settimanale
personale e mensile di tesoreria di clan).
"""

import pytest

from core.repositories.guild_chest_repo import (
    REASON_MONTHLY_CLAN_DECAY,
    REASON_WEEKLY_PERSONAL_DECAY,
    GuildChestRepository,
)


@pytest.fixture
def repo(clean_db):
    return GuildChestRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_saldo_di_default_per_server_mai_visto(repo):
    assert await repo.get_balance(999) == 0


@pytest.mark.asyncio
async def test_deposit_accredita_e_restituisce_il_nuovo_saldo(repo):
    nuovo_saldo = await repo.deposit(100, 5_000, REASON_WEEKLY_PERSONAL_DECAY)

    assert nuovo_saldo == 5_000
    assert await repo.get_balance(100) == 5_000


@pytest.mark.asyncio
async def test_deposit_si_accumula_su_piu_chiamate(repo):
    await repo.deposit(100, 5_000, REASON_WEEKLY_PERSONAL_DECAY)
    await repo.deposit(100, 3_000, REASON_MONTHLY_CLAN_DECAY)

    assert await repo.get_balance(100) == 8_000


@pytest.mark.asyncio
async def test_deposit_non_mischia_server_diversi(repo):
    await repo.deposit(100, 5_000, REASON_WEEKLY_PERSONAL_DECAY)
    await repo.deposit(200, 1_000, REASON_WEEKLY_PERSONAL_DECAY)

    assert await repo.get_balance(100) == 5_000
    assert await repo.get_balance(200) == 1_000


@pytest.mark.asyncio
async def test_deposit_importo_non_positivo_solleva_errore(repo):
    with pytest.raises(ValueError):
        await repo.deposit(100, 0, REASON_WEEKLY_PERSONAL_DECAY)
    with pytest.raises(ValueError):
        await repo.deposit(100, -1, REASON_WEEKLY_PERSONAL_DECAY)


@pytest.mark.asyncio
async def test_deposit_registra_un_movimento_nel_ledger(repo):
    await repo.deposit(100, 5_000, REASON_WEEKLY_PERSONAL_DECAY)
    await repo.deposit(100, 3_000, REASON_MONTHLY_CLAN_DECAY)

    movimenti = await repo.list_ledger(100)

    assert len(movimenti) == 2
    ragioni = {m.reason for m in movimenti}
    assert ragioni == {REASON_WEEKLY_PERSONAL_DECAY, REASON_MONTHLY_CLAN_DECAY}
    assert all(m.guild_id == 100 for m in movimenti)


@pytest.mark.asyncio
async def test_list_ledger_rispetta_il_limite(repo):
    for _ in range(5):
        await repo.deposit(100, 100, REASON_WEEKLY_PERSONAL_DECAY)

    movimenti = await repo.list_ledger(100, limit=2)

    assert len(movimenti) == 2
