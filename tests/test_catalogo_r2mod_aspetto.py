"""
tests/test_catalogo_r2mod_aspetto.py
====================================
Colore e icona dei casi nel log di moderazione scelti dal server (MOD-053). Database vero.
"""

from unittest.mock import AsyncMock

import discord
import pytest

from cogs.moderation import _shared
from cogs.moderation.opzioni import OpzioniModerazioneCog
from cogs.moderation._shared import MODULE_ACTIONS
from core import moderation_aspetto as asp
from core.database import db
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

G = 100


# MOD-053
def test_il_tipo_si_riconosce_dal_titolo_e_le_scelte_strane_si_scartano():
    assert [asp.tipo_da_titolo(t) for t in ("🔨 Ban in massa", "⏳ Tempban", "🔇 Mute (ruolo)", "⚠️ Troppi warn", "ciao", None)] == [
        "ban", "tempban", "mute", None, None, None,
    ]
    assert asp.pulita({"ban": {"colore": 99999999, "icona": "x" * 30}, "boh": {"colore": 1}, "kick": {"colore": 255}}) == {"kick": {"colore": 255}}
    assert asp.pulita("no") == {} and asp.icona_valida("🦊") and not asp.icona_valida("") and not asp.icona_valida("x" * 20)


# MOD-053
def test_si_cambia_la_copia_e_solo_per_il_tipo_scelto():
    embed = discord.Embed(title="🔨 Ban", color=discord.Color.red())
    nuovo = asp.applica(embed, {"ban": {"colore": 0x00FF00, "icona": "🦊"}})
    assert nuovo.title == "🦊 Ban" and nuovo.colour.value == 0x00FF00
    assert embed.title == "🔨 Ban" and embed.colour == discord.Color.red()  # l'originale non cambia
    assert asp.applica(embed, {"kick": {"colore": 1}}) is embed and asp.applica(embed, {}) is embed


@pytest.fixture
async def amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(G, MODULE_ACTIONS, True)
    yield
    database_module.db._modules_cache.clear()


# MOD-053
async def test_il_comando_salva_controlla_e_toglie(amb):
    cog = OpzioniModerazioneCog(bot=None)
    guild = fake_guild(G, owner_id=1)
    admin = fake_member(21, guild_permissions=discord.Permissions(manage_guild=True))
    scelta = discord.app_commands.Choice(name="ban", value="ban")

    async def esegui(**kw):
        i = fake_interaction(guild=guild, user=admin)
        await cog.aspetto.callback(cog, i, scelta, **kw)
        return i

    await esegui(colore="#00ff00", icona="🦊")
    assert await db.get_guild_setting(G, asp.SETTING_ASPETTO) == {"ban": {"colore": 0x00FF00, "icona": "🦊"}}
    i = await esegui(colore="verde")
    assert "colore" in i.response.send_message.await_args.args[0].lower()
    assert (await db.get_guild_setting(G, asp.SETTING_ASPETTO))["ban"]["colore"] == 0x00FF00
    await esegui(icona="x" * 30)
    assert (await db.get_guild_setting(G, asp.SETTING_ASPETTO))["ban"]["icona"] == "🦊"
    await esegui(colore="nessuno", icona="nessuno")
    assert await db.get_guild_setting(G, asp.SETTING_ASPETTO) == {}
    senza = fake_interaction(guild=guild, user=fake_member(22, guild_permissions=discord.Permissions.none()))
    await cog.aspetto.callback(cog, senza, scelta, "#111111")
    assert await db.get_guild_setting(G, asp.SETTING_ASPETTO) == {}


# MOD-053
async def test_il_log_esce_con_l_aspetto_scelto_e_senza_scelta_resta_com_e(amb, monkeypatch):
    guild = fake_guild(G)
    await db.set_guild_setting(G, _shared.SETTING_MOD_LOG_CHANNEL, 5)
    invia = AsyncMock()
    monkeypatch.setattr(_shared.router, "destinazione", AsyncMock(return_value=object()))
    monkeypatch.setattr(_shared.router, "invia_a", invia)
    embed = discord.Embed(title="🔨 Ban", color=discord.Color.red())
    await _shared.post_to_mod_log(guild, embed)
    assert invia.await_args.kwargs["embed"] is embed
    await db.set_guild_setting(G, asp.SETTING_ASPETTO, {"ban": {"icona": "🦊", "colore": 255}})
    await _shared.post_to_mod_log(guild, embed)
    inviato = invia.await_args.kwargs["embed"]
    assert inviato.title == "🦊 Ban" and inviato.colour.value == 255
