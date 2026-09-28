"""
core/webhook_rate_tracker.py
================================
Finestra mobile in memoria per limitare le richieste che
core/custom_webhook_server.py accetta per ogni token (SEC-14): un
token compromesso, o un servizio terzo mal configurato che manda
richieste a raffica, non deve poter inondare il canale Discord di
destinazione. Stesso principio di core/automod_rate_tracker.py, ma
qui la chiave è direttamente il token (il server webhook riceve
richieste HTTP anonime — l'unica identità che vede è il token
nell'URL, non c'è un utente/server Discord da usare come chiave).
"""

from __future__ import annotations

from collections import deque
from datetime import datetime

from core.bounded_cache import BoundedCache

# Oltre questa soglia in questa finestra, le richieste in più
# ricevono un 429 invece di pubblicare un altro messaggio.
WEBHOOK_RATE_LIMIT_MAX_REQUESTS = 10
WEBHOOK_RATE_LIMIT_WINDOW_SECONDS = 60


class WebhookRateTracker:
    def __init__(self, max_size: int = 20_000) -> None:
        self._data: BoundedCache[str, deque] = BoundedCache(max_size=max_size)

    def record_and_count(self, token: str, now: datetime, window_seconds: int) -> int:
        """
        Registra una richiesta ADESSO per questo token e restituisce
        quante richieste risultano nella finestra mobile — INCLUSA
        quella appena registrata. Le richieste più vecchie della
        finestra vengono scartate ad ogni chiamata.
        """
        coda = self._data.get(token)
        if coda is None:
            coda = deque()
        coda.append(now)
        while coda and (now - coda[0]).total_seconds() > window_seconds:
            coda.popleft()
        self._data.set(token, coda)
        return len(coda)


webhook_rate_tracker = WebhookRateTracker()
