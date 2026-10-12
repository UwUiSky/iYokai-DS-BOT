"""
tests/test_moderation_clear_filtri.py
=====================================
Filtri di /mod clear (core/clear_filter_logic.py) e righe di log di
clear, lock, unlock, slowmode (M 1.8).
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.moderation._shared import (
    MODULE_CHANNEL_CONTROL,
    MODULE_CLEAR,
    SETTING_MOD_LOG_CHANNEL,
)
from cogs.moderation.channel_control import ModerationChannelControlCog
from cogs.moderation.clear import ModerationClearCog
from core.clear_filter_logic import FiltriClear, messaggio_passa
from core.database import db
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_message,
    fake_role,
    fake_text_channel,
)


def _msg(testo="", *, bot=False, allegati=(), embeds=(), menzioni=(), fissato=False, webhook=None, ruoli=()):
    m = MagicMock()
    m.content = testo
    m.author = MagicMock(id=5, bot=bot, roles=list(ruoli))
    m.attachments = list(allegati)
    m.embeds = list(embeds)
    m.mentions = list(menzioni)
    m.role_mentions = []
    m.pinned = fissato
    m.webhook_id = webhook
    return m


@pytest.mark.parametrize(
    "filtri,messaggio,atteso",
    [
        (FiltriClear(contiene="ciao"), _msg("Ciao a tutti"), True),
        (FiltriClear(contiene="ciao"), _msg("salve"), False),
        (FiltriClear(non_contiene="spam"), _msg("ok"), True),
        (FiltriClear(non_contiene="spam"), _msg("SPAM qui"), False),
        (FiltriClear(solo_link=True), _msg("guarda https://esempio.it/x"), True),
        (FiltriClear(solo_link=True), _msg("niente"), False),
        (FiltriClear(solo_inviti=True), _msg("vieni discord.gg/abc123"), True),
        (FiltriClear(solo_inviti=True), _msg("https://esempio.it"), False),
        (FiltriClear(solo_embed=True), _msg(embeds=[1]), True),
        (FiltriClear(solo_menzioni=True), _msg(menzioni=[1]), True),
        (FiltriClear(solo_menzioni=True), _msg("x"), False),
        (FiltriClear(solo_persone=True), _msg(bot=True), False),
        (FiltriClear(solo_persone=True), _msg(webhook=9), False),
        (FiltriClear(solo_bot=True), _msg(webhook=9), True),
        (FiltriClear(salta_fissati=True), _msg(fissato=True), False),
        (FiltriClear(ruolo_id=7), _msg(ruoli=[fake_role(role_id=7)]), True),
        (FiltriClear(ruolo_id=7), _msg(ruoli=[fake_role(role_id=8)]), False),
        (FiltriClear(autore_id=6), _msg("x"), False),
        (FiltriClear(contiene="a", solo_link=True), _msg("a senza link"), False),
    ],
)
def test_filtri(filtri, messaggio, atteso):
    assert messaggio_passa(messaggio, filtri) is atteso


ID_SERVER = 100
ID_LOG = 7001


@pytest.fixture
async def ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    for modulo in (MODULE_CLEAR, MODULE_CHANNEL_CONTROL):
        await db.set_module_active_for_guild(ID_SERVER, modulo, True)
    await db.set_guild_setting(ID_SERVER, SETTING_MOD_LOG_CHANNEL, ID_LOG)
    server = fake_guild(ID_SERVER)
    canale_log = fake_text_channel(ID_LOG, "mod-log")
    canale_log.send = AsyncMock()
    server.get_channel.return_value = canale_log
    mod = fake_member(10)
    canale = fake_text_channel(55, "generale")
    canale.purge = AsyncMock(return_value=[1, 2, 3])
    canale.set_permissions = AsyncMock()
    canale.overwrites_for = MagicMock(return_value=discord.PermissionOverwrite())
    canale.edit = AsyncMock()
    inter = fake_interaction(guild=server, user=mod, channel=canale)
    yield inter, canale, canale_log
    database_module.db._modules_cache.clear()


async def test_clear_filtra_e_scrive_nel_log(ambiente):
    inter, canale, canale_log = ambiente
    cog = ModerationClearCog(bot=None)

    await cog.clear.callback(cog, inter, 50, contains="ciao", links_only=True)

    check = canale.purge.call_args.kwargs["check"]
    assert check(_msg("ciao https://a.it")) and not check(_msg("ciao"))
    embed = canale_log.send.call_args.kwargs["embed"]
    assert any("contiene" in f.value for f in embed.fields)


async def test_clear_in_un_altro_canale(ambiente):
    inter, canale, _ = ambiente
    altro = fake_text_channel(66, "altro")
    altro.purge = AsyncMock(return_value=[])
    cog = ModerationClearCog(bot=None)

    await cog.clear.callback(cog, inter, 10, channel=altro)

    altro.purge.assert_awaited()
    canale.purge.assert_not_awaited()


async def test_clear_errore_http_non_esplode(ambiente):
    inter, canale, _ = ambiente
    canale.purge.side_effect = discord.HTTPException(MagicMock(status=500, reason="x"), "x")
    cog = ModerationClearCog(bot=None)

    await cog.clear.callback(cog, inter, 10)

    assert "Non sono riuscito" in inter.followup.send.call_args.args[0]


async def test_lock_unlock_slowmode_lasciano_una_riga_di_log(ambiente):
    inter, canale, canale_log = ambiente
    cog = ModerationChannelControlCog(bot=None)
    inter.guild.default_role = fake_role(role_id=ID_SERVER)

    await cog.lock.callback(cog, inter, None, "Pulizia in corso")
    await cog.unlock.callback(cog, inter, None)
    await cog.slowmode.callback(cog, inter, 10, None)

    assert canale_log.send.await_count == 3
    for chiamata in canale_log.send.call_args_list:
        assert any(f.name == "Moderatore" for f in chiamata.kwargs["embed"].fields)


async def test_clear_su_un_canale_senza_permesso_dell_utente_non_cancella(ambiente):
    inter, canale, _ = ambiente
    altro = fake_text_channel(66, "staff-privato")
    altro.purge = AsyncMock(return_value=[])
    altro.permissions_for = MagicMock(return_value=discord.Permissions(view_channel=False))
    cog = ModerationClearCog(bot=None)

    await cog.clear.callback(cog, inter, 10, channel=altro)

    altro.purge.assert_not_awaited()
    assert inter.response.send_message.call_args.kwargs["ephemeral"] is True
    altro.permissions_for.assert_called_with(inter.user)


async def test_clear_senza_gestire_messaggi_nel_canale_non_cancella(ambiente):
    inter, canale, _ = ambiente
    canale.permissions_for = MagicMock(
        return_value=discord.Permissions(view_channel=True, manage_messages=False)
    )
    cog = ModerationClearCog(bot=None)

    await cog.clear.callback(cog, inter, 10)

    canale.purge.assert_not_awaited()
