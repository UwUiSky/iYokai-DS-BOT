"""
core/sticky_message_logic.py
===============================
Logica pura degli Sticky Messages (SPEC.md §14.13). Il problema da
risolvere non è "quando pubblicare" (sempre, alla configurazione) ma
"quando RI-pubblicare": ad ogni nuovo messaggio nel canale, ripetere
subito cancella+reinvia significherebbe due chiamate API per OGNI
messaggio in un canale attivo — spam di rate limit e via via più
lento quanto più il canale è vivo, esattamente al contrario di quello
che si vuole. Un debounce minimo tra una ripubblicazione e la
successiva risolve senza bisogno di una coda o di un worker dedicato.
"""

from __future__ import annotations

from datetime import datetime, timedelta

MIN_REPOST_INTERVAL_SECONDS = 5


def should_repost_sticky(
    last_reposted_at: datetime | None,
    now: datetime,
    min_interval_seconds: int = MIN_REPOST_INTERVAL_SECONDS,
) -> bool:
    """
    True se è passato abbastanza tempo dall'ultima ripubblicazione.
    Nessuna ripubblicazione precedente (None) è sempre un sì — il
    canale ha uno sticky configurato ma non ancora pubblicato la
    prima volta, non ha senso debounce-arlo.
    """
    if last_reposted_at is None:
        return True
    return (now - last_reposted_at) >= timedelta(seconds=min_interval_seconds)
