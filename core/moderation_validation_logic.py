"""
core/moderation_validation_logic.py
======================================
Logica pura per "reason obbligatorio" (SPEC.md §5.9, BACKLOG.md §5 —
coincide con una voce che Gemini ha proposto indipendentemente,
partendo dallo stesso SPEC.md, e che avevamo già segnato come nostra
stessa deviazione dallo schema originale: il campo reason era stato
reso opzionale in tutti i comandi, contraddicendo la specifica).
"""

from __future__ import annotations

MIN_REASON_LENGTH = 3


def is_valid_reason(reason: str) -> bool:
    """
    True se il motivo, ripulito degli spazi iniziali/finali, ha
    almeno MIN_REASON_LENGTH caratteri. Un motivo di soli spazi
    (" ") o troppo corto ("ok") non deve passare come se fosse un
    motivo reale — l'obbligo di reason serve a lasciare traccia
    utile, non solo a riempire un campo.
    """
    return len(reason.strip()) >= MIN_REASON_LENGTH
