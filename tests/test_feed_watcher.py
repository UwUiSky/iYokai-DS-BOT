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
from tests.support.alert_finti import repo_opzioni_finto  # noqa: F401  (autouse)

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


@pytest.fixture(autouse=True)
def _modulo_attivo(monkeypatch):
    async def _si(guild_id):
        return True

    monkeypatch.setattr("core.feed_alert_gate.modulo_alert_attivo", _si)


class _FakeChannel(discord.TextChannel):
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id
        self.sent_messages: list[str] = []

    async def send(self, content: str, **kwargs) -> None:
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


def _consenti_server_di_test(monkeypatch) -> None:
    """
    SEC-8: safe_get rifiuta per progetto qualunque IP loopback e
    qualunque porta diversa da 80/443 — esattamente ciò su cui gira
    il server finto di questi test (127.0.0.1, porta casuale).
    Disattivato SOLO qui: verifica che feed_watcher chiami davvero
    safe_get e ne usi il risultato, non la protezione SSRF in sé
    (già coperta da tests/test_safe_http.py).
    """
    import core.safe_http as safe_http_module

    monkeypatch.setattr(safe_http_module, "_ip_e_bloccato", lambda ip: False)
    monkeypatch.setattr(safe_http_module, "_schema_e_porta_ammessi", lambda url: True)


@pytest.mark.asyncio
async def test_tick_scarica_e_pubblica_le_voci_nuove(clean_db, server_rss, monkeypatch):
    _consenti_server_di_test(monkeypatch)
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
async def test_tick_pubblica_solo_le_voci_arrivate_dopo(clean_db, server_rss, monkeypatch):
    _consenti_server_di_test(monkeypatch)
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


# ---------------------------------------------------------------------
# BUG-20: una sottoscrizione rotta non deve fermare tutte le successive.
# ---------------------------------------------------------------------


async def _due_sottoscrizioni(repo, url_rotto: str, url_buono: str) -> None:
    """La prima (id più basso) è quella rotta, la seconda è valida e ha una voce nuova."""
    await repo.add_subscription(
        guild_id=100, channel_id=500, feed_url=url_rotto, label="Rotto", created_by=1
    )
    id_buono = await repo.add_subscription(
        guild_id=100, channel_id=500, feed_url=url_buono, label="Buono", created_by=1
    )
    await repo.update_last_seen(id_buono, entry_id="post-1")


@pytest.mark.asyncio
async def test_tick_url_malformato_non_ferma_le_sottoscrizioni_successive(
    clean_db, server_rss, monkeypatch
):
    _consenti_server_di_test(monkeypatch)
    import core.feed_watcher as feed_watcher_module

    repo = FeedSubscriptionRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(feed_watcher_module, "feed_subscription_repo", repo)

    # Un URL salvato prima che /alerts add lo convalidasse.
    url_buono = f"http://{server_rss.host}:{server_rss.port}/feed.rss"
    await _due_sottoscrizioni(repo, "http://a..b/feed.rss", url_buono)

    canale = _FakeChannel(500)
    await FeedWatcherService().tick(_FakeBot(_FakeGuild(100, canale)))

    assert len(canale.sent_messages) == 1
    assert "Nuovo post" in canale.sent_messages[0]


@pytest.mark.asyncio
async def test_tick_errore_imprevisto_su_una_sottoscrizione_non_ferma_le_altre(
    clean_db, server_rss, monkeypatch
):
    _consenti_server_di_test(monkeypatch)
    import core.feed_watcher as feed_watcher_module

    repo = FeedSubscriptionRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(feed_watcher_module, "feed_subscription_repo", repo)

    url_buono = f"http://{server_rss.host}:{server_rss.port}/feed.rss"
    await _due_sottoscrizioni(repo, "http://rotto.invalid/feed.rss", url_buono)

    class _ServizioConScaricoRotto(FeedWatcherService):
        async def _fetch_feed_text(self, url: str, etag: str | None = None):
            if "rotto.invalid" in url:
                raise RuntimeError("errore imprevisto durante lo scarico")
            return await super()._fetch_feed_text(url, etag)

    canale = _FakeChannel(500)
    await _ServizioConScaricoRotto().tick(_FakeBot(_FakeGuild(100, canale)))

    assert len(canale.sent_messages) == 1
    assert "Nuovo post" in canale.sent_messages[0]


