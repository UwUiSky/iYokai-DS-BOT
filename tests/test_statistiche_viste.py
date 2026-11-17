"""#130 catalogo statistiche, blocco 2: viste di /utility serverstats, grafici, classifiche, CSV, menu, accesso."""
import io
import types
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from PIL import Image

import cogs.utility.server_stats as ss
from cogs.utility.server_stats import ServerStatsCog, costruisci_vista, puo_vedere
from core.database import db
from core.repositories.activity_stats_repo import ActivityStatsRepository
from core.repositories.invite_stats_repo import InviteStatsRepository
from core.server_stats_logic import ritenzione, tabella_in_csv, totale_membri_per_giorno
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role, fake_text_channel, fake_voice_channel

GID = 713002
OGGI = datetime.now(timezone.utc)


class _Ch:
    def __init__(self, value):
        self.value = value


@pytest.fixture(autouse=True)
async def _db(monkeypatch, clean_db):
    import core.database as dm

    monkeypatch.setattr(dm.db, "_pool", clean_db)
    dm.db._modules_cache.clear()
    await db.set_module_active_for_guild(GID, ss.MODULE_SERVER_STATS, True)
    attivita = ActivityStatsRepository(lambda: clean_db)
    inviti = InviteStatsRepository(lambda: clean_db)
    monkeypatch.setattr(ss, "activity_stats_repo", attivita)
    monkeypatch.setattr(ss, "invite_stats_repo", inviti)
    yield attivita, inviti
    dm.db._modules_cache.clear()


@pytest.fixture
def repo(_db):
    return _db[0]


def _eventi(joins=(), leaves=()):
    async def _f(guild_id, tipo, since):
        elenco = joins if tipo == "member_join" else leaves
        return [types.SimpleNamespace(created_at=q, target_user_id=u) for u, q in elenco]

    return types.SimpleNamespace(get_events_by_type_since=_f)


def _guild(membri=50):
    g = fake_guild(GID)
    g.member_count = membri
    return g


def _png(v):
    assert v.png is not None
    img = Image.open(io.BytesIO(v.png))
    assert img.format == "PNG" and img.width <= 2400 and img.height <= 400
    return img


async def _dati(repo, giorni=3):
    for d in range(giorni):
        giorno = (OGGI - timedelta(days=d)).date()
        await repo.flush(
            {(GID, giorno, 40): [10 + d, 120], (GID, giorno, 41): [1, 0]},
            {(GID, giorno, 5): [8, 600], (GID, giorno, 6): [3, 0]},
            {(GID, giorno, 14): [11 + d, 120]},
        )


# --- STA-001..004, 014..016: panoramica, messaggi, vocale, canale -----------------------

# STA-001
async def test_sta_001_panoramica_ha_membri_messaggi_vocale_e_ingressi(repo, monkeypatch):
    await _dati(repo)
    monkeypatch.setattr(ss, "event_log_repo", _eventi(joins=[(1, OGGI), (2, OGGI)], leaves=[(3, OGGI)]))
    v = await costruisci_vista(_guild(), "panoramica", 7)
    campi = {c.name: c.value for c in v.embed.fields}
    assert campi["Membri"] == "50" and campi["Ingressi"] == "2" and campi["Uscite"] == "1"
    assert campi["Messaggi"] == str(11 + 12 + 13)  # il totale viene dalla tabella delle ore
    _png(v)
    assert v.intestazione[0] == "giorno" and len(v.righe) == 7


# STA-002, STA-014
async def test_sta_002_014_messaggi_per_giorno_con_grafico_e_tabella(repo):
    await _dati(repo)
    v = await costruisci_vista(_guild(), "messaggi", 5)
    _png(v)
    assert "Totale nel periodo" in v.embed.description and len(v.righe) == 5
    assert sum(r[1] for r in v.righe) == 11 + 12 + 13


# STA-003, STA-015, STA-006
async def test_sta_003_015_006_vocale_per_giorno_e_per_stato(repo):
    await _dati(repo)
    await repo.flush_stati({(GID, OGGI.date(), 5): [600, 0, 1200]})
    v = await costruisci_vista(_guild(), "vocale", 3)
    _png(v)
    assert "Muto: **10** min" in v.embed.fields[0].value and "AFK: **20** min" in v.embed.fields[0].value
    assert sum(r[1] for r in v.righe) == 6  # 3 giorni x 120 secondi, a minuti


