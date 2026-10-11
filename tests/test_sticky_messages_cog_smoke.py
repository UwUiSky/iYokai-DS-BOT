"""
tests/test_sticky_messages_cog_smoke.py
===========================================
Smoke test del cog Sticky Messages.
"""

import discord
from discord import app_commands
from discord.ext import commands

from core.premium import registry
from tests.support.percorsi import comando_nel_gruppo, percorsi_del_gruppo
from cogs.utility.sticky_messages import (
    MODULE_STICKY_MESSAGES,
    setup as sticky_messages_setup,
)


async def test_sticky_messages_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await sticky_messages_setup(bot)

    assert bot.get_cog("StickyMessagesCog") is not None

    module = registry.get(MODULE_STICKY_MESSAGES)
    assert module is not None
    assert module.premium_capable is False

    assert {"messaggi sticky-set", "messaggi sticky-togli"} <= percorsi_del_gruppo("admin")

    assert "on_message" in bot.extra_events


async def test_sticky_set_dichiara_la_lunghezza_massima_del_testo():
    """Un messaggio Discord tiene 2000 caratteri: lo sticky non può superarli."""
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await sticky_messages_setup(bot)

    comando = comando_nel_gruppo("admin", "messaggi sticky-set")
    opzioni = {o["name"]: o for o in comando.to_dict(bot.tree)["options"]}

    assert opzioni["message"]["max_length"] == 2000
