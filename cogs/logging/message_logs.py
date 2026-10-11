"""
cogs/logging/message_logs.py
============================
Log dei messaggi cancellati, modificati e cancellati in blocco. Scrive
nella destinazione «messaggi» del router (canale di testo o forum) e,
per ogni evento, una riga nel log eventi senza il testo. Serve il
Message Content Intent; un messaggio uscito dalla memoria di
discord.py si segnala senza contenuto. Fa parte del Logging Avanzato.
Funzioni coperte: SPEC §8.16 (NF-02)
Dipende da: core/channel_router.py, core/repositories/log_ignora_repo.py
"""

from __future__ import annotations

import io
import logging

import discord
from discord.ext import commands

from cogs.logging.advanced_logs import logging_avanzato_attivo
from core import channel_router as router
from core.channel_router import SETTING_LOG_CHANNEL, TIPO_MESSAGGI
from core.database import db
from core.message_log_logic import (
    MessaggioArchiviato,
    da_ignorare,
    file_blocco,
    riepilogo_blocco,
    senza_accento_grave,
    testo_allegati,
)
from core.repositories.event_log_repo import event_log_repo
from core.repositories.log_ignora_repo import log_ignora_repo
from core.testo_limiti import CAMPO_MAX, DESCRIZIONE_MAX, tronca

logger = logging.getLogger("iyokai.logging.messaggi")


def _scartato(ignorati, canale, message: discord.Message | None, channel_id: int) -> bool:
    """Canale/utente/prefisso ignorati e messaggi dei bot."""
    if message is not None and message.author.bot:
        return True
    return da_ignorare(
        ignorati,
        channel_id=channel_id,
        author_id=message.author.id if message is not None else None,
        testo=message.content if message is not None else None,
        category_id=getattr(canale, "category_id", None),
        thread_parent_id=getattr(canale, "parent_id", None),
    )


class MessageLogsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _scrivi(self, guild: discord.Guild, **contenuto) -> None:
        predefinito = await db.get_guild_setting(guild.id, SETTING_LOG_CHANNEL)
        dest = await router.destinazione(guild, TIPO_MESSAGGI, predefinito)
        if dest is not None:
            await router.invia_a(dest, guild, TIPO_MESSAGGI, **contenuto)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        if payload.guild_id is None:
            return
        if not await logging_avanzato_attivo(payload.guild_id, self.bot):
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        messaggio = payload.cached_message
        if messaggio is not None and messaggio.author.bot:
            return
        canale = guild.get_channel_or_thread(payload.channel_id)
        ignorati = await log_ignora_repo.carica(guild.id)
        if _scartato(ignorati, canale, messaggio, payload.channel_id):
            return

        await event_log_repo.log_event(
            guild.id,
            "message_delete",
            actor_id=None,
            target_user_id=messaggio.author.id if messaggio else None,
            channel_id=payload.channel_id,
            details={"message_id": payload.message_id, "in_memoria": messaggio is not None},
        )
        embed = discord.Embed(
            title="🗑️ Messaggio cancellato",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Canale", value=f"<#{payload.channel_id}>", inline=True)
        if messaggio is None:
            embed.description = "*Contenuto non disponibile: il messaggio è troppo vecchio per la mia memoria.*"
            embed.add_field(name="ID messaggio", value=str(payload.message_id), inline=True)
        else:
            embed.description = (
                tronca(senza_accento_grave(messaggio.content), DESCRIZIONE_MAX) or "*(senza testo)*"
            )
            embed.add_field(
                name="Autore", value=f"{messaggio.author.mention} ({messaggio.author.id})", inline=True
            )
            allegati = testo_allegati([a.filename for a in messaggio.attachments])
            if allegati:
                embed.add_field(name="Allegati", value=allegati, inline=False)
        await self._scrivi(guild, embed=embed)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent) -> None:
        if payload.guild_id is None:
            return
        if not await logging_avanzato_attivo(payload.guild_id, self.bot):
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        canale = guild.get_channel_or_thread(payload.channel_id)
        ignorati = await log_ignora_repo.carica(guild.id)
        if _scartato(ignorati, canale, None, payload.channel_id):
            return

        totale = len(payload.message_ids)
        archiviati = [
            MessaggioArchiviato(
                message_id=m.id,
                author_id=m.author.id,
                author_nome=str(m.author),
                testo=m.content,
                quando=m.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            )
            for m in payload.cached_messages
            if not _scartato(ignorati, canale, m, payload.channel_id)
        ]
        await event_log_repo.log_event(
            guild.id,
            "message_bulk_delete",
            channel_id=payload.channel_id,
            details={"totale": totale, "in_memoria": len(archiviati)},
        )
        embed = discord.Embed(
            title="🗑️ Cancellazione in blocco",
            description=riepilogo_blocco(totale, len(payload.cached_messages), payload.channel_id),
            color=discord.Color.dark_red(),
            timestamp=discord.utils.utcnow(),
        )
        contenuto: dict = {"embed": embed}
        if archiviati:
            dati = file_blocco(archiviati, totale - len(archiviati))
            contenuto["file"] = discord.File(io.BytesIO(dati), filename="messaggi_cancellati.txt")
        await self._scrivi(guild, **contenuto)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if after.guild is None or after.author.bot or before.content == after.content:
            return
        if not await logging_avanzato_attivo(after.guild.id, self.bot):
            return
        ignorati = await log_ignora_repo.carica(after.guild.id)
        if _scartato(ignorati, after.channel, after, after.channel.id):
            return

        await event_log_repo.log_event(
            after.guild.id,
            "message_edit",
            target_user_id=after.author.id,
            channel_id=after.channel.id,
            details={"message_id": after.id},
        )
        embed = discord.Embed(
            title="✏️ Messaggio modificato",
            description=f"[Vai al messaggio]({after.jump_url})",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Autore", value=f"{after.author.mention} ({after.author.id})", inline=True)
        embed.add_field(name="Canale", value=f"<#{after.channel.id}>", inline=True)
        embed.add_field(
            name="Prima", value=tronca(senza_accento_grave(before.content), CAMPO_MAX) or "*(vuoto)*", inline=False
        )
        embed.add_field(
            name="Dopo", value=tronca(senza_accento_grave(after.content), CAMPO_MAX) or "*(vuoto)*", inline=False
        )
        await self._scrivi(after.guild, embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MessageLogsCog(bot))
