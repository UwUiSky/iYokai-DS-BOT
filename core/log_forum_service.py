"""
core/log_forum_service.py
=========================
La vista dei log su un forum: ogni evento con un canale va nel post di quel
canale, ogni caso di moderazione nel suo post. Gli eventi aspettano in una coda
e un solo lavoratore li scrive piano (i forum hanno limiti stretti). Se il server
non ha scelto un forum non succede niente e non costa una query oltre la cache.
Gli eventi spenti con `/log eventi` non vanno neanche nel forum.
Un post chiuso si riapre; un forum con tag obbligatori riceve un tag ammesso; dopo un errore la vista di quel forum si ferma per un po'.
Funzioni coperte: SPEC §8.17
Dipende da: core/repositories/log_forum_repo.py, core/log_forum_logic.py
"""

from __future__ import annotations

import asyncio
import logging
import time

import discord

from core.bot_ready import attendi_bot_pronto
from core.bounded_cache import BoundedCache
from core.log_forum_logic import (
    CODA_MAX,
    DIM_CANALI,
    DIM_CASI,
    MAX_POST_PER_DIMENSIONE,
    descrizione_caso,
    PAUSA_DOPO_ERRORE_SECONDI,
    descrizione_evento,
    scegli_tag,
    titolo_post,
)
from core.repositories.log_eventi_repo import log_eventi_repo
from core.repositories.log_forum_repo import LogForumRepository

logger = logging.getLogger("iyokai.log_forum")

CACHE_SECONDI = 60.0
PAUSA_SECONDI = 1.0
PERMESSI_FORUM = (
    "view_channel", "send_messages", "embed_links", "read_message_history",
    "create_public_threads", "send_messages_in_threads",
)


def _pool():
    from core.database import db

    return db.pool


log_forum_repo = LogForumRepository(pool_provider=_pool)

_bot: discord.Client | None = None
_coda: asyncio.Queue | None = None
_lavoratore: asyncio.Task | None = None
_viste: BoundedCache[int, tuple[float, dict[str, int]]] = BoundedCache(5000)
_sospese: BoundedCache[tuple[int, str], float] = BoundedCache(5000)  # (server, vista) -> fino a quando (monotonic)


def avvia(bot: discord.Client) -> None:
    """Accende la vista: da qui in poi gli eventi dei server che l'hanno scelta vanno nel forum."""
    global _bot, _coda, _lavoratore
    if _lavoratore is not None:
        _lavoratore.cancel()  # un solo lavoratore: un secondo avvio sostituisce il primo
    _bot = bot
    _coda = asyncio.Queue(maxsize=CODA_MAX)
    _lavoratore = asyncio.create_task(_lavora())


async def ferma() -> None:
    global _bot, _coda, _lavoratore
    if _lavoratore is not None:
        _lavoratore.cancel()
        try:
            await _lavoratore
        except asyncio.CancelledError:
            pass
    _bot, _coda, _lavoratore = None, None, None
    _viste.clear()


def invalida(guild_id: int) -> None:
    """Dopo `/log vista-forum`: la scelta nuova vale subito."""
    _viste.delete(guild_id)


async def _forum_scelti(guild_id: int) -> dict[str, int]:
    visto = _viste.get(guild_id)
    if visto is not None and time.monotonic() - visto[0] < CACHE_SECONDI:
        return visto[1]
    scelti = await log_forum_repo.forum_del_server(guild_id)
    _viste.set(guild_id, (time.monotonic(), scelti))
    return scelti


def _accoda(guild_id: int, dimensione: str, chiave: int, testo: str) -> None:
    if _coda is None:
        return
    try:
        _coda.put_nowait((guild_id, dimensione, chiave, testo))
    except asyncio.QueueFull:
        logger.warning("Coda della vista forum piena: evento del server %s non proiettato.", guild_id)


async def notifica_evento(
    guild_id: int,
    event_type: str,
    *,
    actor_id: int | None = None,
    target_user_id: int | None = None,
    channel_id: int | None = None,
    role_id: int | None = None,
    case_number: int | None = None,
    details: dict | None = None,
) -> None:
    """Chiamata dal registro degli eventi dopo ogni scrittura. Non solleva mai."""
    if _bot is None:
        return
    try:
        scelti = await _forum_scelti(guild_id)
        if not scelti or not await log_eventi_repo.evento_acceso(guild_id, event_type):
            return  # evento spento con `/log eventi`: il server non lo vuole, neanche nel forum
        testo = descrizione_evento(
            event_type, actor_id=actor_id, target_user_id=target_user_id, role_id=role_id,
            case_number=case_number, details=details,
        )
        if channel_id and DIM_CANALI in scelti:
            _accoda(guild_id, DIM_CANALI, channel_id, testo)
        if case_number and DIM_CASI in scelti:
            _accoda(guild_id, DIM_CASI, case_number, testo)
    except Exception:
        logger.warning("Vista forum: evento non proiettato (server %s)", guild_id, exc_info=True)


