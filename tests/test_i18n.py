"""
tests/test_i18n.py
======================
Test di core/i18n.py — logica pura, nessuna dipendenza da Discord.
"""

from core.i18n import t


class TestT:
    def test_traduzione_italiana(self):
        assert t("module_not_active", "it") == "Questo modulo non è attivo su questo server."

    def test_traduzione_inglese(self):
        assert t("module_not_active", "en") == "This module is not active on this server."

    def test_lingua_non_supportata_ricade_sull_italiano(self):
        assert t("module_not_active", "pt-BR") == "Questo modulo non è attivo su questo server."

    def test_lingua_presente_ma_vuota_ricade_sull_inglese(self):
        # D58: ripiego lingua -> en-US -> it (fr non ha ancora testi).
        assert t("module_not_active", "fr") == t("module_not_active", "en")

    def test_chiave_inesistente_restituisce_la_chiave_stessa(self):
        assert t("chiave_mai_esistita", "it") == "chiave_mai_esistita"
