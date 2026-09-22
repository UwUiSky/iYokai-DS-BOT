"""
core/drop_logic.py
======================
Logica pura dei "drop" di coin (SPEC.md §15.6) — una piccola
probabilità, ad ogni messaggio idoneo, che compaia un drop di coin
da raccogliere (primo che clicca vince). Nessuna sorgente di
casualità qui dentro: il chiamante estrae il numero (random.random(),
random.randint()) e lo passa già pronto, così questa logica resta
deterministica e testabile senza mockare il modulo random.
"""

from __future__ import annotations

DEFAULT_DROP_CHANCE = 0.005  # 0.5% per messaggio idoneo — raro
# abbastanza da restare una sorpresa, non un evento a ogni scambio
# di messaggi in un server attivo.

DEFAULT_MIN_COINS = 10
DEFAULT_MAX_COINS = 50


def should_trigger_drop(roll: float, chance: float = DEFAULT_DROP_CHANCE) -> bool:
    """roll è un numero in [0, 1) già estratto dal chiamante."""
    return roll < chance
