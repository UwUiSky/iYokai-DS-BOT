"""
cogs/utility/command_search.py
==================================
/-cerca-comando: interroga l'albero comandi VERO del bot (bot.tree, non un
elenco statico che rischierebbe di disallinearsi) per trovare il
comando più pertinente a una descrizione in linguaggio naturale.
Nessun risultato → propone di aprire una richiesta verso lo
sviluppatore, riusando il modal GIÀ ESISTENTE di
cogs/utility/custom_command_requests.py — non uno nuovo.

Nessun gate is_module_active_for_guild: come /utility richiedi-comando,
è uno strumento di scoperta rivolto a chiunque usi il bot, non una
feature che un admin di server attiva o disattiva per i propri membri.
"""

# Issue #147: pannello senza testo (ultimo comando + categorie), ricerca con
# completamento, menzioni cliccabili, `-chiedi` con lo stesso pannello.
# Ultimo comando: scritto dall'evento `app_command_completion` (tabella command_usage).
# La wiki generata (scripts/genera_wiki.py) e l'AI non sono qui.

from __future__ import annotations

import logging
import os

import discord
from discord import app_commands
from discord.ext import commands

from cogs.utility._command_search_views import DatiPannello, PannelloView, RisultatiView
from core import command_search_logic as logica
from core.command_access import puo_usare
from core.command_groups import GRUPPI, NOME_CERCA_COMANDO, NOME_CHIEDI
from core.config import config
from core.repositories.command_usage_repo import command_usage_repo
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.command_search")

CATEGORIA_BASE = "generali"  # i comandi di primo livello che non stanno in un gruppo


