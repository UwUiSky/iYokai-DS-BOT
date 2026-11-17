"""
tests/test_alert_catalogo_r1c.py
================================
Catalogo «Alert social» (#129), blocco 4: Picarto (ALR-008), registrazione Twitch (ALR-012), eventi dal
calendario Twitch (ALR-013), frequenza dei controlli (ALR-034), avvisi quasi immediati (ALR-035).
Twitch e Picarto contro un server aiohttp VERO in locale (stessa forma delle API), non una sessione finta.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer

import core.picarto_watcher as pw
from core import twitch_eventi as ev
from core.alert_frequenze_logic import FREQUENZE, intervallo
from core.repositories.picarto_subscription_repo import PicartoSubscriptionRepository
from core.repositories.twitch_subscription_repo import TwitchSubscriptionRepository
from core.twitch_api_logic import parse_schedule_response, parse_users_response, parse_videos_response
from core.twitch_watcher import TwitchWatcherService
from tests.support.alert_finti import repo_opzioni_finto  # noqa: F401  (autouse)
from tests.support.discord_fakes import fake_guild


@pytest.fixture(autouse=True)
def _modulo_attivo(monkeypatch):
    async def _si(guild_id):
        return True

    monkeypatch.setattr("core.feed_alert_gate.modulo_alert_attivo", _si)


# ------------------------------------------------------------------ ALR-034 / ALR-035
def test_alr034_frequenza_da_env_con_minimo(monkeypatch):
    """ALR-034: l'owner sceglie ogni quanto controllare, mai sotto il minimo che protegge le quote."""
    for nome, (variabile, predefinito, minimo) in FREQUENZE.items():
        monkeypatch.delenv(variabile, raising=False)
        assert intervallo(nome) == predefinito
        monkeypatch.setenv(variabile, "1")
        assert intervallo(nome) == minimo
        monkeypatch.setenv(variabile, "boh")
        assert intervallo(nome) == predefinito
        monkeypatch.setenv(variabile, "999999999")
        assert intervallo(nome) == 86400
    monkeypatch.setenv("ALERT_TWITCH_SECONDI", "45")
    assert intervallo("twitch") == 45


def test_alr035_avvisi_piu_rapidi_ma_con_minimo():
    """ALR-035: la spinta (EventSub, WebSub) richiede un indirizzo pubblico che il bot non ha (D90): l'alternativa
    sono controlli più frequenti, con minimo di 30 s per Twitch e 2 minuti per feed e YouTube."""
    assert FREQUENZE["twitch"][2] == 30 and FREQUENZE["feed"][2] == 120 and FREQUENZE["youtube"][2] == 120


# ------------------------------------------------------------------ ALR-008 Picarto
def test_alr008_lettura_di_un_canale_picarto():
    ok = pw.leggi_canale(json.dumps({"online": True, "title": "<b>Disegno</b> @everyone", "category": ["Creative", "Art"]}), "x")
    assert ok.in_diretta and ok.categoria == "Creative" and "<b>" not in ok.titolo
    assert not pw.leggi_canale('{"online": false}', "x").in_diretta
    for male in ("rotto", "[]", '{"online": "si"}', "", None):
        assert pw.leggi_canale(male, "x") is None


class _Sub:
    def __init__(self, i=1, nome="artista", live=False, guild=1):
        self.id, self.picarto_name, self.last_known_live = i, nome, live
        self.guild_id, self.channel_id, self.label = guild, 10, "Art"
        self.live_message_template = "LIVE {label} {title} {gioco}"
        self.offline_message_template = "FINE {label}"


