"""
tests/test_twitch_subscription_repo.py
===========================================
Test di TwitchSubscriptionRepository contro PostgreSQL reale.
"""

import pytest

from core.repositories.twitch_subscription_repo import (
    DEFAULT_LIVE_MESSAGE_TEMPLATE,
    TwitchSubscriptionRepository,
)


@pytest.fixture
def repo(clean_db):
    return TwitchSubscriptionRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_add_e_list_subscriptions(repo):
    await repo.add_subscription(
        guild_id=100, channel_id=500, twitch_login="StreamerA", label="Streamer A", created_by=1
    )

    lista = await repo.list_subscriptions(100)
    assert len(lista) == 1
    assert lista[0].twitch_login == "streamera"  # normalizzato minuscolo
    assert lista[0].live_message_template == DEFAULT_LIVE_MESSAGE_TEMPLATE
    assert lista[0].last_known_live is False


@pytest.mark.asyncio
async def test_list_subscriptions_filtra_per_server(repo):
    await repo.add_subscription(100, 500, "a", "A", 1)
    await repo.add_subscription(200, 600, "b", "B", 1)

    assert len(await repo.list_subscriptions(100)) == 1


@pytest.mark.asyncio
async def test_remove_subscription(repo):
    subscription_id = await repo.add_subscription(100, 500, "a", "A", 1)

    rimosso = await repo.remove_subscription(subscription_id, guild_id=100)

    assert rimosso is True
    assert await repo.list_subscriptions(100) == []


@pytest.mark.asyncio
async def test_remove_subscription_non_permette_altro_server(repo):
    subscription_id = await repo.add_subscription(100, 500, "a", "A", 1)

    rimosso = await repo.remove_subscription(subscription_id, guild_id=999)

    assert rimosso is False


@pytest.mark.asyncio
async def test_get_all_subscriptions(repo):
    await repo.add_subscription(100, 500, "a", "A", 1)
    await repo.add_subscription(200, 600, "b", "B", 1)

    assert len(await repo.get_all_subscriptions()) == 2


@pytest.mark.asyncio
async def test_update_last_known_live(repo):
    subscription_id = await repo.add_subscription(100, 500, "a", "A", 1)

    await repo.update_last_known_live(subscription_id, is_live=True)

    lista = await repo.list_subscriptions(100)
    assert lista[0].last_known_live is True
