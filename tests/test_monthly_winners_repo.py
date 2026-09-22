"""
tests/test_monthly_winners_repo.py
======================================
Test di MonthlyWinnersRepository contro PostgreSQL reale.
"""

import pytest

from core.repositories.monthly_winners_repo import MonthlyWinnersRepository


@pytest.fixture
def repo(clean_db):
    return MonthlyWinnersRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_set_channel_prima_configurazione_segna_il_periodo_come_coperto(repo):
    await repo.set_channel(100, channel_id=500, already_covered_period="2026-08")

    config = await repo.get_config(100)
    assert config.channel_id == 500
    assert config.last_announced_period == "2026-08"


@pytest.mark.asyncio
async def test_cambio_canale_non_tocca_l_ultimo_periodo_annunciato(repo):
    await repo.set_channel(100, channel_id=500, already_covered_period="2026-08")
    await repo.mark_announced(100, "2026-09")

    await repo.set_channel(100, channel_id=777, already_covered_period="2026-09")

    config = await repo.get_config(100)
    assert config.channel_id == 777
    assert config.last_announced_period == "2026-09"


@pytest.mark.asyncio
async def test_mark_announced(repo):
    await repo.set_channel(100, channel_id=500, already_covered_period="2026-08")

    await repo.mark_announced(100, "2026-09")

    assert (await repo.get_config(100)).last_announced_period == "2026-09"


@pytest.mark.asyncio
async def test_disable(repo):
    await repo.set_channel(100, channel_id=500, already_covered_period="2026-08")

    assert await repo.disable(100) is True
    assert await repo.get_config(100) is None


@pytest.mark.asyncio
async def test_disable_senza_configurazione_restituisce_false(repo):
    assert await repo.disable(999) is False


@pytest.mark.asyncio
async def test_get_all_configs(repo):
    await repo.set_channel(100, channel_id=1, already_covered_period="2026-08")
    await repo.set_channel(200, channel_id=2, already_covered_period="2026-08")

    assert {c.guild_id for c in await repo.get_all_configs()} == {100, 200}
