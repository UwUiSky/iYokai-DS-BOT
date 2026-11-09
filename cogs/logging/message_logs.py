"""
cogs/logging/message_logs.py
============================
Log dei messaggi cancellati, modificati e cancellati in blocco, e degli
inviti Discord scritti nei messaggi. Scrive nella destinazione «messaggi»
del router (canale di testo o forum) e, per ogni evento, una riga nel log
eventi senza il testo. Serve il Message Content Intent; un messaggio
uscito dalla memoria di discord.py si segnala senza contenuto. I messaggi
cancellati restano in memoria un'ora per l'archivio di un canale, solo se
l'evento «messaggi cancellati» è acceso. Le immagini dei messaggi si copiano
senza aprirle (`core/allegati_sicuri.py`, D61): nel log del cancellato vanno i link di
download firmati e al massimo 3 anteprime PNG ricodificate, mai l'originale. Fa parte
del Logging Avanzato. Ogni evento si può spegnere (LOG-017).
Funzioni coperte: SPEC §8.16 (NF-02), §8.18 (LOG-005, LOG-027), D61 (#152)
Dipende da: core/channel_router.py, core/repositories/log_ignora_repo.py,
core/repositories/log_eventi_repo.py
"""

from __future__ import annotations

import io
import logging

import discord
from discord.ext import commands, tasks

from cogs.logging.advanced_logs import logging_avanzato_attivo
from core import allegati_sicuri
from core import channel_router as router
from core.config import config
from core.channel_router import SETTING_LOG_CHANNEL, TIPO_MESSAGGI
from core.database import db
from core.immagini_byte_logic import tipo_atteso
from core.message_log_logic import (
    cancellati_recenti,
    MessaggioArchiviato,
    da_ignorare,
    file_blocco,
    riepilogo_blocco,
    senza_accento_grave,
    testo_allegati,
)
from core.repositories.event_log_repo import event_log_repo
from core.phishing_logic import codici_invito
from core.repositories.log_eventi_repo import log_eventi_repo
from core.repositories.log_ignora_repo import log_ignora_repo
from core.testo_limiti import CAMPO_MAX, DESCRIZIONE_MAX, tronca

logger = logging.getLogger("iyokai.logging.messaggi")

def archiviato(m: discord.Message) -> MessaggioArchiviato:
    allegati = testo_allegati([a.filename for a in m.attachments])
    return MessaggioArchiviato(
        message_id=m.id,
        author_id=m.author.id,
        author_nome=str(m.author),
        testo=m.content + (f" 📎 {allegati}" if allegati else ""),
        quando=m.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    )


def _scartato(ignorati, canale, message: discord.Message | None, channel_id: int) -> bool:
    """Canale, utente, ruolo, prefisso ed espressione ignorati; messaggi dei bot."""
    if message is not None and message.author.bot:
        return True
    return da_ignorare(
        ignorati,
        channel_id=channel_id,
        author_id=message.author.id if message is not None else None,
        testo=message.content if message is not None else None,
        category_id=getattr(canale, "category_id", None),
        thread_parent_id=getattr(canale, "parent_id", None),
        ruoli_autore=[r.id for r in getattr(message.author, "roles", [])] if message is not None else (),
    )


MAX_ANTEPRIME_LOG = 3
MAX_BYTE_ANTEPRIME_LOG = 8 * 1024 * 1024  # LIM-55: un invio non supera i 10 MiB


def e_immagine_dichiarata(a: discord.Attachment) -> bool:
    """Solo gli allegati che dicono di essere immagini si copiano; il tipo vero lo decidono i byte."""
    return tipo_atteso(a.filename, getattr(a, "content_type", None)) is not None


async def copie_per_il_log(guild_id: int, message_id: int) -> tuple[str, list[discord.File]]:
    """
    D61/D62: le copie salvate di un messaggio per il log: elenco con link firmati (se il sotto-dominio e'
    configurato) e al massimo 3 anteprime PNG ricodificate. Mai l'originale nel canale. Non solleva.
    """
    try:
        copie = await allegati_sicuri.del_messaggio(guild_id, message_id)
    except Exception:  # noqa: BLE001 - il log del messaggio esce comunque
        logger.warning("Copie degli allegati non lette", exc_info=True)
        return "", []
    righe, file, peso = [], [], 0
    for c in copie:
        nome = senza_accento_grave(c.nome_file)
        if c.stato == allegati_sicuri.STATO_BLOCCATA:
            righe.append(f"`{nome}`: immagine con contenuto sospetto, non conservata")
            continue
        link = allegati_sicuri.url_download(config.WEB_ALLEGATI_PUBLIC_URL, config.WEB_PANEL_SECRET_KEY, c.id)
        righe.append(f"`{nome}` ({c.dimensione // 1024} KiB)" + (f" [scarica]({link})" if link else ""))
        if c.anteprima and len(file) < MAX_ANTEPRIME_LOG:
            letta = await allegati_sicuri.leggi(c.id, anteprima=True)
            if letta is not None and peso + len(letta[1]) <= MAX_BYTE_ANTEPRIME_LOG:
                peso += len(letta[1])
                file.append(discord.File(io.BytesIO(letta[1]), filename=f"anteprima-{c.id}.png"))
    return "\n".join(righe), file


class MessageLogsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._pulizia = tasks.loop(hours=1)(self._giro_pulizia)

    async def cog_load(self) -> None:
        self._pulizia.start()

    async def cog_unload(self) -> None:
        self._pulizia.cancel()

    async def _giro_pulizia(self) -> None:
        try:
            tolti = await allegati_sicuri.pulisci()
            if tolti:
                logger.info("Copie degli allegati: %d file tolti", tolti)
        except Exception:  # noqa: BLE001
            logger.warning("Pulizia delle copie degli allegati non riuscita", exc_info=True)

    @commands.Cog.listener("on_message")
    async def copia_allegati(self, message: discord.Message) -> None:
        """D61: le immagini dei messaggi si copiano (byte intatti) per il log del messaggio cancellato."""
        guild = message.guild
        if guild is None or message.author.bot or not message.attachments:
            return
        scelti = [a for a in message.attachments if e_immagine_dichiarata(a) and a.size <= allegati_sicuri.MAX_BYTE]
        if not scelti:
            return
        try:
            if not await logging_avanzato_attivo(guild.id, self.bot):
                return
            if not await log_eventi_repo.evento_acceso(guild.id, "message_delete"):
                return
            ignorati = await log_ignora_repo.carica(guild.id)
            if _scartato(ignorati, message.channel, message, message.channel.id):
                return
            for a in scelti[: allegati_sicuri.MAX_PER_MESSAGGIO]:
                await allegati_sicuri.salva(
                    guild.id, message.channel.id, message.id, message.author.id, "log_messaggi", a.filename,
                    await a.read(), content_type=a.content_type,
                )
        except Exception:  # noqa: BLE001 - il log delle copie non deve mai rompere altro
            logger.warning("Copia degli allegati non riuscita", exc_info=True)

    async def _scrivi(self, guild: discord.Guild, evento: str, **contenuto) -> None:
        if not await log_eventi_repo.evento_acceso(guild.id, evento):
            return
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

        # LOG-027: in memoria solo se l'evento è acceso (spento = il server non li vuole).
        if messaggio is not None and await log_eventi_repo.evento_acceso(guild.id, "message_delete"):
            cancellati_recenti.aggiungi(payload.channel_id, archiviato(messaggio))
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
        testo_copie, anteprime = await copie_per_il_log(guild.id, payload.message_id)
        contenuto: dict = {"embed": embed}
        if testo_copie:
            embed.add_field(name="Copie salvate", value=tronca(testo_copie, CAMPO_MAX), inline=False)
        if anteprime:
            embed.set_image(url=f"attachment://{anteprime[0].filename}")
            contenuto["files"] = anteprime
        await self._scrivi(guild, "message_delete", **contenuto)

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
            archiviato(m) for m in payload.cached_messages if not _scartato(ignorati, canale, m, payload.channel_id)
        ]
        if await log_eventi_repo.evento_acceso(guild.id, "message_bulk_delete"):
            for m in archiviati:
                cancellati_recenti.aggiungi(payload.channel_id, m)
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
        await self._scrivi(guild, "message_bulk_delete", **contenuto)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if after.guild is None or after.author.bot or before.content == after.content:
            return
        if not await logging_avanzato_attivo(after.guild.id, self.bot):
            return
        ignorati = await log_ignora_repo.carica(after.guild.id)
        # Il campo "Prima" mostra il testo vecchio: se è lui a dover restare fuori dal log, la modifica non si scrive.
        if _scartato(ignorati, after.channel, after, after.channel.id) or _scartato(
            ignorati, after.channel, before, after.channel.id
        ):
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
        await self._scrivi(after.guild, "message_edit", embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """LOG-005: inviti Discord scritti in un messaggio."""
        if message.guild is None or message.author.bot:
            return
        codici = codici_invito(message.content)
        if not codici:
            return
        if not await logging_avanzato_attivo(message.guild.id, self.bot):
            return
        ignorati = await log_ignora_repo.carica(message.guild.id)
        if _scartato(ignorati, message.channel, message, message.channel.id):
            return
        await event_log_repo.log_event(
            message.guild.id,
            "invite_posted",
            target_user_id=message.author.id,
            channel_id=message.channel.id,
            details={"message_id": message.id, "codici": list(codici)},
        )
        embed = discord.Embed(
            title="🔗 Invito scritto in un messaggio",
            description=f"[Vai al messaggio]({message.jump_url})",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Autore", value=f"{message.author.mention} ({message.author.id})", inline=True)
        embed.add_field(name="Canale", value=f"<#{message.channel.id}>", inline=True)
        embed.add_field(
            name="Inviti", value=tronca(" ".join(f"`discord.gg/{c}`" for c in codici), CAMPO_MAX), inline=False
        )
        await self._scrivi(message.guild, "invite_posted", embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MessageLogsCog(bot))
