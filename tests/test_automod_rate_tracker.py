"""
tests/test_automod_rate_tracker.py
======================================
Test della finestra mobile in memoria (SPEC.md §6.4/§6.6/§6.10) —
istanza isolata di AutomodRateTracker, non il singleton globale.
"""

from datetime import datetime, timedelta, timezone

from core.automod_rate_tracker import AutomodRateTracker


class TestRecordAndCount:
    def test_primo_evento_conta_uno(self):
        tracker = AutomodRateTracker()
        adesso = datetime.now(timezone.utc)
        assert tracker.record_and_count(1, 1, "messages", adesso, window_seconds=10) == 1

    def test_eventi_ravvicinati_si_accumulano(self):
        tracker = AutomodRateTracker()
        base = datetime.now(timezone.utc)
        tracker.record_and_count(1, 1, "messages", base, window_seconds=10)
        tracker.record_and_count(1, 1, "messages", base + timedelta(seconds=2), window_seconds=10)
        conteggio = tracker.record_and_count(1, 1, "messages", base + timedelta(seconds=4), window_seconds=10)
        assert conteggio == 3

    def test_eventi_fuori_finestra_vengono_scartati(self):
        tracker = AutomodRateTracker()
        base = datetime.now(timezone.utc)
        tracker.record_and_count(1, 1, "messages", base, window_seconds=5)
        conteggio = tracker.record_and_count(1, 1, "messages", base + timedelta(seconds=10), window_seconds=5)
        assert conteggio == 1

    def test_categorie_diverse_sono_indipendenti(self):
        tracker = AutomodRateTracker()
        adesso = datetime.now(timezone.utc)
        tracker.record_and_count(1, 1, "messages", adesso, window_seconds=10)
        conteggio_sticker = tracker.record_and_count(1, 1, "sticker", adesso, window_seconds=10)
        assert conteggio_sticker == 1

    def test_utenti_diversi_sono_indipendenti(self):
        tracker = AutomodRateTracker()
        adesso = datetime.now(timezone.utc)
        tracker.record_and_count(1, 1, "messages", adesso, window_seconds=10)
        conteggio_altro_utente = tracker.record_and_count(1, 2, "messages", adesso, window_seconds=10)
        assert conteggio_altro_utente == 1

    def test_server_diversi_sono_indipendenti(self):
        tracker = AutomodRateTracker()
        adesso = datetime.now(timezone.utc)
        tracker.record_and_count(1, 1, "messages", adesso, window_seconds=10)
        conteggio_altro_server = tracker.record_and_count(2, 1, "messages", adesso, window_seconds=10)
        assert conteggio_altro_server == 1
