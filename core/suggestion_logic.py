"""
core/suggestion_logic.py
===========================
Logica pura del Suggestion System (SPEC.md §14.14 — per i server
clienti, distinto da §14.8 che manda richieste al server dello
sviluppatore): gli stati di un suggerimento e quali si possono ancora
cambiare (catalogo #128, UTL-135). Nessuna dipendenza da Discord.
"""

from __future__ import annotations

PENDING = "pending"
CONSIDERING = "considering"
APPROVED = "approved"
REJECTED = "rejected"
IMPLEMENTED = "implemented"

VALID_STATUSES = (PENDING, CONSIDERING, APPROVED, REJECTED, IMPLEMENTED)
# Stati da cui si può ancora decidere: in attesa o in valutazione.
APERTI = (PENDING, CONSIDERING)
# Il motivo scritto dallo staff (finisce nell'embed e nel DM).
MAX_MOTIVO = 512


def can_decide(current_status: str) -> bool:
    """
    Solo un suggerimento in attesa o in valutazione si può ancora
    decidere: una volta approvato, rifiutato o realizzato resta così.
    Evita che un secondo membro dello staff sovrascriva la decisione
    di un altro cliccando di nuovo.
    """
    return current_status in APERTI


def e_finale(status: str) -> bool:
    """Approvato, rifiutato o realizzato: i bottoni si tolgono."""
    return status not in APERTI
