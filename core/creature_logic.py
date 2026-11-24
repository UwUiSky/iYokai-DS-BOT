"""
core/creature_logic.py
======================
Regole pure delle creature di fantasia (yokai e spiriti) comprate al negozio e dei loro scontri con posta (ECO-101).
Forza da 50 a 70 alla nascita, +1 a ogni vittoria fino a 90, -10 a ogni sconfitta: sotto 30 la creatura fugge.
Vince chi estrae sotto la sua quota di forza (forza A / somma delle due). Il caso arriva da fuori (`rng`).
Funzioni coperte: ECO-101
"""

from __future__ import annotations

import random

# Il numero (da 1) è quello salvato in `shop_items.azione_valore` e in `economia_creature.specie`.
SPECIE = ("kitsune", "tanuki", "kappa", "tengu", "nure-onna", "oni", "karakasa", "bakeneko")
FORZA_NASCITA_MIN = 50
FORZA_NASCITA_MAX = 70
FORZA_TETTO = 90
BONUS_VITTORIA = 1
PERDITA_SCONFITTA = 10
SOGLIA_FUGA = 30
MAX_CREATURE = 5  # per persona e per server


def nome_specie(numero: int) -> str:
    if not 1 <= numero <= len(SPECIE):
        raise ValueError("Specie sconosciuta.")
    return SPECIE[numero - 1]


def forza_iniziale(rng: random.Random) -> int:
    return rng.randint(FORZA_NASCITA_MIN, FORZA_NASCITA_MAX)


def probabilita_vittoria(forza_a: int, forza_b: int) -> float:
    return forza_a / (forza_a + forza_b)


def vince_il_primo(forza_a: int, forza_b: int, rng: random.Random) -> bool:
    return rng.random() < probabilita_vittoria(forza_a, forza_b)


def dopo_vittoria(forza: int) -> int:
    return min(FORZA_TETTO, forza + BONUS_VITTORIA)


def dopo_sconfitta(forza: int) -> tuple[int, bool]:
    """(nuova forza, la creatura fugge?)."""
    nuova = forza - PERDITA_SCONFITTA
    return nuova, nuova < SOGLIA_FUGA
