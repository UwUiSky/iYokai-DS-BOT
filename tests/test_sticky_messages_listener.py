"""
tests/test_sticky_messages_listener.py
==========================================
Test di integrazione reale di StickyMessagesCog.on_message() — non
solo che il cog carica, ma il comportamento vero: ripubblica quando
deve, rispetta il debounce, ignora se il modulo è disattivato.
Database reale (Database() connesso al pool di test, stesso pattern
già usato in test_basic_logs_event_integration.py).
"""

import discord
import pytest

from core.database import Database
from core.repositories.sticky_message_repo import StickyMessageRepository
import cogs.utility.sticky_messages as sticky_messages_module
from cogs.utility.sticky_messages import StickyMessagesCog, MODULE_STICKY_MESSAGES


class _FakeAuthor:
    bot = False


class _FakeHTTPResponse:
    status = 404
    reason = "Not Found"


class _FakeOldMessage:
    def __init__(self, message_id: int, channel) -> None:
        self.id = message_id
        self._channel = channel

    async def delete(self) -> None:
        self._channel.deleted_ids.append(self.id)


class _FakeSentMessage:
    def __init__(self, message_id: int) -> None:
        self.id = message_id


class _FakeTextChannel(discord.TextChannel):
    def __init__(self, channel_id: int, messaggio_esistente_id: int | None = None) -> None:
        self.id = channel_id
        self.sent_messages: list[str] = []
        self.deleted_ids: list[int] = []
        self._messaggio_esistente_id = messaggio_esistente_id
        self._prossimo_id = 9000

    async def fetch_message(self, message_id: int):
        if message_id != self._messaggio_esistente_id:
            raise discord.NotFound(response=_FakeHTTPResponse(), message="non trovato")
        return _FakeOldMessage(message_id, self)

    async def send(self, content: str):
        self._prossimo_id += 1
        self.sent_messages.append(content)
        return _FakeSentMessage(self._prossimo_id)


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


class _FakeMessage:
    def __init__(self, guild: _FakeGuild, channel: _FakeTextChannel) -> None:
        self.guild = guild
        self.channel = channel
        self.author = _FakeAuthor()


def _collega(monkeypatch, database):
    # sticky_messages.py fa "from core.database import db" — il nome
    # è legato al modulo AL MOMENTO DELL'IMPORT, quindi patchare
    # core.database.db non lo tocca: va patchato l'attributo db
    # dentro sticky_messages_module stesso (stesso schema già usato
    # in test_basic_logs_event_integration.py).
    monkeypatch.setattr(sticky_messages_module, "db", database)
    monkeypatch.setattr(
        sticky_messages_module,
        "sticky_message_repo",
        StickyMessageRepository(pool_provider=lambda: database.pool),
    )


@pytest.mark.asyncio
async def test_on_message_ripubblica_e_cancella_il_vecchio(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id, channel_id = 700000001, 800000001
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = $1", guild_id
        )
        await database.pool.execute(
            "DELETE FROM sticky_messages WHERE channel_id = $1", channel_id
        )
        await database.set_module_active_for_guild(guild_id, MODULE_STICKY_MESSAGES, True)

        _collega(monkeypatch, database)
        repo = sticky_messages_module.sticky_message_repo
        await repo.set_sticky(channel_id, guild_id, "Leggi le regole!")

        cog = StickyMessagesCog(bot=None)
        canale = _FakeTextChannel(channel_id)
        messaggio = _FakeMessage(_FakeGuild(guild_id), canale)

        await cog.on_message(messaggio)

        assert canale.sent_messages == ["Leggi le regole!"]

        sticky = await repo.get_sticky(channel_id)
        assert sticky.last_message_id is not None
        assert sticky.last_reposted_at is not None
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 700000001"
        )
        await database.pool.execute(
            "DELETE FROM sticky_messages WHERE channel_id = 800000001"
        )
        await database.close()


