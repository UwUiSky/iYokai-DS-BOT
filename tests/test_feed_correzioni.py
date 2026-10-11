"""
tests/test_feed_correzioni.py
=================================
Issue #67, correzioni dal rapporto del cacciatore-bug: tetto di 25 feed
con richieste vere in parallelo, avanzamento solo dopo l'invio riuscito
(feed, Twitch, YouTube), ETag solo dopo l'elaborazione, data che non
torna indietro, sessione condivisa chiusa al cambio di loop, elenco
con righe lunghe, parametri di videos.list.
"""

import asyncio
from datetime import datetime, timezone

import discord
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

import cogs.utility.feed_alerts as cog_modulo
import core.feed_watcher as modulo
import core.safe_http as safe_http
from core.feed_watcher import FeedWatcherService
from core.repositories.feed_subscription_repo import FeedSubscriptionRepository
from tests.test_feed_parsing_logic import RSS_CON_DATE


class _Risposta:
    status = 403
    reason = "Forbidden"


class _Canale(discord.TextChannel):
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id
        self.sent_messages: list[str] = []
        self.fallisci = False

    async def send(self, content: str) -> None:
        if self.fallisci:
            raise discord.Forbidden(_Risposta(), "Missing Permissions")
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


def _rss(*ids_giorni):
    voci = "".join(
        f"<item><title>{i}</title><link>https://e.com/{i}</link><guid>post-{i}</guid>"
        f"<pubDate>{giorno:02d} Oct 2026 12:00:00 GMT</pubDate></item>"
        for i, giorno in ids_giorni
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{voci}</channel></rss>'


@pytest.fixture
async def ambiente(clean_db, monkeypatch):
    stato = {"testo": RSS_CON_DATE, "etag": '"a"', "scarichi": 0, "con_etag": 0}

    async def feed(request):
        stato["scarichi"] += 1
        if stato["etag"] and request.headers.get("If-None-Match") == stato["etag"]:
            stato["con_etag"] += 1
            return web.Response(status=304, headers={"ETag": stato["etag"]})
        intest = {"ETag": stato["etag"]} if stato["etag"] else {}
        return web.Response(text=stato["testo"], content_type="application/xml", headers=intest)

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
    yield servizio, repo, stato, canale, _Bot(canale), f"http://{srv.host}:{srv.port}/feed.rss", clean_db
    await servizio.close()
    await srv.close()


# --- P2: tetto con richieste in parallelo vere -------------------------

@pytest.mark.asyncio
async def test_tetto_25_con_5_richieste_in_parallelo_da_24(ambiente):
    _, repo, *_ = ambiente
    for i in range(24):
        await repo.add_subscription(100, 500, f"https://e.com/{i}", "x", 1)
    esiti = await asyncio.gather(
        *(
            repo.add_subscription(100, 500, f"https://e.com/n{k}", "n", 1, max_per_guild=25)
            for k in range(5)
        )
    )
    assert sum(1 for e in esiti if e is not None) == 1
    assert len(await repo.list_subscriptions(100)) == 25


@pytest.mark.asyncio
async def test_tetto_e_per_server(ambiente):
    _, repo, *_ = ambiente
    for i in range(25):
        await repo.add_subscription(100, 500, f"https://e.com/{i}", "x", 1)
    assert await repo.add_subscription(100, 500, "https://e.com/z", "z", 1, max_per_guild=25) is None
    assert await repo.add_subscription(200, 500, "https://e.com/z", "z", 1, max_per_guild=25)


# --- P3: avanzare solo dopo l'invio ------------------------------------

@pytest.mark.asyncio
async def test_invio_fallito_non_perde_le_voci(ambiente):
    servizio, repo, stato, canale, bot, url, _ = ambiente
    sid = await repo.add_subscription(100, 500, url, "X", 1)
    await repo.update_last_seen(sid, "post-1", datetime(2026, 10, 1, 12, tzinfo=timezone.utc))
    canale.fallisci = True
    await servizio.tick(bot)
    assert (await repo.list_subscriptions(100))[0].last_seen_entry_id == "post-1"

    canale.fallisci = False
    await servizio.tick(bot)
    assert [m for m in canale.sent_messages if "2" in m or "3" in m] and len(canale.sent_messages) == 2
    assert (await repo.list_subscriptions(100))[0].last_seen_entry_id == "post-3"
    await servizio.tick(bot)
    assert len(canale.sent_messages) == 2  # nessun doppione


@pytest.mark.asyncio
async def test_canale_non_in_cache_non_perde_le_voci(ambiente):
    servizio, repo, stato, canale, bot, url, _ = ambiente
    sid = await repo.add_subscription(100, 500, url, "X", 1)
    await repo.update_last_seen(sid, "post-1", datetime(2026, 10, 1, 12, tzinfo=timezone.utc))

    class _BotSenzaCanale:
        def get_guild(self, guild_id):
            return None

    await servizio.tick(_BotSenzaCanale())
    assert (await repo.list_subscriptions(100))[0].last_seen_entry_id == "post-1"
    await servizio.tick(bot)
    assert len(canale.sent_messages) == 2


# --- P4: ETag solo dopo l'elaborazione ---------------------------------

@pytest.mark.asyncio
async def test_etag_non_ricordato_se_l_elaborazione_solleva(ambiente, monkeypatch):
    servizio, repo, stato, canale, bot, url, _ = ambiente
    sid = await repo.add_subscription(100, 500, url, "X", 1)
    await repo.update_last_seen(sid, "post-1", datetime(2026, 10, 1, 12, tzinfo=timezone.utc))

    originale = repo.update_last_seen
    chiamate = {"n": 0}

    async def rotto_una_volta(*a, **k):
        chiamate["n"] += 1
        if chiamate["n"] == 1:
            raise RuntimeError("db giu'")
        return await originale(*a, **k)

    monkeypatch.setattr(repo, "update_last_seen", rotto_una_volta)
    await servizio.tick(bot)  # solleva: l'ETag non si ricorda
    await servizio.tick(bot)  # deve riscaricare (200), non ricevere 304
    assert stato["con_etag"] == 0
    assert len(canale.sent_messages) >= 1


@pytest.mark.asyncio
async def test_etag_cambiato_o_assente_riscarica(ambiente):
    servizio, repo, stato, canale, bot, url, _ = ambiente
    sid = await repo.add_subscription(100, 500, url, "X", 1)
    await repo.update_last_seen(sid, "post-3", datetime(2026, 10, 3, 12, tzinfo=timezone.utc))
    await servizio.tick(bot)
    stato["etag"] = '"b"'
    stato["testo"] = _rss((4, 4), (3, 3))
    await servizio.tick(bot)  # etag diverso: 200 con il contenuto nuovo
    assert stato["con_etag"] == 0 and len(canale.sent_messages) == 1
    stato["etag"] = None  # il server non manda piu' ETag: sempre riscarico
    await servizio.tick(bot)
    await servizio.tick(bot)
    assert stato["con_etag"] == 0


# --- P6bis: la data non torna indietro ---------------------------------

@pytest.mark.asyncio
async def test_copia_vecchia_del_feed_non_fa_ripubblicare(ambiente):
    servizio, repo, stato, canale, bot, url, _ = ambiente
    sid = await repo.add_subscription(100, 500, url, "X", 1)
    await repo.update_last_seen(sid, "post-2", datetime(2026, 10, 2, 12, tzinfo=timezone.utc))
    stato["etag"] = None
    stato["testo"] = _rss((1, 1))  # copia vecchia, mirror in ritardo
    await servizio.tick(bot)
    stato["testo"] = RSS_CON_DATE
    await servizio.tick(bot)
    assert [m for m in canale.sent_messages if "post" in m or "3" in m]
    assert len(canale.sent_messages) == 1  # solo post-3, mai post-2 o post-1 di nuovo
    sub = (await repo.list_subscriptions(100))[0]
    assert sub.last_seen_published == datetime(2026, 10, 3, 12, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_update_last_seen_tiene_la_data_massima(ambiente):
    _, repo, *_ = ambiente
    sid = await repo.add_subscription(100, 500, "https://e.com/f", "X", 1)
    await repo.update_last_seen(sid, "b", datetime(2026, 10, 5, tzinfo=timezone.utc))
    await repo.update_last_seen(sid, "a", datetime(2026, 10, 1, tzinfo=timezone.utc))
    await repo.update_last_seen(sid, "a", None)
    assert (await repo.list_subscriptions(100))[0].last_seen_published == datetime(
        2026, 10, 5, tzinfo=timezone.utc
    )


# --- P6: elenco con righe lunghe ---------------------------------------

def test_elenco_con_riga_lunga_in_testa_mostra_comunque_gli_id():
    righe = ["`RSS-1` **A** → <#1>\n  https://e.com/" + "x" * 5000] + [
        f"`RSS-{i}` **F{i}** → <#1>\n  https://e.com/{i}" for i in range(2, 6)
    ]
    testo = cog_modulo._elenco_tagliato(righe)
    assert "RSS-1" in testo and "RSS-5" in testo
    assert len(testo) <= 4096


# --- P5: sessione condivisa chiusa al cambio di loop --------------------

def test_sessione_vecchia_chiusa_quando_cambia_il_loop():
    async def crea():
        return await safe_http._sessione_condivisa()

    vecchia = asyncio.run(crea())
    assert not vecchia.closed
    asyncio.run(crea())  # nuovo loop
    assert vecchia.closed
    asyncio.run(safe_http.chiudi_sessione_condivisa())
