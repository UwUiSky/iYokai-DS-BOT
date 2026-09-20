"""
tests/test_scheduled_messages_cog_smoke.py
===============================================
Smoke test del cog Scheduled Messages. Usa il registry e lo
scheduler GLOBALI (stesso motivo già documentato per reminders):
registry.register() e scheduler.register_handler() sollevano un
errore su doppia registrazione — un solo test per file.
"""

import discord
from discord import app_commands
from discord.ext import commands

from core.premium import registry
from core.scheduler import scheduler
from cogs.utility.scheduled_messages import (
    MODULE_SCHEDULED_MESSAGES,
    SCHEDULED_MESSAGE_ACTION_TYPE,
    setup as scheduled_messages_setup,
)


async def test_scheduled_messages_cog_si_carica_e_si_registra_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

    await scheduled_messages_setup(bot)

    assert bot.get_cog("ScheduledMessagesCog") is not None

    module = registry.get(MODULE_SCHEDULED_MESSAGES)
    assert module is not None
    assert module.premium_capable is False

    schedule_group = None
    for command in bot.tree.get_commands():
        if isinstance(command, app_commands.Group) and command.name == "schedule-message":
            schedule_group = command
            break
    assert schedule_group is not None

    sottocomandi = {c.name for c in schedule_group.commands}
    assert {"set", "list", "cancel"} <= sottocomandi

    assert SCHEDULED_MESSAGE_ACTION_TYPE in scheduler._handlers
