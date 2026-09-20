"""
tests/test_scheduled_messages_handler.py
=============================================
Test di ScheduledMessagesCog.handle_scheduled_message_fire() — il
comportamento reale di pubblicazione, non solo la registrazione già
verificata in test_scheduled_messages_cog_smoke.py.
"""

import discord
import pytest

from cogs.utility.scheduled_messages import ScheduledMessagesCog


class _FakeHTTPResponse:
    status = 500
    reason = "Internal Server Error"


class _FakeChannel(discord.TextChannel):
    def __init__(self, channel_id: int, invio_fallisce: bool = False) -> None:
        self.id = channel_id
        self._invio_fallisce = invio_fallisce
        self.messaggi_inviati: list[str] = []

    async def send(self, content: str) -> None:
        if self._invio_fallisce:
            raise discord.HTTPException(response=_FakeHTTPResponse(), message="errore")
        self.messaggi_inviati.append(content)


class _FakeGuild:
    def __init__(self, guild_id: int, channel: _FakeChannel | None) -> None:
        self.id = guild_id
        self._channel = channel

    def get_channel(self, channel_id: int):
        return self._channel


class _FakeBot:
    def __init__(self, guild: _FakeGuild | None) -> None:
        self._guild = guild

    def get_guild(self, guild_id: int):
        return self._guild


@pytest.mark.asyncio
async def test_pubblica_il_messaggio_nel_canale_corretto():
    canale = _FakeChannel(channel_id=500)
    guild = _FakeGuild(guild_id=100, channel=canale)
    bot = _FakeBot(guild=guild)
    cog = ScheduledMessagesCog(bot)

    await cog.handle_scheduled_message_fire(
        guild_id=100, user_id=1, payload={"channel_id": 500, "message": "Evento stasera!"}
    )

    assert canale.messaggi_inviati == ["Evento stasera!"]


@pytest.mark.asyncio
async def test_canale_non_raggiungibile_non_solleva():
    guild = _FakeGuild(guild_id=100, channel=None)
    bot = _FakeBot(guild=guild)
    cog = ScheduledMessagesCog(bot)

    # Non deve sollevare — un canale sparito non deve far crashare
    # lo scheduler che ha chiamato l'handler.
    await cog.handle_scheduled_message_fire(
        guild_id=100, user_id=1, payload={"channel_id": 999, "message": "Test"}
    )


@pytest.mark.asyncio
async def test_server_non_raggiungibile_non_solleva():
    bot = _FakeBot(guild=None)
    cog = ScheduledMessagesCog(bot)

    await cog.handle_scheduled_message_fire(
        guild_id=999, user_id=1, payload={"channel_id": 500, "message": "Test"}
    )


@pytest.mark.asyncio
async def test_invio_fallito_non_solleva():
    canale = _FakeChannel(channel_id=500, invio_fallisce=True)
    guild = _FakeGuild(guild_id=100, channel=canale)
    bot = _FakeBot(guild=guild)
    cog = ScheduledMessagesCog(bot)

    await cog.handle_scheduled_message_fire(
        guild_id=100, user_id=1, payload={"channel_id": 500, "message": "Test"}
    )
