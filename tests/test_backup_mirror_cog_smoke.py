"""
tests/test_backup_mirror_cog_smoke.py
=========================================
Smoke test del cog BackupMirrorCog (SPEC.md §11.9) — nessun comando,
solo il listener on_message: si carica e, quando viene scaricato,
chiude il dispatcher.
"""

from unittest.mock import AsyncMock

import discord
from discord.ext import commands

from cogs.utility.backup_mirror import setup as backup_mirror_setup


async def test_backup_mirror_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await backup_mirror_setup(bot)

    assert bot.get_cog("BackupMirrorCog") is not None


async def test_scaricare_il_cog_chiude_il_dispatcher_senza_task_volanti():
    """
    LIM-53: la chiusura del dispatcher non va lanciata come task senza
    riferimento (Python può eliminarlo prima che finisca). Quando
    remove_cog ritorna, la chiusura è già avvenuta.
    """
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await backup_mirror_setup(bot)
    cog = bot.get_cog("BackupMirrorCog")
    cog.dispatcher.close = AsyncMock()

    await bot.remove_cog("BackupMirrorCog")

    cog.dispatcher.close.assert_awaited_once()
