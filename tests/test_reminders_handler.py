"""
tests/test_reminders_handler.py
===================================
Test di RemindersCog.handle_reminder_fire() — il comportamento reale
di consegna (DM, poi fallback nel canale), non solo la registrazione
già verificata in test_reminders_cog_smoke.py.
"""

import discord
import pytest

from cogs.utility.reminders import RemindersCog


class _FakeHTTPResponse:
    status = 500
    reason = "Internal Server Error"


class _FakeUser:
    def __init__(self, user_id: int, dm_fallisce: bool = False) -> None:
        self.id = user_id
        self._dm_fallisce = dm_fallisce
        self.dm_ricevuti: list[str] = []

    async def send(self, content: str) -> None:
        if self._dm_fallisce:
            raise discord.HTTPException(response=_FakeHTTPResponse(), message="DM chiusi")
        self.dm_ricevuti.append(content)


class _FakeChannel(discord.TextChannel):
    def __init__(self, channel_id: int, invio_fallisce: bool = False) -> None:
        self.id = channel_id
        self._invio_fallisce = invio_fallisce
        self.messaggi_inviati: list[str] = []

    async def send(self, content: str) -> None:
        if self._invio_fallisce:
            raise discord.HTTPException(response=_FakeHTTPResponse(), message="canale non raggiungibile")
        self.messaggi_inviati.append(content)


class _FakeGuild:
    def __init__(self, guild_id: int, channel: _FakeChannel | None) -> None:
        self.id = guild_id
        self._channel = channel

    def get_channel(self, channel_id: int):
        return self._channel


class _FakeBot:
    def __init__(self, user: _FakeUser | None, guild: _FakeGuild | None) -> None:
        self._user = user
        self._guild = guild

    def get_user(self, user_id: int):
        return self._user

    async def fetch_user(self, user_id: int):
        if self._user is None:
            raise discord.HTTPException(response=_FakeHTTPResponse(), message="utente non trovato")
        return self._user

    def get_guild(self, guild_id: int):
        return self._guild


@pytest.mark.asyncio
async def test_dm_riuscito_non_prova_il_fallback():
    utente = _FakeUser(user_id=1)
    canale = _FakeChannel(channel_id=500)
    guild = _FakeGuild(guild_id=100, channel=canale)
    bot = _FakeBot(user=utente, guild=guild)
    cog = RemindersCog(bot)

    await cog.handle_reminder_fire(
        guild_id=100, user_id=1, payload={"message": "Comprare il latte", "channel_id": 500}
    )

    assert len(utente.dm_ricevuti) == 1
    assert "Comprare il latte" in utente.dm_ricevuti[0]
    assert canale.messaggi_inviati == []  # il fallback non deve scattare se il DM riesce


@pytest.mark.asyncio
async def test_dm_fallito_usa_il_canale_di_fallback():
    utente = _FakeUser(user_id=1, dm_fallisce=True)
    canale = _FakeChannel(channel_id=500)
    guild = _FakeGuild(guild_id=100, channel=canale)
    bot = _FakeBot(user=utente, guild=guild)
    cog = RemindersCog(bot)

    await cog.handle_reminder_fire(
        guild_id=100, user_id=1, payload={"message": "Comprare il latte", "channel_id": 500}
    )

    assert len(canale.messaggi_inviati) == 1
    assert "Comprare il latte" in canale.messaggi_inviati[0]
    assert "<@1>" in canale.messaggi_inviati[0]  # l'utente va menzionato nel fallback


@pytest.mark.asyncio
async def test_dm_e_fallback_entrambi_falliti_non_solleva_eccezioni():
    utente = _FakeUser(user_id=1, dm_fallisce=True)
    canale = _FakeChannel(channel_id=500, invio_fallisce=True)
    guild = _FakeGuild(guild_id=100, channel=canale)
    bot = _FakeBot(user=utente, guild=guild)
    cog = RemindersCog(bot)

    # Non deve sollevare, solo loggare — un reminder non consegnabile
    # non deve far crashare lo scheduler che lo ha chiamato.
    await cog.handle_reminder_fire(
        guild_id=100, user_id=1, payload={"message": "Test", "channel_id": 500}
    )


@pytest.mark.asyncio
async def test_nessun_channel_id_nel_payload_e_dm_fallito_non_solleva():
    utente = _FakeUser(user_id=1, dm_fallisce=True)
    bot = _FakeBot(user=utente, guild=None)
    cog = RemindersCog(bot)

    await cog.handle_reminder_fire(guild_id=100, user_id=1, payload={"message": "Test"})


@pytest.mark.asyncio
async def test_utente_non_trovato_prova_comunque_il_fallback():
    canale = _FakeChannel(channel_id=500)
    guild = _FakeGuild(guild_id=100, channel=canale)
    bot = _FakeBot(user=None, guild=guild)
    cog = RemindersCog(bot)

    await cog.handle_reminder_fire(
        guild_id=100, user_id=1, payload={"message": "Test", "channel_id": 500}
    )

    assert len(canale.messaggi_inviati) == 1
