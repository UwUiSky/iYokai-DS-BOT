"""
cogs/moderation/channel_control.py
=====================================
Comandi di controllo sul canale: /lock, /unlock, /slowmode. Modulo
SEMPRE GRATUITO (MODULE_CHANNEL_CONTROL, premium_capable=False), come
da schema ("Lock/Unlock" e "Slowmode" sono [Free]).
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.premium import PremiumModule, registry
from cogs.moderation._shared import MODULE_CHANNEL_CONTROL, ensure_module_enabled

# Limite reale di Discord per lo slowmode: 6 ore (21600 secondi). Lo
# controlliamo prima di chiamare l'API per dare un errore chiaro
# invece di un 400 generico.
MAX_SLOWMODE_SECONDS = 21600


class ModerationChannelControlCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="lock", description="Blocca la possibilità di scrivere in un canale."
    )
    @app_commands.describe(
        channel="Il canale da bloccare (default: quello attuale)",
        reason="Motivo del blocco",
    )
    async def lock(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        reason: str | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CHANNEL_CONTROL):
            return

        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message(
                "Questo comando funziona solo su canali testuali.", ephemeral=True
            )
            return

        everyone = interaction.guild.default_role
        overwrite = target.overwrites_for(everyone)
        overwrite.send_messages = False

        try:
            await target.set_permissions(
                everyone, overwrite=overwrite, reason=reason or "Canale bloccato"
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "Non ho i permessi per modificare questo canale.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🔒 Canale bloccato",
            description=f"{target.mention} è stato bloccato.",
            color=discord.Color.red(),
        )
        if reason:
            embed.add_field(name="Motivo", value=reason)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="unlock", description="Sblocca la possibilità di scrivere in un canale."
    )
    @app_commands.describe(channel="Il canale da sbloccare (default: quello attuale)")
    async def unlock(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CHANNEL_CONTROL):
            return

        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message(
                "Questo comando funziona solo su canali testuali.", ephemeral=True
            )
            return

        everyone = interaction.guild.default_role
        overwrite = target.overwrites_for(everyone)
        # None invece di True: ripristina il comportamento ereditato
        # dalla categoria/dai permessi di ruolo, invece di imporre
        # esplicitamente "può scrivere" (che potrebbe sovrascrivere
        # una restrizione voluta a un livello superiore).
        overwrite.send_messages = None

        try:
            await target.set_permissions(
                everyone, overwrite=overwrite, reason="Canale sbloccato"
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "Non ho i permessi per modificare questo canale.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🔓 Canale sbloccato",
            description=f"{target.mention} è stato sbloccato.",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="slowmode", description="Imposta lo slowmode su un canale."
    )
    @app_commands.describe(
        seconds="Secondi di attesa tra un messaggio e l'altro (0 per disattivare, max 21600)",
        channel="Il canale su cui applicare lo slowmode (default: quello attuale)",
    )
    async def slowmode(
        self,
        interaction: discord.Interaction,
        seconds: app_commands.Range[int, 0, MAX_SLOWMODE_SECONDS],
        channel: discord.TextChannel | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CHANNEL_CONTROL):
            return

        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message(
                "Questo comando funziona solo su canali testuali.", ephemeral=True
            )
            return

        try:
            await target.edit(slowmode_delay=seconds)
        except discord.Forbidden:
            await interaction.response.send_message(
                "Non ho i permessi per modificare questo canale.", ephemeral=True
            )
            return

        if seconds == 0:
            messaggio = f"Slowmode disattivato in {target.mention}."
        else:
            messaggio = f"Slowmode impostato a {seconds}s in {target.mention}."
        await interaction.response.send_message(messaggio)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_CHANNEL_CONTROL,
            display_name="Moderazione — Controllo canale",
            description="Lock, unlock, slowmode.",
            premium_capable=False,
        )
    )
    await bot.add_cog(ModerationChannelControlCog(bot))
