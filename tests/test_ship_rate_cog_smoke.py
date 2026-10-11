"""
tests/test_ship_rate_cog_smoke.py
=====================================
Smoke test del cog Ship/Rate.
"""

import discord
from discord.ext import commands

from core.premium import registry
from cogs.fun.ship_rate import MODULE_FUN, setup as ship_rate_setup


async def test_ship_rate_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await ship_rate_setup(bot)

    assert bot.get_cog("ShipRateCog") is not None

    module = registry.get(MODULE_FUN)
    assert module is not None
    assert module.premium_capable is False

    from core.command_groups import GRUPPI

    assert {"ship", "rate"} <= {c.name for c in GRUPPI["fun"].commands}
    assert {"ship", "rate"}.isdisjoint(c.name for c in bot.tree.get_commands())
