"""
tests/test_config_repr_non_svela_segreti.py
===============================================
SEC-16: oggi nessun log stampa `config` per intero, ma basterebbe un
`logger.info(config)` (o un `print(config)` di debug lasciato per
sbaglio) per finire con token Discord, password del database, chiavi
API e chiavi di cifratura nei log in chiaro. `field(repr=False)` sui
campi segreti evita che `repr()`/`str()` li includa — i valori restano
comunque leggibili accedendo al campo per nome (`config.YOKAI_BOT_TOKEN`),
solo non compaiono più "per sbaglio" in una stampa dell'intero oggetto.
"""

from core.config import _load_config


def test_repr_di_config_non_contiene_nessun_segreto(monkeypatch):
    monkeypatch.setenv("YOKAI_BOT_TOKEN", "segreto-bot-main")
    monkeypatch.setenv("YOKAI_CREATOR_TOKEN", "segreto-bot-creator")
    for i in range(1, 6):
        monkeypatch.setenv(f"MUSIC_TOKEN_{i}", f"segreto-music-{i}")
    monkeypatch.setenv("NSFW_TOKEN", "segreto-nsfw")
    monkeypatch.setenv("DATABASE_URL", "postgresql://utente:segreto-db@localhost/db")
    monkeypatch.setenv("LAVALINK_PASSWORD", "segreto-lavalink")
    monkeypatch.setenv("LAVALINK_NODES", "uri1|segreto-nodo-extra")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "segreto-twitch")
    monkeypatch.setenv("YOUTUBE_API_KEY", "segreto-youtube")
    monkeypatch.setenv("PIXABAY_API_KEY", "segreto-pixabay")
    monkeypatch.setenv("OAUTH2_CLIENT_SECRET", "segreto-oauth2")
    monkeypatch.setenv("WEB_PANEL_SECRET_KEY", "segreto-web-panel")
    monkeypatch.setenv("OAUTH_ENCRYPTION_KEY", "segreto-cifratura")

    config = _load_config()
    testo = repr(config)

    for valore_segreto in [
        "segreto-bot-main",
        "segreto-bot-creator",
        "segreto-music-1",
        "segreto-nsfw",
        "segreto-db",
        "segreto-lavalink",
        "segreto-nodo-extra",
        "segreto-twitch",
        "segreto-youtube",
        "segreto-pixabay",
        "segreto-oauth2",
        "segreto-web-panel",
        "segreto-cifratura",
    ]:
        assert valore_segreto not in testo, f"'{valore_segreto}' compare ancora in repr(config)"


def test_i_campi_segreti_restano_comunque_leggibili_per_nome(monkeypatch):
    # repr=False nasconde solo la STAMPA dell'intero oggetto — i
    # valori devono restare normalmente accessibili, altrimenti il
    # resto del bot smette di funzionare.
    monkeypatch.setenv("YOKAI_BOT_TOKEN", "segreto-bot-main")

    config = _load_config()

    assert config.YOKAI_BOT_TOKEN == "segreto-bot-main"


def test_repr_di_config_menziona_ancora_i_campi_non_segreti(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")

    testo = repr(_load_config())

    # Un repr utile per il debug non deve diventare inutile: i campi
    # NON sensibili (es. ENVIRONMENT) devono restare visibili.
    assert "ENVIRONMENT='development'" in testo
