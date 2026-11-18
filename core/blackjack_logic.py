"""
core/blackjack_logic.py
=======================
Regole pure del blackjack contro il banco (ECO-088, ECO-089): mazzo da 52, il banco si ferma su tutti i 17,
blackjack naturale paga 3 a 2, raddoppio sulle prime due carte, resa (torna metà puntata). Il caso arriva
da fuori (`rng`). Le carte sono numeri 1-13 (1 = asso, 11-13 = figure da 10).
Funzioni coperte: ECO-088, ECO-089
"""

from __future__ import annotations

import random

SIMBOLI = {1: "A", 11: "J", 12: "Q", 13: "K"}


def nuovo_mazzo(rng: random.Random) -> list[int]:
    mazzo = [v for v in range(1, 14) for _ in range(4)]
    rng.shuffle(mazzo)
    return mazzo


def valore(mano: list[int]) -> int:
    """Il miglior totale (l'asso vale 11 finché non si sfora)."""
    totale = sum(min(c, 10) for c in mano)
    if 1 in mano and totale + 10 <= 21:
        totale += 10
    return totale


def e_blackjack(mano: list[int]) -> bool:
    return len(mano) == 2 and valore(mano) == 21


def mostra(mano: list[int]) -> str:
    return " ".join(SIMBOLI.get(c, str(c)) for c in mano)


def gioca_banco(mano: list[int], mazzo: list[int]) -> list[int]:
    """Il banco pesca finché ha meno di 17."""
    while valore(mano) < 17:
        mano.append(mazzo.pop())
    return mano


def restituzione(giocatore: list[int], banco: list[int], puntata: int) -> int:
    """
    Monete che tornano al giocatore per la puntata `puntata` (già raddoppiata se serve): 0 se perde,
    `puntata` se pareggia, il doppio se vince, 2,5 volte per il blackjack naturale (arrotondato per difetto).
    """
    g, b = valore(giocatore), valore(banco)
    if g > 21:
        return 0
    if e_blackjack(giocatore) and not e_blackjack(banco):
        return puntata * 5 // 2
    if b > 21 or g > b:
        return puntata * 2
    if g == b:
        return puntata
    return 0


def restituzione_resa(puntata: int) -> int:
    """ECO-089: arrendersi restituisce metà puntata (per difetto)."""
    return puntata // 2
