"""
tests/test_reminders_cog_smoke.py
=====================================
Smoke test del cog Reminder. Usa il registry e lo scheduler GLOBALI
(stesso motivo già documentato in test_moderation_actions_smoke.py):
registry.register() e scheduler.register_handler() sollevano un
errore se lo stesso nome viene registrato due volte, quindi setup()
per questo cog deve girare una volta sola nell'intera sessione di
test — UN SOLO test in questo file, non separarlo in più funzioni.
"""

import discord
from discord import app_commands
from discord.ext import commands

from core.premium import registry
from core.scheduler import scheduler
from cogs.utility.reminders import (
    MODULE_REMINDERS,
    REMINDER_ACTION_TYPE,
    setup as reminders_setup,
)


async def test_reminders_cog_si_carica_e_si_registra_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

    await reminders_setup(bot)

    assert bot.get_cog("RemindersCog") is not None

    module = registry.get(MODULE_REMINDERS)
    assert module is not None
    assert module.premium_capable is False

    reminder_group = None
    for command in bot.tree.get_commands():
        if isinstance(command, app_commands.Group) and command.name == "reminder":
            reminder_group = command
            break
    assert reminder_group is not None

    sottocomandi = {c.name for c in reminder_group.commands}
    assert {"set", "list", "cancel"} <= sottocomandi

    assert REMINDER_ACTION_TYPE in scheduler._handlers
