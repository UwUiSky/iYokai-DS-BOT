"""
tests/test_remaining_moderation_smoke.py
============================================
Smoke test per gli ultimi tre cog di moderazione (channel_control,
report, clear): caricamento reale in un Bot, registrazione premium
corretta, e — per clear.py, che combina @requires_module con
@app_commands.command come case_system.py — verifica che i parametri
restino leggibili da discord.py attraverso il decorator.
"""

import discord
from discord import app_commands
from discord.ext import commands

from core.premium import registry
from cogs.moderation.channel_control import (
    MODULE_CHANNEL_CONTROL,
    setup as channel_control_setup,
)
from cogs.moderation.report import MODULE_REPORT, setup as report_setup
from cogs.moderation.clear import MODULE_CLEAR, setup as clear_setup


async def test_channel_control_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await channel_control_setup(bot)

    assert bot.get_cog("ModerationChannelControlCog") is not None

    module = registry.get(MODULE_CHANNEL_CONTROL)
    assert module is not None
    assert module.premium_capable is False  # sempre gratis, come da schema

    comandi = {c.name for c in bot.tree.get_commands()}
    assert {"lock", "unlock", "slowmode"} <= comandi


async def test_report_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await report_setup(bot)

    assert bot.get_cog("ModerationReportCog") is not None

    module = registry.get(MODULE_REPORT)
    assert module is not None
    assert module.premium_capable is False

    comandi = {c.name for c in bot.tree.get_commands()}
    assert {"report", "report-setup"} <= comandi


async def test_clear_si_carica_e_parametri_leggibili_attraverso_decorator():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await clear_setup(bot)

    assert bot.get_cog("ModerationClearCog") is not None

    module = registry.get(MODULE_CLEAR)
    assert module is not None
    assert module.premium_capable is True  # candidato premium, come da schema

    clear_cmd = None
    for command in bot.tree.get_commands():
        if isinstance(command, app_commands.Command) and command.name == "clear":
            clear_cmd = command
            break
    assert clear_cmd is not None, "Il comando /clear non risulta registrato"

    param_names = {p.name for p in clear_cmd.parameters}
    # Verifica il punto critico: i parametri devono essere quelli
    # reali della funzione, non persi dietro *args/**kwargs del
    # decorator @requires_module.
    assert {"amount", "member", "bots_only", "attachments_only"} <= param_names
