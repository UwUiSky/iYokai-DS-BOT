"""
tests/test_feed_watcher_rete.py
===================================
Issue #67, voce 11.9: due server con lo stesso indirizzo = uno scarico;
ETag: se il feed non e' cambiato (304) non si rifa' il lavoro.
"""

import discord
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

import core.feed_watcher as modulo
import core.safe_http as safe_http
from core.feed_watcher import FeedWatcherService
from core.repositories.feed_subscription_repo import FeedSubscriptionRepository
from tests.test_feed_parsing_logic import RSS_CON_DATE


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


@pytest.fixture
async def ambiente(clean_db, monkeypatch):
    stato = {"scarichi": 0, "con_etag": 0, "testo": RSS_CON_DATE, "etag": '"a"'}

    async def feed(request):
        stato["scarichi"] += 1
        if request.headers.get("If-None-Match") == stato["etag"]:
            stato["con_etag"] += 1
            return web.Response(status=304, headers={"ETag": stato["etag"]})
        return web.Response(text=stato["testo"], content_type="application/xml",
                            headers={"ETag": stato["etag"]})

    app = web.Application()
    app.router.add_get("/feed.rss", feed)
    srv = TestServer(app)
    await srv.start_server()
    monkeypatch.setattr(safe_http, "_ip_e_bloccato", lambda ip: False)
    monkeypatch.setattr(safe_http, "_schema_e_porta_ammessi", lambda url: True)

    repo = FeedSubscriptionRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo, "feed_subscription_repo", repo)

    async def _si(guild_id):
        return True

    monkeypatch.setattr("core.feed_alert_gate.modulo_alert_attivo", _si)
    canale = _Canale(500)
    servizio = FeedWatcherService()
    yield servizio, repo, stato, canale, _Bot(canale), f"http://{srv.host}:{srv.port}/feed.rss"
    await servizio.close()
    await srv.close()


@pytest.mark.asyncio
async def test_due_server_stesso_feed_uno_scarico(ambiente):
    servizio, repo, stato, canale, bot, url = ambiente
    for guild in (100, 200):
        sid = await repo.add_subscription(guild, 500, url, "X", 1)
        await repo.update_last_seen(sid, "post-2")
    await servizio.tick(bot)
    assert stato["scarichi"] == 1
    assert len(canale.sent_messages) == 2  # post-3 in entrambi i server


@pytest.mark.asyncio
async def test_secondo_giro_con_etag_riceve_304_e_non_ripubblica(ambiente):
    servizio, repo, stato, canale, bot, url = ambiente
    sid = await repo.add_subscription(100, 500, url, "X", 1)
    await repo.update_last_seen(sid, "post-2")
    await servizio.tick(bot)
    assert len(canale.sent_messages) == 1
    await servizio.tick(bot)
    assert stato["con_etag"] == 1
    assert len(canale.sent_messages) == 1


@pytest.mark.asyncio
async def test_sottoscrizione_nuova_non_resta_senza_stato_per_colpa_del_304(ambiente):
    servizio, repo, stato, canale, bot, url = ambiente
    await repo.add_subscription(100, 500, url, "X", 1)
    await servizio.tick(bot)  # ricorda l'ETag
    nuova = await repo.add_subscription(200, 500, url, "Y", 1)
    await servizio.tick(bot)  # senza questa regola: 304 e nuova mai inizializzata
    sub = [s for s in await repo.list_subscriptions(200) if s.id == nuova][0]
    assert sub.last_seen_entry_id == "post-3"
