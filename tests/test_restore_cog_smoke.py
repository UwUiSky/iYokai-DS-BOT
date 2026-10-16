"""
tests/test_restore_cog_smoke.py
===================================
Smoke test del cog Restore (/backup restore-modo|restore-utenti).
"""

import discord
from discord.ext import commands

from cogs.utility.restore import BottoneConsensoRestore
from cogs.utility.restore import setup as restore_setup
from tests.support.percorsi import percorsi_del_gruppo


async def test_restore_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await restore_setup(bot)

    assert bot.get_cog("RestoreCog") is not None

    assert {"restore-modo", "restore-utenti"} <= percorsi_del_gruppo("backup")
    # M 12.12: i bottoni del consenso rispondono anche dopo un riavvio.
    registrati = bot._connection._view_store._dynamic_items
    assert BottoneConsensoRestore.__discord_ui_compiled_template__ in registrati
