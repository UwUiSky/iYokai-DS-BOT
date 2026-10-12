"""
core/premium_cache.py
=====================
Punto unico per dire "il premium di questo server è cambiato" (#145).

Chi tiene in memoria un verdetto sul premium (oggi i log avanzati, 60 s)
si registra qui con `registra_invalidatore`. Chi cambia il premio
(whitelist, cassa, abbonamenti, flag del modulo) chiama
`invalida_cache_premium`: tutti i verdetti in memoria vengono dimenticati
e lo sblocco o la revoca valgono subito, non dopo il TTL.

Modulo senza dipendenze: lo importano database.py, i repository e i cog
senza rischio di import circolari.
"""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger("iyokai.premium")

Invalidatore = Callable[[int | None], None]

_invalidatori: list[Invalidatore] = []


def registra_invalidatore(funzione: Invalidatore) -> Invalidatore:
    """Registra una funzione `f(guild_id | None)`. Registrare due volte la stessa non la duplica."""
    if funzione not in _invalidatori:
        _invalidatori.append(funzione)
    return funzione


def invalida_cache_premium(guild_id: int | None = None) -> None:
    """
    Dimentica i verdetti premium in memoria: di un server, o di tutti se
    `guild_id` è None (cambio della flag di un modulo). Un invalidatore che
    fallisce non ferma gli altri e non rompe chi ha cambiato il premio.
    """
    for funzione in tuple(_invalidatori):
        try:
            funzione(guild_id)
        except Exception:  # noqa: BLE001 - la cache non deve far fallire una scrittura
            logger.exception("Invalidatore del premium fallito: %r", funzione)
