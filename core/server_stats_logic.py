"""
core/server_stats_logic.py
=============================
Logica pura di Server Stats (SPEC.md §14.18). Riduce una lista di
eventi join/leave (dal log eventi unificato, core/repositories/
event_log_repo.py) a un conteggio di variazione netta per giorno —
non tenta di ricostruire la popolazione storica assoluta del server
(richiederebbe di sapere il conteggio esatto al giorno zero, che non
abbiamo), mostra invece l'ANDAMENTO (quanti sono entrati/usciti ogni
giorno), che è quello che un grafico di crescita deve comunicare.
"""

from __future__ import annotations

from datetime import date, datetime


def compute_daily_net_change(
    events: list[tuple[datetime, str]],
) -> dict[date, int]:
    """
    events è una lista di (timestamp, event_type) — event_type deve
    essere "member_join" o "member_remove", qualunque altro valore
    viene ignorato silenziosamente (il chiamante può passare una
    lista mista senza doverla pre-filtrare).

    Restituisce {data: variazione_netta}, con SOLO i giorni che
    hanno avuto almeno un evento — un giorno senza eventi non compare
    (0 impliciti), il chiamante decide come trattare i buchi quando
    disegna il grafico.
    """
    variazioni: dict[date, int] = {}
    for timestamp, event_type in events:
        if event_type not in ("member_join", "member_remove"):
            continue
        giorno = timestamp.date()
        delta = 1 if event_type == "member_join" else -1
        variazioni[giorno] = variazioni.get(giorno, 0) + delta
    return variazioni


def fill_missing_days(daily_counts: dict[date, int], start: date, end: date) -> dict[date, int]:
    """
    Completa i buchi tra start e end (inclusi) con 0 — utile per
    disegnare un grafico con l'asse dei giorni continuo, senza salti
    che farebbero sembrare le barre più vicine di quanto siano in
    realtà.
    """
    risultato: dict[date, int] = {}
    giorno_corrente = start
    while giorno_corrente <= end:
        risultato[giorno_corrente] = daily_counts.get(giorno_corrente, 0)
        giorno_corrente = date.fromordinal(giorno_corrente.toordinal() + 1)
    return risultato
