"""
tests/test_voice_catalogo_r1.py
===============================
Catalogo «Vocali temporanei» (#127): permetti e vieta a utenti o ruoli (VOC-002, 003), nascondi (VOC-004),
qualità audio (VOC-005), pannello persistente con tutte le azioni (VOC-009), creazione guidata (VOC-019).
VOC-020 (pagina del pannello web) non è in questo giro: sta in `pannello_web`, vedi DECISIONI D91.
"""

from unittest.mock import AsyncMock, MagicMock, create_autospec

import discord
import pytest

import cogs.voice_temp._pannello as pannello
import cogs.voice_temp.voice_temp as modulo
from core.repositories.voice_temp_repo import VoiceTempRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role, fake_voice_channel


@pytest.fixture(autouse=True)
def _senza_azioni_vietate(monkeypatch):
    """VOC-017: il controllo per ruolo legge le impostazioni del server; qui il database non c'è e nessuna azione è vietata."""
    async def _nessuna(guild_id):
        return {}

    monkeypatch.setattr(modulo.azioni_ruoli, "leggi", _nessuna)


PROPRIETARIO = 10


def _in_vocale(membro, canale):
    membro.voice = create_autospec(discord.VoiceState, instance=True)
    membro.voice.channel = canale
    return membro


@pytest.fixture(autouse=True)
def repo_finto(monkeypatch):
    finto = create_autospec(VoiceTempRepository, instance=True)
    finto.get_owner.return_value = PROPRIETARIO
    monkeypatch.setattr(modulo, "voice_temp_repo", finto)
    monkeypatch.setattr(modulo, "_registra", AsyncMock())
    return finto


@pytest.fixture
def canale():
    c = fake_voice_channel(222)
    c.overwrites_for = MagicMock(side_effect=lambda x: discord.PermissionOverwrite())
    c.set_permissions = AsyncMock()
    c.edit = AsyncMock()
    return c


def _interazione(canale, user_id=PROPRIETARIO, top=None):
    utente = _in_vocale(fake_member(user_id=user_id, roles=[top] if top else None), canale)
    i = fake_interaction(user=utente)
    i.guild.owner_id = 999999
    i.guild.default_role = fake_role(0, "@everyone", position=0)
    i.guild.bitrate_limit = 96000
    i.guild.get_member = MagicMock(return_value=None)
    return i


def _testo(i):
    c = i.response.send_message.call_args
    return c.args[0] if c.args else c.kwargs.get("content", "")


async def test_voc002_permit_ammette_un_ruolo_ma_non_everyone(canale):
    """VOC-002: «Connetti» a un ruolo intero; per aprire a tutti c'è /voice unlock."""
    cog = modulo.VoiceTempCog(bot=None)
    ruolo = fake_role(50, "Amici", position=2)
    i = _interazione(canale)
    await cog.permit.callback(cog, i, ruolo)
    canale.set_permissions.assert_awaited_once()
    assert canale.set_permissions.await_args.args[0] is ruolo
    ow = canale.set_permissions.await_args.kwargs["overwrite"]
    assert ow.connect is True and ow.view_channel is True
    canale.set_permissions.reset_mock()
    i = _interazione(canale)
    await cog.permit.callback(cog, i, fake_role(0, "@everyone", position=0))
    canale.set_permissions.assert_not_awaited()
    assert "unlock" in _testo(i)


async def test_voc002_solo_il_proprietario_puo_ammettere(canale):
    cog = modulo.VoiceTempCog(bot=None)
    i = _interazione(canale, user_id=77)
    await cog.permit.callback(cog, i, fake_member(user_id=5))
    canale.set_permissions.assert_not_awaited()
    assert "proprietario" in _testo(i)


async def test_voc003_deny_ruolo_nega_connetti_e_scollega_chi_e_dentro(canale):
    """VOC-003: il ruolo escluso non può rientrare; chi è dentro viene scollegato (il proprietario no)."""
    cog = modulo.VoiceTempCog(bot=None)
    mio = fake_role(60, "Mio", position=5)
    ruolo = fake_role(50, "Ospiti", position=2)
    dentro = _in_vocale(fake_member(user_id=31), canale); dentro.move_to = AsyncMock()
    fuori = fake_member(user_id=32); fuori.voice = None; fuori.move_to = AsyncMock()
    ruolo.members = [dentro, fuori]
    i = _interazione(canale, top=mio)
    await cog.deny.callback(cog, i, ruolo)
    assert canale.set_permissions.await_args.kwargs["overwrite"].connect is False
    dentro.move_to.assert_awaited_once()
    fuori.move_to.assert_not_awaited()


async def test_voc003_ruoli_dello_staff_o_piu_alti_non_si_vietano(canale):
    cog = modulo.VoiceTempCog(bot=None)
    mio = fake_role(60, "Mio", position=5)
    for ruolo in (
        fake_role(50, "Staff", position=2, permissions=discord.Permissions(manage_channels=True)),
        fake_role(51, "Admin", position=2, permissions=discord.Permissions(administrator=True)),
        fake_role(52, "Piu alto", position=9),
        fake_role(0, "@everyone", position=0),
    ):
        i = _interazione(canale, top=mio)
        await cog.deny.callback(cog, i, ruolo)
        assert "non si può escludere" in _testo(i), ruolo.name
    canale.set_permissions.assert_not_awaited()


async def test_voc003_deny_utente_come_prima(canale):
    cog = modulo.VoiceTempCog(bot=None)
    i = _interazione(canale)
    bersaglio = _in_vocale(fake_member(user_id=31), canale); bersaglio.move_to = AsyncMock()
    cog._puo_espellere = MagicMock(return_value=(True, ""))
    await cog.deny.callback(cog, i, bersaglio)
    assert canale.set_permissions.await_args.args[0] is bersaglio and bersaglio.move_to.await_count == 1
    i = _interazione(canale)
    await cog.deny.callback(cog, i, i.user)  # se stessi: no
    assert "non puoi" in _testo(i).lower()


