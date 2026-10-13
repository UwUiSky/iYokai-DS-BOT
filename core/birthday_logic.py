"""
core/birthday_logic.py
======================
Date e testo degli auguri (NF-26, SPEC §23.4). Solo giorno e mese; tutto in UTC.
Funzioni pure.
Funzioni coperte: SPEC §23 (NF-26)
"""

from __future__ import annotations

import calendar
from datetime import date

MAX_MESSAGGIO = 500
MESSAGGIO_DI_BASE = "🎂 Buon compleanno {users}!"
_MAX_DISCORD = 2000
_GIORNI_DEL_MESE = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)  # febbraio con il 29


def data_valida(giorno: int, mese: int) -> bool:
    if not 1 <= mese <= 12:
        return False
    return 1 <= giorno <= _GIORNI_DEL_MESE[mese - 1]


def festeggia_oggi(giorno: int, mese: int, oggi: date) -> bool:
    """Il 29 febbraio si festeggia il 28 negli anni non bisestili."""
    if giorno == 29 and mese == 2 and not calendar.isleap(oggi.year):
        return oggi.month == 2 and oggi.day == 28
    return oggi.day == giorno and oggi.month == mese


def dividi_auguri(modello: str, menzioni: list[str]) -> list[str]:
    """
    I messaggi di auguri: il modello con `{users}` sostituito dai festeggiati, in più
    messaggi se sono tanti (mai oltre 2000 caratteri ciascuno).
    """
    if "{users}" not in modello:
        modello = f"{modello} {{users}}"
    base = len(modello.replace("{users}", ""))
    spazio = max(_MAX_DISCORD - base, 30)
    messaggi: list[str] = []
    corrente: list[str] = []
    lunghezza = 0
    for menzione in menzioni:
        costo = len(menzione) + (2 if corrente else 0)
        if corrente and lunghezza + costo > spazio:
            messaggi.append(modello.replace("{users}", ", ".join(corrente)))
            corrente, lunghezza, costo = [], 0, len(menzione)
        corrente.append(menzione)
        lunghezza += costo
    if corrente:
        messaggi.append(modello.replace("{users}", ", ".join(corrente)))
    return [m[:_MAX_DISCORD] for m in messaggi]
