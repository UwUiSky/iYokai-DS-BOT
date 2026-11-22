"""
core/negozio_logic.py
=====================
Regole pure del negozio avanzato: prezzo effettivo con lo sconto di un'offerta lampo (un solo punto di calcolo,
usato dalla lista, dalla conferma e dalla scrittura dell'acquisto) e scelta degli oggetti che ruotano.
Funzioni coperte: ECO-075, ECO-076
"""

from __future__ import annotations

import hashlib
from datetime import date

MAX_RICETTE = 25
MAX_INGREDIENTI = 5
MAX_ROTAZIONE = 25
DURATA_MASSIMA_OFFERTA_MIN = 7 * 24 * 60


def prezzo_con_sconto(base: int, sconto_pct: int | None) -> int:
    """Prezzo effettivo: mai sotto 1 moneta, sconto limitato a 1-90%."""
    if not sconto_pct:
        return base
    sconto = min(max(sconto_pct, 1), 90)
    return max(1, base - base * sconto // 100)


def scelti_rotazione(ids: list[int], guild_id: int, giorno: date, quanti: int) -> set[int]:
    """Gli oggetti in vetrina oggi: ordine fissato da server e data, uguale per tutti e per tutto il giorno."""
    if quanti <= 0:
        return set(ids)  # rotazione spenta: tutti
    ordinati = sorted(ids, key=lambda i: hashlib.sha256(f"{guild_id}:{giorno.isoformat()}:{i}".encode()).digest())
    return set(ordinati[:quanti])
