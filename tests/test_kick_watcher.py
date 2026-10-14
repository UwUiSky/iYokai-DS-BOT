"""NF-32 (#103): Kick (API, watcher, repo), ruolo «in diretta», opzioni degli avvisi (#129)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from core import kick_watcher as kw
from core.alert_options_logic import AlertOptions, avviso_fine, invia_alert, menzioni_avviso
from core.kick_api_logic import normalizza_slug, parse_channels_response, parse_token_response
from core.live_role_logic import aggiorna_ruolo_live
from core.repositories.alert_options_repo import AlertOptionsRepository
from core.repositories.kick_subscription_repo import KickSubscriptionRepository
from tests.support.alert_finti import RepoOpzioniFinto
from tests.support.discord_fakes import fake_guild, fake_member, fake_role, fake_text_channel


# ------------------------------------------------------------------ API
def test_slug_normalizzato():
    assert normalizza_slug("https://kick.com/Xqc/") == "xqc"
    assert normalizza_slug("kick.com/some_user-1") == "some_user-1"
    assert normalizza_slug("no spazi") is None and normalizza_slug("a/b") is None and normalizza_slug("") is None


def test_parse_token():
    assert parse_token_response({"access_token": "t", "expires_in": 3600}) == ("t", 3600)
    assert parse_token_response({"access_token": "", "expires_in": 1}) is None
    assert parse_token_response([]) is None


def test_parse_canali_assenti_sono_offline_e_dati_strani_ignorati():
    payload = {"data": [
        {"slug": "Uno", "stream_title": "Ciao", "category": {"name": "Just Chatting"}, "stream": {"is_live": True}},
        {"slug": "due", "stream": {"is_live": False}},
        {"slug": 5}, "x",
    ]}
    r = {s.slug: s for s in parse_channels_response(payload, ["uno", "due", "tre"])}
    assert r["uno"].is_live and r["uno"].title == "Ciao" and r["uno"].category == "Just Chatting"
    assert not r["due"].is_live and not r["tre"].is_live
    assert parse_channels_response("rotto", ["a"])[0].is_live is False


# -------------------------------------------------- opzioni degli avvisi
def test_menzioni_ruolo_solo_se_chi_configura_poteva():
    assert menzioni_avviso(AlertOptions(mention_role_id=5, ping_allowed=False)).roles is False
    m = menzioni_avviso(AlertOptions(mention_role_id=5, ping_allowed=True))
    assert [r.id for r in m.roles] == [5] and m.everyone is False and m.users is False


async def test_invio_con_ruolo_bottone_e_pubblicazione():
    canale = MagicMock(); canale.id = 1
    messaggio = MagicMock(); messaggio.publish = AsyncMock()
    canale.send = AsyncMock(return_value=messaggio)
    canale.is_news.return_value = True
    opz = AlertOptions(mention_role_id=9, ping_allowed=True, crosspost=True)
    await invia_alert(canale, "ciao @everyone", opz, "https://kick.com/x")
    args, kw_ = canale.send.await_args
    assert args[0] == "<@&9> ciao @everyone" and kw_["allowed_mentions"].everyone is False
    assert kw_["view"].children[0].url == "https://kick.com/x"
    messaggio.publish.assert_awaited_once()


async def test_bottone_spento_e_pubblicazione_ko_non_rompe():
    canale = MagicMock(); canale.id = 1
    messaggio = MagicMock(); messaggio.publish = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=403), "no"))
    canale.send = AsyncMock(return_value=messaggio); canale.is_news.return_value = True
    await invia_alert(canale, "x", AlertOptions(watch_button=False, crosspost=True), "https://a.b")
    assert "view" not in canale.send.await_args.kwargs


async def test_fine_diretta_cancella_e_rispetta_il_messaggio_spento():
    canale = MagicMock(); canale.id = 1
    parziale = MagicMock(); parziale.delete = AsyncMock(side_effect=discord.NotFound(MagicMock(status=404), "x"))
    canale.get_partial_message.return_value = parziale
    canale.send = AsyncMock()
    await avviso_fine(canale, "fine", AlertOptions(delete_on_end=True, last_message_id=77, notify_end=False))
    canale.get_partial_message.assert_called_once_with(77)
    canale.send.assert_not_awaited()
    await avviso_fine(canale, "fine", AlertOptions(mention_role_id=3, ping_allowed=True))
    assert canale.send.await_args.args[0] == "fine" and "view" not in canale.send.await_args.kwargs


# --------------------------------------------------------- ruolo in diretta
def _scena(manage=True, posizione_ruolo=2):
    me = fake_member(999, roles=[fake_role(9, position=10)], guild_permissions=discord.Permissions(manage_roles=manage), bot=True)
    g = fake_guild(1, me=me)
    ruolo = fake_role(300, position=posizione_ruolo)
    membro = fake_member(5, roles=[]); membro.add_roles = AsyncMock(); membro.remove_roles = AsyncMock()
    g.get_role = MagicMock(return_value=ruolo); g.get_member = MagicMock(return_value=membro)
    return g, ruolo, membro


async def test_ruolo_live_dato_e_tolto():
    g, ruolo, membro = _scena()
    assert await aggiorna_ruolo_live(g, 5, 300, True)
    membro.add_roles.assert_awaited_once()
    membro.roles = [ruolo]
    assert await aggiorna_ruolo_live(g, 5, 300, True) is False  # già ce l'ha
    assert await aggiorna_ruolo_live(g, 5, 300, False)
    membro.remove_roles.assert_awaited_once()


async def test_ruolo_live_senza_permesso_o_sopra_il_bot_non_fa_nulla():
    g, _, membro = _scena(manage=False)
    assert await aggiorna_ruolo_live(g, 5, 300, True) is False
    g, _, membro = _scena(posizione_ruolo=50)
    assert await aggiorna_ruolo_live(g, 5, 300, True) is False
    membro.add_roles.assert_not_awaited()
    assert await aggiorna_ruolo_live(g, None, 300, True) is False


# ------------------------------------------------------------ watcher Kick
class _Sub:
    def __init__(self, i=1, slug="xqc", live=False, guild=1, canale=10):
        self.id, self.kick_slug, self.last_known_live = i, slug, live
        self.guild_id, self.channel_id = guild, canale
        self.label = "Xqc"
        self.live_message_template = "LIVE {label} {title} {game} {login}"
        self.offline_message_template = "FINE {label}"


@pytest.fixture
def mondo(monkeypatch):
    finto = RepoOpzioniFinto()
    monkeypatch.setattr("core.live_alert_flow.alert_options_repo", finto)
    canale = MagicMock(spec=discord.TextChannel); canale.id = 10
    canale.send = AsyncMock(return_value=MagicMock(id=555))
    g = fake_guild(1); g.get_channel = MagicMock(return_value=canale)
    bot = MagicMock(); bot.get_guild = MagicMock(return_value=g)
    aggiornati = []

    async def _agg(i, live):
        aggiornati.append((i, live))

    repo = MagicMock(get_all_subscriptions=AsyncMock(), update_last_known_live=_agg)
    monkeypatch.setattr(kw, "kick_subscription_repo", repo)

    async def _attive(subs):
        return subs

    monkeypatch.setattr(kw, "filtra_attive", _attive)
    return bot, canale, repo, aggiornati, finto


def _risposta(slug, live):
    return {"data": [{"slug": slug, "stream_title": "T", "category": {"name": "G"}, "stream": {"is_live": live}}]}


async def test_tick_live_pubblica_e_aggiorna_lo_stato(mondo):
    bot, canale, repo, aggiornati, _ = mondo
    repo.get_all_subscriptions.return_value = [_Sub()]
    w = kw.KickWatcherService()
    w._fetch_channels = AsyncMock(return_value=_risposta("xqc", True))
    await w.tick(bot)
    assert canale.send.await_args.args[0] == "LIVE Xqc T G xqc"
    assert canale.send.await_args.kwargs["view"].children[0].url == "https://kick.com/xqc"
    assert aggiornati == [(1, True)]
    await w.tick(bot)  # stesso stato nel database finto = ancora "non live": il fake non lo aggiorna, ma qui nulla cambia
    

async def test_tick_nessun_cambio_nessun_messaggio_e_offline_con_chiusura(mondo):
    bot, canale, repo, aggiornati, _ = mondo
    w = kw.KickWatcherService()
    repo.get_all_subscriptions.return_value = [_Sub(live=False)]
    w._fetch_channels = AsyncMock(return_value=_risposta("xqc", False))
    await w.tick(bot)
    canale.send.assert_not_awaited()
    repo.get_all_subscriptions.return_value = [_Sub(live=True)]
    await w.tick(bot)
    assert canale.send.await_args.args[0] == "FINE Xqc" and aggiornati == [(1, False)]


async def test_invio_fallito_non_avanza_lo_stato(mondo):
    bot, canale, repo, aggiornati, _ = mondo
    canale.send = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=500), "ko"))
    repo.get_all_subscriptions.return_value = [_Sub()]
    w = kw.KickWatcherService()
    w._fetch_channels = AsyncMock(return_value=_risposta("xqc", True))
    await w.tick(bot)
    assert aggiornati == []


async def test_oltre_50_canali_due_richieste_e_doppioni_tolti(mondo):
    bot, _, repo, _, _ = mondo
    subs = [_Sub(i=i, slug=f"c{i}") for i in range(60)] + [_Sub(i=100, slug="c0", guild=2)]
    repo.get_all_subscriptions.return_value = subs
    w = kw.KickWatcherService()
    w._fetch_channels = AsyncMock(return_value={"data": []})
    await w.tick(bot)
    assert w._fetch_channels.await_count == 2
    assert len(w._fetch_channels.await_args_list[0].args[0]) == 50


async def test_ruolo_live_collegato_al_membro_nel_giro(mondo):
    bot, canale, repo, aggiornati, finto = mondo
    finto.opzioni[("KK", 1)] = AlertOptions(live_member_id=5, delete_on_end=True)
    finto.ruoli[1] = 300
    g, ruolo, membro = _scena()
    bot.get_guild = MagicMock(return_value=g)
    g.get_channel = MagicMock(return_value=canale)
    repo.get_all_subscriptions.return_value = [_Sub()]
    w = kw.KickWatcherService()
    w._fetch_channels = AsyncMock(return_value=_risposta("xqc", True))
    await w.tick(bot)
    membro.add_roles.assert_awaited_once()
    assert finto.ultimi_messaggi[("KK", 1)] == 555  # per poterlo cancellare a fine diretta


async def test_senza_credenziali_non_parte_e_non_chiede_token(monkeypatch):
    monkeypatch.delenv("KICK_CLIENT_ID", raising=False)
    w = kw.KickWatcherService()
    assert await w._token() is None
    w.start(MagicMock())
    assert w._loop_task is None


# ------------------------------------------------------------ repository
async def test_tetto_per_server_atomico_con_richieste_insieme(clean_db):
    repo = KickSubscriptionRepository(lambda: clean_db)
    esiti = await asyncio.gather(*[repo.add_subscription(7, 1, f"c{i}", "L", 1, max_per_guild=3) for i in range(8)])
    assert sum(e is not None for e in esiti) == 3
    assert len(await repo.list_subscriptions(7)) == 3
    sub = (await repo.list_subscriptions(7))[0]
    assert sub.kick_slug.startswith("c") and "{login}" in sub.live_message_template
    assert await repo.remove_subscription(sub.id, 8) is False  # un altro server non può cancellarla
    assert await repo.remove_subscription(sub.id, 7) is True


async def test_opzioni_e_ruolo_live_nel_database(clean_db):
    repo = AlertOptionsRepository(lambda: clean_db)
    assert await repo.get("TW", 1) == AlertOptions()
    await repo.set_fields("TW", 1, 7, notify_end=False, mention_role_id=4)
    await repo.set_fields("TW", 1, 7, delete_on_end=True)
    o = await repo.get("TW", 1)
    assert (o.notify_end, o.mention_role_id, o.delete_on_end, o.watch_button) == (False, 4, True, True)
    await repo.set_last_message("TW", 1, 7, 123)
    assert (await repo.get_many("TW", [1, 2]))[1].last_message_id == 123
    with pytest.raises(ValueError):
        await repo.set_fields("TW", 1, 7, nope=1)
    await repo.delete("TW", 1, 7)
    assert await repo.get_many("TW", [1]) == {}
    assert await repo.get_live_role(7) is None
    await repo.set_live_role(7, 55); await repo.set_live_role(7, 56)
    assert await repo.get_live_roles([7, 8]) == {7: 56}
    await repo.set_live_role(7, None)
    assert await repo.get_live_role(7) is None
