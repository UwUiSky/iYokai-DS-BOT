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


@pytest.mark.asyncio
async def test_cog_link_spotify_senza_chiavi_non_chiama_lavalink():
    cog = MusicCog(bot=None)
    assert ms.messaggio_indisponibile("https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC")
    with patch("wavelink.Pool.fetch_tracks", new=AsyncMock()) as f, patch(
        "wavelink.Playable.search", new=AsyncMock()
    ) as s, pytest.raises(ms.FonteNonRisponde):
        await cog._cerca("https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC", object())
    f.assert_not_called()
    s.assert_not_called()
