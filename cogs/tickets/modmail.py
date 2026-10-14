"""
cogs/tickets/modmail.py
=======================
Ticket aperti in DM (ModMail): l'utente scrive in privato al bot e nasce un
canale per lo staff; lo staff risponde con `/ticket rispondi` (anche in forma
anonima) e chiude con `/ticket dm-chiudi`. I messaggi nel canale che NON
passano da `/ticket rispondi` restano interni: l'utente non li vede mai.

- Una sola conversazione aperta per utente in tutti i server (indice unico,
  migrazione 0101): un DM arriva sempre a un canale solo.
- Un utente presente in più server col ModMail acceso sceglie con un menu.
- Il transcript va solo al canale dei log (mai in DM: contiene le note interne).
- Il bot non salva il testo dei messaggi: restano nel canale Discord.
- Il testo degli utenti viene inoltrato senza menzioni attive.

Configurazione per server: tabella `modmail_config` (categoria dove nascono i
canali; non in `guild_config.settings` per non toccare lo schema di /admin
config, che sta in cogs/utility). Il modulo `tickets` deve essere acceso.
Comandi: `/admin ticket dm`, `/admin ticket dm-blocca`, `/ticket rispondi`,
`/ticket dm-chiudi`.
Funzioni coperte: SPEC §23 (NF-33)
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from cogs.logging.basic_logs import SETTING_LOG_CHANNEL
from cogs.moderation._shared import ensure_module_enabled
from cogs.tickets.tickets import (
    ADMIN_TICKET,
    MAX_TRANSCRIPT_FILE_BYTES,
    MODULE_TICKETS,
    RITARDO_ELIMINAZIONE_SECONDI,
    _is_ticket_staff,
    _support_role_ids,
)
from core import channel_router as router
from core import modmail_logic as logica
from core.channel_router import TIPO_EVENTI
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.repositories.blacklist_repo import blacklist_repo
from core.repositories.moderation_repo import moderation_repo
from core.spam_trap_logic import BAN_ACTION_TYPE
from core.repositories.modmail_repo import ConversazioneGiaAperta, ModmailThread, modmail_repo
from core.scheduler import in_seconds, scheduler
from core.ticket_logic import build_transcript_text, format_transcript_line, split_text_by_size
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.modmail")

MODMAIL_DELETE_ACTION_TYPE = "modmail_delete_channel"

SENZA_MENZIONI = discord.AllowedMentions.none()
COLORE_UTENTE = discord.Color.green()
COLORE_STAFF = discord.Color.blurple()


def _autore_riga(m: discord.Message) -> str:
    """Nel canale ModMail chi scrive è sempre il bot: il nome vero sta nell'autore dell'embed."""
    if getattr(m.author, "bot", False) and m.embeds and m.embeds[0].author and m.embeds[0].author.name:
        return str(m.embeds[0].author.name)
    return str(m.author)


class SceltaServerView(BaseView):
    """Menu a tendina nel DM: in quale server vuoi scrivere? Vive 2 minuti, non serve dopo un riavvio."""

    def __init__(self, cog: "ModMailCog", utente: discord.abc.User, messaggio: discord.Message, server: list[discord.Guild]) -> None:
        super().__init__(timeout=120)
        self._cog = cog
        self._utente = utente
        self._messaggio = messaggio
        self._server = {str(g.id): g for g in server}
        select = discord.ui.Select(
            placeholder="Scegli il server...",
            options=[discord.SelectOption(label=g.name[:100], value=str(g.id)) for g in server[: logica.MAX_SERVER_NEL_MENU]],
        )
        select.callback = self._scelto
        self.add_item(select)

    async def on_timeout(self) -> None:
        # Senza questo l'utente resterebbe "in attesa del menu" fino al riavvio del bot.
        self._cog._menu_aperti.discard(self._utente.id)

    async def _scelto(self, interaction: discord.Interaction) -> None:
        guild = self._server.get(interaction.data["values"][0])
        if guild is None or interaction.user.id != self._utente.id:
            await interaction.response.send_message("Scelta non valida.", ephemeral=True)
            return
        self.stop()
        try:
            await interaction.response.edit_message(content=f"Ok: **{guild.name}**. Un attimo...", view=None)
        except discord.HTTPException:
            self._cog._menu_aperti.discard(self._utente.id)
            raise
        await self._cog.apri_da_menu(guild, self._utente, self._messaggio)


class ConfermaInvioView(BaseView):
    """Con un solo server: il primo messaggio parte solo se l'utente lo conferma. Vive 2 minuti."""

    def __init__(self, cog: "ModMailCog", utente: discord.abc.User, messaggio: discord.Message, guild: discord.Guild) -> None:
        super().__init__(timeout=120)
        self._cog = cog
        self._utente = utente
        self._messaggio = messaggio
        self._guild = guild

    async def on_timeout(self) -> None:
        self._cog._menu_aperti.discard(self._utente.id)

    async def _solo_lui(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self._utente.id:
            await interaction.response.send_message("Scelta non valida.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Invia allo staff", style=discord.ButtonStyle.success)
    async def invia(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        if not await self._solo_lui(interaction):
            return
        self.stop()
        try:
            await interaction.response.edit_message(content=f"Ok: invio a **{self._guild.name}**. Un attimo...", view=None)
        except discord.HTTPException:
            self._cog._menu_aperti.discard(self._utente.id)
            raise
        await self._cog.apri_da_menu(self._guild, self._utente, self._messaggio)

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def annulla(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        if not await self._solo_lui(interaction):
            return
        self.stop()
        self._cog._menu_aperti.discard(self._utente.id)
        await interaction.response.edit_message(content="Annullato: il messaggio non è stato inviato.", view=None)


class ModMailCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._limitatore = logica.LimitatoreDM()
        # un DM alla volta per utente: due messaggi insieme si inoltrano in ordine, senza perderne
        self._serrature: dict[int, asyncio.Lock] = {}
        # utenti con un menu dei server ancora aperto (il loro messaggio aspetta la scelta)
        self._menu_aperti: set[int] = set()
        # canali ModMail di cui si sta leggendo la history per il transcript
        self._transcript_in_corso: set[int] = set()

    def _serratura(self, user_id: int) -> asyncio.Lock:
        if len(self._serrature) > 2000:  # memoria limitata: si scartano solo le serrature libere
            self._serrature = {u: s for u, s in self._serrature.items() if s.locked()}
        return self._serrature.setdefault(user_id, asyncio.Lock())

    # ================================================================
    # DM in arrivo
    # ================================================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is not None or message.author.bot:
            return
        if logica.messaggio_vuoto(message.content, len(message.attachments)):
            return
        if not self._limitatore.consenti(message.author.id, time.monotonic()):
            return
        # La serratura FIFO prima dei controlli: i messaggi si inoltrano nell'ordine di arrivo.
        async with self._serratura(message.author.id):
            # Un solo gestore per DM: chi ha un ban dello Spam Trap sta scrivendo un appello e lo
            # gestisce quel cog (risposta e destinazione sue); il ModMail non deve mai vederlo.
            if await self._ha_appello_aperto(message.author.id):
                return
            # Come per ogni altra funzione del bot, un utente in blacklist non apre canali.
            if await blacklist_repo.is_user_blacklisted(message.author.id):
                return
            await self._dm_in_arrivo(message)

    async def _ha_appello_aperto(self, user_id: int) -> bool:
        casi = await moderation_repo.get_active_cases_for_user_across_guilds(user_id, BAN_ACTION_TYPE)
        return any(self.bot.get_guild(c.guild_id) is not None for c in casi)

    async def _server_ok(self, guild: discord.Guild, utente: discord.abc.User) -> bool:
        """Il server accetta ModMail da questo utente adesso (modulo acceso, categoria, nessun blocco)."""
        if guild.get_member(utente.id) is None:
            return False
        if not await db.is_module_active_for_guild(guild.id, MODULE_TICKETS):
            return False
        if await modmail_repo.categoria(guild.id) is None:
            return False
        return not await modmail_repo.bloccato(guild.id, utente.id)

    async def _server_candidati(self, utente: discord.abc.User) -> list[discord.Guild]:
        return [g for g in self.bot.guilds if await self._server_ok(g, utente)]

    async def _dm_in_arrivo(self, message: discord.Message, *, secondo_giro: bool = False) -> None:
        utente = message.author
        thread = await modmail_repo.aperta_dell_utente(utente.id)
        if thread is not None:
            if not await self._inoltra_allo_staff(thread, message) and not secondo_giro:
                # il canale era sparito: la conversazione è chiusa, il messaggio riparte da capo
                await self._dm_in_arrivo(message, secondo_giro=True)
            return
        if utente.id in self._menu_aperti:
            await self._rispondi_dm(message, "Rispondi prima alla domanda qui sopra (scegli o conferma): poi scrivimi di nuovo.")
            return
        candidati = await self._server_candidati(utente)
        decisione = logica.decidi_server([g.id for g in candidati])
        if decisione.esito is logica.Esito.NESSUN_SERVER:
            return
        if decisione.esito is logica.Esito.UN_SERVER:
            # Il primo messaggio va a persone vere solo se l'utente lo vuole: chi scrive al bot può non saperlo.
            guild = candidati[0]
            try:
                await message.channel.send(
                    f"Vuoi inviare questo messaggio allo staff di **{guild.name}**? "
                    "Lo leggeranno persone e ti risponderanno qui.",
                    view=ConfermaInvioView(self, utente, message, guild),
                )
                self._menu_aperti.add(utente.id)
            except discord.HTTPException:
                logger.info("Conferma non consegnata all'utente %s", utente.id)
            return
        scelta = [g for g in candidati if g.id in decisione.guild_ids]
        try:
            await message.channel.send(
                "In quale server vuoi scrivere allo staff?",
                view=SceltaServerView(self, utente, message, scelta),
            )
            self._menu_aperti.add(utente.id)
        except discord.HTTPException:
            logger.info("Menu dei server non consegnato all'utente %s", utente.id)

    async def apri_da_menu(self, guild: discord.Guild, utente: discord.abc.User, primo: discord.Message) -> None:
        """Scelta dal menu: in coda dietro ai DM in corso e con tutti i controlli rifatti."""
        self._menu_aperti.discard(utente.id)
        async with self._serratura(utente.id):
            thread = await modmail_repo.aperta_dell_utente(utente.id)
            if thread is not None:
                await self._inoltra_allo_staff(thread, primo)
                return
            if await self._ha_appello_aperto(utente.id) or await blacklist_repo.is_user_blacklisted(utente.id):
                return
            await self._apri_se_ancora_possibile(guild, utente, primo)

    async def _apri_se_ancora_possibile(self, guild: discord.Guild, utente: discord.abc.User, primo: discord.Message) -> None:
        if not await self._server_ok(guild, utente):
            await self._rispondi_dm(primo, "Questo server non accetta messaggi dal ModMail adesso.")
            return
        await self._apri(guild, utente, primo)

    # ================================================================
    # Apertura e inoltro
    # ================================================================
    async def _apri(self, guild: discord.Guild, utente: discord.abc.User, primo: discord.Message) -> None:
        categoria_id = await modmail_repo.categoria(guild.id)
        categoria = guild.get_channel(categoria_id) if categoria_id else None
        if not isinstance(categoria, discord.CategoryChannel):
            await self._rispondi_dm(primo, "Il ModMail di questo server non è configurato: riprova più tardi.")
            return
        esistente = await modmail_repo.aperta_dell_utente(utente.id)
        if esistente is not None:
            await self._inoltra_allo_staff(esistente, primo)
            return

        sovrascritture = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        for ruolo_id in await _support_role_ids(guild.id):
            ruolo = guild.get_role(ruolo_id)
            if ruolo is not None:
                sovrascritture[ruolo] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True
                )
        try:
            canale = await categoria.create_text_channel(
                name=logica.nome_canale(getattr(utente, "name", ""), utente.id),
                topic=f"ModMail · {utente} · {utente.id}"[:1024],
                overwrites=sovrascritture,
                reason=f"ModMail di {utente}",
            )
        except discord.HTTPException:
            logger.warning("Canale ModMail non creato nel server %s", guild.id)
            await self._rispondi_dm(primo, "Non riesco ad aprire la conversazione adesso: riprova più tardi.")
            return

        try:
            thread = await modmail_repo.crea(guild.id, utente.id, canale.id)
        except ConversazioneGiaAperta:
            try:
                await canale.delete(reason="ModMail doppio")
            except discord.HTTPException:
                logger.warning("Canale ModMail doppio %s non eliminato.", canale.id)
            esistente = await modmail_repo.aperta_dell_utente(utente.id)
            if esistente is not None:
                await self._inoltra_allo_staff(esistente, primo)
            return

        intestazione = discord.Embed(
            title="Nuova conversazione ModMail",
            description=(
                f"{utente.mention} (`{utente.id}`) ha scritto in privato.\n"
                "Rispondi con `/ticket rispondi` (anche anonimo). I messaggi scritti qui restano interni. "
                "Chiudi con `/ticket dm-chiudi`."
            ),
            color=COLORE_STAFF,
        )
        intestazione.add_field(name="Account creato", value=discord.utils.format_dt(utente.created_at, "R"))
        membro = guild.get_member(utente.id)
        if membro is not None and membro.joined_at is not None:
            intestazione.add_field(name="Nel server dal", value=discord.utils.format_dt(membro.joined_at, "R"))
        try:
            await canale.send(embed=intestazione, allowed_mentions=SENZA_MENZIONI)
        except discord.HTTPException:
            logger.warning("Intestazione ModMail non inviata in %s", canale.id)
        await self._inoltra_allo_staff(thread, primo, canale)
        await self._rispondi_dm(
            primo, f"Messaggio ricevuto da **{guild.name}**. Lo staff ti risponderà qui, in privato."
        )

    async def _rispondi_dm(self, messaggio: discord.Message, testo: str) -> None:
        try:
            await messaggio.channel.send(testo)
        except discord.HTTPException:
            logger.info("DM di servizio non consegnato (utente %s)", messaggio.author.id)

    async def _inoltra_allo_staff(self, thread: ModmailThread, message: discord.Message, canale=None) -> bool:
        """True se il messaggio è stato gestito; False se il canale non c'è più (thread chiuso, da riaprire)."""
        canale = canale or self.bot.get_channel(thread.channel_id)
        if canale is None:
            try:
                canale = await self.bot.fetch_channel(thread.channel_id)
            except discord.NotFound:
                await self._canale_sparito(thread)
                return False
        embed = discord.Embed(
            description=logica.testo_inoltrato(message.content) or None,
            color=COLORE_UTENTE,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name=str(message.author)[:256], icon_url=message.author.display_avatar.url)
        if message.attachments:
            embed.add_field(
                name="Allegati",
                value=logica.elenco_allegati([(a.filename, a.url) for a in message.attachments]),
                inline=False,
            )
        try:
            await canale.send(embed=embed, allowed_mentions=SENZA_MENZIONI)
        except discord.NotFound:
            await self._canale_sparito(thread)
            return False
        except discord.HTTPException:
            logger.warning("Inoltro ModMail non riuscito in %s", thread.channel_id)
            await self._rispondi_dm(message, "Non sono riuscito a consegnare il messaggio allo staff: riprova.")
            return True
        try:
            await message.add_reaction("✅")
        except discord.HTTPException:
            pass
        return True

    async def _canale_sparito(self, thread: ModmailThread) -> None:
        """Il canale è stato cancellato a mano: la conversazione si chiude e l'utente può riscrivere."""
        if await modmail_repo.chiudi(thread.channel_id, None, "canale cancellato"):
            logger.info("ModMail %s chiuso: canale cancellato.", thread.channel_id)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if await modmail_repo.chiudi(channel.id, None, "canale cancellato"):
            logger.info("ModMail chiuso perché il canale %s è stato cancellato a mano.", channel.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        thread = await modmail_repo.aperta_dell_utente_nel_server(member.guild.id, member.id)
        if thread is None:
            return
        canale = member.guild.get_channel(thread.channel_id)
        if canale is None:
            await self._canale_sparito(thread)
            return
        await self._chiudi(member.guild, canale, thread, member.guild.me.id, "l'utente ha lasciato il server", avvisa_utente=False)

    # ================================================================
    # Chiusura
    # ================================================================
    async def _transcript_al_log(self, guild: discord.Guild, canale, thread: ModmailThread) -> bool:
        """Solo nel canale dei log: contiene anche le note interne dello staff."""
        try:
            righe = []
            async for m in canale.history(limit=None, oldest_first=True):
                righe.append(
                    format_transcript_line(
                        m.created_at.strftime("%Y-%m-%d %H:%M"),
                        _autore_riga(m),
                        m.content or " / ".join(e.description or "" for e in m.embeds),
                        [a.filename for a in m.attachments],
                    )
                )
            testo = build_transcript_text(
                [f"Transcript ModMail {thread.id}", f"Utente: {thread.user_id}", f"Aperto: {thread.created_at.isoformat()}"],
                righe,
            )
            predefinito = await db.get_guild_setting(guild.id, SETTING_LOG_CHANNEL)
            destinazione = await router.destinazione(guild, TIPO_EVENTI, predefinito)
            if destinazione is None:
                return False
            parti = split_text_by_size(testo, MAX_TRANSCRIPT_FILE_BYTES)
            for numero, parte in enumerate(parti, start=1):
                nome = f"modmail-{thread.id}" + (f"-parte-{numero}" if len(parti) > 1 else "") + ".txt"
                await router.invia_a(
                    destinazione, guild, TIPO_EVENTI,
                    content=f"Transcript ModMail #{thread.id}",
                    file=discord.File(io.BytesIO(parte.encode("utf-8")), filename=nome),
                )
            return True
        except discord.HTTPException:
            logger.warning("Transcript ModMail %s non consegnato.", thread.id)
        except Exception:  # noqa: BLE001 - mai bloccare la chiusura
            logger.exception("Transcript ModMail %s non riuscito", thread.id)
        return False

    async def _chiudi(
        self, guild: discord.Guild, canale, thread: ModmailThread, chiuso_da: int, motivo: str | None, *, avvisa_utente: bool, esito: dict | None = None
    ) -> bool:
        if not await modmail_repo.chiudi(thread.channel_id, chiuso_da, motivo):
            return False
        # Prima l'eliminazione nello scheduler (come i ticket): un riavvio non lascia il canale.
        try:
            await scheduler.schedule(
                guild.id, thread.user_id, MODMAIL_DELETE_ACTION_TYPE, in_seconds(RITARDO_ELIMINAZIONE_SECONDI),
                {"channel_id": thread.channel_id, "reason": "ModMail chiuso"},
            )
        except Exception:
            # Come per i ticket: chiusura e pianificazione sono un passo solo. Chi riprova trova tutto com'era.
            if not await modmail_repo.riapri_dopo_errore(thread.channel_id):
                logger.error("ModMail %s chiuso ma eliminazione non pianificata: canale da togliere a mano.", thread.channel_id)
            raise
        if avvisa_utente:
            try:
                utente = guild.get_member(thread.user_id) or await self.bot.fetch_user(thread.user_id)
                testo = f"La conversazione con **{guild.name}** è stata chiusa."
                if motivo:
                    testo += f"\nMotivo: {logica.taglia(motivo, logica.MAX_MOTIVO_CHIUSURA)}"
                await utente.send(testo)
            except discord.HTTPException:
                logger.info("Avviso di chiusura ModMail non consegnato all'utente %s", thread.user_id)
        self._transcript_in_corso.add(thread.channel_id)
        try:
            consegnato = await self._transcript_al_log(guild, canale, thread)
        finally:
            self._transcript_in_corso.discard(thread.channel_id)
        if esito is not None:
            esito["transcript"] = consegnato
        return True

    async def handle_modmail_delete_channel(self, guild_id: int, user_id: int, payload: dict) -> None:
        """Handler dello scheduler. 404 = già eliminato; gli altri errori escono e lo scheduler riprova."""
        if payload["channel_id"] in self._transcript_in_corso:
            # il transcript sta ancora leggendo la history: si ripassa dopo
            await scheduler.schedule(
                guild_id, user_id, MODMAIL_DELETE_ACTION_TYPE, in_seconds(RITARDO_ELIMINAZIONE_SECONDI), payload
            )
            return
        try:
            canale = self.bot.get_channel(payload["channel_id"]) or await self.bot.fetch_channel(payload["channel_id"])
            await canale.delete(reason=payload.get("reason"))
        except discord.NotFound:
            return
        except discord.Forbidden:
            logger.warning("Permessi mancanti per eliminare il canale ModMail %s", payload["channel_id"])

    # ================================================================
    # Comandi
    # ================================================================
    @comando_di_gruppo(
        "admin",
        nome="dm",
        descrizione="Accendi o spegni il ModMail (ticket in DM).",
        sottogruppo=ADMIN_TICKET,
    )
    @app_commands.describe(
        attivo="Acceso o spento",
        categoria="Categoria dei canali dello staff",
    )
    async def dm(
        self, interaction: discord.Interaction, attivo: bool, categoria: discord.CategoryChannel | None = None
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_TICKETS):
            return
        if attivo:
            if categoria is None:
                await interaction.response.send_message(
                    "Per accendere il ModMail scegli la categoria dei canali dello staff.", ephemeral=True
                )
                return
            await modmail_repo.imposta_categoria(interaction.guild.id, categoria.id, interaction.user.id)
            await interaction.response.send_message(
                f"ModMail acceso: i messaggi privati al bot aprono un canale in **{categoria.name}**. "
                "Lo staff risponde con `/ticket rispondi`.",
                ephemeral=True,
            )
            return
        await modmail_repo.imposta_categoria(interaction.guild.id, None)
        await interaction.response.send_message(
            "ModMail spento. Le conversazioni già aperte restano finché non le chiudi.", ephemeral=True
        )

    @comando_di_gruppo(
        "admin",
        nome="dm-blocca",
        descrizione="Blocca o sblocca un utente dal ModMail.",
        sottogruppo=ADMIN_TICKET,
    )
    @app_commands.describe(utente="L'utente", bloccato="Sì per bloccarlo")
    async def dm_blocca(self, interaction: discord.Interaction, utente: discord.User, bloccato: bool = True) -> None:
        if interaction.guild is None:
            return
        if not bloccato:
            tolto = await modmail_repo.sblocca(interaction.guild.id, utente.id)
            await interaction.response.send_message(
                f"{utente.mention} può usare di nuovo il ModMail." if tolto else f"{utente.mention} non era bloccato.",
                ephemeral=True,
                allowed_mentions=SENZA_MENZIONI,
            )
            return
        await interaction.response.defer(ephemeral=True)
        await modmail_repo.blocca(interaction.guild.id, utente.id, interaction.user.id)
        chiusa = False
        thread = await modmail_repo.aperta_dell_utente_nel_server(interaction.guild.id, utente.id)
        if thread is not None:
            canale = interaction.guild.get_channel(thread.channel_id)
            if canale is not None:
                chiusa = await self._chiudi(
                    interaction.guild, canale, thread, interaction.user.id, "utente bloccato", avvisa_utente=False
                )
            else:
                await self._canale_sparito(thread)
        await interaction.followup.send(
            f"{utente.mention} non può più usare il ModMail." + (" Conversazione aperta chiusa." if chiusa else ""),
            ephemeral=True,
            allowed_mentions=SENZA_MENZIONI,
        )

    async def _thread_per_staff(self, interaction: discord.Interaction) -> ModmailThread | None:
        if not await _is_ticket_staff(interaction):
            await interaction.response.send_message(
                "Solo lo staff (permesso Manage Server o un ruolo di supporto) può usare questo comando.",
                ephemeral=True,
            )
            return None
        thread = await modmail_repo.aperta_del_canale(interaction.channel.id)
        if thread is None:
            await interaction.response.send_message(
                "Questo comando funziona solo dentro un canale ModMail aperto.", ephemeral=True
            )
        return thread

    @comando_di_gruppo("ticket", nome="rispondi", descrizione="Rispondi all'utente di questa conversazione ModMail.")
    @app_commands.describe(
        testo="La risposta (l'utente la riceve in privato)",
        anonimo="Sì per non mostrare il tuo nome all'utente",
        allegato="Un file da inviare (facoltativo)",
    )
    async def rispondi(
        self,
        interaction: discord.Interaction,
        testo: app_commands.Range[str, 1, logica.MAX_RISPOSTA],
        anonimo: bool = False,
        allegato: discord.Attachment | None = None,
    ) -> None:
        thread = await self._thread_per_staff(interaction)
        if thread is None:
            return
        guild = interaction.guild
        # fetch_user + invio del DM + risposta: più di una chiamata a Discord, quindi defer per primo.
        await interaction.response.defer()
        firma = logica.etichetta_firma(anonimo, interaction.user.display_name, guild.name)
        embed = discord.Embed(description=testo, color=COLORE_STAFF, timestamp=datetime.now(timezone.utc))
        embed.set_author(name=firma)
        if allegato is not None:
            if (allegato.content_type or "").startswith("image/"):
                embed.set_image(url=allegato.url)
            else:
                embed.add_field(name="Allegato", value=f"[{logica.taglia(allegato.filename, 60)}]({allegato.url})")
        try:
            utente = guild.get_member(thread.user_id) or await self.bot.fetch_user(thread.user_id)
            await utente.send(embed=embed)
        except discord.NotFound:
            await interaction.followup.send("Questo utente non esiste più.", ephemeral=True)
            return
        except discord.HTTPException:
            await interaction.followup.send(
                "Non riesco a scrivere all'utente: ha i messaggi privati chiusi o ha bloccato il bot.",
                ephemeral=True,
            )
            return
        eco = discord.Embed(description=testo, color=COLORE_STAFF)
        eco.set_author(name=f"{interaction.user.display_name} → utente" + (" (anonimo)" if anonimo else ""))
        await interaction.followup.send(embed=eco, allowed_mentions=SENZA_MENZIONI)

    @comando_di_gruppo("ticket", nome="dm-chiudi", descrizione="Chiudi questa conversazione ModMail.")
    @app_commands.describe(motivo="Il motivo (l'utente lo legge)")
    async def dm_chiudi(
        self,
        interaction: discord.Interaction,
        motivo: app_commands.Range[str, 1, logica.MAX_MOTIVO_CHIUSURA] | None = None,
    ) -> None:
        thread = await self._thread_per_staff(interaction)
        if thread is None:
            return
        # Il transcript può richiedere più di 3 secondi: si risponde subito.
        await interaction.response.defer()
        esito: dict = {}
        if not await self._chiudi(
            interaction.guild, interaction.channel, thread, interaction.user.id, motivo, avvisa_utente=True, esito=esito
        ):
            await interaction.followup.send("Questa conversazione era già stata chiusa.", ephemeral=True)
            return
        testo = "Conversazione chiusa. Questo canale verrà eliminato a breve."
        if not esito.get("transcript"):
            testo += "\nAttenzione: il transcript non è stato salvato (nessun canale dei log raggiungibile)."
        await interaction.followup.send(testo)


async def setup(bot: commands.Bot) -> None:
    cog = ModMailCog(bot)
    await bot.add_cog(cog)
    scheduler.register_handler(MODMAIL_DELETE_ACTION_TYPE, cog.handle_modmail_delete_channel)
