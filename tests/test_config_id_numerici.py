"""
tests/test_config_id_numerici.py
================================
OWNER_ID e MAIN_GUILD_ID devono essere numeri. Con un valore non
numerico l'avvio si ferma con un messaggio che nomina la variabile,
non con un ValueError di Python senza contesto.
"""

import pytest

from core.config import _load_config


@pytest.mark.parametrize("variabile", ["OWNER_ID", "MAIN_GUILD_ID"])
@pytest.mark.parametrize("valore", ["abc", "12 34", "123abc", "<@123456789>"])
def test_id_non_numerico_ferma_l_avvio_nominando_la_variabile(
    monkeypatch, capsys, variabile, valore
):
    monkeypatch.setenv(variabile, valore)

    with pytest.raises(SystemExit) as uscita:
        _load_config()

    assert uscita.value.code == 1
    messaggio = capsys.readouterr().err
    assert variabile in messaggio
    assert "numero" in messaggio
    assert valore in messaggio


def test_id_numerici_vengono_letti_come_interi(monkeypatch):
    monkeypatch.setenv("OWNER_ID", " 123456789012345678 ")
    monkeypatch.setenv("MAIN_GUILD_ID", "987654321098765432")

    config = _load_config()

    assert config.OWNER_ID == 123456789012345678
    assert config.MAIN_GUILD_ID == 987654321098765432
