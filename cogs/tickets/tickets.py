"""
cogs/tickets/tickets.py
==========================
Sistema di ticket: pannello con bottone "Apri Ticket" (persistente,
sopravvive a un riavvio del bot — vedi TicketPanelView più sotto),
creazione di un canale privato, comandi di gestione (claim, add,
remove, rename, priority, close, forceclose).

Configurazione per server, via `guild_config.settings` (stesso
pattern già usato in report.py, basic_logs.py):
- `ticket_category_id`: la categoria Discord dove creare i canali
  (usata come fallback quando non è configurata nessuna categoria
  select-menu — SPEC.md §13.2, vedi TicketCategorySelectView)
- `ticket_support_role_id`: (legacy, un solo ruolo) e
  `ticket_support_role_ids` (SPEC.md §13.13, lista JSON di più
  ruoli) — combinati con core.ticket_logic.merge_support_role_ids,
  entrambi vedono automaticamente ogni ticket appena creato, oltre
  all'utente che lo ha aperto

Chi altro può vedere i ticket oltre all'utente e ai ruoli di
supporto configurati: chiunque abbia già visibilità sulla categoria
per permessi propri (impostati direttamente in Discord dall'admin,
non gestiti da iYokai) — il bot non tenta di replicare o sostituire
la gestione dei permessi di categoria di Discord, solo di aggiungere
gli overwrite specifici del singolo ticket.

SPEC.md §13.10/§13.11 (transcript automatico alla chiusura, inviato
nel canale log + in DM all'utente): la lettura dei messaggi avviene
via channel.history() PRIMA di cancellare il canale — una chiamata
REST, che restituisce il contenuto pieno indipendentemente dal
Message Content Intent (quell'intent riguarda solo gli eventi
gateway in tempo reale, non la history REST governata dal normale
permesso READ_MESSAGE_HISTORY — stessa assunzione già verificata e
documentata in core/spam_trap_logic.py). Vedi core/ticket_logic.py
per la costruzione pura del testo del transcript.

/ticket close: l'eliminazione del canale dopo l'attesa passa dallo
scheduler persistente (core/scheduler.py, azione
`ticket_delete_channel`), così sopravvive a un riavvio del bot o a una
ricarica del cog; gli errori temporanei di Discord vengono riprovati
dallo scheduler. /ticket forceclose elimina subito e funziona anche su
un ticket già chiuso il cui canale è rimasto.
Funzioni coperte: SPEC §13.8/§13.9/§13.10/§13.11, REVIEW.md BUG-1,
BUG-30 (issue #2, #42).
"""

# DA FARE (issue #62, fase F1): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §6 (Ticket).
# DA FARE (issue #84, fase F9): NF-13, Ticket: modulo, più pannelli,
#   chiusura automatica, voto. Vedi
#   revisione/02-piano/NUOVE_FUNZIONI.md.

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.repositories.ticket_repo import ticket_repo, VALID_PRIORITIES
from core.ticket_logic import (
    build_transcript_text,
    format_duration_seconds,
    format_transcript_line,
    is_first_response,
    merge_support_role_ids,
)
from core.premium import PremiumModule, registry
from core.scheduler import in_seconds, scheduler
from core.ui_base import BaseView
from cogs.moderation._shared import ensure_module_enabled
from cogs.logging.basic_logs import SETTING_LOG_CHANNEL

logger = logging.getLogger("iyokai.tickets")

MODULE_TICKETS = "tickets"

SETTING_CATEGORY = "ticket_category_id"
SETTING_SUPPORT_ROLE = "ticket_support_role_id"
SETTING_SUPPORT_ROLES = "ticket_support_role_ids"

# custom_id fisso: è quello che permette a discord.py di rilegare
# un click su un bottone di un messaggio VECCHIO (creato prima
# dell'ultimo riavvio del bot) alla view registrata come persistente
# in setup() — vedi bot.add_view() in fondo al file.
OPEN_TICKET_CUSTOM_ID = "iyokai_ticket_open"

# Azione dello scheduler che elimina il canale di un ticket chiuso.
TICKET_DELETE_ACTION_TYPE = "ticket_delete_channel"
RITARDO_ELIMINAZIONE_SECONDI = 10

PRIORITY_EMOJI = {"normal": "🟢", "high": "🟠", "urgent": "🔴"}


