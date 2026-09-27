"""
tests/test_music_spotify_fallback.py
========================================
Test di MusicCog._search_with_spotify_fallback (SPEC.md §9.5) — la
query Spotify che non risolve sui nodi pubblici deve ritentare
pinnata sul nodo locale/self-hostato (LOCAL_NODE_IDENTIFIER), MAI
per query non-Spotify o quando il nodo locale non è configurato.
Nessuna connessione vera a Lavalink qui: wavelink.Playable.search e
wavelink.Pool.get_node sono mockati.
"""

from unittest.mock import AsyncMock, patch

import pytest
import wavelink

from cogs.music.player import LOCAL_NODE_IDENTIFIER, MusicCog


@pytest.fixture
def cog():
    return MusicCog(bot=None)


@pytest.mark.asyncio
async def test_query_non_spotify_non_tenta_alcun_fallback(cog):
    with patch("wavelink.Playable.search", new=AsyncMock(return_value=[])) as ricerca:
        risultato = await cog._search_with_spotify_fallback("una canzone qualsiasi")

    assert risultato == []
    ricerca.assert_called_once_with("una canzone qualsiasi")


@pytest.mark.asyncio
async def test_query_spotify_con_risultato_sui_nodi_pubblici_non_tenta_il_fallback(cog):
    risultato_atteso = ["traccia_finta"]
    with patch("wavelink.Playable.search", new=AsyncMock(return_value=risultato_atteso)) as ricerca:
        risultato = await cog._search_with_spotify_fallback("spotify:track:abc123")

    assert risultato == risultato_atteso
    ricerca.assert_called_once_with("spotify:track:abc123")


@pytest.mark.asyncio
async def test_query_spotify_senza_risultati_ritenta_sul_nodo_locale(cog):
    nodo_locale_finto = object()

    async def _search_finta(query, node=None):
        if node is None:
            return []  # nodi pubblici: niente
        assert node is nodo_locale_finto
        return ["traccia_dal_nodo_locale"]

    with patch("wavelink.Playable.search", new=AsyncMock(side_effect=_search_finta)):
        with patch("wavelink.Pool.get_node", return_value=nodo_locale_finto) as get_node:
            risultato = await cog._search_with_spotify_fallback("spotify:track:abc123")

    get_node.assert_called_once_with(LOCAL_NODE_IDENTIFIER)
    assert risultato == ["traccia_dal_nodo_locale"]


@pytest.mark.asyncio
async def test_query_spotify_senza_nodo_locale_configurato_restituisce_vuoto(cog):
    with patch("wavelink.Playable.search", new=AsyncMock(return_value=[])):
        with patch(
            "wavelink.Pool.get_node",
            side_effect=wavelink.exceptions.InvalidNodeException("nessun nodo"),
        ):
            risultato = await cog._search_with_spotify_fallback("spotify:track:abc123")

    assert risultato == []
