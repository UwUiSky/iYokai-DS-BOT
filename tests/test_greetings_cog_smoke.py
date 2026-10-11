"""
tests/test_greetings_cog_smoke.py
=====================================
Smoke test del cog Greetings.
"""

import discord
from discord import app_commands
from discord.ext import commands

from core.premium import registry
from tests.support.percorsi import percorsi_del_gruppo
from cogs.utility.greetings import MODULE_GREETINGS, setup as greetings_setup


async def test_greetings_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await greetings_setup(bot)

    assert bot.get_cog("GreetingsCog") is not None

    module = registry.get(MODULE_GREETINGS)
    assert module is not None
    assert module.premium_capable is False

    assert {"benvenuto benvenuto", "benvenuto addio", "benvenuto boost", "benvenuto anteprima"} <= percorsi_del_gruppo(
        "gestione"
    )

    assert {"on_member_join", "on_member_remove", "on_member_update"} <= set(
        bot.extra_events.keys()
    )
