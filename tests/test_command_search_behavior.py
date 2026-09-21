"""
tests/test_command_search_behavior.py
=========================================
Test del comportamento REALE di /search — non solo che il cog carica.
Usa un bot con i comandi reali del progetto caricati (poll, ban, ecc.)
per verificare che la ricerca trovi davvero qualcosa di sensato, non
solo che la funzione non sollevi.
"""

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from cogs.utility.command_search import CommandSearchCog, _NoResultsView


class _FakeResponse:
    def __init__(self) -> None:
        self.sent_embeds: list = []
        self.sent_views: list = []
        self.edited_embeds: list = []
        self.sent_modals: list = []

    async def send_message(self, embed=None, view=None, ephemeral: bool = False) -> None:
        if embed is not None:
            self.sent_embeds.append(embed)
        if view is not None:
            self.sent_views.append(view)

    async def edit_message(self, embed=None, view=None) -> None:
        self.edited_embeds.append(embed)

    async def send_modal(self, modal) -> None:
        self.sent_modals.append(modal)


class _FakeInteraction:
    def __init__(self) -> None:
        self.response = _FakeResponse()


def _bot_con_comandi_reali() -> commands.Bot:
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

    async def _cb(interaction):
        pass

    bot.tree.add_command(
        app_commands.Command(name="ban", description="Banna permanentemente un membro.", callback=_cb)
    )
    bot.tree.add_command(
        app_commands.Command(name="poll", description="Crea un sondaggio (fino a 5 opzioni).", callback=_cb)
    )
    return bot


@pytest.mark.asyncio
async def test_search_trova_un_comando_reale():
    bot = _bot_con_comandi_reali()
    cog = CommandSearchCog(bot)
    interaction = _FakeInteraction()

    await cog.search.callback(cog, interaction, query="voglio bannare qualcuno")

    assert len(interaction.response.sent_embeds) == 1
    embed = interaction.response.sent_embeds[0]
    assert any("/ban" in campo.name for campo in embed.fields)


@pytest.mark.asyncio
async def test_search_senza_risultati_propone_la_richiesta():
    bot = _bot_con_comandi_reali()
    cog = CommandSearchCog(bot)
    interaction = _FakeInteraction()

    await cog.search.callback(cog, interaction, query="ricetta della carbonara")

    assert len(interaction.response.sent_embeds) == 1
    assert "Nessun comando trovato" in interaction.response.sent_embeds[0].title
    assert len(interaction.response.sent_views) == 1
    assert isinstance(interaction.response.sent_views[0], _NoResultsView)


@pytest.mark.asyncio
async def test_bottone_si_apre_il_modal_esistente_se_il_cog_richieste_e_disponibile():
    from cogs.utility.custom_command_requests import (
        CustomCommandRequestsCog,
        CustomCommandRequestModal,
    )

    bot = _bot_con_comandi_reali()
    await bot.add_cog(CustomCommandRequestsCog(bot))

    view = _NoResultsView(bot)
    interaction = _FakeInteraction()
    apri_button = view.children[0]

    await apri_button.callback(interaction)

    assert len(interaction.response.sent_modals) == 1
    assert isinstance(interaction.response.sent_modals[0], CustomCommandRequestModal)


@pytest.mark.asyncio
async def test_bottone_si_senza_cog_richieste_non_solleva():
    bot = _bot_con_comandi_reali()  # CustomCommandRequestsCog NON caricato

    view = _NoResultsView(bot)
    interaction = _FakeInteraction()
    apri_button = view.children[0]

    await apri_button.callback(interaction)

    assert interaction.response.sent_modals == []


@pytest.mark.asyncio
async def test_bottone_no_annulla_senza_aprire_nulla():
    bot = _bot_con_comandi_reali()
    view = _NoResultsView(bot)
    interaction = _FakeInteraction()
    annulla_button = view.children[1]

    await annulla_button.callback(interaction)

    assert "Va bene" in interaction.response.edited_embeds[0].title
    assert interaction.response.sent_modals == []
