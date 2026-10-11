"""
tests/test_youtube_watcher.py
=================================
YouTube live secondo D5 (issue #67, voci 11.1, 11.4, 11.6): per ogni
canale si legge il feed RSS (zero quota), poi UNA chiamata
`videos.list` per gruppo di 50 ID e si guarda `liveBroadcastContent`.
Server aiohttp VERO in locale che imita il feed Atom di YouTube e
videos.list; chiave API fittizia.
"""

import discord
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

import core.youtube_watcher as modulo
from core.repositories.youtube_subscription_repo import YoutubeSubscriptionRepository
from core.youtube_watcher import YoutubeWatcherService


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
    YOUTUBE_API_KEY = "chiave-finta"


def _atom(canale: str, n_video: int = 2) -> str:
    voci = "".join(
        f"""<entry><id>yt:video:{canale}_v{i}</id><title>Video {i} di {canale}</title>
        <link rel="alternate" href="https://www.youtube.com/watch?v={canale}_v{i}"/></entry>"""
        for i in range(n_video)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<feed xmlns="http://www.w3.org/2005/Atom">{voci}</feed>'
    )


@pytest.fixture
async def server():
    stato = {"rss": [], "videos": [], "live": set(), "n_video": 2, "rss_rotto": set()}

    async def rss(request):
        canale = request.query["channel_id"]
        stato["rss"].append(canale)
        if canale in stato["rss_rotto"]:
            return web.Response(status=500)
        return web.Response(text=_atom(canale, stato["n_video"]), content_type="application/atom+xml")

    async def videos(request):
        assert request.query["key"] == "chiave-finta"
        stato.setdefault("parametri", []).append(set(request.query.keys()))
        if "maxResults" in request.query:
            # l'API vera rifiuta maxResults insieme a id
            return web.json_response({"error": "maxResults non ammesso con id"}, status=400)
        ids = request.query["id"].split(",")
        stato["videos"].append(ids)
        items = [
            {
                "id": vid,
                "snippet": {
                    "title": f"Titolo {vid}",
                    "liveBroadcastContent": "live" if vid in stato["live"] else "none",
                },
            }
            for vid in ids
        ]
        return web.json_response({"items": items})

    app = web.Application()
    app.router.add_get("/feeds/videos.xml", rss)
    app.router.add_get("/videos", videos)
    srv = TestServer(app)
    await srv.start_server()
    yield srv, stato
    await srv.close()


@pytest.fixture
def ambiente(clean_db, server, monkeypatch):
    srv, stato = server
    # SEC-8: il server finto e' su loopback e porta casuale; la protezione
    # SSRF e' provata in test_safe_http.py.
    import core.safe_http as safe_http_module

    monkeypatch.setattr(safe_http_module, "_ip_e_bloccato", lambda ip: False)
    monkeypatch.setattr(safe_http_module, "_schema_e_porta_ammessi", lambda url: True)

    monkeypatch.setattr(modulo, "config", _ConfigFinta())
    repo = YoutubeSubscriptionRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo, "youtube_subscription_repo", repo)
    attivo = {"valore": True}

    async def _attivo(guild_id):
        return attivo["valore"]

    monkeypatch.setattr("core.feed_alert_gate.modulo_alert_attivo", _attivo)
    canale = _Canale(500)
    base = f"http://{srv.host}:{srv.port}"
    servizio = YoutubeWatcherService(
        videos_url=f"{base}/videos",
        rss_url_template=base + "/feeds/videos.xml?channel_id={channel_id}",
    )
    return servizio, repo, stato, canale, _Bot(canale), attivo


@pytest.mark.asyncio
async def test_dieci_canali_una_sola_chiamata_videos_list(ambiente):
    servizio, repo, stato, canale, bot, _ = ambiente
    for i in range(10):
        await repo.add_subscription(100, 500, f"UC{i}", f"C{i}", 1)
    try:
        await servizio.tick(bot)
    finally:
        await servizio.close()
    assert len(stato["videos"]) == 1
    assert len(stato["videos"][0]) == 20  # 10 canali x 2 video
    assert sorted(stato["rss"]) == sorted(f"UC{i}" for i in range(10))


@pytest.mark.asyncio
async def test_videos_list_usa_id_senza_maxresults(ambiente):
    servizio, repo, stato, canale, bot, _ = ambiente
    await repo.add_subscription(100, 500, "UCa", "A", 1)
    stato["live"].add("UCa_v0")
    try:
        await servizio.tick(bot)
    finally:
        await servizio.close()
    assert stato["parametri"] == [{"key", "id", "part"}]
    assert len(canale.sent_messages) == 1  # con maxResults l'API risponde 400


@pytest.mark.asyncio
async def test_invio_fallito_ritenta_al_giro_dopo(ambiente):
    servizio, repo, stato, canale, bot, _ = ambiente
    await repo.add_subscription(100, 500, "UCa", "A", 1)
    stato["live"].add("UCa_v0")
    originale = canale.send

    async def rotto(content):
        raise discord.Forbidden(type("R", (), {"status": 403, "reason": "x"})(), "no")

    canale.send = rotto
    try:
        await servizio.tick(bot)
        assert (await repo.list_subscriptions(100))[0].last_known_live is False
        canale.send = originale
        await servizio.tick(bot)
        assert len(canale.sent_messages) == 1
        assert (await repo.list_subscriptions(100))[0].last_known_live is True
    finally:
        await servizio.close()


