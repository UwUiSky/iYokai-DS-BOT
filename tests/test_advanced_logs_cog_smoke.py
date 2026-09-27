"""
tests/test_advanced_logs_cog_smoke.py
==========================================
Smoke test del cog Logging Avanzato — stesso schema di
tests/test_logging_cog_smoke.py: il controllo che conta è che OGNI
listener risulti davvero registrato in bot.extra_events (il
decorator @commands.Cog.listener() è facile da dimenticare su un
metodo on_xxx senza che nulla lo segnali leggendo il codice).
"""

import discord
from discord.ext import commands

from core.premium import registry
from cogs.logging.advanced_logs import MODULE_LOGGING_ADVANCED, setup as advanced_logs_setup


async def test_advanced_logs_cog_si_carica_e_tutti_i_listener_sono_registrati():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await advanced_logs_setup(bot)

    assert bot.get_cog("AdvancedLogsCog") is not None

    module = registry.get(MODULE_LOGGING_ADVANCED)
    assert module is not None
    assert module.premium_capable is True

    eventi_attesi = {
        "on_guild_role_update",
        "on_guild_channel_create",
        "on_guild_channel_delete",
        "on_guild_channel_update",
        "on_invite_create",
        "on_invite_delete",
        "on_member_join",
        "on_voice_state_update",
        "on_webhooks_update",
        "on_guild_emojis_update",
        "on_guild_stickers_update",
        "on_thread_create",
        "on_thread_delete",
        "on_thread_update",
        "on_guild_update",
    }
    assert eventi_attesi <= set(bot.extra_events.keys()), (
        "Uno o più listener non risultano registrati in bot.extra_events: "
        "probabilmente manca il decorator @commands.Cog.listener() su "
        "uno dei metodi on_xxx del cog."
    )
