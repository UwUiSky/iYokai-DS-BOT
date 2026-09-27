"""
tests/test_anti_nuke_cog_smoke.py
=====================================
Smoke test del cog Anti-Nuke: caricamento reale in un Bot,
registrazione premium, comandi presenti.
"""

import discord
from discord import app_commands
from discord.ext import commands

from core.premium import registry
from cogs.security.anti_nuke import MODULE_ANTI_NUKE, setup as anti_nuke_setup


async def test_anti_nuke_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await anti_nuke_setup(bot)

    assert bot.get_cog("AntiNukeCog") is not None

    module = registry.get(MODULE_ANTI_NUKE)
    assert module is not None
    assert module.premium_capable is True

    gruppo = None
    for command in bot.tree.get_commands():
        if isinstance(command, app_commands.Group) and command.name == "anti-nuke":
            gruppo = command
            break
    assert gruppo is not None

    nomi_comandi = {c.name for c in gruppo.commands}
    assert {
        "enable", "limits", "trusted-add", "trusted-remove",
        "punish-action", "recovery", "status",
    } <= nomi_comandi
