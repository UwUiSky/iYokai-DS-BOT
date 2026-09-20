"""
tests/test_server_stats_cog_smoke.py
========================================
Smoke test del cog Server Stats.
"""

import discord
from discord.ext import commands

from core.premium import registry
from cogs.utility.server_stats import (
    MODULE_SERVER_STATS,
    setup as server_stats_setup,
)


async def test_server_stats_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await server_stats_setup(bot)

    assert bot.get_cog("ServerStatsCog") is not None

    module = registry.get(MODULE_SERVER_STATS)
    assert module is not None
    assert module.premium_capable is False

    nomi_comandi = {c.name for c in bot.tree.get_commands()}
    assert "serverstats" in nomi_comandi
