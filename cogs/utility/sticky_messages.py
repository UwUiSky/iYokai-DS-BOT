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

import asyncio
import logging
import weakref
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.admin_mentions_logic import menzioni_ammesse, puo_pingare_ruoli
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.premium import PremiumModule, registry
from core.repositories.sticky_message_repo import sticky_message_repo
from core.sticky_message_logic import should_repost_sticky

logger = logging.getLogger("iyokai.sticky_messages")

MODULE_STICKY_MESSAGES = "sticky_messages"


class StickyMessagesCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # M 10.4: un blocco per canale. Il blocco vive finché qualcuno lo
        # tiene (WeakValueDictionary): nessun elenco da ripulire.
        self._blocchi: "weakref.WeakValueDictionary[int, asyncio.Lock]" = (
            weakref.WeakValueDictionary()
        )

    def _blocco(self, channel_id: int) -> asyncio.Lock:
        blocco = self._blocchi.get(channel_id)
        if blocco is None:
            blocco = asyncio.Lock()
            self._blocchi[channel_id] = blocco
        return blocco

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

        # Lettura, cancellazione, invio e salvataggio dello stato sono un
        # blocco solo: con dieci messaggi veloci ne passa uno e gli altri
        # trovano il debounce già scattato.
        async with self._blocco(message.channel.id):
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
                nuovo_messaggio = await message.channel.send(
                    sticky.message_text,
                    allowed_mentions=menzioni_ammesse(sticky.ping_ruoli),
                )
            except discord.HTTPException as errore:
                # Comprende Forbidden (permessi mancanti) e gli errori 400/5xx.
                logger.warning(
                    "Non riesco a ripubblicare lo sticky nel canale %s: %s",
                    message.channel.id,
                    errore,
                )
                return

            await sticky_message_repo.update_repost_state(
                message.channel.id, nuovo_messaggio.id, ora
            )

    # ================================================================
    # Comandi
    # ================================================================
    @comando_di_gruppo(
        "admin",
        nome="sticky-set",
        descrizione="Imposta lo sticky message di un canale.",
        sottogruppo=("messaggi", "Messaggi programmati e messaggi fissi"),
    )
    @app_commands.describe(
        channel="Il canale dove impostare lo sticky",
        message="Il testo dello sticky message (massimo 2000 caratteri)",
    )
    async def set_sticky(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        # Lo sticky è un messaggio normale: Discord ne accetta 2000 caratteri.
        message: app_commands.Range[str, 1, 2000],
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        if not await db.is_module_active_for_guild(guild.id, MODULE_STICKY_MESSAGES):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server. "
                "Un amministratore può attivarlo con /admin setup attiva.",
                ephemeral=True,
            )
            return

        ping_ruoli = isinstance(interaction.user, discord.Member) and puo_pingare_ruoli(
            interaction.user.guild_permissions
        )
        await sticky_message_repo.set_sticky(channel.id, guild.id, message, ping_ruoli=ping_ruoli)
        await interaction.response.send_message(
            f"Sticky message impostato per {channel.mention}. "
            f"Verrà pubblicato al prossimo messaggio in quel canale.",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "admin",
        nome="sticky-togli",
        descrizione="Rimuove lo sticky message di un canale.",
        sottogruppo=("messaggi", "Messaggi programmati e messaggi fissi"),
    )
    @app_commands.describe(channel="Il canale da cui rimuovere lo sticky")
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
            category="utility",
            description="Messaggio fisso in fondo a un canale, ripubblicato automaticamente.",
            premium_capable=False,
        )
    )
    await bot.add_cog(StickyMessagesCog(bot))
