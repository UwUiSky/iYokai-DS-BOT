"""
tests/test_logs_query_cog_smoke.py
======================================
Smoke test del cog di interrogazione del log eventi.
"""

import discord
from discord import app_commands
from discord.ext import commands

from cogs.logging.logs_query import setup as logs_query_setup


async def test_logs_query_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await logs_query_setup(bot)

    assert bot.get_cog("LogsQueryCog") is not None

    logs_group = None
    for command in bot.tree.get_commands():
        if isinstance(command, app_commands.Group) and command.name == "logs":
            logs_group = command
            break
    assert logs_group is not None

    sottocomandi = {c.name for c in logs_group.commands}
    assert {"user", "channel", "export"} <= sottocomandi
