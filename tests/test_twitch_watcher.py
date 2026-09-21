"""
tests/test_twitch_watcher.py
================================
Test di TwitchWatcherService con un server aiohttp VERO in locale
(aiohttp.test_utils), che imita la FORMA dell'API Twitch (OAuth
Client Credentials + Get Streams) — non un mock della sessione HTTP.
Credenziali fittizie ("simulazione", come richiesto esplicitamente
dall'utente): non validano contro Twitch vero, solo contro questo
server finto.
"""

import discord
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from core.twitch_watcher import TwitchWatcherService
from core.repositories.twitch_subscription_repo import TwitchSubscriptionRepository


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
async def server_twitch_finto():
    stato = {"chiamate_oauth": 0, "streamer_live": set()}

    async def handler_oauth(request):
        stato["chiamate_oauth"] += 1
        return web.json_response(
            {"access_token": "token-finto-123", "expires_in": 3600, "token_type": "bearer"}
        )

    async def handler_streams(request):
        auth = request.headers.get("Authorization", "")
        assert auth == "Bearer token-finto-123"
        logins_richiesti = request.query.getall("user_login", [])
        dati = [
            {"user_login": login, "title": f"Stream di {login}", "game_name": "Just Chatting"}
            for login in logins_richiesti
            if login in stato["streamer_live"]
        ]
        return web.json_response({"data": dati, "pagination": {}})

    app = web.Application()
    app.router.add_post("/oauth2/token", handler_oauth)
    app.router.add_get("/helix/streams", handler_streams)
    server = TestServer(app)
    await server.start_server()
    yield server, stato
    await server.close()


@pytest.mark.asyncio
async def test_tick_rileva_streamer_appena_andato_live(clean_db, server_twitch_finto, monkeypatch):
    server, stato = server_twitch_finto
    import core.twitch_watcher as twitch_watcher_module

    class _ConfigFinta:
        TWITCH_CLIENT_ID = "id-finto"
        TWITCH_CLIENT_SECRET = "secret-finto"

    monkeypatch.setattr(twitch_watcher_module, "config", _ConfigFinta())

    repo = TwitchSubscriptionRepository(pool_provider=lambda: clean_db)
    twitch_watcher_module.twitch_subscription_repo = repo

    await repo.add_subscription(100, 500, "streamera", "Streamer A", 1)
    stato["streamer_live"].add("streamera")

    canale = _FakeChannel(500)
    bot = _FakeBot(_FakeGuild(100, canale))
    servizio = TwitchWatcherService(
        oauth_url=f"http://{server.host}:{server.port}/oauth2/token",
        streams_url=f"http://{server.host}:{server.port}/helix/streams",
    )

    try:
        await servizio.tick(bot)

        assert len(canale.sent_messages) == 1
        assert "diretta" in canale.sent_messages[0].lower()

        sottoscrizioni = await repo.list_subscriptions(100)
        assert sottoscrizioni[0].last_known_live is True
    finally:
        await servizio.close()


@pytest.mark.asyncio
async def test_tick_rileva_streamer_appena_andato_offline(clean_db, server_twitch_finto, monkeypatch):
    server, stato = server_twitch_finto
    import core.twitch_watcher as twitch_watcher_module

    class _ConfigFinta:
        TWITCH_CLIENT_ID = "id-finto"
        TWITCH_CLIENT_SECRET = "secret-finto"

    monkeypatch.setattr(twitch_watcher_module, "config", _ConfigFinta())

    repo = TwitchSubscriptionRepository(pool_provider=lambda: clean_db)
    twitch_watcher_module.twitch_subscription_repo = repo

    subscription_id = await repo.add_subscription(100, 500, "streamera", "Streamer A", 1)
    await repo.update_last_known_live(subscription_id, is_live=True)
    # stato["streamer_live"] resta vuoto -> non è più live

    canale = _FakeChannel(500)
    bot = _FakeBot(_FakeGuild(100, canale))
    servizio = TwitchWatcherService(
        oauth_url=f"http://{server.host}:{server.port}/oauth2/token",
        streams_url=f"http://{server.host}:{server.port}/helix/streams",
    )

    try:
        await servizio.tick(bot)

        assert len(canale.sent_messages) == 1
        assert "terminato" in canale.sent_messages[0].lower()

        sottoscrizioni = await repo.list_subscriptions(100)
        assert sottoscrizioni[0].last_known_live is False
    finally:
        await servizio.close()


