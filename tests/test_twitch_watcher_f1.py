"""
tests/test_twitch_watcher_f1.py
===================================
Issue #67, voci 11.2, 11.3, 11.4, 11.6 per core/twitch_watcher.py:
parametro `first`, blocchi da 100 senza doppioni, token svuotato su
401, modulo spento, modello di messaggio personalizzato.
"""

import discord
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

import core.twitch_watcher as modulo
from core.repositories.twitch_subscription_repo import TwitchSubscriptionRepository
from core.twitch_watcher import TwitchWatcherService


class _Canale(discord.TextChannel):
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id
        self.sent_messages: list[str] = []

    async def send(self, content: str) -> None:
        self.sent_messages.append(content)


class _Guild:
    def __init__(self, canale) -> None:
        self._canale = canale

    def get_channel(self, channel_id: int):
        return self._canale


class _Bot:
    def __init__(self, canale) -> None:
        self._guild = _Guild(canale)

    def get_guild(self, guild_id: int):
        return self._guild


class _ConfigFinta:
    TWITCH_CLIENT_ID = "id-finto"
    TWITCH_CLIENT_SECRET = "secret-finto"


@pytest.fixture
async def server(monkeypatch):
    stato = {"oauth": 0, "richieste": [], "live": set(), "rispondi_401": 0}

    async def oauth(request):
        stato["oauth"] += 1
        return web.json_response({"access_token": f"tok-{stato['oauth']}", "expires_in": 3600})

    async def streams(request):
        stato["richieste"].append(list(request.query.items()))
        if stato["rispondi_401"] > 0:
            stato["rispondi_401"] -= 1
            return web.Response(status=401)
        dati = [
            {"user_login": login, "title": f"Titolo {login}", "game_name": "x"}
            for login in request.query.getall("user_login", [])
            if login in stato["live"]
        ]
        return web.json_response({"data": dati})

    app = web.Application()
    app.router.add_post("/oauth2/token", oauth)
    app.router.add_get("/helix/streams", streams)
    srv = TestServer(app)
    await srv.start_server()
    yield srv, stato
    await srv.close()


@pytest.fixture
def ambiente(clean_db, server, monkeypatch):
    srv, stato = server
    monkeypatch.setattr(modulo, "config", _ConfigFinta())
    repo = TwitchSubscriptionRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo, "twitch_subscription_repo", repo)
    attivo = {"valore": True}

    async def _attivo(guild_id):
        return attivo["valore"]

    monkeypatch.setattr("core.feed_alert_gate.modulo_alert_attivo", _attivo)
    canale = _Canale(500)
    servizio = TwitchWatcherService(
        oauth_url=f"http://{srv.host}:{srv.port}/oauth2/token",
        streams_url=f"http://{srv.host}:{srv.port}/helix/streams",
    )
    return servizio, repo, stato, canale, _Bot(canale), attivo


@pytest.mark.asyncio
async def test_la_richiesta_contiene_first_100(ambiente):
    servizio, repo, stato, canale, bot, _ = ambiente
    await repo.add_subscription(100, 500, "uno", "Uno", 1)
    try:
        await servizio.tick(bot)
    finally:
        await servizio.close()
    assert ("first", "100") in stato["richieste"][0]


@pytest.mark.asyncio
async def test_250_iscrizioni_tre_richieste_senza_doppioni(ambiente):
    servizio, repo, stato, canale, bot, _ = ambiente
    for i in range(250):
        await repo.add_subscription(100, 500, f"login{i}", f"L{i}", 1)
    # stesso streamer seguito anche da un altro server: un solo login nella richiesta
    await repo.add_subscription(200, 500, "login0", "L0 bis", 1)
    try:
        await servizio.tick(bot)
    finally:
        await servizio.close()

    assert len(stato["richieste"]) == 3
    tutti = [v for r in stato["richieste"] for k, v in r if k == "user_login"]
    assert len(tutti) == 250 and len(set(tutti)) == 250
    assert all(len([1 for k, _ in r if k == "user_login"]) <= 100 for r in stato["richieste"])


@pytest.mark.asyncio
async def test_login_doppio_notifica_entrambe_le_iscrizioni(ambiente):
    servizio, repo, stato, canale, bot, _ = ambiente
    await repo.add_subscription(100, 500, "uno", "Uno", 1)
    await repo.add_subscription(200, 500, "uno", "Uno bis", 1)
    stato["live"].add("uno")
    try:
        await servizio.tick(bot)
    finally:
        await servizio.close()
    assert len(canale.sent_messages) == 2


@pytest.mark.asyncio
async def test_401_svuota_il_token_e_il_giro_dopo_ne_chiede_uno_nuovo(ambiente):
    servizio, repo, stato, canale, bot, _ = ambiente
    await repo.add_subscription(100, 500, "uno", "Uno", 1)
    stato["rispondi_401"] = 1
    try:
        await servizio.tick(bot)
        assert stato["oauth"] == 1
        await servizio.tick(bot)
        assert stato["oauth"] == 2
    finally:
        await servizio.close()


@pytest.mark.asyncio
async def test_modulo_spento_nessun_messaggio_e_nessuna_richiesta(ambiente):
    servizio, repo, stato, canale, bot, attivo = ambiente
    await repo.add_subscription(100, 500, "uno", "Uno", 1)
    stato["live"].add("uno")
    attivo["valore"] = False
    try:
        await servizio.tick(bot)
    finally:
        await servizio.close()
    assert canale.sent_messages == []
    assert stato["richieste"] == [] and stato["oauth"] == 0


@pytest.mark.asyncio
async def test_modello_personalizzato_usato_e_segnaposto_ignoto_non_rompe(ambiente):
    servizio, repo, stato, canale, bot, _ = ambiente
    await repo.add_subscription(
        100, 500, "uno", "Uno", 1, live_message_template="LIVE {label} {login} {titolo} {title:>99999999}"
    )
    stato["live"].add("uno")
    try:
        await servizio.tick(bot)
    finally:
        await servizio.close()
    assert canale.sent_messages == ["LIVE Uno uno {titolo} {title:>99999999}"]
