"""
tests/test_logging_cog_smoke.py
==================================
Smoke test del cog di logging. Il controllo più importante qui non è
il solito "il cog si carica": è che OGNI listener risulti davvero
registrato in bot.extra_events — verificato empiricamente (vedi
PROGRESS.md) che discord.py non registra un metodo on_xxx di un Cog
senza il decorator esplicito @commands.Cog.listener(). Un listener
scritto ma dimenticato del decorator passerebbe silenziosamente
inosservato leggendo il codice, ma non qui.
"""

import discord
from discord import app_commands
from discord.ext import commands

from core.premium import registry
from cogs.logging.basic_logs import MODULE_LOGGING, setup as logging_setup


async def test_logging_cog_si_carica_e_tutti_i_listener_sono_registrati():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await logging_setup(bot)

    assert bot.get_cog("BasicLogsCog") is not None

    module = registry.get(MODULE_LOGGING)
    assert module is not None
    assert module.premium_capable is False

    comandi = {c.name for c in bot.tree.get_commands()}
    assert {"logs-setup", "logs-status"} <= comandi

    # Il controllo che conta davvero: ognuno di questi eventi deve
    # comparire in bot.extra_events, altrimenti Discord non chiamerà
    # mai il metodo corrispondente, silenziosamente.
    eventi_attesi = {
        "on_member_join",
        "on_member_remove",
        "on_member_ban",
        "on_member_unban",
        "on_member_update",
        "on_guild_role_create",
        "on_guild_role_delete",
    }
    assert eventi_attesi <= set(bot.extra_events.keys()), (
        "Uno o più listener non risultano registrati in bot.extra_events: "
        "probabilmente manca il decorator @commands.Cog.listener() su "
        "uno dei metodi on_xxx del cog."
    )