@pytest.fixture
def mondo(monkeypatch):
    canale = MagicMock(spec=discord.TextChannel); canale.id = 10
    canale.send = AsyncMock(return_value=MagicMock(id=555))
    g = fake_guild(1); g.get_channel = MagicMock(return_value=canale)
    bot = MagicMock(); bot.get_guild = MagicMock(return_value=g)
    aggiornati = []

    async def _agg(i, live):
        aggiornati.append((i, live))

    repo = MagicMock(get_all_subscriptions=AsyncMock(), update_last_known_live=_agg)
    monkeypatch.setattr(pw, "picarto_subscription_repo", repo)

    async def _attive(subs):
        return subs

    monkeypatch.setattr(pw, "filtra_attive", _attive)
    return bot, canale, repo, aggiornati


async def test_alr008_picarto_diretta_e_fine(mondo):
    bot, canale, repo, aggiornati = mondo
    repo.get_all_subscriptions.return_value = [_Sub()]
    w = pw.PicartoWatcherService()
    w._leggi = AsyncMock(return_value=pw.StatoPicarto("artista", True, "Ritratti", "Creative"))
    await w.tick(bot)
    assert canale.send.await_args.args[0] == "LIVE Art Ritratti Creative" and aggiornati == [(1, True)]
    repo.get_all_subscriptions.return_value = [_Sub(live=True)]
    w._leggi = AsyncMock(return_value=pw.StatoPicarto("artista", False))
    await w.tick(bot)
    assert canale.send.await_args.args[0] == "FINE Art" and aggiornati[-1] == (1, False)


async def test_alr008_picarto_una_richiesta_per_canale_e_tetto_per_giro(mondo):
    bot, _, repo, _ = mondo
    repo.get_all_subscriptions.return_value = [_Sub(i=i, nome=f"c{i}") for i in range(60)] + [_Sub(i=99, nome="c0", guild=2)]
    w = pw.PicartoWatcherService()
    w._leggi = AsyncMock(return_value=None)  # il servizio non risponde: lo stato non cambia
    await w.tick(bot)
    assert w._leggi.await_count == pw.MAX_RICHIESTE_PER_GIRO  # tetto per giro, doppioni tolti
    visti = {c.args[0] for c in w._leggi.await_args_list}
    await w.tick(bot)
    visti |= {c.args[0] for c in w._leggi.await_args_list}
    assert len(visti) == 60  # a rotazione nessuno resta fuori


async def test_alr008_picarto_nome_rete_solo_verso_picarto(monkeypatch):
    chiamate = []

    async def finto(url, max_bytes=0):
        chiamate.append(url)
        return '{"online": true, "title": "t", "category": ["x"]}'

    monkeypatch.setattr(pw, "safe_get", finto)
    s = await pw.PicartoWatcherService()._leggi("nome_1")
    assert s.in_diretta and chiamate == ["https://api.picarto.tv/api/v1/channel/name/nome_1"]


# ------------------------------------------------------------------ ALR-012 / 013 Twitch (server vero)
SEGMENTI = {"data": {"segments": [
    {"id": "s1", "start_time": "2099-01-01T10:00:00Z", "end_time": "2099-01-01T12:00:00Z", "title": "Torneo <b>@everyone</b>",
     "category": {"name": "Valorant"}, "canceled_until": None},
    {"id": "s2", "start_time": "2099-01-02T10:00:00Z", "end_time": None, "title": "Annullata", "category": None, "canceled_until": "2099-01-03T00:00:00Z"},
    {"id": 5}, "x"], "broadcaster_id": "77"}}


@pytest_asyncio.fixture
async def server_twitch():
    stato = {"live": set(), "chiamate": []}

    async def oauth(request):
        return web.json_response({"access_token": "tok", "expires_in": 3600})

    async def streams(request):
        stato["chiamate"].append("streams")
        dati = [{"user_login": l, "title": "T", "game_name": "G"} for l in request.query.getall("user_login", []) if l in stato["live"]]
        return web.json_response({"data": dati})

    async def users(request):
        stato["chiamate"].append("users")
        return web.json_response({"data": [{"id": "77", "login": request.query["login"]}]})

    async def videos(request):
        stato["chiamate"].append("videos")
        assert request.query["user_id"] == "77" and request.query["type"] == "archive"
        return web.json_response({"data": [{"url": "https://www.twitch.tv/videos/123"}]})

    async def schedule(request):
        stato["chiamate"].append("schedule")
        assert request.query["broadcaster_id"] == "77"
        return web.json_response(SEGMENTI)

    app = web.Application()
    app.router.add_post("/oauth2/token", oauth)
    for percorso, h in (("streams", streams), ("users", users), ("videos", videos), ("schedule", schedule)):
        app.router.add_get(f"/helix/{percorso}", h)
    server = TestServer(app)
    await server.start_server()
    yield server, stato
    await server.close()


