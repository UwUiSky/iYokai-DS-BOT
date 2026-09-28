"""
tests/test_config_web_bind_host.py
======================================
SEC-14: i due piccoli server web del progetto (callback OAuth2 del
restore, webhook custom in ricezione) devono ascoltare su localhost
per default, non su 0.0.0.0 — sta al reverse proxy (con HTTPS)
davanti esporli all'esterno. Un solo indirizzo condiviso
(WEB_BIND_HOST) invece di uno per server, così chi vuole cambiarlo
tocca una sola variabile in .env. Stesso pattern di
test_config_enable_eval.py: chiama _load_config() direttamente.
"""

from core.config import _load_config


class TestDefaultWebBindHost:
    def test_default_e_localhost_non_tutte_le_interfacce(self, monkeypatch):
        monkeypatch.delenv("WEB_BIND_HOST", raising=False)

        assert _load_config().WEB_BIND_HOST == "127.0.0.1"


class TestOverrideWebBindHost:
    def test_si_puo_forzare_un_altro_indirizzo(self, monkeypatch):
        monkeypatch.setenv("WEB_BIND_HOST", "0.0.0.0")

        assert _load_config().WEB_BIND_HOST == "0.0.0.0"
