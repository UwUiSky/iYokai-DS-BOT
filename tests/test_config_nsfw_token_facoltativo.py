"""
tests/test_config_nsfw_token_facoltativo.py
===========================================
NSFW_TOKEN è facoltativo finché l'istanza NSFW non esiste (NF-23):
nessuna parte del bot lo usa, quindi la sua assenza non deve fermare
l'avvio. Gli altri token restano obbligatori.
"""

import pytest

from core.config import _load_config


@pytest.mark.parametrize("valore", [None, "", "   "])
def test_avvio_senza_nsfw_token(monkeypatch, valore):
    if valore is None:
        monkeypatch.delenv("NSFW_TOKEN", raising=False)
    else:
        monkeypatch.setenv("NSFW_TOKEN", valore)

    assert _load_config().NSFW_TOKEN == ""


def test_nsfw_token_impostato_viene_letto_e_non_compare_nel_repr(monkeypatch):
    monkeypatch.setenv("NSFW_TOKEN", "segreto-nsfw")

    config = _load_config()

    assert config.NSFW_TOKEN == "segreto-nsfw"
    assert "segreto-nsfw" not in repr(config)


def test_il_token_del_bot_principale_resta_obbligatorio(monkeypatch, capsys):
    monkeypatch.delenv("YOKAI_BOT_TOKEN", raising=False)

    with pytest.raises(SystemExit):
        _load_config()

    assert "YOKAI_BOT_TOKEN" in capsys.readouterr().err