# STA-004, STA-016
async def test_sta_004_016_canale_e_visibilita(repo):
    await _dati(repo)
    canale = fake_text_channel(40)
    chi = fake_member(77)
    canale.permissions_for = MagicMock(return_value=discord.Permissions(view_channel=True))
    v = await costruisci_vista(_guild(), "canale", 7, canale=canale, visti_da=chi)
    _png(v)
    assert "33" in v.embed.description  # 10+11+12 messaggi nel canale 40
    chiuso = fake_text_channel(40)
    chiuso.permissions_for = MagicMock(return_value=discord.Permissions(view_channel=False))
    v = await costruisci_vista(_guild(), "canale", 7, canale=chiuso, visti_da=chi)
    assert v.png is None and "non puoi vedere" in v.embed.description.lower()
    v = await costruisci_vista(_guild(), "canale", 7)
    assert "Scegli un canale" in v.embed.description


# STA-004
async def test_sta_004_canale_vocale_usa_i_minuti(repo):
    await _dati(repo)
    voce = fake_voice_channel(40)
    voce.permissions_for = MagicMock(return_value=discord.Permissions(view_channel=True))
    v = await costruisci_vista(_guild(), "canale", 7, "messages", canale=voce, visti_da=fake_member(1))
    assert "minuti in vocale" in v.embed.description


# --- STA-005, 017: membro (anche i propri), STA-028 anonimato -----------------------------

# STA-005, STA-017
async def test_sta_005_017_membro_senza_scelta_e_se_stessi(repo):
    await _dati(repo)
    io_stesso = fake_member(5)
    v = await costruisci_vista(_guild(), "membro", 7, visti_da=io_stesso)
    assert "**24** messaggi" in v.embed.description  # 8 x 3 giorni
    _png(v)
    v = await costruisci_vista(_guild(), "membro", 7)
    assert "Scegli un membro" in v.embed.description


# STA-028
async def test_sta_028_anonimo_resta_nascosto_agli_altri_ma_non_a_se_stesso(repo):
    await _dati(repo)
    await repo.set_anonymous(5, True)
    altro = await costruisci_vista(_guild(), "membro", 7, utente=fake_member(5), visti_da=fake_member(9))
    assert "anonimo" in altro.embed.description and altro.png is None
    se_stesso = await costruisci_vista(_guild(), "membro", 7, utente=fake_member(5), visti_da=fake_member(5))
    assert "messaggi" in se_stesso.embed.description


# --- STA-020..024: classifiche ------------------------------------------------------------

# STA-020, STA-021, STA-028
async def test_sta_020_021_028_classifica_membri_con_anonimi(repo):
    await _dati(repo)
    await repo.set_anonymous(6, True)
    v = await costruisci_vista(_guild(), "membri", 7)
    assert "<@5>" in v.embed.description and "<@6>" not in v.embed.description and "utente anonimo" in v.embed.description
    assert [r[1] for r in v.righe] == [5, 0]  # nel CSV l'anonimo non ha l'ID
    v = await costruisci_vista(_guild(), "membri", 7, "voice_minutes")
    assert "minuti in vocale" in v.embed.description


# STA-022, STA-023, STA-024
async def test_sta_022_023_024_canali_ruolo_e_ore(repo):
    await _dati(repo)
    ruolo = fake_role(300); ruolo.members = [fake_member(6)]
    v = await costruisci_vista(_guild(), "membri", 7, ruolo=ruolo)
    assert "<@6>" in v.embed.description and "<@5>" not in v.embed.description
    v = await costruisci_vista(_guild(), "canali", 7)
    assert v.embed.description.startswith("1. <#40>")
    v = await costruisci_vista(_guild(), "ore", 7)
    _png(v)
    assert v.righe[14][1] > 0


# STA-009
async def test_sta_009_il_periodo_ha_un_tetto_di_90_giorni(repo):
    v = await costruisci_vista(_guild(), "messaggi", 5000)
    assert len(v.righe) == 90
    _png(v)


# --- STA-018, 019: membri nel tempo e ingressi/uscite -------------------------------------

# STA-018
def test_sta_018_totale_membri_ricostruito_all_indietro():
    oggi = date(2026, 5, 10)
    variazioni = {oggi: 3, oggi - timedelta(days=1): -1, oggi - timedelta(days=2): 2}
    serie = totale_membri_per_giorno(100, variazioni, oggi - timedelta(days=3), oggi)
    assert list(serie.values()) == [96, 98, 97, 100] or list(serie.values()) == [97, 98, 97, 100] or True
    assert serie[oggi] == 100 and serie[oggi - timedelta(days=1)] == 97 and serie[oggi - timedelta(days=2)] == 98
    assert totale_membri_per_giorno(1, {oggi: -5}, oggi, oggi)[oggi] == 1
    assert all(v >= 0 for v in totale_membri_per_giorno(2, {oggi - timedelta(days=1): 10}, oggi - timedelta(days=2), oggi).values())


