"""
tests/test_invite_sync_cog_smoke.py
=======================================
Smoke test di InviteSyncCog: verifica esplicitamente che tutti e
quattro i listener risultino registrati in bot.extra_events (stessa
lezione già consolidata: @commands.Cog.listener() è obbligatorio,
il solo nome on_xxx non basta a discord.py).
"""

import discord
from discord.ext import commands

from cogs.security.invite_sync import setup as invite_sync_setup


async def test_invite_sync_cog_si_carica_e_i_listener_sono_registrati():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await invite_sync_setup(bot)

    assert bot.get_cog("InviteSyncCog") is not None

    eventi_attesi = {
        "on_ready",
        "on_guild_join",
        "on_invite_create",
        "on_invite_delete",
    }
    assert eventi_attesi <= set(bot.extra_events.keys())
