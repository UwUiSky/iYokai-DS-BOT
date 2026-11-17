"""
tests/test_alert_catalogo_r1b.py
================================
Catalogo «Alert social» (#129), blocco 3: social senza interfaccia (ALR-002, 003, 004, 005), Bluesky (ALR-006),
podcast (ALR-007), canale YouTube da un link (ALR-011), tetti con il premium (ALR-041), ping dei ruoli (ALR-019).
"""

import json
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
import pytest_asyncio

import cogs.utility.alert_piattaforme as piat_cog
import cogs.utility.feed_alerts as modulo
from cogs.utility.alert_piattaforme import AlertPiattaformeCog
from cogs.utility.feed_alerts import MODULE_FEED_ALERTS, FeedAlertsCog
from core import alert_limiti_logic as limiti
from core import alert_piattaforme_logic as piat
from core import podcast_logic
from core import youtube_link_logic as ytl
from core.alert_options_logic import GUIDA_SOCIAL, AlertOptions, menzioni_avviso, profilo_social_senza_feed
from core.database import Database
from core.repositories.alert_gestione_repo import AlertGestioneRepository
from core.repositories.alert_options_repo import AlertOptionsRepository
from core.repositories.custom_webhook_repo import CustomWebhookRepository
from core.repositories.feed_subscription_repo import FeedSubscriptionRepository
from core.repositories.kick_subscription_repo import KickSubscriptionRepository
from core.repositories.picarto_subscription_repo import PicartoSubscriptionRepository
from core.repositories.twitch_subscription_repo import TwitchSubscriptionRepository
from core.repositories.youtube_subscription_repo import YoutubeSubscriptionRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

GUILD = 900000131


def _testo(i) -> str:
    c = i.response.send_message.call_args
    return c.args[0] if c.args else c.kwargs.get("content", "")


# ------------------------------------------------------------------ logica pura
def test_alr002_003_004_005_profili_social_senza_feed_si_spiegano():
    """ALR-002, 003, 004, 005: TikTok, Instagram, X e Facebook non si leggono; la guida indica feed ponte e webhook."""
    for url in ("https://www.tiktok.com/@a", "https://instagram.com/a", "https://x.com/a", "https://twitter.com/a",
                "https://www.facebook.com/pagina", "https://fb.watch/x"):
        assert profilo_social_senza_feed(url), url
    assert not profilo_social_senza_feed("https://esempio.it/feed.xml")
    for parola in ("TikTok", "Instagram", "Facebook", "feed «ponte»", "Webhook in ingresso", "bluesky", "podcast"):
        assert parola.lower() in GUIDA_SOCIAL.lower(), parola


def test_alr006_indirizzo_bluesky():
    assert piat.indirizzo_bluesky("@Nome.bsky.social") == "https://bsky.app/profile/nome.bsky.social/rss"
    assert piat.indirizzo_bluesky("https://bsky.app/profile/esempio.com/post/3k") == "https://bsky.app/profile/esempio.com/rss"
    for male in ("", "senzapunto", "a b.com", "../x.com", "https://evil.example/x"):
        assert piat.indirizzo_bluesky(male) is None, male


def test_alr014_016_subreddit_e_elenco_sicuro():
    assert piat.indirizzo_subreddit("r/Python") == "https://www.reddit.com/r/python/new/.rss"
    assert piat.indirizzo_subreddit("a/b") is None and piat.indirizzo_subreddit("ab") is None
    assert piat.indirizzo_subreddit("python", solo_sicuri=True) is None
    assert piat.indirizzo_subreddit("Memes", solo_sicuri=True) is not None


def test_alr015_017_feed_noti_https_e_descritti():
    assert {"anime-news", "manga-uscite", "giochi-gratis"} <= set(piat.FEED_NOTI)
    assert len(piat.FEED_NOTI) <= 25  # un menu di scelta ha al massimo 25 voci
    for url, descrizione in piat.FEED_NOTI.values():
        assert url.startswith("https://") and descrizione and len(descrizione) <= 100


