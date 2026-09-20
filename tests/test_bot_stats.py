"""
tests/test_bot_stats.py
==========================
Test di core/bot_stats.py — logica pura.
"""

from datetime import datetime, timedelta, timezone

from core.bot_stats import RollingCounter


class TestRollingCounter:
    def test_nessun_evento_conta_zero(self):
        contatore = RollingCounter(window_seconds=60)
        assert contatore.count_in_window() == 0

    def test_eventi_dentro_la_finestra_vengono_contati(self):
        ora = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        contatore = RollingCounter(window_seconds=60)
        contatore.record(at=ora - timedelta(seconds=10))
        contatore.record(at=ora - timedelta(seconds=30))
        contatore.record(at=ora - timedelta(seconds=59))

        assert contatore.count_in_window(now=ora) == 3

    def test_eventi_fuori_dalla_finestra_non_vengono_contati(self):
        ora = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        contatore = RollingCounter(window_seconds=60)
        contatore.record(at=ora - timedelta(seconds=61))
        contatore.record(at=ora - timedelta(seconds=120))

        assert contatore.count_in_window(now=ora) == 0

    def test_mix_di_eventi_dentro_e_fuori_la_finestra(self):
        ora = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        contatore = RollingCounter(window_seconds=60)
        contatore.record(at=ora - timedelta(seconds=10))  # dentro
        contatore.record(at=ora - timedelta(seconds=90))  # fuori
        contatore.record(at=ora - timedelta(seconds=5))   # dentro

        assert contatore.count_in_window(now=ora) == 2

    def test_gli_eventi_scaduti_vengono_potati_dalla_coda(self):
        # Non solo esclusi dal conteggio: rimossi per davvero dalla
        # struttura dati, altrimenti un bot che gira per settimane
        # accumulerebbe timestamp vecchi all'infinito.
        ora = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        contatore = RollingCounter(window_seconds=60)
        contatore.record(at=ora - timedelta(seconds=120))

        contatore.count_in_window(now=ora)

        assert len(contatore._timestamps) == 0

    def test_finestra_personalizzata(self):
        ora = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        contatore = RollingCounter(window_seconds=10)
        contatore.record(at=ora - timedelta(seconds=15))

        assert contatore.count_in_window(now=ora) == 0

    def test_record_senza_timestamp_usa_ora_corrente(self):
        contatore = RollingCounter(window_seconds=60)
        contatore.record()  # nessun 'at' esplicito

        assert contatore.count_in_window() == 1
