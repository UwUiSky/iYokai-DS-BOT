"""
cogs/utility/custom_command_requests.py
===========================================
Custom Commands — sistema di RICHIESTA (SPEC.md §14.8, "progettato
in dettaglio" nello schema originale). Un membro, da QUALUNQUE server
dove il bot è presente, propone un nuovo comando tramite un modal —
la richiesta arriva SEMPRE al server principale dello sviluppatore
(config.MAIN_GUILD_ID), mai al server del membro stesso (distinto dal
Suggestion System di §14.14, che è l'opposto: va al server cliente).

Nessun gate is_module_active_for_guild: è uno strumento rivolto allo
sviluppatore, non una feature che un admin di un server cliente
attiva o disattiva per i propri membri — sempre disponibile ovunque
il bot sia presente, come un modulo di contatto/feedback.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.config import config
from core.database import db
from core.repositories.custom_command_request_repo import (
    CustomCommandRequest,
    custom_command_request_repo,
)
from core.suggestion_logic import APPROVED, PENDING, REJECTED, can_decide

logger = logging.getLogger("iyokai.custom_command_requests")

SETTING_REQUESTS_CHANNEL = "custom_command_requests_channel_id"
BUTTON_CUSTOM_ID_PREFIX = "iyokai_ccr"


def _build_embed(request: CustomCommandRequest) -> discord.Embed:
    colori = {
        PENDING: discord.Color.blurple(),
        APPROVED: discord.Color.green(),
        REJECTED: discord.Color.red(),
    }
    etichette = {PENDING: "In attesa", APPROVED: "✅ Approvata", REJECTED: "❌ Rifiutata"}

    embed = discord.Embed(
        title=f"🛠️ Richiesta comando: {request.command_name}",
        color=colori[request.status],
    )
    embed.add_field(name="Descrizione", value=request.description, inline=False)
    embed.add_field(name="Esempio d'uso", value=f"`{request.example}`", inline=False)
    embed.add_field(
        name="Server richiedente",
        value=f"{request.requester_guild_name} (`{request.requester_guild_id}`)",
        inline=True,
    )
    embed.add_field(
        name="Utente",
        value=f"{request.username_snapshot} (<@{request.user_id}>, `{request.user_id}`)",
        inline=True,
    )
    embed.add_field(name="Stato", value=etichette[request.status], inline=True)
    embed.timestamp = request.created_at
    return embed


class CustomCommandRequestModal(discord.ui.Modal, title="Richiedi un nuovo comando"):
    # discord.ui.Label che avvolge il TextInput — pattern corretto e
    # non deprecato, stesso schema già verificato e in uso in
    # StaffReplyModal (cogs/security/spam_trap.py).
    command_name_label = discord.ui.Label(
        text="Nome del comando",
        component=discord.ui.TextInput(placeholder="/esempio", max_length=100),
    )
    description_label = discord.ui.Label(
        text="Descrizione",
        component=discord.ui.TextInput(style=discord.TextStyle.paragraph, max_length=500),
    )
    example_label = discord.ui.Label(
        text="Esempio d'uso",
        component=discord.ui.TextInput(placeholder="/esempio parametro", max_length=200),
    )

    def __init__(self, cog: "CustomCommandRequestsCog") -> None:
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.handle_modal_submit(
            interaction,
            command_name=self.command_name_label.component.value,
            description=self.description_label.component.value,
            example=self.example_label.component.value,
        )


class CustomCommandRequestsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _build_decision_view(self, request_id: int) -> discord.ui.View:
        view = discord.ui.View(timeout=None)

        approve_button: discord.ui.Button = discord.ui.Button(
            label="Approva",
            style=discord.ButtonStyle.success,
            custom_id=f"{BUTTON_CUSTOM_ID_PREFIX}:approve:{request_id}",
        )
        approve_button.callback = self._make_decision_callback(request_id, APPROVED)
        view.add_item(approve_button)

        reject_button: discord.ui.Button = discord.ui.Button(
            label="Rifiuta",
            style=discord.ButtonStyle.danger,
            custom_id=f"{BUTTON_CUSTOM_ID_PREFIX}:reject:{request_id}",
        )
        reject_button.callback = self._make_decision_callback(request_id, REJECTED)
        view.add_item(reject_button)

        return view

    def _make_decision_callback(self, request_id: int, new_status: str):
        async def callback(interaction: discord.Interaction) -> None:
            await self._handle_decision(interaction, request_id, new_status)

        return callback

    async def _handle_decision(
        self, interaction: discord.Interaction, request_id: int, new_status: str
    ) -> None:
        # La decisione è riservata allo staff del server PRINCIPALE
        # (quello dello sviluppatore) — non del server del membro che
        # ha fatto la richiesta, che non è nemmeno chi vede questo
        # messaggio.
        if (
            not isinstance(interaction.user, discord.Member)
            or not interaction.user.guild_permissions.manage_guild
        ):
            await interaction.response.send_message(
                "Solo lo staff può decidere sulle richieste.", ephemeral=True
            )
            return

        request = await custom_command_request_repo.get_request(request_id)
        if request is None:
            await interaction.response.send_message(
                "Questa richiesta non esiste più.", ephemeral=True
            )
            return

        if not can_decide(request.status):
            await interaction.response.send_message(
                "Questa richiesta è già stata decisa.", ephemeral=True
            )
            return

        await custom_command_request_repo.set_status(
            request_id,
            new_status,
            decided_by=interaction.user.id,
            decided_at=datetime.now(timezone.utc),
        )

        request_aggiornata = await custom_command_request_repo.get_request(request_id)
        embed = _build_embed(request_aggiornata)
        view_disabilitata = discord.ui.View(timeout=None)
        await interaction.response.edit_message(embed=embed, view=view_disabilitata)

        # Notifica di ritorno al richiedente, come previsto dallo
        # schema originale.
        try:
            richiedente = self.bot.get_user(request.user_id) or await self.bot.fetch_user(
                request.user_id
            )
            esito = "approvata ✅" if new_status == APPROVED else "rifiutata ❌"
            await richiedente.send(
                f"La tua richiesta per il comando `{request.command_name}` è stata {esito}."
            )
        except discord.HTTPException:
            logger.warning(
                "Impossibile notificare il richiedente %s dell'esito della "
                "richiesta #%s (DM chiusi?).",
                request.user_id,
                request_id,
            )

    async def handle_modal_submit(
        self,
        interaction: discord.Interaction,
        command_name: str,
        description: str,
        example: str,
    ) -> None:
        guild = self.bot.get_guild(config.MAIN_GUILD_ID)
        if guild is None:
            await interaction.response.send_message(
                "Il server principale non è raggiungibile in questo momento. Riprova più tardi.",
                ephemeral=True,
            )
            return

        channel_id = await db.get_guild_setting(guild.id, SETTING_REQUESTS_CHANNEL)
        channel = guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "Il sistema di richiesta comandi non è ancora configurato. Riprova più tardi.",
                ephemeral=True,
            )
            return

        request_id = await custom_command_request_repo.create_request(
            requester_guild_id=interaction.guild.id if interaction.guild else 0,
            requester_guild_name=interaction.guild.name if interaction.guild else "DM",
            user_id=interaction.user.id,
            username_snapshot=str(interaction.user),
            command_name=command_name,
            description=description,
            example=example,
        )
        request = await custom_command_request_repo.get_request(request_id)
        embed = _build_embed(request)
        view = self._build_decision_view(request_id)

        try:
            messaggio = await channel.send(embed=embed, view=view)
        except discord.Forbidden:
            await interaction.response.send_message(
                "Richiesta salvata, ma non è stato possibile pubblicarla — "
                "contatta lo staff.",
                ephemeral=True,
            )
            return

        await custom_command_request_repo.set_message_id(request_id, messaggio.id)
        self.bot.add_view(view, message_id=messaggio.id)

        await interaction.response.send_message(
            "Richiesta inviata! Riceverai un DM quando verrà decisa.", ephemeral=True
        )

    # ================================================================
    # Comandi
    # ================================================================
    @app_commands.command(
        name="request-custom-command", description="Proponi un nuovo comando per il bot."
    )
    async def request_custom_command(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(CustomCommandRequestModal(self))

    @app_commands.command(
        name="custom-command-requests-setup",
        description="[Owner] Imposta il canale delle richieste (solo nel server principale).",
    )
    @app_commands.describe(channel="Il canale dove pubblicare le richieste")
    async def setup_requests_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        if interaction.user.id != config.OWNER_ID:
            await interaction.response.send_message(
                "Solo il proprietario del bot può configurare questo canale.", ephemeral=True
            )
            return
        if interaction.guild is None or interaction.guild.id != config.MAIN_GUILD_ID:
            await interaction.response.send_message(
                "Questo comando va usato nel server principale.", ephemeral=True
            )
            return

        await db.set_guild_setting(interaction.guild.id, SETTING_REQUESTS_CHANNEL, channel.id)
        await interaction.response.send_message(
            f"Le richieste di comandi verranno pubblicate in {channel.mention}.", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    cog = CustomCommandRequestsCog(bot)
    await bot.add_cog(cog)

    for request in await custom_command_request_repo.list_pending():
        view = cog._build_decision_view(request.id)
        bot.add_view(view, message_id=request.message_id)
