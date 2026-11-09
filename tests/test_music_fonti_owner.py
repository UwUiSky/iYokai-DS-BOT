"""
tests/test_music_fonti_owner.py
================================
/owner radio fonti (issue #126, B1): stato di ogni fonte per l'owner, risposta
nascosta, mai il valore delle chiavi; e gli avvisi all'utente quando una fonte manca.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from cogs.music.player import MusicCog
from core import music_sources as ms


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    for v in ("MUSIC_SOURCES_ENABLED", "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "APPLE_MUSIC_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    ms.registro.reset()


def _interazione():
    i = MagicMock()
    i.response.send_message = AsyncMock()
    i.response.defer = AsyncMock()
    i.followup.send = AsyncMock()
    i.guild_id = 1
    i.user.id = 123
    i.locale = None
    return i


@pytest.mark.asyncio
async def test_fonti_mostra_una_riga_per_fonte_in_modo_nascosto(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "idSegretissimo99")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "chiaveSegretissima99")
    cog = MusicCog(bot=None)
    i = _interazione()
    await cog.nonstop_main_fonti.callback(cog, i)
    kwargs = i.response.send_message.call_args.kwargs
    assert kwargs["ephemeral"] is True
    descrizione = kwargs["embed"].description
    assert "Spotify" in descrizione and "Apple Music" in descrizione and "YouTube" in descrizione
    assert "Segretissim" not in descrizione
    assert len(descrizione) <= 4096 and len(kwargs["embed"].title) <= 256
