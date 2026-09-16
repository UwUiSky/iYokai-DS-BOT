"""
tests/test_automod_cog_smoke.py
==================================
Smoke test del cog AutoMod: caricamento reale in un Bot, registrazione
premium, parametri dei comandi leggibili da discord.py.
"""

import discord
from discord import app_commands
from discord.ext import commands

from core.premium import registry
from cogs.automod.automod import MODULE_AUTOMOD, setup as automod_setup


async def test_automod_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await automod_setup(bot)

    assert bot.get_cog("AutomodCog") is not None

    module = registry.get(MODULE_AUTOMOD)
    assert module is not None
    assert module.premium_capable is False  # sempre gratis, come da schema

    automod_group = None
    for command in bot.tree.get_commands():
        if isinstance(command, app_commands.Group) and command.name == "automod":
            automod_group = command
            break
    assert automod_group is not None

    nomi_comandi = {c.name for c in automod_group.commands}
    assert {"badword-add", "badword-remove", "badword-list", "invites", "sync"} <= nomi_comandi

    add_cmd = automod_group.get_command("badword-add")
    assert "word" in [p.name for p in add_cmd.parameters]

    invites_cmd = automod_group.get_command("invites")
    assert "enabled" in [p.name for p in invites_cmd.parameters]
