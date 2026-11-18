"""#130 catalogo statistiche, blocco 1: raccolta (stato della voce), filtri, accesso, anonimato, regole a due condizioni."""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.utility.activity_stats import MODULE_SERVER_STATS, ActivityStatsCog
from core.activity_stats_logic import (
    ActivityBuffer,
    VoiceTracker,
    canali_del_messaggio,
    conta_secondo_i_filtri,
    regola_con_due_condizioni,
)
from core.database import db
from core.repositories.activity_stats_repo import ActivitySettings, ActivityStatsRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_message, fake_role, fake_text_channel

GID = 713001
T0 = datetime(2026, 5, 4, 15, 0, tzinfo=timezone.utc)


class _Ch:
    def __init__(self, value):
        self.value = value


@pytest.fixture(autouse=True)
async def _db(monkeypatch, clean_db):
    import core.database as dm

    monkeypatch.setattr(dm.db, "_pool", clean_db)
    dm.db._modules_cache.clear()
    await db.set_module_active_for_guild(GID, MODULE_SERVER_STATS, True)
    yield
    dm.db._modules_cache.clear()


@pytest.fixture
def cog(clean_db):
    bot = MagicMock()
    bot.guilds = []
    return ActivityStatsCog(bot, repo=ActivityStatsRepository(lambda: clean_db))


@pytest.fixture
def repo(clean_db):
    return ActivityStatsRepository(lambda: clean_db)


def _msg(autore, canale, guild):
    m = fake_message(author=autore, channel=canale, guild=guild)
    m.webhook_id = None
    m.type = discord.MessageType.default
    return m


# --- STA-006: tempo in vocale diviso per stato -------------------------------

# STA-006
def test_sta_006_tracker_divide_il_tempo_per_stato():
    v = VoiceTracker()
    v.entra(GID, 10, 1, T0)
    assert v.cambia_stato(GID, 1, T0 + timedelta(seconds=60), muto=True, sordo=False) == [(GID, 1, 10, 60)]
    assert v.preleva_stati() == []  # i primi 60 secondi erano con il microfono acceso
    v.cambia_stato(GID, 1, T0 + timedelta(seconds=160), muto=True, sordo=True)
    assert v.preleva_stati() == [(GID, 1, 100, True, False, False)]
    v.esce(GID, 1, T0 + timedelta(seconds=200))
    assert v.preleva_stati() == [(GID, 1, 40, True, True, False)]


# STA-006
def test_sta_006_stesso_stato_non_fa_nulla_e_utente_assente_neppure():
    v = VoiceTracker()
    assert v.cambia_stato(GID, 1, T0, True, False) == []
    v.entra(GID, 10, 1, T0)
    assert v.cambia_stato(GID, 1, T0 + timedelta(seconds=30), False, False) == []


# STA-006
def test_sta_006_afk_non_conta_come_vocale_ma_si_segue():
    v = VoiceTracker()
    v.entra(GID, 90, 1, T0, afk=True)
    assert v.esce(GID, 1, T0 + timedelta(seconds=120)) == []
    assert v.preleva_stati() == [(GID, 1, 120, False, False, True)]


# STA-006
def test_sta_006_buffer_somma_e_rimette_in_coda():
    b = ActivityBuffer()
    b.add_voice_state(GID, 1, 30, T0, True, False, False)
    b.add_voice_state(GID, 1, 30, T0, True, True, False)
    b.add_voice_state(GID, 1, 10, T0, False, False, True)
    b.add_voice_state(GID, 1, 99, T0, False, False, False)  # nessuno stato: niente
    stati = b.drain_stati()
    assert stati[(GID, T0.date(), 1)] == [60, 30, 10]
    assert b.drain_stati() == {}
    b.restore_stati(stati)
    assert b.drain_stati() == stati


