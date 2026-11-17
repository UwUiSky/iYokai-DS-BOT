"""
core/leveling_ruoli_classifica_logic.py
=======================================
Logica pura dei ruoli di classifica: chi sta in quale fascia (primo, primi 3, primi 10) e cosa dare o
togliere. Niente oggetti discord.py.
Funzioni coperte: SPEC §15 (LIV-044, 045; catalogo #124)
"""

from __future__ import annotations

FASCE = (1, 3, 10)


def fascia_di_posizione(posizione: int, fasce) -> int | None:
    """La fascia più stretta, tra quelle configurate, che contiene la posizione (1 = primo)."""
    for f in sorted(fasce):
        if posizione <= f:
            return f
    return None


def fasce_degli_utenti(classifica: list[int], fasce) -> dict[int, int]:
    """{utente: fascia} dalla classifica in ordine. Una persona ha una sola fascia: la più stretta."""
    risultato: dict[int, int] = {}
    for posizione, utente in enumerate(classifica, start=1):
        f = fascia_di_posizione(posizione, fasce)
        if f is not None and utente not in risultato:
            risultato[utente] = f
    return risultato


def differenze(
    desiderate: dict[int, int], possessori: dict[int, set[int]]
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """
    (da dare, da togliere) come coppie (utente, fascia). `possessori`: {fascia: utenti che hanno oggi
    il ruolo di quella fascia}. Una persona che cambia fascia riceve il ruolo nuovo e perde il vecchio.
    """
    da_dare = sorted((u, f) for u, f in desiderate.items() if u not in possessori.get(f, set()))
    da_togliere = sorted(
        (u, f) for f, utenti in possessori.items() for u in utenti if desiderate.get(u) != f
    )
    return da_dare, da_togliere
