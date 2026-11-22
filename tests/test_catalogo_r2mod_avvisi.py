"""
tests/test_catalogo_r2mod_avvisi.py
===================================
Avviso della sanzione in un canale invece che in DM (MOD-060). Database vero.
"""

from unittest.mock import AsyncMock

import discord
import pytest

from cogs.moderation import _shared
from cogs.moderation.actions import ModerationActionsCog
from cogs.moderation.opzioni import OpzioniModerazioneCog
from core.database import db
from tests.support.discord_fakes import fake_member, fake_text_channel, fake_interaction
from tests.test_moderation_ordine_azione import ID_SERVER, Scena
from cogs.moderation._shared import MODULE_ACTIONS


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID_SERVER, MODULE_ACTIONS, True)
    yield
    database_module.db._modules_cache.clear()


def _scena_con_canale(permessi=None):
    s = Scena()
    canale = fake_text_channel(8001, "avvisi")
    canale.send = AsyncMock(return_value=object())
    canale.permissions_for = lambda who: permessi or discord.Permissions(view_channel=True, send_messages=True, embed_links=True)
    s.server.get_channel.side_effect = lambda cid: canale if cid == 8001 else s.canale_log
    s.bersaglio.guild = s.server
    return s, canale


# MOD-060
async def test_con_il_canale_l_avviso_va_li_con_la_menzione_della_sola_persona_e_non_in_dm():
    await db.set_guild_setting(ID_SERVER, _shared.SETTING_AVVISO_CANALE, 8001)
    s, canale = _scena_con_canale()
    cog = ModerationActionsCog(bot=None)
    await cog.kick.callback(cog, s.interazione, s.bersaglio, "Spam ripetuto")
    s.bersaglio.send.assert_not_awaited()
    kw = canale.send.await_args.kwargs
    assert kw["content"] == s.bersaglio.mention and kw["embed"] is not None
    assert kw["allowed_mentions"].everyone is False and kw["allowed_mentions"].roles is False
    assert kw["allowed_mentions"].users == [s.bersaglio]


# MOD-060
@pytest.mark.parametrize("caso", ["senza_canale", "senza_permesso", "scrittura_rifiutata"])
async def test_senza_canale_o_se_non_si_puo_scrivere_resta_il_dm(caso):
    if caso != "senza_canale":
        await db.set_guild_setting(ID_SERVER, _shared.SETTING_AVVISO_CANALE, 8001)
    s, canale = _scena_con_canale(discord.Permissions(view_channel=True) if caso == "senza_permesso" else None)
    if caso == "scrittura_rifiutata":
        canale.send.side_effect = discord.Forbidden(AsyncMock(status=403), "no")
    cog = ModerationActionsCog(bot=None)
    await cog.kick.callback(cog, s.interazione, s.bersaglio, "Spam ripetuto")
    s.bersaglio.send.assert_awaited_once()


# MOD-060
async def test_con_dm_no_non_scrive_nemmeno_nel_canale():
    await db.set_guild_setting(ID_SERVER, _shared.SETTING_AVVISO_CANALE, 8001)
    s, canale = _scena_con_canale()
    cog = ModerationActionsCog(bot=None)
    await cog.kick.callback(cog, s.interazione, s.bersaglio, "Spam ripetuto", None, False)
    canale.send.assert_not_awaited()
    s.bersaglio.send.assert_not_awaited()


# MOD-060
async def test_il_comando_sceglie_e_toglie_il_canale_e_controlla_i_permessi_del_bot():
    s, canale = _scena_con_canale()
    s.moderatore.guild_permissions = discord.Permissions(manage_guild=True)
    s.server.me.guild_permissions = discord.Permissions.none()
    cog = OpzioniModerazioneCog(bot=None)
    await cog.avvisi.callback(cog, s.interazione, canale)
    assert await db.get_guild_setting(ID_SERVER, _shared.SETTING_AVVISO_CANALE) == 8001
    await cog.avvisi.callback(cog, fake_interaction(guild=s.server, user=s.moderatore), None)
    assert await db.get_guild_setting(ID_SERVER, _shared.SETTING_AVVISO_CANALE) is None
    cieco, canale_chiuso = _scena_con_canale(discord.Permissions(view_channel=True))
    cieco.moderatore.guild_permissions = discord.Permissions(manage_guild=True)
    await cog.avvisi.callback(cog, cieco.interazione, canale_chiuso)
    assert await db.get_guild_setting(ID_SERVER, _shared.SETTING_AVVISO_CANALE) is None