# STA-006
async def test_sta_006_repo_e_cog_scrivono_i_minuti_per_stato(cog):
    g = fake_guild(GID)
    canale = MagicMock(); canale.id = 91
    m = fake_member(6); m.guild = g; m.roles = []
    entra = MagicMock(channel=canale, self_mute=False, self_deaf=False, mute=False, deaf=False)
    await cog.on_voice_state_update(m, MagicMock(channel=None), entra)
    cog._voce._sessioni[(GID, 6)][1] = datetime.now(timezone.utc) - timedelta(minutes=10)
    muto = MagicMock(channel=canale, self_mute=True, self_deaf=False, mute=False, deaf=False)
    await cog.on_voice_state_update(m, entra, muto)  # stesso canale: cambia solo il microfono
    cog._voce._sessioni[(GID, 6)][1] = datetime.now(timezone.utc) - timedelta(minutes=5)
    await cog.on_voice_state_update(m, muto, MagicMock(channel=None))
    await cog.scrivi_lotto()
    stati = await cog._repo.voice_states(GID, date(2020, 1, 1), 6)
    assert stati["muto"] == 5 and stati["sordo"] == 0 and stati["afk"] == 0
    assert await cog._repo.member_total(GID, 6, date(2020, 1, 1), "voice_minutes") == 15


# --- STA-025, 026, 027: filtri ------------------------------------------------

# STA-025
def test_sta_025_canale_e_categoria_esclusi():
    imp = ActivitySettings(ignored_channels=[500])
    canale = fake_text_channel(40); canale.category_id = 500
    assert not conta_secondo_i_filtri(imp, 1, [], canali_del_messaggio(canale))  # la categoria vale per i suoi canali
    altro = fake_text_channel(41); altro.category_id = 501
    assert conta_secondo_i_filtri(imp, 1, [], canali_del_messaggio(altro))


# STA-025
def test_sta_025_modo_solo_conta_soltanto_l_elenco_e_l_elenco_vuoto_non_limita():
    imp = ActivitySettings(ignored_channels=[40], channel_mode="solo")
    assert conta_secondo_i_filtri(imp, 1, [], {40})
    assert not conta_secondo_i_filtri(imp, 1, [], {41})
    assert conta_secondo_i_filtri(ActivitySettings(channel_mode="solo"), 1, [], {41})


# STA-026
def test_sta_026_membri_esclusi():
    imp = ActivitySettings(ignored_members=[7])
    assert not conta_secondo_i_filtri(imp, 7, [], {1})
    assert conta_secondo_i_filtri(imp, 8, [], {1})


# STA-027
def test_sta_027_ruoli_inclusi_o_esclusi():
    assert not conta_secondo_i_filtri(ActivitySettings(ignored_roles=[9]), 1, [9, 3], {1})
    solo = ActivitySettings(ignored_roles=[9], role_mode="solo")
    assert conta_secondo_i_filtri(solo, 1, [9], {1})
    assert not conta_secondo_i_filtri(solo, 1, [3], {1})


# STA-025, STA-026, STA-027
async def test_sta_025_026_027_filtri_dal_comando_e_dal_conteggio(cog):
    g = fake_guild(GID)
    canale = fake_text_channel(40)
    it = fake_interaction(guild=g)
    membro = fake_member(5)
    await cog.impostazioni.callback(cog, it, None, None, membro, None, None, None, None)
    assert "escluso" in it.response.send_message.await_args.args[0]
    await cog.on_message(_msg(membro, canale, g))
    await cog.on_message(_msg(fake_member(6), canale, g))
    await cog.scrivi_lotto()
    assert await cog._repo.member_total(GID, 5, date(2020, 1, 1), "messages") == 0
    assert await cog._repo.member_total(GID, 6, date(2020, 1, 1), "messages") == 1
    # di nuovo: lo stesso comando rimette il membro
    await cog.impostazioni.callback(cog, fake_interaction(guild=g), None, None, membro, None, None, None, None)
    assert (await cog._repo.get_settings(GID)).ignored_members == []


# STA-025
async def test_sta_025_modo_dal_comando(cog):
    g = fake_guild(GID)
    it = fake_interaction(guild=g)
    await cog.impostazioni.callback(cog, it, fake_text_channel(40), None, None, _Ch("solo"), _Ch("solo"), None, None)
    imp = await cog._repo.get_settings(GID)
    assert imp.channel_mode == "solo" and imp.role_mode == "solo" and imp.ignored_channels == [40]
    assert "solo" in it.response.send_message.await_args.args[0]


