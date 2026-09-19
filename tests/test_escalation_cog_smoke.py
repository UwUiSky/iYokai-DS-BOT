"""
tests/test_escalation_cog_smoke.py
======================================
Smoke test del cog Smart AutoMod Escalation Ladder.
"""

import discord
from discord import app_commands
from discord.ext import commands

from cogs.automod.escalation import setup as escalation_setup


async def test_escalation_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await escalation_setup(bot)

    assert bot.get_cog("EscalationCog") is not None

    escalation_group = None
    for command in bot.tree.get_commands():
        if isinstance(command, app_commands.Group) and command.name == "escalation":
            escalation_group = command
            break
    assert escalation_group is not None

    sottocomandi = {c.name for c in escalation_group.commands}
    assert {
        "enable", "disable", "set-reset-days", "set-step", "remove-step", "reset", "status",
    } <= sottocomandi

    assert "on_automod_action" in bot.extra_events
