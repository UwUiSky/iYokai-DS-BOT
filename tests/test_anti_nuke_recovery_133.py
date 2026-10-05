"""
tests/test_anti_nuke_recovery_133.py
====================================
Issue #133, anti-nuke: il recupero.
- le cancellazioni fatte PRIMA di superare la soglia vengono recuperate
  appena l'autore la supera;
- il ruolo ricreato torna nella posizione di prima e ai suoi membri;
- il forum ricreato riavrà i suoi tag.
Server, canali, ruoli e membri sono finti fedeli.
"""

from unittest.mock import AsyncMock

import discord
import pytest
from discord import app_commands
from discord.ext import commands
from unittest.mock import create_autospec

import cogs.security.anti_nuke as modulo
from core.security_logic import NUKE_CATEGORY_CHANNEL, NUKE_CATEGORY_ROLE
from tests.support.discord_fakes import (
    fake_forum_channel,
    fake_member,
    fake_role,
    fake_text_channel,
)
from tests.test_anti_nuke_f1 import (  # noqa: F401  (fixture condivise)
    AUTORE_ID,
    BOT_ID,
    _canale_cancellato,
    _interazione,
    _server,
    _voce,
    attese,
    db_finto,
)


@pytest.fixture
async def cog_soglia_due(db_finto, attese):
    bot = create_autospec(commands.Bot, instance=True)
    bot.user = fake_member(user_id=BOT_ID, bot=True)
    cog = modulo.AntiNukeCog(bot)
    await cog.enable.callback(cog, _interazione(), True)
    for categoria, nome in ((NUKE_CATEGORY_CHANNEL, "Canali"), (NUKE_CATEGORY_ROLE, "Ruoli")):
        await cog.limits.callback(
            cog, _interazione(), app_commands.Choice(name=nome, value=categoria), 2, 60
        )
    return cog


def _canale_testuale(server, canale_id: int, nome: str):
    canale = _canale_cancellato(fake_text_channel(), server, nome)
    canale.id = canale_id
    canale.topic = None
    canale.nsfw = False
    canale.slowmode_delay = 0
    canale.is_news.return_value = False
    return canale


async def test_cancellazioni_sotto_soglia_sono_recuperate_al_superamento(cog_soglia_due):
    autore = fake_member(user_id=AUTORE_ID)
    voci = [
        _voce(discord.AuditLogAction.channel_delete, AUTORE_ID, i) for i in (7001, 7002, 7003)
    ]
    server = _server(autore, [voci])
    canali = [_canale_testuale(server, 7001 + n, f"c{n}") for n in range(3)]

    await cog_soglia_due.on_guild_channel_delete(canali[0])
    await cog_soglia_due.on_guild_channel_delete(canali[1])
    server.create_text_channel.assert_not_awaited()  # ancora sotto soglia

    await cog_soglia_due.on_guild_channel_delete(canali[2])  # supera la soglia

    nomi = sorted(c.kwargs["name"] for c in server.create_text_channel.await_args_list)
    assert nomi == ["c0", "c1", "c2"]


async def test_cancellazione_sotto_soglia_di_un_altro_autore_non_si_mescola(cog_soglia_due):
    autore = fake_member(user_id=AUTORE_ID)
    altro = 777
    voci = [
        _voce(discord.AuditLogAction.channel_delete, altro, 7001),
        _voce(discord.AuditLogAction.channel_delete, AUTORE_ID, 7002),
        _voce(discord.AuditLogAction.channel_delete, AUTORE_ID, 7003),
        _voce(discord.AuditLogAction.channel_delete, AUTORE_ID, 7004),
    ]
    server = _server(autore, [voci])
    canali = [_canale_testuale(server, 7001 + n, f"c{n}") for n in range(4)]
    for canale in canali:
        await cog_soglia_due.on_guild_channel_delete(canale)

    nomi = sorted(c.kwargs["name"] for c in server.create_text_channel.await_args_list)
    assert nomi == ["c1", "c2", "c3"]  # c0 era di un altro, sotto soglia


async def test_ruolo_ricreato_con_posizione_e_membri(cog_soglia_due):
    cog = cog_soglia_due
    autore = fake_member(user_id=AUTORE_ID)
    voci = [_voce(discord.AuditLogAction.role_delete, AUTORE_ID, 9000 + n) for n in range(3)]
    server = _server(autore, [voci])
    server.me.top_role = fake_role(role_id=5, name="Yokai", position=4)
    nuovo = fake_role(role_id=9100, name="Clan", position=1)
    nuovo.edit = AsyncMock()
    server.create_role.return_value = nuovo

    ruoli = []
    for n in range(3):
        ruolo = fake_role(role_id=9000 + n, name=f"R{n}", position=9)
        ruolo.guild = server
        ruolo.colour = discord.Colour.default()
        ruolo.hoist = False
        ruolo.mentionable = False
        ruolo.members = [fake_member(user_id=100 + n), fake_member(user_id=200 + n)]
        ruoli.append(ruolo)

    for ruolo in ruoli:
        await cog.on_guild_role_delete(ruolo)

    assert server.create_role.await_count == 3
    # posizione di prima, ma mai sopra il ruolo più alto del bot (4 - 1)
    assert nuovo.edit.await_args_list[0].kwargs["position"] == 3
    for ruolo in ruoli:
        for membro in ruolo.members:
            membro.add_roles.assert_awaited()
            assert membro.add_roles.await_args.args[0] is nuovo
            assert len(membro.add_roles.await_args.kwargs["reason"]) <= 512


async def test_forum_ricreato_con_i_suoi_tag(cog_soglia_due):
    cog = cog_soglia_due
    autore = fake_member(user_id=AUTORE_ID)
    voci = [_voce(discord.AuditLogAction.channel_delete, AUTORE_ID, i) for i in (7001, 7002, 7003)]
    server = _server(autore, [voci])
    forum = _canale_cancellato(fake_forum_channel(), server, "aiuto")
    forum.id = 7003
    forum.topic = None
    forum.nsfw = False
    forum.slowmode_delay = 0
    forum.is_media.return_value = False
    forum.available_tags = [
        discord.ForumTag(name="Risolto", moderated=True),
        discord.ForumTag(name="Domanda"),
    ]
    for n in range(2):
        await cog.on_guild_channel_delete(_canale_testuale(server, 7001 + n, f"c{n}"))
    await cog.on_guild_channel_delete(forum)

    tag = server.create_forum.call_args.kwargs["available_tags"]
    assert [(t.name, t.moderated) for t in tag] == [("Risolto", True), ("Domanda", False)]
