"""
tests/test_feed_subscription_repo.py
========================================
Test di FeedSubscriptionRepository contro PostgreSQL reale.
"""

import pytest

from core.repositories.feed_subscription_repo import (
    DEFAULT_MESSAGE_TEMPLATE,
    FeedSubscriptionRepository,
)


@pytest.fixture
def repo(clean_db):
    return FeedSubscriptionRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_add_e_list_subscriptions(repo):
    await repo.add_subscription(
        guild_id=100,
        channel_id=500,
        feed_url="https://reddit.com/r/programming/new/.rss",
        label="r/programming",
        created_by=1,
    )

    lista = await repo.list_subscriptions(100)
    assert len(lista) == 1
    assert lista[0].label == "r/programming"
    assert lista[0].message_template == DEFAULT_MESSAGE_TEMPLATE
    assert lista[0].last_seen_entry_id is None


@pytest.mark.asyncio
async def test_add_con_template_personalizzato(repo):
    await repo.add_subscription(
        100, 500, "https://esempio.com/feed.rss", "Esempio", 1,
        message_template="Nuovo su {label}: {title}",
    )

    lista = await repo.list_subscriptions(100)
    assert lista[0].message_template == "Nuovo su {label}: {title}"


@pytest.mark.asyncio
async def test_list_subscriptions_filtra_per_server(repo):
    await repo.add_subscription(100, 500, "https://a.com/feed", "A", 1)
    await repo.add_subscription(200, 600, "https://b.com/feed", "B", 1)

    lista_100 = await repo.list_subscriptions(100)
    assert len(lista_100) == 1
    assert lista_100[0].label == "A"


@pytest.mark.asyncio
async def test_remove_subscription_funziona(repo):
    subscription_id = await repo.add_subscription(100, 500, "https://a.com/feed", "A", 1)

    rimosso = await repo.remove_subscription(subscription_id, guild_id=100)

    assert rimosso is True
    assert await repo.list_subscriptions(100) == []


@pytest.mark.asyncio
async def test_remove_subscription_non_permette_di_cancellare_di_un_altro_server(repo):
    subscription_id = await repo.add_subscription(100, 500, "https://a.com/feed", "A", 1)

    rimosso = await repo.remove_subscription(subscription_id, guild_id=999)

    assert rimosso is False
    assert len(await repo.list_subscriptions(100)) == 1


@pytest.mark.asyncio
async def test_get_all_subscriptions_prende_di_ogni_server(repo):
    await repo.add_subscription(100, 500, "https://a.com/feed", "A", 1)
    await repo.add_subscription(200, 600, "https://b.com/feed", "B", 1)

    tutte = await repo.get_all_subscriptions()
    assert len(tutte) == 2


@pytest.mark.asyncio
async def test_update_last_seen(repo):
    subscription_id = await repo.add_subscription(100, 500, "https://a.com/feed", "A", 1)

    await repo.update_last_seen(subscription_id, entry_id="entry-123")

    lista = await repo.list_subscriptions(100)
    assert lista[0].last_seen_entry_id == "entry-123"
