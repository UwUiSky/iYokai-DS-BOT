"""
tests/test_error_handler_logic.py
=====================================
Test di core/error_handler_logic.py — logica pura.
"""

from datetime import datetime, timedelta, timezone

from core.error_handler_logic import ERROR_ALERT_COOLDOWN_SECONDS, should_alert_owner


class TestShouldAlertOwner:
    def test_mai_avvisato_prima_manda_alert(self):
        assert should_alert_owner(last_alert_at=None) is True

    def test_avvisato_da_poco_non_manda(self):
        ora = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        ultimo = ora - timedelta(minutes=1)
        assert should_alert_owner(ultimo, now=ora) is False

    def test_avvisato_da_abbastanza_manda_di_nuovo(self):
        ora = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        ultimo = ora - timedelta(seconds=ERROR_ALERT_COOLDOWN_SECONDS + 1)
        assert should_alert_owner(ultimo, now=ora) is True

    def test_esattamente_al_confine_manda(self):
        ora = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        ultimo = ora - timedelta(seconds=ERROR_ALERT_COOLDOWN_SECONDS)
        assert should_alert_owner(ultimo, now=ora) is True

    def test_un_secondo_prima_del_confine_non_manda(self):
        ora = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        ultimo = ora - timedelta(seconds=ERROR_ALERT_COOLDOWN_SECONDS - 1)
        assert should_alert_owner(ultimo, now=ora) is False
