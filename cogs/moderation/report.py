"""
cogs/moderation/report.py
============================
Sistema di report: un membro qualsiasi può segnalare un altro utente
allo staff. Modulo SEMPRE GRATUITO (MODULE_REPORT), come da schema.

/admin config canale-report imposta il canale dove arrivano le segnalazioni
(solo admin del bot, lo dà il gruppo) — usa la colonna "settings" di
guild_config (vedi core/database.py), non "modules": è configurazione,
non un interruttore attivo/spento.
"""

from __future__ import annotations

import logging
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.premium import PremiumModule, registry
from cogs.moderation._shared import MODULE_REPORT, ensure_module_enabled

logger = logging.getLogger("iyokai.report")

SETTING_REPORT_CHANNEL = "report_channel_id"


class ModerationReportCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "admin",
        nome="canale-report",
        descrizione="Imposta il canale delle segnalazioni.",
        sottogruppo=("config", "Configurazione: canali, storico, ripristino ed esportazione"),
    )
    @app_commands.describe(channel="Il canale dove arriveranno le segnalazioni")
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

    @comando_di_gruppo("utility", nome="report", descrizione="Segnala un utente allo staff del server.")
    @app_commands.describe(
        member="L'utente da segnalare",
        reason="Descrizione della segnalazione (da 3 a 1000 caratteri)",
        categoria="Di che tipo è (se non lo scegli, la propone l'AI quando è accesa)",
    )
    async def report(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        # Il motivo finisce in un campo di embed, che tiene 1024 caratteri.
        reason: app_commands.Range[str, 3, 1000],
        categoria: Literal["spam", "insulti", "truffa", "altro"] | None = None,
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
                "/admin config canale-report.",
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(channel_id)
        if channel is None:
            await interaction.response.send_message(
                "Il canale delle segnalazioni configurato non esiste più. "
                "Un amministratore deve riconfigurarlo con /admin config canale-report.",
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
        await interaction.response.defer(ephemeral=True)  # l'etichetta con l'AI può metterci un po'
        vista = None
        try:
            from cogs.ai.segnalazioni import CAMPO, EtichettaView, etichetta_segnalazione
            from core.segnalazioni_logic import testo_etichetta

            etichetta = await etichetta_segnalazione(interaction.guild.id, interaction.user.id, reason, categoria)
            embed.add_field(name=CAMPO, value=testo_etichetta(etichetta), inline=False)
            vista = EtichettaView()
        except Exception:
            logger.warning("Segnalazione senza etichetta.", exc_info=True)

        try:
            await channel.send(embed=embed, view=vista) if vista else await channel.send(embed=embed)
        except discord.Forbidden:
            await interaction.followup.send(
                "Non riesco a inviare la segnalazione nel canale configurato "
                "(permessi mancanti). Contatta un amministratore.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                "Non riesco a inviare la segnalazione nel canale configurato "
                "(errore di Discord). Riprova tra poco o contatta un "
                "amministratore.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            "Segnalazione inviata allo staff. Grazie.", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_REPORT,
            display_name="Moderazione — Report",
            category="moderation",
            description="Sistema di segnalazioni verso lo staff.",
            premium_capable=False,
        )
    )
    await bot.add_cog(ModerationReportCog(bot))
