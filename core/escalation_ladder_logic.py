"""
core/escalation_ladder_logic.py
==================================
Logica pura della Smart AutoMod Escalation Ladder (BACKLOG.md §11,
estensione di SPEC.md §6 AutoMod). Discord's AutoMod nativo esegue
SEMPRE la stessa azione ad ogni trigger di una regola (non ha un
concetto di "seconda volta più severo") — l'escalation è quindi
gestita lato bot, tramite l'evento on_automod_action
(cogs/automod/escalation.py). Qui c'è la scelta del gradino; il
conteggio delle infrazioni (con il reset dopo buona condotta) è nel
database, in core/repositories/escalation_repo.py.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

# Il timeout di Discord arriva al massimo a 28 giorni.
MAX_TIMEOUT_SECONDI = 28 * 24 * 3600


@dataclass(frozen=True)
class LadderStep:
    level: int
    action_type: str  # "warn" | "timeout" | "kick" | "ban"
    duration_seconds: int | None = None  # solo per "timeout"


def get_ladder_action(
    violation_count: int,
    ladder: list[LadderStep],
    moltiplicatore: float = 1.0,
    tetto_strike: int = 5,
) -> LadderStep | None:
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
    ultimo = ladder_ordinata[-1]
    return timeout_che_cresce(ultimo, violation_count - ultimo.level, moltiplicatore, tetto_strike)


def timeout_che_cresce(
    step: LadderStep, ricadute: int, moltiplicatore: float, tetto_strike: int
) -> LadderStep:
    """
    AMD-070: un timeout ripetuto dopo l'ultimo gradino dura
    base × moltiplicatore^ricadute, con le ricadute contate fino a
    `tetto_strike` e la durata entro i 28 giorni di Discord.
    Moltiplicatore 1 (o un gradino che non è un timeout): nessun cambio.
    """
    if step.action_type != "timeout" or not step.duration_seconds or moltiplicatore <= 1:
        return step
    ricadute = max(0, min(ricadute, tetto_strike))
    durata = int(step.duration_seconds * moltiplicatore**ricadute)
    return replace(step, duration_seconds=min(durata, MAX_TIMEOUT_SECONDI))
