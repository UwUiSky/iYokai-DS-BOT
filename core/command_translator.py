"""
core/command_translator.py
==========================
Nomi e descrizioni dei comandi tradotti da Discord (NF-06, #77, SPEC §21, D1, D58).

Come funziona
-------------
- La lingua di base nel codice resta l'italiano (nomi e descrizioni scritti nei cog).
- Ogni lingua ha il suo `locales/<lingua>/comandi.json` (codici di Discord: en-US, de, es-ES, fr,
  ja, ko, ru, uk, zh-CN; `en-GB` usa `en-US`). Sezioni:
    * `nomi`: segmento italiano -> segmento tradotto (vale in tutto l'albero);
    * `descrizioni`: percorso del comando ("modban tempban") -> descrizione;
    * `parametri`: "percorso:parametro" -> descrizione dell'opzione;
    * `menu`: nome di un menu del tasto destro ("Testo pulito") -> nome tradotto (maiuscole e spazi ammessi);
    * `aiuto`: percorso -> spiegazione lunga, letta da /info e /cerca-comando (ripiego lingua -> en-US -> it).
- Il traduttore `TraduttoreYokai` manda a Discord solo le chiavi tradotte; per l'italiano e per le
  lingue non gestite risponde None (Discord usa la base). Un file vuoto = nessuna localizzazione.
- Un nome tradotto non valido per Discord (maiuscole, caratteri non ammessi, oltre 32 caratteri), uno
  che toglie il prefisso `admin-` / `mod-` / `founder` (D60) o una descrizione oltre 100 caratteri
  si scartano: meglio la base che far fallire la sync.
- `tests/test_command_translator.py` controlla l'albero VERO: descrizioni inglesi complete, nessun
  duplicato tra fratelli, limiti di Discord (nome 32, descrizione 100, 8000 con la versione più lunga
  tra tutte le lingue presenti).

L'impronta della sync (core/command_sync.py) include le traduzioni: cambiare un testo in un
comandi.json fa risincronizzare i comandi al prossimo avvio.
"""


from __future__ import annotations

import json
import logging
import pathlib
import unicodedata
from typing import Any

import discord
from discord import app_commands

from core.i18n import DEFAULT_LANGUAGE, LINGUA_RIPIEGO, LINGUE, da_locale_discord, normalizza_lingua, percorso_comandi

logger = logging.getLogger("iyokai.command_translator")

FILE_COMANDI = "comandi.json"
MAX_NOME = 32
MAX_DESCRIZIONE = 100
SEZIONI = ("nomi", "descrizioni", "parametri", "menu", "aiuto")
# Il prefisso dei gruppi dello staff non si traduce in nessuna lingua (D60).
PREFISSI_NON_TRADOTTI = ("admin-", "mod-", "founder")
_SEPARATORI_VALIDI = "-_\u02bc"  # trattino, underscore, apostrofo modificatore (ʼ)

# lingua -> sezione -> chiave -> testo
_dati: dict[str, dict[str, dict[str, str]]] = {}


