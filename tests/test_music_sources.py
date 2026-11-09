"""
tests/test_music_sources.py
===========================
Registro delle fonti musicali (issue #126, B1, D73): classificatore dei link,
stato di ogni fonte (accesa, chiavi, pausa) e circuito di pausa.
Logica pura: nessuna rete, nessun Lavalink.
"""

import pytest

from core import music_sources as ms


@pytest.fixture(autouse=True)
def _ambiente_pulito(monkeypatch):
    for nome in (
        "MUSIC_SOURCES_ENABLED", "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "APPLE_MUSIC_TOKEN",
        "APPLE_KEY_ID", "APPLE_TEAM_ID", "APPLE_PRIVATE_KEY_PATH", "YANDEX_MUSIC_TOKEN", "TIDAL_TOKEN",
    ):
        monkeypatch.delenv(nome, raising=False)
    ms.registro.reset()


# --- classificatore -------------------------------------------------
@pytest.mark.parametrize(
    "url,atteso",
    [
        ("https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC", ("spotify", "brano")),
        ("https://open.spotify.com/intl-it/album/1DFixLWuPkv3KT3TnV35m3", ("spotify", "album")),
        ("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abc", ("spotify", "playlist")),
        ("https://open.spotify.com/artist/0TnOYISbd1XYRBk9myaseg", ("spotify", "artista")),
        ("spotify:track:4uLU6hMCjMI75M1A2tKUQC", ("spotify", "brano")),
        ("https://music.apple.com/it/song/blinding-lights/1488408568", ("applemusic", "brano")),
        ("https://music.apple.com/it/album/after-hours/1499378108", ("applemusic", "album")),
        ("https://music.apple.com/it/album/blinding-lights/1499378108?i=1499378112", ("applemusic", "brano")),
        ("https://music.apple.com/us/playlist/todays-hits/pl.f4d106fed2bd41149aaacabb233eb5eb", ("applemusic", "playlist")),
        ("https://music.apple.com/it/artist/the-weeknd/479756766", ("applemusic", "artista")),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", ("youtube", "brano")),
        ("https://youtu.be/dQw4w9WgXcQ", ("youtube", "brano")),
        ("https://music.youtube.com/playlist?list=PL123", ("youtube", "playlist")),
        ("https://soundcloud.com/artista/brano", ("soundcloud", "brano")),
        ("https://artista.bandcamp.com/album/disco", ("bandcamp", "album")),
        ("https://www.twitch.tv/qualcuno", ("twitch", "diretta")),
        ("https://vimeo.com/123456", ("vimeo", "brano")),
        ("https://tidal.com/browse/track/12345", ("tidal", "brano")),
        ("https://www.deezer.com/it/album/12345", ("deezer", "album")),
        ("https://music.yandex.ru/album/1/track/2", ("yandex", "brano")),
    ],
)
def test_classifica_i_link_delle_fonti(url, atteso):
    link = ms.classifica_link(url)
    assert link is not None and (link.fonte, link.tipo) == atteso


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/brano.mp3",  # sito non noto: link diretto
        "https://open.spotify.com.evil.example/track/abc",  # host solo simile
        "https://evilopen.spotify.com.example/track/abc",
        "https://example.com/?u=https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC",
        "http://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC",  # solo https per i servizi noti
        "https://open.spotify.com/show/abc",  # podcast: non supportato
        "https://open.spotify.com/track/",  # senza id
        "https://utente@open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC",  # userinfo
        "https://open.spotify.com:8443/track/4uLU6hMCjMI75M1A2tKUQC",  # porta
        "https://evil.example\\@open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC",  # barra rovesciata
        "https://open.spotify.com./track/4uLU6hMCjMI75M1A2tKUQC",  # punto finale
        "https://xn--pen-spotify-x1b.com/track/4uLU6hMCjMI75M1A2tKUQC",  # punycode
        "https://open.spotify.com@evil.example/track/4uLU6hMCjMI75M1A2tKUQC",
        "spotify:show:abc",
        "una canzone qualsiasi",
        "",
        "https://open.spotify.com/track/" + "a" * 400,  # oltre 300 caratteri
    ],
)
def test_non_classifica_cio_che_non_e_un_link_di_fonte(url):
    assert ms.classifica_link(url) is None