# ---- blocco C: dopo i rifiuti 403 di Discord pausa crescente e poi la sottoscrizione si ferma ----
def test_freni_pausa_crescente_e_disattivazione_al_quinto_rifiuto():
    from core.feed_alert_gate import FreniInvio

    f = FreniInvio()
    k = ("rss", 1)
    assert f.puo_provare(k, 0.0)
    assert f.rifiutato(k, 0.0) is False
    assert not f.puo_provare(k, 599.0) and f.puo_provare(k, 601.0)  # prima pausa: 10 minuti
    assert f.rifiutato(k, 1000.0) is False
    assert not f.puo_provare(k, 1000.0 + 1799.0)  # seconda: 30 minuti
    for _ in range(2):
        assert f.rifiutato(k, 5000.0) is False
    assert f.rifiutato(k, 6000.0) is True  # il quinto: da disattivare
    assert f.puo_provare(k, 6000.0)  # e il conto riparte da zero


def test_un_invio_riuscito_azzera_i_rifiuti():
    from core.feed_alert_gate import FreniInvio

    f = FreniInvio()
    k = ("rss", 2)
    for _ in range(4):
        f.rifiutato(k, 0.0)
    f.riuscito(k)
    assert f.rifiutato(k, 0.0) is False  # dal primo, di nuovo


@pytest.mark.asyncio
async def test_il_feed_con_403_non_si_riprova_ogni_giro_e_alla_fine_va_in_pausa(monkeypatch):
    import discord

    import core.feed_watcher as fw
    from core.feed_alert_gate import FreniInvio

    chiamate, paused = [], []

    class _Resp:
        status, reason = 403, "Forbidden"

    async def invia_403(*a, **k):
        chiamate.append(1)
        raise discord.Forbidden(_Resp(), "Missing Access")

    from core.alert_options_logic import AlertOptions

    async def opz_get(kind, sub_id):
        return AlertOptions()

    async def set_fields(kind, sub_id, guild_id, **campi):
        paused.append(campi)

    async def mai_pericoloso(link):
        return False

    async def aggiorna(*a, **k):
        return None

    monkeypatch.setattr(fw, "invia_alert", invia_403)
    monkeypatch.setattr(fw, "e_link_pericoloso", mai_pericoloso)
    from types import SimpleNamespace

    monkeypatch.setattr(fw, "alert_options_repo", SimpleNamespace(get=opz_get, set_fields=set_fields))
    monkeypatch.setattr(fw, "feed_subscription_repo", SimpleNamespace(update_last_seen=aggiorna))
    orologio = {"t": 1000.0}
    monkeypatch.setattr(fw.time, "monotonic", lambda: orologio["t"])

    canale = discord.TextChannel.__new__(discord.TextChannel)
    guild = type("G", (), {"get_channel": lambda self, cid: canale})()
    bot = type("B", (), {"get_guild": lambda self, gid: guild})()
    sottoscrizione = type("S", (), {
        "id": 7, "guild_id": 1, "channel_id": 2, "feed_url": "x", "label": "L", "message_template": "{titolo}",
        "last_seen_entry_id": "vecchio", "last_seen_published": None,
    })()
    voce = type("V", (), {"entry_id": "nuovo", "link": "https://esempio.org/a", "published": None, "titolo": "T"})()
    monkeypatch.setattr(fw, "find_new_entries", lambda voci, a, b: [voce])
    monkeypatch.setattr(fw, "data_piu_recente", lambda voci: None)
    monkeypatch.setattr(fw, "valori_voce", lambda *a: {})
    monkeypatch.setattr(fw, "render_template", lambda *a: "msg")

    servizio = fw.FeedWatcherService()
    for _ in range(3):  # tre giri a distanza di un minuto: la pausa di 10 minuti li salta
        await servizio._controlla_sottoscrizione(bot, sottoscrizione, [voce])
        orologio["t"] += 60
    assert len(chiamate) == 1, "dopo il primo 403 non si deve richiedere subito"
    for _ in range(FreniInvio.RIFIUTI_PER_DISATTIVARE):
        orologio["t"] += 30000  # oltre ogni pausa
        await servizio._controlla_sottoscrizione(bot, sottoscrizione, [voce])
    assert paused == [{"paused": True}]