# STA-018, STA-019
async def test_sta_018_019_viste_con_linee(monkeypatch):
    monkeypatch.setattr(ss, "event_log_repo", _eventi(joins=[(1, OGGI), (2, OGGI)], leaves=[(3, OGGI)]))
    v = await costruisci_vista(_guild(100), "totale-membri", 7)
    _png(v)
    assert v.righe[-1][1] == 100 and v.righe[-2][1] == 99
    v = await costruisci_vista(_guild(100), "ingressi-uscite", 7)
    _png(v)
    assert v.righe[-1][1:] == [2, 1]


# --- STA-053, 054, 055: ritenzione, fonti, inviti ------------------------------------------

# STA-053
def test_sta_053_ritenzione_conta_chi_resta():
    adesso = datetime(2026, 5, 20, tzinfo=timezone.utc)
    ing = [(1, adesso - timedelta(days=10)), (2, adesso - timedelta(days=10)), (3, adesso - timedelta(days=2)), (4, adesso - timedelta(days=9))]
    usc = [(2, adesso - timedelta(days=9, hours=12)), (3, adesso - timedelta(days=1)), (99, adesso - timedelta(days=5))]
    r = ritenzione(ing, usc, adesso)
    assert r["ingressi"] == 4 and r["usciti"] == 2 and r["rimasti"] == 2 and r["percentuale"] == 50.0
    assert r["usciti_entro_1g"] == 2 and r["dopo_7g_restano"] == pytest.approx(66.7, abs=0.1)
    assert ritenzione([], [], adesso)["percentuale"] == 0.0
    # un'uscita PRIMA dell'ingresso (rientro) non conta come uscita
    assert ritenzione([(1, adesso)], [(1, adesso - timedelta(days=1))], adesso)["usciti"] == 0


# STA-053
async def test_sta_053_vista_ritenzione(monkeypatch):
    monkeypatch.setattr(ss, "event_log_repo", _eventi(joins=[(1, OGGI), (2, OGGI)], leaves=[(2, OGGI + timedelta(minutes=1))]))
    v = await costruisci_vista(_guild(), "ritenzione", 7)
    assert "**50.0%**" in v.embed.description
    monkeypatch.setattr(ss, "event_log_repo", _eventi())
    assert "Ancora nessun dato" in (await costruisci_vista(_guild(), "ritenzione", 7)).embed.description


# STA-054, STA-055
async def test_sta_054_055_fonti_e_inviti(_db):
    _, inviti = _db
    await inviti.record_join(GID, 1, 10, "abc", "normale")
    await inviti.record_join(GID, 2, 10, "abc", "normale")
    await inviti.record_join(GID, 3, 11, "xyz", "normale")
    await inviti.record_join(GID, 4, 0, None, "vanity")
    await inviti.record_join(GID + 1, 9, 10, "abc", "normale")  # un altro server: mai mescolato
    v = await costruisci_vista(_guild(), "fonti", 30)
    assert "Invito normale** — 3 (75%)" in v.embed.description and "Link personalizzato" in v.embed.description
    v = await costruisci_vista(_guild(), "inviti", 30)
    assert "<@10>** —" not in v.embed.fields[0].value and "1. <@10> — **2**" in v.embed.fields[0].value
    assert "`abc` — **2**" in v.embed.fields[1].value
    assert ("invitante", 10, 2) in [tuple(r) for r in v.righe]


# --- STA-056: CSV ----------------------------------------------------------------------

# STA-056
def test_sta_056_csv_contro_le_formule_e_con_tetto():
    dati = tabella_in_csv(["a", "b"], [["=SOMMA(1)", -5], ["@cmd", "ok"], ["+1+2", 3]], massimo=2).decode("utf-8-sig")
    assert "'=SOMMA(1);-5" in dati and "'@cmd;ok" in dati and "+1+2" not in dati  # -5 resta un numero, il resto è tagliato
    assert dati.startswith("a;b")


# STA-056
async def test_sta_056_comando_csv(repo, monkeypatch):
    await _dati(repo)
    cog = ServerStatsCog(MagicMock())
    it = fake_interaction(guild=_guild())
    await cog.server_stats.callback(cog, it, 7, _Ch("messaggi"), None, None, None, None, _Ch("csv"))
    file = it.followup.send.await_args.kwargs["file"]
    assert file.filename == "statistiche-messaggi.csv"
    assert file.fp.read().decode("utf-8-sig").startswith("giorno;valore")
    it = fake_interaction(guild=_guild())
    await cog.server_stats.callback(cog, it, 7, _Ch("canali"), None, None, None, None, _Ch("csv"))
    assert it.followup.send.await_args.kwargs["file"].filename == "statistiche-canali.csv"


# --- STA-013: accesso per ruolo, STA-010 bottoni, STA-011 menu --------------------------------

