"""
cogs/tickets/tickets.py
==========================
Sistema di ticket: pannello con bottone "Apri Ticket" (persistente,
sopravvive a un riavvio del bot — vedi TicketPanelView più sotto),
creazione di un canale privato, comandi di gestione (claim, add,
remove, rename, priority, close).

Configurazione per server, via `guild_config.settings` (stesso
pattern già usato in report.py, basic_logs.py):
- `ticket_category_id`: la categoria Discord dove creare i canali
- `ticket_support_role_id`: (opzionale) un ruolo che vede
  automaticamente ogni ticket appena creato, oltre all'utente che
  lo ha aperto

Chi altro può vedere i ticket oltre all'utente e al ruolo di
supporto configurato: chiunque abbia già visibilità sulla categoria
per permessi propri (impostati direttamente in Discord dall'admin,
non gestiti da iYokai) — il bot non tenta di replicare o sostituire
la gestione dei permessi di categoria di Discord, solo di aggiungere
gli overwrite specifici del singolo ticket.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.repositories.ticket_repo import ticket_repo, VALID_PRIORITIES
from core.premium import PremiumModule, registry
from cogs.moderation._shared import ensure_module_enabled

MODULE_TICKETS = "tickets"

SETTING_CATEGORY = "ticket_category_id"
SETTING_SUPPORT_ROLE = "ticket_support_role_id"

# custom_id fisso: è quello che permette a discord.py di rilegare
# un click su un bottone di un messaggio VECCHIO (creato prima
# dell'ultimo riavvio del bot) alla view registrata come persistente
# in setup() — vedi bot.add_view() in fondo al file.
OPEN_TICKET_CUSTOM_ID = "iyokai_ticket_open"

PRIORITY_EMOJI = {"normal": "🟢", "high": "🟠", "urgent": "🔴"}


class TicketPanelView(discord.ui.View):
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

        already_open = await ticket_repo.count_open_tickets_for_user(
            guild.id, interaction.user.id
        )
        if already_open > 0:
            await interaction.response.send_message(
                "Hai già un ticket aperto su questo server. Chiudilo "
                "prima di aprirne uno nuovo.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True
            ),
        }

        support_role_id = await db.get_guild_setting(guild.id, SETTING_SUPPORT_ROLE)
        if support_role_id is not None:
            support_role = guild.get_role(support_role_id)
            if support_role is not None:
                overwrites[support_role] = discord.PermissionOverwrite(
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
            guild.id, interaction.user.id, channel.id
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
        await channel.send(content=interaction.user.mention, embed=embed)

        await interaction.followup.send(
            f"Ticket creato: {channel.mention}", ephemeral=True
        )


class TicketsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

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

    @ticket_group.command(name="close", description="Chiudi questo ticket.")
    async def close(self, interaction: discord.Interaction) -> None:
        ticket = await self._get_ticket_or_reply(interaction)
        if ticket is None:
            return

        await ticket_repo.close_ticket(interaction.channel.id, interaction.user.id)
        await interaction.response.send_message(
            "Ticket chiuso. Questo canale verrà eliminato tra 10 secondi."
        )
        await interaction.channel.delete(
            reason=f"Ticket chiuso da {interaction.user}", delay=10
        )


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_TICKETS,
            display_name="Ticket System",
            description="Pannello di apertura ticket, claim, gestione, priorità.",
            premium_capable=False,
        )
    )
    await bot.add_cog(TicketsCog(bot))

    # Registrazione della view persistente: DEVE avvenire ad ogni
    # avvio del bot, non solo quando il pannello viene pubblicato per
    # la prima volta — è quello che permette ai bottoni dei pannelli
    # già esistenti nei server (pubblicati prima di un riavvio) di
    # continuare a funzionare.
    bot.add_view(TicketPanelView())
