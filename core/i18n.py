"""
core/i18n.py
============
NF-06 (#77, SPEC §21): tutti i testi del bot in un file per lingua
(`locales/it.json`, `locales/en.json`, stesse chiavi e stessi segnaposto,
controllati da `tests/test_i18n_completo.py`).

Quale lingua si usa
-------------------
- Risposta pubblica: la lingua del SERVER (`/admin lingua set`).
- Risposta che vede solo l'utente: la sua lingua PERSONALE (`/utility lingua`)
  se l'ha scelta, altrimenti quella del server.
- Fuori da un server (DM): la lingua personale, altrimenti l'italiano.
- Mai un errore: se il database non risponde si torna all'italiano.

`t(chiave, lingua, **valori)` non solleva mai: lingua o chiave sconosciute
ricadono sull'italiano e poi sulla chiave stessa.
Un testo nuovo si aggiunge in entrambi i file; un test fallisce se le chiavi
o i segnaposto non coincidono.
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Any

logger = logging.getLogger("iyokai.i18n")

LINGUE: tuple[str, ...] = ("it", "en")
DEFAULT_LANGUAGE = "it"
CARTELLA_LOCALES = pathlib.Path(__file__).resolve().parent.parent / "locales"

_CATALOGO: dict[str, dict[str, str]] = {}


def carica_catalogo(forza: bool = False) -> dict[str, dict[str, str]]:
    """Legge i file delle lingue (una volta sola). Un file mancante o rotto dà un catalogo vuoto per quella lingua."""
    if _CATALOGO and not forza:
        return _CATALOGO
    _CATALOGO.clear()
    for lingua in LINGUE:
        try:
            dati = json.loads((CARTELLA_LOCALES / f"{lingua}.json").read_text(encoding="utf-8"))
            _CATALOGO[lingua] = {k: v for k, v in dati.items() if isinstance(k, str) and isinstance(v, str)}
        except (OSError, ValueError):
            logger.error("Catalogo delle lingue illeggibile: %s.json", lingua)
            _CATALOGO[lingua] = {}
    return _CATALOGO


class _Sicuro(dict):
    def __missing__(self, chiave: str) -> str:
        return "{" + chiave + "}"


def t(key: str, language: str | None = None, **valori: Any) -> str:
    """Il testo `key` nella lingua richiesta, con i segnaposto riempiti con `valori`."""
    catalogo = carica_catalogo()
    lingua = language if language in catalogo else DEFAULT_LANGUAGE
    testo = catalogo.get(lingua, {}).get(key)
    if testo is None:
        testo = catalogo.get(DEFAULT_LANGUAGE, {}).get(key)
    if testo is None:
        return key
    if valori:
        try:
            return testo.format_map(_Sicuro(valori))
        except (ValueError, IndexError, KeyError, AttributeError):
            return testo
    return testo


def lingua_valida(codice: Any) -> bool:
    return isinstance(codice, str) and codice in LINGUE


def da_locale_discord(locale: Any) -> str | None:
    """`it` per l'italiano di Discord, `en` per ogni inglese, altrimenti None (lingua non gestita)."""
    testo = str(getattr(locale, "value", locale) or "").lower()
    if testo.startswith("it"):
        return "it"
    if testo.startswith("en"):
        return "en"
    return None


async def lingua_utente(user_id: int | None) -> str | None:
    """La lingua personale scelta dall'utente, o None."""
    if not user_id:
        return None
    from core.repositories.user_language_repo import user_language_repo

    valore = await user_language_repo.get(user_id)
    return valore if lingua_valida(valore) else None


async def lingua_server(guild_id: int | None) -> str:
    if not guild_id:
        return DEFAULT_LANGUAGE
    from core.database import db

    valore = await db.get_guild_language(guild_id)
    return valore if lingua_valida(valore) else DEFAULT_LANGUAGE


async def lingua_risposta(guild_id: int | None, user_id: int | None = None, *, pubblica: bool = False) -> str:
    """Quale lingua usare. `pubblica=True`: la risposta la vedono tutti, quindi decide il server."""
    try:
        if not pubblica:
            personale = await lingua_utente(user_id)
            if personale:
                return personale
        return await lingua_server(guild_id)
    except Exception:
        logger.debug("Lingua non letta dal database: uso l'italiano.", exc_info=True)
        return DEFAULT_LANGUAGE


async def lingua_interazione(interaction: Any, *, pubblica: bool = False) -> str:
    """Come `lingua_risposta`, partendo da un'interazione di Discord (tollerante: mai eccezioni)."""
    try:
        guild_id = getattr(getattr(interaction, "guild", None), "id", None)
        user_id = getattr(getattr(interaction, "user", None), "id", None)
        if not isinstance(guild_id, int):
            guild_id = None
        if not isinstance(user_id, int):
            user_id = None
        return await lingua_risposta(guild_id, user_id, pubblica=pubblica)
    except Exception:
        return DEFAULT_LANGUAGE


async def testo_per(interaction: Any, key: str, *, pubblica: bool = False, **valori: Any) -> str:
    return t(key, await lingua_interazione(interaction, pubblica=pubblica), **valori)


async def imposta_lingua_utente(user_id: int, scelta: str | None) -> str | None:
    """
    Un solo punto per scrivere la lingua personale (comando e futuro pannello).
    `scelta` None o "server": toglie la preferenza. Solleva ValueError per una lingua non ammessa.
    Restituisce la lingua salvata, o None se è stata tolta.
    """
    from core.repositories.user_language_repo import user_language_repo

    if scelta is None or scelta == "server":
        await user_language_repo.clear(user_id)
        return None
    if not lingua_valida(scelta):
        raise ValueError(scelta)
    await user_language_repo.set(user_id, scelta)
    return scelta
