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
        guild_id = interaction.guild_id
        if guild_id is not None and guild_id == config.MAIN_GUILD_ID:
            async def fetch():
                globali = await self.bot.tree.fetch_commands()
                del_server = await self.bot.tree.fetch_commands(guild=discord.Object(id=guild_id))
                return [*globali, *del_server]  # quelli del server vincono

            return await self.cache_ids_main.ottieni(fetch, serve)
        return await self.cache_ids.ottieni(self.bot.tree.fetch_commands, serve)

    async def _comandi_accessibili(self, interaction: discord.Interaction) -> list[logica.ComandoInfo]:
        """I comandi che l'utente può usare: livello dei gruppi e `@richiedi` di ogni comando (albero vero)."""

        async def puo(livello):
            return await puo_usare(interaction, livello)

        return await logica.filtra_per_livelli(logica.raccogli_comandi(self.bot.tree.get_commands()), puo)

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
        # Le chiamate a database e a Discord possono superare i 3 secondi: si risponde subito.
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
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
            in_dm=guild_id is None,
            wiki_base=os.getenv("WIKI_BASE_URL", ""),
        )
        view = PannelloView(dati)
        await interaction.followup.send(embed=view.embed, view=view, ephemeral=True)

    async def _ricerca(self, interaction: discord.Interaction, query: str, nota: str | None = None) -> None:
        if not query.strip():
            await interaction.response.send_message(
                "Scrivi almeno una parola per cercare, oppure lascia vuoto per il pannello.", ephemeral=True
            )
            return
        query = query.strip()
        await interaction.response.defer(ephemeral=True)
        in_dm = interaction.guild_id is None
        comandi = await self._comandi_accessibili(interaction)
        risultati = logica.cerca(query, comandi)

        if risultati:
            ids = await self._ids(interaction, serve={r.gruppo for r in risultati})
            embed = logica.embed_risultati(risultati, ids, query)
            if in_dm:
                embed.set_footer(text="In privato puoi solo cercare: i comandi si usano nei server.")
            extra = {}
            view = RisultatiView(os.getenv("WIKI_BASE_URL", ""), risultati[0].percorso)
            if view.children:
                extra["view"] = view
            if nota:
                extra["content"] = nota
            await interaction.followup.send(embed=embed, ephemeral=True, **extra)
            return

        embed = discord.Embed(
            title="Nessun comando trovato",
            description=(
                f'Non ho trovato un comando che corrisponda a "{query}". '
                f"Vuoi proporre questa funzione allo sviluppatore?"
            ),
            color=discord.Color.orange(),
        )
        extra = {"content": nota} if nota else {}
        await interaction.followup.send(embed=embed, view=_NoResultsView(self.bot), ephemeral=True, **extra)

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
        if query is None:
            await self._mostra_pannello(interaction)
            return
        await self._ricerca(interaction, query)

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
        if domanda is None:
            await self._mostra_pannello(interaction)
            return
        pulita = domanda.strip()
        nota = None
        if len(pulita) > 100:
            # Fino all'AI (F12) la domanda si tratta come una ricerca da 100 caratteri al massimo.
            nota = "La domanda era lunga: ho cercato solo con i primi 100 caratteri."
            pulita = pulita[:100]
        await self._ricerca(interaction, pulita, nota)

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
            await self.repo.registra(interaction.guild_id, interaction.user.id, percorso)
        except Exception:
            logger.warning("Ultimo comando non salvato.", exc_info=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CommandSearchCog(bot))
