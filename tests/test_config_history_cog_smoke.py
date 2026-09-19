"""
tests/test_config_history_cog_smoke.py
==========================================
Smoke test del cog Config Diff & Rollback.
"""

import discord
from discord import app_commands
from discord.ext import commands

from cogs.utility.config_history import (
    RollbackConfirmView,
    setup as config_history_setup,
)


async def test_config_history_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await config_history_setup(bot)

    assert bot.get_cog("ConfigHistoryCog") is not None

    config_group = None
    for command in bot.tree.get_commands():
        if isinstance(command, app_commands.Group) and command.name == "config":
            config_group = command
            break
    assert config_group is not None

    sottocomandi = {c.name for c in config_group.commands}
    assert {"history", "rollback"} <= sottocomandi


def test_rollback_confirm_view_si_istanzia_correttamente():
    view = RollbackConfirmView(entry_id=42, requested_by_id=100)

    assert view.entry_id == 42
    assert view.requested_by_id == 100
    assert view.timeout == 60  # non persistente, per scelta dichiarata

    bottoni = [c for c in view.children if isinstance(c, discord.ui.Button)]
    etichette = {b.label for b in bottoni}
    assert {"Conferma rollback", "Annulla"} <= etichette
