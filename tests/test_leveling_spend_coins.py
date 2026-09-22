"""
tests/test_leveling_spend_coins.py
======================================
Test di LevelingRepository.spend_coins() contro PostgreSQL reale.
"""

import pytest

from core.repositories.leveling_repo import LevelingRepository


@pytest.fixture
def repo(clean_db):
    return LevelingRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_spend_coins_con_saldo_sufficiente(repo):
    await repo.add_coins(100, 1, 50)

    riuscito = await repo.spend_coins(100, 1, amount=30)

    assert riuscito is True
    totali = await repo.get_totals(100, 1)
    assert totali.coins_total == 20


@pytest.mark.asyncio
async def test_spend_coins_saldo_insufficiente_non_scrive_nulla(repo):
    await repo.add_coins(100, 1, 10)

    riuscito = await repo.spend_coins(100, 1, amount=50)

    assert riuscito is False
    totali = await repo.get_totals(100, 1)
    assert totali.coins_total == 10  # invariato


@pytest.mark.asyncio
async def test_spend_coins_senza_alcun_saldo_precedente(repo):
    riuscito = await repo.spend_coins(100, 999, amount=10)
    assert riuscito is False


@pytest.mark.asyncio
async def test_spend_coins_importo_non_positivo_solleva(repo):
    with pytest.raises(ValueError):
        await repo.spend_coins(100, 1, amount=0)
