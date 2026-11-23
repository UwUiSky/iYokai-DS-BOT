"""
core/giveaway_guidato_logic.py
==============================
Logica pura della creazione guidata di un giveaway: lettura e controllo di premio, durata, vincitori e
requisiti scritti nelle finestre, e testo del riepilogo. Nessuna dipendenza da Discord o dal database.
Funzioni coperte: SPEC §15.5 (UTL-121; D124)
Dipende da: core/giveaway_logic.py
"""

from __future__ import annotations

import re
from typing import Any

from core.giveaway_logic import MAX_MESSAGGI_RICHIESTI, MAX_PREMIO_GIVEAWAY

MAX_DURATA_MINUTI = 43200
MAX_VINCITORI = 50
MAX_LIVELLO = 1000
_CONTROLLO = re.compile(r"[\x00-\x1f\x7f​-‏‪-‮⁦-⁩]")
_DURATA = re.compile(r"(\d{1,6})\s*([mhg d]?)", re.IGNORECASE)
_MOLTIPLICATORE = {"": 1, "m": 1, "h": 60, "d": 1440, "g": 1440}


def pulisci_premio(testo: str) -> str:
    """Il premio senza caratteri di controllo né spazi doppi, al massimo MAX_PREMIO_GIVEAWAY caratteri."""
    return re.sub(r"\s+", " ", _CONTROLLO.sub(" ", testo or "")).strip()[:MAX_PREMIO_GIVEAWAY]


def leggi_durata(testo: str) -> int | None:
    """Minuti da «90», «2h» o «3d» (anche «g» per giorni). None se non è valida o fuori da 1..43200."""
    trovato = _DURATA.fullmatch((testo or "").strip().replace(" ", ""))
    if trovato is None:
        return None
    minuti = int(trovato.group(1)) * _MOLTIPLICATORE[trovato.group(2).strip().lower()]
    return minuti if 1 <= minuti <= MAX_DURATA_MINUTI else None


def leggi_numero(testo: str, minimo: int, massimo: int) -> int | None:
    pulito = (testo or "").strip()
    if not pulito.isascii() or not pulito.isdigit():
        return None
    valore = int(pulito)
    return valore if minimo <= valore <= massimo else None


def leggi_base(premio: str, durata: str, vincitori: str) -> tuple[dict[str, Any] | None, str | None]:
    """(dati, None) se è tutto a posto, altrimenti (None, chiave del testo dell'errore)."""
    pulito = pulisci_premio(premio)
    if not pulito:
        return None, "giveaway_guidato_err_premio"
    minuti = leggi_durata(durata)
    if minuti is None:
        return None, "giveaway_guidato_err_durata"
    numero = leggi_numero(vincitori or "1", 1, MAX_VINCITORI)
    if numero is None:
        return None, "giveaway_guidato_err_vincitori"
    return {"premio": pulito, "durata": minuti, "vincitori": numero}, None


def leggi_requisiti(livello: str, messaggi: str) -> tuple[dict[str, int] | None, str | None]:
    liv = leggi_numero(livello or "0", 0, MAX_LIVELLO)
    mess = leggi_numero(messaggi or "0", 0, MAX_MESSAGGI_RICHIESTI)
    if liv is None or mess is None:
        return None, "giveaway_guidato_err_requisiti"
    return {"livello_min": liv, "messaggi_min": mess}, None


def durata_leggibile(minuti: int) -> str:
    giorni, resto = divmod(minuti, 1440)
    ore, minuti_r = divmod(resto, 60)
    parti = [f"{giorni} g" if giorni else "", f"{ore} h" if ore else "", f"{minuti_r} min" if minuti_r else ""]
    return " ".join(p for p in parti if p) or "0 min"