def _servizio(server, monkeypatch):
    import core.twitch_watcher as modulo

    class _Cfg:
        TWITCH_CLIENT_ID = "id"
        TWITCH_CLIENT_SECRET = "secret"

    monkeypatch.setattr(modulo, "config", _Cfg())
    return TwitchWatcherService(
        oauth_url=f"http://{server.host}:{server.port}/oauth2/token",
        streams_url=f"http://{server.host}:{server.port}/helix/streams",
    )


def test_parser_twitch_users_videos_schedule():
    assert parse_users_response({"data": [{"id": "77"}]}) == "77"
    assert parse_users_response({"data": [{"id": "x; drop"}]}) is None and parse_users_response([]) is None
    assert parse_videos_response({"data": [{"url": "https://www.twitch.tv/videos/9"}]}) == "https://www.twitch.tv/videos/9"
    assert parse_videos_response({"data": [{"url": "https://evil.example/x"}]}) is None
    segmenti = parse_schedule_response(SEGMENTI)
    assert [s.id for s in segmenti] == ["s1", "s2"] and segmenti[1].cancellata and segmenti[0].categoria == "Valorant"
    assert parse_schedule_response({"data": None}) == [] and parse_schedule_response("x") == []


async def test_alr012_vod_nel_messaggio_di_fine_solo_se_richiesto(server_twitch, monkeypatch, clean_db):
    server, stato = server_twitch
    servizio = _servizio(server, monkeypatch)
    try:
        assert await servizio.ultimo_vod("streamera") == "https://www.twitch.tv/videos/123"
        assert await servizio.ultimo_vod("streamera") == "https://www.twitch.tv/videos/123"
        assert stato["chiamate"].count("users") == 1  # l'ID si ricorda
        # nel giro: la diretta finisce, il modello ha {vod}
        import core.twitch_watcher as modulo

        repo = TwitchSubscriptionRepository(pool_provider=lambda: clean_db)
        monkeypatch.setattr(modulo, "twitch_subscription_repo", repo)
        n = await repo.add_subscription(100, 500, "streamera", "Str", 1)
        await clean_db.execute("UPDATE twitch_subscriptions SET last_known_live = true, offline_message_template = $2 WHERE id = $1",
                               n, "Fine {label}. Rivedi: {vod}")
        canale = MagicMock(spec=discord.TextChannel); canale.id = 500
        canale.send = AsyncMock(return_value=MagicMock(id=1))
        g = fake_guild(100); g.get_channel = MagicMock(return_value=canale)
        bot = MagicMock(); bot.get_guild = MagicMock(return_value=g)
        await servizio.tick(bot)
        assert canale.send.await_args.args[0] == "Fine Str. Rivedi: https://www.twitch.tv/videos/123"
        # senza {vod} nel modello nessuna richiesta in più
        await clean_db.execute("UPDATE twitch_subscriptions SET last_known_live = true, offline_message_template = 'Fine' WHERE id = $1", n)
        prima = stato["chiamate"].count("videos")
        await servizio.tick(bot)
        assert stato["chiamate"].count("videos") == prima
    finally:
        await servizio.close() if hasattr(servizio, "close") else None
        await clean_db.execute("DELETE FROM twitch_subscriptions WHERE guild_id = 100")