def _leggi_lingua(lingua: str) -> dict[str, dict[str, str]]:
    grezzo: dict[str, Any] = {}
    try:
        grezzo = json.loads(percorso_comandi(lingua).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.error("Traduzioni dei comandi illeggibili: %s/%s", lingua, FILE_COMANDI)
    if not isinstance(grezzo, dict):
        grezzo = {}
    risultato: dict[str, dict[str, str]] = {}
    for sezione in SEZIONI:
        voce = grezzo.get(sezione)
        risultato[sezione] = (
            {k: v for k, v in voce.items() if isinstance(k, str) and isinstance(v, str)}
            if isinstance(voce, dict)
            else {}
        )
    return risultato


def carica_tutte(forza: bool = False) -> dict[str, dict[str, dict[str, str]]]:
    """Legge il comandi.json di ogni lingua (una volta sola)."""
    if _dati and not forza:
        return _dati
    _dati.clear()
    for lingua in LINGUE:
        _dati[lingua] = _leggi_lingua(lingua)
    return _dati


def carica_traduzioni(forza: bool = False, lingua: str = LINGUA_RIPIEGO) -> dict[str, dict[str, str]]:
    """Le sezioni di una lingua (di norma l'inglese); file mancante o rotto = tutto vuoto."""
    return carica_tutte(forza).setdefault(lingua, {s: {} for s in SEZIONI})


def lingue_dei_comandi() -> tuple[str, ...]:
    """Le lingue con almeno una traduzione dei comandi (l'italiano è la base: non conta)."""
    dati = carica_tutte()
    return tuple(
        l for l in LINGUE if l != DEFAULT_LANGUAGE and any(dati.get(l, {}).get(s) for s in ("nomi", "descrizioni", "parametri", "menu"))
    )


def _carattere_ammesso(c: str) -> bool:
    if c in _SEPARATORI_VALIDI:
        return True
    categoria = unicodedata.category(c)
    if categoria[0] in ("L", "N"):
        return True
    # Devanagari e Thai: anche i segni combinanti (vocali, accenti).
    if categoria[0] == "M":
        nome = unicodedata.name(c, "")
        return nome.startswith(("DEVANAGARI", "THAI"))
    return False


def nome_valido(nome: str) -> bool:
    """Regola dei nomi di Discord: 1-32 caratteri, minuscoli, lettere/cifre/trattino/underscore (anche altre scritture)."""
    return 1 <= len(nome) <= MAX_NOME and nome == nome.lower() and all(_carattere_ammesso(c) for c in nome)


def _prefisso_ok(segmento: str, tradotto: str) -> bool:
    for prefisso in PREFISSI_NON_TRADOTTI:
        if segmento == prefisso or segmento.startswith(prefisso):
            return tradotto == prefisso if segmento == prefisso else tradotto.startswith(prefisso)
    return True


def nome_tradotto(segmento: str, lingua: str = LINGUA_RIPIEGO) -> str | None:
    """Il segmento tradotto di un nome italiano, o None se non c'è (o non è valido)."""
    tradotto = carica_traduzioni(lingua=lingua)["nomi"].get(segmento)
    return tradotto if tradotto and nome_valido(tradotto) and _prefisso_ok(segmento, tradotto) else None


def menu_tradotto(nome: str, lingua: str = LINGUA_RIPIEGO) -> str | None:
    """Il nome tradotto di un menu del tasto destro (fino a 32 caratteri), o None."""
    tradotto = carica_traduzioni(lingua=lingua)["menu"].get(nome)
    return tradotto if tradotto and len(tradotto) <= MAX_NOME and tradotto.strip() == tradotto else None


def descrizione_tradotta(percorso: str, lingua: str = LINGUA_RIPIEGO) -> str | None:
    testo = carica_traduzioni(lingua=lingua)["descrizioni"].get(percorso)
    return testo if testo and 1 <= len(testo) <= MAX_DESCRIZIONE else None


def parametro_tradotto(percorso: str, parametro: str, lingua: str = LINGUA_RIPIEGO) -> str | None:
    testo = carica_traduzioni(lingua=lingua)["parametri"].get(f"{percorso}:{parametro}")
    return testo if testo and 1 <= len(testo) <= MAX_DESCRIZIONE else None


# Nomi storici (l'inglese era l'unica lingua).
def nome_inglese(segmento: str) -> str | None:
    return nome_tradotto(segmento)


def menu_inglese(nome: str) -> str | None:
    return menu_tradotto(nome)


def descrizione_inglese(percorso: str) -> str | None:
    return descrizione_tradotta(percorso)


def parametro_inglese(percorso: str, parametro: str) -> str | None:
    return parametro_tradotto(percorso, parametro)


def aiuto_comando(percorso: str, lingua: str | None) -> str | None:
    """La spiegazione lunga di un comando nella lingua richiesta; ripiego en-US, poi it. None se non esiste."""
    scelta = normalizza_lingua(lingua) or DEFAULT_LANGUAGE
    for candidata in (scelta, LINGUA_RIPIEGO, DEFAULT_LANGUAGE):
        testo = carica_traduzioni(lingua=candidata)["aiuto"].get(percorso)
        if testo:
            return testo
    return None


def _lingue_tradotte() -> tuple[str, ...]:
    return tuple(l for l in LINGUE if l != DEFAULT_LANGUAGE)


def caratteri_con_traduzioni(nodo: Any) -> int:
    """
    I caratteri che Discord conta per un comando o gruppo (limite 8000): per ogni campo conta
    solo la traduzione PIÙ LUNGA tra tutte le lingue presenti, base compresa (docs.discord.com).
    """
    percorso = nodo.qualified_name
    lingue = _lingue_tradotte()
    totale = max([len(nodo.name)] + [len(nome_tradotto(nodo.name, l) or "") for l in lingue]) + max(
        [len(nodo.description)] + [len(descrizione_tradotta(percorso, l) or "") for l in lingue]
    )
    if isinstance(nodo, app_commands.Group):
        return totale + sum(caratteri_con_traduzioni(c) for c in nodo.commands)
    for param in nodo.parameters:
        totale += len(param.name)
        totale += max([len(param.description)] + [len(parametro_tradotto(percorso, param.name, l) or "") for l in lingue])
        for scelta in param.choices:
            totale += len(scelta.name) + len(str(scelta.value))
    return totale


def tradotto_per(contesto: Any, lingua: str) -> str | None:
    """Il testo tradotto per un contesto di discord.py nella lingua (cartella), o None. L'italiano è la base."""
    lingua = normalizza_lingua(lingua)
    if lingua is None or lingua == DEFAULT_LANGUAGE:
        return None
    posizione = contesto.location
    dato = contesto.data
    L = app_commands.TranslationContextLocation
    if posizione is L.command_name and isinstance(dato, app_commands.ContextMenu):
        return menu_tradotto(dato.name, lingua)
    if posizione in (L.command_name, L.group_name):
        return nome_tradotto(dato.name, lingua)
    if posizione in (L.command_description, L.group_description):
        return descrizione_tradotta(dato.qualified_name, lingua)
    if posizione is L.parameter_description:
        comando = getattr(dato, "command", None)
        return parametro_tradotto(comando.qualified_name, dato.name, lingua) if comando is not None else None
    return None


class TraduttoreYokai(app_commands.Translator):
    async def load(self) -> None:
        carica_traduzioni(forza=True)

    async def translate(
        self, string: app_commands.locale_str, locale: discord.Locale, context: app_commands.TranslationContextTypes
    ) -> str | None:
        lingua = da_locale_discord(locale)
        if lingua is None:
            return None
        try:
            return tradotto_per(context, lingua)
        except Exception:
            logger.debug("Traduzione non riuscita per %r", string.message, exc_info=True)
            return None
