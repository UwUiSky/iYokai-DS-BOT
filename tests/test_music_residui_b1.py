"""
tests/test_music_residui_b1.py
==============================
Residui del blocco B1 (issue #126): righe di stato delle fonti nella lingua di chi legge,
stato onesto per Spotify e Apple Music (chiavi su Lavalink), messaggi di `_play_nel_canale`
presi da locales. Nessuna rete.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cogs.music.player import MusicCog
from core import music_sources as ms
from core.i18n import t


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    for v in ("MUSIC_SOURCES_ENABLED", "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "APPLE_MUSIC_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    ms.registro.reset()


def test_spotify_senza_chiavi_nel_bot_dice_chiavi_su_lavalink_non_senza_chiavi():
    testo = "\n".join(ms.righe_stato("it"))
    riga = next(r for r in testo.split("\n") if "Spotify" in r)
    assert "Lavalink" in riga and "senza chiavi" not in riga
    riga_apple = next(r for r in testo.split("\n") if "Apple Music" in r)
    assert "Lavalink" in riga_apple


def test_tidal_senza_chiavi_resta_senza_chiavi():
    riga = next(r for r in ms.righe_stato("it") if "Tidal" in r)
    assert "spenta" in riga  # Tidal non è tra le fonti di base


def test_righe_in_inglese_non_hanno_parole_italiane(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "idSegretissimo99")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "chiaveSegretissima99")
    testo = "\n".join(ms.righe_stato("en-US"))
    assert "keys yes" in testo and "off" in testo
    for parola in ("chiavi", "spenta", "non servono", "sì"):
        assert parola not in testo
    assert "Segretissim" not in testo


def test_righe_predefinite_restano_in_italiano():
    assert "chiavi sì" in "\n".join(ms.righe_stato()) or "chiavi non servono" in "\n".join(ms.righe_stato())


@pytest.mark.asyncio
async def test_nessun_nodo_usa_il_testo_di_locales():
    cog = MusicCog(bot=MagicMock())
    cog.bot.music_nodes = MagicMock()
    cog.bot.music_nodes.node_for.return_value = None
    cog.bot.music_fleet.release_session = AsyncMock()
    worker_bot, worker_guild = MagicMock(), MagicMock()
    worker_guild.voice_client = None
    rispondi = AsyncMock()
    with patch("cogs.music.player.lingua_risposta", new=AsyncMock(return_value="en-US")):
        esito = await cog._play_nel_canale(1, 2, "x", False, MagicMock(), worker_bot, worker_guild, 3, rispondi)
    assert esito is False
    assert rispondi.call_args.args[0] == t("music_nessun_nodo", "en-US")
    assert "node" in rispondi.call_args.args[0].lower()


@pytest.mark.asyncio
async def test_nessun_risultato_usa_il_testo_di_locales():
    cog = MusicCog(bot=MagicMock())
    cog.bot.music_nodes = MagicMock()
    cog.bot.music_nodes.node_for.return_value = object()
    cog.bot.music_nodes.locale_di.return_value = None
    cog.bot.music_fleet.release_session = AsyncMock()
    worker_guild = MagicMock()
    worker_guild.voice_client = None
    rispondi = AsyncMock()
    cerca = AsyncMock(return_value=([], object()))
    with patch("cogs.music.player.lingua_risposta", new=AsyncMock(return_value="en-US")):
        await cog._play_nel_canale(1, 2, "x", False, MagicMock(), MagicMock(), worker_guild, 3, rispondi, cerca)
    assert rispondi.call_args.args[0] == t("music_nessun_risultato", "en-US")
    assert t("music_nessun_risultato", "it").startswith("Nessun risultato")
