"""
tests/test_sticky_messages_cog_smoke.py
===========================================
Smoke test del cog Sticky Messages.
"""

import discord
from discord import app_commands
from discord.ext import commands

from core.premium import registry
from cogs.utility.sticky_messages import (
    MODULE_STICKY_MESSAGES,
    setup as sticky_messages_setup,
)


async def test_sticky_messages_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await sticky_messages_setup(bot)

    assert bot.get_cog("StickyMessagesCog") is not None

    module = registry.get(MODULE_STICKY_MESSAGES)
    assert module is not None
    assert module.premium_capable is False

    sticky_group = None
    for command in bot.tree.get_commands():
        if isinstance(command, app_commands.Group) and command.name == "sticky":
            sticky_group = command
            break
    assert sticky_group is not None

    sottocomandi = {c.name for c in sticky_group.commands}
    assert {"set", "remove"} <= sottocomandi

    assert "on_message" in bot.extra_events
