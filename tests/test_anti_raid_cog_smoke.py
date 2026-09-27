"""
tests/test_anti_raid_cog_smoke.py
=====================================
Smoke test del cog Anti-Raid: caricamento reale in un Bot,
registrazione premium, comandi presenti.
"""

import discord
from discord import app_commands
from discord.ext import commands

from core.premium import registry
from cogs.security.anti_raid import MODULE_ANTI_RAID, setup as anti_raid_setup


async def test_anti_raid_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await anti_raid_setup(bot)

    assert bot.get_cog("AntiRaidCog") is not None

    module = registry.get(MODULE_ANTI_RAID)
    assert module is not None
    assert module.premium_capable is True

    gruppo = None
    for command in bot.tree.get_commands():
        if isinstance(command, app_commands.Group) and command.name == "anti-raid":
            gruppo = command
            break
    assert gruppo is not None

    nomi_comandi = {c.name for c in gruppo.commands}
    assert {
        "enable", "join-rate", "account-age", "username-check",
        "avatar-check", "lockdown-action", "alert-channel", "status",
    } <= nomi_comandi