def test_alr007_risultati_del_podcast_puliti():
    dati = {"results": [
        {"collectionName": "Serial <b>x</b>", "artistName": "NYT", "feedUrl": "https://feeds.example/serial"},
        {"collectionName": "Senza feed"},
        {"collectionName": "Feed strano", "feedUrl": "file:///etc/passwd"},
        {"collectionName": "Doppione", "feedUrl": "https://feeds.example/serial"},
        {"collectionName": "Lungo", "feedUrl": "https://a.b/" + "x" * 600},
        "non è un dizionario",
    ]}
    trovati = podcast_logic.leggi_risultati(json.dumps(dati))
    assert [p.feed_url for p in trovati] == ["https://feeds.example/serial"] and "<b>" not in trovati[0].nome
    assert podcast_logic.leggi_risultati("rotto") == [] and podcast_logic.leggi_risultati("[]") == []
    assert "itunes.apple.com" in podcast_logic.url_ricerca("a b & c") and "%26" in podcast_logic.url_ricerca("a b & c")


def test_alr011_id_del_canale_da_ogni_tipo_di_link():
    uc = "UC" + "a1_-" * 5 + "bc"
    assert ytl.id_canale_diretto(uc) == uc
    assert ytl.id_canale_diretto(f"https://www.youtube.com/channel/{uc}/videos") == uc
    assert ytl.id_canale_diretto("https://www.youtube.com/@nome") is None
    assert ytl.indirizzo_youtube("@nome") == "https://www.youtube.com/@nome"
    assert ytl.indirizzo_youtube("youtu.be/abc123") == "https://youtu.be/abc123"
    for male in ("https://evil.example/youtube.com", "https://youtube.com.evil.example/x", "ftp://youtube.com/x",
                 "https://user@www.youtube.com/x", "http://127.0.0.1/x"):
        assert ytl.indirizzo_youtube(male) is None, male
    pagina = f'<html><meta itemprop="channelId" content="{uc}"> altro "channelId":"UC{"z" * 22}"</html>'
    assert ytl.id_nella_pagina(pagina) == uc
    assert ytl.id_nella_pagina('"externalId":"UC' + "q" * 22 + '"') == "UC" + "q" * 22
    assert ytl.id_nella_pagina("niente") is None


async def test_alr011_risolvi_canale_una_sola_richiesta_solo_a_youtube(monkeypatch):
    uc = "UC" + "k" * 22
    pagina = AsyncMock(return_value=f'<meta itemprop="channelId" content="{uc}">')
    monkeypatch.setattr(ytl, "safe_get", pagina)
    assert await ytl.risolvi_canale("https://www.youtube.com/shorts/abc") == uc
    assert pagina.await_count == 1
    assert await ytl.risolvi_canale("https://evil.example/shorts/abc") is None
    assert pagina.await_count == 1  # nessuna richiesta verso altri siti
    assert await ytl.risolvi_canale(f"https://youtube.com/channel/{uc}") == uc
    assert pagina.await_count == 1  # l'ID nel link non costa una richiesta


async def test_alr041_tetti_base_e_premium(monkeypatch):
    """ALR-041: 25 per tipo e 50 in tutto; il premium li porta a 100 e 200."""
    monkeypatch.setattr(limiti, "server_premium", AsyncMock(return_value=False))
    assert await limiti.tetti(1) == (25, 50)
    monkeypatch.setattr(limiti, "server_premium", AsyncMock(return_value=True))
    assert await limiti.tetti(1) == (100, 200)


async def test_alr041_un_controllo_premium_rotto_vale_il_piano_gratuito(monkeypatch):
    import core.premium as premium

    monkeypatch.setattr(premium, "guild_has_premium_access", AsyncMock(side_effect=RuntimeError("db")))
    assert await limiti.server_premium(1) is False


def test_alr019_everyone_e_here_mai_e_il_ruolo_solo_se_permesso():
    """ALR-019 (scelta D12): @everyone e @here non partono mai dagli avvisi; si usa un ruolo menzionabile."""
    ruolo_ok = AlertOptions(mention_role_id=5, ping_allowed=True)
    m = menzioni_avviso(ruolo_ok)
    assert m.everyone is False and m.users is False and [r.id for r in m.roles] == [5]
    assert menzioni_avviso(AlertOptions(mention_role_id=5, ping_allowed=False)).roles is False
    ruolo_everyone = MagicMock(spec=discord.Role)
    ruolo_everyone.is_default.return_value = True
    assert FeedAlertsCog._errore_ruolo_avviso(ruolo_everyone, MagicMock()) is not None