# --- STA-013: chi può guardare le statistiche ----------------------------------

# STA-013
async def test_sta_013_ruoli_che_vedono_le_statistiche(cog):
    g = fake_guild(GID)
    ruolo = fake_role(300)
    await cog.impostazioni.callback(cog, fake_interaction(guild=g), None, None, None, None, None, ruolo, None)
    assert (await cog._repo.get_settings(GID)).view_roles == [300]
    await cog.impostazioni.callback(cog, fake_interaction(guild=g), None, None, None, None, None, ruolo, None)
    assert (await cog._repo.get_settings(GID)).view_roles == []


# STA-013
async def test_sta_013_everyone_non_si_accetta(cog):
    g = fake_guild(GID)
    everyone = fake_role(GID)
    everyone.is_default = MagicMock(return_value=True)
    it = fake_interaction(guild=g)
    await cog.impostazioni.callback(cog, it, None, None, None, None, None, everyone, None)
    assert (await cog._repo.get_settings(GID)).view_roles == []
    assert it.response.send_message.await_args.kwargs["ephemeral"] is True


# --- STA-028: anonimato ------------------------------------------------------------

# STA-028
async def test_sta_028_anonimo_si_accende_e_si_spegne(cog):
    it = fake_interaction(guild=fake_guild(GID))
    it.user = fake_member(55)
    await cog.privacy_statistiche.callback(cog, it, True)
    assert await cog._repo.is_anonymous(55)
    assert await cog._repo.anonymous_among([55, 56]) == {55}
    await cog.privacy_statistiche.callback(cog, it, False)
    assert not await cog._repo.is_anonymous(55)
    assert await cog._repo.anonymous_among([]) == set()


# --- STA-032: due condizioni -------------------------------------------------------

# STA-032
def test_sta_032_unione_delle_condizioni():
    assert regola_con_due_condizioni({1, 2}, {2, 3}, "e") == {2}
    assert regola_con_due_condizioni({1, 2}, {2, 3}, "o") == {1, 2, 3}
    assert regola_con_due_condizioni({1, 2}, None, "e") == {1, 2}


# STA-032
async def test_sta_032_regola_con_messaggi_e_vocale(cog):
    it = fake_interaction(guild=fake_guild(GID))
    it.guild.me.top_role = fake_role(9, position=10)
    await cog.ruolo_aggiungi.callback(cog, it, fake_role(300, position=2), _Ch("messages"), 50, 7, True, _Ch("voice_minutes"), 60, _Ch("e"))
    assert "50 messaggi e 60 minuti in vocale" in it.response.send_message.await_args.args[0]
    regola = (await cog._repo.list_rules(GID))[0]
    assert (regola.metric2, regola.threshold2, regola.combine) == ("voice_minutes", 60, "e")
    # una sola metà della seconda condizione si rifiuta
    it = fake_interaction(guild=fake_guild(GID))
    it.guild.me.top_role = fake_role(9, position=10)
    await cog.ruolo_aggiungi.callback(cog, it, fake_role(301, position=2), _Ch("messages"), 5, 7, True, _Ch("voice_minutes"), None, None)
    assert len(await cog._repo.list_rules(GID)) == 1


# STA-032
async def test_sta_032_il_ruolo_va_solo_a_chi_passa_tutte_e_due(cog, monkeypatch):
    me = fake_member(999, roles=[fake_role(9, position=10)], guild_permissions=discord.Permissions(manage_roles=True), bot=True)
    g = fake_guild(GID, me=me)
    ruolo = fake_role(300, position=2); ruolo.members = []
    entrambi, solo_msg = fake_member(5), fake_member(6)
    for m in (entrambi, solo_msg):
        m.add_roles = AsyncMock(); m.remove_roles = AsyncMock()
    g.get_role = MagicMock(return_value=ruolo)
    g.get_member = MagicMock(side_effect=lambda u: {5: entrambi, 6: solo_msg}.get(u))
    cog.bot.get_guild = MagicMock(return_value=g)
    oggi = datetime.now(timezone.utc).date()
    await cog._repo.flush({}, {(GID, oggi, 5): [10, 3600], (GID, oggi, 6): [10, 0]}, {})
    await cog._repo.add_rule(GID, 300, "messages", 5, 7, True, "voice_minutes", 30, "e")
    import cogs.utility.activity_stats as m
    monkeypatch.setattr(m.asyncio, "sleep", AsyncMock())
    await cog.aggiorna_ruoli()
    entrambi.add_roles.assert_awaited_once()
    solo_msg.add_roles.assert_not_awaited()


