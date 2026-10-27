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

    gruppo = bot.tree.get_command("log")
    cerca = gruppo.get_command("cerca")
    assert {c.name for c in cerca.commands} == {"utente", "canale", "ruolo"}
    assert gruppo.get_command("esporta") is not None
    await bot.remove_cog("LogsQueryCog")
