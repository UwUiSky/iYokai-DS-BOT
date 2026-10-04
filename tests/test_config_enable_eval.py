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

import pytest

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


class TestEnvironmentSoloValoriNoti:
    """
    Prima qualunque ENVIRONMENT diverso da "production" esatto (anche
    "prod", "live" o la variabile assente) accendeva eval e lo sblocco
    premium in silenzio. Ora l'avvio viene rifiutato.
    """

    @pytest.mark.parametrize("valore", ["prod", "live", "staging", "produzione", "production2"])
    def test_valore_sconosciuto_ferma_l_avvio_con_un_messaggio_chiaro(
        self, monkeypatch, capsys, valore
    ):
        monkeypatch.setenv("ENVIRONMENT", valore)
        monkeypatch.delenv("ENABLE_EVAL", raising=False)

        with pytest.raises(SystemExit) as uscita:
            _load_config()

        assert uscita.value.code == 1
        errore = capsys.readouterr().err
        assert "ENVIRONMENT" in errore and valore in errore
        assert "development" in errore and "production" in errore

    @pytest.mark.parametrize("valore", [None, "", "   "])
    def test_environment_assente_o_vuoto_ferma_l_avvio(self, monkeypatch, capsys, valore):
        if valore is None:
            monkeypatch.delenv("ENVIRONMENT", raising=False)
        else:
            monkeypatch.setenv("ENVIRONMENT", valore)
        # Nemmeno un ENABLE_EVAL esplicito rende valido un ambiente ignoto.
        monkeypatch.setenv("ENABLE_EVAL", "false")

        with pytest.raises(SystemExit):
            _load_config()

        assert "ENVIRONMENT" in capsys.readouterr().err

    @pytest.mark.parametrize("valore", ["  Production ", "PRODUCTION", "production"])
    def test_production_con_spazi_e_maiuscole_spegne_eval_e_sblocco_premium(
        self, monkeypatch, valore
    ):
        monkeypatch.setenv("ENVIRONMENT", valore)
        monkeypatch.delenv("ENABLE_EVAL", raising=False)
        monkeypatch.delenv("PREMIUM_ALPHA_UNLOCK_ALL", raising=False)

        caricata = _load_config()

        assert caricata.ENVIRONMENT == "production" and caricata.is_production
        assert caricata.ENABLE_EVAL is False
        assert caricata.PREMIUM_ALPHA_UNLOCK_ALL is False

    def test_development_con_maiuscole_resta_sviluppo(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", " Development ")
        monkeypatch.delenv("ENABLE_EVAL", raising=False)

        caricata = _load_config()

        assert caricata.ENVIRONMENT == "development" and caricata.is_development
        assert caricata.ENABLE_EVAL is True


class TestAvvisoAllAvvio:
    def _config_con(self, monkeypatch, **campi):
        import dataclasses

        import main as main_module

        monkeypatch.setattr(main_module, "config", dataclasses.replace(main_module.config, **campi))
        return main_module

    def test_eval_acceso_viene_segnalato_con_un_warning(self, monkeypatch, caplog):
        main_module = self._config_con(monkeypatch, ENABLE_EVAL=True, PREMIUM_ALPHA_UNLOCK_ALL=False)

        with caplog.at_level("WARNING", logger="iyokai.main"):
            main_module.avvisa_opzioni_rischiose()

        avvisi = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        assert len(avvisi) == 1 and "ENABLE_EVAL" in avvisi[0]

    def test_eval_spento_nessun_warning(self, monkeypatch, caplog):
        main_module = self._config_con(monkeypatch, ENABLE_EVAL=False, PREMIUM_ALPHA_UNLOCK_ALL=False)

        with caplog.at_level("WARNING", logger="iyokai.main"):
            main_module.avvisa_opzioni_rischiose()

        assert caplog.records == []
