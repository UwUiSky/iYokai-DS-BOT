"""
core/music_fleet_logic.py
=============================
Logica pura di instradamento multi-istanza Music (SPEC.md §9.1/9.2).
Architettura chiarita dall'utente: UN SOLO punto di ingresso comandi
(il bot principale), ma l'esecuzione vera (join vocale, riproduzione)
avviene su una delle 5 istanze separate (MUSIC_TOKENS, già dichiarati
in config.py) — quella libera per prima. Il bot principale non entra
MAI in un canale per /play: la sua unica funzione vocale è lo
streaming 24/7 dalla playlist personale dell'utente, un comando
completamente separato (vedi cogs/music/player.py).
"""

from __future__ import annotations

TOTAL_WORKERS = 5


def find_free_worker(occupied_workers: set[int], total_workers: int = TOTAL_WORKERS) -> int | None:
    """
    Il primo indice di worker (1-based, corrisponde a MUSIC_TOKENS[i-1]
    in config.py) NON presente in occupied_workers — "quella libera
    per prima", come richiesto esplicitamente. None se tutti occupati
    (nessuna sessione disponibile in questo momento).
    """
    for indice in range(1, total_workers + 1):
        if indice not in occupied_workers:
            return indice
    return None