@pytest.mark.asyncio
async def test_oltre_50_id_si_divide_in_gruppi_da_50(ambiente):
    servizio, repo, stato, canale, bot, _ = ambiente
    stato["n_video"] = 5
    for i in range(12):  # 60 ID
        await repo.add_subscription(100, 500, f"UC{i}", f"C{i}", 1)
    try:
        await servizio.tick(bot)
    finally:
        await servizio.close()
    assert [len(g) for g in stato["videos"]] == [50, 10]


@pytest.mark.asyncio
async def test_stesso_canale_in_due_server_un_solo_scarico_e_due_messaggi(ambiente):
    servizio, repo, stato, canale, bot, _ = ambiente
    await repo.add_subscription(100, 500, "UCa", "A", 1)
    await repo.add_subscription(200, 500, "UCa", "A bis", 1)
    stato["live"].add("UCa_v0")
    try:
        await servizio.tick(bot)
    finally:
        await servizio.close()
    assert stato["rss"] == ["UCa"]
    assert len(stato["videos"]) == 1 and len(stato["videos"][0]) == 2
    assert len(canale.sent_messages) == 2


@pytest.mark.asyncio
async def test_canale_appena_andato_live(ambiente):
    servizio, repo, stato, canale, bot, _ = ambiente
    await repo.add_subscription(100, 500, "UCa", "Canale A", 1)
    stato["live"].add("UCa_v1")
    try:
        await servizio.tick(bot)
        assert len(canale.sent_messages) == 1
        assert "diretta" in canale.sent_messages[0].lower()
        assert "UCa_v1" in canale.sent_messages[0]
        assert (await repo.list_subscriptions(100))[0].last_known_live is True
        await servizio.tick(bot)  # nessun cambiamento: niente doppioni
        assert len(canale.sent_messages) == 1
    finally:
        await servizio.close()


@pytest.mark.asyncio
async def test_canale_appena_andato_offline(ambiente):
    servizio, repo, stato, canale, bot, _ = ambiente
    sid = await repo.add_subscription(100, 500, "UCa", "Canale A", 1)
    await repo.update_last_known_live(sid, True)
    try:
        await servizio.tick(bot)
        assert len(canale.sent_messages) == 1
        assert "terminato" in canale.sent_messages[0].lower()
        assert (await repo.list_subscriptions(100))[0].last_known_live is False
    finally:
        await servizio.close()


@pytest.mark.asyncio
async def test_feed_rotto_non_cambia_lo_stato(ambiente):
    servizio, repo, stato, canale, bot, _ = ambiente
    sid = await repo.add_subscription(100, 500, "UCa", "Canale A", 1)
    await repo.update_last_known_live(sid, True)
    stato["rss_rotto"].add("UCa")
    try:
        await servizio.tick(bot)
    finally:
        await servizio.close()
    assert canale.sent_messages == []
    assert (await repo.list_subscriptions(100))[0].last_known_live is True


@pytest.mark.asyncio
async def test_modulo_spento_nessun_messaggio_e_nessuna_quota(ambiente):
    servizio, repo, stato, canale, bot, attivo = ambiente
    await repo.add_subscription(100, 500, "UCa", "Canale A", 1)
    stato["live"].add("UCa_v0")
    attivo["valore"] = False
    try:
        await servizio.tick(bot)
    finally:
        await servizio.close()
    assert canale.sent_messages == []
    assert stato["rss"] == [] and stato["videos"] == []


@pytest.mark.asyncio
async def test_modello_personalizzato_usato_e_segnaposto_ignoto_non_rompe(ambiente):
    servizio, repo, stato, canale, bot, _ = ambiente
    await repo.add_subscription(
        100, 500, "UCa", "A", 1, live_message_template="LIVE {label} {video_id} {titolo}"
    )
    stato["live"].add("UCa_v0")
    try:
        await servizio.tick(bot)
    finally:
        await servizio.close()
    assert canale.sent_messages == ["LIVE A UCa_v0 {titolo}"]


@pytest.mark.asyncio
async def test_senza_chiave_configurata_salta_il_tick_senza_sollevare(clean_db, monkeypatch):
    class _ConfigVuota:
        YOUTUBE_API_KEY = ""

    monkeypatch.setattr(modulo, "config", _ConfigVuota())
    repo = YoutubeSubscriptionRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo, "youtube_subscription_repo", repo)
    await repo.add_subscription(100, 500, "UCabc", "Canale A", 1)

    canale = _Canale(500)
    servizio = YoutubeWatcherService()
    try:
        await servizio.tick(_Bot(canale))  # non deve sollevare
        assert canale.sent_messages == []
    finally:
        await servizio.close()
