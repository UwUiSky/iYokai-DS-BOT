"""
tests/test_guild_clan_boost_logic.py
========================================
Test di core/guild_clan_boost_logic.py — logica pura dei boost
XP/Coin del Sistema Gilde/Clan (SPEC.md §15.14).
"""

from datetime import datetime, timedelta, timezone

import pytest

from core.guild_clan_boost_logic import (
    BOOST_DURATION_HOURS,
    BOOST_MULTIPLIER,
    compute_boosted_reward,
    extend_boost_expiry,
    is_boost_active,
)

ORA = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)


class TestIsBoostActive:
    def test_nessuna_scadenza_non_attivo(self):
        assert is_boost_active(None, ORA) is False

    def test_scadenza_futura_attivo(self):
        assert is_boost_active(ORA + timedelta(hours=1), ORA) is True

    def test_scadenza_passata_non_attivo(self):
        assert is_boost_active(ORA - timedelta(hours=1), ORA) is False

    def test_scadenza_esattamente_ora_non_attivo(self):
        assert is_boost_active(ORA, ORA) is False


class TestComputeBoostedReward:
    def test_nessun_boost_attivo_invariato(self):
        assert compute_boosted_reward(30, 2, individual_active=False, guild_active=False) == (30, 2)

    def test_solo_individuale_raddoppia(self):
        assert compute_boosted_reward(30, 2, individual_active=True, guild_active=False) == (60, 4)

    def test_solo_gilda_raddoppia(self):
        assert compute_boosted_reward(30, 2, individual_active=False, guild_active=True) == (60, 4)

    def test_entrambi_si_moltiplicano(self):
        assert compute_boosted_reward(30, 2, individual_active=True, guild_active=True) == (120, 8)

    def test_ricompensa_zero_resta_zero_anche_con_boost(self):
        # decadimento/tetto giornaliero già a zero: nessun boost la fa
        # ripartire da un valore positivo.
        assert compute_boosted_reward(0, 0, individual_active=True, guild_active=True) == (0, 0)

    def test_moltiplicatore_coerente_con_la_costante(self):
        assert compute_boosted_reward(10, 10, individual_active=True, guild_active=False) == (
            10 * BOOST_MULTIPLIER, 10 * BOOST_MULTIPLIER,
        )


class TestExtendBoostExpiry:
    def test_nessun_boost_precedente_parte_da_ora(self):
        nuova = extend_boost_expiry(None, ORA)
        assert nuova == ORA + timedelta(hours=BOOST_DURATION_HOURS)

    def test_boost_precedente_gia_scaduto_parte_da_ora(self):
        nuova = extend_boost_expiry(ORA - timedelta(hours=1), ORA)
        assert nuova == ORA + timedelta(hours=BOOST_DURATION_HOURS)

    def test_boost_precedente_ancora_attivo_si_estende_da_li(self):
        scadenza_attuale = ORA + timedelta(hours=5)
        nuova = extend_boost_expiry(scadenza_attuale, ORA)
        assert nuova == scadenza_attuale + timedelta(hours=BOOST_DURATION_HOURS)
