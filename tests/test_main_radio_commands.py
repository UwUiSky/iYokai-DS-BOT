"""
tests/test_main_radio_commands.py
=====================================
Test del comportamento REALE dei comandi /nonstop-main (playlist e
avvio della radio condivisa) — contro PostgreSQL vero per lo stato
persistente, con wavelink.Playable.search() e i player finti (non è
possibile una connessione Lavalink/voce vera in questo ambiente,
stesso limite dichiarato in cogs/music/player.py).
"""

from datetime import datetime, timedelta, timezone

import discord
import pytest

from cogs.music.player import MusicCog
from core.database import Database
from core.repositories.main_radio_repo import MainRadioRepository


class _FakeResponse:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []
        self.sent_embeds: list = []

    async def send_message(self, content: str = None, embed=None, ephemeral: bool = False) -> None:
        if content is not None:
            self.sent_messages.append(content)
        if embed is not None:
            self.sent_embeds.append(embed)

    async def defer(self, ephemeral: bool = False) -> None:
        pass


class _FakeFollowup:
    def __init__(self, sent_messages: list[str]) -> None:
        self._sent_messages = sent_messages

    async def send(self, content: str) -> None:
        self._sent_messages.append(content)


class _FakeGuild:
    def __init__(self, guild_id: int, voice_client=None) -> None:
        self.id = guild_id
        self.voice_client = voice_client


class _FakeRealMember(discord.Member):
    def __init__(self, voice, user_id: int = 1) -> None:
        self._voice_finta = voice
        self._id_finto = user_id

    @property
    def voice(self):
        return self._voice_finta

    @property
    def id(self):
        return self._id_finto


class _FakeInteraction:
    def __init__(self, guild_id: int | None, user=None, voice_client=None) -> None:
        self.guild = _FakeGuild(guild_id, voice_client) if guild_id is not None else None
        self.user = user or _FakeRealMember(voice=None)
        self.response = _FakeResponse()
        self.followup = _FakeFollowup(self.response.sent_messages)


class _FakeTrack:
    def __init__(self, title: str, length: int) -> None:
        self.title = title
        self.length = length


class _FakeQueue:
    def __init__(self) -> None:
        self.mode = None
        self.tracce_accodate: list = []

    async def put_wait(self, track) -> None:
        self.tracce_accodate.append(track)


class _FakePlayer:
    def __init__(self) -> None:
        self.autoplay = None
        self.queue = _FakeQueue()
        self.chiamate_play: list[tuple] = []

    async def play(self, track, start: int = 0) -> None:
        self.chiamate_play.append((track, start))


class _FakeVoiceChannel:
    def __init__(self, player: _FakePlayer) -> None:
        self._player = player

    async def connect(self, cls) -> _FakePlayer:
        return self._player


@pytest.fixture
async def database_e_repo():
    database = Database()
    await database.connect()
    await database.run_migrations()
    repo = MainRadioRepository(pool_provider=lambda: database.pool)
    yield database, repo
    await database.pool.execute("DELETE FROM main_radio_tracks")
    await database.pool.execute("DELETE FROM main_radio_state")
    await database.close()


@pytest.mark.asyncio
async def test_add_track_risolve_e_salva(database_e_repo, monkeypatch):
    database, repo = database_e_repo
    import cogs.music.player as music_module
    monkeypatch.setattr(music_module, "main_radio_repo", repo)

    cog = MusicCog(bot=None)

    async def _risolvi(identifier):
        return _FakeTrack(title="Titolo Risolto", length=200_000)

    cog._resolve_radio_track = _risolvi

    interaction = _FakeInteraction(guild_id=100)
    await cog.nonstop_main_add_track.callback(cog, interaction, query="una canzone", label=None)

    assert "Aggiunta" in interaction.response.sent_messages[0]
    tracce = await repo.list_tracks()
    assert len(tracce) == 1
    assert tracce[0].label == "Titolo Risolto"
    assert tracce[0].duration_ms == 200_000


@pytest.mark.asyncio
async def test_add_track_nessun_risultato_non_salva(database_e_repo, monkeypatch):
    database, repo = database_e_repo
    import cogs.music.player as music_module
    monkeypatch.setattr(music_module, "main_radio_repo", repo)

    cog = MusicCog(bot=None)

    async def _nessun_risultato(identifier):
        return None

    cog._resolve_radio_track = _nessun_risultato

    interaction = _FakeInteraction(guild_id=100)
    await cog.nonstop_main_add_track.callback(cog, interaction, query="query senza risultati", label=None)

    assert "Nessun risultato" in interaction.response.sent_messages[0]
    assert await repo.list_tracks() == []


@pytest.mark.asyncio
async def test_list_tracks_vuota(database_e_repo, monkeypatch):
    database, repo = database_e_repo
    import cogs.music.player as music_module
    monkeypatch.setattr(music_module, "main_radio_repo", repo)

    cog = MusicCog(bot=None)
    interaction = _FakeInteraction(guild_id=100)

    await cog.nonstop_main_list_tracks.callback(cog, interaction)

    assert "vuota" in interaction.response.sent_messages[0].lower()


