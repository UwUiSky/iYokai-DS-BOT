"""
core/suoni_ruoli_logic.py
=========================
Chi può far partire un suono della soundboard (`/music suono`): per ogni suono un elenco di ruoli «consenti» e
uno di ruoli «vieta» (massimo 20 in tutto). Regola: chi ha un ruolo vietato non può; se c'è almeno un ruolo
consentito serve averne uno; senza regole il suono è di tutti. Chi ha il permesso di amministratore passa sempre.
Funzioni coperte: SPEC §23 (FUN-076; B11 di #131)
Dipende da: core/repositories/suoni_ruoli_repo.py
"""

from __future__ import annotations

MAX_RUOLI_PER_SUONO = 20
MODI = ("consenti", "vieta")


def puo_suonare(regole: list[tuple[int, str]], ruoli_utente: set[int], amministratore: bool = False) -> bool:
    if amministratore or not regole:
        return True
    if any(modo == "vieta" and ruolo in ruoli_utente for ruolo, modo in regole):
        return False
    consentiti = {ruolo for ruolo, modo in regole if modo == "consenti"}
    return not consentiti or bool(consentiti & ruoli_utente)
