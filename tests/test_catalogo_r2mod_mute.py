"""
tests/test_catalogo_r2mod_mute.py
=================================
Controllo delle aree chiuse (#115, giro r2mod): ruolo del mute scelto o creato (MOD-018),
blocco rimesso su tutti i canali (MOD-019), reazioni negate al mute (MOD-020). Database vero.
"""

import discord
import pytest

from cogs.moderation import softban_mute
from cogs.moderation.opzioni import OpzioniModerazioneCog
from core.database import db
from tests.support.discord_fakes import fake_role, fake_text_channel
from tests.test_moderation_ordine_azione import ID_SERVER, Scena

from cogs.moderation._shared import MODULE_ACTIONS


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID_SERVER, MODULE_ACTIONS, True)
    monkeypatch.setattr(softban_mute, "PAUSA_AGGIORNA", 0)
    yield
    database_module.db._modules_cache.clear()


def _scena() -> Scena:
    s = Scena()
    s.moderatore.guild_permissions = discord.Permissions(manage_guild=True)
    s.server.me.guild_permissions = discord.Permissions(manage_roles=True, manage_channels=True)
    s.server.channels = []
    return s


def _canale(numero: int, *, coperto: bool):
    canale = fake_text_channel(numero, f"c{numero}")
    sovrascrizione = discord.PermissionOverwrite()
    if coperto:
        sovrascrizione.update(**{nome: False for nome in softban_mute.MUTE_OVERWRITE})
    canale.overwrites_for.return_value = sovrascrizione
    return canale


# MOD-020
def test_il_mute_nega_anche_le_reazioni():
    assert softban_mute.MUTE_OVERWRITE["add_reactions"] is False


# MOD-020
async def test_il_blocco_sul_canale_toglie_le_reazioni():
    canale = _canale(1, coperto=False)
    ruolo = fake_role(300, "Muto", position=10)
    assert await softban_mute._apply_mute_overwrite(canale, ruolo) is True
    messo = canale.set_permissions.call_args.kwargs["overwrite"]
    assert messo.add_reactions is False and messo.send_messages is False


# MOD-018
async def test_il_ruolo_scelto_si_salva_se_sta_sotto_il_bot_e_sotto_il_moderatore():
    s = _scena()
    ruolo = fake_role(300, "Silenziati", position=10)
    s.server.me.top_role = fake_role(3, position=50)
    s.moderatore.top_role = fake_role(1, position=40)
    cog = OpzioniModerazioneCog(bot=None)
    await cog.muto.callback(cog, s.interazione, ruolo, None, False)
    assert await db.get_guild_setting(ID_SERVER, softban_mute.SETTING_MUTE_ROLE_ID) == 300


# MOD-018
@pytest.mark.parametrize("posizione,gestito", [(60, False), (45, False), (10, True)])
async def test_un_ruolo_sopra_il_bot_o_sopra_chi_comanda_o_di_integrazione_si_rifiuta(posizione, gestito):
    s = _scena()
    ruolo = fake_role(300, "Alto", position=posizione, managed=gestito)
    s.server.me.top_role = fake_role(3, position=50)
    s.moderatore.top_role = fake_role(1, position=40)
    cog = OpzioniModerazioneCog(bot=None)
    await cog.muto.callback(cog, s.interazione, ruolo, None, False)
    assert await db.get_guild_setting(ID_SERVER, softban_mute.SETTING_MUTE_ROLE_ID) is None
    s.interazione.followup.send.assert_awaited_once()


# MOD-018
async def test_un_ruolo_con_permessi_pericolosi_non_diventa_il_ruolo_del_mute():
    s = _scena()
    ruolo = fake_role(300, "Admin", position=10, permissions=discord.Permissions(administrator=True))
    s.server.me.top_role = fake_role(3, position=50)
    s.moderatore.top_role = fake_role(1, position=40)
    cog = OpzioniModerazioneCog(bot=None)
    await cog.muto.callback(cog, s.interazione, ruolo, None, False)
    assert await db.get_guild_setting(ID_SERVER, softban_mute.SETTING_MUTE_ROLE_ID) is None


