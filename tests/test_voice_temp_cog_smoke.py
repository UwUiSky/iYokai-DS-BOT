"""
tests/test_voice_temp_cog_smoke.py
=====================================
Smoke test del cog vocali temporanei. Come per il ticket system,
verifica esplicitamente che CreateVoiceView sia persistente (non si
accontenta che setup() non sollevi eccezioni), e come per il logging
verifica esplicitamente che on_voice_state_update compaia in
bot.extra_events (non basta il nome del metodo, serve il decorator
@commands.Cog.listener() — vedi le due lezioni già in PROGRESS.md).
"""

import discord
from discord import app_commands
from discord.ext import commands

from core.premium import registry
from cogs.voice_temp.voice_temp import (
    MODULE_VOICE_TEMP,
    CreateVoiceView,
    setup as voice_temp_setup,
)


async def test_voice_temp_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await voice_temp_setup(bot)

    assert bot.get_cog("VoiceTempCog") is not None

    module = registry.get(MODULE_VOICE_TEMP)
    assert module is not None
    assert module.premium_capable is False

    comandi = {c.name for c in bot.tree.get_commands()}
    assert {"voicetemp-setup", "voicetemp-panel"} <= comandi

    voice_group = None
    for command in bot.tree.get_commands():
        if isinstance(command, app_commands.Group) and command.name == "voice":
            voice_group = command
            break
    assert voice_group is not None

    sottocomandi = {c.name for c in voice_group.commands}
    assert {"rename", "limit", "lock", "unlock", "kick", "transfer"} <= sottocomandi

    assert "on_voice_state_update" in bot.extra_events


def test_create_voice_view_e_davvero_persistente():
    view = CreateVoiceView()
    assert view.is_persistent() is True
    assert view.timeout is None

    bottone = view.children[0]
    assert isinstance(bottone, discord.ui.Button)
    assert bottone.custom_id == "iyokai_voice_temp_create"
