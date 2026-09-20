"""
tests/test_owner_premium_cog_smoke.py
=========================================
Smoke test del cog owner/premium — mancava, colmato mentre si
aggiungeva /owner memory-status (che vive in questo file per un
motivo tecnico: app_commands.Group non ammette due gruppi di primo
livello con lo stesso nome "owner" registrati da cog diversi — vedi
il commento nel file del cog).
"""

import discord
from discord import app_commands
from discord.ext import commands

from cogs.utility.owner_premium import setup as owner_premium_setup


async def test_owner_premium_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await owner_premium_setup(bot)

    assert bot.get_cog("OwnerPremiumCog") is not None

    owner_group = None
    for command in bot.tree.get_commands():
        if isinstance(command, app_commands.Group) and command.name == "owner":
            owner_group = command
            break
    assert owner_group is not None, "Il gruppo /owner non risulta registrato"

    sottocomandi = {c.name for c in owner_group.commands}
    assert {
        "premium-list",
        "premium-toggle",
        "whitelist-add",
        "whitelist-remove",
        "memory-status",
        "blacklist-user-add",
        "blacklist-user-remove",
        "blacklist-user-list",
        "blacklist-guild-add",
        "blacklist-guild-remove",
        "blacklist-guild-list",
        "leave-guild",
        "announce",
        "stats",
        "premium-panel",
        "eval",
        "shell",
        "cog-load",
        "cog-unload",
        "cog-reload",
    } <= sottocomandi
