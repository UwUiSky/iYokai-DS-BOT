"""
core/setup_wizard_logic.py
==============================
Logica pura del Wizard di configurazione guidata (SPEC.md §2.2) —
navigazione avanti/indietro tra gli step, nessuna dipendenza
Discord/DB.
"""

from __future__ import annotations


def clamp_step(index: int, total_steps: int) -> int:
    """Mantiene l'indice dello step dentro i limiti validi [0, total_steps - 1]."""
    if total_steps <= 0:
        raise ValueError("total_steps deve essere positivo.")
    return max(0, min(index, total_steps - 1))


def next_step(current: int, total_steps: int) -> int:
    return clamp_step(current + 1, total_steps)


def previous_step(current: int, total_steps: int) -> int:
    return clamp_step(current - 1, total_steps)


def is_last_step(current: int, total_steps: int) -> bool:
    return current >= total_steps - 1
