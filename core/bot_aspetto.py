"""
core/bot_aspetto.py
===================
Aspetto del bot in un solo server (CFG-021, CFG-030, #122): nickname, avatar, banner e descrizione
del profilo del bot in quel server, senza un secondo bot. Discord salva il profilo: niente tabelle.
Punto unico (D16) per `/admin config nickname-bot`, `/admin premium aspetto` e il pannello web.
Funzioni coperte: catalogo #122 (CFG-021, CFG-030)
Dipende da: core/safe_image.py (controllo delle immagini), core/premium.py
"""

from __future__ import annotations

import logging

import discord

from core.safe_image import MAX_IMAGE_BYTES, run_image_task, safe_open_image
from core.web_panel_logic import LimiteFrequenza

logger = logging.getLogger("iyokai.aspetto")

MODULO_ASPETTO = "aspetto"
MAX_NICK = 32
MAX_BIO = 190
MAX_IMMAGINE = MAX_IMAGE_BYTES
FORMATI_PROFILO = frozenset({"PNG", "JPEG", "GIF", "WEBP"})
# Discord limita i cambi di avatar e banner: quattro immagini ogni dieci minuti per server.
_limite_immagini = LimiteFrequenza(4, 600)


class _Manca:
    def __repr__(self) -> str:
        return "MANCA"


MANCA = _Manca()  # il campo non si tocca (None invece lo toglie)


class AspettoRifiutato(ValueError):
    """Un valore non si può usare. `motivo` è la chiave del messaggio per l'utente."""

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


def _testo(valore: str | None, massimo: int) -> str | None:
    valore = (valore or "").strip()
    if len(valore) > massimo:
        raise AspettoRifiutato("asp_testo_lungo")
    return valore or None


def _formato(dati: bytes) -> str | None:
    return safe_open_image(dati).format


async def controlla_immagine(dati: bytes) -> bytes:
    """L'immagine va bene per il profilo (formato, byte e pixel). Altrimenti `AspettoRifiutato`."""
    if len(dati) > MAX_IMMAGINE:
        raise AspettoRifiutato("asp_immagine_grande")
    try:
        formato = await run_image_task(_formato, dati)
    except Exception as exc:  # noqa: BLE001 - file rotto, formato sconosciuto o troppi pixel
        raise AspettoRifiutato("asp_immagine_non_valida") from exc
    if formato not in FORMATI_PROFILO:
        raise AspettoRifiutato("asp_immagine_non_valida")
    return dati


async def applica_aspetto(
    bot, guild: discord.Guild, autore_id: int, *, nick=MANCA, avatar=MANCA, banner=MANCA, bio=MANCA
) -> str:
    """
    Cambia l'aspetto del bot nel server. Ogni campo: MANCA = non si tocca, None = si toglie,
    testo o byte = il valore nuovo. Il nickname è libero; avatar, banner e descrizione sono premium.
    Restituisce la chiave del messaggio per l'utente.
    """
    from core.premium import guild_has_premium_access

    immagini = {n: v for n, v in (("avatar", avatar), ("banner", banner)) if v is not MANCA}
    if nick is MANCA and bio is MANCA and not immagini:
        return "asp_niente"
    if (immagini or bio is not MANCA) and not await guild_has_premium_access(guild.id, MODULO_ASPETTO, bot=bot):
        return "asp_richiede_premium"
    campi: dict = {}
    try:
        if nick is not MANCA:
            campi["nick"] = _testo(nick, MAX_NICK)
        if bio is not MANCA:
            campi["bio"] = _testo(bio, MAX_BIO)
        for nome, dati in immagini.items():
            campi[nome] = None if dati is None else await controlla_immagine(dati)
    except AspettoRifiutato as exc:
        return exc.motivo
    if any(campi.get(n) is not None for n in ("avatar", "banner")) and not _limite_immagini.consenti(str(guild.id)):
        return "asp_attendi"
    try:
        await guild.me.edit(**campi, reason=f"Aspetto del bot, richiesto da {autore_id}")
    except discord.Forbidden:
        return "cfg_nick_permesso" if "nick" in campi else "asp_errore"
    except discord.HTTPException as exc:
        logger.info("Discord ha rifiutato l'aspetto del bot nel server %s (%s).", guild.id, exc.status)
        return "asp_errore"
    logger.info("Aspetto del bot cambiato nel server %s da %s: %s.", guild.id, autore_id, ", ".join(sorted(campi)))
    return "asp_ok"


def stato_aspetto(guild: discord.Guild) -> dict:
    """Cosa si vede del profilo del bot nel server (la descrizione Discord non la restituisce)."""
    me = guild.me
    avatar = getattr(me, "guild_avatar", None)
    banner = getattr(me, "guild_banner", None)
    return {
        "nick": getattr(me, "nick", None),
        "avatar": avatar.url if avatar else None,
        "banner": banner.url if banner else None,
    }
