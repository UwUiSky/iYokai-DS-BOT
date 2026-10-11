"""
tests/test_feed_alerts_cog_smoke.py
=======================================
Smoke test del cog Feed Alerts.
"""

import discord
from discord import app_commands
from discord.ext import commands

from core.premium import registry
from tests.support.percorsi import percorsi_del_gruppo
from cogs.utility.feed_alerts import MODULE_FEED_ALERTS, setup as feed_alerts_setup


async def test_feed_alerts_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await feed_alerts_setup(bot)

    assert bot.get_cog("FeedAlertsCog") is not None

    module = registry.get(MODULE_FEED_ALERTS)
    assert module is not None
    assert module.premium_capable is False

    assert {
        "alert feed", "alert twitch", "alert youtube-live", "alert rimuovi", "alert elenco", "alert webhook",
    } <= percorsi_del_gruppo("moduli")
