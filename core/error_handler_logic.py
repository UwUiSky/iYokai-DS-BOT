"""
core/error_handler_logic.py
==============================
Logica pura del cooldown per gli alert DM dell'error handler globale
(SPEC.md §1.6). Stesso principio di core/memory_guard_logic.py: un
errore non catturato in un evento potrebbe ripetersi decine di volte
al minuto (es. un listener che fallisce ad ogni messaggio durante un
raid) — senza un cooldown, l'owner riceverebbe un DM per ognuno.

Nota sulla duplicazione: questo è il QUARTO cooldown "è passato
abbastanza tempo dall'ultima volta?" nel progetto (gli altri:
can_appeal in spam_trap_logic.py, can_claim_daily/work in
leveling_logic.py, should_send_alert in memory_guard_logic.py). Sono
abbastanza diversi nel contesto (soglie diverse, alcuni globali
altri per-utente) da non consolidarli qui senza rischiare di rompere
codice già testato altrove — segnalato esplicitamente per una futura
sessione di refactoring, non nascosto.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Più breve del cooldown di Memory Guard (30 minuti): un errore in un
# evento è più probabile che segnali qualcosa di specifico e
# azionabile subito, a differenza della RAM che sale gradualmente.
ERROR_ALERT_COOLDOWN_SECONDS = 15 * 60


def should_alert_owner(
    last_alert_at: datetime | None, now: datetime | None = None
) -> bool:
    """
    True se è passato abbastanza tempo dall'ultimo alert per QUESTO
    specifico tipo di evento (il chiamante tiene un cooldown separato
    per ogni event_method — vedi main.py — così un errore ripetuto in
    on_message non silenzia gli alert per un errore diverso in
    on_member_join).
    """
    if last_alert_at is None:
        return True
    current = now or datetime.now(timezone.utc)
    return (current - last_alert_at) >= timedelta(seconds=ERROR_ALERT_COOLDOWN_SECONDS)
