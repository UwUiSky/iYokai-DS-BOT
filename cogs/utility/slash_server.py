"""
cogs/utility/slash_server.py
============================
Comandi e menu del tasto destro di un server che rispondono con un tag (B28): `/admin-automazioni slash pubblica|togli|elenco|menu`.
I comandi stanno nell'albero del server (mai globali); la sync con Discord è una sola per server, solo se qualcosa è cambiato,
al massimo una ogni 5 minuti (le altre vanno in coda nello scheduler) e al massimo 200 creazioni al giorno.
Funzioni coperte: catalogo #128 UTL-045, UTL-046 (D69, D60, B28)
Dipende da: cogs/utility/custom_commands.py (la risposta è quella di `/tag usa`), core/slash_server_logic.py
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core import slash_server_logic as L
from core.config import config
from core.command_access import Livello, autocomplete_protetto
from core.command_groups import CogConGruppi, SOTTOGRUPPI, comando_di_gruppo
from core.custom_command_logic import MAX_ARGOMENTI
from core.database import db
from core.i18n import testo_per
from core.repositories.custom_command_repo import custom_command_repo
from core.repositories.slash_server_repo import slash_server_repo
from core.scheduler import scheduler

logger = logging.getLogger("iyokai.slash_server")

MODULE_CUSTOM_COMMANDS = "custom_commands"
_NESSUNA = discord.AllowedMentions.none()
_AZIONI_MENU = [app_commands.Choice(name=n, value=v) for n, v in (("aggiungi o cambia", "aggiungi"), ("togli", "togli"), ("elenco", "elenco"))]
_TIPI_MENU = [app_commands.Choice(name=n, value=v) for n, v in (("su un utente", "utente"), ("su un messaggio", "messaggio"))]
_TIPO_DISCORD = {"utente": discord.AppCommandType.user, "messaggio": discord.AppCommandType.message}


async def monta_per_avvio(bot: commands.Bot) -> None:
    """Unico punto d'avvio: i comandi dei server entrano nell'albero PRIMA della sync (sennò Discord li perde)."""
    cog = bot.get_cog("SlashServerCog")
    if cog is not None:
        await cog.monta_tutti()


def adesso() -> datetime:
    return datetime.now(timezone.utc)


class SlashServerCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._montati: dict[int, list[tuple[str, discord.AppCommandType]]] = {}
        self._blocchi: dict[int, asyncio.Lock] = {}

    async def cog_load(self) -> None:
        await super().cog_load()
        scheduler.register_handler(L.AZIONE_SYNC, self.handle_sync)

    async def cog_unload(self) -> None:
        for guild_id in list(self._montati):
            self._smonta(guild_id)
        await super().cog_unload()

    # ------------------------------------------------------------ albero del server
    def _smonta(self, guild_id: int) -> None:
        for nome, tipo in self._montati.pop(guild_id, []):
            self.bot.tree.remove_command(nome, guild=discord.Object(id=guild_id), type=tipo)

    def _aggiungi(self, voce, guild: discord.Object, nome: str) -> bool:
        """Aggiunge una voce all'albero del server; una collisione si salta e si scrive nel log."""
        try:
            self.bot.tree.add_command(voce, guild=guild)
        except (app_commands.CommandAlreadyRegistered, ValueError, TypeError):
            logger.warning("Comando del server %s «%s» non montato: nome già usato.", guild.id, nome, exc_info=True)
            return False
        return True

    async def _monta(self, guild_id: int) -> None:
        """Mette nell'albero del server i comandi e i menu del database (e toglie quelli di prima). Non parla con Discord."""
        self._smonta(guild_id)
        guild, montati = discord.Object(id=guild_id), []
        gruppi: dict[str, app_commands.Group] = {}
        for r in await slash_server_repo.comandi(guild_id):
            comando = self._comando(r["nome"], r["sotto"], r["descrizione"], guild_id)
            if r["sotto"]:
                gruppo = gruppi.get(r["nome"])
                if gruppo is None:
                    nuovo = app_commands.Group(name=r["nome"], description="Comandi di questo server", guild_only=True)
                    if not self._aggiungi(nuovo, guild, r["nome"]):
                        continue
                    gruppo = gruppi[r["nome"]] = nuovo
                    montati.append((r["nome"], discord.AppCommandType.chat_input))
                gruppo.add_command(comando)
            elif self._aggiungi(comando, guild, r["nome"]):
                montati.append((r["nome"], discord.AppCommandType.chat_input))
        for r in await slash_server_repo.menu(guild_id):
            if self._aggiungi(self._menu(r["nome"], r["tipo"], guild_id), guild, r["nome"]):
                montati.append((r["nome"], _TIPO_DISCORD[r["tipo"]]))
        self._montati[guild_id] = montati

    async def monta_tutti(self) -> None:
        """Rimette nell'albero i comandi di tutti i server (senza sync). Da chiamare prima di ogni `tree.sync(guild=...)`."""
        for guild_id in await slash_server_repo.server_con_voci():
            try:
                await self._monta(guild_id)
            except Exception:
                logger.warning("Comandi del server %s non montati.", guild_id, exc_info=True)

    def _comando(self, nome: str, sotto: str, descrizione: str, guild_id: int) -> app_commands.Command:
        async def callback(interaction: discord.Interaction, argomenti: app_commands.Range[str, 0, MAX_ARGOMENTI] = "") -> None:
            await self._rispondi(interaction, nome, sotto, argomenti, None)

        app_commands.describe(argomenti="Testo da passare al comando (facoltativo)")(callback)
        return app_commands.Command(name=sotto or nome, description=descrizione[:L.MAX_DESCRIZIONE], callback=callback)

    def _menu(self, nome: str, tipo: str, guild_id: int) -> app_commands.ContextMenu:
        if tipo == "utente":
            async def sull_utente(interaction: discord.Interaction, utente: discord.Member) -> None:
                await self._rispondi_menu(interaction, nome, tipo, "", utente)

            return app_commands.ContextMenu(name=nome, callback=sull_utente, type=discord.AppCommandType.user)

        async def sul_messaggio(interaction: discord.Interaction, messaggio: discord.Message) -> None:
            autore = messaggio.author if isinstance(messaggio.author, discord.Member) else None
            await self._rispondi_menu(interaction, nome, tipo, (messaggio.content or "")[:MAX_ARGOMENTI], autore)

        return app_commands.ContextMenu(name=nome, callback=sul_messaggio, type=discord.AppCommandType.message)

    # ------------------------------------------------------------ risposta
    async def _rispondi(self, interaction: discord.Interaction, nome: str, sotto: str, argomenti: str, bersaglio) -> None:
        riga = await slash_server_repo.comando(interaction.guild.id, nome, sotto) if interaction.guild else None
        await self._con_il_tag(interaction, riga["tag"] if riga else None, argomenti, bersaglio)

    async def _rispondi_menu(self, interaction: discord.Interaction, nome: str, tipo: str, argomenti: str, bersaglio) -> None:
        riga = await slash_server_repo.una_voce_di_menu(interaction.guild.id, nome, tipo) if interaction.guild else None
        await self._con_il_tag(interaction, riga["tag"] if riga else None, argomenti, bersaglio)

    async def _con_il_tag(self, interaction: discord.Interaction, tag: str | None, argomenti: str, bersaglio) -> None:
        tag_cog = self.bot.get_cog("CustomCommandsCog")
        if tag is None or tag_cog is None:
            await interaction.response.send_message(await testo_per(interaction, "slash_sparito"), ephemeral=True)
            return
        # la risposta, i permessi, la pausa e gli script sono quelli di /tag usa
        await tag_cog.tag.callback(tag_cog, interaction, tag, argomenti, bersaglio)

    # ------------------------------------------------------------ sync con Discord
    def _blocco(self, guild_id: int) -> asyncio.Lock:
        return self._blocchi.setdefault(guild_id, asyncio.Lock())

    async def sincronizza(self, guild_id: int) -> tuple[str, int]:
        """("fatto"|"uguale"|"attesa"|"limite"|"errore", secondi da aspettare). Una sync per volta per server."""
        async with self._blocco(guild_id):
            comandi = [(r["nome"], r["sotto"], r["descrizione"]) for r in await slash_server_repo.comandi(guild_id)]
            menu = [(r["nome"], r["tipo"]) for r in await slash_server_repo.menu(guild_id)]
            impronta, ora = L.impronta(comandi, menu), adesso()
            stato = await slash_server_repo.stato(guild_id)
            if stato is not None and stato["impronta"] == impronta:
                return "uguale", 0
            nomi = L.nomi_di_discord(comandi, menu)
            nuove = L.creazioni_nuove(json.loads(stato["nomi"]) if stato else [], nomi)
            usate = L.creazioni_di_oggi(stato["giorno"], stato["creazioni"], ora.date()) if stato else 0
            if usate + nuove > L.MAX_CREAZIONI_GIORNO:
                return "limite", 0
            attesa = L.attesa_sync(stato["ultimo_sync"] if stato else None, ora)
            if attesa > 0:
                await self._metti_in_coda(guild_id, stato, ora + timedelta(seconds=attesa))
                return "attesa", attesa
            await self._monta(guild_id)
            try:
                await self.bot.tree.sync(guild=discord.Object(id=guild_id))
            except discord.HTTPException:
                logger.warning("Sync dei comandi del server %s non riuscita.", guild_id, exc_info=True)
                await self._metti_in_coda(guild_id, stato, ora + timedelta(seconds=L.INTERVALLO_SYNC))
                return "errore", 0
            await slash_server_repo.salva_sync(guild_id, ora, impronta, nomi, ora.date(), usate + nuove)
            return "fatto", 0

    async def dopo_tag_eliminato(self, guild_id: int) -> None:
        """Il tag non c'è più: l'albero si rimonta senza i suoi comandi e la sync segue la regola dei 5 minuti."""
        await self._monta(guild_id)
        await self.sincronizza(guild_id)

    async def _metti_in_coda(self, guild_id: int, stato, quando: datetime) -> None:
        """Una sola sync in coda per server: i cambi in più finiscono tutti nella stessa."""
        if stato is not None and stato["in_coda"]:
            return
        await slash_server_repo.segna_in_coda(guild_id, True)
        await scheduler.schedule(guild_id, 0, L.AZIONE_SYNC, quando, {"guild_id": guild_id})

    async def handle_sync(self, guild_id: int, user_id: int, payload: dict) -> None:
        """Giro dello scheduler: la sync rimandata."""
        await slash_server_repo.segna_in_coda(guild_id, False)
        await self._monta(guild_id)
        await self.sincronizza(guild_id)

    # ------------------------------------------------------------ comandi
    async def _pronto(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_CUSTOM_COMMANDS):
            await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
            return False
        return True

    def _globali(self) -> set[str]:
        """Nomi che il server non può usare: globali, /owner e ogni comando di server che non è nostro."""
        nomi = {c.name for c in self.bot.tree.get_commands()} | set(L.NOMI_RISERVATI)
        main = getattr(config, "MAIN_GUILD_ID", None)
        if main:
            nostri = {n for n, _ in self._montati.get(main, [])}
            nomi |= {c.name for c in self.bot.tree.get_commands(guild=discord.Object(id=main)) if c.name not in nostri}
        return nomi

    async def _dire(self, interaction: discord.Interaction, chiave: str, **valori) -> None:
        await interaction.response.send_message(await testo_per(interaction, chiave, **valori), ephemeral=True, allowed_mentions=_NESSUNA)

    async def _cambiato(self, interaction: discord.Interaction, chiave_ok: str, **valori) -> None:
        """Dopo un cambio: l'albero si aggiorna subito, Discord quando la regola dei 5 minuti lo permette."""
        await interaction.response.defer(ephemeral=True)
        await self._monta(interaction.guild.id)
        esito, secondi = await self.sincronizza(interaction.guild.id)
        chiave = {"fatto": chiave_ok, "uguale": chiave_ok, "attesa": "slash_in_coda", "limite": "slash_limite_giorno", "errore": "slash_errore_sync"}[esito]
        await interaction.followup.send(await testo_per(interaction, chiave, secondi=secondi, minuti=max(1, round(secondi / 60)), **valori),
                                        ephemeral=True, allowed_mentions=_NESSUNA)

    @autocomplete_protetto(Livello.ADMIN)
    async def _completa_tag(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        nomi = await custom_command_repo.search_names(interaction.guild.id, current.lower(), 25)
        return [app_commands.Choice(name=n, value=n) for n in nomi]

    @autocomplete_protetto(Livello.ADMIN)
    async def _completa_comando(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        nomi = sorted({r["nome"] for r in await slash_server_repo.comandi(interaction.guild.id)})
        return [app_commands.Choice(name=n, value=n) for n in nomi if current.lower() in n][:25]

    @comando_di_gruppo("admin-automazioni", nome="pubblica", descrizione="Crea un comando del server che risponde con un tag.",
                       sottogruppo=SOTTOGRUPPI["admin-automazioni slash"])
    @app_commands.describe(nome="Il nome del comando (minuscole, cifre, - e _)", tag="Il tag che risponde",
                           sotto="Un sotto-comando: il nome diventa un gruppo", descrizione="Cosa fa, come lo vedono gli altri (max 100)")
    @app_commands.autocomplete(tag=_completa_tag, nome=_completa_comando)
    async def pubblica(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, L.MAX_NOME], tag: app_commands.Range[str, 1, L.MAX_NOME],
                       sotto: app_commands.Range[str, 0, L.MAX_NOME] = "", descrizione: app_commands.Range[str, 0, L.MAX_DESCRIZIONE] = "") -> None:
        if not await self._pronto(interaction):
            return
        nome_pulito, sotto_pulito = L.normalizza_nome(nome), (L.normalizza_nome(sotto) if sotto else "")
        errore = "slash_nome_non_valido" if nome_pulito is None or sotto_pulito is None else L.errore_nome_comando(nome_pulito, self._globali())
        if errore is None and await custom_command_repo.get_tag(interaction.guild.id, tag.strip().lower()) is None:
            errore = "slash_tag_manca"
        if errore is not None:
            await self._dire(interaction, errore)
            return
        esito = await slash_server_repo.pubblica(interaction.guild.id, nome_pulito, sotto_pulito, tag.strip().lower(),
                                                 descrizione.strip() or f"Tag {tag.strip().lower()}", interaction.user.id)
        if esito != "ok":
            await self._dire(interaction, {"pieno": "slash_pieno", "troppi": "slash_troppi", "conflitto": "slash_conflitto"}[esito],
                             massimo=L.MAX_COMANDI if esito == "pieno" else L.MAX_SOTTO)
            return
        await self._cambiato(interaction, "slash_pubblicato", nome=(f"{nome_pulito} {sotto_pulito}").strip())

    @comando_di_gruppo("admin-automazioni", nome="togli", descrizione="Toglie un comando del server.", sottogruppo=SOTTOGRUPPI["admin-automazioni slash"])
    @app_commands.describe(nome="Il comando", sotto="Il sotto-comando, se ce l'ha")
    @app_commands.autocomplete(nome=_completa_comando)
    async def togli(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, L.MAX_NOME], sotto: app_commands.Range[str, 0, L.MAX_NOME] = "") -> None:
        if not await self._pronto(interaction):
            return
        fatto = await slash_server_repo.togli(interaction.guild.id, nome.strip().lower(), sotto.strip().lower())
        if not fatto:
            await self._dire(interaction, "slash_non_trovato")
            return
        await self._cambiato(interaction, "slash_tolto")

    @comando_di_gruppo("admin-automazioni", nome="elenco", descrizione="I comandi e i menu del server.", sottogruppo=SOTTOGRUPPI["admin-automazioni slash"])
    async def elenco(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        comandi, menu = await slash_server_repo.comandi(interaction.guild.id), await slash_server_repo.menu(interaction.guild.id)
        if not comandi and not menu:
            await self._dire(interaction, "slash_elenco_vuoto")
            return
        righe = [f"`/{r['nome']}{' ' + r['sotto'] if r['sotto'] else ''}` → **{r['tag']}**" for r in comandi]
        righe += [f"{r['tipo']}: «{r['nome']}» → **{r['tag']}**" for r in menu]
        testo = await testo_per(interaction, "slash_elenco_titolo", n=len(comandi), m=len(menu)) + "\n" + "\n".join(righe)
        await interaction.response.send_message(testo[:2000], ephemeral=True, allowed_mentions=_NESSUNA)

    @comando_di_gruppo("admin-automazioni", nome="menu", descrizione="Voci del menu col tasto destro (su un utente o un messaggio) che rispondono con un tag.",
                       sottogruppo=SOTTOGRUPPI["admin-automazioni slash"])
    @app_commands.describe(azione="Cosa fare", tipo="Dove compare la voce", nome="Il nome della voce (max 32)", tag="Il tag che risponde (per aggiungere)")
    @app_commands.choices(azione=_AZIONI_MENU, tipo=_TIPI_MENU)
    @app_commands.autocomplete(tag=_completa_tag)
    async def menu(self, interaction: discord.Interaction, azione: app_commands.Choice[str], tipo: app_commands.Choice[str],
                   nome: app_commands.Range[str, 1, L.MAX_NOME], tag: app_commands.Range[str, 0, L.MAX_NOME] = "") -> None:
        if not await self._pronto(interaction):
            return
        guild_id, nome = interaction.guild.id, nome.strip()
        if azione.value == "togli":
            if not await slash_server_repo.togli_menu(guild_id, nome, tipo.value):
                await self._dire(interaction, "slash_non_trovato")
                return
            await self._cambiato(interaction, "slash_menu_tolto")
            return
        if azione.value == "elenco":
            voci = [r for r in await slash_server_repo.menu(guild_id) if r["tipo"] == tipo.value]
            await self._dire(interaction, "slash_menu_elenco" if voci else "slash_elenco_vuoto",
                             voci="\n".join(f"«{r['nome']}» → **{r['tag']}**" for r in voci))
            return
        errore = L.errore_nome_menu(nome, self._globali())
        if errore is None and (not tag or await custom_command_repo.get_tag(guild_id, tag.strip().lower()) is None):
            errore = "slash_tag_manca"
        if errore is not None:
            await self._dire(interaction, errore)
            return
        if await slash_server_repo.aggiungi_menu(guild_id, nome, tipo.value, tag.strip().lower(), interaction.user.id) != "ok":
            await self._dire(interaction, "slash_menu_pieno", massimo=L.MAX_MENU)
            return
        await self._cambiato(interaction, "slash_menu_aggiunto")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SlashServerCog(bot))
