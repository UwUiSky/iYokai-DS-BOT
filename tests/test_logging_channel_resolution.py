"""
tests/test_logging_channel_resolution.py
============================================
Test di _get_log_channel() (cogs/logging/basic_logs.py) contro il
database reale, con un oggetto Guild finto minimale (espone solo .id
e .get_channel(), gli unici due usati davvero da quella funzione).
Verifica i tre "se" che devono essere tutti veri perché un log parta:
modulo attivo, canale configurato, canale ancora esistente.
"""

import pytest

from core.database import Database
import cogs.logging.basic_logs as basic_logs


class _FakeChannel:
    def __init__(self, id_: int) -> None:
        self.id = id_


class _FakeTextChannel(_FakeChannel):
    """Serve una classe distinta da _FakeChannel perché
    _get_log_channel controlla isinstance(channel, discord.TextChannel)
    — non possiamo mockare quell'isinstance senza un vero oggetto
    discord, quindi qui testiamo separatamente il ramo che NON supera
    quel controllo (vedi test_canale_di_tipo_sbagliato_restituisce_none)."""
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
        guild_id = 700000001
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = $1", guild_id
        )
        # Canale configurato, ma modulo MAI attivato.
        await database.set_guild_setting(guild_id, "log_channel_id", 999)

        original_db = basic_logs.db
        basic_logs.db = database
        try:
            fake_guild = _FakeGuild(guild_id, {})
            risultato = await basic_logs._get_log_channel(fake_guild)
            assert risultato is None
        finally:
            basic_logs.db = original_db
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 700000001"
        )
        await database.close()


@pytest.mark.asyncio
async def test_modulo_attivo_ma_nessun_canale_configurato_restituisce_none():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000002
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = $1", guild_id
        )
        await database.set_module_active_for_guild(guild_id, "logging_basic", True)
        # Nessun canale impostato.

        original_db = basic_logs.db
        basic_logs.db = database
        try:
            fake_guild = _FakeGuild(guild_id, {})
            risultato = await basic_logs._get_log_channel(fake_guild)
            assert risultato is None
        finally:
            basic_logs.db = original_db
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 700000002"
        )
        await database.close()


@pytest.mark.asyncio
async def test_canale_configurato_ma_non_piu_esistente_restituisce_none():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000003
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = $1", guild_id
        )
        await database.set_module_active_for_guild(guild_id, "logging_basic", True)
        await database.set_guild_setting(guild_id, "log_channel_id", 999)
        # Il canale 999 non esiste in _channels: simula un canale
        # cancellato dopo essere stato configurato come log.

        original_db = basic_logs.db
        basic_logs.db = database
        try:
            fake_guild = _FakeGuild(guild_id, {})  # canale 999 assente
            risultato = await basic_logs._get_log_channel(fake_guild)
            assert risultato is None
        finally:
            basic_logs.db = original_db
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 700000003"
        )
        await database.close()


@pytest.mark.asyncio
async def test_canale_di_tipo_sbagliato_restituisce_none():
    # Anche se un ID è configurato e "esiste" tra i canali del server,
    # se non è un TextChannel (es. l'admin ha configurato per errore
    # un canale vocale) il log non deve provare a scriverci.
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 700000004
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = $1", guild_id
        )
        await database.set_module_active_for_guild(guild_id, "logging_basic", True)
        await database.set_guild_setting(guild_id, "log_channel_id", 999)

        original_db = basic_logs.db
        basic_logs.db = database
        try:
            # _FakeChannel non è un discord.TextChannel reale, quindi
            # isinstance() fallisce esattamente come per un canale
            # vocale vero.
            fake_guild = _FakeGuild(guild_id, {999: _FakeChannel(999)})
            risultato = await basic_logs._get_log_channel(fake_guild)
            assert risultato is None
        finally:
            basic_logs.db = original_db
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 700000004"
        )
        await database.close()