async def test_voc004_nascondi_toglie_la_vista_a_everyone_dopo_aver_protetto_chi_e_dentro(canale):
    cog = modulo.VoiceTempCog(bot=None)
    dentro = fake_member(user_id=31)
    canale.members = [dentro]
    i = _interazione(canale)
    await cog.nascondi.callback(cog, i, True)
    destinatari = [c.args[0] for c in canale.set_permissions.await_args_list]
    assert dentro in destinatari and destinatari[-1] is i.guild.default_role  # @everyone per ultimo
    assert canale.set_permissions.await_args_list[-1].kwargs["overwrite"].view_channel is False


async def test_voc005_qualita_audio_limitata_dal_livello_del_server(canale):
    cog = modulo.VoiceTempCog(bot=None)
    i = _interazione(canale)
    await cog.bitrate.callback(cog, i, 128)
    canale.edit.assert_not_awaited()
    assert "96" in _testo(i)
    i = _interazione(canale)
    await cog.bitrate.callback(cog, i, 64)
    canale.edit.assert_awaited_once_with(bitrate=64000)


# ------------------------------------------------------------------ VOC-009: pannello
def test_voc009_il_pannello_e_persistente_con_otto_azioni():
    v = pannello.PannelloVocaleView()
    assert v.timeout is None
    ids = [b.custom_id for b in v.children]
    assert len(ids) == 8 and len(set(ids)) == 8 and all(i.startswith("iyokai_voice_panel_") for i in ids)
    assert all(len(i) <= 100 for i in ids)
    assert max(b.row for b in v.children) == 1  # al massimo 5 per riga: due righe


async def test_voc009_ogni_clic_passa_dal_controllo_del_proprietario(canale):
    """VOC-009: un clic di chi non è il proprietario arriva ai comandi di /voice, che lo rifiutano."""
    cog = modulo.VoiceTempCog(bot=None)
    i = _interazione(canale, user_id=77)  # non è il proprietario
    i.client = MagicMock(); i.client.get_cog = MagicMock(return_value=cog)
    v = pannello.PannelloVocaleView()
    await v.blocca.callback(i)
    assert "proprietario" in _testo(i)
    canale.set_permissions.assert_not_awaited()


async def test_voc009_nascondi_e_mostra_chiamano_lo_stesso_comando(canale):
    cog = modulo.VoiceTempCog(bot=None)
    cog.nascondi = MagicMock(callback=AsyncMock())
    i = _interazione(canale)
    i.client = MagicMock(); i.client.get_cog = MagicMock(return_value=cog)
    v = pannello.PannelloVocaleView()
    await v.nascondi.callback(i)
    await v.mostra.callback(i)
    assert [c.args[2] for c in cog.nascondi.callback.await_args_list] == [True, False]


async def test_voc009_finestre_di_rinomina_e_limite(canale):
    cog = modulo.VoiceTempCog(bot=None)
    cog.rename = MagicMock(callback=AsyncMock()); cog.limit = MagicMock(callback=AsyncMock())
    i = _interazione(canale)
    i.client = MagicMock(); i.client.get_cog = MagicMock(return_value=cog)
    f = pannello._FinestraNome()
    f.nome._value = "  Stanza di Ale  "
    await f.on_submit(i)
    cog.rename.callback.assert_awaited_once_with(cog, i, "Stanza di Ale")
    f2 = pannello._FinestraLimite()
    f2.limite._value = "abc"
    await f2.on_submit(i)
    cog.limit.callback.assert_not_awaited()
    f2.limite._value = "12"
    await f2.on_submit(i)
    cog.limit.callback.assert_awaited_once_with(cog, i, 12)


async def test_voc009_scelta_dell_utente_solo_di_chi_ha_aperto_il_menu(canale, monkeypatch):
    s = pannello._SceltaMembro(10, "espelli")
    intruso = fake_interaction(user=fake_member(user_id=99))
    assert await s.interaction_check(intruso) is False


async def test_voc009_la_vista_si_registra_all_avvio():
    bot = MagicMock(); bot.add_cog = AsyncMock(); bot.add_view = MagicMock()
    await modulo.setup(bot)
    tipi = [type(c.args[0]).__name__ for c in bot.add_view.call_args_list]
    assert "PannelloVocaleView" in tipi


# ------------------------------------------------------------------ VOC-019
async def test_voc019_crea_categoria_e_generatore_e_configura(repo_finto):
    cog = modulo.VoiceTempCog(bot=None)
    guild = fake_guild(5)
    guild.me.guild_permissions = discord.Permissions(manage_channels=True)
    categoria = MagicMock(); categoria.id = 700; categoria.name = "Vocali"
    generatore = MagicMock(); generatore.id = 701; generatore.mention = "<#701>"
    categoria.create_voice_channel = AsyncMock(return_value=generatore)
    guild.create_category = AsyncMock(return_value=categoria)
    i = fake_interaction(guild=guild, user=fake_member(user_id=1))
    i.response.defer = AsyncMock()
    await cog.voicetemp_crea.callback(cog, i, "Vocali", "➕ Crea")
    repo_finto.set_config.assert_awaited_once_with(5, 701, 700)
    i = fake_interaction(guild=guild, user=fake_member(user_id=1))
    guild.me.guild_permissions = discord.Permissions(manage_channels=False)
    guild.create_category.reset_mock()
    await cog.voicetemp_crea.callback(cog, i, "Vocali", "➕ Crea")
    guild.create_category.assert_not_awaited()
    assert "Gestisci canali" in _testo(i)
