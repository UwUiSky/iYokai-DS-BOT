"""
core/account_rubato.py
======================
Difesa dagli account rubati (D67): quando una persona manda immagini malevole o lo stesso messaggio in più
canali o server in poco tempo, il bot (1) manda allo staff UN SOLO avviso riassuntivo per persona, aggiornato
invece di nuovi messaggi, senza allegati né copie delle immagini; (2) la limita subito con il timeout di Discord
e cancella quello che ha mandato; (3) le scrive in privato di mettere al sicuro l'account; il suo messaggio
privato dopo apre il ticket ModMail con lo staff (core/verify_blocchi.py). Nessuna esenzione dello staff (un
account staff rubato è il caso tipico): per lui servono solo più canali; i canali annunci non contano. Opzione per server accesa di base e minuti di timeout (core/account_rubato_opzioni.py).
Funzioni coperte: SPEC §6.20 (D67, #153)
Dipende da: core/account_rubato_logic.py, core/automod_azioni.py, core/verify_blocchi.py
"""

from __future__ import annotations

import asyncio
import logging
import time

import discord

from core import account_rubato_logic as lg
from core import account_rubato_opzioni as opzioni
from core import bot_roles
from core.account_rubato_logic import Sintesi
from core.automod_azioni import Bersaglio, esegui_azioni
from core.automod_regole_logic import azioni_da_json
from core.bounded_cache import BoundedCache
from core.i18n import lingua_risposta, t

logger = logging.getLogger("iyokai.account_rubato")

REGOLA = "account_rubato"
PAUSA_DM_S = 6 * 3600  # un solo messaggio privato per persona, anche se continua a mandare

registro = lg.RegistroInvii()
_avvisi: BoundedCache[tuple[int, int], tuple[int, int]] = BoundedCache(5_000)  # (server, persona) -> (canale, messaggio)
_dm_fatti: BoundedCache[int, float] = BoundedCache(5_000)
_serrature: BoundedCache[int, asyncio.Lock] = BoundedCache(5_000)  # una persona alla volta: lo spam arriva a raffica


def _serratura(user_id: int) -> asyncio.Lock:
    serratura = _serrature.get(user_id)
    if serratura is None:
        serratura = asyncio.Lock()
        _serrature.set(user_id, serratura)
    return serratura


def firma_da_messaggio(message: discord.Message) -> str | None:
    """Impronta del messaggio: testo, allegati (nome e misura) e testo degli inoltri."""
    inoltrati = [getattr(s, "content", "") or "" for s in getattr(message, "message_snapshots", None) or ()]
    allegati = [(a.filename, a.size) for a in getattr(message, "attachments", None) or ()]
    for snapshot in getattr(message, "message_snapshots", None) or ():
        allegati += [(a.filename, a.size) for a in getattr(snapshot, "attachments", None) or ()]
    return lg.firma_messaggio(message.content, allegati, inoltrati)


async def controlla_messaggio(bot: discord.Client, message: discord.Message, *, malevola: bool = False) -> bool:
    """Registra l'invio e, se l'account sembra rubato, agisce. True se ha agito. Bot e webhook non si contano mai."""
    guild = message.guild
    if guild is None or message.author.bot or getattr(message, "webhook_id", None) or not isinstance(message.author, discord.Member):
        return False
    if not malevola and _canale_annunci(message.channel):
        return False  # gli annunci (e i loro crosspost) non sono spam di un account rubato
    firma = firma_da_messaggio(message)
    if firma is None and not malevola:
        return False
    staff = message.channel.permissions_for(message.author).manage_messages
    sintesi = registro.registra(
        message.author.id, guild.id, message.channel.id, message.id, firma or f"msg:{message.id}", time.monotonic(),
        malevola=malevola, min_canali=lg.MIN_CANALI_STAFF if staff else lg.MIN_CANALI_UGUALI,
    )
    if sintesi is None:
        return False
    return await gestisci(bot, sintesi, message)


def _canale_annunci(canale) -> bool:
    """Canale annunci, o un suo thread."""
    tipo = getattr(getattr(canale, "parent", None), "type", None) if isinstance(canale, discord.Thread) else getattr(canale, "type", None)
    return tipo == discord.ChannelType.news


async def gestisci(bot: discord.Client, sintesi: Sintesi, message: discord.Message | None) -> bool:
    """Agisce in ogni server della sintesi, una persona alla volta (un solo avviso e un solo timeout)."""
    async with _serratura(sintesi.user_id):
        return await _gestisci(bot, sintesi, message)


async def _gestisci(bot: discord.Client, sintesi: Sintesi, message: discord.Message | None) -> bool:
    limitato_in: list[discord.Guild] = []
    for guild_id in sintesi.guild_ids:
        guild = bot.get_guild(guild_id)
        if guild is None or not await opzioni.attivo(guild_id):
            continue
        membro = guild.get_member(sintesi.user_id)
        if membro is None:
            continue
        try:
            await _in_server(guild, membro, sintesi, message if message is not None and message.guild.id == guild_id else None)
        except Exception:
            logger.exception("Account rubato: errore nel server %s", guild_id)
            continue
        limitato_in.append(guild)
    if limitato_in and sintesi.prima_volta:
        await _avvisa_la_persona(limitato_in, sintesi)
    return bool(limitato_in)