# --- stato delle fonti -------------------------------------------------
def test_di_base_spotify_e_apple_sono_spente_senza_chiavi():
    assert ms.stato_fonte("spotify") == ms.STATO_SENZA_CHIAVI
    assert ms.stato_fonte("applemusic") == ms.STATO_SENZA_CHIAVI
    assert ms.stato_fonte("soundcloud") == ms.STATO_OK
    assert ms.stato_fonte("youtube") == ms.STATO_OK


def test_con_le_chiavi_spotify_si_accende(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id-finto")
    assert ms.stato_fonte("spotify") == ms.STATO_SENZA_CHIAVI  # serve anche il secret
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret-finto")
    assert ms.stato_fonte("spotify") == ms.STATO_OK


def test_apple_accetta_il_token_oppure_la_chiave_musickit(monkeypatch):
    monkeypatch.setenv("APPLE_MUSIC_TOKEN", "token-finto")
    assert ms.stato_fonte("applemusic") == ms.STATO_OK
    monkeypatch.delenv("APPLE_MUSIC_TOKEN")
    for nome in ("APPLE_KEY_ID", "APPLE_TEAM_ID", "APPLE_PRIVATE_KEY_PATH"):
        monkeypatch.setenv(nome, "x")
    assert ms.stato_fonte("applemusic") == ms.STATO_OK


def test_yandex_e_spenta_di_base_anche_con_il_token(monkeypatch):
    monkeypatch.setenv("YANDEX_MUSIC_TOKEN", "token-finto")
    assert ms.stato_fonte("yandex") == ms.STATO_SPENTA
    monkeypatch.setenv("MUSIC_SOURCES_ENABLED", "youtube,yandex")
    assert ms.stato_fonte("yandex") == ms.STATO_OK


def test_l_owner_spegne_youtube_in_un_colpo(monkeypatch):
    monkeypatch.setenv("MUSIC_SOURCES_ENABLED", "soundcloud,bandcamp")
    assert ms.stato_fonte("youtube") == ms.STATO_SPENTA
    assert ms.stato_fonte("soundcloud") == ms.STATO_OK


def test_la_ricerca_per_titolo_parte_da_youtube_poi_soundcloud(monkeypatch):
    assert ms.prefissi_ricerca_testo() == ["ytmsearch:", "scsearch:"]
    monkeypatch.setenv("MUSIC_SOURCES_ENABLED", "soundcloud")
    assert ms.prefissi_ricerca_testo() == ["scsearch:"]
    monkeypatch.setenv("MUSIC_SOURCES_ENABLED", "bandcamp")
    assert ms.prefissi_ricerca_testo() == []


def test_deezer_non_ha_mai_una_via_con_chiave_di_decifrazione():
    chiavi = {c for g in ms.FONTI["deezer"].chiavi for c in g}
    assert not any("DECRYPT" in c.upper() or "ARL" in c.upper() for c in chiavi)
    assert ms.FONTI["deezer"].tipo_provider == "metadati"


def test_ogni_fonte_con_dominio_e_nei_siti_conosciuti():
    from core.music_settings_logic import SITI_CONOSCIUTI

    for fonte in ms.FONTI.values():
        for host in fonte.domini:
            assert any(host == s or host.endswith("." + s) for s in SITI_CONOSCIUTI), host


# --- circuito di pausa ---------------------------------------------------
def test_tre_errori_di_fila_mettono_la_fonte_in_pausa_per_dieci_minuti():
    r = ms.registro
    for i in range(2):
        r.errore("soundcloud", "timeout", adesso=100.0 + i)
    assert ms.stato_fonte("soundcloud", adesso=102.0) == ms.STATO_OK
    r.errore("soundcloud", "timeout", adesso=102.0)
    assert ms.stato_fonte("soundcloud", adesso=103.0) == ms.STATO_IN_PAUSA
    assert ms.stato_fonte("soundcloud", adesso=102.0 + 599) == ms.STATO_IN_PAUSA


def test_un_successo_azzera_gli_errori_di_fila():
    r = ms.registro
    r.errore("soundcloud", "x", adesso=1.0)
    r.errore("soundcloud", "x", adesso=2.0)
    r.ok("soundcloud")
    r.errore("soundcloud", "x", adesso=3.0)
    assert ms.stato_fonte("soundcloud", adesso=4.0) == ms.STATO_OK


@pytest.mark.parametrize("codice", [401, 403, 429])
def test_due_errori_di_blocco_in_60_secondi_mettono_in_pausa(codice):
    r = ms.registro
    r.errore("spotify", f"HTTP {codice}", adesso=10.0, codice=codice)
    assert not r.in_pausa("spotify", 11.0)
    r.errore("spotify", f"HTTP {codice}", adesso=50.0, codice=codice)
    assert r.in_pausa("spotify", 51.0)


def test_due_errori_di_blocco_a_piu_di_60_secondi_non_bastano():
    r = ms.registro
    r.errore("spotify", "HTTP 429", adesso=10.0, codice=429)
    r.errore("spotify", "HTTP 429", adesso=100.0, codice=429)
    assert not r.in_pausa("spotify", 101.0)


def test_finita_la_pausa_passa_una_sola_richiesta_di_prova():
    r = ms.registro
    for i in range(3):
        r.errore("soundcloud", "x", adesso=float(i))
    fine = 2.0 + ms.PAUSA_SECONDI
    assert r.puo_provare("soundcloud", fine - 1) is False
    assert r.puo_provare("soundcloud", fine + 1) is True  # la prova
    assert r.puo_provare("soundcloud", fine + 2) is False  # le altre aspettano
    r.ok("soundcloud")
    assert r.puo_provare("soundcloud", fine + 3) is True


def test_la_prova_fallita_rimette_la_fonte_in_pausa():
    r = ms.registro
    for i in range(3):
        r.errore("soundcloud", "x", adesso=float(i))
    fine = 2.0 + ms.PAUSA_SECONDI
    assert r.puo_provare("soundcloud", fine + 1)
    r.errore("soundcloud", "x", adesso=fine + 1)
    assert r.in_pausa("soundcloud", fine + 2)


def test_il_codice_si_legge_dal_testo_dell_errore():
    assert ms.codice_da_errore("HTTP 429 Too Many Requests") == 429
    assert ms.codice_da_errore("status code 403") == 403
    assert ms.codice_da_errore("timeout") is None
    assert ms.codice_da_errore("porta 14290 chiusa") is None


# --- messaggi all'utente ---------------------------------------------------
def test_fonte_spenta_dall_owner_non_e_usabile(monkeypatch):
    monkeypatch.setenv("MUSIC_SOURCES_ENABLED", "youtube")
    assert ms.fonte_usabile("spotify") is False


def test_spotify_senza_chiavi_nel_bot_si_prova_lo_stesso():
    # Le chiavi possono stare solo nell'.env di Lavalink: decide la risposta di Lavalink.
    assert ms.fonte_usabile("spotify") is True
    assert ms.fonte_usabile("applemusic") is True


def test_yandex_senza_chiavi_non_si_prova(monkeypatch):
    monkeypatch.setenv("MUSIC_SOURCES_ENABLED", "yandex")
    assert ms.fonte_usabile("yandex") is False


@pytest.mark.asyncio
async def test_messaggio_fonte_spenta_in_italiano_e_in_inglese(monkeypatch):
    monkeypatch.setenv("MUSIC_SOURCES_ENABLED", "youtube")
    monkeypatch.setattr("core.i18n.lingua_risposta", _lingua("it"))
    assert "non è attiva" in await ms.messaggio_per_fonte("spotify")
    monkeypatch.setattr("core.i18n.lingua_risposta", _lingua("en-US"))
    assert "is not enabled" in await ms.messaggio_per_fonte("spotify")


@pytest.mark.asyncio
async def test_messaggio_fonte_in_pausa_nella_lingua_dell_utente(monkeypatch):
    for i in range(3):
        ms.registro.errore("spotify", "x")
    monkeypatch.setattr("core.i18n.lingua_risposta", _lingua("en-US"))
    assert "is not responding" in await ms.messaggio_per_fonte("spotify")
    monkeypatch.setattr("core.i18n.lingua_risposta", _lingua("it"))
    assert "non risponde" in await ms.messaggio_per_fonte("spotify")
    assert "Riprova" in await ms.messaggio_per_fonte("sconosciuta")


def _lingua(codice):
    async def _l(*a, **k):
        return codice

    return _l


def test_riga_di_stato_non_mostra_mai_i_valori(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id-segretissimo")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "chiave-segretissima")
    testo = "\n".join(ms.righe_stato())
    assert "segretissim" not in testo
    assert "Spotify" in testo and "chiavi sì" in testo
