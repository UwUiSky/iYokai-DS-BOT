"""
tests/test_config_enable_eval.py
====================================
SEC-13/D7: ENABLE_EVAL deve essere spento di default in produzione,
acceso di default altrove, e sempre sovrascrivibile esplicitamente
con la variabile d'ambiente. Chiama core.config._load_config()
direttamente (non modifica il singleton `config` già importato da
tutto il resto del progetto) — le variabili obbligatorie sono già
impostate da tests/conftest.py con os.environ.setdefault, quindi qui
basta sovrascrivere ENVIRONMENT/ENABLE_EVAL per il singolo test.
"""

from core.config import _load_config


class TestDefaultEnableEval:
    def test_spento_di_default_in_produzione(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("ENABLE_EVAL", raising=False)

        assert _load_config().ENABLE_EVAL is False

    def test_acceso_di_default_in_sviluppo(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("ENABLE_EVAL", raising=False)

        assert _load_config().ENABLE_EVAL is True

    def test_maiuscole_minuscole_di_environment_non_contano(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "PRODUCTION")
        monkeypatch.delenv("ENABLE_EVAL", raising=False)

        assert _load_config().ENABLE_EVAL is False


class TestOverrideEsplicito:
    def test_enable_eval_true_forza_lattivazione_anche_in_produzione(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("ENABLE_EVAL", "true")

        assert _load_config().ENABLE_EVAL is True

    def test_enable_eval_false_forza_lo_spegnimento_anche_in_sviluppo(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("ENABLE_EVAL", "false")

        assert _load_config().ENABLE_EVAL is False
