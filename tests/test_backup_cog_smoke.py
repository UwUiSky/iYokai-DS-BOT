"""
tests/test_backup_cog_smoke.py
==================================
Smoke test del cog Backup (/backup main|crea|promuovi).
"""

import discord
from discord.ext import commands

from cogs.utility.backup import setup as backup_setup
from tests.support.percorsi import percorsi_del_gruppo


async def test_backup_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await backup_setup(bot)

    assert bot.get_cog("BackupCog") is not None

    assert {"main", "crea", "promuovi"} <= percorsi_del_gruppo("backup")
