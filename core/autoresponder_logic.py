"""
core/autoresponder_logic.py
===========================
Quando un messaggio fa scattare una risposta automatica (NF-10, SPEC §14.7):
corrispondenza esatta o parziale (parola intera, senza espressioni
regolari), jolly `*` dentro la parola, canale e ruolo come condizioni.
Funzioni pure.
Funzioni coperte: SPEC §14.7 (NF-10)
"""

from __future__ import annotations

import re
from typing import Iterable

MAX_RISPOSTE = 50  # per server
MAX_TRIGGER = 100
MAX_RISPOSTA = 2000
PAUSA_CANALE_SECONDI = 10
MODI = ("parziale", "esatta")
MAX_JOLLY = 5  # asterischi per parola


def jolly_validi(trigger: str) -> bool:
    """Il jolly `*` sostituisce un pezzo di parola. Servono lettere vere e al massimo MAX_JOLLY asterischi."""
    return trigger.count("*") <= MAX_JOLLY and bool(trigger.replace("*", "").strip())


def trigger_corrisponde(trigger: str, modo: str, messaggio: str) -> bool:
    """Senza badare alle maiuscole. "parziale": il trigger è una parola o frase intera nel messaggio. `*` = pezzo di parola."""
    t = trigger.strip().lower()
    m = messaggio.strip().lower()
    if not t or not m:
        return False
    if not jolly_validi(t):
        return False
    pezzi = t.split("*")
    if modo == "esatta":
        return m.startswith(pezzi[0]) and _da_qui(pezzi, m, 0, True)
    i = m.find(pezzi[0])
    while i >= 0:
        if (i == 0 or _PAROLA.match(m, i - 1) is None) and _da_qui(pezzi, m, i, False):
            return True
        if i >= len(m):
            break
        i = m.find(pezzi[0], i + 1)
    return False


_SPAZIO = re.compile(r"\s")
_PAROLA = re.compile(r"\w")


def _primo_spazio(m: str, da: int) -> int:
    trovato = _SPAZIO.search(m, da)
    return trovato.start() if trovato else len(m)


def _da_qui(pezzi: list[str], m: str, inizio: int, esatta: bool) -> bool:
    """
    I pezzi del trigger dalla posizione `inizio` (il primo c'è già). Ogni jolly è un tratto senza
    spazi. Si prende sempre il pezzo più a sinistra: niente regex con jolly annidati, che con un
    messaggio lungo bloccherebbero il bot (tempo esponenziale).
    """
    pos = inizio + len(pezzi[0])
    if len(pezzi) == 1:
        return pos == len(m) if esatta else (pos == len(m) or _PAROLA.match(m, pos) is None)
    for pezzo in pezzi[1:-1]:
        j = m.find(pezzo, pos)
        if j < 0 or j > _primo_spazio(m, pos):
            return False
        pos = j + len(pezzo)
    ultimo, limite = pezzi[-1], _primo_spazio(m, pos)
    if esatta:
        j = len(m) - len(ultimo)
        return pos <= j <= limite and m.endswith(ultimo)
    trovato = re.compile(re.escape(ultimo) + r"(?!\w)").search(m, pos)
    return trovato is not None and trovato.start() <= limite


def scegli_risposta(regole: Iterable, messaggio: str, canale_id: int, ruoli_autore: set[int]):
    """
    La regola che scatta (una sola per messaggio): la più specifica, cioè col trigger
    più lungo; a parità la più vecchia. None se nessuna.
    """
    candidate = []
    for r in regole:
        if r.channel_id is not None and r.channel_id != canale_id:
            continue
        if r.role_id is not None and r.role_id not in ruoli_autore:
            continue
        if trigger_corrisponde(r.trigger, r.match_mode, messaggio):
            candidate.append(r)
    if not candidate:
        return None
    return sorted(candidate, key=lambda r: (-len(r.trigger), r.id))[0]
