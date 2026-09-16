"""
cogs/moderation/report.py
============================
Sistema di report: un membro qualsiasi può segnalare un altro utente
allo staff. Modulo SEMPRE GRATUITO (MODULE_REPORT), come da schema.

/report-setup imposta il canale dove arrivano le segnalazioni
(richiede il permesso Manage Server) — usa la colonna "settings" di
guild_config (vedi core/database.py), non "modules": è configurazione,
non un interruttore attivo/spento.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.premium import PremiumModule, registry
from cogs.moderation._shared import MODULE_REPORT, ensure_module_enabled

SETTING_REPORT_CHANNEL = "report_channel_id"


class ModerationReportCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="report-setup", description="[Admin] Imposta il canale delle segnalazioni."
    )
    @app_commands.describe(channel="Il canale dove arriveranno le segnalazioni")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def report_setup(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_REPORT):
            return

        await db.set_guild_setting(
            interaction.guild.id, SETTING_REPORT_CHANNEL, channel.id
        )
        await interaction.response.send_message(
            f"Le segnalazioni verranno inviate in {channel.mention}.",
            ephemeral=True,
        )

    @app_commands.command(
        name="report", description="Segnala un utente allo staff del server."
    )
    @app_commands.describe(
        member="L'utente da segnalare", reason="Descrizione della segnalazione"
    )
    async def report(
        self, interaction: discord.Interaction, member: discord.Member, reason: str
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_REPORT):
            return

        channel_id = await db.get_guild_setting(
            interaction.guild.id, SETTING_REPORT_CHANNEL
        )
        if channel_id is None:
            await interaction.response.send_message(
                "Il sistema di segnalazioni non è ancora stato configurato "
                "su questo server. Un amministratore deve usare "
                "/report-setup.",
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(channel_id)
        if channel is None:
            await interaction.response.send_message(
                "Il canale delle segnalazioni configurato non esiste più. "
                "Un amministratore deve riconfigurarlo con /report-setup.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🚩 Nuova segnalazione",
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="Segnalato", value=f"{member.mention} ({member.id})", inline=False
        )
        embed.add_field(
            name="Segnalato da",
            value=f"{interaction.user.mention} ({interaction.user.id})",
            inline=False,
        )
        embed.add_field(name="Motivo", value=reason, inline=False)
        embed.timestamp = discord.utils.utcnow()

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message(
                "Non riesco a inviare la segnalazione nel canale configurato "
                "(permessi mancanti). Contatta un amministratore.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Segnalazione inviata allo staff. Grazie.", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_REPORT,
            display_name="Moderazione — Report",
            description="Sistema di segnalazioni verso lo staff.",
            premium_capable=False,
        )
    )
    await bot.add_cog(ModerationReportCog(bot))
