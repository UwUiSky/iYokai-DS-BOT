"""
cogs/moderation/nickname.py
===========================
/mod-sanzioni nick: cambia o azzera il soprannome di un membro. Servono «Gestire i soprannomi» a chi comanda
e al bot, e la gerarchia dei ruoli. Niente caso: è una correzione, non una sanzione; resta la riga nel log.
Funzioni coperte: SPEC §5.1 (MOD-101)
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from cogs.moderation._shared import MODULE_ACTIONS, audit_reason, check_can_moderate, ensure_module_enabled, post_to_mod_log
from core import moderazione_canali_logic as logica
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.i18n import testo_per


class ModerationNicknameCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo("mod-sanzioni", nome="nick", descrizione="Cambia o azzera il soprannome di un membro.")
    @app_commands.describe(
        membro="Il membro",
        nuovo=f"Il nuovo soprannome (da 1 a {logica.MAX_NICK} caratteri). Vuoto: torna al nome normale",
    )
    async def nick(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        nuovo: app_commands.Range[str, 1, logica.MAX_NICK] | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        if not interaction.user.guild_permissions.manage_nicknames:
            await interaction.response.send_message(await testo_per(interaction, "nickname_serve_permesso_tuo"), ephemeral=True)
            return
        if not interaction.guild.me.guild_permissions.manage_nicknames:
            await interaction.response.send_message(await testo_per(interaction, "nickname_serve_permesso_bot"), ephemeral=True)
            return
        if not await check_can_moderate(interaction, membro):
            return
        try:
            await membro.edit(nick=nuovo, reason=audit_reason(f"Soprannome cambiato da {interaction.user.id}"))
        except discord.HTTPException:
            await interaction.response.send_message(await testo_per(interaction, "nickname_non_riuscito"), ephemeral=True)
            return
        chiave = "nickname_cambiato" if nuovo else "nickname_azzerato"
        await interaction.response.send_message(await testo_per(interaction, chiave, membro=membro.mention, nuovo=nuovo or ""), ephemeral=True)
        embed = discord.Embed(title=await testo_per(interaction, "nickname_titolo", pubblica=True), color=discord.Color.blurple())
        embed.add_field(name=await testo_per(interaction, "voce_membro", pubblica=True), value=membro.mention, inline=True)
        embed.add_field(name=await testo_per(interaction, "channelcontr_moderatore", pubblica=True), value=interaction.user.mention, inline=True)
        embed.add_field(name=await testo_per(interaction, "nickname_nuovo", pubblica=True), value=(nuovo or "-")[:100], inline=True)
        await post_to_mod_log(interaction.guild, embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModerationNicknameCog(bot))
