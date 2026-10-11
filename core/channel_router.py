"""
core/channel_router.py
======================
Un solo punto che decide dove scrive il bot: per ogni tipo di log un
canale di testo oppure un forum (nel forum, un post per tipo, D3).
Se il canale sparisce o il bot perde il permesso, il proprietario del
server riceve un solo avviso (si riarma al primo invio riuscito).
Funzioni coperte: SPEC §18 (NF-01), §8.17
Dipende da: core/repositories/output_channel_repo.py
"""

from __future__ import annotations

import logging

import discord

from core.repositories.output_channel_repo import output_channel_repo

logger = logging.getLogger("iyokai.channel_router")

SETTING_LOG_CHANNEL = "log_channel_id"

TIPO_EVENTI = "eventi"
TIPO_MESSAGGI = "messaggi"
TIPO_VOCE = "voce"
TIPO_SERVER = "server"
TIPI_LOG = (TIPO_EVENTI, TIPO_MESSAGGI, TIPO_VOCE, TIPO_SERVER)

DESCRIZIONE_TIPO = {
    TIPO_EVENTI: "Eventi dei membri e dei ruoli",
    TIPO_MESSAGGI: "Messaggi cancellati e modificati",
    TIPO_VOCE: "Entrate e uscite dai vocali",
    TIPO_SERVER: "Canali, inviti, webhook, emoji e impostazioni del server",
}
NOME_POST = {
    TIPO_EVENTI: "Log eventi",
    TIPO_MESSAGGI: "Log messaggi",
    TIPO_VOCE: "Log voce",
    TIPO_SERVER: "Log server",
}

# LIM-38: dal 16/11/2026 Discord mostra così i canali che il bot non vede.
NOME_CANALE_NASCOSTO = "___hidden___"

# (guild_id, tipo) con l'avviso già mandato: evita una query a ogni invio.
_avvisati: set[tuple[int, str]] = set()


def canale_nascosto(canale) -> bool:
    return getattr(canale, "name", None) == NOME_CANALE_NASCOSTO


class PostForum:
    """Un forum visto come destinazione: ha `send`, il post si crea al primo invio."""

    def __init__(self, forum: discord.ForumChannel, tipo: str, post_id: int | None) -> None:
        self.forum = forum
        self.tipo = tipo
        self.post_id = post_id
        self.id = forum.id
        self.guild = forum.guild

    async def send(self, **kw):
        post = self.guild.get_thread(self.post_id) if self.post_id else None
        if post is not None:
            try:
                return await post.send(**kw)
            except discord.NotFound:
                pass  # post cancellato a mano: ne nasce uno nuovo
        creato = await self.forum.create_thread(name=NOME_POST[self.tipo], **kw)
        self.post_id = creato.thread.id
        await output_channel_repo.salva_post(
            self.guild.id, self.tipo, self.forum.id, self.post_id
        )
        return creato.message


async def avvisa_proprietario(guild: discord.Guild, tipo: str, channel_id: int, motivo: str) -> None:
    """Un solo avviso per (server, tipo) finché l'invio non torna a funzionare."""
    if not await output_channel_repo.segna_avvisato(guild.id, tipo, channel_id):
        _avvisati.add((guild.id, tipo))
        return
    _avvisati.add((guild.id, tipo))
    proprietario = guild.get_member(guild.owner_id)
    if proprietario is None:
        return
    try:
        await proprietario.send(
            f"Non riesco a scrivere i log «{DESCRIZIONE_TIPO.get(tipo, tipo)}» "
            f"in <#{channel_id}> su **{guild.name}**: {motivo}. "
            f"Controlla i permessi o scegli un altro canale con /log canale. "
            f"Questo avviso non si ripete finché il problema resta."
        )
    except discord.HTTPException:
        logger.info("DM di avviso log non consegnato (server %s)", guild.id)


async def destinazione(guild: discord.Guild, tipo: str, predefinito_id: int | None = None):
    """
    Canale (TextChannel o PostForum) dove scrivere il log `tipo`, oppure None.
    Prima la scelta fatta per quel tipo, poi il canale generale dei log.
    """
    riga = await output_channel_repo.ottieni(guild.id, tipo)
    if riga is not None and riga.avvisato:
        _avvisati.add((guild.id, tipo))
    channel_id = riga.channel_id if riga else predefinito_id
    if channel_id is None:
        return None
    canale = guild.get_channel(channel_id)
    if canale is None:
        await avvisa_proprietario(guild, tipo, channel_id, "il canale non esiste più")
        return None
    if canale_nascosto(canale):
        return None
    if isinstance(canale, discord.ForumChannel):
        return PostForum(canale, tipo, riga.post_id if riga else None)
    if isinstance(canale, discord.TextChannel):
        return canale
    return None


async def invia_a(dest, guild: discord.Guild, tipo: str, **kw) -> bool:
    """Scrive nella destinazione. Mai solleva: l'evento è già nel database."""
    try:
        await dest.send(**kw)
    except (discord.Forbidden, discord.NotFound) as errore:
        await avvisa_proprietario(guild, tipo, dest.id, "mi manca il permesso o il canale non c'è più")
        logger.warning("Log %s non inviato nel canale %s (server %s): %s", tipo, dest.id, guild.id, errore)
        return False
    except discord.HTTPException as errore:
        logger.warning("Log %s non inviato nel canale %s (server %s): %s", tipo, dest.id, guild.id, errore)
        return False
    if (guild.id, tipo) in _avvisati:
        _avvisati.discard((guild.id, tipo))
        await output_channel_repo.azzera_avviso(guild.id, tipo)
    return True
