"""
core/escalation_ladder_logic.py
==================================
Logica pura della Smart AutoMod Escalation Ladder (BACKLOG.md §11,
estensione di SPEC.md §6 AutoMod). Discord's AutoMod nativo esegue
SEMPRE la stessa azione ad ogni trigger di una regola (non ha un
concetto di "seconda volta più severo") — l'escalation è quindi
gestita lato bot, tramite l'evento on_automod_action
(cogs/automod/escalation.py), contando le infrazioni per utente con
una finestra di reset per il "reset dopo buona condotta".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class LadderStep:
    level: int
    action_type: str  # "warn" | "timeout" | "kick" | "ban"
    duration_seconds: int | None = None  # solo per "timeout"


def should_reset_violation_count(
    last_violation_at: datetime | None, reset_after_days: int, now: datetime | None = None
) -> bool:
    """
    True se è passato abbastanza tempo di buona condotta dall'ultima
    infrazione perché il contatore debba ripartire da zero. Nessuna
    infrazione precedente (None) non è "da resettare" — semplicemente
    non c'è ancora nulla da contare, il chiamante tratta questo caso
    a parte.
    """
    if last_violation_at is None:
        return False
    current = now or datetime.now(last_violation_at.tzinfo)
    return (current - last_violation_at) >= timedelta(days=reset_after_days)


def next_violation_count(current_count: int, should_reset: bool) -> int:
    """Il contatore dopo QUESTA infrazione — non prima di applicarla."""
    if should_reset:
        return 1
    return current_count + 1


def get_ladder_action(violation_count: int, ladder: list[LadderStep]) -> LadderStep | None:
    """
    Trova il gradino della scala corrispondente a questo numero di
    infrazione. Se il conteggio supera l'ultimo gradino definito
    (es. scala di 3 livelli, 5a infrazione), si applica L'ULTIMO
    gradino — il più severo — invece di non fare nulla: un utente
    recidivo oltre la scala definita non deve "uscire" dal sistema di
    escalation, deve restare al massimo livello configurato.

    None se la scala è vuota (nessuna escalation configurata).
    """
    if not ladder:
        return None

    ladder_ordinata = sorted(ladder, key=lambda step: step.level)

    per_livello = {step.level: step for step in ladder_ordinata}
    if violation_count in per_livello:
        return per_livello[violation_count]

    # Oltre l'ultimo gradino definito: resta sull'ultimo (il più
    # severo), non su un gradino a caso o su "nessuna azione".
    return ladder_ordinata[-1]
