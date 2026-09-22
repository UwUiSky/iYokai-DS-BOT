"""
core/giveaway_logic.py
==========================
Logica pura del giveaway (SPEC.md §15.5, con requisiti di ruolo/
livello). random.Random iniettato dal chiamante — mai chiamato
random.sample() direttamente qui dentro — così la selezione dei
vincitori resta deterministica e testabile con un seed fisso.
"""

from __future__ import annotations

import random


def pick_winners(entries: list[int], winners_count: int, rng: random.Random) -> list[int]:
    """
    Estrae fino a winners_count vincitori SENZA ripetizioni tra gli
    ID già partecipanti. Se ci sono meno partecipanti dei vincitori
    richiesti, li vincono tutti (non ha senso "estrarre" più
    partecipanti di quanti ce ne siano).
    """
    if not entries:
        return []
    quanti = min(winners_count, len(entries))
    return rng.sample(entries, quanti)


def is_eligible(
    user_level: int,
    user_role_ids: set[int],
    min_level: int,
    required_role_id: int | None,
) -> bool:
    """
    Vero se l'utente soddisfa i requisiti per partecipare — entrambi
    i requisiti (livello E ruolo) se presenti, non uno a scelta:
    un giveaway "livello 10 + ruolo Veterano" richiede entrambi,
    altrimenti il secondo requisito configurato non avrebbe senso.
    """
    if user_level < min_level:
        return False
    if required_role_id is not None and required_role_id not in user_role_ids:
        return False
    return True