# --- STA-029: diagnosi ------------------------------------------------------------

# STA-029
async def test_sta_029_diagnosi_dice_quali_canali_non_si_leggono(cog):
    g = fake_guild(GID)
    cieco = fake_text_channel(41, "segreto")
    cieco.permissions_for = MagicMock(return_value=discord.Permissions(view_channel=False))
    g.text_channels = [cieco]
    it = fake_interaction(guild=g)
    await cog.diagnosi.callback(cog, it)
    testo = it.response.send_message.await_args.args[0]
    assert "non posso leggere: 1" in testo and "Filtro dei canali" in testo


# --- STA-008: campioni dei membri online -------------------------------------------

# STA-008
async def test_sta_008_interruttore_e_campioni(cog, repo):
    await cog.impostazioni.callback(cog, fake_interaction(guild=fake_guild(GID)), None, None, None, None, None, None, True)
    assert (await repo.get_settings(GID)).track_online
    assert await repo.guilds_tracking_online() == [GID]
    ora = datetime(2026, 5, 4, 15, tzinfo=timezone.utc)
    await repo.add_online_sample(GID, ora, 40)
    await repo.add_online_sample(GID, ora, 42)  # lo stesso orario si aggiorna
    assert await repo.online_samples(GID, ora - timedelta(hours=1)) == [(ora, 42)]
    assert await repo.online_samples(GID + 1, ora - timedelta(hours=1)) == []  # mai i dati di un altro server


# STA-008
async def test_sta_008_il_giro_orario_salva_solo_i_server_che_lo_vogliono(cog, repo, monkeypatch):
    import cogs.utility.activity_stats as m

    monkeypatch.setattr(m.asyncio, "sleep", AsyncMock())
    await repo.set_track_online(GID, True)
    await repo.set_track_online(GID + 1, True)
    cog.bot.get_guild = MagicMock(side_effect=lambda gid: MagicMock() if gid == GID else None)
    cog.bot.fetch_guild = AsyncMock(return_value=MagicMock(approximate_presence_count=17))
    await cog.campiona_online()
    cog.bot.fetch_guild.assert_awaited_once_with(GID, with_counts=True)
    campioni = await repo.online_samples(GID, datetime(2020, 1, 1, tzinfo=timezone.utc))
    assert [n for _, n in campioni] == [17]
    cog.bot.fetch_guild = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=500), "x"))
    await cog.campiona_online()  # un errore di Discord non ferma il giro


# STA-057
async def test_sta_057_esporta_zip_solo_del_proprio_server(cog, repo):
    import io, zipfile
    oggi = datetime.now(timezone.utc).date()
    await repo.flush({(GID, oggi, 40): [3, 0], (GID + 1, oggi, 99): [7, 0]}, {(GID, oggi, 5): [3, 0]}, {})
    await repo.add_rule(GID, 300, "messages", 5, 7, True)
    it = fake_interaction(guild=fake_guild(GID))
    await cog.esporta.callback(cog, it)
    f = it.followup.send.await_args.kwargs["file"]
    z = zipfile.ZipFile(io.BytesIO(f.fp.read()))
    assert {"activity_channel_daily.csv", "regole.csv", "contatori.csv", "impostazioni.csv"} <= set(z.namelist())
    canali = z.read("activity_channel_daily.csv").decode("utf-8-sig")
    assert ";40;" in canali and ";99;" not in canali  # mai dati di un altro server
    assert "messages" in z.read("regole.csv").decode("utf-8-sig")
