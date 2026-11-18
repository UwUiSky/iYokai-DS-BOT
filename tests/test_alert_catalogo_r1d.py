"""
tests/test_alert_catalogo_r1d.py
================================
Catalogo «Alert social» (#129), blocco 5: ruolo «in diretta» automatico (ALR-042 .. 048). Logica pura, regole
su PostgreSQL vero e comandi con interazioni finte fedeli.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
import pytest_asyncio

import cogs.utility.alert_ruolo_live as cog_mod
from cogs.utility.alert_ruolo_live import AlertRuoloLiveCog, ruolo_assegnabile
from core import live_role_logic as lr
from core.database import Database
from core.repositories.live_role_repo import MAX_REGOLE, MAX_VOCI, LiveRoleRepository, RegolaLive
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role, fake_text_channel

GUILD = 900000142
ADESSO = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)


def _regola(**kw):
    base = dict(id=1, guild_id=GUILD, role_id=300)
    base.update(kw)
    return RegolaLive(**base)


def _diretta(titolo="Torneo di prova", gioco="Valorant", url="https://www.twitch.tv/x"):
    return lr.Diretta(titolo, gioco, url)


# ------------------------------------------------------------------ logica pura
def test_alr042_attivita_streaming_con_link_sicuro():
    """ALR-042: il ruolo segue lo stato «in diretta» di Discord; solo link di siti di dirette noti."""
    s = discord.Streaming(name="Twitch", url="https://www.twitch.tv/nome", details="<b>Titolo</b> @everyone", state="Valorant")
    d = lr.diretta_da_attivita([discord.Game("altro"), s])
    assert d.gioco == "Valorant" and d.url == "https://www.twitch.tv/nome" and "<b>" not in d.titolo
    assert lr.diretta_da_attivita([discord.Game("solo gioco")]) is None and lr.diretta_da_attivita([]) is None
    cattivo = discord.Streaming(name="Twitch", url="https://evil.example/twitch.tv", details="x")
    assert lr.diretta_da_attivita([cattivo]).url == ""
    assert lr.indirizzo_diretta("http://twitch.tv/x") == "" and lr.indirizzo_diretta("https://twitch.tv.evil.example/x") == ""


def test_alr043_solo_chi_ha_un_ruolo():
    r = _regola(only_role_id=7)
    assert lr.regola_ammette(r, 1, {7, 8}, _diretta()) and not lr.regola_ammette(r, 1, {8}, _diretta())
    assert lr.regola_ammette(_regola(), 1, set(), _diretta())  # nessun ruolo richiesto: tutti


def test_alr044_esclusi_vincono_su_tutto():
    r = _regola(esclusi_membri=frozenset({5}), esclusi_ruoli=frozenset({9}), eccezioni=frozenset({5, 6}))
    assert not lr.regola_ammette(r, 5, set(), _diretta())  # escluso e anche in eccezione: vince l'esclusione
    assert not lr.regola_ammette(r, 1, {9}, _diretta())
    assert lr.regola_ammette(r, 1, {10}, _diretta())


def test_alr045_parole_e_giochi():
    r = _regola(keywords="torneo, -replica", games="Valorant, Just Chatting")
    assert lr.regola_ammette(r, 1, set(), _diretta("Grande TORNEO", "valorant"))
    assert not lr.regola_ammette(r, 1, set(), _diretta("Torneo replica", "Valorant"))
    assert not lr.regola_ammette(r, 1, set(), _diretta("Chiacchiere", "Valorant"))
    assert not lr.regola_ammette(r, 1, set(), _diretta("Torneo", "Minecraft"))
    assert lr.regola_ammette(_regola(keywords="-replica"), 1, set(), _diretta("Live"))


def test_alr046_eccezioni_saltano_i_filtri_ma_non_il_ruolo_richiesto():
    r = _regola(keywords="torneo", games="Valorant", only_role_id=7, eccezioni=frozenset({4}))
    assert lr.regola_ammette(r, 4, {7}, _diretta("Chiacchiere", "Minecraft"))
    assert not lr.regola_ammette(r, 4, set(), _diretta("Torneo", "Valorant"))  # il ruolo richiesto serve comunque


def _membro(uid=5, ruoli=()):
    m = fake_member(uid, roles=list(ruoli))
    m.display_name = "Nome @everyone"
    return m


async def test_alr042_048_applica_piu_regole_da_e_toglie(monkeypatch):
    """ALR-048: più regole nello stesso server; ognuna dà o toglie il suo ruolo."""
    chiamate = []

    async def finto(guild, membro_id, role_id, in_diretta):
        chiamate.append((role_id, in_diretta))
        return True

    monkeypatch.setattr(lr, "aggiorna_ruolo_live", finto)
    lr._azzera_annunci_per_test()
    regole = [_regola(id=1, role_id=300), _regola(id=2, role_id=301, games="Minecraft"), _regola(id=3, role_id=302, only_role_id=77)]
    guild = fake_guild(GUILD)
    await lr.applica_regole(guild, _membro(), regole, _diretta(), ADESSO)
    assert chiamate == [(300, True)]  # solo la prima: gioco diverso per la seconda, ruolo richiesto per la terza
    chiamate.clear()
    ruolo = fake_role(300); ruolo.id = 300
    await lr.applica_regole(guild, _membro(ruoli=[ruolo]), regole, None, ADESSO)  # diretta finita: lo toglie
    assert chiamate == [(300, False)]
    chiamate.clear()
    bot = _membro(); bot.bot = True
    await lr.applica_regole(guild, bot, regole, _diretta(), ADESSO)
    assert chiamate == []


async def test_alr047_annuncio_con_pausa_per_membro_e_senza_ping(monkeypatch):
    lr._azzera_annunci_per_test()
    canale = MagicMock(spec=discord.TextChannel)
    canale.permissions_for.return_value = discord.Permissions(send_messages=True)
    canale.send = AsyncMock()
    guild = fake_guild(GUILD); guild.get_channel = MagicMock(return_value=canale); guild.me = MagicMock()
    regola = _regola(announce_channel_id=10, announce_template="{utente} gioca a {gioco} {link}", announce_gap_minutes=60)
    m = _membro()
    assert await lr.annuncia(guild, m, regola, _diretta(), ADESSO) is True
    testo = canale.send.await_args.args[0]
    assert "@everyone" not in testo.replace("@​everyone", "") and "Valorant" in testo
    assert canale.send.await_args.kwargs["allowed_mentions"].everyone is False
    assert await lr.annuncia(guild, m, regola, _diretta(), ADESSO + timedelta(minutes=30)) is False  # dentro la pausa
    assert await lr.annuncia(guild, m, regola, _diretta(), ADESSO + timedelta(minutes=61)) is True
    assert await lr.annuncia(guild, _membro(6), regola, _diretta(), ADESSO) is True  # un altro membro ha la sua pausa
    senza_canale = _regola(announce_channel_id=None)
    assert await lr.annuncia(guild, m, senza_canale, _diretta(), ADESSO) is False
    canale.permissions_for.return_value = discord.Permissions(send_messages=False)
    assert await lr.annuncia(guild, _membro(9), regola, _diretta(), ADESSO) is False


def test_ruolo_assegnabile_controlla_gerarchia_e_ruoli_dei_bot():
    guild = MagicMock()
    guild.me.guild_permissions = discord.Permissions(manage_roles=True)
    sopra = MagicMock(spec=discord.Role); sopra.is_default.return_value = False; sopra.managed = False
    sopra.__ge__ = lambda s, a: True
    assert ruolo_assegnabile(sopra, guild) == "alertlive_ruolo_sopra_il_bot"
    gestito = MagicMock(spec=discord.Role); gestito.is_default.return_value = False; gestito.managed = True
    assert ruolo_assegnabile(gestito, guild) == "alertlive_ruolo_non_valido"
    ok = MagicMock(spec=discord.Role); ok.is_default.return_value = False; ok.managed = False
    ok.__ge__ = lambda s, a: False
    assert ruolo_assegnabile(ok, guild) is None
    guild.me.guild_permissions = discord.Permissions(manage_roles=False)
    assert ruolo_assegnabile(ok, guild) == "alertlive_ruolo_sopra_il_bot"


def _ruolo_sotto_il_bot(**permessi):
    ruolo = MagicMock(spec=discord.Role)
    ruolo.is_default.return_value = False
    ruolo.managed = False
    ruolo.name = "Streamer"
    ruolo.permissions = discord.Permissions(**permessi)
    ruolo.__ge__ = lambda s, a: False
    return ruolo


def _server_con(ruolo, membro):
    guild = MagicMock()
    guild.id = GUILD
    guild.owner_id = 1
    guild.me.guild_permissions = discord.Permissions(manage_roles=True)
    guild.get_role = lambda rid: ruolo
    guild.get_member = lambda mid: membro
    return guild


@pytest.mark.asyncio
async def test_ruolo_live_con_permessi_pericolosi_non_viene_mai_dato():
    """Un ruolo che ha preso Amministratore dopo la regola non arriva a chi va in diretta."""
    membro = MagicMock(); membro.bot = False; membro.roles = []; membro.add_roles = AsyncMock()
    ruolo = _ruolo_sotto_il_bot(administrator=True)
    assert await lr.aggiorna_ruolo_live(_server_con(ruolo, membro), 5, 300, True) is False
    membro.add_roles.assert_not_awaited()
    sicuro = _ruolo_sotto_il_bot(send_messages=True)
    assert await lr.aggiorna_ruolo_live(_server_con(sicuro, membro), 5, 300, True) is True
    membro.add_roles.assert_awaited_once()


@pytest.mark.asyncio
async def test_regola_con_ruolo_pericoloso_rifiutata(monkeypatch):
    """Lo staff non può creare una regola con un ruolo che ha permessi pericolosi."""
    aggiungi = AsyncMock(return_value=1)
    monkeypatch.setattr(cog_mod.live_role_repo, "aggiungi", aggiungi)
    ruolo = _ruolo_sotto_il_bot(ban_members=True)
    inter = MagicMock()
    inter.guild = _server_con(ruolo, None)
    inter.user.id = 2
    inter.user.top_role = MagicMock()
    inter.response.send_message = AsyncMock()
    cog = AlertRuoloLiveCog(MagicMock())
    await AlertRuoloLiveCog.aggiungi.callback(cog, inter, ruolo)
    aggiungi.assert_not_awaited()
    assert "ban_members" in inter.response.send_message.await_args.args[0]


# ------------------------------------------------------------------ database e comandi
@pytest_asyncio.fixture
async def ambiente(monkeypatch):
    database = Database()
    await database.connect()
    await database.run_migrations()
    repo = LiveRoleRepository(pool_provider=lambda: database.pool)
    monkeypatch.setattr(cog_mod, "live_role_repo", repo)
    monkeypatch.setattr(cog_mod, "chiede_intent_presenze", lambda: True)
    yield database, repo
    await database.pool.execute("DELETE FROM live_role_regole WHERE guild_id = ANY($1::bigint[])", [GUILD, GUILD + 1])
    await database.close()


async def test_alr048_repo_tetti_e_voci(ambiente):
    _, repo = ambiente
    ids = [await repo.aggiungi(GUILD, 300 + i, 1) for i in range(MAX_REGOLE)]
    assert None not in ids and await repo.aggiungi(GUILD, 999, 1) is None  # tetto di 5
    assert await repo.aggiungi(GUILD + 1, 300, 1) is not None  # un altro server ha le sue
    for n in range(MAX_VOCI):
        assert await repo.voce(GUILD, ids[0], "eccezione", 1000 + n, True) == "ok"
    assert await repo.voce(GUILD, ids[0], "eccezione", 5000, True) == "pieno"
    assert await repo.voce(GUILD + 1, ids[0], "eccezione", 1, True) == "manca"  # la regola è di un altro server
    assert await repo.voce(GUILD, ids[0], "eccezione", 1000, False) == "ok"
    regole = await repo.regole(GUILD)
    assert len(regole) == 5 and len(regole[0].eccezioni) == MAX_VOCI - 1
    assert await repo.rimuovi(GUILD + 1, ids[0]) is False and await repo.rimuovi(GUILD, ids[0]) is True
    assert await ambiente[0].pool.fetchval("SELECT count(*) FROM live_role_voci WHERE regola_id = $1", ids[0]) == 0  # a cascata


def _ruolo_ok(rid):
    r = MagicMock(spec=discord.Role); r.id = rid; r.name = f"Ruolo{rid}"
    r.is_default.return_value = False; r.managed = False
    r.permissions = discord.Permissions.none()
    r.__ge__ = lambda s, a: False
    return r


def _i(user_id=42):
    g = fake_guild(GUILD)
    g.me = MagicMock(); g.me.guild_permissions = discord.Permissions(manage_roles=True)
    return fake_interaction(guild=g, user=fake_member(user_id))


def _testo(i):
    c = i.response.send_message.call_args
    return c.args[0] if c.args else c.kwargs.get("content", "")


async def test_alr042_048_comandi_aggiungi_filtri_esclusi_eccezioni_annuncio(ambiente):
    _, repo = ambiente
    cog = AlertRuoloLiveCog(bot=MagicMock())
    i = _i(); await cog.aggiungi.callback(cog, i, _ruolo_ok(300), _ruolo_ok(77))
    assert "Regola" in _testo(i)
    n = (await repo.regole(GUILD))[0].id
    i = _i(); await cog.filtri.callback(cog, i, n, "torneo, -replica", "Valorant", None, False)
    i = _i(); await cog.esclusi.callback(cog, i, n, _ruolo_ok(9), False)
    membro = fake_member(55)
    i = _i(); await cog.esclusi.callback(cog, i, n, membro, False)
    i = _i(); await cog.eccezioni.callback(cog, i, n, fake_member(66), False)
    canale = fake_text_channel(); canale.id = 123; canale.guild = MagicMock(); canale.guild.id = GUILD
    canale.permissions_for.return_value = discord.Permissions(view_channel=True, send_messages=True)
    i = _i(); await cog.annuncio.callback(cog, i, n, canale, "{utente} è live", 30)
    r = (await repo.regole(GUILD))[0]
    assert (r.only_role_id, r.keywords, r.games, r.announce_channel_id, r.announce_gap_minutes) == (77, "torneo, -replica", "Valorant", 123, 30)
    assert r.esclusi_ruoli == {9} and r.esclusi_membri == {55} and r.eccezioni == {66}
    i = _i(); await cog.filtri.callback(cog, i, n, "-", "-", None, True)  # toglie parole, giochi e ruolo richiesto
    r = (await repo.regole(GUILD))[0]
    assert (r.only_role_id, r.keywords, r.games) == (None, "", "")
    i = _i(); await cog.elenco.callback(cog, i)
    assert f"**{n}**" in _testo(i)
    i = _i(); await cog.filtri.callback(cog, i, 999999, None, None, None, False)
    assert "Non trovo" in _testo(i)
    i = _i(); await cog.rimuovi.callback(cog, i, n)
    assert "rimossa" in _testo(i) and await repo.regole(GUILD) == []


async def test_alr042_presenze_spente_e_aggiornamenti_inutili(ambiente, monkeypatch):
    _, repo = ambiente
    cog = AlertRuoloLiveCog(bot=MagicMock())
    applica = AsyncMock()
    monkeypatch.setattr(cog_mod, "applica_regole", applica)
    prima = MagicMock(activities=[]); dopo = MagicMock(activities=[], bot=False)
    dopo.guild = fake_guild(GUILD)
    await cog.on_presence_update(prima, dopo)  # nessuna attività «in diretta»: niente da fare, nemmeno una query
    applica.assert_not_awaited()
    await repo.aggiungi(GUILD, 300, 1)
    live = MagicMock(activities=[discord.Streaming(name="Twitch", url="https://www.twitch.tv/a", details="x")], bot=False)
    live.guild = fake_guild(GUILD)
    await cog.on_presence_update(prima, live)
    assert applica.await_count == 1
    await cog.on_presence_update(live, live)  # stessa diretta: niente
    assert applica.await_count == 1
    monkeypatch.setattr(cog_mod, "chiede_intent_presenze", lambda: False)
    await cog.on_presence_update(prima, live)
    assert applica.await_count == 1
    # il bot stesso e gli altri bot non contano
    monkeypatch.setattr(cog_mod, "chiede_intent_presenze", lambda: True)
    live.bot = True
    await cog.on_presence_update(prima, live)
    assert applica.await_count == 1
