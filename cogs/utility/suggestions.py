"""
cogs/utility/suggestions.py
==============================
Suggestion System (SPEC.md §14.14 — per i server clienti, distinto
da §14.8 che manda richieste al server dello sviluppatore). Un
membro propone, il server vota con reazioni native 👍👎, lo staff
decide con bottoni persistenti (approva/rifiuta) — stesso pattern di
View dinamica per-messaggio già collaudato per i Role Menu
(bot.add_view(view, message_id=...), ricostruita ad ogni avvio per
ogni suggestion ancora in sospeso).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.premium import PremiumModule, registry
from core.repositories.suggestion_repo import Suggestion, suggestion_repo
from core.suggestion_logic import APPROVED, PENDING, REJECTED, can_decide

logger = logging.getLogger("iyokai.suggestions")

MODULE_SUGGESTIONS = "suggestions"
SETTING_SUGGESTIONS_CHANNEL = "suggestions_channel_id"

BUTTON_CUSTOM_ID_PREFIX = "iyokai_suggestion"


def _build_embed(suggestion: Suggestion) -> discord.Embed:
    colori = {
        PENDING: discord.Color.blurple(),
        APPROVED: discord.Color.green(),
        REJECTED: discord.Color.red(),
    }
    etichette = {PENDING: "In attesa", APPROVED: "✅ Approvata", REJECTED: "❌ Rifiutata"}

    embed = discord.Embed(
        title=f"💡 Suggerimento #{suggestion.id}",
        description=suggestion.suggestion_text,
        color=colori[suggestion.status],
    )
    embed.add_field(name="Proposto da", value=f"<@{suggestion.user_id}>", inline=True)
    embed.add_field(name="Stato", value=etichette[suggestion.status], inline=True)
    if suggestion.decided_by is not None:
        embed.add_field(name="Deciso da", value=f"<@{suggestion.decided_by}>", inline=True)
    return embed


class SuggestionsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _build_decision_view(self, suggestion_id: int) -> discord.ui.View:
        view = discord.ui.View(timeout=None)

        approve_button: discord.ui.Button = discord.ui.Button(
            label="Approva",
            style=discord.ButtonStyle.success,
            custom_id=f"{BUTTON_CUSTOM_ID_PREFIX}:approve:{suggestion_id}",
        )
        approve_button.callback = self._make_decision_callback(suggestion_id, APPROVED)
        view.add_item(approve_button)

        reject_button: discord.ui.Button = discord.ui.Button(
            label="Rifiuta",
            style=discord.ButtonStyle.danger,
            custom_id=f"{BUTTON_CUSTOM_ID_PREFIX}:reject:{suggestion_id}",
        )
        reject_button.callback = self._make_decision_callback(suggestion_id, REJECTED)
        view.add_item(reject_button)

        return view

    def _make_decision_callback(self, suggestion_id: int, new_status: str):
        async def callback(interaction: discord.Interaction) -> None:
            await self._handle_decision(interaction, suggestion_id, new_status)

        return callback

    async def _handle_decision(
        self, interaction: discord.Interaction, suggestion_id: int, new_status: str
    ) -> None:
        if (
            not isinstance(interaction.user, discord.Member)
            or not interaction.user.guild_permissions.manage_guild
        ):
            await interaction.response.send_message(
                "Solo lo staff può decidere sui suggerimenti.", ephemeral=True
            )
            return

        suggestion = await suggestion_repo.get_suggestion(suggestion_id)
        if suggestion is None:
            await interaction.response.send_message(
                "Questo suggerimento non esiste più.", ephemeral=True
            )
            return

        if not can_decide(suggestion.status):
            await interaction.response.send_message(
                "Questo suggerimento è già stato deciso.", ephemeral=True
            )
            return

        await suggestion_repo.set_status(
            suggestion_id,
            new_status,
            decided_by=interaction.user.id,
            decided_at=datetime.now(timezone.utc),
        )

        suggestion_aggiornata = await suggestion_repo.get_suggestion(suggestion_id)
        embed = _build_embed(suggestion_aggiornata)

        # View vuota: una decisione presa non deve poter essere
        # ri-cliccata (approva/rifiuta due volte, o cambiare idea).
        view_disabilitata = discord.ui.View(timeout=None)
        await interaction.response.edit_message(embed=embed, view=view_disabilitata)

    # ================================================================
    # Comandi
    # ================================================================
    @app_commands.command(
        name="suggestion-setup", description="[Admin] Imposta il canale dei suggerimenti."
    )
    @app_commands.describe(channel="Il canale dove pubblicare i suggerimenti")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def suggestion_setup(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        guild = interaction.guild
        if guild is None:
            return
        await db.set_guild_setting(guild.id, SETTING_SUGGESTIONS_CHANNEL, channel.id)
        await interaction.response.send_message(
            f"I suggerimenti verranno pubblicati in {channel.mention}.", ephemeral=True
        )

    @app_commands.command(name="suggest", description="Proponi un'idea per questo server.")
    @app_commands.describe(text="Il tuo suggerimento")
    async def suggest(self, interaction: discord.Interaction, text: str) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        if not await db.is_module_active_for_guild(guild.id, MODULE_SUGGESTIONS):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server. "
                "Un amministratore può attivarlo con /setup.",
                ephemeral=True,
            )
            return

        channel_id = await db.get_guild_setting(guild.id, SETTING_SUGGESTIONS_CHANNEL)
        if channel_id is None:
            await interaction.response.send_message(
                "Il canale dei suggerimenti non è ancora stato configurato "
                "(un amministratore deve usare /suggestion-setup).",
                ephemeral=True,
            )
            return

        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "Il canale dei suggerimenti configurato non è più raggiungibile.",
                ephemeral=True,
            )
            return

        suggestion_id = await suggestion_repo.create_suggestion(
            guild.id, channel.id, interaction.user.id, text
        )
        suggestion = await suggestion_repo.get_suggestion(suggestion_id)
        embed = _build_embed(suggestion)
        view = self._build_decision_view(suggestion_id)

        try:
            messaggio = await channel.send(embed=embed, view=view)
        except discord.Forbidden:
            await interaction.response.send_message(
                "Non ho i permessi per pubblicare nel canale dei suggerimenti.",
                ephemeral=True,
            )
            return

        await suggestion_repo.set_message_id(suggestion_id, messaggio.id)
        self.bot.add_view(view, message_id=messaggio.id)

        try:
            await messaggio.add_reaction("👍")
            await messaggio.add_reaction("👎")
        except discord.HTTPException:
            logger.warning(
                "Impossibile aggiungere le reazioni di voto al suggerimento %s.",
                suggestion_id,
            )

        await interaction.response.send_message(
            f"Suggerimento pubblicato in {channel.mention}!", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_SUGGESTIONS,
            display_name="Suggestions",
            description="Sistema di suggerimenti per i membri, con voto e decisione dello staff.",
            premium_capable=False,
        )
    )
    cog = SuggestionsCog(bot)
    await bot.add_cog(cog)

    # Ricostruzione delle View dinamiche persistenti per OGNI
    # suggestion ancora in sospeso, ad ogni avvio — stesso principio
    # già usato per i Role Menu.
    for suggestion in await suggestion_repo.list_pending():
        view = cog._build_decision_view(suggestion.id)
        bot.add_view(view, message_id=suggestion.message_id)
