"""
core/suoni_ruoli_logic.py
=========================
Chi può far partire un suono della soundboard (`/music suono`): per ogni suono un elenco di ruoli «consenti» e
uno di ruoli «vieta» (massimo 20 in tutto). Tolto l'ultimo «consenti», il suono resta bloccato. Regola: chi ha un ruolo vietato non può; se c'è almeno un ruolo
consentito serve averne uno; senza regole il suono è di tutti. Chi ha il permesso di amministratore passa sempre.
Funzioni coperte: SPEC §23 (FUN-076; B11 di #131)
Dipende da: core/repositories/suoni_ruoli_repo.py
"""

from __future__ import annotations

MAX_RUOLI_PER_SUONO = 20
MODI = ("consenti", "vieta")
# Riga di blocco: resta quando si toglie l'ultimo ruolo «consenti». Nessun utente ha il ruolo 0, quindi il suono
# resta chiuso a tutti (tranne gli amministratori) finché lo staff non sceglie un ruolo nuovo.
RUOLO_BLOCCO = 0


def puo_suonare(regole: list[tuple[int, str]], ruoli_utente: set[int], amministratore: bool = False) -> bool:
    if amministratore or not regole:
        return True
    if any(modo == "vieta" and ruolo in ruoli_utente for ruolo, modo in regole):
        return False
    consentiti = {ruolo for ruolo, modo in regole if modo == "consenti"}
    return not consentiti or bool(consentiti & ruoli_utente)
