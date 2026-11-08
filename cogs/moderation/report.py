"""
cogs/moderation/report.py
============================
Sistema di report: un membro qualsiasi può segnalare un altro utente
allo staff. Modulo SEMPRE GRATUITO (MODULE_REPORT), come da schema.

/admin-bot config canale-report imposta il canale dove arrivano le segnalazioni
(solo admin del bot, lo dà il gruppo) — usa la colonna "settings" di
guild_config (vedi core/database.py), non "modules": è configurazione,
non un interruttore attivo/spento.
"""

from __future__ import annotations

import io
import logging
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.i18n import testo_per
from core.premium import PremiumModule, registry
from cogs.moderation._shared import MODULE_REPORT, ensure_module_enabled

logger = logging.getLogger("iyokai.report")

SETTING_REPORT_CHANNEL = "report_channel_id"


MAX_CAMPO = 1024
MESSAGGI_DI_CONTESTO = 5


async def _aggiungi_messaggio(interaction: discord.Interaction, embed: discord.Embed, messaggio: discord.Message) -> discord.File | None:
    """MOD-105: link, testo (1.024 al massimo) e i 5 messaggi prima, con il testo intero in un file. None se non serve il file."""
    embed.add_field(name=await testo_per(interaction, "report_messaggio", pubblica=True), value=messaggio.jump_url, inline=False)
    testo = messaggio.content or ""
    if testo:
        embed.add_field(name=await testo_per(interaction, "report_testo", pubblica=True), value=testo[: MAX_CAMPO - 1] + ("…" if len(testo) > MAX_CAMPO else ""), inline=False)
    try:
        prima = [m async for m in messaggio.channel.history(limit=MESSAGGI_DI_CONTESTO, before=messaggio)]
    except (discord.Forbidden, discord.HTTPException, AttributeError):
        prima = []
    prima.reverse()
    vuoto = await testo_per(interaction, "report_senza_testo", pubblica=True)
    righe = [f"{m.author} ({m.author.id}): {m.content or vuoto}" for m in prima]
    if righe:
        riepilogo = "\n".join(r[:150] for r in righe)
        embed.add_field(name=await testo_per(interaction, "report_messaggi_prima", pubblica=True), value=riepilogo[: MAX_CAMPO - 1] + ("…" if len(riepilogo) > MAX_CAMPO else ""), inline=False)
    if len(testo) <= MAX_CAMPO and len("\n".join(righe)) <= MAX_CAMPO:
        return None
    intero = "\n".join([*righe, f"--- segnalato ---\n{messaggio.author} ({messaggio.author.id}): {testo}"])
    return discord.File(io.BytesIO(intero.encode("utf-8")), filename="contesto.txt")


async def invia_segnalazione(
    interaction: discord.Interaction,
    member: discord.abc.User,
    reason: str,
    categoria: str | None = None,
    messaggio: discord.Message | None = None,
) -> None:
    """Manda la segnalazione nel canale dello staff e risponde a chi l'ha fatta. Con `messaggio` (MOD-105) aggiunge il testo e il contesto."""
    channel_id = await db.get_guild_setting(
        interaction.guild.id, SETTING_REPORT_CHANNEL
    )
    if channel_id is None:
        await interaction.response.send_message(
            await testo_per(interaction, "report_il_sistema_di_segnalazioni_non"),
            ephemeral=True,
        )
        return

    channel = interaction.guild.get_channel(channel_id)
    if channel is None:
        await interaction.response.send_message(
            await testo_per(interaction, "report_il_canale_delle_segnalazioni_configurato"),
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title=await testo_per(interaction, "report_nuova_segnalazione", pubblica=True),
        color=discord.Color.gold(),
    )
    embed.add_field(
        name=await testo_per(interaction, "report_segnalato", pubblica=True), value=f"{member.mention} ({member.id})", inline=False
    )
    embed.add_field(
        name=await testo_per(interaction, "report_segnalato_da", pubblica=True),
        value=f"{interaction.user.mention} ({interaction.user.id})",
        inline=False,
    )
    embed.add_field(name=await testo_per(interaction, "channelcontr_motivo", pubblica=True), value=reason, inline=False)
    embed.timestamp = discord.utils.utcnow()
    file = None
    if messaggio is not None:
        file = await _aggiungi_messaggio(interaction, embed, messaggio)
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
        argomenti = {"embed": embed}
        if vista:
            argomenti["view"] = vista
        if file is not None:
            argomenti["file"] = file
        await channel.send(**argomenti)
    except discord.Forbidden:
        await interaction.followup.send(
            await testo_per(interaction, "report_non_riesco_inviare_la_segnalazione"),
            ephemeral=True,
        )
        return
    except discord.HTTPException:
        await interaction.followup.send(
            await testo_per(interaction, "report_non_riesco_inviare_la_segnalazione_2"),
            ephemeral=True,
        )
        return

    await interaction.followup.send(
        await testo_per(interaction, "report_segnalazione_inviata_allo_staff_grazie"), ephemeral=True
    )


class ModerationReportCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "admin-bot",
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
            await testo_per(interaction, "report_le_segnalazioni_verranno_inviate_in", mention=channel.mention),
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

        await invia_segnalazione(interaction, member, reason, categoria)


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