async def _in_server(guild: discord.Guild, membro: discord.Member, sintesi: Sintesi, corrente: discord.Message | None) -> None:
    lingua = await lingua_risposta(guild.id, pubblica=True)
    motivo = _motivo(sintesi, lingua)
    azioni = []
    if corrente is not None:
        azioni.append({"t": "cancella"})
    if not membro.is_timed_out():
        azioni.append({"t": "timeout", "secondi": await opzioni.timeout_secondi(guild.id, sintesi.malevole)})
    fatte = await esegui_azioni(
        azioni_da_json(azioni),
        Bersaglio(guild=guild, motivo=motivo, regola_chiave=REGOLA, regola_nome=t("arub_titolo", lingua), membro=membro,
                  messaggio=corrente, canale=getattr(corrente, "channel", None), senza_scudo=True),
    )
    cancellati = await _cancella_precedenti(guild, sintesi, corrente.id if corrente is not None else None)
    await _scrivi_avviso(guild, membro, sintesi, lingua, timeout="mute" in fatte or membro.is_timed_out(),
                         cancellati=cancellati or "delete" in fatte)


async def _cancella_precedenti(guild: discord.Guild, sintesi: Sintesi, escluso: int | None) -> bool:
    """Cancella gli altri invii contati in questo server (in blocco per canale quando sono più di uno)."""
    per_canale: dict[int, list[int]] = {}
    for guild_id, canale_id, messaggio_id in sintesi.messaggi:
        if guild_id == guild.id and messaggio_id != escluso:
            per_canale.setdefault(canale_id, []).append(messaggio_id)
    fatto = False
    for canale_id, ids in per_canale.items():
        canale = guild.get_channel_or_thread(canale_id)
        if canale is None:
            continue
        parziali = [canale.get_partial_message(i) for i in ids]
        try:
            if len(parziali) == 1:
                await bot_roles.cancella_messaggio(parziali[0])
            else:
                await bot_roles.cancella_messaggi(canale, parziali)
            fatto = True
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            continue
    return fatto


def _motivo(sintesi: Sintesi, lingua: str) -> str:
    cause = ", ".join(t(f"arub_motivo_{m}", lingua) for m in sintesi.motivi)
    return t("arub_motivo_audit", lingua, cause=cause)[:400]


def _canale_avviso(guild: discord.Guild, canale_log_id: int | None, mod_log_id):
    for candidato in (canale_log_id, mod_log_id):
        canale = guild.get_channel(candidato) if isinstance(candidato, int) else None
        if isinstance(canale, discord.abc.Messageable):
            return canale
    return None


async def _scrivi_avviso(guild: discord.Guild, membro: discord.Member, sintesi: Sintesi, lingua: str, *, timeout: bool,
                         cancellati: bool) -> None:
    """Un solo messaggio per persona e server: se esiste già lo aggiorna. Niente file, solo numeri."""
    from cogs.moderation._shared import SETTING_MOD_LOG_CHANNEL
    from core import immagini_opzioni
    from core.database import db

    canale = _canale_avviso(guild, (await immagini_opzioni.leggi(guild.id)).canale_log_id,
                            await db.get_guild_setting(guild.id, SETTING_MOD_LOG_CHANNEL))
    if canale is None:
        return
    embed = discord.Embed(title=t("arub_titolo", lingua), color=discord.Color.red())
    embed.description = t(
        "arub_riepilogo", lingua, cause=", ".join(t(f"arub_motivo_{m}", lingua) for m in sintesi.motivi),
        invii=sintesi.invii, canali=sintesi.canali, server=sintesi.server,
    )[:1000]
    embed.add_field(name=t("arub_campo_persona", lingua), value=f"{membro.mention} (`{membro.id}`)", inline=True)
    fatto = [t(c, lingua) for c, ok in (("arub_azione_timeout", timeout), ("arub_azione_cancellati", cancellati)) if ok]
    embed.add_field(name=t("arub_campo_azioni", lingua), value=", ".join(fatto) or t("arub_azione_nessuna", lingua), inline=True)
    embed.set_footer(text=t("arub_piede", lingua))
    precedente = _avvisi.get((guild.id, membro.id))
    if precedente is not None and precedente[0] == canale.id:
        try:
            await canale.get_partial_message(precedente[1]).edit(embed=embed)
            return
        except discord.HTTPException:
            pass  # cancellato o non modificabile: ne nasce uno nuovo
    try:
        inviato = await canale.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        logger.info("Avviso account rubato non consegnato nel server %s", guild.id)
        return
    _avvisi.set((guild.id, membro.id), (canale.id, inviato.id))


async def _avvisa_la_persona(server: list[discord.Guild], sintesi: Sintesi) -> None:
    """Il messaggio privato (una volta ogni 6 ore) e il blocco che fa aprire il ticket al suo prossimo messaggio."""
    from cogs.moderation._shared import try_dm
    from core import verify_blocchi

    primo = server[0]
    membro = primo.get_member(sintesi.user_id)
    if membro is None:
        return
    lingua = await lingua_risposta(primo.id, pubblica=True)
    for guild in server:
        await verify_blocchi.registra_limitazione(guild, sintesi.user_id, _motivo(sintesi, lingua))
    adesso = time.monotonic()
    ultimo = _dm_fatti.get(sintesi.user_id)
    if ultimo is not None and adesso - ultimo < PAUSA_DM_S:
        return
    _dm_fatti.set(sintesi.user_id, adesso)
    embed = discord.Embed(title=t("arub_dm_titolo", lingua), description=t("arub_dm", lingua), color=discord.Color.red())
    await try_dm(membro, embed, guild_id=primo.id)