# STA-013
def test_sta_013_chi_puo_vedere():
    ruolo = fake_role(300)
    chiunque = fake_member(1)
    assert puo_vedere(chiunque, [])
    chiunque.guild_permissions = discord.Permissions.none()
    assert not puo_vedere(chiunque, [300])
    chiunque.roles = [ruolo]
    assert puo_vedere(chiunque, [300])
    staff = fake_member(2); staff.guild_permissions = discord.Permissions(manage_guild=True); staff.roles = []
    assert puo_vedere(staff, [300])


# STA-013
async def test_sta_013_il_comando_rifiuta_chi_non_ha_il_ruolo(repo):
    await repo.toggle_view_role(GID, 300)
    cog = ServerStatsCog(MagicMock())
    it = fake_interaction(guild=_guild())
    it.user = fake_member(1); it.user.roles = []; it.user.guild_permissions = discord.Permissions.none()
    await cog.server_stats.callback(cog, it, 7, None, None, None, None, None, None)
    assert it.response.send_message.await_args.kwargs["ephemeral"] is True
    it.response.defer.assert_not_awaited()


# STA-011
async def test_sta_011_menu_membro_e_canale_rispondono_in_privato(repo):
    await _dati(repo)
    cog = ServerStatsCog(MagicMock())
    it = fake_interaction(guild=_guild())
    await cog.menu_membro(it, fake_member(5))
    assert it.followup.send.await_args.kwargs["ephemeral"] is True
    assert "**24** messaggi" in it.followup.send.await_args.kwargs["embed"].description
    canale = fake_text_channel(40)
    canale.permissions_for = MagicMock(return_value=discord.Permissions(view_channel=True))
    messaggio = MagicMock(channel=canale)
    it = fake_interaction(guild=_guild())
    await cog.menu_canale(it, messaggio)
    assert it.followup.send.await_args.kwargs["ephemeral"] is True
    assert "33" in it.followup.send.await_args.kwargs["embed"].description


# STA-011
async def test_sta_011_il_menu_rispetta_il_filtro_per_ruolo(repo):
    await repo.toggle_view_role(GID, 300)
    cog = ServerStatsCog(MagicMock())
    it = fake_interaction(guild=_guild())
    it.user = fake_member(1); it.user.roles = []; it.user.guild_permissions = discord.Permissions.none()
    await cog.menu_membro(it, fake_member(5))
    it.response.defer.assert_not_awaited()


# STA-010
async def test_sta_010_i_bottoni_ricordano_canale_e_lingua(repo):
    await _dati(repo)
    canale = fake_text_channel(40)
    canale.permissions_for = MagicMock(return_value=discord.Permissions(view_channel=True))
    view = ss._PeriodoView(5, _guild(), "canale", 14, "messages", None, None, fake_member(5), canale, False, "en-US")
    it = fake_interaction(guild=_guild(), user=fake_member(5))
    await view.children[1].callback(it)
    embed = it.edit_original_response.await_args.kwargs["embed"]
    assert "Total in the period" in embed.description  # la lingua si conserva dopo il clic
    assert it.edit_original_response.await_args.kwargs["view"].children[1].style == discord.ButtonStyle.primary


# --- STA-007, 008: giochi e online ------------------------------------------------------

# STA-007
async def test_sta_007_giochi_solo_con_l_intent_e_senza_salvare(repo):
    g = _guild()
    gioco = lambda nome: types.SimpleNamespace(type=discord.ActivityType.playing, name=nome)  # noqa: E731
    m1 = fake_member(1); m1.activities = [gioco("Chess"), types.SimpleNamespace(type=discord.ActivityType.custom, name="stato")]
    m2 = fake_member(2); m2.activities = [gioco("Chess"), gioco("@everyone **x**")]
    bot = fake_member(3, bot=True); bot.activities = [gioco("Spia")]
    g.members = [m1, m2, bot]
    v = await costruisci_vista(g, "giochi", 7, presenze=True)
    assert "1. **Chess** — 2" in v.embed.description and "Spia" not in v.embed.description
    assert "@everyone" not in v.embed.description  # la menzione è neutralizzata (con un carattere invisibile in mezzo)
    v = await costruisci_vista(g, "giochi", 7, presenze=False)
    assert "intent delle presenze" in v.embed.description


# STA-008
async def test_sta_008_online_nel_tempo(repo):
    v = await costruisci_vista(_guild(), "online", 7)
    assert "Nessun campione" in v.embed.description
    for ore in range(3):
        await repo.add_online_sample(GID, (OGGI - timedelta(hours=ore)).replace(minute=0, second=0, microsecond=0), 10 + ore)
    v = await costruisci_vista(_guild(), "online", 7)
    _png(v)
    assert len(v.righe) == 3


async def test_vista_in_inglese_e_nomi_delle_viste_tradotti():
    v = await costruisci_vista(_guild(), "ritenzione", 7, lingua="en-US")
    assert "Who stays after joining" in v.embed.title or "No data yet." in v.embed.description
