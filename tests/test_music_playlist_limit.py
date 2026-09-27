"""
tests/test_music_playlist_limit.py
======================================
Test del limite di tracce aggiunte da UNA playlist a /play (SPEC.md
§9.4) — richiesto esplicitamente dall'utente: un link a una playlist
enorme (es. Spotify, che ne permette fino a 10.000 brani) non deve
poter riempire la coda di un server all'infinito in un colpo solo.
Limite: 750 tracce per singolo link (core.music_logic.
MAX_PLAYLIST_TRACKS). Nessuna connessione vera a Lavalink: il player
e la ricerca sono mockati, come in tests/test_music_routing.py.
"""

from unittest.mock import AsyncMock, patch

import discord
import pytest
import wavelink

from cogs.music.player import MODULE_MUSIC, MusicCog
from core.database import Database


class _FakeTrack:
    def __init__(self, i: int) -> None:
        self.title = f"Traccia {i}"
        self.length = 200_000


class _FakePlaylist:
    """Sostituisce interamente wavelink.Playlist per la durata di
    ogni test (monkeypatch.setattr(wavelink, "Playlist", ...)) — non
    ha senso costruire un wavelink.Playlist VERO qui: richiederebbe
    un payload Lavalink completo per ogni traccia, quando l'unica
    cosa che /play usa davvero è name/len/slicing/iterazione."""

    def __init__(self, n: int, name: str = "Playlist finta") -> None:
        self.name = name
        self._tracks = [_FakeTrack(i) for i in range(n)]

    def __len__(self) -> int:
        return len(self._tracks)

    def __getitem__(self, item):
        return self._tracks[item]

    def __iter__(self):
        return iter(self._tracks)


class _FakeQueue:
    def __init__(self) -> None:
        self.put_wait_chiamato_con = None
        self.is_empty = True

    async def put_wait(self, item) -> None:
        self.put_wait_chiamato_con = item


class _FakePlayer:
    def __init__(self) -> None:
        self.queue = _FakeQueue()
        self.playing = True  # evita che /play tenti di avviare subito la prossima traccia


class _FakeResponse:
    async def defer(self) -> None:
        pass


class _FakeFollowup:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []

    async def send(self, content: str) -> None:
        self.sent_messages.append(content)


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


class _FakeVoiceChannel:
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id


class _FakeVoiceState:
    def __init__(self, channel_id: int) -> None:
        self.channel = _FakeVoiceChannel(channel_id)


class _FakeRealMember(discord.Member):
    def __init__(self, voice) -> None:
        self._voice_finta = voice

    @property
    def voice(self):
        return self._voice_finta


class _FakeInteraction:
    def __init__(self, guild_id: int, user) -> None:
        self.guild = _FakeGuild(guild_id)
        self.user = user
        self.response = _FakeResponse()
        self.followup = _FakeFollowup()


class _FakeWorkerGuild:
    def __init__(self, voice_client) -> None:
        self.voice_client = voice_client

    def get_channel(self, channel_id: int):
        return _FakeVoiceChannel(channel_id)


class _FakeWorkerBot:
    def __init__(self, worker_guild) -> None:
        self._worker_guild = worker_guild

    def get_guild(self, guild_id: int):
        return self._worker_guild


class _FakeFleet:
    def __init__(self, player) -> None:
        self._player = player

    async def get_or_assign_worker_for_guild(self, guild_id: int):
        worker_guild = _FakeWorkerGuild(voice_client=self._player)
        worker_bot = _FakeWorkerBot(worker_guild)
        return 1, worker_bot


class _FakeBot:
    def __init__(self, fleet) -> None:
        self.music_fleet = fleet


async def _prepara_modulo_attivo(guild_id: int, monkeypatch):
    database = Database()
    await database.connect()
    await database.run_migrations()
    await database.set_module_active_for_guild(guild_id, MODULE_MUSIC, True)

    import cogs.music.player as music_module
    monkeypatch.setattr(music_module, "db", database)
    return database


@pytest.mark.asyncio
async def test_play_con_playlist_sopra_il_limite_la_taglia_a_750(monkeypatch):
    guild_id = 700000030
    database = await _prepara_modulo_attivo(guild_id, monkeypatch)
    try:
        monkeypatch.setattr(wavelink, "Playlist", _FakePlaylist)

        player_finto = _FakePlayer()
        bot = _FakeBot(_FakeFleet(player_finto))
        cog = MusicCog(bot=bot)
        interaction = _FakeInteraction(
            guild_id, user=_FakeRealMember(voice=_FakeVoiceState(channel_id=1))
        )

        playlist_finta = _FakePlaylist(1000, name="Playlist Gigante")
        with patch.object(
            cog, "_search_with_spotify_fallback", new=AsyncMock(return_value=playlist_finta)
        ):
            await cog.play.callback(
                cog, interaction, query="https://open.spotify.com/playlist/xyz"
            )

        assert len(player_finto.queue.put_wait_chiamato_con) == 750
        messaggio = interaction.followup.sent_messages[0]
        assert "750" in messaggio
        assert "1000" in messaggio
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)
        await database.close()


@pytest.mark.asyncio
async def test_play_con_playlist_sotto_il_limite_non_la_taglia(monkeypatch):
    guild_id = 700000031
    database = await _prepara_modulo_attivo(guild_id, monkeypatch)
    try:
        monkeypatch.setattr(wavelink, "Playlist", _FakePlaylist)

        player_finto = _FakePlayer()
        bot = _FakeBot(_FakeFleet(player_finto))
        cog = MusicCog(bot=bot)
        interaction = _FakeInteraction(
            guild_id, user=_FakeRealMember(voice=_FakeVoiceState(channel_id=1))
        )

        playlist_finta = _FakePlaylist(20, name="Playlist Piccola")
        with patch.object(
            cog, "_search_with_spotify_fallback", new=AsyncMock(return_value=playlist_finta)
        ):
            await cog.play.callback(
                cog, interaction, query="https://open.spotify.com/playlist/abc"
            )

        assert len(player_finto.queue.put_wait_chiamato_con) == 20
        messaggio = interaction.followup.sent_messages[0]
        assert "20" in messaggio
        assert "limite" not in messaggio.lower()
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)
        await database.close()


@pytest.mark.asyncio
async def test_play_con_playlist_esattamente_al_limite_non_la_taglia(monkeypatch):
    guild_id = 700000032
    database = await _prepara_modulo_attivo(guild_id, monkeypatch)
    try:
        monkeypatch.setattr(wavelink, "Playlist", _FakePlaylist)

        player_finto = _FakePlayer()
        bot = _FakeBot(_FakeFleet(player_finto))
        cog = MusicCog(bot=bot)
        interaction = _FakeInteraction(
            guild_id, user=_FakeRealMember(voice=_FakeVoiceState(channel_id=1))
        )

        playlist_finta = _FakePlaylist(750, name="Playlist Esatta")
        with patch.object(
            cog, "_search_with_spotify_fallback", new=AsyncMock(return_value=playlist_finta)
        ):
            await cog.play.callback(
                cog, interaction, query="https://open.spotify.com/playlist/exact"
            )

        assert len(player_finto.queue.put_wait_chiamato_con) == 750
        assert "limite" not in interaction.followup.sent_messages[0].lower()
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)
        await database.close()
