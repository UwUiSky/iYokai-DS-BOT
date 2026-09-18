"""
tests/test_greetings_repo.py
===============================
Test di GreetingsRepository contro PostgreSQL reale.
"""

import pytest

from core.greetings_logic import (
    DEFAULT_BOOST_TEMPLATE,
    DEFAULT_GOODBYE_TEMPLATE,
    DEFAULT_WELCOME_TEMPLATE,
)
from core.repositories.greetings_repo import GreetingsRepository


@pytest.fixture
def repo(clean_db):
    return GreetingsRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_config_di_default(repo):
    config = await repo.get_config(100)
    assert config.welcome_enabled is False
    assert config.welcome_message == DEFAULT_WELCOME_TEMPLATE
    assert config.goodbye_message == DEFAULT_GOODBYE_TEMPLATE
    assert config.boost_message == DEFAULT_BOOST_TEMPLATE


@pytest.mark.asyncio
async def test_set_welcome(repo):
    await repo.set_welcome(100, enabled=True, channel_id=111, message="Ciao {user}!", dm=True)
    config = await repo.get_config(100)
    assert config.welcome_enabled is True
    assert config.welcome_channel_id == 111
    assert config.welcome_message == "Ciao {user}!"
    assert config.welcome_dm is True


@pytest.mark.asyncio
async def test_set_goodbye(repo):
    await repo.set_goodbye(100, enabled=True, channel_id=222, message="Ciao {username}!")
    config = await repo.get_config(100)
    assert config.goodbye_enabled is True
    assert config.goodbye_channel_id == 222
    assert config.goodbye_message == "Ciao {username}!"


@pytest.mark.asyncio
async def test_set_boost(repo):
    await repo.set_boost(100, enabled=True, channel_id=333, message="Grazie {user}!")
    config = await repo.get_config(100)
    assert config.boost_enabled is True
    assert config.boost_channel_id == 333
    assert config.boost_message == "Grazie {user}!"


@pytest.mark.asyncio
async def test_set_welcome_non_tocca_goodbye_e_boost(repo):
    # Le tre impostazioni condividono la stessa riga: modificarne una
    # non deve toccare le altre due, che devono restare ai default.
    await repo.set_welcome(100, enabled=True, channel_id=111, message="X", dm=False)
    config = await repo.get_config(100)

    assert config.goodbye_enabled is False
    assert config.goodbye_message == DEFAULT_GOODBYE_TEMPLATE
    assert config.boost_enabled is False
    assert config.boost_message == DEFAULT_BOOST_TEMPLATE


@pytest.mark.asyncio
async def test_set_welcome_due_volte_sovrascrive(repo):
    await repo.set_welcome(100, True, 111, "primo", False)
    await repo.set_welcome(100, True, 222, "secondo", True)

    config = await repo.get_config(100)
    assert config.welcome_channel_id == 222
    assert config.welcome_message == "secondo"
    assert config.welcome_dm is True


@pytest.mark.asyncio
async def test_tutte_e_tre_le_impostazioni_insieme(repo):
    await repo.set_welcome(100, True, 111, "welcome", False)
    await repo.set_goodbye(100, True, 222, "goodbye")
    await repo.set_boost(100, True, 333, "boost")

    config = await repo.get_config(100)
    assert config.welcome_channel_id == 111
    assert config.goodbye_channel_id == 222
    assert config.boost_channel_id == 333


@pytest.mark.asyncio
async def test_config_non_mischia_server(repo):
    await repo.set_welcome(100, True, 111, "server 100", False)
    await repo.set_welcome(200, True, 222, "server 200", False)

    config_100 = await repo.get_config(100)
    config_200 = await repo.get_config(200)
    assert config_100.welcome_message == "server 100"
    assert config_200.welcome_message == "server 200"
