"""
tests/test_webhook_rate_tracker.py
======================================
SEC-14: finestra mobile in memoria per limitare le richieste che
core/custom_webhook_server.py accetta per ogni singolo token — senza
questo, un token webhook compromesso (o un servizio terzo mal
configurato) può inondare di messaggi il canale Discord di
destinazione senza alcun limite.
"""

from datetime import datetime, timedelta, timezone

from core.webhook_rate_tracker import WebhookRateTracker


def test_conta_le_richieste_nella_finestra():
    tracker = WebhookRateTracker()
    ora = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert tracker.record_and_count("token-a", ora, window_seconds=60) == 1
    assert tracker.record_and_count("token-a", ora, window_seconds=60) == 2
    assert tracker.record_and_count("token-a", ora, window_seconds=60) == 3


def test_token_diversi_non_si_mescolano():
    tracker = WebhookRateTracker()
    ora = datetime(2026, 1, 1, tzinfo=timezone.utc)

    tracker.record_and_count("token-a", ora, window_seconds=60)
    tracker.record_and_count("token-a", ora, window_seconds=60)

    assert tracker.record_and_count("token-b", ora, window_seconds=60) == 1


def test_le_richieste_fuori_dalla_finestra_vengono_scartate():
    tracker = WebhookRateTracker()
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)

    tracker.record_and_count("token-a", t0, window_seconds=60)
    tracker.record_and_count("token-a", t0, window_seconds=60)

    t1 = t0 + timedelta(seconds=61)
    assert tracker.record_and_count("token-a", t1, window_seconds=60) == 1
