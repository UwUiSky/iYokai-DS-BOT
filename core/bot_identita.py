"""
core/bot_identita.py
====================
Identità dei bot secondari in un server (MUS-090, D111): per ognuno (Mod, Creator, NSFW, App) il server sceglie se tenere
nickname e logo originali o metterne di suoi. Si cambia il PROFILO DEL BOT NEL SERVER (nickname del server e avatar del
server: `Member.edit`, cioè PATCH /guilds/{id}/members/@me), mai il nome vero del bot. I bot musicali sono esclusi: restano
«iYokai Music» con il loro logo e ai comandi risponde sempre il bot principale. Punto unico (D16) per il comando e per il
pannello. Il logo passa dai controlli delle immagini di D74 (byte, peso, sandbox) e si carica solo la copia ricodificata.
Funzioni coperte: SPEC §23 (MUS-090, D111), catalogo #126
Dipende da: core/immagini_pipeline.py, core/web_panel_logic.py
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import discord

from core.web_panel_logic import LimiteFrequenza

logger = logging.getLogger("iyokai.identita_bot")

MAX_NICK = 32
MAX_LOGO = 8 * 1024 * 1024
BOT_SCELTI = ("mod", "creator", "nsfw", "app")  # i soli bot di cui il server sceglie l'identità
BOT_ESCLUSI = ("musica", "music", "worker")  # D111: tutti «iYokai Music», stesso logo
# Pausa contro i cambi ripetuti: Discord limita già le immagini; qui al massimo 4 cambi ogni 10 minuti per server e bot.
_limite_cambi = LimiteFrequenza(4, 600)

_clients: dict[str, discord.Client] = {}


class _Manca:
    def __repr__(self) -> str:
        return "MANCA"


MANCA = _Manca()  # il campo non si tocca (None lo riporta all'originale)


@dataclass(frozen=True)
class StatoIdentita:
    chiave: str
    presente: bool
    nick: str | None = None
    logo: str | None = None  # indirizzo dell'avatar del server, se c'è

    @property
    def personalizzato(self) -> bool:
        return bool(self.nick or self.logo)


def registra(chiave: str, client: discord.Client | None) -> None:
    """Collega un bot secondario (None lo scollega). I bot musicali non si registrano mai. Lo chiama solo main.py."""
    if chiave in BOT_ESCLUSI:
        raise ValueError("I bot musicali non hanno un'identità scelta dal server.")
    if chiave not in BOT_SCELTI:
        raise ValueError(f"Bot sconosciuto: {chiave}")
    if client is None:
        _clients.pop(chiave, None)
    else:
        _clients[chiave] = client


def _server_del_bot(chiave: str, guild_id: int) -> discord.Guild | None:
    client = _clients.get(chiave)
    if client is None or client.is_closed():
        return None
    return client.get_guild(guild_id)


def stati(guild_id: int) -> list[StatoIdentita]:
    """I bot secondari presenti e collegati in questo server, con il profilo che hanno ora."""
    risultato = []
    for chiave in BOT_SCELTI:
        guild = _server_del_bot(chiave, guild_id)
        me = getattr(guild, "me", None) if guild is not None else None
        if me is None:
            continue
        logo = getattr(me, "guild_avatar", None)
        risultato.append(StatoIdentita(chiave, True, getattr(me, "nick", None), logo.url if logo else None))
    return risultato


def puo_gestire(utente) -> bool:
    """Solo chi può gestire il server (riletto a ogni richiesta)."""
    permessi = getattr(utente, "guild_permissions", None)
    return bool(permessi and (permessi.manage_guild or permessi.administrator))


async def _logo_sicuro(dati: bytes, guild_id: int) -> bytes:
    """La copia ricodificata del logo (D74). Solleva ValueError con la chiave del messaggio se non va."""
    from core.immagini_pipeline import PULITA, analizza_immagine

    if len(dati) > MAX_LOGO:
        raise ValueError("idn_logo_grande")
    esito = await analizza_immagine(dati, "logo", None, guild_id)
    if esito.verdetto != PULITA or esito.non_analizzata is not None or not esito.png:
        raise ValueError("idn_logo_non_valido")
    return esito.png


def _nick(valore: str | None) -> str | None:
    valore = (valore or "").strip()
    if len(valore) > MAX_NICK:
        raise ValueError("idn_nick_lungo")
    return valore or None


async def applica_identita(
    utente, guild_id: int, chiave: str, *, nick=MANCA, logo=MANCA
) -> str:
    """
    Cambia nickname e logo di un bot secondario nel server. Ogni campo: MANCA = non si tocca, None = torna all'originale,
    testo o byte = il valore nuovo. Restituisce la chiave del messaggio per l'utente. Non solleva.
    """
    if chiave in BOT_ESCLUSI:
        return "idn_musica_esclusa"
    if chiave not in BOT_SCELTI:
        return "idn_bot_sconosciuto"
    if not puo_gestire(utente):
        return "idn_permesso_utente"
    if nick is MANCA and logo is MANCA:
        return "idn_niente"
    guild = _server_del_bot(chiave, guild_id)
    if guild is None or getattr(guild, "me", None) is None:
        return "idn_bot_assente"
    campi: dict = {}
    try:
        if nick is not MANCA:
            campi["nick"] = _nick(nick)
        if logo is not MANCA:
            campi["avatar"] = None if logo is None else await _logo_sicuro(logo, guild_id)
    except ValueError as exc:
        return str(exc)
    except Exception:  # noqa: BLE001 - un'immagine strana o la sandbox ferma: si rifiuta, non si carica l'originale
        logger.warning("Controllo del logo non riuscito per il server %s.", guild_id, exc_info=True)
        return "idn_logo_non_valido"
    tornano_originali = all(v is None for v in campi.values())  # tornare all'originale non si blocca mai
    if not tornano_originali and not _limite_cambi.consenti(f"{guild_id}:{chiave}"):
        return "idn_attendi"
    try:
        await guild.me.edit(**campi, reason=f"Identità del bot, richiesta da {getattr(utente, 'id', 0)}")
    except discord.Forbidden:
        return "idn_permesso_bot" if "nick" in campi else "idn_errore"
    except discord.HTTPException as exc:
        logger.info("Discord ha rifiutato l'identità del bot %s nel server %s (%s).", chiave, guild_id, exc.status)
        return "idn_errore"
    logger.info("Identità del bot %s cambiata nel server %s: %s.", chiave, guild_id, ", ".join(sorted(campi)))
    return "idn_ok" if not tornano_originali else "idn_ripristinato"


async def ripristina_originale(utente, guild_id: int, chiave: str) -> str:
    """Nickname e logo originali del bot (sempre possibile a chi gestisce il server)."""
    return await applica_identita(utente, guild_id, chiave, nick=None, logo=None)
