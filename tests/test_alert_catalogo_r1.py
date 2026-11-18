"""
tests/test_alert_catalogo_r1.py
===============================
Catalogo «Alert social» (#129), blocchi 1 e 2: modelli di messaggio (ALR-020, 021, 022, 023, 029),
embed e formato (ALR-014, 024, 009), sposta, ferma tutti, elenco con stato, controllo a mano
(ALR-037, 038, 039, 040). Logica pura, watcher con oggetti finti e comandi su PostgreSQL vero.
"""

from datetime import timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
import pytest_asyncio

import cogs.utility.alert_gestione as gestione
import cogs.utility.feed_alerts as modulo
from cogs.utility.alert_gestione import AlertGestioneCog
from cogs.utility.feed_alerts import MODULE_FEED_ALERTS, FeedAlertsCog
from core import diretta_controllo_logic as controllo
from core import kick_watcher as kw
from core.alert_messaggio_logic import (
    durata_leggibile,
    embed_da_modello,
    embed_predefinito,
    neutralizza_menzioni,
    pulisci_esterno,
    segnaposto_sconosciuti,
    valori_voce,
)
from core.alert_options_logic import AlertOptions, invia_alert
from core.alert_options_logic import testo_con_menzione as con_menzione
from core.database import Database
from core.embed_builder_logic import DatiEmbed
from core.feed_parsing_logic import parse_feed
from core.repositories.alert_gestione_repo import AlertGestioneRepository
from core.repositories.alert_options_repo import AlertOptionsRepository
from core.repositories.custom_webhook_repo import CustomWebhookRepository
from core.repositories.feed_subscription_repo import FeedSubscriptionRepository
from core.repositories.kick_subscription_repo import KickSubscriptionRepository
from core.repositories.picarto_subscription_repo import PicartoSubscriptionRepository
from core.repositories.saved_embed_repo import SavedEmbedRepository
from core.repositories.twitch_subscription_repo import TwitchSubscriptionRepository
from core.repositories.youtube_subscription_repo import YoutubeSubscriptionRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel
from tests.test_kick_watcher import _Sub, _risposta, mondo  # noqa: F401  (fixture del watcher)

GUILD = 900000129
ALTRO = 900000130


def _testo(i) -> str:
    c = i.response.send_message.call_args
    return c.args[0] if c.args else c.kwargs.get("content", "")


# ------------------------------------------------------------------ messaggio
def test_alr021_ruolo_dove_vuole_chi_scrive():
    """ALR-021: `{ruolo}` mette il ping al suo posto; senza il segnaposto il ruolo va davanti."""
    opz = AlertOptions(mention_role_id=9, ping_allowed=True)
    assert con_menzione("Evviva {ruolo}: si parte", opz) == "Evviva <@&9>: si parte"
    assert con_menzione("Si parte", opz) == "<@&9> Si parte"
    assert con_menzione("Si parte {ruolo}", AlertOptions()) == "Si parte"  # nessun ruolo: il segnaposto sparisce


def test_alr022_e_alr020_segnaposto_per_tipo():
    """ALR-022 e ALR-020: `{gioco}` per Twitch e Kick; ogni tipo dichiara i suoi segnaposto."""
    assert segnaposto_sconosciuti("{label} {gioco} {game} {ruolo}", "TW") == []
    assert segnaposto_sconosciuti("{label} {titolo} {gioco}", "YT") == ["titolo", "gioco"]
    assert segnaposto_sconosciuti("{thumbnail} {descrizione} {durata} {link}", "RSS") == []


def test_menzioni_nei_testi_di_fuori_neutralizzate():
    """D12: un titolo non può far partire @everyone né il ruolo dell'avviso."""
    pulito = pulisci_esterno("<b>Ciao</b> @everyone @here <@&5> <@7> <#9>   a\ncapo")
    assert "@everyone" not in pulito.replace("@​everyone", "") and "<@&" not in pulito and "<@7" not in pulito
    assert "<b>" not in pulito and "\n" not in pulito
    assert neutralizza_menzioni("a @everyone").startswith("a @​")
    assert len(pulisci_esterno("x" * 1000)) <= 256


