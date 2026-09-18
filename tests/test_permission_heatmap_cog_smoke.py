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

    nomi_comandi = {c.name for c in bot.tree.get_commands()}
    assert "permission-heatmap" in nomi_comandi

    assert "on_member_update" in bot.extra_events