class _NoResultsView(BaseView):
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
        self.cache_ids = logica.CacheIdComandi()
        self.cache_ids_main = logica.CacheIdComandi()
        self.repo = command_usage_repo

    async def cog_load(self) -> None:
        """Pulizia iniziale dei dati vecchi; se il database non c'è ancora, niente di grave."""
        try:
            await command_usage_repo.pulisci(command_usage_repo.giorni, command_usage_repo.tetto)
        except Exception:
            logger.info("Pulizia di command_usage rimandata.")

    def invalida_id(self) -> None:
        """Da chiamare dopo una sync dei comandi: le menzioni ricaricano gli ID."""
        self.cache_ids.invalida()
        self.cache_ids_main.invalida()

    # ------------------------------------------------------------------
    # Dati
    # ------------------------------------------------------------------
    async def _ids(self, interaction: discord.Interaction, serve=()) -> dict[str, int]:
        """ID dei comandi da Discord (`fetch_commands`). Nel server dell'owner contano anche i comandi del server."""
        guild = interaction.guild
        if guild is not None and guild.id == config.MAIN_GUILD_ID:
            async def fetch():
                globali = await self.bot.tree.fetch_commands()
                del_server = await self.bot.tree.fetch_commands(guild=discord.Object(id=guild.id))
                return [*globali, *del_server]  # quelli del server vincono

            return await self.cache_ids_main.ottieni(fetch, serve)
        return await self.cache_ids.ottieni(self.bot.tree.fetch_commands, serve)

    async def _comandi_accessibili(self, interaction: discord.Interaction) -> list[logica.ComandoInfo]:
        radici = self.bot.tree.get_commands()
        gruppi_albero = {c.name for c in radici if isinstance(c, app_commands.Group)}
        tutti = logica.raccogli_comandi(radici)
        gruppi = sorted({c.gruppo for c in tutti if c.gruppo in gruppi_albero})

        async def puo(livello):
            return await puo_usare(interaction, livello)

        visibili = set(
            await logica.gruppi_accessibili(
                gruppi, lambda n: getattr(GRUPPI.get(n), "livello", None), puo
            )
        )
        return [c for c in tutti if c.gruppo not in gruppi_albero or c.gruppo in visibili]

    def _categorie(self, comandi: list[logica.ComandoInfo]) -> tuple[list[str], dict[str, list[logica.ComandoInfo]]]:
        gruppi_albero = {c.name for c in self.bot.tree.get_commands() if isinstance(c, app_commands.Group)}
        per_categoria: dict[str, list[logica.ComandoInfo]] = {}
        for c in comandi:
            nome = c.gruppo if c.gruppo in gruppi_albero else CATEGORIA_BASE
            per_categoria.setdefault(nome, []).append(c)
        ordine = [n for n in GRUPPI if n in per_categoria] + sorted(
            n for n in per_categoria if n not in GRUPPI and n != CATEGORIA_BASE
        )
        if CATEGORIA_BASE in per_categoria:
            ordine.append(CATEGORIA_BASE)
        return ordine, per_categoria

    async def _mostra_pannello(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild.id if interaction.guild is not None else None
        comandi = await self._comandi_accessibili(interaction)
        categorie, per_categoria = self._categorie(comandi)
        try:
            ultimo = await self.repo.ultimo(guild_id, interaction.user.id)
        except Exception:
            logger.warning("Ultimo comando non letto.", exc_info=True)
            ultimo = None
        ids = await self._ids(interaction, serve={c.gruppo for c in comandi} | ({ultimo.split(" ")[0]} if ultimo else set()))
        dati = DatiPannello(
            categorie=categorie,
            comandi=per_categoria,
            ids=ids,
            ultimo=ultimo,
            in_dm=interaction.guild is None,
            wiki_base=os.getenv("WIKI_BASE_URL", ""),
        )
        view = PannelloView(dati)
        await interaction.response.send_message(embed=view.embed, view=view, ephemeral=True)

    # ------------------------------------------------------------------
    # Comandi
    # ------------------------------------------------------------------
    # Comando di PRIMO livello (non in /utility); usabile anche in DM (D24, 11/10/2026).
    @app_commands.command(name=NOME_CERCA_COMANDO, description="Cerca un comando per descrizione.")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(query="Descrivi cosa vuoi fare, es. 'bannare qualcuno' (vuoto: pannello)")
    async def search(
        self,
        interaction: discord.Interaction,
        # Il testo viene ricopiato nella risposta: va tenuto corto.
        query: app_commands.Range[str, 1, 100] | None = None,
    ) -> None:
        if not query:
            await self._mostra_pannello(interaction)
            return

        in_dm = getattr(interaction, "guild", None) is None
        comandi = await self._comandi_accessibili(interaction)
        risultati = logica.cerca(query, comandi)

        if risultati:
            ids = await self._ids(interaction, serve={r.gruppo for r in risultati})
            embed = logica.embed_risultati(risultati, ids, query)
            if in_dm:
                embed.set_footer(text="In privato puoi solo cercare: i comandi si usano nei server.")
            view = RisultatiView(os.getenv("WIKI_BASE_URL", ""), risultati[0].percorso)
            if not view.children:
                view = None
            kwargs = {"view": view} if view is not None else {}
            await interaction.response.send_message(embed=embed, ephemeral=True, **kwargs)
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

    @search.autocomplete("query")
    async def autocompleta_query(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        comandi = await self._comandi_accessibili(interaction)
        return [
            app_commands.Choice(name=nome, value=valore)
            for nome, valore in logica.suggerimenti(current, comandi)
        ]

    # `-chiedi` (primo livello): per ora mostra lo stesso pannello; la risposta AI arriva in F12.
    @app_commands.command(name=NOME_CHIEDI, description="Chiedi aiuto: ti mostro i comandi giusti.")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(domanda="Cosa vuoi fare? (vuoto: pannello dei comandi)")
    async def chiedi(
        self,
        interaction: discord.Interaction,
        domanda: app_commands.Range[str, 1, 500] | None = None,
    ) -> None:
        if domanda:
            # Fino all'AI (F12) la domanda si tratta come una ricerca; max 100 caratteri.
            await self.search.callback(self, interaction, domanda[:100])
            return
        await self._mostra_pannello(interaction)

    # ------------------------------------------------------------------
    # Ultimo comando usato
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command) -> None:
        if not isinstance(command, app_commands.Command):
            return  # menu contestuali: non sono comandi da cercare
        percorso = command.qualified_name
        if percorso in (NOME_CERCA_COMANDO, NOME_CHIEDI):
            return
        try:
            guild = interaction.guild
            await self.repo.registra(guild.id if guild is not None else None, interaction.user.id, percorso)
        except Exception:
            logger.warning("Ultimo comando non salvato.", exc_info=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CommandSearchCog(bot))
