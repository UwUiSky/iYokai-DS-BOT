"""
tests/test_backup_cog_smoke.py
==================================
Smoke test del cog Backup (/define-main, /define-backup).
"""

import discord
from discord.ext import commands

from cogs.utility.backup import setup as backup_setup


async def test_backup_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await backup_setup(bot)

    assert bot.get_cog("BackupCog") is not None

    nomi_comandi = {c.name for c in bot.tree.get_commands()}
    assert {"define-main", "define-backup"} <= nomi_comandi
