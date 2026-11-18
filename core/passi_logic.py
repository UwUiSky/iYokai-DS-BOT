"""
core/passi_logic.py
===================
Regole pure di due giochi a più passi con incasso libero: «più alto o più basso» (ECO-094) e «torre»
(ECO-098). In entrambi il moltiplicatore è 0,95 diviso la probabilità vera di ogni passo: la resa media
è sempre 95% qualunque sia il momento in cui si incassa (nessuna strategia batte il banco).
Il caso arriva da fuori (`rng`).
Funzioni coperte: ECO-094, ECO-098
"""

from __future__ import annotations

import random

RESA = 0.95
CARTE = 13
TORRE_PROBABILITA = (0.85, 0.80, 0.75, 0.70, 0.65, 0.60, 0.55, 0.50, 0.45, 0.40)  # sopravvivere a ogni piano
SCELTE_PIU_ALTO = ("alto", "basso")


def probabilita_scelta(carta: int, scelta: str) -> float:
    """Probabilità di indovinare (parità = si perde): carte da 1 a 13 estratte a caso, ogni volta."""
    if scelta == "alto":
        return (CARTE - carta) / CARTE
    if scelta == "basso":
        return (carta - 1) / CARTE
    raise ValueError(f"Scelta sconosciuta: {scelta}")


def passo_possibile(carta: int, scelta: str) -> bool:
    return probabilita_scelta(carta, scelta) > 0


def moltiplicatore_passo(carta: int, scelta: str) -> float:
    """Di quanto cresce il premio se si indovina (mai con probabilità 0)."""
    p = probabilita_scelta(carta, scelta)
    if p <= 0:
        raise ValueError("Scelta impossibile: non può vincere.")
    return RESA / p


def estrai_carta(rng: random.Random) -> int:
    return rng.randint(1, CARTE)


def indovinato(carta: int, nuova: int, scelta: str) -> bool:
    return nuova > carta if scelta == "alto" else nuova < carta


def torre_moltiplicatore(piani: int) -> float:
    """Moltiplicatore dopo aver salito `piani` piani (0 = ancora a terra)."""
    if piani <= 0:
        return 1.0
    if piani > len(TORRE_PROBABILITA):
        raise ValueError("Piani oltre la cima.")
    prodotto = 1.0
    for p in TORRE_PROBABILITA[:piani]:
        prodotto *= p
    return RESA / prodotto


def torre_crolla(piano: int, rng: random.Random) -> bool:
    """Vero se salendo al piano `piano` (1 = il primo) la torre crolla."""
    p = TORRE_PROBABILITA[piano - 1]
    return rng.random() >= p


def incasso(puntata: int, moltiplicatore: float) -> int:
    """Monete incassate: puntata per moltiplicatore, per difetto (mai sotto la puntata se si è saliti)."""
    return int(puntata * moltiplicatore)
