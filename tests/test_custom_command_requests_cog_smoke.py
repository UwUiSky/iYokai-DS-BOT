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

        from core.command_groups import GRUPPI

        utility = {c.name for c in GRUPPI["utility"].commands}
        assert "richiedi-comando" in utility
        system = GRUPPI["owner"].get_command("system")
        assert system is not None and system.get_command("richieste-canale") is not None
        # i vecchi comandi di primo livello non esistono più
        nomi_top = {c.name for c in bot.tree.get_commands()}
        assert not {"request-custom-command", "custom-command-requests-setup"} & nomi_top
    finally:
        await db.close()
