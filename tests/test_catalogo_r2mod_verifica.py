"""
tests/test_catalogo_r2mod_verifica.py
=====================================
Verifica (#118, r2mod): pannello personalizzato (VER-028), ruolo avvisato a ogni account doppio (VER-023). Database vero.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord

from cogs.security import alt_detection as cog_alt
from core import alt_detection_logic as logica
from core.database import db
from core.verify_logic import pannello_personalizzato
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role
from tests.test_verify_risposta_subito import GUILD_ID, scenario  # noqa: F401


# VER-028
def test_il_pannello_personalizzato_controlla_colore_e_lunghezze():
    ok, errore = pannello_personalizzato("Benvenuto", "Premi per entrare", "#c24a3a", "Entra", "🦊")
    assert errore is None and ok.colore == 0xC24A3A and ok.bottone == "Entra"
    assert pannello_personalizzato(None, None, "rosso", None, None)[1] is not None
    assert pannello_personalizzato("x" * 300, None, None, None, None)[1] is not None
    assert pannello_personalizzato(None, "x" * 2001, None, None, None)[1] is not None
    assert pannello_personalizzato(None, None, None, "x" * 81, None)[1] is not None
    assert pannello_personalizzato(None, None, None, None, "non un emoji lunghissimo")[1] is not None
    vuoto, errore = pannello_personalizzato(None, None, None, None, None)
    assert errore is None and vuoto.titolo is None


# VER-028
async def test_il_pannello_esce_con_titolo_testo_colore_e_bottone_scelti(scenario):
    await scenario.configura(captcha=False)
    i = fake_interaction(guild=scenario.server, user=fake_member(1))
    i.original_response = AsyncMock(return_value=MagicMock(channel=MagicMock(id=5), id=6))
    await scenario.cog.panel_cmd.callback(scenario.cog, i, "Porta del bosco", "Premi per entrare", "#c24a3a", "Entra", "🦊")
    kw = i.response.send_message.call_args.kwargs
    assert kw["embed"].title == "Porta del bosco" and kw["embed"].description == "Premi per entrare"
    assert kw["embed"].colour.value == 0xC24A3A
    assert kw["view"].children[0].label == "Entra" and str(kw["view"].children[0].emoji) == "🦊"
    assert kw["view"].children[0].custom_id  # resta il bottone persistente di sempre
    assert kw["allowed_mentions"].roles is False and kw["allowed_mentions"].everyone is False


# VER-028
async def test_un_pannello_con_colore_sbagliato_non_si_pubblica(scenario):
    await scenario.configura(captcha=False)
    i = fake_interaction(guild=scenario.server, user=fake_member(1))
    await scenario.cog.panel_cmd.callback(scenario.cog, i, None, None, "verde", None, None)
    i.response.send_message.assert_awaited_once()
    assert "embed" not in i.response.send_message.call_args.kwargs


def _canale_e_server(ruolo_id):
    canale = MagicMock(spec=discord.TextChannel)
    canale.send = AsyncMock()
    guild = fake_guild(guild_id=GUILD_ID)
    guild.get_channel = MagicMock(return_value=canale)
    ruolo = fake_role(ruolo_id, "Staff", position=3)
    guild.get_role = lambda rid: ruolo if rid == ruolo_id else None
    return canale, guild


# VER-023
async def test_l_avviso_dell_account_doppio_pinga_solo_il_ruolo_scelto(clean_db, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    canale, guild = _canale_e_server(321)
    await db.set_guild_setting(GUILD_ID, cog_alt.SETTING_RUOLO_AVVISO_ALT, 321)
    monkeypatch.setattr(cog_alt.verify_repo, "get_config", AsyncMock(return_value=SimpleNamespace(log_channel_id=5)))
    assert await cog_alt.avvisa_staff(guild, fake_member(1), [logica.Doppio(2, "alto")])
    kw = canale.send.await_args.kwargs
    assert kw["content"] == "<@&321>"
    assert kw["allowed_mentions"].everyone is False and kw["allowed_mentions"].users is False
    assert [r.id for r in kw["allowed_mentions"].roles] == [321]


# VER-023
async def test_senza_ruolo_o_con_ruolo_sparito_nessun_ping(clean_db, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    canale, guild = _canale_e_server(321)
    monkeypatch.setattr(cog_alt.verify_repo, "get_config", AsyncMock(return_value=SimpleNamespace(log_channel_id=5)))
    await cog_alt.avvisa_staff(guild, fake_member(1), [logica.Doppio(2, "alto")])
    assert canale.send.await_args.kwargs["content"] is None
    await db.set_guild_setting(GUILD_ID, cog_alt.SETTING_RUOLO_AVVISO_ALT, 999)  # il ruolo non esiste più
    await cog_alt.avvisa_staff(guild, fake_member(1), [logica.Doppio(2, "alto")])
    assert canale.send.await_args.kwargs["content"] is None


# VER-023
async def test_il_ruolo_si_sceglie_solo_con_menziona_tutti_e_mai_everyone(scenario):
    ruolo = fake_role(321, "Staff", position=1)
    for permessi, ruolo_scelto, atteso in (
        (discord.Permissions(manage_guild=True), ruolo, None),
        (discord.Permissions(manage_guild=True, mention_everyone=True), ruolo, 321),
        (discord.Permissions(mention_everyone=True), fake_role(0, "@everyone", position=0), None),
    ):
        await db.set_guild_setting(GUILD_ID, cog_alt.SETTING_RUOLO_AVVISO_ALT, None)
        i = fake_interaction(guild=scenario.server, user=fake_member(55, guild_permissions=permessi))
        await scenario.cog.options_cmd.callback(scenario.cog, i, None, None, None, None, False, None, ruolo_scelto)
        assert await db.get_guild_setting(GUILD_ID, cog_alt.SETTING_RUOLO_AVVISO_ALT) == atteso
