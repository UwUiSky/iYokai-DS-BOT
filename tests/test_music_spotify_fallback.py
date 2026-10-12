"""
tests/test_music_spotify_fallback.py
========================================
Test di MusicCog._cerca (SPEC.md §9.5, M 8.3, BUG-10) — la ricerca gira
su un nodo SCELTO, mai su "il meno carico del Pool"; un link `spotify:`
non diventa una ricerca su YouTube Music; la query Spotify senza
risultati ritenta UNA volta sul nodo locale del bot, mai per le altre.
Nessuna connessione vera a Lavalink: wavelink.Playable.search e
wavelink.Pool.fetch_tracks sono mockati.
"""

from unittest.mock import AsyncMock, patch

import pytest

from cogs.music.player import MusicCog


@pytest.fixture
def cog():
    return MusicCog(bot=None)


@pytest.mark.asyncio
async def test_ricerca_normale_gira_sul_nodo_scelto(cog):
    nodo = object()
    with patch("wavelink.Playable.search", new=AsyncMock(return_value=["t"])) as ricerca:
        risultato, usato = await cog._cerca("una canzone qualsiasi", nodo)

    assert risultato == ["t"] and usato is nodo
    ricerca.assert_called_once_with("una canzone qualsiasi", node=nodo)


@pytest.mark.asyncio
async def test_query_non_spotify_senza_risultati_non_tenta_il_nodo_locale(cog):
    nodo, locale = object(), object()
    with patch("wavelink.Playable.search", new=AsyncMock(return_value=[])) as ricerca:
        risultato, usato = await cog._cerca("niente", nodo, locale)

    assert risultato == [] and usato is nodo
    ricerca.assert_called_once()


@pytest.mark.asyncio
async def test_uri_spotify_non_diventa_ricerca_youtube_music(cog):
    nodo = object()
    with patch("wavelink.Pool.fetch_tracks", new=AsyncMock(return_value=["t"])) as grezzo, patch(
        "wavelink.Playable.search", new=AsyncMock()
    ) as ricerca:
        risultato, _ = await cog._cerca("spotify:track:abc123", nodo)

    assert risultato == ["t"]
    grezzo.assert_called_once_with("spotify:track:abc123", node=nodo)
    ricerca.assert_not_called()


@pytest.mark.asyncio
async def test_query_spotify_senza_risultati_ritenta_sul_nodo_locale(cog):
    nodo, locale = object(), object()

    async def _fetch(query, node=None):
        return [] if node is nodo else ["dal_nodo_locale"]

    with patch("wavelink.Pool.fetch_tracks", new=AsyncMock(side_effect=_fetch)):
        risultato, usato = await cog._cerca("spotify:track:abc123", nodo, locale)

    assert risultato == ["dal_nodo_locale"]
    assert usato is locale  # il player deve nascere dove c'è il plugin


@pytest.mark.asyncio
async def test_query_spotify_senza_nodo_locale_restituisce_vuoto(cog):
    nodo = object()
    with patch("wavelink.Pool.fetch_tracks", new=AsyncMock(return_value=[])):
        risultato, usato = await cog._cerca("https://open.spotify.com/track/x", nodo, None)

    assert risultato == [] and usato is nodo


@pytest.mark.asyncio
async def test_una_query_local_scritta_da_un_utente_non_va_mai_al_filesystem(cog):
    """Solo la radio legge i percorsi locali: una ricerca utente `local:` è una ricerca normale."""
    nodo = object()
    with patch("wavelink.Playable.search", new=AsyncMock(return_value=[])) as ricerca, patch(
        "wavelink.Pool.fetch_tracks", new=AsyncMock()
    ) as grezzo:
        await cog._cerca("local:/etc/passwd", nodo)

    ricerca.assert_called_once()
    grezzo.assert_not_called()
