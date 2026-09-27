"""
cogs/security/global_ban.py
================================
Ban globale (SPEC.md §7.3) — propagazione cross-server di un ban
scattato dalla Spam Trap (§7.3) verso ogni altro server che condivide
il bot E ha aderito alla stessa rete di ban globali. Modulo CANDIDATO
PREMIUM (come Spam Trap/Anti-Raid/Anti-Nuke).

Vedi core/global_ban_logic.py per la nota di design completa sul
perché questo è distinto dal ban globale via fingerprint/alt-
detection descritto in SPEC.md §4.3 (quello resta bloccato,
correttamente, sulla dipendenza da §4.2 — raccolta OAuth2 al momento
del verify — non costruita): qui si banna lo STESSO account Discord
(stesso user id) su ogni server aderente, non un account diverso
sospettato di essere un alt.

L'opt-in usa l'attivazione modulo già esistente
(`db.is_module_active_for_guild`/`set_module_active_for_guild`,
MODULE_GLOBAL_BAN) — nessuna tabella di configurazione dedicata,
vedi core/repositories/global_ban_repo.py. Reciprocità: un ban
scattato nel server A si propaga al server B SOLO SE entrambi hanno
il modulo attivo — un server che non ha aderito non riceve mai un
ban deciso altrove.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.global_ban_logic import should_propagate_ban
from core.premium import PremiumModule, registry
from core.repositories.global_ban_repo import global_ban_repo

logger = logging.getLogger("iyokai.global_ban")

MODULE_GLOBAL_BAN = "global_ban"


async def propagate_ban(
    bot: commands.Bot, source_guild: discord.Guild, user_id: int, reason: str
) -> list[int]:
    """
    Chiamata dalla Spam Trap (§7.3) subito dopo un ban confermato.
    Restituisce la lista degli ID dei server in cui il ban è stato
    effettivamente propagato (per il log di chi ha chiamato).

    Best-effort: un fallimento (permessi insufficienti, rate limit,
    utente già bannato lì) su UN server target non deve bloccare la
    propagazione verso gli altri — viene solo loggato e saltato.
    """
    source_opted_in = await db.is_module_active_for_guild(source_guild.id, MODULE_GLOBAL_BAN)
    if not source_opted_in:
        return []

    propagati: list[int] = []
    for target in list(bot.guilds):
        target_opted_in = await db.is_module_active_for_guild(target.id, MODULE_GLOBAL_BAN)
        if not should_propagate_ban(
            source_guild_id=source_guild.id,
            target_guild_id=target.id,
            source_opted_in=source_opted_in,
            target_opted_in=target_opted_in,
        ):
            continue

        try:
            await target.ban(
                discord.Object(id=user_id),
                reason=f"Ban globale — Spam Trap innescata su {source_guild.name}: {reason}",
                delete_message_seconds=0,
            )
        except discord.Forbidden:
            logger.warning(
                "Ban globale: permessi insufficienti per bannare %s nel server %s.",
                user_id, target.id,
            )
            continue
        except discord.HTTPException:
            logger.warning(
                "Ban globale: errore HTTP bannando %s nel server %s (probabilmente già bannato).",
                user_id, target.id,
            )
            continue

        await global_ban_repo.log_propagation(source_guild.id, target.id, user_id, reason)
        propagati.append(target.id)

    return propagati


class GlobalBanCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    global_ban_group = app_commands.Group(
        name="global-ban",
        description="Configura la rete di ban globali (propagazione cross-server dei ban Spam Trap).",
    )

    @global_ban_group.command(name="enable", description="Aderisci alla rete di ban globali (propaga e ricevi).")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def enable(self, interaction: discord.Interaction) -> None:
        await db.set_module_active_for_guild(
            interaction.guild.id, MODULE_GLOBAL_BAN, True, changed_by=interaction.user.id
        )
        await interaction.response.send_message(
            "✅ Ban globale attivato: i ban della Spam Trap di questo server verranno propagati "
            "verso ogni altro server aderente, e questo server riceverà a sua volta i loro.",
            ephemeral=True,
        )

    @global_ban_group.command(name="disable", description="Abbandona la rete di ban globali.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def disable(self, interaction: discord.Interaction) -> None:
        await db.set_module_active_for_guild(
            interaction.guild.id, MODULE_GLOBAL_BAN, False, changed_by=interaction.user.id
        )
        await interaction.response.send_message("❌ Ban globale disattivato.", ephemeral=True)

    @global_ban_group.command(name="status", description="Mostra lo stato e la storia recente del ban globale.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def status(self, interaction: discord.Interaction) -> None:
        attivo = await db.is_module_active_for_guild(interaction.guild.id, MODULE_GLOBAL_BAN)
        outgoing = await global_ban_repo.get_recent_outgoing(interaction.guild.id, limit=5)
        incoming = await global_ban_repo.get_recent_incoming(interaction.guild.id, limit=5)

        embed = discord.Embed(
            title="🌐 Ban globale — stato",
            description=f"**Attivo**: {'sì' if attivo else 'no'}",
            color=discord.Color.blue() if attivo else discord.Color.dark_gray(),
        )
        embed.add_field(
            name="Ban propagati da qui",
            value="\n".join(
                f"<@{e.user_id}> → server {e.target_guild_id}" for e in outgoing
            ) or "Nessuno.",
            inline=False,
        )
        embed.add_field(
            name="Ban ricevuti da altri server",
            value="\n".join(
                f"<@{e.user_id}> ← server {e.source_guild_id}" for e in incoming
            ) or "Nessuno.",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_GLOBAL_BAN,
            display_name="Ban Globale",
            description="Propaga i ban della Spam Trap verso ogni server aderente alla rete.",
            premium_capable=True,
        )
    )
    await bot.add_cog(GlobalBanCog(bot))