async def test_alr022_diretta_kick_con_gioco_e_titolo_ripuliti(mondo):  # noqa: F811
    bot, canale, repo, aggiornati, _ = mondo
    sub = _Sub()
    sub.live_message_template = "{label}: {gioco} / {game} / {title}"
    repo.get_all_subscriptions.return_value = [sub]
    w = kw.KickWatcherService()
    w._fetch_channels = AsyncMock(return_value={"data": [{
        "slug": "xqc", "stream_title": "<i>Torneo</i> @everyone", "category": {"name": "Valorant"}, "stream": {"is_live": True},
    }]})
    await w.tick(bot)
    testo = canale.send.await_args.args[0]
    assert testo.startswith("Xqc: Valorant / Valorant / Torneo") and "@everyone" not in testo.replace("@​everyone", "")


def test_alr029_testo_fisso_con_il_modello():
    """ALR-029: un testo fisso (per esempio un ping) è parte del modello, che accetta fino a 500 caratteri."""
    from core.alert_messaggio_logic import MAX_MODELLO

    assert MAX_MODELLO == 500
    assert con_menzione("Novità! {ruolo} {label}", AlertOptions(mention_role_id=3)).startswith("Novità! <@&3>")


# ------------------------------------------------------------------ feed: miniatura, descrizione, durata
YT_ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/">
<entry><id>yt:video:abc123</id><title>Nuovo video</title><link rel="alternate" href="https://www.youtube.com/watch?v=abc123"/>
<published>2026-11-01T10:00:00+00:00</published>
<media:group><media:title>Nuovo video</media:title><media:thumbnail url="https://i.ytimg.com/vi/abc123/hqdefault.jpg" width="480" height="360"/>
<media:description>Prima riga &lt;b&gt;grassetto&lt;/b&gt;
seconda @everyone</media:description></media:group></entry>
<entry><id>yt:video:short1</id><title>Corto</title><link rel="alternate" href="https://www.youtube.com/shorts/short1"/></entry>
</feed>"""


def test_alr023_miniatura_e_descrizione_dal_feed_di_youtube():
    """ALR-023: miniatura e descrizione dal feed Atom (ripulite); la durata viene dalla API."""
    voci = parse_feed(YT_ATOM)
    assert voci[0].thumbnail == "https://i.ytimg.com/vi/abc123/hqdefault.jpg"
    assert voci[0].description.startswith("Prima riga grassetto seconda")
    v = valori_voce("Canale", voci[0], durata="12:30")
    assert "@everyone" not in v["descrizione"].replace("@​everyone", "") and v["durata"] == "12:30"
    assert voci[1].thumbnail == "" and voci[1].description == ""


def test_alr023_durata_leggibile():
    assert durata_leggibile("PT1H2M3S") == "1:02:03"
    assert durata_leggibile("PT45S") == "0:45"
    assert durata_leggibile("P0D") == "" and durata_leggibile(None) == "" and durata_leggibile("boh") == ""


def test_alr023_miniatura_solo_http_e_corta():
    xml = """<rss xmlns:media="http://search.yahoo.com/mrss/"><channel><item><title>t</title><link>https://a.b/1</link>
    <media:thumbnail url="javascript:alert(1)"/></item></channel></rss>"""
    assert parse_feed(xml)[0].thumbnail == ""


# ------------------------------------------------------------------ embed e formato
def test_alr014_embed_predefinito_con_titolo_link_e_miniatura():
    e = embed_predefinito({"title": "Post", "descrizione": "Testo", "thumbnail": "https://a.b/x.png", "label": "r/x"}, "https://reddit.com/p")
    assert e.title == "Post" and e.url == "https://reddit.com/p" and e.description == "Testo" and e.thumbnail.url == "https://a.b/x.png"


def test_alr024_embed_salvato_con_segnaposto_e_fallback():
    dati = DatiEmbed(title="{label}: {title}", description="Guarda {link}", footer="{ruolo}", fields=(("Gioco", "{gioco}", True),))
    e = embed_da_modello(dati, {"label": "L", "title": "T", "link": "https://x.y", "gioco": "G"})
    assert e.title == "L: T" and e.description == "Guarda https://x.y" and e.fields[0].value == "G"
    vuoto = DatiEmbed(title="{nulla}")  # un segnaposto sconosciuto resta testo: valido
    assert embed_da_modello(vuoto, {}).title == "{nulla}"
    assert embed_da_modello(DatiEmbed(description="{x}", color="rosso"), {"x": "a"}) is None  # colore non valido: si usa il predefinito


async def test_alr014_024_invio_come_embed_lascia_nel_messaggio_solo_il_ruolo():
    canale = MagicMock(); canale.guild.id = 1
    canale.send = AsyncMock(return_value=MagicMock())
    canale.is_news.return_value = False
    opz = AlertOptions(formato="embed", mention_role_id=4, ping_allowed=True, watch_button=False)
    await invia_alert(canale, "testo lungo", opz, "https://a.b", {"title": "T", "label": "L"})
    args, kwargs = canale.send.await_args
    assert args[0] == "<@&4>" and kwargs["embed"].title == "T" and kwargs["allowed_mentions"].everyone is False
    canale.send.reset_mock()
    await invia_alert(canale, "solo testo", AlertOptions(), None, {"title": "T"})
    assert canale.send.await_args.args[0] == "solo testo" and "embed" not in canale.send.await_args.kwargs
    canale.send.reset_mock()
    await invia_alert(canale, "x", AlertOptions(formato="embed", watch_button=False), None, {"label": "L"})
    assert canale.send.await_args.args[0] is None  # niente ruolo: nessun testo, solo l'embed


async def test_alr009_short_filtrati_dal_link(monkeypatch):
    """ALR-009: con `shorts=no` gli Short non si pubblicano (ma lo stato avanza), con `solo` solo gli Short."""
    from core import feed_watcher as fw

    voci = parse_feed(YT_ATOM)
    for modo, atteso in (("no", ["Nuovo video"]), ("solo", ["Corto"]), ("tutti", ["Corto", "Nuovo video"])):
        invia = AsyncMock()
        avanza = AsyncMock()
        monkeypatch.setattr(fw, "invia_alert", invia)
        monkeypatch.setattr(fw.feed_subscription_repo, "update_last_seen", avanza, raising=False)
        monkeypatch.setattr(fw, "alert_options_repo", MagicMock(get=AsyncMock(return_value=AlertOptions(shorts=modo))))
        canale = MagicMock(spec=discord.TextChannel)
        guild = MagicMock(); guild.get_channel.return_value = canale
        bot = MagicMock(); bot.get_guild.return_value = guild
        sub = MagicMock(id=1, guild_id=1, channel_id=2, label="C", message_template="{title}",
                        last_seen_entry_id="vecchio", last_seen_published=None)
        monkeypatch.setattr(fw, "find_new_entries", lambda v, a, b: list(v))
        await fw.FeedWatcherService()._controlla_sottoscrizione(bot, sub, voci)
        inviati = sorted(c.args[1] for c in invia.await_args_list)
        assert inviati == sorted(atteso), modo
        assert avanza.await_count == 2  # lo stato avanza anche per le voci scartate


# ------------------------------------------------------------------ comandi su PostgreSQL
@pytest_asyncio.fixture
async def ambiente(monkeypatch):
    database = Database()
    await database.connect()
    await database.run_migrations()
    for g in (GUILD, ALTRO):
        await database.set_module_active_for_guild(g, MODULE_FEED_ALERTS, True)
    pool = lambda: database.pool  # noqa: E731
    monkeypatch.setattr(gestione, "db", database)
    monkeypatch.setattr(modulo, "db", database)
    monkeypatch.setattr(gestione, "alert_gestione_repo", AlertGestioneRepository(pool_provider=pool))
    monkeypatch.setattr(gestione, "alert_options_repo", AlertOptionsRepository(pool_provider=pool))
    monkeypatch.setattr(gestione, "saved_embed_repo", SavedEmbedRepository(pool_provider=pool))
    import core.alert_options_logic  # noqa: F401
    for nome, classe in (
        ("feed_subscription_repo", FeedSubscriptionRepository), ("twitch_subscription_repo", TwitchSubscriptionRepository),
        ("youtube_subscription_repo", YoutubeSubscriptionRepository), ("kick_subscription_repo", KickSubscriptionRepository),
        ("picarto_subscription_repo", PicartoSubscriptionRepository),
        ("alert_options_repo", AlertOptionsRepository), ("custom_webhook_repo", CustomWebhookRepository),
    ):
        monkeypatch.setattr(modulo, nome, classe(pool_provider=pool))
    yield database
    for tabella in ("feed_subscriptions", "twitch_subscriptions", "youtube_subscriptions", "kick_subscriptions",
                    "picarto_subscriptions", "alert_options"):
        await database.pool.execute(f"DELETE FROM {tabella} WHERE guild_id = ANY($1::bigint[])", [GUILD, ALTRO])
    await database.pool.execute("DELETE FROM saved_embeds WHERE guild_id = ANY($1::bigint[])", [GUILD, ALTRO])
    await database.close()


def _guild(g=GUILD, permessi_bot=True):
    guild = fake_guild(); guild.id = g
    me = MagicMock(); guild.me = me
    return guild


def _canale(cid=500, ok=True):
    c = MagicMock(spec=discord.TextChannel)
    c.id, c.mention = cid, f"<#{cid}>"
    c.guild = MagicMock(); c.guild.id = GUILD
    c.permissions_for.return_value = discord.Permissions(view_channel=ok, send_messages=ok, embed_links=ok)
    return c


async def _twitch(db, guild=GUILD, canale=500, live=False):
    n = await TwitchSubscriptionRepository(lambda: db.pool).add_subscription(
        guild_id=guild, channel_id=canale, twitch_login="strimmer", label="Str", created_by=1)
    if live:
        await TwitchSubscriptionRepository(lambda: db.pool).update_last_known_live(n, True)
    return n


async def test_alr020_messaggio_per_twitch_inizio_e_fine_e_isolamento_tra_server(ambiente):
    """ALR-020: il modello vale anche per Twitch (inizio e fine); un altro server non può toccarlo."""
    cog = AlertGestioneCog(bot=None)
    n = await _twitch(ambiente)
    g = _guild()
    i = fake_interaction(guild=g, user=fake_member())
    await cog.messaggio.callback(cog, i, f"TW-{n}", "{ruolo} {label} gioca a {gioco}: {titolo}")
    assert "aggiornato" in _testo(i) and "{titolo}" in _testo(i) and "ruolo" in _testo(i)
    riga = await ambiente.pool.fetchrow("SELECT * FROM twitch_subscriptions WHERE id = $1", n)
    assert riga["live_message_template"].startswith("{ruolo}")
    i = fake_interaction(guild=g, user=fake_member())
    await cog.messaggio.callback(cog, i, f"TW-{n}", "Finito {label}", app_commands_choice("fine"))
    assert (await ambiente.pool.fetchval("SELECT offline_message_template FROM twitch_subscriptions WHERE id = $1", n)) == "Finito {label}"
    # altro server: non lo trova
    i = fake_interaction(guild=_guild(ALTRO), user=fake_member())
    await cog.messaggio.callback(cog, i, f"TW-{n}", "rubato")
    assert "Nessuna sottoscrizione" in _testo(i)
    assert (await ambiente.pool.fetchval("SELECT live_message_template FROM twitch_subscriptions WHERE id = $1", n)).startswith("{ruolo}")


def app_commands_choice(valore):
    c = MagicMock(); c.value = valore; c.name = valore
    return c


async def test_alr020_feed_non_ha_il_messaggio_di_fine_e_modulo_spento(ambiente):
    cog = AlertGestioneCog(bot=None)
    rss = await FeedSubscriptionRepository(lambda: ambiente.pool).add_subscription(
        guild_id=GUILD, channel_id=500, feed_url="https://e.com/f", label="f", created_by=1, message_template=None, max_per_guild=25)
    i = fake_interaction(guild=_guild(), user=fake_member())
    await cog.messaggio.callback(cog, i, f"RSS-{rss}", "x", app_commands_choice("fine"))
    assert "messaggio di fine" in _testo(i)
    await ambiente.set_module_active_for_guild(GUILD, MODULE_FEED_ALERTS, False)
    i = fake_interaction(guild=_guild(), user=fake_member())
    await cog.messaggio.callback(cog, i, f"RSS-{rss}", "x")
    assert "non attivo" in _testo(i).lower() or "modulo" in _testo(i).lower()
    await ambiente.set_module_active_for_guild(GUILD, MODULE_FEED_ALERTS, True)


async def test_alr024_formato_embed_salvato_e_shorts(ambiente):
    """ALR-014, 024, 009: formato, embed salvato come modello e Short salvati nelle opzioni."""
    cog = AlertGestioneCog(bot=None)
    rss = await FeedSubscriptionRepository(lambda: ambiente.pool).add_subscription(
        guild_id=GUILD, channel_id=500, feed_url="https://e.com/f", label="f", created_by=1, message_template=None, max_per_guild=25)
    await SavedEmbedRepository(lambda: ambiente.pool).create(GUILD, "annuncio", '{"title": "{title}", "description": "x"}', 1)
    g = _guild()
    i = fake_interaction(guild=g, user=fake_member())
    await cog.formato.callback(cog, i, f"RSS-{rss}", app_commands_choice("embed"), "Annuncio", app_commands_choice("no"))
    opz = await AlertOptionsRepository(lambda: ambiente.pool).get("RSS", rss)
    assert (opz.formato, opz.embed_nome, opz.shorts) == ("embed", "annuncio", "no")
    i = fake_interaction(guild=g, user=fake_member())
    await cog.formato.callback(cog, i, f"RSS-{rss}", None, "inesistente")
    assert "Non trovo" in _testo(i)
    i = fake_interaction(guild=g, user=fake_member())
    await cog.formato.callback(cog, i, f"RSS-{rss}", None, "-")
    assert (await AlertOptionsRepository(lambda: ambiente.pool).get("RSS", rss)).embed_nome == ""
    tw = await _twitch(ambiente)
    i = fake_interaction(guild=g, user=fake_member())
    await cog.formato.callback(cog, i, f"TW-{tw}", None, None, app_commands_choice("solo"))
    assert "solo per i feed" in _testo(i)


async def test_alr037_sposta_in_un_canale_dove_il_bot_scrive(ambiente):
    """ALR-037: lo spostamento controlla i permessi del bot nel nuovo canale."""
    cog = AlertGestioneCog(bot=None)
    n = await _twitch(ambiente)
    i = fake_interaction(guild=_guild(), user=fake_member())
    await cog.sposta.callback(cog, i, f"TW-{n}", _canale(777, ok=False))
    assert "non può scrivere" in _testo(i)
    assert await ambiente.pool.fetchval("SELECT channel_id FROM twitch_subscriptions WHERE id = $1", n) == 500
    i = fake_interaction(guild=_guild(), user=fake_member())
    await cog.sposta.callback(cog, i, f"TW-{n}", _canale(777))
    assert await ambiente.pool.fetchval("SELECT channel_id FROM twitch_subscriptions WHERE id = $1", n) == 777


async def test_alr038_ferma_tutti_con_conferma_solo_dell_autore(ambiente, monkeypatch):
    """ALR-038: cancella tutto (o un canale) solo dopo la conferma di chi ha lanciato il comando; altri server intatti."""
    cog = AlertGestioneCog(bot=None)
    a = await _twitch(ambiente, canale=500)
    b = await _twitch(ambiente, canale=600)
    altro = await _twitch(ambiente, guild=ALTRO)
    await AlertOptionsRepository(lambda: ambiente.pool).set_fields("TW", a, GUILD, paused=True)

    async def conferma(self):
        self.scelta = True

    async def annulla(self):
        self.scelta = False

    utente = fake_member(); utente.id = 42
    monkeypatch.setattr(gestione._Conferma, "wait", annulla)
    i = fake_interaction(guild=_guild(), user=utente)
    i.edit_original_response = AsyncMock()
    await cog.ferma_tutti.callback(cog, i, None)
    assert await ambiente.pool.fetchval("SELECT count(*) FROM twitch_subscriptions WHERE guild_id = $1", GUILD) == 2
    monkeypatch.setattr(gestione._Conferma, "wait", conferma)
    i = fake_interaction(guild=_guild(), user=utente)
    i.edit_original_response = AsyncMock()
    await cog.ferma_tutti.callback(cog, i, _canale(500))
    assert await ambiente.pool.fetchval("SELECT count(*) FROM twitch_subscriptions WHERE guild_id = $1", GUILD) == 1
    assert await ambiente.pool.fetchval("SELECT count(*) FROM alert_options WHERE guild_id = $1", GUILD) == 0
    i = fake_interaction(guild=_guild(), user=utente)
    i.edit_original_response = AsyncMock()
    await cog.ferma_tutti.callback(cog, i, None)
    assert await ambiente.pool.fetchval("SELECT count(*) FROM twitch_subscriptions WHERE guild_id = $1", GUILD) == 0
    assert await ambiente.pool.fetchval("SELECT count(*) FROM twitch_subscriptions WHERE guild_id = $1", ALTRO) == 1
    # il bottone lo preme solo chi ha lanciato il comando
    vista = gestione._Conferma(42)
    intruso = fake_interaction(user=fake_member()); intruso.user.id = 43
    assert await vista.interaction_check(intruso) is False


async def test_alr039_elenco_mostra_chi_e_in_diretta_ora(ambiente):
    """ALR-039: l'elenco segna con un pallino chi è in diretta (Twitch e YouTube come Kick)."""
    n = await _twitch(ambiente, live=True)
    cog = FeedAlertsCog(bot=None)
    i = fake_interaction(guild=_guild(), user=fake_member())
    await cog.list_alerts.callback(cog, i)
    descrizione = i.response.send_message.call_args.kwargs["embed"].description
    assert f"TW-{n}" in descrizione and "in diretta" in descrizione


