"""
tests/test_premium_pricing_logic.py
=======================================
Test di core/premium_pricing_logic.py — logica pura, nessuna
dipendenza da Discord o dal database.
"""

from datetime import datetime, timezone

import pytest

from core.premium_pricing_logic import (
    is_tier_time_unlocked,
    member_count_bracket,
    months_elapsed,
    premium_tier_cost,
    round_up_to_step,
)


class TestMonthsElapsed:
    def test_stesso_giorno_zero_mesi(self):
        join = datetime(2026, 1, 15, tzinfo=timezone.utc)
        assert months_elapsed(join, join) == 0

    def test_now_prima_del_join_zero_mesi(self):
        join = datetime(2026, 1, 15, tzinfo=timezone.utc)
        prima = datetime(2025, 12, 1, tzinfo=timezone.utc)
        assert months_elapsed(join, prima) == 0

    def test_sei_mesi_esatti_stesso_giorno_del_mese(self):
        join = datetime(2026, 1, 15, tzinfo=timezone.utc)
        now = datetime(2026, 7, 15, tzinfo=timezone.utc)
        assert months_elapsed(join, now) == 6

    def test_un_giorno_prima_del_traguardo_mensile_non_conta_il_mese(self):
        join = datetime(2026, 1, 15, tzinfo=timezone.utc)
        now = datetime(2026, 7, 14, tzinfo=timezone.utc)
        assert months_elapsed(join, now) == 5

    def test_un_anno_esatto(self):
        join = datetime(2025, 1, 1, tzinfo=timezone.utc)
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert months_elapsed(join, now) == 12

    def test_due_anni_esatti(self):
        join = datetime(2024, 1, 1, tzinfo=timezone.utc)
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert months_elapsed(join, now) == 24


class TestMemberCountBracket:
    def test_meno_di_mille_fascia_zero(self):
        assert member_count_bracket(0) == 0
        assert member_count_bracket(999) == 0

    def test_esattamente_mille_fascia_uno(self):
        assert member_count_bracket(1_000) == 1

    def test_meno_di_diecimila_fascia_uno(self):
        assert member_count_bracket(9_999) == 1

    def test_esattamente_diecimila_fascia_due(self):
        assert member_count_bracket(10_000) == 2

    def test_centomila_fascia_tre(self):
        assert member_count_bracket(100_000) == 3

    def test_negativo_solleva_errore(self):
        with pytest.raises(ValueError):
            member_count_bracket(-1)


class TestRoundUpToStep:
    def test_valore_gia_multiplo_resta_uguale(self):
        assert round_up_to_step(50_000) == 50_000

    def test_valore_non_multiplo_arrotonda_in_eccesso(self):
        assert round_up_to_step(50_001) == 75_000

    def test_zero_resta_zero(self):
        assert round_up_to_step(0) == 0

    def test_valore_negativo_resta_zero(self):
        assert round_up_to_step(-100) == 0


class TestPremiumTierCost:
    def test_tier1_fascia_base_sotto_i_1000_membri(self):
        assert premium_tier_cost(1, 500) == 500_000

    def test_tier2_fascia_base_sotto_i_1000_membri(self):
        assert premium_tier_cost(2, 500) == 5_000_000

    def test_tier3_fascia_base_sotto_i_1000_membri(self):
        assert premium_tier_cost(3, 500) == 50_000_000

    def test_tier1_fascia_sotto_i_10000_membri_e_dieci_volte_la_base(self):
        assert premium_tier_cost(1, 5_000) == 5_000_000

    def test_tier2_fascia_sotto_i_10000_membri(self):
        assert premium_tier_cost(2, 5_000) == 50_000_000

    def test_tier3_fascia_sotto_i_10000_membri(self):
        assert premium_tier_cost(3, 5_000) == 500_000_000

    def test_fascia_sotto_i_100000_membri_ulteriore_dieci_volte(self):
        assert premium_tier_cost(1, 50_000) == 50_000_000

    def test_tier_non_definito_solleva_errore(self):
        with pytest.raises(ValueError):
            premium_tier_cost(4, 500)


class TestIsTierTimeUnlocked:
    def test_tier1_sbloccato_dopo_sei_mesi(self):
        join = datetime(2026, 1, 1, tzinfo=timezone.utc)
        dopo_sei_mesi = datetime(2026, 7, 1, tzinfo=timezone.utc)
        assert is_tier_time_unlocked(1, join, dopo_sei_mesi) is True

    def test_tier1_non_sbloccato_prima_di_sei_mesi(self):
        join = datetime(2026, 1, 1, tzinfo=timezone.utc)
        dopo_cinque_mesi = datetime(2026, 6, 1, tzinfo=timezone.utc)
        assert is_tier_time_unlocked(1, join, dopo_cinque_mesi) is False

    def test_tier2_sbloccato_dopo_un_anno(self):
        join = datetime(2025, 1, 1, tzinfo=timezone.utc)
        dopo_un_anno = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert is_tier_time_unlocked(2, join, dopo_un_anno) is True

    def test_tier3_sbloccato_dopo_due_anni(self):
        join = datetime(2024, 1, 1, tzinfo=timezone.utc)
        dopo_due_anni = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert is_tier_time_unlocked(3, join, dopo_due_anni) is True

    def test_tier3_non_sbloccato_dopo_un_anno_e_mezzo(self):
        join = datetime(2024, 1, 1, tzinfo=timezone.utc)
        dopo_un_anno_e_mezzo = datetime(2025, 7, 1, tzinfo=timezone.utc)
        assert is_tier_time_unlocked(3, join, dopo_un_anno_e_mezzo) is False

    def test_tier_non_definito_solleva_errore(self):
        join = datetime(2024, 1, 1, tzinfo=timezone.utc)
        with pytest.raises(ValueError):
            is_tier_time_unlocked(4, join, join)
