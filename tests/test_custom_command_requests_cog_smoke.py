"""
tests/test_custom_command_requests_cog_smoke.py
====================================================
Smoke test del cog Custom Commands request system. Richiede il
singleton db davvero connesso — setup() interroga list_pending() per
ricostruire le View persistenti esistenti, stesso schema già usato
per role_menus e suggestions.
"""

import discord
from discord.ext import commands

from cogs.utility.custom_command_requests import setup as ccr_setup


async def test_custom_command_requests_cog_si_carica_correttamente(clean_db):
    from core.database import db

    await db.connect()
    try:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        await ccr_setup(bot)

        assert bot.get_cog("CustomCommandRequestsCog") is not None

        nomi_comandi = {c.name for c in bot.tree.get_commands()}
        assert {"request-custom-command", "custom-command-requests-setup"} <= nomi_comandi
    finally:
        await db.close()