@pytest.mark.asyncio
async def test_tick_nessun_cambiamento_non_pubblica_nulla(clean_db, server_twitch_finto, monkeypatch):
    server, stato = server_twitch_finto
    import core.twitch_watcher as twitch_watcher_module

    class _ConfigFinta:
        TWITCH_CLIENT_ID = "id-finto"
        TWITCH_CLIENT_SECRET = "secret-finto"

    monkeypatch.setattr(twitch_watcher_module, "config", _ConfigFinta())

    repo = TwitchSubscriptionRepository(pool_provider=lambda: clean_db)
    twitch_watcher_module.twitch_subscription_repo = repo

    # Già offline, e resta offline (non aggiunto a streamer_live).
    await repo.add_subscription(100, 500, "streamera", "Streamer A", 1)

    canale = _FakeChannel(500)
    bot = _FakeBot(_FakeGuild(100, canale))
    servizio = TwitchWatcherService(
        oauth_url=f"http://{server.host}:{server.port}/oauth2/token",
        streams_url=f"http://{server.host}:{server.port}/helix/streams",
    )

    try:
        await servizio.tick(bot)

        assert canale.sent_messages == []
    finally:
        await servizio.close()


@pytest.mark.asyncio
async def test_token_viene_riusato_tra_due_tick_senza_richiederlo_di_nuovo(
    clean_db, server_twitch_finto, monkeypatch
):
    server, stato = server_twitch_finto
    import core.twitch_watcher as twitch_watcher_module

    class _ConfigFinta:
        TWITCH_CLIENT_ID = "id-finto"
        TWITCH_CLIENT_SECRET = "secret-finto"

    monkeypatch.setattr(twitch_watcher_module, "config", _ConfigFinta())

    repo = TwitchSubscriptionRepository(pool_provider=lambda: clean_db)
    twitch_watcher_module.twitch_subscription_repo = repo

    await repo.add_subscription(100, 500, "streamera", "Streamer A", 1)

    canale = _FakeChannel(500)
    bot = _FakeBot(_FakeGuild(100, canale))
    servizio = TwitchWatcherService(
        oauth_url=f"http://{server.host}:{server.port}/oauth2/token",
        streams_url=f"http://{server.host}:{server.port}/helix/streams",
    )

    try:
        await servizio.tick(bot)
        await servizio.tick(bot)

        # Un token valido per un'ora non deve essere richiesto una
        # seconda volta al secondo tick, appena 90 secondi dopo.
        assert stato["chiamate_oauth"] == 1
    finally:
        await servizio.close()


@pytest.mark.asyncio
async def test_senza_credenziali_configurate_salta_il_tick_senza_sollevare(clean_db, monkeypatch):
    import core.twitch_watcher as twitch_watcher_module

    class _ConfigVuota:
        TWITCH_CLIENT_ID = ""
        TWITCH_CLIENT_SECRET = ""

    monkeypatch.setattr(twitch_watcher_module, "config", _ConfigVuota())

    repo = TwitchSubscriptionRepository(pool_provider=lambda: clean_db)
    twitch_watcher_module.twitch_subscription_repo = repo

    await repo.add_subscription(100, 500, "streamera", "Streamer A", 1)

    canale = _FakeChannel(500)
    bot = _FakeBot(_FakeGuild(100, canale))
    servizio = TwitchWatcherService()

    try:
        await servizio.tick(bot)  # non deve sollevare
        assert canale.sent_messages == []
    finally:
        await servizio.close()
