"""
tests/test_command_search_cog_smoke.py
==========================================
Smoke test del cog /cerca-comando (comando di primo livello, col trattino davanti).
"""

import discord
from discord.ext import commands

from discord import app_commands

from cogs.utility.command_search import setup as command_search_setup
from core.command_groups import NOME_HELP
from tests.support.percorsi import percorsi_del_gruppo


async def test_command_search_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await command_search_setup(bot)

    assert bot.get_cog("CommandSearchCog") is not None

    nomi_comandi = {c.name for c in bot.tree.get_commands()}
    assert NOME_HELP == "help"
    assert NOME_HELP in nomi_comandi  # primo livello, non in /utility
    assert "search" not in nomi_comandi and "chiedi" not in nomi_comandi and "cerca-comando" not in nomi_comandi
    assert "help" not in percorsi_del_gruppo("utility")
    comando = bot.tree.get_command(NOME_HELP)
    assert not isinstance(comando, app_commands.Group)


async def test_help_funziona_anche_in_dm():
    """D24: `/help` (ex `cerca-comando` e `chiedi`) è usabile anche in DM (richiesta owner 11/10)."""
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await command_search_setup(bot)

    comando = bot.tree.get_command(NOME_HELP)
    assert comando.guild_only is False
    assert sorted(comando.to_dict(bot.tree)["contexts"]) == [0, 1, 2]


def test_il_nome_del_comando_di_primo_livello_sta_in_command_groups():
    from tests.test_command_tree_invariants import REGEX_NOME

    assert NOME_HELP == "help"
    assert REGEX_NOME.match(NOME_HELP) and NOME_HELP == NOME_HELP.lower() and len(NOME_HELP) <= 32


async def test_help_dichiara_la_lunghezza_massima_del_testo():
    """
    LIM-23: il testo scritto viene ricopiato nella risposta "Nessun comando trovato" (ridotto a 100 caratteri
    senza AI). Con un massimo di 500 caratteri la richiesta resta sotto il limite dell'embed.
    """
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await command_search_setup(bot)

    opzioni = {o["name"]: o for o in bot.tree.get_command(NOME_HELP).to_dict(bot.tree)["options"]}

    assert opzioni["domanda"]["min_length"] == 1
    assert not opzioni["domanda"].get("required")  # senza testo: pannello
    assert opzioni["domanda"]["max_length"] == 500
    assert opzioni["domanda"]["autocomplete"] is True