# ------------------------------------------------------------------ controllo a mano
def test_alr040_nomi_validi_per_servizio():
    assert controllo.nome_valido("twitch", "Strimmer_1") == "strimmer_1"
    assert controllo.nome_valido("twitch", "a b") is None and controllo.nome_valido("twitch", "x" * 26) is None
    assert controllo.nome_valido("kick", "https://kick.com/Nome") == "nome"
    assert controllo.nome_valido("youtube", "UC" + "a" * 22) == "UC" + "a" * 22
    assert controllo.nome_valido("youtube", "@handle") is None  # l'handle si risolve con /admin-alert youtube


async def test_alr040_controllo_con_memoria_e_pausa_per_server(monkeypatch):
    """ALR-040: una sola lettura al servizio ogni 60 s per canale; una richiesta ogni 10 s per server."""
    controllo._azzera_per_test()
    from core import twitch_watcher as tw

    fetch = AsyncMock(return_value={"data": [{"user_login": "strimmer", "title": "<b>Torneo</b>", "game_name": "Valorant"}]})
    monkeypatch.setattr(tw.twitch_watcher, "_fetch_streams", fetch)
    s = await controllo.controlla("twitch", "strimmer")
    assert s.in_diretta is True and s.titolo == "Torneo" and s.gioco == "Valorant"
    await controllo.controlla("twitch", "strimmer")
    assert fetch.await_count == 1
    assert controllo.pausa_server(5, adesso=100.0) == 0.0
    assert 0 < controllo.pausa_server(5, adesso=103.0) <= 7
    assert controllo.pausa_server(5, adesso=111.0) == 0.0
    fetch.return_value = None  # servizio muto: non si ricorda
    s = await controllo.controlla("twitch", "altro")
    assert s.in_diretta is None


async def test_alr040_comando_diretta(ambiente, monkeypatch):
    controllo._azzera_per_test()
    cog = AlertGestioneCog(bot=None)
    monkeypatch.setattr(gestione.controllo, "controlla", AsyncMock(
        return_value=controllo.StatoDiretta("twitch", "x", True, "Titolo", "Gioco")))
    scelta = app_commands_choice("twitch"); scelta.name = "Twitch"
    i = fake_interaction(guild=_guild(), user=fake_member())
    i.response.defer = AsyncMock()
    await cog.diretta.callback(cog, i, scelta, "strimmer")
    assert "in diretta" in i.followup.send.await_args.args[0] and i.followup.send.await_args.kwargs["allowed_mentions"].roles is False
    i = fake_interaction(guild=_guild(), user=fake_member())
    await cog.diretta.callback(cog, i, scelta, "strimmer")  # subito dopo: pausa
    assert "Aspetta" in _testo(i)
    controllo._azzera_per_test()
    i = fake_interaction(guild=_guild(), user=fake_member())
    await cog.diretta.callback(cog, i, scelta, "non valido!")
    assert "non valido" in _testo(i).lower()
