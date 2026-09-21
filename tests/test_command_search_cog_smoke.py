"""
tests/test_command_search_cog_smoke.py
==========================================
Smoke test del cog /search.
"""

import discord
from discord.ext import commands

from cogs.utility.command_search import setup as command_search_setup


async def test_command_search_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await command_search_setup(bot)

    assert bot.get_cog("CommandSearchCog") is not None

    nomi_comandi = {c.name for c in bot.tree.get_commands()}
    assert "search" in nomi_comandi
