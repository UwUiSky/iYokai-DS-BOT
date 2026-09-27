"""
tests/test_snipe_cog_smoke.py
================================
Smoke test del cog Reactionsnipe/Ghost ping — stesso schema di
tests/test_advanced_logs_cog_smoke.py: verifica che i listener
risultino davvero registrati in bot.extra_events.
"""

import discord
from discord.ext import commands

from core.premium import registry
from cogs.utility.snipe import (
    MODULE_GHOST_PING,
    MODULE_REACTIONSNIPE,
    setup as snipe_setup,
)


async def test_snipe_cog_si_carica_e_i_listener_sono_registrati():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await snipe_setup(bot)

    assert bot.get_cog("SnipeCog") is not None

    reactionsnipe_module = registry.get(MODULE_REACTIONSNIPE)
    assert reactionsnipe_module is not None
    ghost_ping_module = registry.get(MODULE_GHOST_PING)
    assert ghost_ping_module is not None

    comandi = {c.name for c in bot.tree.get_commands()}
    assert "reactionsnipe" in comandi

    eventi_attesi = {"on_raw_reaction_remove", "on_message", "on_raw_message_delete"}
    assert eventi_attesi <= set(bot.extra_events.keys()), (
        "Uno o più listener non risultano registrati in bot.extra_events: "
        "probabilmente manca il decorator @commands.Cog.listener()."
    )
