"""
tests/test_moderation_vocale_m4.py
==================================
Moderazione della voce, blocco M4 (#115): muta e sordina (MOD-022), scollega (MOD-023), sposta (MOD-024),
sposta tutti (MOD-025), mute con scollega o sposta (MOD-026), dove sta un utente e sorveglianza (MOD-112).
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.moderation._shared import MODULE_ACTIONS, SETTING_MOD_LOG_CHANNEL
from cogs.moderation.voce import ModerationVoceCog
from core import moderazione_vocale_logic as logica
from core.database import db
from core.repositories.moderation_repo import moderation_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel, fake_voice_channel

G = 100


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(G, MODULE_ACTIONS, True)
    await db.set_guild_setting(G, SETTING_MOD_LOG_CHANNEL, 7001)
    monkeypatch.setattr("cogs.moderation.voce.PAUSA_SPOSTA", 0)
    yield
    database_module.db._modules_cache.clear()


def _permessi_bot(**kw):
    return discord.Permissions(**kw)


def _canale(cid, **perm_bot):
    c = fake_voice_channel(cid, f"voce{cid}")
    c.mention = f"<#{cid}>"
    c.members = []
    c.permissions_for = MagicMock(return_value=_permessi_bot(connect=True, view_channel=True, **perm_bot))
    return c


def _amb_cmd(perm_staff, *, bot_move=True, bot_mute=True):
    server = fake_guild(G)
    server.me.top_role = SimpleNamespace(position=50)
    server.me.guild_permissions = discord.Permissions(move_members=bot_move, mute_members=bot_mute, deafen_members=bot_mute)
    log = fake_text_channel(7001)
    log.send = AsyncMock()
    server.get_channel.return_value = log
    mod = fake_member(10, guild_permissions=discord.Permissions(**perm_staff))
    mod.top_role = SimpleNamespace(position=40)
    server.get_member = MagicMock(return_value=mod)
    return fake_interaction(guild=server, user=mod), server


def _bersaglio(uid=20, canale=None):
    m = fake_member(uid)
    m.top_role = SimpleNamespace(position=10)
    m.voice = SimpleNamespace(channel=canale, mute=False, deaf=False) if canale else None
    m.edit = AsyncMock()
    m.move_to = AsyncMock()
    m.roles = []
    return m


def _cog():
    return ModerationVoceCog(MagicMock())


def _testo(inter):
    c = inter.response.send_message.call_args
    return c.args[0] if c.args else c.kwargs.get("content", "")


def _cb(cmd):
    return getattr(cmd, "callback", cmd)


# --- logica ---

def test_permesso_mancante_per_azione():
    assert logica.permesso_per("muta") == "mute_members"
    assert logica.permesso_per("sordina") == "deafen_members"
    assert logica.permesso_per("scollega") == "move_members"
    assert logica.permesso_per("sposta") == "move_members"
    with pytest.raises(ValueError):
        logica.permesso_per("altro")


def test_da_spostare_ha_un_tetto_e_dice_quanti_restano():
    membri = list(range(250))
    scelti, restano = logica.da_spostare(membri)
    assert len(scelti) == logica.MAX_SPOSTA_TUTTI == 200
    assert restano == 50
    assert logica.da_spostare([1, 2]) == ([1, 2], 0)


def test_sposta_nello_stesso_canale_e_un_errore():
    assert logica.stesso_canale(5, 5) is True
    assert logica.stesso_canale(5, 6) is False


@pytest.mark.parametrize("scelta,canale,ok", [
    ("niente", None, True), ("scollega", None, True), ("sposta", 5, True), ("sposta", None, False), ("altro", None, False),
])
def test_scelta_vocale_del_mute(scelta, canale, ok):
    assert logica.scelta_mute_valida(scelta, canale) is ok


def test_sorveglianza_dura_24_ore():
    ora = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
    assert logica.scadenza_sorveglianza(ora) == ora + timedelta(hours=24)


# --- repo ---

async def test_sorveglianza_nel_db_si_aggiunge_si_legge_e_scade():
    ora = datetime.now(timezone.utc)
    await moderation_repo.add_vocale_sorveglia(G, 20, 10, ora + timedelta(hours=1))
    await moderation_repo.add_vocale_sorveglia(G, 20, 11, ora - timedelta(hours=1))  # scaduta
    attive = await moderation_repo.vocale_sorveglianti(G, 20)
    assert attive == [10]
    await moderation_repo.delete_vocale_sorveglia(G, 20)
    assert await moderation_repo.vocale_sorveglianti(G, 20) == []


async def test_sorveglianza_un_solo_record_per_staff_e_tetto_per_server():
    ora = datetime.now(timezone.utc) + timedelta(hours=1)
    await moderation_repo.add_vocale_sorveglia(G, 20, 10, ora)
    await moderation_repo.add_vocale_sorveglia(G, 20, 10, ora + timedelta(hours=1))
    assert await moderation_repo.count_vocale_sorveglia(G) == 1
    assert await moderation_repo.count_vocale_sorveglia(G) == 1


# --- comandi ---

async def test_muta_senza_permesso_dello_staff_e_rifiutato():
    inter, _ = _amb_cmd({})
    bers = _bersaglio(canale=_canale(1))
    await _cb(_cog().vocale_muta)(_cog(), inter, bers, True)
    bers.edit.assert_not_called()
    assert "mute_members" in _testo(inter)


async def test_muta_mette_il_mute_del_server_e_scrive_il_log():
    inter, server = _amb_cmd({"mute_members": True})
    bers = _bersaglio(canale=_canale(1, mute_members=True))
    await _cb(_cog().vocale_muta)(_cog(), inter, bers, True)
    assert bers.edit.await_args.kwargs["mute"] is True
    server.get_channel.return_value.send.assert_awaited()


async def test_sordina_toglie_la_sordina():
    inter, _ = _amb_cmd({"deafen_members": True})
    bers = _bersaglio(canale=_canale(1, deafen_members=True))
    await _cb(_cog().vocale_sordina)(_cog(), inter, bers, False)
    assert bers.edit.await_args.kwargs["deafen"] is False


async def test_membro_non_in_vocale_riceve_un_messaggio_e_nessuna_azione():
    inter, _ = _amb_cmd({"move_members": True})
    bers = _bersaglio(canale=None)
    await _cb(_cog().vocale_scollega)(_cog(), inter, bers)
    bers.move_to.assert_not_called()
    assert _testo(inter)


async def test_scollega_chiama_move_to_none():
    inter, _ = _amb_cmd({"move_members": True})
    bers = _bersaglio(canale=_canale(1, move_members=True))
    await _cb(_cog().vocale_scollega)(_cog(), inter, bers)
    assert bers.move_to.await_args.args[0] is None


async def test_scollega_senza_permesso_del_bot_non_agisce():
    inter, _ = _amb_cmd({"move_members": True})
    bers = _bersaglio(canale=_canale(1))  # il bot non ha move_members nel canale
    await _cb(_cog().vocale_scollega)(_cog(), inter, bers)
    bers.move_to.assert_not_called()


async def test_sposta_porta_il_membro_nel_canale_scelto():
    inter, _ = _amb_cmd({"move_members": True})
    dest = _canale(2)
    bers = _bersaglio(canale=_canale(1, move_members=True))
    await _cb(_cog().vocale_sposta)(_cog(), inter, bers, dest)
    assert bers.move_to.await_args.args[0] is dest


async def test_sposta_nello_stesso_canale_non_fa_nulla():
    inter, _ = _amb_cmd({"move_members": True})
    c = _canale(1, move_members=True)
    bers = _bersaglio(canale=c)
    await _cb(_cog().vocale_sposta)(_cog(), inter, bers, c)
    bers.move_to.assert_not_called()


async def test_sposta_tutti_rispetta_il_tetto_e_dice_quanti_restano():
    inter, _ = _amb_cmd({"move_members": True})
    da, a = _canale(1, move_members=True), _canale(2)
    da.members = [_bersaglio(1000 + i, da) for i in range(230)]
    await _cb(_cog().vocale_sposta_tutti)(_cog(), inter, da, a)
    mossi = sum(m.move_to.await_count for m in da.members)
    assert mossi == 200
    testo = inter.followup.send.call_args.args[0]
    assert "30" in testo


async def test_sposta_tutti_si_ferma_dopo_tre_403_di_fila():
    inter, _ = _amb_cmd({"move_members": True})
    da, a = _canale(1, move_members=True), _canale(2)
    da.members = [_bersaglio(1000 + i, da) for i in range(10)]
    risposta = MagicMock(status=403, reason="x")
    for m in da.members:
        m.move_to = AsyncMock(side_effect=discord.Forbidden(risposta, "no"))
    await _cb(_cog().vocale_sposta_tutti)(_cog(), inter, da, a)
    assert sum(m.move_to.await_count for m in da.members) == 3


async def test_dove_mostra_il_canale_e_non_crea_sorveglianza_se_e_in_vocale():
    inter, _ = _amb_cmd({"move_members": True})
    bers = _bersaglio(canale=_canale(1))
    await _cb(_cog().vocale_dove)(_cog(), inter, bers, True)
    assert "<#1>" in _testo(inter)
    assert await moderation_repo.count_vocale_sorveglia(G) == 0


async def test_dove_avvisa_crea_la_sorveglianza_se_non_e_in_vocale():
    inter, _ = _amb_cmd({"move_members": True})
    bers = _bersaglio(canale=None)
    await _cb(_cog().vocale_dove)(_cog(), inter, bers, True)
    assert await moderation_repo.vocale_sorveglianti(G, 20) == [10]


async def test_ingresso_in_vocale_avvisa_lo_staff_una_volta():
    cog = _cog()
    server = fake_guild(G)
    staff = fake_member(10)
    staff.send = AsyncMock()
    server.get_member = MagicMock(return_value=staff)
    await moderation_repo.add_vocale_sorveglia(G, 20, 10, datetime.now(timezone.utc) + timedelta(hours=1))
    bers = fake_member(20)
    bers.guild = server
    prima = SimpleNamespace(channel=None)
    dopo = SimpleNamespace(channel=_canale(3))
    await cog.on_voice_state_update(bers, prima, dopo)
    staff.send.assert_awaited_once()
    await cog.on_voice_state_update(bers, prima, dopo)
    staff.send.assert_awaited_once()


async def test_le_sorveglianze_scadute_escono_dalla_memoria(monkeypatch):
    """Chi non entra mai in vocale non deve restare per sempre nella memoria del cog."""
    cog = _cog()
    inter, _ = _amb_cmd({"move_members": True})
    vera = logica.scadenza_sorveglianza
    monkeypatch.setattr(logica, "scadenza_sorveglianza", lambda adesso: adesso - timedelta(hours=1))
    await _cb(cog.vocale_dove)(cog, inter, _bersaglio(uid=21, canale=None), True)
    monkeypatch.setattr(logica, "scadenza_sorveglianza", vera)
    inter2, _ = _amb_cmd({"move_members": True})
    await _cb(cog.vocale_dove)(cog, inter2, _bersaglio(uid=22, canale=None), True)
    assert (G, 21) not in cog._sorvegliati
    assert (G, 22) in cog._sorvegliati


# --- mute con ruolo + voce (MOD-026) ---

def _mute_env(monkeypatch, perm_staff):
    from cogs.moderation import softban_mute as sm

    inter, server = _amb_cmd(perm_staff)
    ruolo = SimpleNamespace(id=900, position=1)
    monkeypatch.setattr(sm, "_get_or_create_mute_role", AsyncMock(return_value=ruolo))
    monkeypatch.setattr(sm, "try_dm", AsyncMock())
    bers = _bersaglio(canale=_canale(1, move_members=True))
    bers.add_roles = AsyncMock()
    return sm, inter, bers


async def test_mute_con_scollega_toglie_il_membro_dal_vocale(monkeypatch):
    sm, inter, bers = _mute_env(monkeypatch, {"move_members": True})
    cog = sm.ModerationSoftbanMuteCog(MagicMock())
    await _cb(cog.mute_role)(cog, inter, bers, "motivo lungo", None, False, "scollega", None)
    assert bers.move_to.await_args.args[0] is None


async def test_mute_con_sposta_senza_canale_e_rifiutato(monkeypatch):
    sm, inter, bers = _mute_env(monkeypatch, {"move_members": True})
    cog = sm.ModerationSoftbanMuteCog(MagicMock())
    await _cb(cog.mute_role)(cog, inter, bers, "motivo lungo", None, False, "sposta", None)
    bers.add_roles.assert_not_called()


async def test_mute_con_scollega_senza_permesso_dello_staff_non_muta(monkeypatch):
    sm, inter, bers = _mute_env(monkeypatch, {})
    cog = sm.ModerationSoftbanMuteCog(MagicMock())
    await _cb(cog.mute_role)(cog, inter, bers, "motivo lungo", None, False, "scollega", None)
    bers.add_roles.assert_not_called()
