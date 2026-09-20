"""
tests/test_suggestion_logic.py
==================================
Test di core/suggestion_logic.py — logica pura.
"""

from core.suggestion_logic import APPROVED, PENDING, REJECTED, can_decide


class TestCanDecide:
    def test_pending_puo_essere_deciso(self):
        assert can_decide(PENDING) is True

    def test_approved_non_puo_essere_deciso_di_nuovo(self):
        assert can_decide(APPROVED) is False

    def test_rejected_non_puo_essere_deciso_di_nuovo(self):
        assert can_decide(REJECTED) is False
