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


# --- opzioni del server (D69, B7) ---
ESITI = ("modifica", "nuovo")
EMOJI_VOTO_SU = "👍"


def colore_attuale(stato: str, voti_su: int, soglia: int, colore_soglia: str | None, colore_stato: int) -> int:
    """Il colore dell'embed: quello della soglia se i voti sono arrivati, solo finché è in attesa."""
    if stato in APERTI and soglia > 0 and colore_soglia and voti_su >= soglia:
        return int(colore_soglia[1:], 16)
    return colore_stato


def fuori_dal_canale_unico(canale_id: int, solo_canale_id: int | None) -> bool:
    """True se il server ha scelto un solo canale e questo non è quello."""
    return solo_canale_id is not None and canale_id != solo_canale_id
