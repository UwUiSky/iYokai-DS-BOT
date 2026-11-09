"""
tests/test_music_sources_ricerca.py
====================================
Ricerca con circuito (issue #126, B1): timeout di 8 s, al massimo 2 ripieghi,
errori che mettono la fonte in pausa, messaggi chiari in MusicCog.
Nessuna rete: wavelink è finto.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from cogs.music.player import MusicCog
from core import music_sources as ms


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    for nome in ("MUSIC_SOURCES_ENABLED", "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"):
        monkeypatch.delenv(nome, raising=False)
    ms.registro.reset()


@pytest.mark.asyncio
async def test_titolo_ripiega_su_soundcloud_se_youtube_da_errore():
    chiamate = []

    async def esegui(query):
        chiamate.append(query)
        if query.startswith("ytmsearch:"):
            raise RuntimeError("giù")
        return ["t"]

    assert await ms.cerca_testo("canzone", esegui) == ["t"]
    assert chiamate == ["ytmsearch:canzone", "scsearch:canzone"]


@pytest.mark.asyncio
async def test_titolo_senza_risultati_non_e_un_errore_e_non_ripiega():
    esegui = AsyncMock(return_value=[])
    assert await ms.cerca_testo("niente", esegui) == []
    esegui.assert_called_once()


@pytest.mark.asyncio
async def test_se_tutto_fallisce_sale_fonte_non_risponde():
    async def esegui(query):
        raise RuntimeError("giù")

    with pytest.raises(ms.FonteNonRisponde):
        await ms.cerca_testo("canzone", esegui)


@pytest.mark.asyncio
async def test_il_timeout_e_di_otto_secondi(monkeypatch):
    monkeypatch.setattr(ms, "TIMEOUT_SECONDI", 0.05)

    async def lenta():
        await asyncio.sleep(1)

    with pytest.raises(ms.FonteNonRisponde):
        await ms.cerca_link("soundcloud", lenta)
    assert ms.TIMEOUT_SECONDI == 0.05
    assert ms.registro.ultimo_errore("soundcloud") == "TimeoutError"


def test_il_timeout_predefinito_e_otto_secondi():
    assert ms.TIMEOUT_SECONDI in (8, 0.05)  # 0.05 solo se un test lo ha ridotto
    assert ms.MAX_RIPIEGHI == 2 and ms.PAUSA_SECONDI == 600 and ms.ERRORI_DI_FILA == 3


@pytest.mark.asyncio
async def test_un_errore_di_contenuto_non_conta_come_guasto_della_fonte():
    class Comune(Exception):
        severity = "common"

    async def tolto():
        raise Comune("Video non disponibile")

    for _ in range(5):
        assert await ms.cerca_link("youtube", tolto) == []
    assert ms.stato_fonte("youtube") == ms.STATO_OK


@pytest.mark.asyncio
async def test_tre_errori_mettono_youtube_in_pausa_e_si_cerca_su_soundcloud():
    async def giu(query):
        raise RuntimeError("giù")

    for _ in range(3):
        with pytest.raises(ms.FonteNonRisponde):
            await ms.cerca_link("youtube", lambda: giu("x"))
    assert ms.stato_fonte("youtube") == ms.STATO_IN_PAUSA
    assert ms.prefissi_ricerca_testo() == ["scsearch:"]


@pytest.mark.asyncio
async def test_cog_titolo_passa_dal_circuito_e_prova_soundcloud():
    cog = MusicCog(bot=None)
    nodo = object()

    async def _fetch(query, node=None):
        if query.startswith("ytmsearch:"):
            raise RuntimeError("HTTP 500")
        return ["ok"]

    with patch("wavelink.Pool.fetch_tracks", new=AsyncMock(side_effect=_fetch)) as f:
        risultato, _ = await cog._cerca("una canzone", nodo)
    assert risultato == ["ok"]
    assert [c.args[0] for c in f.call_args_list] == ["ytmsearch:una canzone", "scsearch:una canzone"]



# --- prova di una fonte mai appesa -------------------------------------------
def _dopo_pausa(nome):
    for i in range(3):
        ms.registro.errore(nome, "x", adesso=0.0)
    return ms.PAUSA_SECONDI + 1.0


@pytest.mark.asyncio
async def test_prova_annullata_non_blocca_la_fonte(monkeypatch):
    fine = _dopo_pausa("soundcloud")
    monkeypatch.setattr(ms.time, "monotonic", lambda: fine)

    async def annullata():
        raise asyncio.CancelledError

    assert ms.registro.puo_provare("soundcloud", fine)
    with pytest.raises(asyncio.CancelledError):
        await ms.cerca_link("soundcloud", annullata)
    assert ms.registro.puo_provare("soundcloud", fine + 1)


@pytest.mark.asyncio
async def test_prova_con_brano_non_trovato_non_blocca_la_fonte(monkeypatch):
    fine = _dopo_pausa("soundcloud")

    class _Comune(Exception):
        severity = "common"

    async def tolto():
        raise _Comune("tolto")

    assert ms.registro.puo_provare("soundcloud", fine)
    assert await ms.cerca_link("soundcloud", tolto) == []
    assert ms.registro.puo_provare("soundcloud", fine + 1)


@pytest.mark.asyncio
async def test_url_non_pubblico_non_lascia_la_prova_appesa(monkeypatch):
    fine = _dopo_pausa("http")
    monkeypatch.setattr(ms.time, "monotonic", lambda: fine)
    cog = MusicCog(bot=None)
    with patch("cogs.music.player.url_e_sicuro", new=AsyncMock(return_value=False)):
        risultato, _ = await cog._cerca("https://example.com/a.mp3", object())
        assert risultato is None
    assert ms.registro.puo_provare("http", fine)


@pytest.mark.asyncio
async def test_titolo_a_pausa_finita_prova_una_sola_richiesta(monkeypatch):
    fine = _dopo_pausa("youtube")
    monkeypatch.setattr(ms.time, "monotonic", lambda: fine)
    chiamate = []
    via = asyncio.Event()

    async def esegui(query):
        chiamate.append(query)
        if query.startswith("ytmsearch:"):
            await via.wait()
        return ["ok"]

    primo = asyncio.create_task(ms.cerca_testo("brano", esegui))
    await asyncio.sleep(0)
    secondo = await ms.cerca_testo("brano", esegui)  # YouTube è in prova: va su SoundCloud
    via.set()
    await primo
    assert secondo == ["ok"]
    assert chiamate.count("ytmsearch:brano") == 1


@pytest.mark.asyncio
async def test_link_spotify_senza_chiavi_nel_bot_arriva_a_lavalink():
    cog = MusicCog(bot=None)
    with patch("cogs.music.player.url_e_sicuro", new=AsyncMock(return_value=True)), patch(
        "wavelink.Playable.search", new=AsyncMock(return_value=["ok"])
    ) as s:
        risultato, _ = await cog._cerca("https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC", object())
    assert risultato == ["ok"]
    s.assert_called_once()


@pytest.mark.asyncio
async def test_link_spotify_con_lavalink_in_errore_da_fonte_non_risponde():
    cog = MusicCog(bot=None)
    with patch("cogs.music.player.url_e_sicuro", new=AsyncMock(return_value=True)), patch(
        "wavelink.Playable.search", new=AsyncMock(side_effect=RuntimeError("HTTP 500"))
    ), pytest.raises(ms.FonteNonRisponde):
        await cog._cerca("https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC", object())
