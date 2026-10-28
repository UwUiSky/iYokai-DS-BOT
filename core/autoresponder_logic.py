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
    corpo = r"\S*".join(re.escape(pezzo) for pezzo in t.split("*"))
    if modo == "esatta":
        return re.fullmatch(corpo, m) is not None
    return re.search(rf"(?<!\w){corpo}(?!\w)", m) is not None


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
