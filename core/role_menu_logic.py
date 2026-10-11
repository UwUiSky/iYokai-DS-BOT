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

# DA FARE (issue #85, fase F9): NF-14, Modalità dei reaction roles. Vedi
#   revisione/02-piano/NUOVE_FUNZIONI.md.

from __future__ import annotations

import re
import unicodedata
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


# LIM-17 (M 10.7): l'emoji di un'opzione si controlla quando l'admin la scrive,
# non quando Discord la rifiuta. Personalizzata: <:nome:id> o <a:nome:id>.
_EMOJI_PERSONALIZZATA = re.compile(r"^<a?:[A-Za-z0-9_]{2,32}:(\d{15,22})>$")
_EMOJI_TASTO = re.compile("^[0-9#*]\ufe0f?\u20e3$")
MAX_LUNGHEZZA_EMOJI_UNICODE = 20


def id_emoji_personalizzata(testo: str) -> int | None:
    """L'ID di un'emoji personalizzata scritta come <:nome:id>, altrimenti None."""
    trovata = _EMOJI_PERSONALIZZATA.match(testo)
    return int(trovata.group(1)) if trovata else None


def valida_emoji(testo: str) -> bool:
    """
    True se `testo` è UNA emoji: personalizzata ben formata, un tasto
    (1️⃣) o una sequenza unicode di simboli (bandiere, tonalità, ZWJ).
    Lettere, cifre, spazi e testo libero sono rifiutati. Se l'emoji
    personalizzata esiste davvero lo dice poi Discord / la cache del bot.
    """
    if not testo or len(testo) > MAX_LUNGHEZZA_EMOJI_UNICODE and not testo.startswith("<"):
        return False
    if testo.startswith("<"):
        return _EMOJI_PERSONALIZZATA.match(testo) is not None
    if _EMOJI_TASTO.match(testo):
        return True
    for carattere in testo:
        categoria = unicodedata.category(carattere)
        if ord(carattere) < 128 or not (categoria[0] in ("S", "M") or categoria == "Cf"):
            return False
    return unicodedata.category(testo[0])[0] == "S"
