"""
tests/test_music_lavalink_yml.py
=================================
Generatore di application.yml per Lavalink (issue #126, B1, D73): fonti accese,
chiavi solo come ${VARIABILE}, nessun valore nel file. Il file in repository
deve coincidere con quello generato senza chiavi.
"""

import re
from pathlib import Path

import pytest

from core import music_sources as ms
from core.lavalink_yml import genera_application_yml

RADICE = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    for v in ("MUSIC_SOURCES_ENABLED", "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "APPLE_MUSIC_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    ms.registro.reset()


def _riga(testo, chiave):
    return re.search(rf"^\s*{chiave}:\s*(\S+)", testo, re.MULTILINE).group(1)


def test_senza_chiavi_spotify_e_apple_restano_spenti():
    y = genera_application_yml()
    assert _riga(y, "spotify") == "false" and _riga(y, "applemusic") == "false"
    assert '"${SPOTIFY_CLIENT_ID}"' in y  # la sezione c'è, ma solo con segnaposto


def test_con_le_chiavi_spotify_si_accende_con_i_segnaposto(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id-segreto-123")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret-segreto-456")
    y = genera_application_yml()
    assert _riga(y, "spotify") == "true"
    assert '"${SPOTIFY_CLIENT_ID}"' in y and '"${SPOTIFY_CLIENT_SECRET}"' in y
    assert "segreto-123" not in y and "segreto-456" not in y


def test_apple_con_token_usa_il_segnaposto(monkeypatch):
    monkeypatch.setenv("APPLE_MUSIC_TOKEN", "token-apple-segreto")
    y = genera_application_yml()
    assert _riga(y, "applemusic") == "true"
    assert '"${APPLE_MUSIC_TOKEN}"' in y and "token-apple-segreto" not in y


def test_provider_con_youtube_acceso_prima_isrc_poi_titolo():
    y = genera_application_yml()
    assert y.index('ytsearch:"%ISRC%"') < y.index("ytsearch:%QUERY%") < y.index("scsearch:%QUERY%")


def test_spegnendo_youtube_restano_solo_i_provider_soundcloud(monkeypatch):
    monkeypatch.setenv("MUSIC_SOURCES_ENABLED", "soundcloud,bandcamp,http")
    y = genera_application_yml()
    assert "ytsearch" not in y and "scsearch:%QUERY%" in y
    assert _riga(y, "enabled") == "false"  # plugin YouTube spento
    assert _riga(y, "youtube") == "false"


def test_twitch_e_vimeo_seguono_le_fonti_accese(monkeypatch):
    assert _riga(genera_application_yml(), "twitch") == "true"
    monkeypatch.setenv("MUSIC_SOURCES_ENABLED", "youtube,soundcloud")
    y = genera_application_yml()
    assert _riga(y, "twitch") == "false" and _riga(y, "vimeo") == "false" and _riga(y, "http") == "false"


def test_deezer_resta_sempre_spento_e_senza_chiavi_di_decifrazione(monkeypatch):
    monkeypatch.setenv("MUSIC_SOURCES_ENABLED", "deezer,youtube")
    y = genera_application_yml()
    assert _riga(y, "deezer") == "false"
    assert "masterDecryptionKey" not in y and "arl" not in y.lower().split("deezer")[-1][:200]


def test_il_file_in_repository_e_quello_generato_senza_chiavi():
    assert (RADICE / "deploy/lavalink/application.yml").read_text(encoding="utf-8") == genera_application_yml()


def test_il_compose_e_l_esempio_non_contengono_valori_di_chiavi():
    compose = (RADICE / "deploy/lavalink/docker-compose.yml").read_text(encoding="utf-8")
    for v in ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "APPLE_MUSIC_TOKEN", "YANDEX_MUSIC_TOKEN", "TIDAL_TOKEN"):
        assert f"{v}=${{{v}:-}}" in compose
