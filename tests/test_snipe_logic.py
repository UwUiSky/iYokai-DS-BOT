"""
tests/test_snipe_logic.py
============================
Test di core/snipe_logic.py — logica pura, nessuna dipendenza da
Discord.
"""

from core.snipe_logic import is_ghost_ping_candidate


class TestIsGhostPingCandidate:
    def test_menziona_un_utente(self):
        assert is_ghost_ping_candidate([1], mentions_everyone=False, author_is_bot=False) is True

    def test_menziona_everyone(self):
        assert is_ghost_ping_candidate([], mentions_everyone=True, author_is_bot=False) is True

    def test_nessuna_menzione(self):
        assert is_ghost_ping_candidate([], mentions_everyone=False, author_is_bot=False) is False

    def test_messaggio_di_un_bot_non_conta_anche_se_menziona(self):
        assert is_ghost_ping_candidate([1], mentions_everyone=True, author_is_bot=True) is False
