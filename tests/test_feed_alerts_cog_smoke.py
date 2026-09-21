"""
tests/test_feed_alerts_cog_smoke.py
=======================================
Smoke test del cog Feed Alerts.
"""

import discord
from discord import app_commands
from discord.ext import commands

from core.premium import registry
from cogs.utility.feed_alerts import MODULE_FEED_ALERTS, setup as feed_alerts_setup


async def test_feed_alerts_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await feed_alerts_setup(bot)

    assert bot.get_cog("FeedAlertsCog") is not None

    module = registry.get(MODULE_FEED_ALERTS)
    assert module is not None
    assert module.premium_capable is False

    alerts_group = None
    for command in bot.tree.get_commands():
        if isinstance(command, app_commands.Group) and command.name == "alerts":
            alerts_group = command
            break
    assert alerts_group is not None

    sottocomandi = {c.name for c in alerts_group.commands}
    assert {"add", "add-twitch", "remove", "list"} <= sottocomandi
