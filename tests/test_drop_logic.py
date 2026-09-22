"""
tests/test_drop_logic.py
============================
Test di core/drop_logic.py — logica pura.
"""

from core.drop_logic import should_trigger_drop


def test_roll_sotto_la_soglia_attiva_il_drop():
    assert should_trigger_drop(roll=0.001, chance=0.005) is True


def test_roll_sopra_la_soglia_non_attiva_il_drop():
    assert should_trigger_drop(roll=0.5, chance=0.005) is False


def test_roll_esattamente_alla_soglia_non_attiva():
    assert should_trigger_drop(roll=0.005, chance=0.005) is False


def test_chance_zero_non_attiva_mai():
    assert should_trigger_drop(roll=0.0, chance=0.0) is False
