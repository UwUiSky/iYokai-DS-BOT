"""
core/setup_guidato_logic.py
===========================
Logica pura del setup guidato (`/admin-bot setup guidato`): primo setup o modifica di uno già fatto, e cosa è
davvero cambiato rispetto a prima. Le scritture stanno negli stessi punti unici dei comandi (D16).
Funzioni coperte: SPEC §2.2 (UTL-121; D124)
Dipende da: core/setup_wizard_logic.py
"""

from __future__ import annotations

from core.setup_wizard_logic import moduli_da_scrivere

MODO_PRIMO = "primo"
MODO_MODIFICA = "modifica"


def modo_setup(ruoli_attuali: dict[str, int | None], moduli_attuali: dict[str, bool]) -> str:
    """«modifica» se un ruolo del bot è già scelto o qualche modulo è già acceso, altrimenti «primo»."""
    if any(ruoli_attuali.values()) or any(moduli_attuali.values()):
        return MODO_MODIFICA
    return MODO_PRIMO


def ruoli_cambiati(iniziali: dict[str, int | None], scelti: dict[str, int | None]) -> list[tuple[str, int | None]]:
    """Solo i ruoli il cui valore è davvero diverso da quello di partenza."""
    return [(tipo, nuovo) for tipo, nuovo in scelti.items() if iniziali.get(tipo) != nuovo]


def moduli_cambiati(iniziali: dict[str, bool], scelti: dict[str, bool]) -> list[tuple[str, bool]]:
    return moduli_da_scrivere(iniziali, scelti)
