"""
cogs/utility/snipe.py
========================
Reactionsnipe (SPEC.md §14.11) e Ghost ping detection (§14.12) —
gli UNICI due della "famiglia snipe" costruibili senza il Message
Content Intent. Snipe (§14.9) ed Editsnipe (§14.10), che mostrano il
contenuto del messaggio, restano rimandati come §8.16 — vedi il
docstring di core/snipe_logic.py per la verifica punto-per-punto che
ha distinto questi due casi (buildabili) dagli altri due (bloccati),
invece di liquidare in blocco tutta la "famiglia snipe" come fatto
per errore su §8.13/§8.8 (vedi PROGRESS.md Fase 70b).

Stato in memoria, non persistito: entrambe le funzionalità mostrano
"l'ultimo evento", non uno storico — perdere quello stato a un
riavvio del bot è accettabile e coerente con come funzionano i bot
"snipe" in generale (nessuno si aspetta che sopravviva a un riavvio).
BoundedCache (SPEC.md §1.5) invece di un dict semplice, per non far
crescere la memoria senza limite su un bot multi-tenant.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.bounded_cache import BoundedCache
from core.database import db
from core.snipe_logic import is_ghost_ping_candidate
from core.premium import PremiumModule, registry
from cogs.logging.basic_logs import SETTING_LOG_CHANNEL

logger = logging.getLogger("iyokai.snipe")

MODULE_REACTIONSNIPE = "reactionsnipe"
MODULE_GHOST_PING = "ghost_ping_detection"

_CACHE_MAX_SIZE = 2000


@dataclass(frozen=True)
class _RemovedReaction:
    emoji: str
    user_id: int
    message_id: int
    removed_at: datetime


@dataclass(frozen=True)
class _TrackedMention:
    author_id: int
    mentioned_user_ids: tuple[int, ...]
    mentions_everyone: bool
    channel_id: int
    created_at: datetime


class SnipeCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Chiave: channel_id -> ultima reazione rimossa in quel canale.
        self._last_removed_reaction: BoundedCache[int, _RemovedReaction] = BoundedCache(_CACHE_MAX_SIZE)
        # Chiave: message_id -> messaggio candidato ghost ping, in
        # attesa di essere cancellato (o mai, se resta lì finché la
        # cache non lo scarta per LRU).
        self._tracked_mentions: BoundedCache[int, _TrackedMention] = BoundedCache(_CACHE_MAX_SIZE)

    # ================================================================
    # SPEC.md §14.11 — Reactionsnipe
    # ================================================================
    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None:
            return
        if not await db.is_module_active_for_guild(payload.guild_id, MODULE_REACTIONSNIPE):
            return

        self._last_removed_reaction.set(
            payload.channel_id,
            _RemovedReaction(
                emoji=str(payload.emoji),
                user_id=payload.user_id,
                message_id=payload.message_id,
                removed_at=datetime.now(timezone.utc),
            ),
        )

    @app_commands.command(
        name="reactionsnipe",
        description="Mostra l'ultima reazione rimossa in questo canale.",
    )
    async def reactionsnipe(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or interaction.channel is None:
            return

        rimossa = self._last_removed_reaction.get(interaction.channel.id)
        if rimossa is None:
            await interaction.response.send_message(
                "Nessuna reazione rimossa recentemente in questo canale.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🎯 Reactionsnipe",
            description=(
                f"{rimossa.emoji} rimossa da <@{rimossa.user_id}> dal "
                f"[messaggio](https://discord.com/channels/{interaction.guild.id}/"
                f"{interaction.channel.id}/{rimossa.message_id})."
            ),
            color=discord.Color.orange(),
            timestamp=rimossa.removed_at,
        )
        await interaction.response.send_message(embed=embed)

    # ================================================================
    # SPEC.md §14.12 — Ghost ping detection
    # ================================================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None:
            return
        if not await db.is_module_active_for_guild(message.guild.id, MODULE_GHOST_PING):
            return

        mentioned_ids = [m.id for m in message.mentions]
        if not is_ghost_ping_candidate(mentioned_ids, message.mention_everyone, message.author.bot):
            return

        self._tracked_mentions.set(
            message.id,
            _TrackedMention(
                author_id=message.author.id,
                mentioned_user_ids=tuple(mentioned_ids),
                mentions_everyone=message.mention_everyone,
                channel_id=message.channel.id,
                created_at=datetime.now(timezone.utc),
            ),
        )

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        if payload.guild_id is None:
            return

        tracciato = self._tracked_mentions.get(payload.message_id)
        if tracciato is None:
            return
        self._tracked_mentions.delete(payload.message_id)

        if not await db.is_module_active_for_guild(payload.guild_id, MODULE_GHOST_PING):
            return

        log_channel_id = await db.get_guild_setting(payload.guild_id, SETTING_LOG_CHANNEL)
        if log_channel_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        log_channel = guild.get_channel(log_channel_id)
        if not isinstance(log_channel, discord.TextChannel):
            return

        if tracciato.mentions_everyone:
            menzioni = "@everyone/@here"
        else:
            menzioni = ", ".join(f"<@{uid}>" for uid in tracciato.mentioned_user_ids)

        embed = discord.Embed(
            title="👻 Ghost ping rilevato",
            description=(
                f"<@{tracciato.author_id}> ha menzionato {menzioni} in "
                f"<#{tracciato.channel_id}> e ha cancellato il messaggio."
            ),
            color=discord.Color.dark_grey(),
        )
        try:
            await log_channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("Impossibile inviare l'avviso di ghost ping nel server %s", payload.guild_id)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_REACTIONSNIPE,
            display_name="Reactionsnipe",
            description="Mostra l'ultima reazione rimossa in un canale.",
            premium_capable=False,
        )
    )
    registry.register(
        PremiumModule(
            name=MODULE_GHOST_PING,
            display_name="Ghost Ping Detection",
            description="Segnala nel canale log chi menziona e poi cancella il messaggio.",
            premium_capable=False,
        )
    )
    await bot.add_cog(SnipeCog(bot))
