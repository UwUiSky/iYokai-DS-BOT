"""
tests/test_voice_temp_repo.py
================================
Test di VoiceTempRepository contro PostgreSQL reale.
"""

import pytest

from core.repositories.voice_temp_repo import VoiceTempRepository


@pytest.fixture
def repo(clean_db):
    return VoiceTempRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_config_di_default_e_vuota(repo):
    config = await repo.get_config(100)
    assert config.generator_channel_id is None
    assert config.category_id is None


@pytest.mark.asyncio
async def test_set_e_get_config(repo):
    await repo.set_config(100, generator_channel_id=42, category_id=99)
    config = await repo.get_config(100)
    assert config.generator_channel_id == 42
    assert config.category_id == 99


@pytest.mark.asyncio
async def test_set_config_sovrascrive_la_precedente(repo):
    await repo.set_config(100, generator_channel_id=42, category_id=99)
    await repo.set_config(100, generator_channel_id=43, category_id=100)
    config = await repo.get_config(100)
    assert config.generator_channel_id == 43
    assert config.category_id == 100


@pytest.mark.asyncio
async def test_get_owner_di_canale_non_tracciato_e_none(repo):
    owner = await repo.get_owner(999999)
    assert owner is None


@pytest.mark.asyncio
async def test_register_e_get_owner(repo):
    await repo.register_channel(channel_id=5001, guild_id=100, owner_id=42)
    owner = await repo.get_owner(5001)
    assert owner == 42


@pytest.mark.asyncio
async def test_register_due_volte_sullo_stesso_canale_aggiorna_owner(repo):
    await repo.register_channel(5001, 100, owner_id=42)
    await repo.register_channel(5001, 100, owner_id=99)
    owner = await repo.get_owner(5001)
    assert owner == 99


@pytest.mark.asyncio
async def test_set_owner_trasferisce_proprieta(repo):
    await repo.register_channel(5001, 100, owner_id=42)
    trasferito = await repo.set_owner(5001, new_owner_id=99)
    assert trasferito is True
    assert await repo.get_owner(5001) == 99


@pytest.mark.asyncio
async def test_set_owner_su_canale_non_tracciato_restituisce_false(repo):
    trasferito = await repo.set_owner(999999, new_owner_id=99)
    assert trasferito is False


@pytest.mark.asyncio
async def test_unregister_channel(repo):
    await repo.register_channel(5001, 100, owner_id=42)
    await repo.unregister_channel(5001)
    assert await repo.get_owner(5001) is None


@pytest.mark.asyncio
async def test_unregister_canale_inesistente_non_fallisce(repo):
    await repo.unregister_channel(999999)  # non deve sollevare eccezioni
