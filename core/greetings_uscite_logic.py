"""
core/greetings_uscite_logic.py
==============================
Messaggi di ban e di addio (D37): chi esce tra «entrambi», «solo ban», «solo addio», «nessuno»,
i testi di base, la grafica (link https o file) e l'ordine «prima il martello, poi l'addio»
quando un ban fa scattare due eventi. Niente Discord: si prova con test semplici.
Funzioni coperte: SPEC §14.4 (RUO-016, D37)
Dipende da: core/safe_http.py (link), core/safe_image.py (file)
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from core.bounded_cache import BoundedCache
from core.safe_http import url_e_sicuro
from core.safe_image import safe_open_image

MODO_ENTRAMBI = "entrambi"
MODO_SOLO_BAN = "solo_ban"
MODO_SOLO_ADDIO = "solo_addio"
MODO_NESSUNO = "nessuno"
MODI = (MODO_ENTRAMBI, MODO_SOLO_BAN, MODO_SOLO_ADDIO, MODO_NESSUNO)
ETICHETTE_MODO = {
    MODO_ENTRAMBI: "ban e addio",
    MODO_SOLO_BAN: "solo il messaggio di ban",
    MODO_SOLO_ADDIO: "solo l'addio",
    MODO_NESSUNO: "nessuno dei due",
}

TIPO_BAN = "ban"
TIPO_ADDIO = "addio"
TIPI = (TIPO_BAN, TIPO_ADDIO)

# Testi di base (solo testo ed emoji: nessuna gif di serie, vedi D37).
TESTO_BAN_DI_BASE = "🔨 Il martello ha parlato: **{username}** è stato bandito da {server}."
TESTO_ADDIO_DI_BASE = "Ciao, è stato bello vederti, **{username}**! 👋"

MAX_LINK = 500
MAX_BYTE_GRAFICA = 3 * 1024 * 1024
FORMATI_GRAFICA = {"PNG": "png", "JPEG": "jpg", "GIF": "gif", "WEBP": "webp"}
TOGLI = "togli"
ATTESA_BAN = 3.0  # secondi: l'addio aspetta di sapere se l'uscita è un ban


def modo_valido(modo: str) -> bool:
    return modo in MODI


def invia_ban(modo: str) -> bool:
    return modo in (MODO_ENTRAMBI, MODO_SOLO_BAN)


def invia_addio(modo: str) -> bool:
    return modo in (MODO_ENTRAMBI, MODO_SOLO_ADDIO)


def testo_ban(personalizzato: str) -> str:
    return personalizzato or TESTO_BAN_DI_BASE


async def valida_link(testo: str) -> str | None:
    """Il motivo del rifiuto, oppure None se il link https è accettabile (passa da safe_http)."""
    testo = testo.strip()
    if len(testo) > MAX_LINK:
        return f"Il link è troppo lungo (massimo {MAX_LINK} caratteri)."
    if not testo.lower().startswith("https://"):
        return "Il link deve cominciare con https://"
    if not await url_e_sicuro(testo):
        return "Questo link non è raggiungibile in sicurezza."
    return None


def valida_file(dati: bytes) -> tuple[str | None, str | None]:
    """(estensione, errore) di un file caricato: formato e pixel controllati da safe_image (16 MP)."""
    from PIL import UnidentifiedImageError

    from core.safe_image import ImmagineTroppoGrande

    if len(dati) > MAX_BYTE_GRAFICA:
        return None, "Il file pesa troppo: il limite è 3 MB."
    try:
        immagine = safe_open_image(dati)
    except ImmagineTroppoGrande:
        return None, "L'immagine ha troppi pixel: il limite è 16 megapixel."
    except (UnidentifiedImageError, OSError):
        return None, "Non riesco ad aprire il file: usa un PNG, JPEG, GIF o WebP."
    estensione = FORMATI_GRAFICA.get(immagine.format or "")
    if estensione is None:
        return None, "Formato non ammesso: usa PNG, JPEG, GIF o WebP."
    return estensione, None


@dataclass
class _Stato:
    evento: asyncio.Event
    soppresso: bool = False
    quando: float = 0.0


_stati: BoundedCache[tuple[int, int], _Stato] = BoundedCache(2000)
_VALIDITA = 30.0


def _stato(guild_id: int, user_id: int) -> _Stato:
    chiave = (guild_id, user_id)
    stato = _stati.get(chiave)
    if stato is None or time.monotonic() - stato.quando > _VALIDITA:
        stato = _Stato(asyncio.Event(), quando=time.monotonic())
        _stati.set(chiave, stato)
    return stato


def segna_ban(guild_id: int, user_id: int, *, soppresso: bool) -> None:
    """Il ban è stato gestito (messaggio inviato o no). `soppresso`: durante un raid niente addio per lui."""
    stato = _stato(guild_id, user_id)
    stato.soppresso = soppresso
    stato.evento.set()


async def addio_soppresso(guild_id: int, user_id: int, *, attendi: bool) -> bool:
    """
    True se l'uscita è un ban fatto durante un raid (niente addio). Con `attendi` aspetta fino a
    ATTESA_BAN secondi l'evento di ban: così il martello esce sempre prima dell'addio.
    """
    stato = _stato(guild_id, user_id)
    if attendi and not stato.evento.is_set():
        try:
            await asyncio.wait_for(stato.evento.wait(), ATTESA_BAN)
        except asyncio.TimeoutError:
            pass
    risultato = stato.evento.is_set() and stato.soppresso
    _stati.delete((guild_id, user_id))
    return risultato
