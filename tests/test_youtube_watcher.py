"""
tests/test_youtube_watcher.py
=================================
Test di YoutubeWatcherService con un server aiohttp VERO in locale
(aiohttp.test_utils), che imita la FORMA della YouTube Data API
(search.list) — non un mock della sessione HTTP. Stesso schema di
tests/test_twitch_watcher.py, ma senza il livello OAuth (la Data API
usa una semplice API key come parametro di query).
"""

import discord
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from core.youtube_watcher import YoutubeWatcherService
from core.repositories.youtube_subscription_repo import YoutubeSubscriptionRepository


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
async def server_youtube_finto():
    stato = {"chiamate": 0, "canali_live": {}}  # channel_id -> (video_id, title)

    async def handler_search(request):
        stato["chiamate"] += 1
        assert request.query.get("key") == "chiave-finta"
        channel_id = request.query.get("channelId")
        if channel_id in stato["canali_live"]:
            video_id, titolo = stato["canali_live"][channel_id]
            items = [{"id": {"videoId": video_id}, "snippet": {"title": titolo}}]
        else:
            items = []
        return web.json_response({"items": items})

    app = web.Application()
    app.router.add_get("/search", handler_search)
    server = TestServer(app)
    await server.start_server()
    yield server, stato
    await server.close()


@pytest.mark.asyncio
async def test_tick_rileva_canale_appena_andato_live(clean_db, server_youtube_finto, monkeypatch):
    server, stato = server_youtube_finto
    import core.youtube_watcher as youtube_watcher_module

    class _ConfigFinta:
        YOUTUBE_API_KEY = "chiave-finta"

    monkeypatch.setattr(youtube_watcher_module, "config", _ConfigFinta())

    repo = YoutubeSubscriptionRepository(pool_provider=lambda: clean_db)
    youtube_watcher_module.youtube_subscription_repo = repo

    await repo.add_subscription(100, 500, "UCabc", "Canale A", 1)
    stato["canali_live"]["UCabc"] = ("video123", "Diretta di prova")

    canale = _FakeChannel(500)
    bot = _FakeBot(_FakeGuild(100, canale))
    servizio = YoutubeWatcherService(search_url=f"http://{server.host}:{server.port}/search")

    try:
        await servizio.tick(bot)

        assert len(canale.sent_messages) == 1
        assert "diretta" in canale.sent_messages[0].lower()
        assert "video123" in canale.sent_messages[0]

        sottoscrizioni = await repo.list_subscriptions(100)
        assert sottoscrizioni[0].last_known_live is True
    finally:
        await servizio.close()


@pytest.mark.asyncio
async def test_tick_rileva_canale_appena_andato_offline(clean_db, server_youtube_finto, monkeypatch):
    server, stato = server_youtube_finto
    import core.youtube_watcher as youtube_watcher_module

    class _ConfigFinta:
        YOUTUBE_API_KEY = "chiave-finta"

    monkeypatch.setattr(youtube_watcher_module, "config", _ConfigFinta())

    repo = YoutubeSubscriptionRepository(pool_provider=lambda: clean_db)
    youtube_watcher_module.youtube_subscription_repo = repo

    subscription_id = await repo.add_subscription(100, 500, "UCabc", "Canale A", 1)
    await repo.update_last_known_live(subscription_id, is_live=True)
    # stato["canali_live"] resta vuoto -> non è più live

    canale = _FakeChannel(500)
    bot = _FakeBot(_FakeGuild(100, canale))
    servizio = YoutubeWatcherService(search_url=f"http://{server.host}:{server.port}/search")

    try:
        await servizio.tick(bot)

        assert len(canale.sent_messages) == 1
        assert "terminato" in canale.sent_messages[0].lower()

        sottoscrizioni = await repo.list_subscriptions(100)
        assert sottoscrizioni[0].last_known_live is False
    finally:
        await servizio.close()


@pytest.mark.asyncio
async def test_tick_nessun_cambiamento_non_pubblica_nulla(clean_db, server_youtube_finto, monkeypatch):
    server, stato = server_youtube_finto
    import core.youtube_watcher as youtube_watcher_module

    class _ConfigFinta:
        YOUTUBE_API_KEY = "chiave-finta"

    monkeypatch.setattr(youtube_watcher_module, "config", _ConfigFinta())

    repo = YoutubeSubscriptionRepository(pool_provider=lambda: clean_db)
    youtube_watcher_module.youtube_subscription_repo = repo

    # Già offline, e resta offline (non aggiunto a canali_live).
    await repo.add_subscription(100, 500, "UCabc", "Canale A", 1)

    canale = _FakeChannel(500)
    bot = _FakeBot(_FakeGuild(100, canale))
    servizio = YoutubeWatcherService(search_url=f"http://{server.host}:{server.port}/search")

    try:
        await servizio.tick(bot)

        assert canale.sent_messages == []
    finally:
        await servizio.close()


@pytest.mark.asyncio
async def test_senza_chiave_configurata_salta_il_tick_senza_sollevare(clean_db, monkeypatch):
    import core.youtube_watcher as youtube_watcher_module

    class _ConfigVuota:
        YOUTUBE_API_KEY = ""

    monkeypatch.setattr(youtube_watcher_module, "config", _ConfigVuota())

    repo = YoutubeSubscriptionRepository(pool_provider=lambda: clean_db)
    youtube_watcher_module.youtube_subscription_repo = repo

    await repo.add_subscription(100, 500, "UCabc", "Canale A", 1)

    canale = _FakeChannel(500)
    bot = _FakeBot(_FakeGuild(100, canale))
    servizio = YoutubeWatcherService()

    try:
        await servizio.tick(bot)  # non deve sollevare
        assert canale.sent_messages == []
    finally:
        await servizio.close()
