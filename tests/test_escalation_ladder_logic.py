"""
tests/test_escalation_ladder_logic.py
=========================================
Test di core/escalation_ladder_logic.py — logica pura, nessuna
dipendenza da Discord.
"""

from core.escalation_ladder_logic import LadderStep, get_ladder_action


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
