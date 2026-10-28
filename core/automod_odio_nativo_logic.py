"""
core/automod_odio_nativo_logic.py
=================================
Regola nativa dell'AutoMod di Discord per le frasi palesemente d'odio (D35): un
insulto razzista della lista di base vicino a una minaccia o un incitamento
(in un verso o nell'altro), bloccata prima dell'invio con un testo scelto dal
server. Qui si costruiscono le espressioni regolari nei limiti di Discord
(10 per regola, 260 caratteri l'una, sintassi Rust); la sincronizzazione sta in
core/automod_odio_azioni.py. Le parole sospette (cognomi) non entrano: le
giudica l'AI (core/odio_giudizio_logic.py).
Funzioni coperte: SPEC §6 (D35)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.automod_parole_logic import carica_base

RULE_NAME_ODIO = "iYokai — Odio"

MAX_REGEX = 10  # per regola (LIMITI.md 1.7)
MAX_LUNGHEZZA_REGEX = 260
DISTANZA = 40  # caratteri tra insulto e minaccia

# Radici di minacce e incitamenti, italiano e inglese (con \w* dopo la radice).
MINACCE = (
    "ammazz", "uccid", "uccis", "brucia", "impicc", "linci", "stermin", "gassa", "morite", "crepate",
    "kill", "hang", "lynch", "burn", "exterminat", "shoot",
)

_PAROLA = re.compile(r"[a-z]{4,14}")
_RADICE_MINACCE = "(?:" + "|".join(MINACCE) + r")\w*"


@dataclass(frozen=True)
class RegexOdio:
    pattern: tuple[str, ...]
    insulti_inclusi: int
    insulti_esclusi: int


def insulti_di_base() -> tuple[str, ...]:
    """Le voci di base adatte a una regola nativa: solo lettere semplici, da 4 a 14 (senza doppioni)."""
    voci, _ = carica_base()
    viste: dict[str, None] = {}
    for voce, _dentro in voci:
        if _PAROLA.fullmatch(voce):
            viste[voce] = None
    return tuple(viste)


def _coppia(insulti: tuple[str, ...]) -> tuple[str, str]:
    ins = r"\b(?:" + "|".join(insulti) + r")s?\b"
    minaccia = r"\b" + _RADICE_MINACCE
    lontano = r"[^\n]{0," + str(DISTANZA) + "}"
    return f"(?i){ins}{lontano}{minaccia}", f"(?i){minaccia}{lontano}{ins}"


def costruisci_regex(insulti: tuple[str, ...] | None = None) -> RegexOdio:
    """Le espressioni regolari della regola: tutte entro i limiti di Discord, le voci in eccesso restano fuori."""
    insulti = insulti if insulti is not None else insulti_di_base()
    modelli: list[str] = []
    gruppo: list[str] = []
    incluse = 0

    def chiudi() -> None:
        if gruppo:
            modelli.extend(_coppia(tuple(gruppo)))

    for parola in insulti:
        prova = _coppia((*gruppo, parola))
        if all(len(p) <= MAX_LUNGHEZZA_REGEX for p in prova):
            gruppo.append(parola)
            incluse += 1
            continue
        if len(modelli) + 4 > MAX_REGEX:  # non c'e' posto per un altro gruppo (2 + 2)
            break
        chiudi()
        gruppo = [parola]
        incluse += 1
    if gruppo and len(modelli) + 2 <= MAX_REGEX:
        chiudi()
    else:
        incluse -= len(gruppo)
    return RegexOdio(tuple(modelli), incluse, len(insulti) - incluse)
