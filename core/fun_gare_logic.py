"""
core/fun_gare_logic.py
======================
Logica pura delle gare con classifica e del mazzo di carte (#131, D70, B3): periodi (giorno, settimana),
righe di classifica sotto i 100 caratteri, mazzo da 52 carte come stringa, durata dello spinner.
Funzioni coperte: SPEC §16 (FUN-015, 016, 018, 003)
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

GARE = ("dado", "spinner", "quiz", "battitura", "acronimi", "carte")
MAX_RIGA = 100
TOP = 10
MAX_PESCA = 10
SPINNER_MIN, SPINNER_MAX = 1, 60
SPINNER_ATTESA_SECONDI = 3600
DADO_FACCE = 100

_VALORI = "A23456789TJQK"
_SEMI = "SHDC"
_SIMBOLI = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}
MAZZO_INTERO = tuple(v + s for s in _SEMI for v in _VALORI)


def adesso() -> datetime:
    return datetime.now(timezone.utc)


def periodo_giorno(quando: datetime | None = None, giorni_fa: int = 0) -> str:
    return ((quando or adesso()) - timedelta(days=giorni_fa)).strftime("%Y-%m-%d")


def periodo_settimana(quando: datetime | None = None) -> str:
    anno, settimana, _ = (quando or adesso()).isocalendar()
    return f"{anno}-W{settimana:02d}"


def nuovo_mazzo(rng: random.Random) -> str:
    carte = list(MAZZO_INTERO)
    rng.shuffle(carte)
    return ",".join(carte)


def carta_testo(codice: str) -> str:
    return ("10" if codice[0] == "T" else codice[0]) + _SIMBOLI[codice[1]]


def pesca_dal_mazzo(rimaste: str, quante: int) -> tuple[list[str], str]:
    """Le prime `quante` carte (al massimo MAX_PESCA) e il mazzo che resta."""
    carte = [c for c in rimaste.split(",") if c]
    n = max(0, min(quante, MAX_PESCA, len(carte)))
    return carte[:n], ",".join(carte[n:])


def restanti(rimaste: str) -> int:
    return len([c for c in rimaste.split(",") if c])


def durata_spinner(rng: random.Random) -> int:
    return rng.randint(SPINNER_MIN, SPINNER_MAX)


def riga_classifica(posizione: int, user_id: int, valore: int, unita: str = "") -> str:
    medaglia = {1: "🥇", 2: "🥈", 3: "🥉"}.get(posizione, f"{posizione}.")
    return f"{medaglia} <@{user_id}> **{valore}**{unita}"[:MAX_RIGA]


def testo_classifica(righe: list[tuple[int, int]], unita: str = "") -> str:
    """`righe` = (user_id, valore) già in ordine. Vuota se non c'è nessuno."""
    return "\n".join(riga_classifica(i, u, v, unita) for i, (u, v) in enumerate(righe[:TOP], 1))
