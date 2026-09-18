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

    nomi_comandi = {c.name for c in bot.tree.get_commands()}
    assert {"softban", "mute-role", "unmute-role", "mod-log-setup"} <= nomi_comandi


async def test_reason_obbligatorio_su_softban_e_mute():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await softban_mute_setup(bot)

    comandi_con_reason_obbligatorio = {"softban", "mute-role", "unmute-role"}
    for command in bot.tree.get_commands():
        if not isinstance(command, app_commands.Command):
            continue
        if command.name not in comandi_con_reason_obbligatorio:
            continue
        reason_param = next(p for p in command.parameters if p.name == "reason")
        assert reason_param.required is True, f"/{command.name}: reason deve essere obbligatorio"
