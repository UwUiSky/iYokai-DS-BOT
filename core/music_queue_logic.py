"""
core/music_queue_logic.py
=============================
Logica pura della coda musicale (catalogo MUS, issue #126): chi ha messo
cosa, brano precedente, mescola solo i propri.
Nessuna dipendenza da discord.py o wavelink: lavora su liste di titoli e di
id utente. Chi ha richiesto un brano sta in `track.extras.requester_id`
(vedi `requester_of`).
"""

from __future__ import annotations

import random
from collections import Counter

from core.music_logic import truncate_title

MAX_SHARE_LINES = 5
MAX_HISTORY_SHOWN = 10


def requester_of(track) -> int | None:
    """L'id di chi ha messo il brano in coda; None se non si sa (radio, vecchie code)."""
    extras = getattr(track, "extras", None)
    if isinstance(extras, dict):
        valore = extras.get("requester_id")
    else:
        valore = getattr(extras, "requester_id", None)
    return valore if isinstance(valore, int) else None


def share_by_user(richiedenti: list[int | None]) -> list[tuple[int, int, int]]:
    """
    (id utente, brani, percentuale intera) dal più al meno presente. I
    brani senza richiedente noto non contano nella lista ma restano nel
    totale della percentuale.
    """
    totale = len(richiedenti)
    if totale == 0:
        return []
    conteggi = Counter(r for r in richiedenti if r is not None)
    righe = [(uid, n, round(100 * n / totale)) for uid, n in conteggi.items()]
    return sorted(righe, key=lambda r: (-r[1], r[0]))


def format_share(righe: list[tuple[int, int, int]], max_chars: int = 1024) -> str:
    """Testo per un campo di embed (1024): al massimo 5 utenti, sempre entro il limite."""
    testo = "\n".join(
        f"<@{uid}> — {n} {'brano' if n == 1 else 'brani'} ({pct}%)"
        for uid, n, pct in righe[:MAX_SHARE_LINES]
    )
    return truncate_title(testo, max_chars)


def previous_track_position(lunghezza_storico: int, c_e_un_corrente: bool = True) -> int | None:
    """
    L'indice nello storico del brano da riprendere. Con un brano in corso, lo
    storico lo contiene (wavelink lo aggiunge quando parte): il precedente e' il
    penultimo. A coda finita (nessun brano in corso) l'ultimo dello storico e' il
    brano appena finito: e' quello che si riprende. None se non c'e'.
    """
    if c_e_un_corrente:
        return lunghezza_storico - 2 if lunghezza_storico >= 2 else None
    return lunghezza_storico - 1 if lunghezza_storico >= 1 else None


def own_shuffle_order(
    richiedenti: list[int | None], user_id: int, rng: random.Random | None = None
) -> list[int]:
    """
    Nuovo ordine (indici della coda attuale) in cui SOLO i brani di
    `user_id` si scambiano di posto tra loro: gli altri restano dove sono.
    """
    rng = rng or random
    suoi = [i for i, r in enumerate(richiedenti) if r == user_id]
    mescolati = suoi[:]
    rng.shuffle(mescolati)
    ordine = list(range(len(richiedenti)))
    for posto, scelto in zip(suoi, mescolati):
        ordine[posto] = scelto
    return ordine
