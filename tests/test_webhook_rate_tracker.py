"""
tests/test_webhook_rate_tracker.py
======================================
SEC-14/BUG-33: finestra mobile in memoria per limitare le richieste
che core/custom_webhook_server.py accetta. Si contano solo le
richieste accettate: un traffico costante sopra soglia viene
rallentato, non bloccato per sempre, e la coda resta limitata.
"""

from datetime import datetime, timedelta, timezone

from core.webhook_rate_tracker import WebhookRateTracker

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_accetta_fino_al_limite_poi_rifiuta():
    tracker = WebhookRateTracker()

    esiti = [tracker.allow("token-a", T0, max_requests=3, window_seconds=60) for _ in range(5)]

    assert esiti == [True, True, True, False, False]
    assert tracker.count_recent("token-a", T0, window_seconds=60) == 3


def test_chiavi_diverse_non_si_mescolano():
    tracker = WebhookRateTracker()

    tracker.allow("token-a", T0, max_requests=1, window_seconds=60)

    assert tracker.allow("token-a", T0, max_requests=1, window_seconds=60) is False
    assert tracker.allow("token-b", T0, max_requests=1, window_seconds=60) is True


def test_le_richieste_fuori_dalla_finestra_vengono_scartate():
    tracker = WebhookRateTracker()
    tracker.allow("token-a", T0, max_requests=2, window_seconds=60)
    tracker.allow("token-a", T0, max_requests=2, window_seconds=60)

    dopo = T0 + timedelta(seconds=61)

    assert tracker.count_recent("token-a", dopo, window_seconds=60) == 0
    assert tracker.allow("token-a", dopo, max_requests=2, window_seconds=60) is True


def test_count_recent_non_registra_nulla():
    tracker = WebhookRateTracker()

    for _ in range(5):
        assert tracker.count_recent("token-a", T0, window_seconds=60) == 0


def test_traffico_costante_sopra_soglia_non_blocca_per_sempre():
    """BUG-33: 12 richieste al minuto per 10 minuti, limite 10 al minuto."""
    tracker = WebhookRateTracker()

    accettate = sum(
        tracker.allow("token-a", T0 + timedelta(seconds=5 * i), max_requests=10, window_seconds=60)
        for i in range(120)
    )

    assert 90 <= accettate <= 100


def test_le_richieste_rifiutate_non_occupano_memoria():
    """BUG-33: mille richieste rifiutate non allungano la coda."""
    tracker = WebhookRateTracker()

    for _ in range(1000):
        tracker.allow("token-a", T0, max_requests=10, window_seconds=60)

    assert len(tracker._data.get("token-a")) == 10
