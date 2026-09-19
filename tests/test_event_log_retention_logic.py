"""
tests/test_event_log_retention_logic.py
===========================================
Test di core/event_log_retention_logic.py — logica pura.
"""

from core.event_log_retention_logic import (
    FREE_RETENTION_DAYS,
    PREMIUM_RETENTION_DAYS,
    retention_days_for,
)


def test_free_restituisce_30_giorni():
    assert retention_days_for(is_premium=False) == FREE_RETENTION_DAYS
    assert retention_days_for(is_premium=False) == 30


def test_premium_restituisce_180_giorni():
    assert retention_days_for(is_premium=True) == PREMIUM_RETENTION_DAYS
    assert retention_days_for(is_premium=True) == 180


def test_premium_e_sempre_maggiore_di_free():
    assert retention_days_for(True) > retention_days_for(False)
