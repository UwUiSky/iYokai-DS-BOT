"""
cogs/utility/command_search.py
==================================
-cerca-comando e -chiedi (issue #147), comandi di primo livello usabili anche in DM e
installabili dall'utente (NF-36, #107): dove il bot non c'è valgono come in DM.

- Senza testo: pannello effimero con l'ultimo comando usato (tabella `command_usage`,
  scritta dall'evento `app_command_completion`) e i bottoni delle categorie, filtrate
  con i livelli dei gruppi e dei `@richiedi` di ogni comando, a pagine.
- Con testo: completamento (max 25) e risultati con descrizione e opzioni, interrogando
  l'albero VERO del bot (`bot.tree`), con menzioni cliccabili `</gruppo comando:ID>`
  (ID da `fetch_commands`: cache che si ricarica per scadenza o quando manca un ID).
- Nessun risultato: propone di aprire una richiesta allo sviluppatore, riusando il modal
  di cogs/utility/custom_command_requests.py.
- -chiedi: con l'AI accesa nel server risponde l'assistente (cogs/ai/helpdesk.py) con al
  massimo 3 comandi cliccabili; senza AI, o se l'AI non risponde, la ricerca per parole.
- Bottone "Apri nella wiki" se WIKI_BASE_URL è impostato.

Nessun gate is_module_active_for_guild: è uno strumento di scoperta rivolto a chiunque.
"""


