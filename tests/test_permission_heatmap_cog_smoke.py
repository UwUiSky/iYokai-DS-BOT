"""
tests/test_permission_heatmap_cog_smoke.py
==============================================
Smoke test del cog Permission Risk Heatmap.
"""

import discord
from discord.ext import commands

from core.premium import registry
from cogs.security.permission_heatmap import (
    MODULE_PERMISSION_HEATMAP,
    setup as permission_heatmap_setup,
)


async def test_permission_heatmap_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await permission_heatmap_setup(bot)

    assert bot.get_cog("PermissionHeatmapCog") is not None

    module = registry.get(MODULE_PERMISSION_HEATMAP)
    assert module is not None
    assert module.premium_capable is True  # candidato premium, come Spam Trap

    assert bot.tree.get_command("security").get_command("heatmap") is not None

    assert "on_member_update" in bot.extra_events
    await bot.remove_cog("PermissionHeatmapCog")
