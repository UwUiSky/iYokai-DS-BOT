"""
cogs/security/security_score.py
====================================
Security Score (SPEC.md §7.5): health-check della configurazione di
sicurezza del server, un comando `/security-score` che restituisce
un punteggio 0-100 + consigli azionabili. Logica pura in
core/security_logic.py (compute_security_score) — qui solo la
raccolta dei segnali reali (permessi, 2FA, moduli attivi).

Modulo SEMPRE GRATUITO: è un semplice check di lettura, non una
protezione attiva come Anti-Raid/Anti-Nuke.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.premium import PremiumModule, registry
from core.repositories.security_repo import security_repo
from core.security_logic import ServerSecuritySignals, compute_security_score
from cogs.moderation._shared import ensure_module_enabled

MODULE_SECURITY_SCORE = "security_score"

_VERIFICATION_LEVEL_NAMES = {
    discord.VerificationLevel.none: "none",
    discord.VerificationLevel.low: "low",
    discord.VerificationLevel.medium: "medium",
    discord.VerificationLevel.high: "high",
    discord.VerificationLevel.highest: "highest",
}


async def _collect_signals(guild: discord.Guild) -> ServerSecuritySignals:
    security_settings = await security_repo.get_settings(guild.id)
    automod_active = await db.is_module_active_for_guild(guild.id, "automod")

    membri = guild.members
    admin_count = sum(1 for m in membri if not m.bot and m.guild_permissions.administrator)
    umani = sum(1 for m in membri if not m.bot)

    return ServerSecuritySignals(
        mfa_level=guild.mfa_level,
        verification_level=_VERIFICATION_LEVEL_NAMES.get(guild.verification_level, "low"),
        admin_member_count=admin_count,
        total_member_count=umani,
        anti_raid_enabled=security_settings.anti_raid.enabled,
        anti_nuke_enabled=security_settings.anti_nuke.enabled,
        automod_badwords_active=automod_active,
    )


def _build_embed(punteggio: int, consigli: tuple[str, ...]) -> discord.Embed:
    colore = discord.Color.green() if punteggio >= 80 else discord.Color.orange() if punteggio >= 50 else discord.Color.red()
    embed = discord.Embed(title="🛡️ Security Score", description=f"**{punteggio}/100**", color=colore)
    if consigli:
        embed.add_field(name="Consigli", value="\n".join(f"• {c}" for c in consigli), inline=False)
    else:
        embed.add_field(name="Consigli", value="Nessuno: la configurazione è già solida.", inline=False)
    return embed


class SecurityScoreCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="security-score", description="Calcola il punteggio di sicurezza del server con consigli.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def security_score(self, interaction: discord.Interaction) -> None:
        if not await ensure_module_enabled(interaction, MODULE_SECURITY_SCORE):
            return

        segnali = await _collect_signals(interaction.guild)
        punteggio, consigli = compute_security_score(segnali)

        # Effimera: i punti deboli del server non vanno mostrati a tutto il canale.
        await interaction.response.send_message(
            embed=_build_embed(punteggio, consigli), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_SECURITY_SCORE,
            display_name="Security Score",
            category="security",
            description="Health-check della configurazione di sicurezza del server, con consigli azionabili.",
            premium_capable=False,
        )
    )
    await bot.add_cog(SecurityScoreCog(bot))
