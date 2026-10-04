"""
core/webhook_rate_tracker.py
================================
Finestra mobile in memoria per limitare le richieste che
core/custom_webhook_server.py accetta (SEC-14, BUG-33): un token
compromesso, o un servizio terzo mal configurato che manda richieste
a raffica, non deve poter inondare il canale Discord di destinazione.
La chiave è una stringa scelta dal chiamante (il token, o l'IP per i
tentativi con token inesistenti); si contano solo le richieste
accettate.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime

from core.bounded_cache import BoundedCache

# Oltre questa soglia in questa finestra, le richieste in più
# ricevono un 429 invece di pubblicare un altro messaggio.
WEBHOOK_RATE_LIMIT_MAX_REQUESTS = 10
WEBHOOK_RATE_LIMIT_WINDOW_SECONDS = 60

# Quante richieste con un token inesistente può fare lo stesso IP
# nella stessa finestra prima di ricevere 429 senza che il database
# venga più interrogato (BUG-33).
WEBHOOK_UNKNOWN_TOKEN_LIMIT_PER_IP = 20


class WebhookRateTracker:
    def __init__(self, max_size: int = 20_000) -> None:
        self._data: BoundedCache[str, deque] = BoundedCache(max_size=max_size)

    def count_recent(self, key: str, now: datetime, window_seconds: int) -> int:
        """
        Quante richieste ACCETTATE risultano per questa chiave nella
        finestra mobile. Non registra nulla: scarta solo gli istanti
        più vecchi della finestra.
        """
        coda = self._data.get(key)
        if coda is None:
            return 0
        while coda and (now - coda[0]).total_seconds() > window_seconds:
            coda.popleft()
        return len(coda)

    def allow(self, key: str, now: datetime, max_requests: int, window_seconds: int) -> bool:
        """
        True se nella finestra c'è ancora posto, e in quel caso
        registra la richiesta. False se il limite è raggiunto: una
        richiesta rifiutata NON viene registrata (BUG-33), così un
        traffico costante sopra soglia viene rallentato, non bloccato
        per sempre, e la coda non supera mai `max_requests` elementi.
        """
        if self.count_recent(key, now, window_seconds) >= max_requests:
            return False
        coda = self._data.get(key)
        if coda is None:
            coda = deque(maxlen=max_requests)
            self._data.set(key, coda)
        coda.append(now)
        return True


webhook_rate_tracker = WebhookRateTracker()
