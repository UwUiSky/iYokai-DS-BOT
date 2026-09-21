"""
cogs/utility/command_search.py
==================================
/search: interroga l'albero comandi VERO del bot (bot.tree, non un
elenco statico che rischierebbe di disallinearsi) per trovare il
comando più pertinente a una descrizione in linguaggio naturale.
Nessun risultato → propone di aprire una richiesta verso lo
sviluppatore, riusando il modal GIÀ ESISTENTE di
cogs/utility/custom_command_requests.py — non uno nuovo.

Nessun gate is_module_active_for_guild: come /request-custom-command,
è uno strumento di scoperta rivolto a chiunque usi il bot, non una
feature che un admin di server attiva o disattiva per i propri membri.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.command_search_logic import search_commands
from core.command_tree_utils import walk_commands


class _NoResultsView(discord.ui.View):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(timeout=60)
        self.bot = bot

    @discord.ui.button(label="Sì, proponi al developer", style=discord.ButtonStyle.primary)
    async def apri_richiesta(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        from cogs.utility.custom_command_requests import CustomCommandRequestModal

        cog_richieste = self.bot.get_cog("CustomCommandRequestsCog")
        if cog_richieste is None:
            await interaction.response.send_message(
                "Il sistema di richieste non è al momento disponibile.", ephemeral=True
            )
            return

        await interaction.response.send_modal(CustomCommandRequestModal(cog_richieste))

    @discord.ui.button(label="No, grazie", style=discord.ButtonStyle.secondary)
    async def annulla(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        embed = discord.Embed(title="Va bene", color=discord.Color.greyple())
        await interaction.response.edit_message(embed=embed, view=None)


class CommandSearchCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="search", description="Cerca un comando per descrizione.")
    @app_commands.describe(query="Descrivi cosa vuoi fare, es. 'bannare qualcuno'")
    async def search(self, interaction: discord.Interaction, query: str) -> None:
        tutti_comandi = walk_commands(self.bot.tree.get_commands())
        risultati = search_commands(query, tutti_comandi)

        if risultati:
            embed = discord.Embed(
                title="🔍 Risultati della ricerca", color=discord.Color.blurple()
            )
            for nome, descrizione, _punteggio in risultati:
                embed.add_field(name=f"/{nome}", value=descrizione, inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="Nessun comando trovato",
            description=(
                f'Non ho trovato un comando che corrisponda a "{query}". '
                f"Vuoi proporre questa funzione allo sviluppatore?"
            ),
            color=discord.Color.orange(),
        )
        view = _NoResultsView(self.bot)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CommandSearchCog(bot))
