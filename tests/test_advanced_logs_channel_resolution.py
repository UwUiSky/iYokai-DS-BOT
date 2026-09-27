"""
tests/test_advanced_logs_channel_resolution.py
====================================================
Test di _advanced_log_channel() (cogs/logging/advanced_logs.py) —
stesso schema di tests/test_logging_channel_resolution.py, con
MODULE_LOGGING_ADVANCED al posto di MODULE_LOGGING (i due livelli
usano lo stesso canale configurato, ma moduli diversi decidono se ci
scrive dentro).
"""

import pytest

from core.database import Database
import cogs.logging.advanced_logs as advanced_logs
from cogs.logging.advanced_logs import MODULE_LOGGING_ADVANCED


class _FakeChannel:
    def __init__(self, id_: int) -> None:
        self.id = id_


class _FakeTextChannel(_FakeChannel):
    pass


class _FakeGuild:
    def __init__(self, guild_id: int, channels: dict[int, object]) -> None:
        self.id = guild_id
        self._channels = channels

    def get_channel(self, channel_id: int):
        return self._channels.get(channel_id)


@pytest.mark.asyncio
async def test_nessun_modulo_attivo_restituisce_none():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000501
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)
        await database.set_guild_setting(guild_id, "log_channel_id", 999)

        original_db = advanced_logs.db
        advanced_logs.db = database
        try:
            fake_guild = _FakeGuild(guild_id, {})
            risultato = await advanced_logs._advanced_log_channel(fake_guild)
            assert risultato is None
        finally:
            advanced_logs.db = original_db
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 700000501")
        await database.close()


@pytest.mark.asyncio
async def test_modulo_attivo_ma_nessun_canale_configurato_restituisce_none():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000502
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)
        await database.set_module_active_for_guild(guild_id, MODULE_LOGGING_ADVANCED, True)

        original_db = advanced_logs.db
        advanced_logs.db = database
        try:
            fake_guild = _FakeGuild(guild_id, {})
            risultato = await advanced_logs._advanced_log_channel(fake_guild)
            assert risultato is None
        finally:
            advanced_logs.db = original_db
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 700000502")
        await database.close()


@pytest.mark.asyncio
async def test_modulo_di_base_attivo_ma_avanzato_no_restituisce_none():
    # Il modulo Free (logging_basic) attivo NON basta a far passare
    # gli eventi Premium — verificato esplicitamente, non assunto.
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000503
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)
        await database.set_module_active_for_guild(guild_id, "logging_basic", True)
        await database.set_guild_setting(guild_id, "log_channel_id", 999)

        original_db = advanced_logs.db
        advanced_logs.db = database
        try:
            fake_guild = _FakeGuild(guild_id, {999: _FakeTextChannel(999)})
            risultato = await advanced_logs._advanced_log_channel(fake_guild)
            assert risultato is None
        finally:
            advanced_logs.db = original_db
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 700000503")
        await database.close()


@pytest.mark.asyncio
async def test_canale_di_tipo_sbagliato_restituisce_none():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000504
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)
        await database.set_module_active_for_guild(guild_id, MODULE_LOGGING_ADVANCED, True)
        await database.set_guild_setting(guild_id, "log_channel_id", 999)

        original_db = advanced_logs.db
        advanced_logs.db = database
        try:
            fake_guild = _FakeGuild(guild_id, {999: _FakeChannel(999)})
            risultato = await advanced_logs._advanced_log_channel(fake_guild)
            assert risultato is None
        finally:
            advanced_logs.db = original_db
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 700000504")
        await database.close()
