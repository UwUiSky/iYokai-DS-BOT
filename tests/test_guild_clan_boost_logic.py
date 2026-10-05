"""
tests/test_guild_clan_boost_logic.py
========================================
Test di core/guild_clan_boost_logic.py — logica pura dei boost
XP/Coin del Sistema Gilde/Clan (SPEC.md §15.14, D23: tipi exp/coin/super).
"""

from datetime import datetime, timedelta, timezone

import pytest

from core.guild_clan_boost_logic import (
    BOOST_DURATION_HOURS,
    BOOST_MULTIPLIER,
    GUILD_BOOST_COSTS,
    INDIVIDUAL_BOOST_COSTS,
    Beneficio,
    TipoBoost,
    benefici_attivi,
    compute_boosted_reward,
    is_boost_active,
    nuove_scadenze,
    tipi_acquistabili,
)

ORA = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
FUTURO = ORA + timedelta(hours=5)
PASSATO = ORA - timedelta(hours=1)


class TestIsBoostActive:
    def test_none_non_attivo(self):
        assert is_boost_active(None, ORA) is False

    def test_futuro_attivo(self):
        assert is_boost_active(ORA + timedelta(hours=1), ORA) is True

    def test_passato_non_attivo(self):
        assert is_boost_active(ORA - timedelta(hours=1), ORA) is False

    def test_scadenza_esattamente_ora_non_attivo(self):
        assert is_boost_active(ORA, ORA) is False


class TestPrezzi:
    def test_individuali(self):
        assert INDIVIDUAL_BOOST_COSTS == {
            TipoBoost.EXP: 6_000, TipoBoost.COIN: 6_000, TipoBoost.SUPER: 10_000,
        }

    def test_di_gilda(self):
        assert GUILD_BOOST_COSTS == {
            TipoBoost.EXP: 60_000, TipoBoost.COIN: 60_000, TipoBoost.SUPER: 100_000,
        }


class TestBeneficiAttivi:
    def test_nessuno(self):
        assert benefici_attivi(None, None, ORA) == {}

    def test_solo_exp(self):
        assert benefici_attivi(FUTURO, None, ORA) == {Beneficio.EXP: FUTURO}

    def test_scaduto_non_conta(self):
        assert benefici_attivi(PASSATO, FUTURO, ORA) == {Beneficio.COIN: FUTURO}


class TestNuoveScadenze:
    def test_exp_imposta_solo_exp(self):
        assert nuove_scadenze(TipoBoost.EXP, ORA) == {
            Beneficio.EXP: ORA + timedelta(hours=BOOST_DURATION_HOURS)
        }

    def test_coin_imposta_solo_coin(self):
        assert set(nuove_scadenze(TipoBoost.COIN, ORA)) == {Beneficio.COIN}

    def test_super_imposta_entrambe_uguali(self):
        s = nuove_scadenze(TipoBoost.SUPER, ORA)
        assert set(s) == {Beneficio.EXP, Beneficio.COIN}
        assert s[Beneficio.EXP] == s[Beneficio.COIN] == ORA + timedelta(hours=24)


class TestTipiAcquistabili:
    """Matrice completa D23."""

    @pytest.mark.parametrize(
        "scad_exp, scad_coin, atteso",
        [
            (None, None, {TipoBoost.EXP, TipoBoost.COIN, TipoBoost.SUPER}),
            (None, FUTURO, {TipoBoost.EXP}),   # coin attivo: solo exp
            (FUTURO, None, {TipoBoost.COIN}),  # exp attivo: solo coin
            (FUTURO, FUTURO, set()),           # super attivo: niente
            (PASSATO, PASSATO, {TipoBoost.EXP, TipoBoost.COIN, TipoBoost.SUPER}),
            (PASSATO, FUTURO, {TipoBoost.EXP}),
        ],
    )
    def test_matrice(self, scad_exp, scad_coin, atteso):
        assert set(tipi_acquistabili(scad_exp, scad_coin, ORA)) == atteso


class TestComputeBoostedReward:
    def test_nessun_boost_invariato(self):
        assert compute_boosted_reward(30, 2) == (30, 2)

    def test_exp_individuale_raddoppia_solo_xp(self):
        assert compute_boosted_reward(30, 2, individuale_exp=True) == (60, 2)

    def test_coin_individuale_raddoppia_solo_coin(self):
        assert compute_boosted_reward(30, 2, individuale_coin=True) == (30, 4)

    def test_exp_di_gilda_raddoppia_solo_xp(self):
        assert compute_boosted_reward(30, 2, gilda_exp=True) == (60, 2)

    def test_coin_di_gilda_raddoppia_solo_coin(self):
        assert compute_boosted_reward(30, 2, gilda_coin=True) == (30, 4)

    def test_super_individuale(self):
        assert compute_boosted_reward(
            30, 2, individuale_exp=True, individuale_coin=True
        ) == (60, 4)

    def test_individuale_e_gilda_si_moltiplicano(self):
        assert compute_boosted_reward(
            30, 2, individuale_exp=True, individuale_coin=True, gilda_exp=True, gilda_coin=True
        ) == (30 * 4, 2 * 4)

    def test_exp_individuale_e_coin_di_gilda_restano_separati(self):
        assert compute_boosted_reward(
            10, 10, individuale_exp=True, gilda_coin=True
        ) == (10 * BOOST_MULTIPLIER, 10 * BOOST_MULTIPLIER)

    def test_zero_resta_zero(self):
        assert compute_boosted_reward(
            0, 0, individuale_exp=True, individuale_coin=True, gilda_exp=True, gilda_coin=True
        ) == (0, 0)
