"""
tests/test_setup_wizard_logic.py
====================================
Test di core/setup_wizard_logic.py — logica pura.
"""

import pytest

from core.setup_wizard_logic import clamp_step, is_last_step, next_step, previous_step


class TestClampStep:
    def test_dentro_i_limiti(self):
        assert clamp_step(2, 5) == 2

    def test_sotto_zero_si_ferma_a_zero(self):
        assert clamp_step(-3, 5) == 0

    def test_sopra_il_massimo_si_ferma_all_ultimo(self):
        assert clamp_step(99, 5) == 4

    def test_total_steps_non_positivo_solleva_errore(self):
        with pytest.raises(ValueError):
            clamp_step(0, 0)


class TestNextStep:
    def test_avanza_normalmente(self):
        assert next_step(1, 5) == 2

    def test_non_supera_l_ultimo_step(self):
        assert next_step(4, 5) == 4


class TestPreviousStep:
    def test_torna_indietro_normalmente(self):
        assert previous_step(2, 5) == 1

    def test_non_va_sotto_zero(self):
        assert previous_step(0, 5) == 0


class TestIsLastStep:
    def test_ultimo_step(self):
        assert is_last_step(4, 5) is True

    def test_non_ultimo_step(self):
        assert is_last_step(2, 5) is False
