"""
tests/test_poll_cog_smoke.py
================================
Smoke test del cog Poll.
"""

import discord
from discord.ext import commands

from core.premium import registry
from cogs.utility.poll import MODULE_POLL, setup as poll_setup


async def test_poll_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await poll_setup(bot)

    assert bot.get_cog("PollCog") is not None

    module = registry.get(MODULE_POLL)
    assert module is not None
    assert module.premium_capable is False

    nomi_comandi = {c.name for c in bot.tree.get_commands()}
    assert "poll" in nomi_comandi
