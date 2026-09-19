"""
tests/test_escalation_ladder_logic.py
=========================================
Test di core/escalation_ladder_logic.py — logica pura, nessuna
dipendenza da Discord.
"""

from datetime import datetime, timedelta, timezone

from core.escalation_ladder_logic import (
    LadderStep,
    get_ladder_action,
    next_violation_count,
    should_reset_violation_count,
)


class TestShouldResetViolationCount:
    def test_nessuna_infrazione_precedente_non_e_da_resettare(self):
        assert should_reset_violation_count(None, reset_after_days=7) is False

    def test_infrazione_recente_non_resetta(self):
        ora = datetime(2026, 1, 10, tzinfo=timezone.utc)
        ultima = ora - timedelta(days=1)
        assert should_reset_violation_count(ultima, reset_after_days=7, now=ora) is False

    def test_infrazione_abbastanza_vecchia_resetta(self):
        ora = datetime(2026, 1, 10, tzinfo=timezone.utc)
        ultima = ora - timedelta(days=10)
        assert should_reset_violation_count(ultima, reset_after_days=7, now=ora) is True

    def test_esattamente_al_confine_resetta(self):
        ora = datetime(2026, 1, 10, tzinfo=timezone.utc)
        ultima = ora - timedelta(days=7)
        assert should_reset_violation_count(ultima, reset_after_days=7, now=ora) is True


class TestNextViolationCount:
    def test_senza_reset_incrementa(self):
        assert next_violation_count(current_count=2, should_reset=False) == 3

    def test_con_reset_riparte_da_uno(self):
        assert next_violation_count(current_count=5, should_reset=True) == 1

    def test_da_zero_senza_reset(self):
        assert next_violation_count(current_count=0, should_reset=False) == 1


class TestGetLadderAction:
    LADDER = [
        LadderStep(level=1, action_type="warn"),
        LadderStep(level=2, action_type="timeout", duration_seconds=600),
        LadderStep(level=3, action_type="timeout", duration_seconds=3600),
    ]

    def test_primo_livello(self):
        step = get_ladder_action(1, self.LADDER)
        assert step.action_type == "warn"

    def test_secondo_livello(self):
        step = get_ladder_action(2, self.LADDER)
        assert step.action_type == "timeout"
        assert step.duration_seconds == 600

    def test_oltre_lultimo_gradino_resta_sul_piu_severo(self):
        # 5a infrazione, scala definita solo fino al livello 3: deve
        # applicare il livello 3 (il più severo), non "nessuna azione".
        step = get_ladder_action(5, self.LADDER)
        assert step.level == 3
        assert step.duration_seconds == 3600

    def test_scala_vuota_restituisce_none(self):
        assert get_ladder_action(1, []) is None

    def test_scala_non_ordinata_in_ingresso_funziona_comunque(self):
        scala_disordinata = [
            LadderStep(level=3, action_type="ban"),
            LadderStep(level=1, action_type="warn"),
            LadderStep(level=2, action_type="timeout", duration_seconds=60),
        ]
        assert get_ladder_action(1, scala_disordinata).action_type == "warn"
        assert get_ladder_action(10, scala_disordinata).action_type == "ban"

    def test_scala_con_un_solo_gradino(self):
        scala_singola = [LadderStep(level=1, action_type="timeout", duration_seconds=300)]
        assert get_ladder_action(1, scala_singola).duration_seconds == 300
        # Anche la 100esima infrazione resta sull'unico gradino esistente.
        assert get_ladder_action(100, scala_singola).duration_seconds == 300
