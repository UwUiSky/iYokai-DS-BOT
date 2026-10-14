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

import asyncio
import logging

import discord

from core.bounded_cache import BoundedCache
from core.repositories.output_channel_repo import output_channel_repo

logger = logging.getLogger("iyokai.channel_router")

SETTING_LOG_CHANNEL = "log_channel_id"

TIPO_EVENTI = "eventi"
TIPO_MESSAGGI = "messaggi"
TIPO_VOCE = "voce"
TIPO_SERVER = "server"
TIPI_LOG = (TIPO_EVENTI, TIPO_MESSAGGI, TIPO_VOCE, TIPO_SERVER)
# Tipi di uscita che non sono log: non entrano in TIPI_LOG, quindi /log setup
# non crea canali per loro. Si scelgono dal comando della funzione che li usa.
TIPO_ALLARMI = "allarmi"  # allarmi dell'anti-nuke (#59 3.18)
TIPO_PHISHING = "phishing"  # log del filtro phishing (SIC-043)
TIPO_AI = "ai"  # segnalazioni dell'AI allo staff (§25.37)

DESCRIZIONE_TIPO = {
    TIPO_EVENTI: "Eventi dei membri e dei ruoli",
    TIPO_MESSAGGI: "Messaggi cancellati e modificati",
    TIPO_VOCE: "Entrate e uscite dai vocali",
    TIPO_SERVER: "Canali, inviti, webhook, emoji e impostazioni del server",
    TIPO_ALLARMI: "Allarmi dell'anti-nuke",
    TIPO_PHISHING: "Link di phishing cancellati",
    TIPO_AI: "Messaggi segnalati dall'AI allo staff",
}
NOME_POST = {
    TIPO_EVENTI: "Log eventi",
    TIPO_MESSAGGI: "Log messaggi",
    TIPO_VOCE: "Log voce",
    TIPO_SERVER: "Log server",
    TIPO_ALLARMI: "Allarmi anti-nuke",
    TIPO_PHISHING: "Log phishing",
    TIPO_AI: "Segnalazioni AI",
}

# LIM-38: dal 16/11/2026 Discord mostra così i canali che il bot non vede.
NOME_CANALE_NASCOSTO = "___hidden___"

# (guild_id, tipo) con l'avviso già mandato: evita una query a ogni invio.
_avvisati: set[tuple[int, str]] = set()
# (guild_id, tipo) con un avviso in corso: due eventi insieme non mandano due DM.
_avvisando: set[tuple[int, str]] = set()
# Un blocco per (server, tipo): due invii insieme in un forum creano un solo post.
_blocchi: BoundedCache[tuple[int, str], asyncio.Lock] = BoundedCache(10_000)
_post_noti: BoundedCache[tuple[int, str], discord.Thread] = BoundedCache(10_000)


def _blocco(chiave: tuple[int, str]) -> asyncio.Lock:
    blocco = _blocchi.get(chiave)
    if blocco is None:
        blocco = asyncio.Lock()
        _blocchi.set(chiave, blocco)
    return blocco


def canale_nascosto(canale) -> bool:
    return getattr(canale, "name", None) == NOME_CANALE_NASCOSTO


def _riarma_file(kw: dict) -> None:
    """Un discord.File già letto da un invio fallito va riavvolto prima di riusarlo."""
    for file in [kw.get("file"), *(kw.get("files") or [])]:
        if file is not None:
            file.reset()


class PostForum:
    """Un forum visto come destinazione: ha `send`, il post si crea al primo invio."""

    def __init__(self, forum: discord.ForumChannel, tipo: str, post_id: int | None) -> None:
        self.forum = forum
        self.tipo = tipo
        self.post_id = post_id
        self.id = forum.id
        self.guild = forum.guild

    async def _trova_post(self):
        """Il post del tipo, anche se archiviato (non è in cache): None se non c'è più."""
        chiave = (self.guild.id, self.tipo)
        noto = _post_noti.get(chiave)
        if noto is not None:
            if getattr(noto, "parent_id", None) == self.forum.id:
                return noto
            _post_noti.delete(chiave)  # il tipo ora scrive in un altro forum
        riga = await output_channel_repo.ottieni(self.guild.id, self.tipo)
        post_id = riga.post_id if riga and riga.channel_id == self.forum.id else None
        if post_id is None:
            return None
        post = self.guild.get_thread(post_id)
        if post is None:
            try:
                post = await self.guild.fetch_channel(post_id)
            except discord.HTTPException:
                return None
        return post

    async def send(self, **kw):
        chiave = (self.guild.id, self.tipo)
        async with _blocco(chiave):
            post = await self._trova_post()
            if post is not None:
                try:
                    inviato = await post.send(**kw)
                    _post_noti.set(chiave, post)
                    return inviato
                except discord.NotFound:
                    _post_noti.delete(chiave)
                    _riarma_file(kw)
            creato = await self.forum.create_thread(name=NOME_POST[self.tipo], **kw)
            self.post_id = creato.thread.id
            _post_noti.set(chiave, creato.thread)
            await output_channel_repo.salva_post(
                self.guild.id, self.tipo, self.forum.id, self.post_id
            )
            return creato.message


async def avvisa_proprietario(guild: discord.Guild, tipo: str, channel_id: int, motivo: str) -> None:
    """
    Un solo DM per (server, tipo, canale) finché l'invio non torna a funzionare.
    L'avviso si ricorda solo dopo che il DM è partito (o che i DM sono chiusi).
    """
    chiave = (guild.id, tipo)
    if chiave in _avvisando:
        return
    _avvisando.add(chiave)
    try:
        riga = await output_channel_repo.ottieni(guild.id, tipo)
        if riga is not None and riga.avvisato and riga.channel_id == channel_id:
            _avvisati.add(chiave)
            return
        proprietario = guild.get_member(guild.owner_id)
        if proprietario is None:
            return  # non in memoria adesso: si riprova al prossimo evento
        try:
            await proprietario.send(
                f"Non riesco a scrivere i log «{DESCRIZIONE_TIPO.get(tipo, tipo)}» "
                f"in <#{channel_id}> su **{guild.name}**: {motivo}. "
                f"Controlla i permessi o scegli un altro canale con /log canale. "
                f"Questo avviso non si ripete finché il problema resta."
            )
        except discord.Forbidden:
            logger.info("DM di avviso log non consegnato, DM chiusi (server %s)", guild.id)
        except discord.HTTPException:
            logger.info("DM di avviso log non consegnato (server %s)", guild.id)
            return
        await output_channel_repo.segna_avvisato(guild.id, tipo, channel_id)
        _avvisati.add(chiave)
    finally:
        _avvisando.discard(chiave)


async def destinazione(guild: discord.Guild, tipo: str, predefinito_id: int | None = None):
    """
    Canale (TextChannel o PostForum) dove scrivere il log `tipo`, oppure None.
    Prima la scelta esplicita fatta per quel tipo, poi il canale generale dei
    log. Le righe nate dal ripiego (post, avviso) valgono solo per il canale
    a cui si riferiscono.
    """
    riga = await output_channel_repo.ottieni(guild.id, tipo)
    if riga is not None and riga.esplicito:
        channel_id = riga.channel_id
    else:
        channel_id = predefinito_id
    if channel_id is None:
        return None
    if riga is not None and riga.channel_id != channel_id:
        riga = None  # riga di un canale che non è più quello in uso
    if riga is not None and riga.avvisato:
        _avvisati.add((guild.id, tipo))
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
