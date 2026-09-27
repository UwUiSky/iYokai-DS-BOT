"""
tests/test_restore_cog_smoke.py
===================================
Smoke test del cog Restore (/configura-restore, /restore-users).
"""

import discord
from discord.ext import commands

from cogs.utility.restore import setup as restore_setup


async def test_restore_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await restore_setup(bot)

    assert bot.get_cog("RestoreCog") is not None

    nomi_comandi = {c.name for c in bot.tree.get_commands()}
    assert {"configura-restore", "restore-users"} <= nomi_comandi
