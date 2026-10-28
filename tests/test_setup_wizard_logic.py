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


class TestPassiDelWizard:
    ORDINE = ("moderation", "logging", "utility")

    def test_primo_passo_i_ruoli_poi_una_categoria_per_passo(self):
        from core.setup_wizard_logic import costruisci_passi

        passi = costruisci_passi({"utility": ["a"], "logging": ["b", "c"]}, self.ORDINE)
        assert [(p.tipo, p.categoria) for p in passi] == [
            ("ruoli", None), ("moduli", "logging"), ("moduli", "utility"),
        ]

    def test_categoria_vuota_non_ha_passo(self):
        from core.setup_wizard_logic import costruisci_passi

        assert len(costruisci_passi({"logging": []}, self.ORDINE)) == 1

    def test_oltre_25_moduli_si_divide_e_nessun_modulo_si_perde(self):
        from core.setup_wizard_logic import costruisci_passi

        nomi = [f"m{i}" for i in range(60)]
        passi = costruisci_passi({"utility": nomi}, self.ORDINE)[1:]
        assert [len(p.nomi) for p in passi] == [25, 25, 10]
        assert [p.parte for p in passi] == [1, 2, 3] and passi[0].parti == 3
        assert [n for p in passi for n in p.nomi] == nomi

    def test_categoria_fuori_ordine_va_in_coda(self):
        from core.setup_wizard_logic import costruisci_passi

        passi = costruisci_passi({"zeta": ["z"], "utility": ["u"], "alfa": ["a"]}, self.ORDINE)
        assert [p.categoria for p in passi[1:]] == ["utility", "alfa", "zeta"]

    def test_moduli_da_scrivere_solo_i_cambiati(self):
        from core.setup_wizard_logic import moduli_da_scrivere

        assert moduli_da_scrivere({"a": True, "b": False, "c": False}, {"a": False, "b": False, "c": True}) == [
            ("a", False), ("c", True)
        ]
