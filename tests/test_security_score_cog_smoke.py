"""
tests/test_security_score_cog_smoke.py
==========================================
Smoke test del cog Security Score: caricamento reale in un Bot,
registrazione (sempre gratuita), comando presente.
"""

import discord
from discord import app_commands
from discord.ext import commands

from core.premium import registry
from cogs.security.security_score import MODULE_SECURITY_SCORE, setup as security_score_setup


async def test_security_score_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await security_score_setup(bot)

    assert bot.get_cog("SecurityScoreCog") is not None

    module = registry.get(MODULE_SECURITY_SCORE)
    assert module is not None
    assert module.premium_capable is False

    comando = bot.tree.get_command("security").get_command("score")
    assert comando is not None
    await bot.remove_cog("SecurityScoreCog")
