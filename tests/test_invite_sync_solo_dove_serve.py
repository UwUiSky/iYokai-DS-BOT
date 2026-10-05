"""
tests/test_invite_sync_solo_dove_serve.py
=========================================
LC-6: gli inviti si scaricano solo nei server dove un modulo li usa
(spam-trap o log avanzati). Prima `on_ready` li scaricava per tutti i
server, una chiamata a Discord per ognuno.
"""

from unittest.mock import MagicMock, create_autospec

import discord
import pytest
from discord.ext import commands

import cogs.security.invite_sync as modulo
from core.database import Database
from core.invite_tracker import InviteTracker
from tests.support.discord_fakes import fake_guild

SERVER_CON_SPAM_TRAP = 100
SERVER_CON_LOG_AVANZATI = 200
SERVER_SENZA_NIENTE = 300


@pytest.fixture
def cog(monkeypatch):
    attivi = {
        (SERVER_CON_SPAM_TRAP, "spam_trap"),
        (SERVER_CON_LOG_AVANZATI, "logging_advanced"),
    }
    db_finto = create_autospec(Database, instance=True)
    db_finto.is_module_active_for_guild.side_effect = (
        lambda guild_id, nome_modulo: (guild_id, nome_modulo) in attivi
    )
    monkeypatch.setattr(modulo, "db", db_finto)
    monkeypatch.setattr(modulo, "invite_tracker", InviteTracker())

    bot = create_autospec(commands.Bot, instance=True)
    bot.guilds = [_server(numero) for numero in (100, 200, 300)]
    return modulo.InviteSyncCog(bot)


def _server(guild_id: int) -> MagicMock:
    server = fake_guild(guild_id)
    server.invites.return_value = []
    return server


def _invito_di(server: MagicMock) -> MagicMock:
    invito = create_autospec(discord.Invite, instance=True)
    invito.guild = server
    return invito


async def test_all_avvio_si_leggono_gli_inviti_solo_dove_servono(cog):
    con_trap, con_log, senza = cog.bot.guilds

    await cog.on_ready()

    con_trap.invites.assert_awaited_once()
    con_log.invites.assert_awaited_once()
    senza.invites.assert_not_awaited()


async def test_un_server_che_da_errore_non_ferma_gli_altri(cog):
    con_trap, con_log, _ = cog.bot.guilds
    con_trap.invites.side_effect = RuntimeError("risposta inattesa")

    await cog.on_ready()

    con_log.invites.assert_awaited_once()


async def test_invito_creato_o_tolto_dove_non_serve_non_fa_niente(cog):
    _, _, senza = cog.bot.guilds

    await cog.on_invite_create(_invito_di(senza))
    await cog.on_invite_delete(_invito_di(senza))
    await cog.on_guild_join(senza)

    senza.invites.assert_not_awaited()


async def test_invito_creato_dove_serve_aggiorna_gli_inviti(cog):
    con_trap, _, _ = cog.bot.guilds

    await cog.on_invite_create(_invito_di(con_trap))

    con_trap.invites.assert_awaited_once()
