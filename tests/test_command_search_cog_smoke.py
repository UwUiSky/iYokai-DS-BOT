"""
tests/test_command_search_cog_smoke.py
==========================================
Smoke test del cog /-cerca-comando (comando di primo livello, col trattino davanti).
"""

import discord
from discord.ext import commands

from discord import app_commands

from cogs.utility.command_search import setup as command_search_setup
from core.command_groups import NOME_CERCA_COMANDO, NOME_CHIEDI
from tests.support.percorsi import percorsi_del_gruppo


async def test_command_search_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await command_search_setup(bot)

    assert bot.get_cog("CommandSearchCog") is not None

    nomi_comandi = {c.name for c in bot.tree.get_commands()}
    assert NOME_CERCA_COMANDO == "-cerca-comando"
    assert NOME_CERCA_COMANDO in nomi_comandi  # primo livello, non in /utility
    assert "search" not in nomi_comandi
    assert "cerca-comando" not in percorsi_del_gruppo("utility")
    comando = bot.tree.get_command(NOME_CERCA_COMANDO)
    assert not isinstance(comando, app_commands.Group)


async def test_cerca_comando_funziona_anche_in_dm():
    """D24: `-cerca-comando` è usabile anche in DM (richiesta owner 11/10)."""
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await command_search_setup(bot)

    comando = bot.tree.get_command(NOME_CERCA_COMANDO)
    assert comando.guild_only is False
    assert sorted(comando.to_dict(bot.tree)["contexts"]) == [0, 1, 2]


def test_i_nomi_dei_due_comandi_di_primo_livello_stanno_in_command_groups():
    assert (NOME_CERCA_COMANDO, NOME_CHIEDI) == ("-cerca-comando", "-chiedi")


def test_i_due_nomi_con_il_trattino_sono_validi_per_discord():
    """Il trattino davanti è ammesso dalla regola dei nomi (mappa F7 §6); `/chiedi` arriva con #147."""
    from tests.test_command_tree_invariants import REGEX_NOME

    for nome in (NOME_CERCA_COMANDO, NOME_CHIEDI):
        assert REGEX_NOME.match(nome) and nome == nome.lower() and len(nome) <= 32


async def test_search_dichiara_la_lunghezza_massima_del_testo_cercato():
    """
    LIM-23: il testo cercato viene ricopiato nella risposta "Nessun
    comando trovato". Con un massimo di 100 caratteri la descrizione
    dell'embed resta sempre molto sotto il limite di 4096.
    """
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await command_search_setup(bot)

    opzioni = {o["name"]: o for o in bot.tree.get_command(NOME_CERCA_COMANDO).to_dict(bot.tree)["options"]}

    assert opzioni["query"]["min_length"] == 1
    assert not opzioni["query"].get("required")  # senza testo: pannello
    assert opzioni["query"]["max_length"] == 100
