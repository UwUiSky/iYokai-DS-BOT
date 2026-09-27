"""
tests/test_entertainment_cog_smoke.py
==========================================
Smoke test del cog Entertainment (SPEC.md §16.1/§16.8) — tutti i
comandi vivono sotto UN SOLO gruppo top-level (/fun), per non
consumare 7 slot separati su un limite globale di Discord di 100
comandi top-level (vedi il docstring di cogs/fun/entertainment.py).
"""

import discord
from discord import app_commands
from discord.ext import commands

from core.premium import registry
from cogs.fun.entertainment import MODULE_FUN, setup as entertainment_setup


async def test_entertainment_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await entertainment_setup(bot)

    assert bot.get_cog("EntertainmentCog") is not None

    module = registry.get(MODULE_FUN)
    assert module is not None
    assert module.premium_capable is False

    fun_group = None
    for command in bot.tree.get_commands():
        if isinstance(command, app_commands.Group) and command.name == "fun":
            fun_group = command
            break
    assert fun_group is not None, "Il gruppo /fun non risulta registrato"

    sottocomandi = {c.name for c in fun_group.commands}
    assert {"coinflip", "dice", "rps", "8ball", "joke", "quote", "fact"} <= sottocomandi
