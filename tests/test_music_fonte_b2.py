"""
tests/test_music_fonte_b2.py
============================
Blocco B2 di #126: opzione `fonte` di /music play, fonte preferita per server (D16),
Deezer come soli metadati (ISRC, poi titolo), sezioni Yandex e Tidal nel yml generato.
Nessuna rete: wavelink e l'API di Deezer sono finti.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cogs.music.player import MusicCog
from core import music_sources as ms
from core.lavalink_yml import genera_application_yml

LINK_DEEZER = "https://www.deezer.com/it/track/3135556"


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    for v in ("MUSIC_SOURCES_ENABLED", "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "APPLE_MUSIC_TOKEN",
              "YANDEX_MUSIC_TOKEN", "TIDAL_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    ms.registro.reset()


# --- yml: Yandex e Tidal ------------------------------------------------------
def test_yml_ha_le_sezioni_yandex_e_tidal_solo_con_segnaposto():
    testo = genera_application_yml()
    assert "yandexmusic:" in testo and '"${YANDEX_MUSIC_TOKEN}"' in testo
    assert "tidal:" in testo and '"${TIDAL_TOKEN}"' in testo
    assert "yandexmusic: false" in testo and "tidal: false" in testo


def test_yml_accende_tidal_solo_se_accesa_e_con_la_chiave(monkeypatch):
    monkeypatch.setenv("MUSIC_SOURCES_ENABLED", "youtube,soundcloud,tidal")
    assert "tidal: false" in genera_application_yml()
    monkeypatch.setenv("TIDAL_TOKEN", "valoreSegretissimo77")
    testo = genera_application_yml()
    assert "tidal: true" in testo and "Segretissimo" not in testo


def test_yandex_spento_di_base_anche_con_il_token(monkeypatch):
    monkeypatch.setenv("YANDEX_MUSIC_TOKEN", "valoreSegretissimo88")
    testo = genera_application_yml()
    assert "yandexmusic: false" in testo and "Segretissimo" not in testo
    monkeypatch.setenv("MUSIC_SOURCES_ENABLED", "youtube,yandex")
    assert "yandexmusic: true" in genera_application_yml()


def test_deezer_resta_spenta_in_lavalink(monkeypatch):
    monkeypatch.setenv("MUSIC_SOURCES_ENABLED", "youtube,deezer")
    assert "deezer: false" in genera_application_yml()


# --- ricerca per fonte ------------------------------------------------------
def test_la_fonte_preferita_viene_prima():
    assert ms.prefissi_ricerca_testo("soundcloud") == ["scsearch:", "ytmsearch:"]
    assert ms.prefissi_ricerca_testo("spotify") == ["spsearch:", "ytmsearch:", "scsearch:"]
    assert ms.prefissi_ricerca_testo(None) == ["ytmsearch:", "scsearch:"]


def test_una_fonte_preferita_spenta_o_in_pausa_si_salta(monkeypatch):
    assert ms.prefissi_ricerca_testo("tidal") == ["ytmsearch:", "scsearch:"]  # spenta di base
    for _ in range(3):
        ms.registro.errore("spotify", "x")
    assert ms.prefissi_ricerca_testo("spotify") == ["ytmsearch:", "scsearch:"]


@pytest.mark.asyncio
async def test_cerca_testo_con_preferita_ripiega_sul_predefinito():
    chiamate = []

    async def esegui(q):
        chiamate.append(q)
        if q.startswith("spsearch:"):
            raise RuntimeError("giù")
        return ["ok"]

    assert await ms.cerca_testo("canzone", esegui, "spotify") == ["ok"]
    assert chiamate == ["spsearch:canzone", "ytmsearch:canzone"]


def test_fonti_di_ricerca_sono_sei_e_disponibili_dipende_dallo_stato():
    assert len(ms.FONTI_DI_RICERCA) == 6
    assert ms.fonte_di_ricerca_disponibile("youtube")
    assert not ms.fonte_di_ricerca_disponibile("tidal")  # spenta di base
    assert not ms.fonte_di_ricerca_disponibile("bandcamp")  # non è una fonte di ricerca
    assert ms.fonte_di_ricerca_disponibile("deezer")


# --- Deezer: solo metadati --------------------------------------------------
TRACCIA = {"title": "One More Time", "artist": {"name": "Daft Punk"}, "isrc": "GBDUW0000059"}


def test_metadati_di_un_brano():
    m = ms.interpreta_deezer("brano", TRACCIA)
    assert m == [ms.Metadato("One More Time", "Daft Punk", "GBDUW0000059")]


def test_metadati_di_un_album_con_tetto_e_senza_isrc():
    dati = {"data": [{"title": f"T{i}", "artist": {"name": "A"}} for i in range(30)]}
    m = ms.interpreta_deezer("album", dati)
    assert len(m) == ms.MAX_BRANI_DEEZER and m[0].isrc == ""


def test_isrc_non_valido_viene_scartato_e_i_testi_sono_corti():
    dati = {"title": "x" * 500, "artist": {"name": "a" * 500}, "isrc": '" OR 1; drop'}
    m = ms.interpreta_deezer("brano", dati)[0]
    assert m.isrc == "" and len(m.titolo) <= 150 and len(m.artista) <= 150


def test_risposta_con_errore_o_senza_titolo_non_da_metadati():
    assert ms.interpreta_deezer("brano", {"error": {"code": 800}}) == []
    assert ms.interpreta_deezer("brano", {"artist": {}}) == []


def test_ricerche_prima_isrc_poi_titolo():
    m = ms.Metadato("One More Time", "Daft Punk", "GBDUW0000059")
    assert ms.ricerche_da_metadato(m) == ['"GBDUW0000059"', "Daft Punk One More Time"]
    assert ms.ricerche_da_metadato(ms.Metadato("T", "A", "")) == ["A T"]


def test_id_del_link_deezer():
    assert ms.id_deezer(LINK_DEEZER) == "3135556"
    assert ms.id_deezer("https://www.deezer.com/album/302127") == "302127"
    assert ms.id_deezer("https://www.deezer.com/it/profile/55") is None
    assert ms.id_deezer("https://example.com/track/55") is None


@pytest.mark.asyncio
async def test_metadati_deezer_usa_solo_l_api_pubblica_senza_credenziali():
    scaricati = []

    async def finto(url):
        scaricati.append(url)
        return TRACCIA

    with patch.object(ms, "_scarica_json", new=finto):
        m = await ms.metadati_deezer("brano", "3135556")
    assert m[0].titolo == "One More Time"
    assert scaricati == ["https://api.deezer.com/track/3135556"]
    import inspect
    sorgente = inspect.getsource(ms._scarica_json)
    assert "arl" not in sorgente.lower().replace("charl", "") or "Cookie" not in sorgente
    assert "masterDecryptionKey" not in inspect.getsource(ms)


@pytest.mark.asyncio
async def test_errore_http_di_deezer_conta_per_il_circuito():
    async def giu(url):
        raise RuntimeError("Deezer HTTP 429")

    with patch.object(ms, "_scarica_json", new=giu):
        for _ in range(3):
            with pytest.raises(ms.FonteNonRisponde):
                await ms.cerca_link("deezer", lambda: ms.metadati_deezer("brano", "1"))
    assert ms.stato_fonte("deezer") == ms.STATO_IN_PAUSA


@pytest.mark.asyncio
async def test_link_deezer_cerca_prima_per_isrc_poi_per_titolo():
    cog = MusicCog(bot=None)
    chiamate = []

    async def _fetch(query, node=None):
        chiamate.append(query)
        return [] if "GBDUW" in query else ["trovato"]

    with patch.object(ms, "_scarica_json", new=AsyncMock(return_value=TRACCIA)), patch(
        "wavelink.Pool.fetch_tracks", new=AsyncMock(side_effect=_fetch)
    ), patch("wavelink.Playable.search", new=AsyncMock()) as diretta:
        risultato, _ = await cog._cerca(LINK_DEEZER, object())
    assert risultato == ["trovato"]
    assert chiamate == ['ytmsearch:"GBDUW0000059"', "ytmsearch:Daft Punk One More Time"]
    diretta.assert_not_called()  # il link Deezer non va mai a Lavalink


@pytest.mark.asyncio
async def test_link_deezer_con_fonte_spenta_da_messaggio_chiaro(monkeypatch):
    monkeypatch.setenv("MUSIC_SOURCES_ENABLED", "youtube,soundcloud")
    cog = MusicCog(bot=None)
    with pytest.raises(ms.FonteNonRisponde):
        await cog._cerca(LINK_DEEZER, object())


@pytest.mark.asyncio
async def test_album_deezer_diventa_una_playlist_di_brani_trovati():
    cog = MusicCog(bot=None)
    dati = {"data": [{"title": f"T{i}", "artist": {"name": "A"}} for i in range(3)]}

    def _traccia(i):
        return SimpleNamespace(raw_data={"encoded": f"e{i}", "info": {"title": f"T{i}", "author": "A", "length": 1000,
                "identifier": f"id{i}", "isStream": False, "isSeekable": True, "uri": None, "sourceName": "youtube",
                "position": 0, "artworkUrl": None, "isrc": None}, "pluginInfo": {}, "userData": {}})

    async def _fetch(query, node=None):
        return [_traccia(query[-1])]

    with patch.object(ms, "_scarica_json", new=AsyncMock(return_value=dati)), patch(
        "wavelink.Pool.fetch_tracks", new=AsyncMock(side_effect=_fetch)
    ):
        risultato, _ = await cog._cerca("https://www.deezer.com/album/302127", object())
    import wavelink
    assert isinstance(risultato, wavelink.Playlist) and len(risultato.tracks) == 3


@pytest.mark.asyncio
async def test_titolo_con_fonte_deezer_legge_i_metadati_poi_cerca_altrove():
    cog = MusicCog(bot=None)
    chiamate = []

    async def _fetch(query, node=None):
        chiamate.append(query)
        return ["ok"]

    with patch.object(ms, "_scarica_json", new=AsyncMock(return_value={"data": [TRACCIA]})) as s, patch(
        "wavelink.Pool.fetch_tracks", new=AsyncMock(side_effect=_fetch)
    ):
        risultato, _ = await cog._cerca("one more time", object(), None, "deezer")
    assert risultato == ["ok"]
    assert s.call_args.args[0].startswith("https://api.deezer.com/search?")
    assert chiamate[0] == 'ytmsearch:"GBDUW0000059"'


@pytest.mark.asyncio
async def test_titolo_con_fonte_deezer_se_deezer_non_risponde_ripiega_sul_predefinito():
    cog = MusicCog(bot=None)

    async def giu(url):
        raise RuntimeError("giù")

    with patch.object(ms, "_scarica_json", new=giu), patch(
        "wavelink.Pool.fetch_tracks", new=AsyncMock(return_value=["ok"])
    ) as f:
        risultato, _ = await cog._cerca("canzone", object(), None, "deezer")
    assert risultato == ["ok"] and f.call_args.args[0] == "ytmsearch:canzone"


# --- opzione fonte nel cog ----------------------------------------------------
@pytest.mark.asyncio
async def test_titolo_con_fonte_spotify_usa_spsearch():
    cog = MusicCog(bot=None)
    with patch("wavelink.Pool.fetch_tracks", new=AsyncMock(return_value=["ok"])) as f:
        await cog._cerca("canzone", object(), None, "spotify")
    assert f.call_args.args[0] == "spsearch:canzone"


@pytest.mark.asyncio
async def test_un_link_vince_sulla_fonte_scelta():
    cog = MusicCog(bot=None)
    with patch("cogs.music.player.url_e_sicuro", new=AsyncMock(return_value=True)), patch(
        "wavelink.Playable.search", new=AsyncMock(return_value=["ok"])
    ) as s, patch("wavelink.Pool.fetch_tracks", new=AsyncMock()) as f:
        await cog._cerca("https://soundcloud.com/a/b", object(), None, "spotify")
    s.assert_called_once()
    f.assert_not_called()


def test_play_ha_l_opzione_fonte_con_sei_scelte():
    cb = MusicCog.play.callback
    scelte = cb.__discord_app_commands_param_choices__["fonte"]
    assert [c.value for c in scelte] == list(ms.FONTI_DI_RICERCA)
    assert len(scelte) <= 25
    assert len(cb.__discord_app_commands_param_description__["fonte"]) <= 100
    import inspect
    assert len(inspect.signature(cb).parameters) - 2 <= 25  # senza self e interaction


@pytest.mark.asyncio
async def test_play_con_fonte_spenta_risponde_prima_del_defer(monkeypatch):
    cog = MusicCog(bot=None)
    cog._controlli_base = AsyncMock(return_value=True)
    cog.accoda = AsyncMock()
    i = MagicMock()
    i.response.send_message = AsyncMock()
    i.response.defer = AsyncMock()
    i.guild_id, i.user.id, i.locale = 1, 2, None
    await cog.play.callback(cog, i, "canzone", False, None, "tidal")
    i.response.send_message.assert_called_once()
    assert i.response.send_message.call_args.kwargs["ephemeral"] is True
    i.response.defer.assert_not_called()
    cog.accoda.assert_not_called()


@pytest.mark.asyncio
async def test_play_passa_la_fonte_ad_accoda():
    cog = MusicCog(bot=None)
    cog._controlli_base = AsyncMock(return_value=True)
    cog.accoda = AsyncMock()
    i = MagicMock()
    i.response.defer = AsyncMock()
    await cog.play.callback(cog, i, "canzone", False, None, "soundcloud")
    assert cog.accoda.call_args.kwargs["fonte"] == "soundcloud"


@pytest.mark.asyncio
async def test_la_fonte_di_default_del_server_vale_se_non_si_sceglie():
    from core.music_settings_logic import MusicSettings

    cog = MusicCog(bot=MagicMock())
    cog.bot.music_nodes = MagicMock()
    cog.bot.music_nodes.node_for.return_value = object()
    cog.bot.music_nodes.locale_di.return_value = None
    cog.bot.music_fleet.release_session = AsyncMock()
    worker_guild = MagicMock()
    worker_guild.voice_client = None
    cog._cerca = AsyncMock(return_value=([], object()))
    imp = MusicSettings(default_search="soundcloud")
    await cog._play_nel_canale(1, 2, "x", False, imp, MagicMock(), worker_guild, 3, AsyncMock())
    assert cog._cerca.call_args.args[3] == "soundcloud"
    cog._cerca.reset_mock()
    await cog._play_nel_canale(1, 2, "x", False, imp, MagicMock(), worker_guild, 3, AsyncMock(), None, "spotify")
    assert cog._cerca.call_args.args[3] == "spotify"
