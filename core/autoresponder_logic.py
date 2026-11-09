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
from functools import lru_cache
from typing import Iterable

MAX_RISPOSTE = 50  # per server
MAX_TRIGGER = 100
MAX_REGEX = 200
MAX_RESTO = 500  # caratteri di {resto} che finiscono nella risposta
MAX_GLOBALI = 20
MAX_RISPOSTA = 2000
PAUSA_CANALE_SECONDI = 10
MODI = ("parziale", "esatta", "inizia", "regex")
MAX_JOLLY = 5  # asterischi per parola


def jolly_validi(trigger: str) -> bool:
    """Il jolly `*` sostituisce un pezzo di parola. Servono lettere vere e al massimo MAX_JOLLY asterischi."""
    return trigger.count("*") <= MAX_JOLLY and bool(trigger.replace("*", "").strip())


def regex_valida(modello: str) -> str | None:
    """None se l'espressione va bene (RE2: niente backtracking, non può bloccare il bot); altrimenti il motivo."""
    if not 1 <= len(modello) <= MAX_REGEX:
        return "lunghezza"
    try:
        _compila(modello)
    except Exception:
        return "sintassi"
    return None


@lru_cache(maxsize=512)
def _compila(modello: str):
    import re2

    opzioni = re2.Options()
    opzioni.max_mem = 1 << 19  # mezzo MiB: un'espressione enorme viene rifiutata
    opzioni.case_sensitive = False
    return re2.compile(modello, opzioni)


def resto_dopo(trigger: str, messaggio: str) -> str:
    """Il testo che segue l'innesco nel modo «inizia con» (senza spazi attorno, tagliato)."""
    return messaggio.strip()[len(trigger.strip()):].strip()[:MAX_RESTO]


def trigger_corrisponde(trigger: str, modo: str, messaggio: str) -> bool:
    """Senza badare alle maiuscole. "parziale": il trigger è una parola o frase intera nel messaggio. `*` = pezzo di parola."""
    if modo == "regex":
        try:
            return bool(messaggio) and _compila(trigger.strip()).search(messaggio[:2000]) is not None
        except Exception:
            return False
    t = trigger.strip().lower()
    m = messaggio.strip().lower()
    if not t or not m:
        return False
    if modo == "inizia":  # all'inizio del messaggio, e l'innesco finisce a fine parola
        return m.startswith(t) and (len(m) == len(t) or not (m[len(t) - 1].isalnum() and m[len(t)].isalnum()))
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
