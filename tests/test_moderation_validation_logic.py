"""
tests/test_moderation_validation_logic.py
=============================================
Test di core/moderation_validation_logic.py — logica pura.
"""

from core.moderation_validation_logic import MIN_REASON_LENGTH, is_valid_reason


class TestIsValidReason:
    def test_motivo_valido(self):
        assert is_valid_reason("Spam ripetuto in più canali") is True

    def test_motivo_troppo_corto(self):
        assert is_valid_reason("ok") is False

    def test_motivo_vuoto(self):
        assert is_valid_reason("") is False

    def test_motivo_solo_spazi(self):
        assert is_valid_reason("   ") is False

    def test_motivo_esattamente_al_limite(self):
        assert is_valid_reason("a" * MIN_REASON_LENGTH) is True

    def test_motivo_un_carattere_sotto_il_limite(self):
        assert is_valid_reason("a" * (MIN_REASON_LENGTH - 1)) is False

    def test_spazi_iniziali_finali_non_contano_come_contenuto(self):
        # "  ab  " ripulito è "ab", 2 caratteri: sotto soglia anche
        # se la stringa grezza è più lunga di 3.
        assert is_valid_reason("  ab  ") is False
