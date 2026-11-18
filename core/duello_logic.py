"""
core/duello_logic.py
====================
Regole pure del duello tra due utenti con una posta in monete (ECO-104): tre scontri a testa con un
dado da 20, vince chi ha il totale più alto (parità: si ritira finché cambia). Equo: 50% a testa.
Il caso arriva da fuori (`rng`).
Funzioni coperte: ECO-104
"""

from __future__ import annotations

import random
from dataclasses import dataclass

SCONTRI = 3
POSTA_MINIMA = 1
POSTA_MASSIMA = 100_000
ATTESA_RISPOSTA = 60  # secondi per accettare


@dataclass(frozen=True)
class EsitoDuello:
    tiri_sfidante: tuple[int, ...]
    tiri_sfidato: tuple[int, ...]
    vince_sfidante: bool


def lancia_duello(rng: random.Random) -> EsitoDuello:
    """Tre tiri a testa; il totale più alto vince; in parità si ripete l'intero duello."""
    while True:
        a = tuple(rng.randint(1, 20) for _ in range(SCONTRI))
        b = tuple(rng.randint(1, 20) for _ in range(SCONTRI))
        if sum(a) != sum(b):
            return EsitoDuello(a, b, sum(a) > sum(b))


def guadagno_con_tetto(posta: int, saldo_vincitore: int, tetto: int | None) -> int:
    """Quanto passa davvero dal perdente al vincitore: la posta, ma non oltre il tetto al saldo del vincitore."""
    if tetto is None or tetto <= 0:
        return posta
    return max(0, min(posta, tetto - saldo_vincitore))
