"""
tests/test_music_chiavi_non_nei_log.py
=======================================
Le chiavi delle fonti musicali (Spotify, Apple, ...) non finiscono mai nei log,
nei messaggi agli utenti, nello stato di /owner radio fonti né nel repr della
configurazione (issue #126, B1, D73). Il bot sa solo «presente sì/no».
"""

import logging

import pytest

from core import music_sources as ms

VALORI = {
    "SPOTIFY_CLIENT_ID": "idSpotifyFINTO-8841",
    "SPOTIFY_CLIENT_SECRET": "segretoSpotifyFINTO-7712",
    "APPLE_MUSIC_TOKEN": "tokenAppleFINTO-5530",
    "YANDEX_MUSIC_TOKEN": "tokenYandexFINTO-9021",
    "TIDAL_TOKEN": "tokenTidalFINTO-1187",
}


@pytest.fixture(autouse=True)
def _chiavi_finte(monkeypatch):
    for k, v in VALORI.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("MUSIC_SOURCES_ENABLED", "youtube,spotify,applemusic,yandex,tidal")
    ms.registro.reset()


def _niente_chiavi(testo: str):
    for v in VALORI.values():
        assert v not in testo, v


@pytest.mark.asyncio
async def test_un_errore_che_contiene_la_chiave_viene_ripulito(caplog):
    async def guasta():
        raise RuntimeError(f"401 token {VALORI['SPOTIFY_CLIENT_SECRET']} rifiutato")

    with caplog.at_level(logging.DEBUG), pytest.raises(ms.FonteNonRisponde):
        await ms.cerca_link("spotify", guasta)
    _niente_chiavi(ms.registro.ultimo_errore("spotify"))
    _niente_chiavi(caplog.text)
    _niente_chiavi("\n".join(ms.righe_stato()))
    _niente_chiavi(await ms.messaggio_per_fonte("spotify"))


def test_ripulisci_toglie_ogni_valore():
    testo = " ".join(VALORI.values())
    assert ms.ripulisci(testo) == " ".join(["***"] * len(VALORI))


def test_lo_stato_dice_solo_si_o_no():
    righe = "\n".join(ms.righe_stato())
    _niente_chiavi(righe)
    assert "chiavi sì" in righe


def test_il_repr_della_configurazione_non_contiene_le_chiavi_delle_fonti():
    from core.config import _load_config

    config = _load_config()
    _niente_chiavi(repr(config))
    assert not any(v in str(getattr(config, c)) for c in vars(config) for v in VALORI.values())