@pytest.mark.asyncio
async def test_on_message_cancella_il_vecchio_sticky_prima_di_ripubblicare(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id, channel_id = 700000002, 800000002
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = $1", guild_id
        )
        await database.pool.execute(
            "DELETE FROM sticky_messages WHERE channel_id = $1", channel_id
        )
        await database.set_module_active_for_guild(guild_id, MODULE_STICKY_MESSAGES, True)

        _collega(monkeypatch, database)
        repo = sticky_messages_module.sticky_message_repo
        await repo.set_sticky(channel_id, guild_id, "Testo")
        # Simuliamo un ciclo precedente: c'è già un messaggio sticky
        # live (id=1234) da un repost passato.
        from datetime import datetime, timedelta, timezone
        vecchio_momento = datetime.now(timezone.utc) - timedelta(seconds=60)
        await repo.update_repost_state(channel_id, message_id=1234, reposted_at=vecchio_momento)

        cog = StickyMessagesCog(bot=None)
        canale = _FakeTextChannel(channel_id, messaggio_esistente_id=1234)
        messaggio = _FakeMessage(_FakeGuild(guild_id), canale)

        await cog.on_message(messaggio)

        assert canale.deleted_ids == [1234]
        assert len(canale.sent_messages) == 1
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 700000002"
        )
        await database.pool.execute(
            "DELETE FROM sticky_messages WHERE channel_id = 800000002"
        )
        await database.close()


@pytest.mark.asyncio
async def test_on_message_rispetta_il_debounce(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id, channel_id = 700000003, 800000003
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = $1", guild_id
        )
        await database.pool.execute(
            "DELETE FROM sticky_messages WHERE channel_id = $1", channel_id
        )
        await database.set_module_active_for_guild(guild_id, MODULE_STICKY_MESSAGES, True)

        _collega(monkeypatch, database)
        repo = sticky_messages_module.sticky_message_repo
        await repo.set_sticky(channel_id, guild_id, "Testo")

        from datetime import datetime, timezone
        appena_ora = datetime.now(timezone.utc)
        await repo.update_repost_state(channel_id, message_id=1234, reposted_at=appena_ora)

        cog = StickyMessagesCog(bot=None)
        canale = _FakeTextChannel(channel_id, messaggio_esistente_id=1234)
        messaggio = _FakeMessage(_FakeGuild(guild_id), canale)

        await cog.on_message(messaggio)

        # Ripubblicato pochissimo fa: il debounce deve impedire un
        # nuovo repost immediato.
        assert canale.sent_messages == []
        assert canale.deleted_ids == []
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 700000003"
        )
        await database.pool.execute(
            "DELETE FROM sticky_messages WHERE channel_id = 800000003"
        )
        await database.close()


@pytest.mark.asyncio
async def test_on_message_modulo_disattivato_non_fa_nulla(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id, channel_id = 700000004, 800000004
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = $1", guild_id
        )
        await database.pool.execute(
            "DELETE FROM sticky_messages WHERE channel_id = $1", channel_id
        )
        # Modulo NON attivato.

        _collega(monkeypatch, database)
        repo = sticky_messages_module.sticky_message_repo
        await repo.set_sticky(channel_id, guild_id, "Testo")

        cog = StickyMessagesCog(bot=None)
        canale = _FakeTextChannel(channel_id)
        messaggio = _FakeMessage(_FakeGuild(guild_id), canale)

        await cog.on_message(messaggio)

        assert canale.sent_messages == []
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 700000004"
        )
        await database.pool.execute(
            "DELETE FROM sticky_messages WHERE channel_id = 800000004"
        )
        await database.close()


@pytest.mark.asyncio
async def test_on_message_ignora_messaggi_di_bot(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id, channel_id = 700000005, 800000005
        await database.set_module_active_for_guild(guild_id, MODULE_STICKY_MESSAGES, True)

        _collega(monkeypatch, database)
        repo = sticky_messages_module.sticky_message_repo
        await repo.set_sticky(channel_id, guild_id, "Testo")

        cog = StickyMessagesCog(bot=None)
        canale = _FakeTextChannel(channel_id)
        messaggio = _FakeMessage(_FakeGuild(guild_id), canale)
        messaggio.author.bot = True  # il messaggio è del bot stesso (es. lo sticky appena inviato)

        await cog.on_message(messaggio)

        assert canale.sent_messages == []
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 700000005"
        )
        await database.pool.execute(
            "DELETE FROM sticky_messages WHERE channel_id = 800000005"
        )
        await database.close()