async def notifica_caso(
    guild_id: int,
    case_number: int,
    azione: str,
    *,
    user_id: int,
    moderator_id: int,
    motivo: str | None = None,
    revocato_da: int | None = None,
) -> None:
    """Chiamata dal registro dei casi: l'apertura o la revoca va nel post del caso."""
    if _bot is None:
        return
    try:
        if DIM_CASI not in await _forum_scelti(guild_id):
            return
        _accoda(
            guild_id, DIM_CASI, case_number,
            descrizione_caso(
                case_number, azione, user_id=user_id, moderator_id=moderator_id,
                motivo=motivo, revocato_da=revocato_da,
            ),
        )
    except Exception:
        logger.warning("Vista forum: caso non proiettato (server %s)", guild_id, exc_info=True)


async def _lavora() -> None:
    await attendi_bot_pronto(_bot)
    while True:
        guild_id, dimensione, chiave, testo = await _coda.get()
        try:
            await scrivi(guild_id, dimensione, chiave, testo)
        except Exception:
            logger.warning("Vista forum: scrittura non riuscita (server %s)", guild_id, exc_info=True)
        await asyncio.sleep(PAUSA_SECONDI)


async def _trova_post(guild: discord.Guild, thread_id: int):
    post = guild.get_thread(thread_id)
    if post is not None:
        return post
    try:
        return await guild.fetch_channel(thread_id)
    except discord.HTTPException:
        return None


def _sospesa(guild_id: int, dimensione: str) -> bool:
    fino_a = _sospese.get((guild_id, dimensione))
    return fino_a is not None and time.monotonic() < fino_a


def _sospendi(guild_id: int, dimensione: str, motivo: object) -> None:
    """Ferma la vista di questo forum per un po' e lo scrive una volta sola nei log."""
    if not _sospesa(guild_id, dimensione):
        logger.warning(
            "Vista forum sospesa %d minuti (server %s, vista %s): %s",
            PAUSA_DOPO_ERRORE_SECONDI // 60, guild_id, dimensione, motivo,
        )
    _sospese.set((guild_id, dimensione), time.monotonic() + PAUSA_DOPO_ERRORE_SECONDI)


async def _scrivi_nel_post(post, embed: discord.Embed) -> bool:
    """
    Scrive in un post che c'è già. Un post chiuso (archiviato o bloccato) si riapre; se non si riesce
    a riaprirlo o a scriverci, False e il chiamante lo dimentica. NotFound: il post non c'è più.
    """
    try:
        if getattr(post, "archived", False) or getattr(post, "locked", False):
            await post.edit(archived=False, locked=False)
        await post.send(embed=embed)
        return True
    except discord.NotFound:
        return False
    except discord.HTTPException:
        pass
    try:  # un solo secondo tentativo, dopo aver riaperto il post
        await post.edit(archived=False, locked=False)
        await post.send(embed=embed)
        return True
    except discord.HTTPException:
        return False


async def scrivi(guild_id: int, dimensione: str, chiave: int, testo: str) -> bool:
    """Scrive nel post della chiave (lo crea se serve). True se il testo è arrivato."""
    guild = _bot.get_guild(guild_id) if _bot is not None else None
    if guild is None or _sospesa(guild_id, dimensione):
        return False
    forum_id = (await _forum_scelti(guild_id)).get(dimensione)
    forum = guild.get_channel(forum_id) if forum_id else None
    if not isinstance(forum, discord.ForumChannel):
        return False
    embed = discord.Embed(description=testo, color=discord.Color.blurple())
    thread_id = await log_forum_repo.post_di(guild_id, dimensione, chiave)
    if thread_id is not None:
        post = await _trova_post(guild, thread_id)
        if post is not None and getattr(post, "parent_id", None) == forum.id:
            if await _scrivi_nel_post(post, embed):
                return True
        await log_forum_repo.dimentica_post(guild_id, dimensione, chiave)  # il post non c'è più o non si apre
    if await log_forum_repo.conta_post(guild_id, dimensione) >= MAX_POST_PER_DIMENSIONE:
        return False
    nome = getattr(guild.get_channel(chiave), "name", None) if dimensione == DIM_CANALI else None
    argomenti = {"name": titolo_post(dimensione, chiave, nome), "embed": embed}
    if forum.flags.require_tag:
        tag = scegli_tag(forum.available_tags)
        if tag is None:
            _sospendi(guild_id, dimensione, "il forum vuole un tag ma non ne ha")
            return False
        argomenti["applied_tags"] = [tag]
    try:
        creato = await forum.create_thread(**argomenti)
    except discord.HTTPException as errore:
        _sospendi(guild_id, dimensione, errore)
        return False
    await log_forum_repo.salva_post(guild_id, dimensione, chiave, creato.thread.id)
    return True
