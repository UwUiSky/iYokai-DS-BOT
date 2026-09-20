"""
tests/test_suggestions_cog_smoke.py
=======================================
Smoke test del cog Suggestion System. Richiede il singleton db
davvero connesso — setup() interroga suggestion_repo.list_pending()
per ricostruire le View persistenti esistenti, esattamente come
avviene in produzione (db.connect() avviene sempre prima del
caricamento dei cog) — stesso schema già usato per role_menus.
"""

import discord
from discord.ext import commands

from core.premium import registry
from cogs.utility.suggestions import (
    MODULE_SUGGESTIONS,
    setup as suggestions_setup,
)


async def test_suggestions_cog_si_carica_correttamente(clean_db):
    from core.database import db

    await db.connect()
    try:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        await suggestions_setup(bot)

        assert bot.get_cog("SuggestionsCog") is not None

        module = registry.get(MODULE_SUGGESTIONS)
        assert module is not None
        assert module.premium_capable is False

        nomi_comandi = {c.name for c in bot.tree.get_commands()}
        assert {"suggestion-setup", "suggest"} <= nomi_comandi
    finally:
        await db.close()