# MOD-018
async def test_il_ruolo_si_puo_creare_con_un_nome_e_il_motivo_sta_nei_limiti():
    s = _scena()
    nuovo = fake_role(301, "Silenzio", position=2)
    s.server.create_role.return_value = nuovo
    cog = OpzioniModerazioneCog(bot=None)
    await cog.muto.callback(cog, s.interazione, None, "Silenzio", False)
    assert await db.get_guild_setting(ID_SERVER, softban_mute.SETTING_MUTE_ROLE_ID) == 301
    assert len(s.server.create_role.call_args.kwargs["reason"]) <= 512


# MOD-018
async def test_senza_il_permesso_di_gestire_il_server_non_cambia_niente():
    s = _scena()
    s.moderatore.guild_permissions = discord.Permissions.none()
    cog = OpzioniModerazioneCog(bot=None)
    await cog.muto.callback(cog, s.interazione, fake_role(300, position=10), None, False)
    assert await db.get_guild_setting(ID_SERVER, softban_mute.SETTING_MUTE_ROLE_ID) is None


# MOD-019
async def test_aggiorna_sistema_solo_i_canali_scoperti_e_uno_che_rifiuta_non_ferma_gli_altri():
    s = _scena()
    ruolo = fake_role(300, "Muto", position=10)
    s.server.me.top_role = fake_role(3, position=50)
    s.moderatore.top_role = fake_role(1, position=40)
    coperto, scoperto_a, scoperto_b = _canale(1, coperto=True), _canale(2, coperto=False), _canale(3, coperto=False)
    scoperto_a.set_permissions.side_effect = discord.HTTPException(
        __import__("unittest.mock").mock.MagicMock(status=403, reason="x"), "no"
    )
    s.server.channels = [coperto, scoperto_a, scoperto_b]
    fatti, falliti = await softban_mute.aggiorna_ruolo_muto(s.server, ruolo)
    assert (fatti, falliti) == (1, 1)
    coperto.set_permissions.assert_not_called()
    scoperto_b.set_permissions.assert_awaited_once()


# MOD-019
async def test_aggiorna_si_ferma_a_cinquecento_canali():
    s = _scena()
    ruolo = fake_role(300, "Muto", position=10)
    s.server.channels = [_canale(i, coperto=False) for i in range(1, 521)]
    fatti, falliti = await softban_mute.aggiorna_ruolo_muto(s.server, ruolo)
    assert fatti + falliti == softban_mute.MAX_CANALI_AGGIORNA


# MOD-019
async def test_il_comando_aggiorna_chiede_il_permesso_sui_canali_al_bot():
    s = _scena()
    s.server.me.guild_permissions = discord.Permissions(manage_roles=True)
    cog = OpzioniModerazioneCog(bot=None)
    await cog.muto.callback(cog, s.interazione, None, None, True)
    s.interazione.response.send_message.assert_awaited_once()
    assert await db.get_guild_setting(ID_SERVER, softban_mute.SETTING_MUTE_ROLE_ID) is None


# MOD-111
async def test_i_permessi_di_un_membro_in_un_canale_si_vedono_con_utility_permessi():
    from unittest.mock import MagicMock

    from cogs.utility.schede import SchedeCog
    from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

    cog = SchedeCog(MagicMock())
    membro = fake_member(77)
    canale = fake_text_channel(5, "staff")
    canale.permissions_for = MagicMock(return_value=discord.Permissions(send_messages=True, ban_members=False))
    it = fake_interaction(guild=fake_guild(), channel=canale)
    await cog.permessi.callback(cog, it, membro, canale)
    canale.permissions_for.assert_called_once_with(membro)
    campi = {c.name: c.value for c in it.response.send_message.call_args.kwargs["embed"].fields}
    assert "Concessi" in campi and "Mancanti" in campi