# ------------------------------------------------------------------ comandi su PostgreSQL
@pytest_asyncio.fixture
async def ambiente(monkeypatch):
    database = Database()
    await database.connect()
    await database.run_migrations()
    await database.set_module_active_for_guild(GUILD, MODULE_FEED_ALERTS, True)
    pool = lambda: database.pool  # noqa: E731
    monkeypatch.setattr(piat_cog, "db", database)
    monkeypatch.setattr(modulo, "db", database)
    for nome, classe in (
        ("feed_subscription_repo", FeedSubscriptionRepository), ("youtube_subscription_repo", YoutubeSubscriptionRepository),
        ("picarto_subscription_repo", PicartoSubscriptionRepository), ("alert_options_repo", AlertOptionsRepository),
    ):
        monkeypatch.setattr(piat_cog, nome, classe(pool_provider=pool))
    for nome, classe in (
        ("feed_subscription_repo", FeedSubscriptionRepository), ("twitch_subscription_repo", TwitchSubscriptionRepository),
        ("youtube_subscription_repo", YoutubeSubscriptionRepository), ("kick_subscription_repo", KickSubscriptionRepository),
        ("alert_options_repo", AlertOptionsRepository), ("custom_webhook_repo", CustomWebhookRepository),
    ):
        monkeypatch.setattr(modulo, nome, classe(pool_provider=pool))
    import core.repositories.alert_gestione_repo as g

    monkeypatch.setattr(g, "alert_gestione_repo", AlertGestioneRepository(pool_provider=pool))
    monkeypatch.setattr(limiti, "server_premium", AsyncMock(return_value=False))
    monkeypatch.setattr(piat_cog, "url_e_sicuro", AsyncMock(return_value=True))
    yield database
    for tabella in ("feed_subscriptions", "twitch_subscriptions", "youtube_subscriptions", "kick_subscriptions",
                    "picarto_subscriptions", "alert_options"):
        await database.pool.execute(f"DELETE FROM {tabella} WHERE guild_id = $1", GUILD)
    await database.close()


def _guild():
    g = fake_guild(); g.id = GUILD; g.me = MagicMock()
    return g


def _canale(cid=500, ok=True):
    c = MagicMock(spec=discord.TextChannel)
    c.id, c.mention = cid, f"<#{cid}>"
    c.guild = MagicMock(); c.guild.id = GUILD
    c.permissions_for.return_value = discord.Permissions(view_channel=ok, send_messages=ok, embed_links=ok)
    return c


def _interazione():
    i = fake_interaction(guild=_guild(), user=fake_member())
    i.client = MagicMock()
    return i


def _scelta(valore):
    c = MagicMock(); c.value = valore; c.name = valore
    return c


async def _conta(db, tabella):
    return await db.pool.fetchval(f"SELECT count(*) FROM {tabella} WHERE guild_id = $1", GUILD)


async def test_alr006_comando_bluesky(ambiente):
    cog = AlertPiattaformeCog(bot=None)
    i = _interazione()
    await cog.bluesky.callback(cog, i, "no valido", _canale(), "B")
    assert "Bluesky" in _testo(i) and await _conta(ambiente, "feed_subscriptions") == 0
    i = _interazione()
    await cog.bluesky.callback(cog, i, "@nome.bsky.social", _canale(), "Nome")
    riga = await ambiente.pool.fetchrow("SELECT * FROM feed_subscriptions WHERE guild_id = $1", GUILD)
    assert riga["feed_url"] == "https://bsky.app/profile/nome.bsky.social/rss" and "{link}" in riga["message_template"]
    # il bot non scrive nel canale: niente
    i = _interazione()
    await cog.bluesky.callback(cog, i, "altro.bsky.social", _canale(ok=False), "X")
    assert "non può scrivere" in _testo(i) and await _conta(ambiente, "feed_subscriptions") == 1


async def test_alr007_podcast_scelta_e_solo_di_chi_ha_lanciato(ambiente, monkeypatch):
    cog = AlertPiattaformeCog(bot=None)
    trovati = [podcast_logic.Podcast("Uno", "A", "https://f.example/uno"), podcast_logic.Podcast("Due", "B", "https://f.example/due")]
    monkeypatch.setattr(piat_cog, "cerca_podcast", AsyncMock(return_value=trovati))
    i = _interazione(); i.response.defer = AsyncMock()
    await cog.podcast.callback(cog, i, "serial", _canale())
    vista = i.followup.send.await_args.kwargs["view"]
    assert [o.label for o in vista.children[0].options] == ["Uno", "Due"]
    intruso = fake_interaction(user=fake_member()); intruso.user.id = 12345
    assert await vista.interaction_check(intruso) is False
    scelta = _interazione(); scelta.user.id = i.user.id; scelta.data = {"values": ["1"]}
    monkeypatch.setattr("core.ui_base._utente_o_server_in_blacklist", AsyncMock(return_value=False))
    assert await vista.interaction_check(scelta) is True
    await vista._scelto(scelta)
    assert await ambiente.pool.fetchval("SELECT feed_url FROM feed_subscriptions WHERE guild_id = $1", GUILD) == "https://f.example/due"
    monkeypatch.setattr(piat_cog, "cerca_podcast", AsyncMock(return_value=[]))
    i = _interazione(); i.response.defer = AsyncMock()
    await cog.podcast.callback(cog, i, "niente", _canale())
    assert "Non ho trovato" in i.followup.send.await_args.args[0]


