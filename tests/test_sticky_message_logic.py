"""
tests/test_sticky_message_logic.py
======================================
Test di core/sticky_message_logic.py — logica pura.
"""

from datetime import datetime, timedelta, timezone

from core.sticky_message_logic import MIN_REPOST_INTERVAL_SECONDS, should_repost_sticky


class TestShouldRepostSticky:
    def test_mai_ripubblicato_prima_e_sempre_si(self):
        ora = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert should_repost_sticky(None, now=ora) is True

    def test_ripubblicato_da_poco_non_ripete(self):
        ora = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ultimo = ora - timedelta(seconds=2)
        assert should_repost_sticky(ultimo, now=ora) is False

    def test_ripubblicato_abbastanza_tempo_fa_ripete(self):
        ora = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ultimo = ora - timedelta(seconds=10)
        assert should_repost_sticky(ultimo, now=ora) is True

    def test_esattamente_al_confine_ripete(self):
        ora = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ultimo = ora - timedelta(seconds=MIN_REPOST_INTERVAL_SECONDS)
        assert should_repost_sticky(ultimo, now=ora) is True

    def test_intervallo_personalizzato(self):
        ora = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ultimo = ora - timedelta(seconds=8)
        assert should_repost_sticky(ultimo, now=ora, min_interval_seconds=10) is False
        assert should_repost_sticky(ultimo, now=ora, min_interval_seconds=5) is True
