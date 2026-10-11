"""
tests/test_moderation_softban_mute_smoke.py
===============================================
Smoke test del cog softban/mute via ruolo. Verifica anche
esplicitamente "reason obbligatorio" sui suoi comandi, stesso
controllo già fatto per actions.py.
"""

import discord
from discord import app_commands
from discord.ext import commands

from cogs.moderation.softban_mute import setup as softban_mute_setup


async def test_softban_mute_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await softban_mute_setup(bot)

    assert bot.get_cog("ModerationSoftbanMuteCog") is not None

    assert bot.tree.get_command("modban").get_command("softban") is not None
    nomi_mod = {c.name for c in bot.tree.get_command("mod").commands}
    assert {"mute", "unmute"} <= nomi_mod
    await bot.remove_cog("ModerationSoftbanMuteCog")


async def test_reason_obbligatorio_su_softban_e_mute():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await softban_mute_setup(bot)

    comandi = [
        bot.tree.get_command("modban").get_command("softban"),
        bot.tree.get_command("mod").get_command("mute"),
        bot.tree.get_command("mod").get_command("unmute"),
    ]
    for command in comandi:
        reason_param = next(p for p in command.parameters if p.name == "reason")
        assert reason_param.required is True, f"/{command.qualified_name}: reason deve essere obbligatorio"
    await bot.remove_cog("ModerationSoftbanMuteCog")