async def test_alr013_calendario_e_creazione_eventi(server_twitch, monkeypatch):
    server, _ = server_twitch
    servizio = _servizio(server, monkeypatch)
    segmenti = await servizio.calendario("streamera")
    await servizio.close()
    assert len(segmenti) == 2

    registro = {}

    class _Repo:
        async def segmenti_fatti(self, g, s):
            return set(registro)

        async def segna(self, g, s, seg, evento, inizio):
            registro[seg] = evento

    monkeypatch.setattr(ev, "twitch_eventi_repo", _Repo())
    guild = MagicMock()
    guild.id = 1
    guild.me.guild_permissions = discord.Permissions(manage_events=True)
    guild.scheduled_events = []
    guild.create_scheduled_event = AsyncMock(return_value=MagicMock(id=900))
    adesso = datetime(2098, 12, 25, tzinfo=timezone.utc)
    assert await ev.crea_eventi_del_canale(guild, 3, "streamera", segmenti, adesso) == 1  # s2 è cancellata
    kw = guild.create_scheduled_event.await_args.kwargs
    assert kw["location"] == "https://twitch.tv/streamera" and "<b>" not in kw["name"] and len(kw["name"]) <= 100
    assert "@everyone" not in kw["name"].replace("@​everyone", "")
    assert kw["entity_type"] == discord.EntityType.external and kw["end_time"] > kw["start_time"]
    # già fatto: nessun doppione; passato o troppo lontano: ignorato
    assert await ev.crea_eventi_del_canale(guild, 3, "streamera", segmenti, adesso) == 0
    assert await ev.crea_eventi_del_canale(guild, 4, "streamera", segmenti, datetime(2100, 1, 1, tzinfo=timezone.utc)) == 0
    registro.clear()
    assert await ev.crea_eventi_del_canale(guild, 5, "streamera", segmenti, datetime(2090, 1, 1, tzinfo=timezone.utc)) == 0  # oltre 14 giorni


def test_alr013_servono_il_permesso_e_spazio_tra_i_100_eventi():
    guild = MagicMock()
    guild.me.guild_permissions = discord.Permissions(manage_events=False)
    guild.scheduled_events = []
    assert ev.puo_creare_eventi(guild) is False
    guild.me.guild_permissions = discord.Permissions(manage_events=True)
    assert ev.puo_creare_eventi(guild) is True
    guild.scheduled_events = [object()] * 100
    assert ev.puo_creare_eventi(guild) is False


async def test_alr013_comando_eventi_twitch(monkeypatch):
    import cogs.utility.alert_gestione as g

    cog = g.AlertGestioneCog(bot=None)
    monkeypatch.setattr(g, "db", MagicMock(is_module_active_for_guild=AsyncMock(return_value=True)))
    monkeypatch.setattr(g, "alert_gestione_repo", MagicMock(esiste=AsyncMock(return_value=True)))
    opzioni = MagicMock(set_fields=AsyncMock())
    monkeypatch.setattr(g, "alert_options_repo", opzioni)
    from tests.support.discord_fakes import fake_interaction, fake_member

    def _i(permesso=True):
        i = fake_interaction(guild=fake_guild(7), user=fake_member())
        i.guild.me = MagicMock(); i.guild.me.guild_permissions = discord.Permissions(manage_events=permesso)
        return i

    i = _i(); await cog.eventi_twitch.callback(cog, i, "KK-1", True)
    assert "solo per gli avvisi Twitch" in i.response.send_message.call_args.args[0]
    i = _i(permesso=False); await cog.eventi_twitch.callback(cog, i, "TW-1", True)
    assert "Gestisci eventi" in i.response.send_message.call_args.args[0] and not opzioni.set_fields.await_count
    i = _i(); await cog.eventi_twitch.callback(cog, i, "TW-1", True)
    opzioni.set_fields.assert_awaited_once_with("TW", 1, 7, schedule_events=True)
    i = _i(permesso=False); await cog.eventi_twitch.callback(cog, i, "TW-1", False)  # spegnere non chiede il permesso
    assert opzioni.set_fields.await_count == 2
