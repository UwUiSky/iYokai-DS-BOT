"""
tests/test_music_guard_clauses.py
=====================================
Test di MusicCog._controlli_base() — la parte verificabile senza una
connessione Lavalink/voce vera (vedi il limite dichiarato in cima a
cogs/music/player.py). Contro PostgreSQL reale per il controllo del
modulo attivo.
"""

import discord
import pytest

from cogs.music.player import MODULE_MUSIC, MusicCog
from core.database import Database


class _FakeResponse:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []

    async def send_message(self, content: str, ephemeral: bool = False) -> None:
        self.sent_messages.append(content)


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


class _FakeMember:
    def __init__(self, voice) -> None:
        self.voice = voice


class _FakeRealMember(discord.Member):
    """Eredita davvero da discord.Member (senza chiamarne il
    costruttore) — serve perché _controlli_base fa isinstance(...,
    discord.Member), che un semplice oggetto finto senza questa
    eredità non supererebbe mai. discord.Member.voice è una PROPERTY
    di sola lettura che legge da self.guild._voice_state_for(...) -
    troppo legata agli interni veri per un fake semplice, quindi la
    sovrascriviamo qui con una property nostra invece di provare ad
    assegnare self.voice direttamente (che fallirebbe: "property has
    no setter" — trovato scrivendo questo stesso test)."""

    def __init__(self, voice) -> None:
        self._voice_finta = voice

    @property
    def voice(self):
        return self._voice_finta


class _FakeInteraction:
    def __init__(self, guild_id: int | None, user) -> None:
        self.guild = _FakeGuild(guild_id) if guild_id is not None else None
        self.user = user
        self.response = _FakeResponse()


@pytest.mark.asyncio
async def test_fuori_da_un_server_rifiuta():
    cog = MusicCog(bot=None)
    interaction = _FakeInteraction(guild_id=None, user=_FakeMember(voice=None))

    risultato = await cog._controlli_base(interaction)

    assert risultato is False
    assert "solo dentro un server" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_modulo_disattivato_rifiuta(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000010
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)

        import cogs.music.player as music_module
        monkeypatch.setattr(music_module, "db", database)

        cog = MusicCog(bot=None)
        interaction = _FakeInteraction(guild_id, user=_FakeMember(voice=None))

        risultato = await cog._controlli_base(interaction)

        assert risultato is False
        assert "non è attivo" in interaction.response.sent_messages[0]
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 700000010")
        await database.close()


@pytest.mark.asyncio
async def test_utente_non_in_vocale_rifiuta(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000011
        await database.set_module_active_for_guild(guild_id, MODULE_MUSIC, True)

        import cogs.music.player as music_module
        monkeypatch.setattr(music_module, "db", database)

        cog = MusicCog(bot=None)
        interaction = _FakeInteraction(guild_id, user=_FakeRealMember(voice=None))

        risultato = await cog._controlli_base(interaction)

        assert risultato is False
        assert "canale vocale" in interaction.response.sent_messages[0]
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 700000011")
        await database.close()


@pytest.mark.asyncio
async def test_tutti_i_controlli_passano(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000012
        await database.set_module_active_for_guild(guild_id, MODULE_MUSIC, True)

        import cogs.music.player as music_module
        monkeypatch.setattr(music_module, "db", database)

        interaction = _FakeInteraction(guild_id, user=_FakeRealMember(voice=object()))

        cog = MusicCog(bot=None)
        risultato = await cog._controlli_base(interaction)

        assert risultato is True
        assert interaction.response.sent_messages == []
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 700000012")
        await database.close()
