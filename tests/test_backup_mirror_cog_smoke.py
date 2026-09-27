"""
tests/test_backup_mirror_cog_smoke.py
=========================================
Smoke test del cog BackupMirrorCog (SPEC.md §11.9) — nessun comando,
solo il listener on_message; qui basta verificare che si carichi.
"""

import discord
from discord.ext import commands

from cogs.utility.backup_mirror import setup as backup_mirror_setup


async def test_backup_mirror_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await backup_mirror_setup(bot)

    assert bot.get_cog("BackupMirrorCog") is not None
