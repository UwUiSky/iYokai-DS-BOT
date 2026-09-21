"""
tests/test_feed_watcher.py
=============================
Test di FeedWatcherService.tick() con un server aiohttp VERO in
locale (aiohttp.test_utils), non un mock della sessione — verifica
il download HTTP reale, non solo che la funzione di parsing venga
chiamata con l'input giusto.
"""

import discord
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from core.feed_watcher import FeedWatcherService
from core.repositories.feed_subscription_repo import FeedSubscriptionRepository

RSS_DI_ESEMPIO = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Nuovo post</title>
      <link>https://esempio.com/post2</link>
      <guid>post-2</guid>
    </item>
    <item>
      <title>Post vecchio</title>
      <link>https://esempio.com/post1</link>
      <guid>post-1</guid>
    </item>
  </channel>
</rss>
"""


class _FakeChannel(discord.TextChannel):
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id
        self.sent_messages: list[str] = []

    async def send(self, content: str) -> None:
        self.sent_messages.append(content)


class _FakeGuild:
    def __init__(self, guild_id: int, channel: _FakeChannel) -> None:
        self.id = guild_id
        self._channel = channel

    def get_channel(self, channel_id: int):
        return self._channel


class _FakeBot:
    def __init__(self, guild: _FakeGuild) -> None:
        self._guild = guild

    def get_guild(self, guild_id: int):
        return self._guild


@pytest.fixture
async def server_rss():
    async def handler(request):
        return web.Response(text=RSS_DI_ESEMPIO, content_type="application/xml")

    app = web.Application()
    app.router.add_get("/feed.rss", handler)
    server = TestServer(app)
    await server.start_server()
    yield server
    await server.close()


@pytest.mark.asyncio
async def test_tick_scarica_e_pubblica_le_voci_nuove(clean_db, server_rss):
    import core.feed_watcher as feed_watcher_module

    repo = FeedSubscriptionRepository(pool_provider=lambda: clean_db)
    feed_watcher_module.feed_subscription_repo = repo

    url_feed = f"http://{server_rss.host}:{server_rss.port}/feed.rss"
    await repo.add_subscription(
        guild_id=100, channel_id=500, feed_url=url_feed, label="Esempio", created_by=1
    )

    canale = _FakeChannel(500)
    bot = _FakeBot(_FakeGuild(100, canale))
    servizio = FeedWatcherService()

    try:
        # Primo tick: nessun last_seen precedente -> non deve
        # pubblicare nulla, solo memorizzare la voce più recente.
        await servizio.tick(bot)
        assert canale.sent_messages == []

        sottoscrizioni = await repo.list_subscriptions(100)
        assert sottoscrizioni[0].last_seen_entry_id == "post-2"
    finally:
        await servizio.close()


@pytest.mark.asyncio
async def test_tick_pubblica_solo_le_voci_arrivate_dopo(clean_db, server_rss):
    import core.feed_watcher as feed_watcher_module

    repo = FeedSubscriptionRepository(pool_provider=lambda: clean_db)
    feed_watcher_module.feed_subscription_repo = repo

    url_feed = f"http://{server_rss.host}:{server_rss.port}/feed.rss"
    subscription_id = await repo.add_subscription(
        guild_id=100, channel_id=500, feed_url=url_feed, label="Esempio", created_by=1
    )
    # Simula che "post-1" (il più vecchio) fosse già l'ultimo visto -
    # "post-2" deve risultare nuovo.
    await repo.update_last_seen(subscription_id, entry_id="post-1")

    canale = _FakeChannel(500)
    bot = _FakeBot(_FakeGuild(100, canale))
    servizio = FeedWatcherService()

    try:
        await servizio.tick(bot)

        assert len(canale.sent_messages) == 1
        assert "Nuovo post" in canale.sent_messages[0]
        assert "https://esempio.com/post2" in canale.sent_messages[0]
        assert "Post vecchio" not in canale.sent_messages[0]
    finally:
        await servizio.close()


@pytest.mark.asyncio
async def test_tick_canale_non_raggiungibile_non_solleva(clean_db, server_rss):
    import core.feed_watcher as feed_watcher_module

    repo = FeedSubscriptionRepository(pool_provider=lambda: clean_db)
    feed_watcher_module.feed_subscription_repo = repo

    url_feed = f"http://{server_rss.host}:{server_rss.port}/feed.rss"
    subscription_id = await repo.add_subscription(
        guild_id=100, channel_id=999, feed_url=url_feed, label="Esempio", created_by=1
    )
    await repo.update_last_seen(subscription_id, entry_id="post-1")

    bot = _FakeBot(_FakeGuild(100, channel=None))  # canale mai trovato
    servizio = FeedWatcherService()

    try:
        await servizio.tick(bot)  # non deve sollevare
    finally:
        await servizio.close()


@pytest.mark.asyncio
async def test_tick_feed_irraggiungibile_non_solleva(clean_db):
    import core.feed_watcher as feed_watcher_module

    repo = FeedSubscriptionRepository(pool_provider=lambda: clean_db)
    feed_watcher_module.feed_subscription_repo = repo

    # Porta quasi certamente chiusa: nessun server in ascolto lì.
    await repo.add_subscription(
        guild_id=100, channel_id=500, feed_url="http://127.0.0.1:1/inesistente",
        label="Esempio", created_by=1,
    )

    canale = _FakeChannel(500)
    bot = _FakeBot(_FakeGuild(100, canale))
    servizio = FeedWatcherService()

    try:
        await servizio.tick(bot)  # non deve sollevare
        assert canale.sent_messages == []
    finally:
        await servizio.close()
