"""
tests/test_command_search_cog_smoke.py
==========================================
Smoke test del cog /search.
"""

import discord
from discord.ext import commands

from cogs.utility.command_search import setup as command_search_setup


async def test_command_search_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await command_search_setup(bot)

    assert bot.get_cog("CommandSearchCog") is not None

    nomi_comandi = {c.name for c in bot.tree.get_commands()}
    assert "search" in nomi_comandi


async def test_search_dichiara_la_lunghezza_massima_del_testo_cercato():
    """
    LIM-23: il testo cercato viene ricopiato nella risposta "Nessun
    comando trovato". Con un massimo di 100 caratteri la descrizione
    dell'embed resta sempre molto sotto il limite di 4096.
    """
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await command_search_setup(bot)

    opzioni = {o["name"]: o for o in bot.tree.get_command("search").to_dict(bot.tree)["options"]}

    assert opzioni["query"]["min_length"] == 1
    assert opzioni["query"]["max_length"] == 100