async def _support_role_ids(guild_id: int) -> list[int]:
    """SPEC.md §13.13 — combina il ruolo legacy con la lista nuova."""
    legacy = await db.get_guild_setting(guild_id, SETTING_SUPPORT_ROLE)
    extra = await db.get_guild_setting(guild_id, SETTING_SUPPORT_ROLES, default=[])
    return merge_support_role_ids(legacy, extra)


async def _is_ticket_staff(interaction: discord.Interaction) -> bool:
    """
    SPEC.md §13.9: chi può usare /ticket forceclose — chi ha il
    permesso Discord Manage Server, oppure chi ha almeno uno dei
    ruoli di supporto configurati (§13.13). A differenza di /ticket
    close (aperto a chiunque abbia accesso al canale, incluso
    l'utente che lo ha aperto), forceclose è riservato allo staff.
    """
    if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
        return False
    if interaction.user.guild_permissions.manage_guild:
        return True
    ruoli_supporto = set(await _support_role_ids(interaction.guild.id))
    ruoli_utente = {r.id for r in interaction.user.roles}
    return bool(ruoli_supporto & ruoli_utente)


async def _open_ticket_channel(
    interaction: discord.Interaction,
    guild: discord.Guild,
    category: discord.CategoryChannel,
    category_label: str | None,
) -> None:
    """
    Logica di apertura di un ticket condivisa dal bottone unico
    (nessuna categoria configurata) e dal select menu categorie
    (SPEC.md §13.2) — l'interazione arriva già deferred, quindi qui
    si usa sempre .followup.
    """
    already_open = await ticket_repo.count_open_tickets_for_user(
        guild.id, interaction.user.id
    )
    if already_open > 0:
        await interaction.followup.send(
            "Hai già un ticket aperto su questo server. Chiudilo "
            "prima di aprirne uno nuovo.",
            ephemeral=True,
        )
        return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True
        ),
    }

    for role_id in await _support_role_ids(guild.id):
        role = guild.get_role(role_id)
        if role is not None:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )

    # Il canale si crea PRIMA di registrare il ticket nel DB, così
    # se la creazione fallisce (permessi mancanti, categoria
    # piena — Discord limita 50 canali per categoria) non resta
    # un ticket "fantasma" senza canale reale.
    try:
        channel = await category.create_text_channel(
            name="ticket-nuovo",  # rinominato subito dopo con il numero vero
            overwrites=overwrites,
            reason=f"Ticket aperto da {interaction.user}",
        )
    except discord.Forbidden:
        await interaction.followup.send(
            "Non ho i permessi per creare un canale in quella categoria.",
            ephemeral=True,
        )
        return
    except discord.HTTPException:
        await interaction.followup.send(
            "Impossibile creare il canale del ticket (la categoria "
            "potrebbe aver raggiunto il limite di 50 canali).",
            ephemeral=True,
        )
        return

    ticket_number = await ticket_repo.create_ticket(
        guild.id, interaction.user.id, channel.id, category_label=category_label
    )
    await channel.edit(name=f"ticket-{ticket_number:04d}")

    embed = discord.Embed(
        title=f"Ticket #{ticket_number:04d}",
        description=(
            f"Ciao {interaction.user.mention}, grazie per averci "
            f"contattato. Descrivi il tuo problema e lo staff ti "
            f"risponderà a breve."
        ),
        color=discord.Color.blurple(),
    )
    if category_label is not None:
        embed.add_field(name="Categoria", value=category_label)
    await channel.send(content=interaction.user.mention, embed=embed)

    await interaction.followup.send(
        f"Ticket creato: {channel.mention}", ephemeral=True
    )


