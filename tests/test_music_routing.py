"""
tests/test_music_routing.py
===============================
Test del comportamento di instradamento introdotto dalla riscrittura
multi-istanza: nessuna sessione attiva, worker non invitato nel
server, rilascio del worker alla disconnessione. Usa oggetti finti
per bot/flotta/worker (i test con PostgreSQL VERO sulla flotta stessa
sono in tests/test_music_fleet.py — qui si verifica che il COG usi
la flotta correttamente, non che la flotta funzioni).
"""

import discord
import pytest

from cogs.music.player import MODULE_MUSIC, MusicCog
from core.database import Database


class _FakeFollowup:
    def __init__(self, sent_messages: list[str]) -> None:
        self._sent_messages = sent_messages

    async def send(self, content: str) -> None:
        self._sent_messages.append(content)


class _FakeResponse:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []

    async def send_message(self, content: str, ephemeral: bool = False) -> None:
        self.sent_messages.append(content)

    async def defer(self) -> None:
        pass


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


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
        self.followup = _FakeFollowup(self.response.sent_messages)


class _FakePlayer:
    def __init__(self) -> None:
        self.disconnect_chiamato = False

    async def disconnect(self) -> None:
        self.disconnect_chiamato = True


class _FakeWorkerGuild:
    def __init__(self, voice_client=None) -> None:
        self.voice_client = voice_client


class _FakeWorkerBot:
    def __init__(self, worker_guild) -> None:
        self._worker_guild = worker_guild

    def get_guild(self, guild_id: int):
        return self._worker_guild


class _FakeFleetSenzaSessione:
    """Nessuna sessione esiste mai — simula un server che non ha
    ancora fatto /play."""

    async def get_worker_for_guild(self, guild_id: int):
        return None

    async def get_or_assign_worker_for_guild(self, guild_id: int):
        return None


class _FakeFleetTuttiOccupati:
    async def get_or_assign_worker_for_guild(self, guild_id: int):
        return None


class _FakeFleetWorkerNonInvitato:
    """Una sessione esiste (worker 1 assegnato), ma quel bot worker
    non risulta nel server (get_guild restituisce None) — es. non è
    mai stato invitato, o è stato espulso."""

    async def get_worker_for_guild(self, guild_id: int):
        worker_bot = _FakeWorkerBot(worker_guild=None)
        return 1, worker_bot

    async def get_or_assign_worker_for_guild(self, guild_id: int):
        return await self.get_worker_for_guild(guild_id)


class _FakeFleetConSessione:
    def __init__(self, player) -> None:
        self._player = player
        self.release_guild_chiamato_per: list[int] = []

    async def get_worker_for_guild(self, guild_id: int):
        worker_guild = _FakeWorkerGuild(voice_client=self._player)
        worker_bot = _FakeWorkerBot(worker_guild)
        return 1, worker_bot

    async def get_or_assign_worker_for_guild(self, guild_id: int):
        return await self.get_worker_for_guild(guild_id)

    async def release_guild(self, guild_id: int) -> None:
        self.release_guild_chiamato_per.append(guild_id)


class _FakeBot:
    def __init__(self, music_fleet) -> None:
        self.music_fleet = music_fleet


async def _prepara_modulo_attivo(guild_id: int, monkeypatch):
    database = Database()
    await database.connect()
    await database.run_migrations()
    await database.set_module_active_for_guild(guild_id, MODULE_MUSIC, True)

    import cogs.music.player as music_module
    monkeypatch.setattr(music_module, "db", database)
    return database


@pytest.mark.asyncio
async def test_skip_senza_sessione_fallisce_pulito(monkeypatch):
    guild_id = 700000020
    database = await _prepara_modulo_attivo(guild_id, monkeypatch)
    try:
        bot = _FakeBot(_FakeFleetSenzaSessione())
        cog = MusicCog(bot=bot)
        interaction = _FakeInteraction(guild_id, user=_FakeRealMember(voice=object()))

        await cog.skip.callback(cog, interaction)

        assert "nessuna sessione musicale attiva" in interaction.response.sent_messages[0].lower()
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)
        await database.close()


@pytest.mark.asyncio
async def test_play_con_tutti_i_worker_occupati_avvisa_l_utente(monkeypatch):
    guild_id = 700000021
    database = await _prepara_modulo_attivo(guild_id, monkeypatch)
    try:
        bot = _FakeBot(_FakeFleetTuttiOccupati())
        cog = MusicCog(bot=bot)
        interaction = _FakeInteraction(guild_id, user=_FakeRealMember(voice=object()))

        await cog.play.callback(cog, interaction, query="una canzone qualsiasi")

        assert "occupati" in interaction.response.sent_messages[0].lower()
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)
        await database.close()


@pytest.mark.asyncio
async def test_worker_non_invitato_nel_server_avvisa_correttamente(monkeypatch):
    guild_id = 700000022
    database = await _prepara_modulo_attivo(guild_id, monkeypatch)
    try:
        bot = _FakeBot(_FakeFleetWorkerNonInvitato())
        cog = MusicCog(bot=bot)
        interaction = _FakeInteraction(guild_id, user=_FakeRealMember(voice=object()))

        await cog.skip.callback(cog, interaction)

        assert "non risulta invitato" in interaction.response.sent_messages[0]
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)
        await database.close()


@pytest.mark.asyncio
async def test_disconnect_rilascia_il_worker_nella_flotta(monkeypatch):
    guild_id = 700000023
    database = await _prepara_modulo_attivo(guild_id, monkeypatch)
    try:
        player_finto = _FakePlayer()
        fleet = _FakeFleetConSessione(player_finto)
        bot = _FakeBot(fleet)
        cog = MusicCog(bot=bot)
        interaction = _FakeInteraction(guild_id, user=_FakeRealMember(voice=object()))

        await cog.disconnect.callback(cog, interaction)

        assert player_finto.disconnect_chiamato is True
        assert fleet.release_guild_chiamato_per == [guild_id]
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)
        await database.close()


@pytest.mark.asyncio
async def test_stop_con_sessione_esistente_ferma_e_svuota(monkeypatch):
    guild_id = 700000024
    database = await _prepara_modulo_attivo(guild_id, monkeypatch)
    try:
        class _FakeQueue:
            def __init__(self) -> None:
                self.cleared = False

            def clear(self) -> None:
                self.cleared = True

        class _FakePlayerConCoda(_FakePlayer):
            def __init__(self) -> None:
                super().__init__()
                self.queue = _FakeQueue()
                self.stop_chiamato = False

            async def stop(self) -> None:
                self.stop_chiamato = True

        player_finto = _FakePlayerConCoda()
        fleet = _FakeFleetConSessione(player_finto)
        bot = _FakeBot(fleet)
        cog = MusicCog(bot=bot)
        interaction = _FakeInteraction(guild_id, user=_FakeRealMember(voice=object()))

        await cog.stop.callback(cog, interaction)

        assert player_finto.stop_chiamato is True
        assert player_finto.queue.cleared is True
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)
        await database.close()