@pytest.mark.asyncio
async def test_list_tracks_con_tracce(database_e_repo, monkeypatch):
    database, repo = database_e_repo
    import cogs.music.player as music_module
    monkeypatch.setattr(music_module, "main_radio_repo", repo)

    await repo.add_track("q1", 180_000, "Canzone Uno", 1)

    cog = MusicCog(bot=None)
    interaction = _FakeInteraction(guild_id=100)

    await cog.nonstop_main_list_tracks.callback(cog, interaction)

    assert "Canzone Uno" in interaction.response.sent_embeds[0].description


@pytest.mark.asyncio
async def test_remove_track_esistente(database_e_repo, monkeypatch):
    database, repo = database_e_repo
    import cogs.music.player as music_module
    monkeypatch.setattr(music_module, "main_radio_repo", repo)

    track_id = await repo.add_track("q1", 180_000, "X", 1)

    cog = MusicCog(bot=None)
    interaction = _FakeInteraction(guild_id=100)
    await cog.nonstop_main_remove_track.callback(cog, interaction, track_id=track_id)

    assert "rimossa" in interaction.response.sent_messages[0].lower()
    assert await repo.list_tracks() == []


@pytest.mark.asyncio
async def test_add_local_senza_cartella_configurata_avvisa(database_e_repo, monkeypatch):
    database, repo = database_e_repo
    import cogs.music.player as music_module

    class _ConfigVuota:
        MAIN_RADIO_LOCAL_FOLDER = ""

    monkeypatch.setattr(music_module, "config", _ConfigVuota())
    monkeypatch.setattr(music_module, "main_radio_repo", repo)

    cog = MusicCog(bot=None)
    interaction = _FakeInteraction(guild_id=100)

    await cog.nonstop_main_add_local.callback(cog, interaction, filename="inedito.mp3", label=None)

    assert "non è configurata" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_start_primo_avvio_in_assoluto_imposta_lo_stato_da_zero(database_e_repo, monkeypatch):
    database, repo = database_e_repo
    import cogs.music.player as music_module

    monkeypatch.setattr(music_module, "main_radio_repo", repo)

    await repo.add_track("traccia-a", 180_000, "Traccia A", 1)
    await repo.add_track("traccia-b", 200_000, "Traccia B", 1)

    cog = MusicCog(bot=None)

    async def _risolvi(identifier):
        return _FakeTrack(title=identifier, length=180_000)

    cog._resolve_radio_track = _risolvi

    player_finto = _FakePlayer()
    canale_finto = _FakeVoiceChannel(player_finto)
    membro = _FakeRealMember(voice=type("V", (), {"channel": canale_finto})())
    interaction = _FakeInteraction(guild_id=100, user=membro, voice_client=None)

    await cog.nonstop_main_start.callback(cog, interaction)

    stato = await repo.get_state()
    assert stato is not None
    assert stato.track_index == 0
    assert stato.is_active is True

    # Alla PRIMA traccia (indice 0), start=0 perché non è ancora
    # passato alcun tempo reale dal riferimento appena creato.
    assert player_finto.chiamate_play[0][1] == 0
    assert "Radio avviata" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_start_con_stato_esistente_calcola_la_posizione_reale(database_e_repo, monkeypatch):
    database, repo = database_e_repo
    import cogs.music.player as music_module

    monkeypatch.setattr(music_module, "main_radio_repo", repo)

    await repo.add_track("traccia-a", 180_000, "Traccia A", 1)  # 3 minuti
    await repo.add_track("traccia-b", 200_000, "Traccia B", 1)

    # La radio è "iniziata" 90 secondi fa sulla traccia 0 (durata 3
    # minuti) - un nuovo server che entra ora deve unirsi a metà
    # della stessa traccia, non ripartire da zero.
    riferimento = datetime.now(timezone.utc) - timedelta(seconds=90)
    await repo.set_state(track_index=0, track_started_at=riferimento, is_active=True)

    cog = MusicCog(bot=None)

    async def _risolvi(identifier):
        return _FakeTrack(title=identifier, length=180_000)

    cog._resolve_radio_track = _risolvi

    player_finto = _FakePlayer()
    canale_finto = _FakeVoiceChannel(player_finto)
    membro = _FakeRealMember(voice=type("V", (), {"channel": canale_finto})())
    interaction = _FakeInteraction(guild_id=200, user=membro, voice_client=None)

    await cog.nonstop_main_start.callback(cog, interaction)

    _traccia, start_ms = player_finto.chiamate_play[0]
    # ~90 secondi = 90_000 ms, con un po' di tolleranza per il tempo
    # di esecuzione del test stesso.
    assert 85_000 < start_ms < 95_000
