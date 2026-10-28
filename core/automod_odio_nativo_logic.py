"""
core/automod_odio_nativo_logic.py
=================================
Regola nativa dell'AutoMod di Discord per le frasi palesemente d'odio (D35): un
insulto razzista della lista di base vicino a una minaccia o un incitamento
(in un verso o nell'altro), bloccata prima dell'invio con un testo scelto dal
server. Qui si costruiscono le espressioni regolari nei limiti di Discord
(10 per regola, 260 caratteri l'una, sintassi Rust), con le varianti di scrittura
piu' comuni (cifre al posto delle vocali: «n1gger», «terr0ne») e le voci della stessa
famiglia unite per prefisso, cosi' la lista di base entra tutta; la sincronizzazione sta in
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

# Radici di minacce e incitamenti, italiano e inglese («ucci» prende uccido, uccisi...).
MINACCE = (
    "ammazz", "ucci", "brucia", "impicc", "linci", "stermin", "gassa", "morite", "crepate",
    "kill", "hang", "lynch", "burn", "extermin", "shoot",
)

# Lettere che si scrivono spesso con una cifra o un simbolo (classi Rust, niente lookaround).
SOSTITUZIONI = {"a": "[a4@]", "e": "[e3]", "i": "[i1!]", "o": "[o0]"}

_PAROLA = re.compile(r"[a-z]{4,14}")
_RADICE_MINACCE = "(?:" + "|".join(MINACCE) + ")"  # basta la radice: dopo non serve altro


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


def _atomo(pezzo: str) -> bool:
    return len(pezzo) == 1 or (pezzo.startswith("[") and pezzo.endswith("]") and pezzo.count("[") == 1)


def _albero(parole: tuple[str, ...]) -> dict:
    radice: dict = {}
    for parola in parole:
        nodo = radice
        for lettera in parola:
            nodo = nodo.setdefault(lettera, {})
        nodo[""] = {}
    return radice


def _da_albero(nodo: dict) -> str:
    """Le parole con lo stesso inizio in una sola alternativa: «nigg(?:a|er)»."""
    rami = [SOSTITUZIONI.get(c, c) + _da_albero(figlio) for c, figlio in sorted(nodo.items()) if c]
    if not rami:
        return ""
    if len(rami) > 1 and all(_atomo(r) for r in rami):
        corpo = "[" + "".join(r.strip("[]") for r in rami) + "]"
    elif len(rami) == 1:
        corpo = rami[0]
    else:
        corpo = "(?:" + "|".join(rami) + ")"
    if "" not in nodo:
        return corpo
    return corpo + "?" if _atomo(corpo) or (corpo.startswith("(?:") and len(rami) > 1) else f"(?:{corpo})?"


def _coppia(insulti: tuple[str, ...]) -> tuple[str, str]:
    corpo = _da_albero(_albero(insulti))
    ins = r"\b" + (corpo if corpo.startswith("(?:") else f"(?:{corpo})") + r"s?\b"
    minaccia = r"\b" + _RADICE_MINACCE
    lontano = ".{0," + str(DISTANZA) + "}"  # «.» non attraversa l'a capo, come in Rust
    return f"(?i){ins}{lontano}{minaccia}", f"(?i){minaccia}{lontano}{ins}"


def costruisci_regex(insulti: tuple[str, ...] | None = None) -> RegexOdio:
    """Le espressioni regolari della regola: tutte entro i limiti di Discord, le voci in eccesso restano fuori."""
    insulti = insulti if insulti is not None else tuple(sorted(insulti_di_base()))  # in ordine: le famiglie stanno insieme
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
