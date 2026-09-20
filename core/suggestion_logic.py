"""
core/suggestion_logic.py
===========================
Logica pura del Suggestion System (SPEC.md §14.14 — per i server
clienti, distinto da §14.8 che manda richieste al server dello
sviluppatore). Solo lo stato di una suggestion, nessuna dipendenza
da Discord.
"""

from __future__ import annotations

PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"

VALID_STATUSES = (PENDING, APPROVED, REJECTED)


def can_decide(current_status: str) -> bool:
    """
    Solo una suggestion ancora "pending" può essere approvata o
    rifiutata — una volta decisa, resta decisa. Evita che un secondo
    membro dello staff sovrascriva silenziosamente la decisione di un
    altro cliccando di nuovo il bottone (es. due moderatori online
    nello stesso momento).
    """
    return current_status == PENDING
