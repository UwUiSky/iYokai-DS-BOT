"""
tests/test_global_ban_cog_smoke.py
======================================
Smoke test del cog Ban Globale: caricamento reale in un Bot,
registrazione premium, comandi presenti — stesso schema di
tests/test_anti_raid_cog_smoke.py.
"""

import discord
from discord import app_commands
from discord.ext import commands

from core.premium import registry
from cogs.security.global_ban import MODULE_GLOBAL_BAN, setup as global_ban_setup


async def test_global_ban_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await global_ban_setup(bot)

    assert bot.get_cog("GlobalBanCog") is not None

    module = registry.get(MODULE_GLOBAL_BAN)
    assert module is not None
    assert module.premium_capable is True

    gruppo = None
    for command in bot.tree.get_commands():
        if isinstance(command, app_commands.Group) and command.name == "global-ban":
            gruppo = command
            break
    assert gruppo is not None

    nomi_comandi = {c.name for c in gruppo.commands}
    assert {"enable", "disable", "status"} <= nomi_comandi
