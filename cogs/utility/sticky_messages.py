"""
cogs/utility/sticky_messages.py
===================================
Sticky Messages (SPEC.md §14.13): un messaggio che resta sempre in
fondo a un canale — ad ogni nuovo messaggio, il vecchio sticky viene
cancellato e ripubblicato in coda. Debounce minimo (core/sticky_
message_logic.py) per non cancellare+reinviare ad ogni singolo
messaggio in un canale attivo.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.premium import PremiumModule, registry
from core.repositories.sticky_message_repo import sticky_message_repo
from core.sticky_message_logic import should_repost_sticky

logger = logging.getLogger("iyokai.sticky_messages")

MODULE_STICKY_MESSAGES = "sticky_messages"


class StickyMessagesCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if message.guild is None:
            return
        if not isinstance(message.channel, discord.TextChannel):
            return

        if not await db.is_module_active_for_guild(message.guild.id, MODULE_STICKY_MESSAGES):
            return

        sticky = await sticky_message_repo.get_sticky(message.channel.id)
        if sticky is None:
            return

        ora = datetime.now(timezone.utc)
        if not should_repost_sticky(sticky.last_reposted_at, ora):
            return

        if sticky.last_message_id is not None:
            try:
                vecchio = await message.channel.fetch_message(sticky.last_message_id)
                await vecchio.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass  # già cancellato o non raggiungibile: non blocca la ripubblicazione

        try:
            nuovo_messaggio = await message.channel.send(sticky.message_text)
        except discord.Forbidden:
            logger.warning(
                "Permessi insufficienti per ripubblicare lo sticky nel canale %s.",
                message.channel.id,
            )
            return

        await sticky_message_repo.update_repost_state(
            message.channel.id, nuovo_messaggio.id, ora
        )

    # ================================================================
    # Comandi
    # ================================================================
    sticky_group = app_commands.Group(
        name="sticky", description="Gestisci il messaggio fisso di un canale."
    )

    @sticky_group.command(name="set", description="[Admin] Imposta lo sticky message di un canale.")
    @app_commands.describe(
        channel="Il canale dove impostare lo sticky",
        message="Il testo dello sticky message",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_sticky(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: str,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        await sticky_message_repo.set_sticky(channel.id, guild.id, message)
        await interaction.response.send_message(
            f"Sticky message impostato per {channel.mention}. "
            f"Verrà pubblicato al prossimo messaggio in quel canale.",
            ephemeral=True,
        )

    @sticky_group.command(name="remove", description="[Admin] Rimuove lo sticky message di un canale.")
    @app_commands.describe(channel="Il canale da cui rimuovere lo sticky")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def remove_sticky(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        sticky = await sticky_message_repo.get_sticky(channel.id)
        rimosso = await sticky_message_repo.remove_sticky(channel.id)

        if not rimosso:
            await interaction.response.send_message(
                f"Nessuno sticky message configurato per {channel.mention}.",
                ephemeral=True,
            )
            return

        if sticky is not None and sticky.last_message_id is not None:
            try:
                vecchio = await channel.fetch_message(sticky.last_message_id)
                await vecchio.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

        await interaction.response.send_message(
            f"Sticky message rimosso da {channel.mention}.", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_STICKY_MESSAGES,
            display_name="Sticky Messages",
            description="Messaggio fisso in fondo a un canale, ripubblicato automaticamente.",
            premium_capable=False,
        )
    )
    await bot.add_cog(StickyMessagesCog(bot))
