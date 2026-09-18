"""
core/role_menu_logic.py
==========================
Logica pura dei Role Menu (SPEC.md §14.1-14.3: Reaction Roles,
Button Roles, Select Menu Roles). Le tre modalità condividono lo
stesso modello dati (un "menu" con delle "opzioni", ciascuna legata
a un ruolo) e buona parte della logica — cambia solo COME l'utente
interagisce (reazione emoji, click bottone, scelta da tendina).

Nessuna dipendenza da discord.py qui: solo insiemi di ID e stringhe.
"""

from __future__ import annotations

from typing import Literal

# Limiti pratici per modalità — non tutti sono limiti hard dell'API
# Discord (i bottoni sì: 25 per messaggio, 5 per riga; il select
# menu sì: 25 opzioni), la reazione è un limite di usabilità nostro
# (oltre una ventina di reazioni su un messaggio diventa scomodo da
# leggere per un utente, anche se Discord tecnicamente non lo vieta).
MODE_MAX_OPTIONS: dict[str, int] = {
    "reaction": 20,
    "button": 25,
    "select": 25,
}


def can_add_option(current_option_count: int, mode: str) -> bool:
    limite = MODE_MAX_OPTIONS.get(mode, 25)
    return current_option_count < limite


def compute_toggle_action(member_has_role: bool) -> Literal["add", "remove"]:
    """
    Per le modalità bottone e reazione (con toggle attivo): se il
    membro ha già il ruolo, l'interazione lo rimuove; altrimenti lo
    assegna. Logica identica per entrambe le modalità, isolata qui
    una volta sola.
    """
    return "remove" if member_has_role else "add"


def compute_select_sync(
    current_member_role_ids: set[int],
    menu_role_ids: set[int],
    selected_role_ids: set[int],
) -> tuple[set[int], set[int]]:
    """
    Per la modalità select: l'utente sceglie da una tendina quali
    ruoli (tra quelli del menu) vuole avere ORA — non è un toggle
    incrementale come bottone/reazione, è uno stato finale dichiarato
    in un colpo solo. Calcola quali ruoli aggiungere e quali togliere
    per portare il membro esattamente a quello stato, SENZA toccare
    ruoli che il membro ha ma che non appartengono a questo menu
    (un select di "colori preferiti" non deve mai rimuovere un ruolo
    di moderazione solo perché non è tra le opzioni scelte).

    Restituisce (da_aggiungere, da_rimuovere).
    """
    da_aggiungere = selected_role_ids - current_member_role_ids
    da_rimuovere = (menu_role_ids & current_member_role_ids) - selected_role_ids
    return da_aggiungere, da_rimuovere
