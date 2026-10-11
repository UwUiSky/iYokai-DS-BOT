"""
tests/test_restore_cog_smoke.py
===================================
Smoke test del cog Restore (/admin backup restore-modo|restore-utenti).
"""

import discord
from discord.ext import commands

from cogs.utility.restore import setup as restore_setup
from tests.support.percorsi import percorsi_del_gruppo


async def test_restore_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await restore_setup(bot)

    assert bot.get_cog("RestoreCog") is not None

    assert {"backup restore-modo", "backup restore-utenti"} <= percorsi_del_gruppo("admin")