async def test_alr011_comando_youtube_da_link_con_live(ambiente, monkeypatch):
    cog = AlertPiattaformeCog(bot=None)
    uc = "UC" + "m" * 22
    monkeypatch.setattr(piat_cog, "risolvi_canale", AsyncMock(return_value=uc))
    i = _interazione(); i.response.defer = AsyncMock()
    await cog.youtube.callback(cog, i, "https://www.youtube.com/@nome", _canale(), "Nome", True)
    assert await ambiente.pool.fetchval("SELECT feed_url FROM feed_subscriptions WHERE guild_id = $1", GUILD) == (
        f"https://www.youtube.com/feeds/videos.xml?channel_id={uc}")
    assert await ambiente.pool.fetchval("SELECT youtube_channel_id FROM youtube_subscriptions WHERE guild_id = $1", GUILD) == uc
    monkeypatch.setattr(piat_cog, "risolvi_canale", AsyncMock(return_value=None))
    i = _interazione(); i.response.defer = AsyncMock()
    await cog.youtube.callback(cog, i, "https://www.youtube.com/boh", _canale(), "X", False)
    assert "Non riesco" in i.followup.send.await_args.args[0]


async def test_alr014_016_subreddit_formato_e_immagini(ambiente):
    cog = AlertPiattaformeCog(bot=None)
    i = _interazione(); i.response.defer = AsyncMock()
    await cog.subreddit.callback(cog, i, "python", _canale(), _scelta("embed"), False)
    n = await ambiente.pool.fetchval("SELECT id FROM feed_subscriptions WHERE guild_id = $1", GUILD)
    assert (await piat_cog.alert_options_repo.get("RSS", n)).formato == "embed"
    i = _interazione()
    await cog.subreddit.callback(cog, i, "python", _canale(), None, True)  # ALR-016: fuori dall'elenco sicuro
    assert "solo questi" in _testo(i).lower()
    i = _interazione(); i.response.defer = AsyncMock()
    await cog.subreddit.callback(cog, i, "memes", _canale(), None, True)
    assert await _conta(ambiente, "feed_subscriptions") == 2


async def test_alr015_017_feed_noto(ambiente):
    cog = AlertPiattaformeCog(bot=None)
    i = _interazione(); i.response.defer = AsyncMock()
    await cog.feed_noto.callback(cog, i, _scelta("giochi-gratis"), _canale())
    assert await ambiente.pool.fetchval("SELECT feed_url FROM feed_subscriptions WHERE guild_id = $1", GUILD) == piat.FEED_NOTI["giochi-gratis"][0]


async def test_alr041_il_tetto_totale_blocca_e_il_premium_lo_alza(ambiente, monkeypatch):
    cog = AlertPiattaformeCog(bot=None)
    for n in range(50):
        await ambiente.pool.execute(
            "INSERT INTO kick_subscriptions (guild_id, channel_id, kick_slug, label, live_message_template, offline_message_template, created_by)"
            " VALUES ($1, 1, $2, 'x', 'a', 'b', 1)", GUILD, f"c{n}")  # 25 per tipo: li metto su più tabelle
    # 50 righe tutte Kick superano il tetto per tipo, ma qui conta il totale: il comando deve rifiutare comunque
    i = _interazione(); i.response.defer = AsyncMock()
    await cog.bluesky.callback(cog, i, "nome.bsky.social", _canale(), "N")
    assert "massimo di avvisi in tutto" in i.followup.send.await_args.args[0]
    assert await _conta(ambiente, "feed_subscriptions") == 0
    monkeypatch.setattr(limiti, "server_premium", AsyncMock(return_value=True))
    i = _interazione(); i.response.defer = AsyncMock()
    await cog.bluesky.callback(cog, i, "nome.bsky.social", _canale(), "N")
    assert await _conta(ambiente, "feed_subscriptions") == 1
