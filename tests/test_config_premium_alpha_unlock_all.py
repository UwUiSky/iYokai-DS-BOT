"""
tests/test_config_premium_alpha_unlock_all.py
==================================================
#41: PREMIUM_ALPHA_UNLOCK_ALL deve essere spento di default in
produzione (sblocca TUTTE le feature premium per TUTTI i server —
pericoloso da lasciare acceso per dimenticanza), acceso di default
altrove, e sempre sovrascrivibile esplicitamente con la variabile
d'ambiente. Stesso pattern di tests/test_config_enable_eval.py.
"""

from core.config import _load_config


class TestDefaultPremiumAlphaUnlockAll:
    def test_spento_di_default_in_produzione(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("PREMIUM_ALPHA_UNLOCK_ALL", raising=False)

        assert _load_config().PREMIUM_ALPHA_UNLOCK_ALL is False

    def test_acceso_di_default_in_sviluppo(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("PREMIUM_ALPHA_UNLOCK_ALL", raising=False)

        assert _load_config().PREMIUM_ALPHA_UNLOCK_ALL is True

    def test_maiuscole_minuscole_di_environment_non_contano(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "PRODUCTION")
        monkeypatch.delenv("PREMIUM_ALPHA_UNLOCK_ALL", raising=False)

        assert _load_config().PREMIUM_ALPHA_UNLOCK_ALL is False


class TestOverrideEsplicito:
    def test_true_forza_lattivazione_anche_in_produzione(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("PREMIUM_ALPHA_UNLOCK_ALL", "true")

        assert _load_config().PREMIUM_ALPHA_UNLOCK_ALL is True

    def test_false_forza_lo_spegnimento_anche_in_sviluppo(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("PREMIUM_ALPHA_UNLOCK_ALL", "false")

        assert _load_config().PREMIUM_ALPHA_UNLOCK_ALL is False
