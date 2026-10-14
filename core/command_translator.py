"""
core/command_translator.py
==========================
Nomi e descrizioni dei comandi tradotti da Discord (NF-06, #77, SPEC §21, D1).

Come funziona
-------------
- La lingua di base nel codice resta l'italiano (nomi e descrizioni scritti nei cog).
- Discord mostra l'inglese a chi ha il client in inglese (en-US, en-GB): il traduttore
  `TraduttoreYokai` risponde dal file `locales/comandi.en.json`:
    * `nomi`: segmento italiano -> segmento inglese (vale in tutto l'albero);
    * `descrizioni`: percorso del comando ("modban tempban") -> descrizione;
    * `parametri`: "percorso:parametro" -> descrizione dell'opzione.
- Per ogni altra lingua (italiano compreso) risponde None: Discord usa la base.
- Un nome tradotto non valido per Discord (maiuscole, spazi, oltre 32 caratteri) o una
  descrizione oltre 100 caratteri si scartano: meglio la base che far fallire la sync.
- `tests/test_command_translator.py` controlla l'albero VERO: ogni comando e gruppo ha
  la descrizione inglese, nessun duplicato tra fratelli, limiti di Discord (nome 32,
  descrizione 100, totale 8000 per comando anche con le traduzioni).

L'impronta della sync (core/command_sync.py) include le traduzioni: cambiare un testo in
locales/comandi.en.json fa risincronizzare i comandi al prossimo avvio.
"""

from __future__ import annotations

import json
import logging
import pathlib
import re
from typing import Any

import discord
from discord import app_commands

from core.i18n import CARTELLA_LOCALES, da_locale_discord

logger = logging.getLogger("iyokai.command_translator")

FILE_COMANDI_EN = "comandi.en.json"
MAX_NOME = 32
MAX_DESCRIZIONE = 100
# Stessa regola dei nomi di Discord (minuscole, cifre, trattino e underscore).
_NOME_VALIDO = re.compile(r"^[-_\w]{1,32}$", re.UNICODE)

_dati: dict[str, dict[str, str]] = {}


def carica_traduzioni(forza: bool = False) -> dict[str, dict[str, str]]:
    """{'nomi': {...}, 'descrizioni': {...}, 'parametri': {...}}; file mancante o rotto = tutto vuoto."""
    if _dati and not forza:
        return _dati
    _dati.clear()
    grezzo: dict[str, Any] = {}
    try:
        grezzo = json.loads((pathlib.Path(CARTELLA_LOCALES) / FILE_COMANDI_EN).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.error("Traduzioni dei comandi illeggibili: %s", FILE_COMANDI_EN)
    for sezione in ("nomi", "descrizioni", "parametri"):
        voce = grezzo.get(sezione)
        _dati[sezione] = (
            {k: v for k, v in voce.items() if isinstance(k, str) and isinstance(v, str)}
            if isinstance(voce, dict)
            else {}
        )
    return _dati


def nome_valido(nome: str) -> bool:
    return bool(_NOME_VALIDO.match(nome)) and nome == nome.lower()


def nome_inglese(segmento: str) -> str | None:
    """Il segmento inglese di un nome italiano, o None se non c'è (o non è valido)."""
    tradotto = carica_traduzioni()["nomi"].get(segmento)
    return tradotto if tradotto and nome_valido(tradotto) else None


def descrizione_inglese(percorso: str) -> str | None:
    testo = carica_traduzioni()["descrizioni"].get(percorso)
    return testo if testo and 1 <= len(testo) <= MAX_DESCRIZIONE else None


def parametro_inglese(percorso: str, parametro: str) -> str | None:
    testo = carica_traduzioni()["parametri"].get(f"{percorso}:{parametro}")
    return testo if testo and 1 <= len(testo) <= MAX_DESCRIZIONE else None


def caratteri_con_traduzioni(nodo: Any) -> int:
    """
    I caratteri che Discord conta per un comando o gruppo (limite 8000): per ogni campo conta
    solo la traduzione PIÙ LUNGA, base compresa (docs.discord.com, application commands).
    """
    percorso = nodo.qualified_name
    totale = max(len(nodo.name), len(nome_inglese(nodo.name) or "")) + max(
        len(nodo.description), len(descrizione_inglese(percorso) or "")
    )
    if isinstance(nodo, app_commands.Group):
        return totale + sum(caratteri_con_traduzioni(c) for c in nodo.commands)
    for param in nodo.parameters:
        totale += len(param.name) + max(len(param.description), len(parametro_inglese(percorso, param.name) or ""))
        for scelta in param.choices:
            totale += len(scelta.name) + len(str(scelta.value))
    return totale


def tradotto_per(contesto: Any, lingua: str) -> str | None:
    """Il testo tradotto per un contesto di discord.py, o None. Solo l'inglese è tradotto."""
    if lingua != "en":
        return None
    posizione = contesto.location
    dato = contesto.data
    L = app_commands.TranslationContextLocation
    if posizione in (L.command_name, L.group_name):
        return nome_inglese(dato.name)
    if posizione in (L.command_description, L.group_description):
        return descrizione_inglese(dato.qualified_name)
    if posizione is L.parameter_description:
        comando = getattr(dato, "command", None)
        return parametro_inglese(comando.qualified_name, dato.name) if comando is not None else None
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
