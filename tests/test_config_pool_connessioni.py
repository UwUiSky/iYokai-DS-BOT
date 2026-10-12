"""
M 14.6 (LIM-50): Aiven gratuito concede 20 connessioni. In sviluppo il pool
parte piccolo (2-5); in produzione resta 5-10. Le variabili DB_POOL_MIN e
DB_POOL_MAX valgono sempre, in entrambi gli ambienti.
"""

import pytest

from core.config import _load_config


@pytest.fixture(autouse=True)
def _senza_variabili_pool(monkeypatch):
    monkeypatch.delenv("DB_POOL_MIN", raising=False)
    monkeypatch.delenv("DB_POOL_MAX", raising=False)


def test_in_sviluppo_il_pool_e_piccolo(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    c = _load_config()
    assert (c.DB_POOL_MIN, c.DB_POOL_MAX) == (2, 5)


def test_in_produzione_il_pool_resta_5_10(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    c = _load_config()
    assert (c.DB_POOL_MIN, c.DB_POOL_MAX) == (5, 10)


@pytest.mark.parametrize("ambiente", ["development", "production"])
def test_i_valori_del_file_env_vincono(monkeypatch, ambiente):
    monkeypatch.setenv("ENVIRONMENT", ambiente)
    monkeypatch.setenv("DB_POOL_MIN", "1")
    monkeypatch.setenv("DB_POOL_MAX", "3")
    c = _load_config()
    assert (c.DB_POOL_MIN, c.DB_POOL_MAX) == (1, 3)


def test_env_example_spiega_il_limite_di_aiven():
    from pathlib import Path

    testo = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    assert "20 connessioni" in testo