from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from cogs.utility._command_search_views import DatiPannello, PannelloView, RisultatiView
from core import command_search_logic as logica
from core.i18n import testo_per
from core.command_access import Livello, puo_usare
from core.command_groups import GRUPPI, NOME_CERCA_COMANDO, NOME_CHIEDI
from core.config import config
from core.database import db
from core.i18n import lingua_interazione, t
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
                await testo_per(interaction, "cerca_richieste_non_disponibili"), ephemeral=True
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

    # ------------------------------------------------------------------
    # Dati
    # ------------------------------------------------------------------
    async def _ids(self, interaction: discord.Interaction, serve=()) -> dict[str, int]:
        """ID dei comandi da Discord (`fetch_commands`). Nel server dell'owner contano anche i comandi del server."""
        guild_id = _server_del_bot(interaction)
        if guild_id is not None and guild_id == config.MAIN_GUILD_ID:
            async def fetch():
                globali = await self.bot.tree.fetch_commands()
                del_server = await self.bot.tree.fetch_commands(guild=discord.Object(id=guild_id))
                return [*globali, *del_server]  # quelli del server vincono

            return await self.cache_ids_main.ottieni(fetch, serve)
        return await self.cache_ids.ottieni(self.bot.tree.fetch_commands, serve)

    async def _comandi_accessibili(self, interaction: discord.Interaction) -> list[logica.ComandoInfo]:
        """I comandi che l'utente può usare: livello dei gruppi e `@richiedi` di ogni comando (albero vero)."""

        guild_id = _server_del_bot(interaction)
        fuori_dal_bot = guild_id is None and interaction.guild_id is not None

        async def puo(livello):
            # App installata sull'utente in un server senza il bot: là i permessi dello staff non
            # valgono (come in DM); conta solo l'owner del bot.
            if fuori_dal_bot and livello is not Livello.OWNER:
                return False
            return await puo_usare(interaction, livello)

        visibili = await logica.filtra_per_livelli(logica.raccogli_comandi(self.bot.tree.get_commands()), puo)
        if guild_id is None:
            return visibili

        async def attivo(modulo: str) -> bool:
            return await db.is_module_active_for_guild(guild_id, modulo)

        try:
            # NF-06 (21.5): un comando il cui modulo è spento nel server non si propone.
            return await logica.filtra_per_moduli(visibili, attivo)
        except Exception:
            logger.warning("Moduli del server non letti: mostro tutti i comandi.", exc_info=True)
            return visibili

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
        guild_id = _server_del_bot(interaction)
        comandi = await self._comandi_accessibili(interaction)
        categorie, per_categoria = self._categorie(comandi)
        lingua = await lingua_interazione(interaction)
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
            wiki_base=config.WIKI_BASE_URL,
            lingua=lingua,
        )
        view = PannelloView(dati)
        await interaction.followup.send(embed=view.embed, view=view, ephemeral=True)

    async def _ricerca(
        self, interaction: discord.Interaction, query: str, nota: str | None = None, *, gia_differita: bool = False
    ) -> None:
        lingua = await lingua_interazione(interaction)
        if not query.strip():
            await interaction.response.send_message(t("cerca_serve_testo", lingua), ephemeral=True)
            return
        query = query.strip()
        if not gia_differita:
            await interaction.response.defer(ephemeral=True)
        in_dm = _server_del_bot(interaction) is None
        comandi = await self._comandi_accessibili(interaction)
        risultati = logica.cerca(query, comandi)

        if risultati:
            ids = await self._ids(interaction, serve={r.gruppo for r in risultati})
            embed = logica.embed_risultati(risultati, ids, query, lingua)
            if in_dm:
                embed.set_footer(text=t("cerca_in_dm", lingua))
            extra = {}
            view = RisultatiView(config.WIKI_BASE_URL, risultati[0].percorso)
            if view.children:
                extra["view"] = view
            if nota:
                extra["content"] = nota
            await interaction.followup.send(embed=embed, ephemeral=True, **extra)
            return

        embed = discord.Embed(
            title=t("cerca_nulla_titolo", lingua),
            description=t("cerca_nulla_testo", lingua, query=query),
            color=discord.Color.orange(),
        )
        extra = {"content": nota} if nota else {}
        await interaction.followup.send(embed=embed, view=_NoResultsView(self.bot), ephemeral=True, **extra)

    # ------------------------------------------------------------------
    # Comandi
    # ------------------------------------------------------------------
    # Comando di PRIMO livello (non in /utility); usabile anche in DM (D24, 11/10/2026) e installabile
    # dall'utente (NF-36): nei server senza il bot vale come un DM.
    @app_commands.command(name=NOME_CERCA_COMANDO, description="Cerca un comando per descrizione.")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
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
            for nome, valore in logica.suggerimenti(current, comandi, lingua=await lingua_interazione(interaction))
        ]

    # `-chiedi` (primo livello): senza testo il pannello; con testo l'assistente AI o la ricerca.
    @app_commands.command(name=NOME_CHIEDI, description="Chiedi aiuto: ti mostro i comandi giusti.")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
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
        esito_ai = await self._risposta_ai(interaction, pulita)
        if esito_ai is True:
            return
        nota = None
        if len(pulita) > 100:
            # Senza AI la domanda si tratta come una ricerca da 100 caratteri al massimo.
            nota = t("cerca_domanda_lunga", await lingua_interazione(interaction))
            pulita = pulita[:100]
        if esito_ai is False:
            await self._ricerca(interaction, pulita, nota, gia_differita=True)
        else:
            await self._ricerca(interaction, pulita, nota)

    async def _risposta_ai(self, interaction: discord.Interaction, domanda: str) -> bool | None:
        """
        Risposta dell'AI (§25.5). True: risposta mandata. False: risposta già differita ma l'AI
        non ha risposto. None: AI non disponibile, niente toccato. Negli ultimi due casi si
        torna alla ricerca per parole.
        """
        from cogs.ai.helpdesk import risposta_ai_chiedi
        from core.ai_servizio import AINonDisponibile, servizio_ai

        try:
            await servizio_ai().controlla_accesso(_server_del_bot(interaction), interaction.channel_id)
        except AINonDisponibile:
            return None
        except Exception:
            logger.warning("Accesso all'AI non controllato.", exc_info=True)
            return None
        await interaction.response.defer(ephemeral=True)
        comandi = await self._comandi_accessibili(interaction)
        testo, citati, _locale = await risposta_ai_chiedi(
            interaction, domanda, comandi, guild_id=_server_del_bot(interaction)
        )
        if testo is None:
            return False  # già differita: la ricerca per parole risponde con followup
        ids = await self._ids(interaction, serve={c.gruppo for c in citati})
        testo = logica.menziona_percorsi(testo, [c.percorso for c in citati], ids)
        embed = discord.Embed(title="Assistente", description=testo[:4000], color=discord.Color.blurple())
        embed.set_footer(text="Risposta dell'AI: controlla prima di usarla")
        view = RisultatiView(config.WIKI_BASE_URL, citati[0].percorso) if citati else None
        extra = {"view": view} if view is not None and view.children else {}
        await interaction.followup.send(embed=embed, ephemeral=True, **extra)
        return True

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
            await self.repo.registra(_server_del_bot(interaction), interaction.user.id, percorso)
        except Exception:
            logger.warning("Ultimo comando non salvato.", exc_info=True)


def _server_del_bot(interaction: discord.Interaction) -> int | None:
    """
    Il server dove il bot è installato, o None. Con l'app installata solo sull'utente (NF-36) in un
    server senza il bot `guild_id` c'è, ma l'interazione non è autorizzata dal server: vale come un DM
    (niente moduli, niente staff). Un server installato ma non in cache resta un server (#147).
    """
    if interaction.guild_id is None or not interaction.is_guild_integration():
        return None
    return interaction.guild_id


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CommandSearchCog(bot))
