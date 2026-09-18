"""
cogs/utility/greetings.py
============================
Welcome / Goodbye / Boost messages (SPEC.md §14.4-14.6). Modulo
gratuito — stessa assunzione dichiarata di role_menus.py: lo schema
non specifica esplicitamente Free/Premium per questa voce di §14.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.greetings_logic import render_template
from core.premium import PremiumModule, registry
from core.repositories.greetings_repo import greetings_repo

logger = logging.getLogger("iyokai.greetings")

MODULE_GREETINGS = "greetings"


def _render_for_member(template: str, member: discord.Member) -> str:
    return render_template(
        template,
        user_mention=member.mention,
        username=member.name,
        server_name=member.guild.name,
        member_count=member.guild.member_count or 0,
    )


class GreetingsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ================================================================
    # Eventi
    # ================================================================
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not await db.is_module_active_for_guild(member.guild.id, MODULE_GREETINGS):
            return

        config = await greetings_repo.get_config(member.guild.id)
        if not config.welcome_enabled:
            return

        testo = _render_for_member(config.welcome_message, member)

        if config.welcome_channel_id is not None:
            channel = member.guild.get_channel(config.welcome_channel_id)
            if isinstance(channel, discord.TextChannel):
                try:
                    await channel.send(testo)
                except discord.HTTPException:
                    logger.warning(
                        "Impossibile inviare il welcome message nel server %s.",
                        member.guild.id,
                    )

        if config.welcome_dm:
            try:
                await member.send(testo)
            except discord.HTTPException:
                pass  # DM chiusi: non è un errore da segnalare, è normale

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if not await db.is_module_active_for_guild(member.guild.id, MODULE_GREETINGS):
            return

        config = await greetings_repo.get_config(member.guild.id)
        if not config.goodbye_enabled or config.goodbye_channel_id is None:
            return

        channel = member.guild.get_channel(config.goodbye_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        testo = _render_for_member(config.goodbye_message, member)
        try:
            await channel.send(testo)
        except discord.HTTPException:
            logger.warning(
                "Impossibile inviare il goodbye message nel server %s.", member.guild.id
            )

    @commands.Cog.listener()
    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        # Rilevamento inizio boost: premium_since passa da None a un
        # timestamp. Non ci interessa il caso opposto (fine boost) né
        # i cambi di ruolo/nickname — quelli sono gestiti da
        # cogs/logging/basic_logs.py, un evento diverso con uno scopo
        # diverso (log, non annuncio).
        if before.premium_since is not None or after.premium_since is None:
            return

        if not await db.is_module_active_for_guild(after.guild.id, MODULE_GREETINGS):
            return

        config = await greetings_repo.get_config(after.guild.id)
        if not config.boost_enabled or config.boost_channel_id is None:
            return

        channel = after.guild.get_channel(config.boost_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        testo = _render_for_member(config.boost_message, after)
        try:
            await channel.send(testo)
        except discord.HTTPException:
            logger.warning(
                "Impossibile inviare il boost message nel server %s.", after.guild.id
            )

    # ================================================================
    # Comandi
    # ================================================================
    greetings_group = app_commands.Group(
        name="greetings", description="Configura i messaggi di benvenuto/addio/boost."
    )

    @greetings_group.command(
        name="welcome-setup", description="[Admin] Configura il messaggio di benvenuto."
    )
    @app_commands.describe(
        enabled="Attiva o disattiva il welcome message",
        channel="Canale dove pubblicarlo",
        message="Testo del messaggio ({user}, {username}, {server}, {membercount})",
        dm="Manda anche un DM all'utente",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def welcome_setup(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        channel: discord.TextChannel | None = None,
        message: str | None = None,
        dm: bool = False,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        config_attuale = await greetings_repo.get_config(guild.id)
        canale_finale = channel or (
            guild.get_channel(config_attuale.welcome_channel_id)
            if config_attuale.welcome_channel_id
            else None
        )
        if enabled and canale_finale is None:
            await interaction.response.send_message(
                "Specifica un canale per attivare il welcome message.", ephemeral=True
            )
            return

        await greetings_repo.set_welcome(
            guild.id,
            enabled=enabled,
            channel_id=canale_finale.id if canale_finale else 0,
            message=message or config_attuale.welcome_message,
            dm=dm,
        )
        await interaction.response.send_message(
            f"Welcome message {'attivato' if enabled else 'disattivato'}.", ephemeral=True
        )

    @greetings_group.command(
        name="goodbye-setup", description="[Admin] Configura il messaggio di addio."
    )
    @app_commands.describe(
        enabled="Attiva o disattiva il goodbye message",
        channel="Canale dove pubblicarlo",
        message="Testo del messaggio ({username}, {server}, {membercount})",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def goodbye_setup(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        channel: discord.TextChannel | None = None,
        message: str | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        config_attuale = await greetings_repo.get_config(guild.id)
        canale_finale = channel or (
            guild.get_channel(config_attuale.goodbye_channel_id)
            if config_attuale.goodbye_channel_id
            else None
        )
        if enabled and canale_finale is None:
            await interaction.response.send_message(
                "Specifica un canale per attivare il goodbye message.", ephemeral=True
            )
            return

        await greetings_repo.set_goodbye(
            guild.id,
            enabled=enabled,
            channel_id=canale_finale.id if canale_finale else 0,
            message=message or config_attuale.goodbye_message,
        )
        await interaction.response.send_message(
            f"Goodbye message {'attivato' if enabled else 'disattivato'}.", ephemeral=True
        )

    @greetings_group.command(
        name="boost-setup", description="[Admin] Configura il messaggio di boost."
    )
    @app_commands.describe(
        enabled="Attiva o disattiva il boost message",
        channel="Canale dove pubblicarlo",
        message="Testo del messaggio ({user}, {server})",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def boost_setup(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        channel: discord.TextChannel | None = None,
        message: str | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        config_attuale = await greetings_repo.get_config(guild.id)
        canale_finale = channel or (
            guild.get_channel(config_attuale.boost_channel_id)
            if config_attuale.boost_channel_id
            else None
        )
        if enabled and canale_finale is None:
            await interaction.response.send_message(
                "Specifica un canale per attivare il boost message.", ephemeral=True
            )
            return

        await greetings_repo.set_boost(
            guild.id,
            enabled=enabled,
            channel_id=canale_finale.id if canale_finale else 0,
            message=message or config_attuale.boost_message,
        )
        await interaction.response.send_message(
            f"Boost message {'attivato' if enabled else 'disattivato'}.", ephemeral=True
        )

    @greetings_group.command(
        name="preview", description="Mostra un'anteprima di come apparirebbe un messaggio."
    )
    @app_commands.describe(kind="Quale messaggio vedere in anteprima")
    @app_commands.choices(
        kind=[
            app_commands.Choice(name="Welcome", value="welcome"),
            app_commands.Choice(name="Goodbye", value="goodbye"),
            app_commands.Choice(name="Boost", value="boost"),
        ]
    )
    async def preview(self, interaction: discord.Interaction, kind: app_commands.Choice[str]) -> None:
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        config = await greetings_repo.get_config(guild.id)
        template = {
            "welcome": config.welcome_message,
            "goodbye": config.goodbye_message,
            "boost": config.boost_message,
        }[kind.value]

        testo = _render_for_member(template, interaction.user)
        await interaction.response.send_message(f"Anteprima:\n\n{testo}", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_GREETINGS,
            display_name="Greetings",
            description="Messaggi di benvenuto, addio e boost con segnaposto personalizzabili.",
            premium_capable=False,
        )
    )
    await bot.add_cog(GreetingsCog(bot))
