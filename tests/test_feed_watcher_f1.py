"""
tests/test_feed_watcher_f1.py
=================================
Issue #67, voci 11.4 (modulo spento) e 11.5 (elemento visto sparito dal
feed) per core/feed_watcher.py. Server aiohttp vero in locale.
"""

from datetime import datetime, timezone

import discord
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

import core.feed_watcher as modulo
from core.feed_watcher import FeedWatcherService
from core.repositories.feed_subscription_repo import FeedSubscriptionRepository
from tests.test_feed_parsing_logic import RSS_CON_DATE
from tests.support.alert_finti import repo_opzioni_finto  # noqa: F401  (autouse)


class _Canale(discord.TextChannel):
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id
        self.sent_messages: list[str] = []

    async def send(self, content: str, **kwargs) -> None:
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
    stato = {"scarichi": 0}

    async def feed(request):
        stato["scarichi"] += 1
        return web.Response(text=RSS_CON_DATE, content_type="application/xml")

    app = web.Application()
    app.router.add_get("/feed.rss", feed)
    srv = TestServer(app)
    await srv.start_server()

    import core.safe_http as safe_http_module

    monkeypatch.setattr(safe_http_module, "_ip_e_bloccato", lambda ip: False)
    monkeypatch.setattr(safe_http_module, "_schema_e_porta_ammessi", lambda url: True)

    repo = FeedSubscriptionRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo, "feed_subscription_repo", repo)
    attivo = {"valore": True}

    async def _attivo(guild_id):
        return attivo["valore"]

    monkeypatch.setattr("core.feed_alert_gate.modulo_alert_attivo", _attivo)
    canale = _Canale(500)
    servizio = FeedWatcherService()
    yield servizio, repo, stato, canale, _Bot(canale), attivo, f"http://{srv.host}:{srv.port}/feed.rss"
    await servizio.close()
    await srv.close()


@pytest.mark.asyncio
async def test_modulo_spento_nessun_messaggio_e_nessuno_scarico(ambiente):
    servizio, repo, stato, canale, bot, attivo, url = ambiente
    sid = await repo.add_subscription(100, 500, url, "X", 1)
    await repo.update_last_seen(sid, "post-1")
    attivo["valore"] = False
    await servizio.tick(bot)
    assert canale.sent_messages == []
    assert stato["scarichi"] == 0
    assert (await repo.list_subscriptions(100))[0].last_seen_entry_id == "post-1"


@pytest.mark.asyncio
async def test_elemento_sparito_non_ripubblica_tutto(ambiente):
    servizio, repo, stato, canale, bot, attivo, url = ambiente
    sid = await repo.add_subscription(100, 500, url, "X", 1)
    # l'ultimo visto ("post-0") non c'e' piu' nel feed; si ricorda la data di post-2
    await repo.update_last_seen(sid, "post-0", datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc))

    await servizio.tick(bot)
    assert len(canale.sent_messages) == 1 and "3" in canale.sent_messages[0]

    await servizio.tick(bot)  # ora l'ultimo visto e' post-3: niente doppioni
    assert len(canale.sent_messages) == 1


@pytest.mark.asyncio
async def test_primo_giro_ricorda_id_e_data_senza_pubblicare(ambiente):
    servizio, repo, stato, canale, bot, attivo, url = ambiente
    await repo.add_subscription(100, 500, url, "X", 1)
    await servizio.tick(bot)
    assert canale.sent_messages == []
    sub = (await repo.list_subscriptions(100))[0]
    assert sub.last_seen_entry_id == "post-3"
    assert sub.last_seen_published == datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