class TicketCategorySelectView(BaseView):
    """
    SPEC.md §13.2: select menu tra più categorie di ticket, mostrato
    invece del bottone unico quando il server ne ha configurato
    almeno una. NON persistente: vive solo per la durata
    dell'interazione ephemeral che la mostra, non deve sopravvivere
    a un riavvio del bot (a differenza di TicketPanelView, che è il
    pannello pubblico sempre visibile).
    """

    def __init__(self, guild: discord.Guild, categorie) -> None:
        super().__init__(timeout=180)
        self._guild = guild
        select = discord.ui.Select(
            placeholder="Scegli una categoria...",
            options=[
                discord.SelectOption(label=c.label, value=c.label, emoji=c.emoji)
                for c in categorie
            ],
        )
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        select = self.children[0]
        label_scelta = select.values[0]
        categorie = await ticket_repo.list_categories(self._guild.id)
        scelta = next((c for c in categorie if c.label == label_scelta), None)
        if scelta is None:
            await interaction.response.send_message(
                "Questa categoria non è più disponibile.", ephemeral=True
            )
            return

        category_channel = self._guild.get_channel(scelta.category_id)
        if not isinstance(category_channel, discord.CategoryChannel):
            await interaction.response.send_message(
                "La categoria Discord collegata non esiste più. "
                "Un amministratore deve riconfigurarla.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        await _open_ticket_channel(interaction, self._guild, category_channel, scelta.label)


class TicketPanelView(BaseView):
    """
    View PERSISTENTE: timeout=None e un custom_id esplicito sul
    bottone sono entrambi obbligatori perché bot.add_view() la
    accetti (discord.py la rifiuta altrimenti con un ValueError
    esplicito — verificato prima di scrivere questo file, non
    assunto). Senza persistenza, il bottone smetterebbe di
    funzionare ad ogni riavvio del bot per tutti i pannelli già
    pubblicati nei server.
    """

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Apri Ticket",
        style=discord.ButtonStyle.primary,
        emoji="🎫",
        custom_id=OPEN_TICKET_CUSTOM_ID,
    )
    async def open_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        guild = interaction.guild
        if guild is None:
            return

        if not await db.is_module_active_for_guild(guild.id, MODULE_TICKETS):
            await interaction.response.send_message(
                "Il sistema di ticket non è attivo su questo server.",
                ephemeral=True,
            )
            return

        # SPEC.md §13.2: se il server ha configurato almeno una
        # categoria, si mostra il select menu invece del bottone
        # unico storico — retrocompatibile con chi non ne ha ancora
        # configurata nessuna.
        categorie = await ticket_repo.list_categories(guild.id)
        if categorie:
            await interaction.response.send_message(
                "Scegli la categoria del tuo ticket:",
                view=TicketCategorySelectView(guild, categorie),
                ephemeral=True,
            )
            return

        category_id = await db.get_guild_setting(guild.id, SETTING_CATEGORY)
        if category_id is None:
            await interaction.response.send_message(
                "Il sistema di ticket non è ancora stato configurato "
                "(manca la categoria). Un amministratore deve usare "
                "/ticket-setup.",
                ephemeral=True,
            )
            return

        category = guild.get_channel(category_id)
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                "La categoria configurata per i ticket non esiste più. "
                "Un amministratore deve riconfigurarla con /ticket-setup.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        await _open_ticket_channel(interaction, guild, category, category_label=None)


class TicketsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Canali di cui si sta ancora leggendo la history per il
        # transcript: lo scheduler non li elimina finché non ha finito.
        self._transcript_in_corso: set[int] = set()

    @app_commands.command(
        name="ticket-setup",
        description="[Admin] Configura la categoria (e opzionalmente il ruolo di supporto) per i ticket.",
    )
    @app_commands.describe(
        category="La categoria dove verranno creati i canali dei ticket",
        support_role="Ruolo che vedrà automaticamente ogni ticket (facoltativo)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_setup(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        support_role: discord.Role | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.",
                ephemeral=True,
            )
            return

        await db.set_guild_setting(interaction.guild.id, SETTING_CATEGORY, category.id)
        if support_role is not None:
            await db.set_guild_setting(
                interaction.guild.id, SETTING_SUPPORT_ROLE, support_role.id
            )

        messaggio = f"Categoria dei ticket impostata su **{category.name}**."
        if support_role is not None:
            messaggio += f" Ruolo di supporto: {support_role.mention}."
        await interaction.response.send_message(messaggio, ephemeral=True)

    @app_commands.command(
        name="ticket-panel",
        description="[Admin] Pubblica il pannello per l'apertura dei ticket in questo canale.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_panel(self, interaction: discord.Interaction) -> None:
        if not await ensure_module_enabled(interaction, MODULE_TICKETS):
            return

        embed = discord.Embed(
            title="🎫 Supporto",
            description="Premi il bottone qui sotto per aprire un ticket privato con lo staff.",
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, view=TicketPanelView())

    # ================================================================
    # SPEC.md §13.2 — categorie ticket configurabili
    # ================================================================
    ticket_category_group = app_commands.Group(
        name="ticket-category",
        description="[Admin] Gestisci le categorie mostrate nel select menu di apertura ticket.",
    )

    @ticket_category_group.command(name="add", description="[Admin] Aggiungi (o aggiorna) una categoria di ticket.")
    @app_commands.describe(
        label="Nome mostrato nel select menu (es. 'Supporto tecnico')",
        category="La categoria Discord dove creare i canali di questa categoria",
        emoji="Emoji da mostrare accanto al nome (facoltativo)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_category_add(
        self,
        interaction: discord.Interaction,
        label: str,
        category: discord.CategoryChannel,
        emoji: str | None = None,
    ) -> None:
        if interaction.guild is None:
            return
        await ticket_repo.add_category(interaction.guild.id, label, category.id, emoji)
        await interaction.response.send_message(
            f"Categoria **{label}** impostata su **{category.name}**.", ephemeral=True
        )

    @ticket_category_group.command(name="remove", description="[Admin] Rimuovi una categoria di ticket.")
    @app_commands.describe(label="Il nome esatto della categoria da rimuovere")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_category_remove(self, interaction: discord.Interaction, label: str) -> None:
        if interaction.guild is None:
            return
        rimossa = await ticket_repo.remove_category(interaction.guild.id, label)
        if rimossa:
            await interaction.response.send_message(f"Categoria **{label}** rimossa.", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"Nessuna categoria chiamata **{label}**.", ephemeral=True
            )

    @ticket_category_group.command(name="list", description="[Admin] Elenca le categorie di ticket configurate.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_category_list(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        categorie = await ticket_repo.list_categories(interaction.guild.id)
        if not categorie:
            await interaction.response.send_message(
                "Nessuna categoria configurata: il pannello mostra il bottone unico.",
                ephemeral=True,
            )
            return
        righe = [f"- {c.emoji or ''} **{c.label}** -> <#{c.category_id}>".strip() for c in categorie]
        await interaction.response.send_message("\n".join(righe), ephemeral=True)

    # ================================================================
    # SPEC.md §13.13 — ruoli di supporto multipli
    # ================================================================
    ticket_support_role_group = app_commands.Group(
        name="ticket-support-role",
        description="[Admin] Gestisci i ruoli che vedono automaticamente ogni ticket.",
    )

    @ticket_support_role_group.command(name="add", description="[Admin] Aggiungi un ruolo di supporto.")
    @app_commands.describe(role="Il ruolo da aggiungere")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_support_role_add(self, interaction: discord.Interaction, role: discord.Role) -> None:
        if interaction.guild is None:
            return
        attuali = await db.get_guild_setting(interaction.guild.id, SETTING_SUPPORT_ROLES, default=[])
        if role.id not in attuali:
            attuali.append(role.id)
            await db.set_guild_setting(interaction.guild.id, SETTING_SUPPORT_ROLES, attuali)
        await interaction.response.send_message(
            f"{role.mention} aggiunto ai ruoli di supporto.", ephemeral=True
        )

    @ticket_support_role_group.command(name="remove", description="[Admin] Rimuovi un ruolo di supporto.")
    @app_commands.describe(role="Il ruolo da rimuovere")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_support_role_remove(self, interaction: discord.Interaction, role: discord.Role) -> None:
        if interaction.guild is None:
            return
        attuali = await db.get_guild_setting(interaction.guild.id, SETTING_SUPPORT_ROLES, default=[])
        if role.id in attuali:
            attuali.remove(role.id)
            await db.set_guild_setting(interaction.guild.id, SETTING_SUPPORT_ROLES, attuali)
        await interaction.response.send_message(
            f"{role.mention} rimosso dai ruoli di supporto.", ephemeral=True
        )

    @ticket_support_role_group.command(name="list", description="[Admin] Elenca i ruoli di supporto configurati.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_support_role_list(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        ruoli_id = await _support_role_ids(interaction.guild.id)
        if not ruoli_id:
            await interaction.response.send_message("Nessun ruolo di supporto configurato.", ephemeral=True)
            return
        righe = [f"<@&{rid}>" for rid in ruoli_id]
        await interaction.response.send_message(", ".join(righe), ephemeral=True)

    # ================================================================
    # SPEC.md §13.12 — statistiche
    # ================================================================
    @app_commands.command(name="ticket-stats", description="[Admin] Statistiche del sistema di ticket.")
    @app_commands.describe(operator="Mostra le statistiche di questo operatore invece di quelle del server")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_stats(
        self, interaction: discord.Interaction, operator: discord.Member | None = None
    ) -> None:
        if interaction.guild is None:
            return

        if operator is not None:
            stats = await ticket_repo.get_operator_stats(interaction.guild.id, operator.id)
            embed = discord.Embed(
                title=f"Statistiche ticket — {operator.display_name}",
                color=discord.Color.blurple(),
            )
            embed.add_field(name="Presi in carico", value=str(stats.claimed_count))
            embed.add_field(name="Chiusi", value=str(stats.closed_count))
            embed.add_field(
                name="Tempo medio di prima risposta",
                value=format_duration_seconds(stats.avg_response_seconds),
            )
        else:
            stats = await ticket_repo.get_guild_stats(interaction.guild.id)
            embed = discord.Embed(title="Statistiche ticket del server", color=discord.Color.blurple())
            embed.add_field(name="Totali", value=str(stats.total_count))
            embed.add_field(name="Aperti", value=str(stats.open_count))
            embed.add_field(name="Chiusi", value=str(stats.closed_count))
            embed.add_field(
                name="Tempo medio di prima risposta",
                value=format_duration_seconds(stats.avg_response_seconds),
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    ticket_group = app_commands.Group(
        name="ticket", description="Comandi di gestione dei ticket."
    )

    async def _get_ticket_or_reply(self, interaction: discord.Interaction):
        ticket = await ticket_repo.get_ticket_by_channel(interaction.channel.id)
        if ticket is None or ticket.status != "open":
            await interaction.response.send_message(
                "Questo comando funziona solo dentro un canale ticket aperto.",
                ephemeral=True,
            )
            return None
        return ticket

    @ticket_group.command(name="claim", description="Prendi in carico questo ticket.")
    async def claim(self, interaction: discord.Interaction) -> None:
        ticket = await self._get_ticket_or_reply(interaction)
        if ticket is None:
            return

        await ticket_repo.claim_ticket(interaction.channel.id, interaction.user.id)
        await interaction.response.send_message(
            f"Ticket preso in carico da {interaction.user.mention}."
        )

    @ticket_group.command(name="add", description="Aggiungi un utente a questo ticket.")
    @app_commands.describe(member="L'utente da aggiungere")
    async def add(self, interaction: discord.Interaction, member: discord.Member) -> None:
        ticket = await self._get_ticket_or_reply(interaction)
        if ticket is None:
            return

        await interaction.channel.set_permissions(
            member, view_channel=True, send_messages=True, read_message_history=True
        )
        await interaction.response.send_message(f"{member.mention} aggiunto al ticket.")

    @ticket_group.command(name="remove", description="Rimuovi un utente da questo ticket.")
    @app_commands.describe(member="L'utente da rimuovere")
    async def remove(self, interaction: discord.Interaction, member: discord.Member) -> None:
        ticket = await self._get_ticket_or_reply(interaction)
        if ticket is None:
            return

        await interaction.channel.set_permissions(member, overwrite=None)
        await interaction.response.send_message(f"{member.mention} rimosso dal ticket.")

    @ticket_group.command(name="rename", description="Rinomina questo ticket.")
    @app_commands.describe(name="Il nuovo nome del canale")
    async def rename(self, interaction: discord.Interaction, name: str) -> None:
        ticket = await self._get_ticket_or_reply(interaction)
        if ticket is None:
            return

        await interaction.channel.edit(name=name)
        await interaction.response.send_message(f"Ticket rinominato in **{name}**.")

    @ticket_group.command(name="priority", description="Imposta la priorità di questo ticket.")
    @app_commands.describe(level="Livello di priorità")
    @app_commands.choices(
        level=[app_commands.Choice(name=p, value=p) for p in VALID_PRIORITIES]
    )
    async def priority(
        self, interaction: discord.Interaction, level: app_commands.Choice[str]
    ) -> None:
        ticket = await self._get_ticket_or_reply(interaction)
        if ticket is None:
            return

        await ticket_repo.set_priority(interaction.channel.id, level.value)
        emoji = PRIORITY_EMOJI.get(level.value, "")
        await interaction.response.send_message(
            f"Priorità impostata su {emoji} **{level.value}**."
        )

    async def _build_transcript_text(self, channel: discord.TextChannel, ticket) -> str:
        """
        SPEC.md §13.10: legge la history del canale (REST — vedi il
        docstring del modulo sul perché non serve il Message Content
        Intent) e la trasforma in testo semplice tramite le funzioni
        pure di core/ticket_logic.py.
        """
        header = [
            f"Transcript ticket #{ticket.ticket_number:04d}",
            f"Aperto da: {ticket.user_id} il {ticket.created_at.isoformat()}",
            f"Categoria: {ticket.category_label or 'n/d'}",
            f"Priorità: {ticket.priority}",
            f"Preso in carico da: {ticket.claimed_by or 'nessuno'}",
        ]
        righe = []
        async for messaggio in channel.history(limit=None, oldest_first=True):
            righe.append(
                format_transcript_line(
                    messaggio.created_at.strftime("%Y-%m-%d %H:%M"),
                    str(messaggio.author),
                    messaggio.content,
                )
            )
        return build_transcript_text(header, righe)

    async def _deliver_transcript(
        self, guild: discord.Guild, channel: discord.TextChannel, ticket
    ) -> None:
        """SPEC.md §13.11: invio nel canale log configurato + DM all'utente."""
        try:
            testo = await self._build_transcript_text(channel, ticket)
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("Impossibile leggere la history del ticket %s per il transcript", channel.id)
            return

        nome_file = f"ticket-{ticket.ticket_number:04d}-transcript.txt"

        log_channel_id = await db.get_guild_setting(guild.id, SETTING_LOG_CHANNEL)
        if log_channel_id is not None:
            log_channel = guild.get_channel(log_channel_id)
            if isinstance(log_channel, discord.TextChannel):
                try:
                    await log_channel.send(
                        content=f"Transcript ticket #{ticket.ticket_number:04d}",
                        file=discord.File(io.BytesIO(testo.encode("utf-8")), filename=nome_file),
                    )
                except (discord.Forbidden, discord.HTTPException):
                    logger.warning("Impossibile inviare il transcript nel canale log del server %s", guild.id)

        try:
            utente = guild.get_member(ticket.user_id) or await self.bot.fetch_user(ticket.user_id)
            await utente.send(
                content=f"Ecco il transcript del tuo ticket #{ticket.ticket_number:04d}.",
                file=discord.File(io.BytesIO(testo.encode("utf-8")), filename=nome_file),
            )
        except (discord.Forbidden, discord.HTTPException, discord.NotFound):
            logger.info("Impossibile inviare il transcript in DM all'utente %s (DM chiusi?)", ticket.user_id)

    async def _transcript_senza_bloccare(
        self, guild: discord.Guild, channel: discord.TextChannel, ticket
    ) -> None:
        """Un transcript che fallisce non deve mai impedire l'eliminazione del canale."""
        self._transcript_in_corso.add(channel.id)
        try:
            await self._deliver_transcript(guild, channel, ticket)
        except Exception:
            logger.exception("Transcript del ticket %s non riuscito", channel.id)
        finally:
            self._transcript_in_corso.discard(channel.id)

    async def _elimina_canale(self, channel_id: int, motivo: str | None) -> None:
        """
        Elimina il canale del ticket. 404 = già eliminato, 403 = solo
        registrato (riprovare non serve). Gli altri errori di Discord
        (5xx) escono: chi chiama riprova più tardi.
        """
        try:
            channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
            await channel.delete(reason=motivo)
        except discord.NotFound:
            return
        except discord.Forbidden:
            logger.warning("Permessi mancanti per eliminare il canale ticket %s", channel_id)

    async def _pianifica_eliminazione(
        self, interaction: discord.Interaction, motivo: str, ritardo: int
    ) -> None:
        """BUG-30: nello scheduler persistente, non in un task in memoria."""
        await scheduler.schedule(
            interaction.guild.id,
            interaction.user.id,
            TICKET_DELETE_ACTION_TYPE,
            in_seconds(ritardo),
            {"channel_id": interaction.channel.id, "reason": motivo},
        )

    async def handle_ticket_delete_channel(self, guild_id: int, user_id: int, payload: dict) -> None:
        """Handler dello scheduler. Se solleva, lo scheduler riprova più tardi."""
        channel_id = payload["channel_id"]
        if channel_id in self._transcript_in_corso:
            # Il transcript sta ancora leggendo i messaggi: si ripassa dopo.
            await scheduler.schedule(
                guild_id,
                user_id,
                TICKET_DELETE_ACTION_TYPE,
                in_seconds(RITARDO_ELIMINAZIONE_SECONDI),
                payload,
            )
            return
        await self._elimina_canale(channel_id, payload.get("reason"))

    @ticket_group.command(name="close", description="Chiudi questo ticket.")
    async def close(self, interaction: discord.Interaction) -> None:
        ticket = await self._get_ticket_or_reply(interaction)
        if ticket is None:
            return

        await ticket_repo.close_ticket(interaction.channel.id, interaction.user.id)
        # Prima di tutto il resto: da qui in poi un riavvio o un errore
        # nel transcript non lasciano più il canale per sempre.
        await self._pianifica_eliminazione(
            interaction, f"Ticket chiuso da {interaction.user}", RITARDO_ELIMINAZIONE_SECONDI
        )
        await interaction.response.send_message(
            "Ticket chiuso. Questo canale verrà eliminato entro un minuto."
        )
        await self._transcript_senza_bloccare(interaction.guild, interaction.channel, ticket)

    @ticket_group.command(
        name="forceclose",
        description="[Staff] Chiudi immediatamente questo ticket, senza attesa.",
    )
    async def forceclose(self, interaction: discord.Interaction) -> None:
        """
        SPEC.md §13.9: a differenza di /ticket close (aperto a
        chiunque abbia accesso al canale, incluso chi ha aperto il
        ticket), questo è riservato allo staff ed elimina il canale
        SUBITO, senza attesa — pensato per i ticket da chiudere
        immediatamente (es. abuso, spam). Funziona anche su un ticket
        già chiuso il cui canale è rimasto (BUG-30).
        """
        if not await _is_ticket_staff(interaction):
            await interaction.response.send_message(
                "Solo lo staff (permesso Manage Server o un ruolo di "
                "supporto configurato) può forzare la chiusura.",
                ephemeral=True,
            )
            return

        ticket = await ticket_repo.get_ticket_by_channel(interaction.channel.id)
        if ticket is None:
            await interaction.response.send_message(
                "Questo comando funziona solo dentro un canale ticket.", ephemeral=True
            )
            return

        # Su un ticket già chiuso non cambia nulla nel database.
        await ticket_repo.close_ticket(interaction.channel.id, interaction.user.id, force=True)
        await interaction.response.send_message(
            f"Ticket chiuso forzatamente da {interaction.user.mention}. Elimino il canale."
        )
        await self._transcript_senza_bloccare(interaction.guild, interaction.channel, ticket)

        motivo = f"Ticket forzatamente chiuso da {interaction.user}"
        try:
            await self._elimina_canale(interaction.channel.id, motivo)
        except discord.HTTPException:
            logger.warning(
                "Eliminazione del canale ticket %s non riuscita: riprovo dallo scheduler.",
                interaction.channel.id,
            )
            await self._pianifica_eliminazione(interaction, motivo, RITARDO_ELIMINAZIONE_SECONDI)

    # ================================================================
    # SPEC.md §13.12 — traccia la prima risposta nel canale ticket
    # ================================================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None:
            return

        ticket = await ticket_repo.get_ticket_by_channel(message.channel.id)
        if ticket is None or ticket.status != "open" or ticket.first_response_at is not None:
            return

        if not is_first_response(message.author.id, ticket.user_id, message.author.bot):
            return

        await ticket_repo.record_first_response(message.channel.id, datetime.now(timezone.utc))


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_TICKETS,
            display_name="Ticket System",
            category="tickets",
            description="Pannello di apertura ticket, claim, gestione, priorità.",
            premium_capable=False,
        )
    )
    cog = TicketsCog(bot)
    await bot.add_cog(cog)
    scheduler.register_handler(TICKET_DELETE_ACTION_TYPE, cog.handle_ticket_delete_channel)

    # Registrazione della view persistente: DEVE avvenire ad ogni
    # avvio del bot, non solo quando il pannello viene pubblicato per
    # la prima volta — è quello che permette ai bottoni dei pannelli
    # già esistenti nei server (pubblicati prima di un riavvio) di
    # continuare a funzionare.
    bot.add_view(TicketPanelView())
