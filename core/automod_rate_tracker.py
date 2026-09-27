"""
core/automod_rate_tracker.py
================================
Finestra mobile in memoria per i filtri AutoMod basati su un
conteggio nel tempo (messaggi/sticker/allegati ripetuti in pochi
secondi — SPEC.md §6.4/§6.6/§6.10). Deliberatamente NON persistito
su database: è uno stato "caldo" (secondi, non giorni), lo stesso
principio già usato per `core/invite_tracker.py` — una `BoundedCache`
con dimensione massima, così non cresce senza limiti con il numero
di server/utenti (SPEC.md §1.3 Memory Guard).

Una singola istanza condivisa (`rate_tracker` in fondo), usata da
`cogs/automod/automod_advanced.py`.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime

from core.bounded_cache import BoundedCache


class AutomodRateTracker:
    def __init__(self, max_size: int = 20_000) -> None:
        self._data: BoundedCache[tuple[int, int, str], deque] = BoundedCache(max_size=max_size)

    def record_and_count(
        self,
        guild_id: int,
        user_id: int,
        category: str,
        now: datetime,
        window_seconds: int,
    ) -> int:
        """
        Registra un evento ADESSO per (server, utente, categoria) e
        restituisce quanti eventi di quella categoria risultano nella
        finestra mobile — INCLUSO quello appena registrato. Gli
        eventi più vecchi della finestra vengono scartati ad ogni
        chiamata, non serve un job di pulizia separato.
        """
        chiave = (guild_id, user_id, category)
        coda = self._data.get(chiave)
        if coda is None:
            coda = deque()
        coda.append(now)
        while coda and (now - coda[0]).total_seconds() > window_seconds:
            coda.popleft()
        self._data.set(chiave, coda)
        return len(coda)


rate_tracker = AutomodRateTracker()
