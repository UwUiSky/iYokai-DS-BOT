"""
tests/test_moderation_opzioni.py
================================
Opzioni di moderazione del server (`/mod opzioni`): giorni di messaggi al
ban (MOD-010), durata predefinita del timeout (MOD-017), DM per tipo di
azione (MOD-057), ruoli immuni (MOD-068, solo il proprietario).
"""

from unittest.mock import MagicMock

import discord
import pytest

from cogs.moderation._shared import MODULE_ACTIONS
from cogs.moderation.actions import ModerationActionsCog
from cogs.moderation.opzioni import OpzioniModerazioneCog
from cogs.utility.config_history import errore_chiavi_solo_proprietario
from core import moderation_opzioni as opzioni
from core.database import db
from core.moderation_bulk_logic import azzera_usi
from core.repositories.moderation_repo import moderation_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role

SERVER = 100
PROPRIETARIO = 1
MOD = 444444444444444444
A = 111111111111111111
IMMUNE = 77


@pytest.fixture(autouse=True)
async def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    database_module.db._settings_cache.clear()
    azzera_usi()
    await db.set_module_active_for_guild(SERVER, MODULE_ACTIONS, True)
    yield
    database_module.db._modules_cache.clear()
    database_module.db._settings_cache.clear()


def _scena(ruoli_bersaglio=(), chi=MOD, admin=True):
    server = fake_guild(SERVER, owner_id=PROPRIETARIO)
    server.me.top_role = fake_role(role_id=3, position=50)
    server.me.id = 999
    server.get_channel.return_value = None
    permessi = discord.Permissions(administrator=admin)
    moderatore = fake_member(chi, roles=[fake_role(role_id=1, position=40)], guild_permissions=permessi)
    moderatore.guild = server
    ruoli = [fake_role(role_id=2, position=5)] + [fake_role(role_id=r, position=6) for r in ruoli_bersaglio]
    membro = fake_member(A, roles=ruoli)
    membro.guild = server
    server.get_member.side_effect = {chi: moderatore, A: membro}.get
    return membro, fake_interaction(guild=server, user=moderatore)


def _cog():
    bot = MagicMock()
    bot.user = fake_member(999, bot=True)
    return ModerationActionsCog(bot=bot)


async def _tipi(uid=A):
    return [c.action_type for c in await moderation_repo.list_cases_for_user(SERVER, uid)]


async def test_ban_senza_giorni_usa_il_valore_del_server():
    await opzioni.imposta_giorni_ban(SERVER, 3, MOD)
    membro, interazione = _scena()
    await _cog().ban.callback(_cog(), interazione, membro, "spam ripetuto")
    assert membro.ban.await_args.kwargs["delete_message_seconds"] == 3 * 86400

    membro, interazione = _scena()
    await _cog().ban.callback(_cog(), interazione, membro, "spam ripetuto", 0)
    assert membro.ban.await_args.kwargs["delete_message_seconds"] == 0


async def test_timeout_senza_durata():
    membro, interazione = _scena()
    await _cog().timeout.callback(_cog(), interazione, membro, "spam ripetuto")
    membro.timeout.assert_not_awaited()
    assert "/mod opzioni" in interazione.response.send_message.call_args.args[0]

    await opzioni.imposta_durata_timeout(SERVER, 900, MOD)
    membro, interazione = _scena()
    await _cog().timeout.callback(_cog(), interazione, membro, "spam ripetuto")
    assert membro.timeout.await_args.args[0].total_seconds() == 900


async def test_dm_spento_per_un_azione():
    await opzioni.imposta_dm(SERVER, "warn", False, MOD)
    membro, interazione = _scena()
    await _cog().warn.callback(_cog(), interazione, membro, "linguaggio")
    membro.send.assert_not_awaited()
    assert await _tipi() == ["warn"]

    await opzioni.imposta_dm(SERVER, "warn", True, MOD)
    membro, interazione = _scena()
    await _cog().warn.callback(_cog(), interazione, membro, "linguaggio")
    membro.send.assert_awaited_once()


async def test_ruolo_immune_ferma_lo_staff_ma_non_il_proprietario():
    await opzioni.cambia_ruolo_immune(SERVER, IMMUNE, True, PROPRIETARIO)
    membro, interazione = _scena(ruoli_bersaglio=(IMMUNE,))
    await _cog().warn.callback(_cog(), interazione, membro, "linguaggio")
    assert "immune" in interazione.response.send_message.call_args.args[0]
    assert await _tipi() == []

    membro, interazione = _scena(ruoli_bersaglio=(IMMUNE,))
    await _cog().warn_massa.callback(_cog(), interazione, str(A), "linguaggio")
    assert await _tipi() == []
    assert "immune" in interazione.followup.send.call_args.kwargs["embed"].description

    membro, interazione = _scena(ruoli_bersaglio=(IMMUNE,), chi=PROPRIETARIO)
    await _cog().warn.callback(_cog(), interazione, membro, "linguaggio")
    assert await _tipi() == ["warn"]


async def test_comandi_delle_opzioni():
    cog = OpzioniModerazioneCog(MagicMock())
    _, interazione = _scena()
    await cog.imposta.callback(cog, interazione, 2, "1h")
    letto = await opzioni.leggi(SERVER)
    assert letto.giorni_ban == 2 and letto.durata_timeout == 3600

    _, interazione = _scena()
    await cog.imposta.callback(cog, interazione, None, "no")
    assert (await opzioni.leggi(SERVER)).durata_timeout is None

    _, interazione = _scena()
    await cog.dm.callback(cog, interazione, discord.app_commands.Choice(name="Ban", value="ban"), False)
    assert (await opzioni.leggi(SERVER)).dm_spenti == {"ban"}

    # Senza «Gestire il server» niente cambia.
    _, interazione = _scena(admin=False)
    await cog.imposta.callback(cog, interazione, 7, None)
    assert (await opzioni.leggi(SERVER)).giorni_ban == 2


async def test_ruoli_immuni_li_sceglie_solo_il_proprietario():
    cog = OpzioniModerazioneCog(MagicMock())
    aggiungi = discord.app_commands.Choice(name="Aggiungi", value="aggiungi")
    ruolo = fake_role(role_id=IMMUNE, position=6)

    _, interazione = _scena()
    await cog.immuni.callback(cog, interazione, aggiungi, ruolo)
    assert (await opzioni.leggi(SERVER)).ruoli_immuni == ()

    _, interazione = _scena(chi=PROPRIETARIO)
    await cog.immuni.callback(cog, interazione, aggiungi, ruolo)
    assert (await opzioni.leggi(SERVER)).ruoli_immuni == (IMMUNE,)

    # Anche l'import della configurazione: un admin non se li cambia.
    server = fake_guild(SERVER, owner_id=PROPRIETARIO)
    admin = fake_member(MOD)
    assert await errore_chiavi_solo_proprietario(server, admin, {"mod_ruoli_immuni": [5]})
    assert await errore_chiavi_solo_proprietario(server, admin, {"mod_ruoli_immuni": [IMMUNE]}) is None


def test_lettura_ignora_valori_sporchi():
    assert opzioni.motivo_immune((5,), [5], attore_proprietario=False)
    assert opzioni.motivo_immune((5,), [5], attore_proprietario=True) is None
    assert opzioni.motivo_immune((), [5], attore_proprietario=False) is None
