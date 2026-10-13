"""
core/fun_logic.py
====================
Logica pura di Ship (SPEC.md §16.5), Rate (§16.7) e Misura (§23.16, NF-40). Deterministica
via hash, non random.randint() ad ogni chiamata — stessa coppia di
utenti o stesso testo devono dare sempre lo stesso risultato,
altrimenti /fun ship @a @b darebbe un numero diverso ogni volta che
qualcuno lo richiama, che sembra un bug più che una feature scherzosa
(la gente si aspetta un risultato "loro", stabile, non un dado).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date


def compute_ship_percentage(user_id_a: int, user_id_b: int) -> int:
    """
    0-100, simmetrico: ship(a, b) == ship(b, a), perché l'ordine in
    cui i due utenti vengono menzionati nel comando non deve cambiare
    il risultato — ordiniamo gli ID prima di calcolare l'hash.
    """
    a, b = sorted((user_id_a, user_id_b))
    chiave = f"{a}-{b}".encode("utf-8")
    hash_bytes = hashlib.sha256(chiave).digest()
    return hash_bytes[0] % 101


def ship_flavor_text(percentage: int) -> str:
    if percentage >= 90:
        return "Anime gemelle. 💍"
    if percentage >= 70:
        return "C'è del potenziale! 💕"
    if percentage >= 40:
        return "Potrebbe funzionare... o no. 🤔"
    if percentage >= 15:
        return "Meglio restare amici. 😅"
    return "Acqua e olio. 🧊"


def compute_rate_score(text: str) -> int:
    """0-10, deterministico sul testo normalizzato (spazi ai bordi e
    maiuscole/minuscole non devono cambiare il voto di "Pizza" contro
    " pizza ")."""
    chiave = text.strip().lower().encode("utf-8")
    hash_bytes = hashlib.sha256(chiave).digest()
    return hash_bytes[0] % 11


def rate_flavor_text(score: int) -> str:
    if score >= 9:
        return "Perfezione assoluta. 🌟"
    if score >= 7:
        return "Niente male! 👍"
    if score >= 4:
        return "Nella media. 🤷"
    if score >= 1:
        return "Si può migliorare. 😬"
    return "Un disastro totale. 💀"


# ----------------------------------------------------------------------
# Misura (NF-40): misuratore a tema libero, alternativa neutra a SPEC §16.6.
# ----------------------------------------------------------------------
MAX_TEMA_MISURA = 60

# Radici di parole che indicano caratteristiche protette (orientamento, origine,
# religione, salute, disabilità…): un misuratore non le giudica.
_RADICI_VIETATE = (
    "gay", "lesb", "omosess", "eterosess", "bisess", "transess", "transgender", "trans ",
    "queer", "lgbt", "razza", "razzi", "etnia", "etnic", "negro",
    "religio", "musulman", "islam", "ebre", "cristian", "cattolic", "ateo", "ateis",
    "buddis", "induis", "disabil", "handicap", "autis", "malat", "depress", "tumor",
    "cancro", "immigrat", "straniero", "nazional", "politic", "comunist", "fascist",
    "sessualit", "orientamento",
    "race", "racial", "ethnic", "religion", "muslim", "jewish", "christian", "disabled",
    "sexuality", "straight",
)


def _normalizza_tema(tema: str) -> str:
    senza_accenti = unicodedata.normalize("NFKD", tema).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", senza_accenti).strip().lower()


def tema_ammesso(tema: str) -> bool:
    """Vero se il tema non è vuoto e non misura una caratteristica protetta."""
    normale = _normalizza_tema(tema)
    if not normale:
        return False
    cercato = normale + " "
    return not any(radice in cercato for radice in _RADICI_VIETATE)


def compute_misura(user_id: int, tema: str, giorno: date) -> int:
    """
    0-100, stabile per la stessa persona, lo stesso tema e lo stesso giorno
    (domani il risultato cambia). Maiuscole e spazi nel tema non contano.
    """
    chiave = f"{user_id}|{_normalizza_tema(tema)}|{giorno.isoformat()}".encode("utf-8")
    return hashlib.sha256(chiave).digest()[0] % 101
