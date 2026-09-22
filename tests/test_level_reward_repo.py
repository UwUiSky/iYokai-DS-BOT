"""
tests/test_level_reward_repo.py
===================================
Test di LevelRewardRepository contro PostgreSQL reale.
"""

import pytest

from core.repositories.level_reward_repo import LevelRewardRepository


@pytest.fixture
def repo(clean_db):
    return LevelRewardRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_add_reward_e_list_rewards(repo):
    await repo.add_reward(guild_id=100, level_threshold=5, role_id=555)

    ricompense = await repo.list_rewards(100)
    assert len(ricompense) == 1
    assert ricompense[0].level_threshold == 5
    assert ricompense[0].role_id == 555


@pytest.mark.asyncio
async def test_add_reward_stesso_livello_due_volte_sostituisce_il_ruolo(repo):
    await repo.add_reward(100, level_threshold=5, role_id=111)
    await repo.add_reward(100, level_threshold=5, role_id=222)  # stesso livello, ruolo diverso

    ricompense = await repo.list_rewards(100)
    assert len(ricompense) == 1  # non due righe per lo stesso livello
    assert ricompense[0].role_id == 222


@pytest.mark.asyncio
async def test_list_rewards_ordinate_per_livello(repo):
    await repo.add_reward(100, level_threshold=10, role_id=1)
    await repo.add_reward(100, level_threshold=5, role_id=2)
    await repo.add_reward(100, level_threshold=20, role_id=3)

    ricompense = await repo.list_rewards(100)
    assert [r.level_threshold for r in ricompense] == [5, 10, 20]


@pytest.mark.asyncio
async def test_remove_reward(repo):
    reward_id = await repo.add_reward(100, level_threshold=5, role_id=555)

    rimossa = await repo.remove_reward(reward_id, guild_id=100)

    assert rimossa is True
    assert await repo.list_rewards(100) == []


@pytest.mark.asyncio
async def test_remove_reward_non_permette_altro_server(repo):
    reward_id = await repo.add_reward(100, level_threshold=5, role_id=555)

    rimossa = await repo.remove_reward(reward_id, guild_id=999)

    assert rimossa is False


@pytest.mark.asyncio
async def test_get_rewards_up_to_level_e_cumulativo(repo):
    await repo.add_reward(100, level_threshold=5, role_id=1)
    await repo.add_reward(100, level_threshold=10, role_id=2)
    await repo.add_reward(100, level_threshold=15, role_id=3)

    # Livello 12: deve includere le soglie 5 e 10, non la 15.
    ricompense = await repo.get_rewards_up_to_level(100, level=12)

    assert [r.role_id for r in ricompense] == [1, 2]


@pytest.mark.asyncio
async def test_get_rewards_up_to_level_include_la_soglia_esatta(repo):
    await repo.add_reward(100, level_threshold=10, role_id=1)

    ricompense = await repo.get_rewards_up_to_level(100, level=10)

    assert len(ricompense) == 1


@pytest.mark.asyncio
async def test_get_rewards_up_to_level_nessuna_ricompensa_configurata(repo):
    assert await repo.get_rewards_up_to_level(100, level=50) == []
