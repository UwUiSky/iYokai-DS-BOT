"""
tests/test_soundboard_log_service.py
=========================================
Test di SoundboardLogService.tick() (core/soundboard_log_service.py,
SPEC.md §8.13) contro un database reale — stesso schema di
tests/test_event_log_retention.py: sostituzione del pool sul
singleton reale (molte funzioni lo importano localmente) e sul
repository usato dal servizio.
"""

from datetime import datetime, timedelta, timezone

import discord
import pytest

from core.database import Database
from core.repositories.event_log_repo import EventLogRepository
from core.soundboard_log_service import SoundboardLogService
import core.soundboard_log_service as soundboard_log_service_module
from cogs.logging.advanced_logs import MODULE_LOGGING_ADVANCED, SETTING_SOUNDBOARD_WATERMARK


class _FakeAuditEntry:
    def __init__(self, user_id: int, created_at, name: str | None = None) -> None:
        self.user_id = user_id
        self.created_at = created_at
        self.after = _FakeDiff(name)
        self.before = _FakeDiff(None)
        self.target = None


class _FakeDiff:
    def __init__(self, name: str | None) -> None:
        self.name = name


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id
        self._entries: dict = {}
        self._forbidden_actions: set = set()

    def set_entries(self, action, entries) -> None:
        self._entries[action] = entries

    def set_forbidden(self, action) -> None:
        self._forbidden_actions.add(action)

    async def audit_logs(self, action=None, limit=10):
        if action in self._forbidden_actions:
            raise discord.Forbidden(response=_FakeHTTPResponse(), message="no")
        for entry in self._entries.get(action, [])[:limit]:
            yield entry


class _FakeHTTPResponse:
    status = 403
    reason = "Forbidden"


class _FakeBot:
    def __init__(self, guilds: list[_FakeGuild]) -> None:
        self.guilds = guilds


GUILD_ID = 800000200


@pytest.fixture
async def contesto(monkeypatch):
    database = Database()
    await database.connect()
    await database.run_migrations()
    await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", GUILD_ID)
    await database.pool.execute("DELETE FROM event_log WHERE guild_id = $1", GUILD_ID)

    from core.database import db as real_db_singleton

    original_pool = real_db_singleton._pool
    real_db_singleton._pool = database.pool
    # is_module_active_for_guild ha una cache PER ISTANZA
    # (core/bounded_cache.py) — real_db_singleton è un'istanza
    # Database DIVERSA da quella creata qui sopra, con la sua cache
    # separata. set_module_active_for_guild() nel test invalida solo
    # la cache dell'istanza su cui viene chiamato: senza invalidare
    # anche quella del singleton reale, un test precedente su questo
    # stesso GUILD_ID lascerebbe qui un valore stantio.
    real_db_singleton._modules_cache.delete(GUILD_ID)

    original_provider = soundboard_log_service_module.event_log_repo._pool_provider
    soundboard_log_service_module.event_log_repo._pool_provider = lambda: database.pool

    yield database

    soundboard_log_service_module.event_log_repo._pool_provider = original_provider
    real_db_singleton._pool = original_pool
    await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", GUILD_ID)
    await database.pool.execute("DELETE FROM event_log WHERE guild_id = $1", GUILD_ID)
    await database.close()


@pytest.mark.asyncio
async def test_modulo_non_attivo_viene_ignorato(contesto):
    guild = _FakeGuild(GUILD_ID)
    guild.set_entries(
        discord.AuditLogAction.soundboard_sound_create,
        [_FakeAuditEntry(1, datetime.now(timezone.utc), "boop")],
    )
    bot = _FakeBot([guild])

    service = SoundboardLogService()
    await service.tick(bot)

    watermark = await contesto.get_guild_setting(GUILD_ID, SETTING_SOUNDBOARD_WATERMARK)
    assert watermark is None


@pytest.mark.asyncio
async def test_prima_attivazione_non_riversa_storico_ma_stabilisce_watermark(contesto):
    await contesto.set_module_active_for_guild(GUILD_ID, MODULE_LOGGING_ADVANCED, True)
    guild = _FakeGuild(GUILD_ID)
    creato_il = datetime.now(timezone.utc) - timedelta(minutes=30)
    guild.set_entries(
        discord.AuditLogAction.soundboard_sound_create,
        [_FakeAuditEntry(500, creato_il, "boop")],
    )
    bot = _FakeBot([guild])

    service = SoundboardLogService()
    await service.tick(bot)

    repo = EventLogRepository(pool_provider=lambda: contesto.pool)
    eventi = await repo.get_recent_events(GUILD_ID)
    assert eventi == []  # storico non riversato al primo giro

    watermark = await contesto.get_guild_setting(GUILD_ID, SETTING_SOUNDBOARD_WATERMARK)
    assert watermark is not None  # ma la base è stata stabilita


@pytest.mark.asyncio
async def test_secondo_tick_rileva_una_voce_nuova(contesto):
    await contesto.set_module_active_for_guild(GUILD_ID, MODULE_LOGGING_ADVANCED, True)
    guild = _FakeGuild(GUILD_ID)
    vecchia = datetime.now(timezone.utc) - timedelta(minutes=30)
    guild.set_entries(
        discord.AuditLogAction.soundboard_sound_create,
        [_FakeAuditEntry(500, vecchia, "boop")],
    )
    bot = _FakeBot([guild])
    service = SoundboardLogService()
    await service.tick(bot)  # stabilisce il watermark, non logga nulla

    nuova = datetime.now(timezone.utc)
    guild.set_entries(
        discord.AuditLogAction.soundboard_sound_create,
        [_FakeAuditEntry(500, vecchia, "boop"), _FakeAuditEntry(600, nuova, "yay")],
    )
    await service.tick(bot)

    repo = EventLogRepository(pool_provider=lambda: contesto.pool)
    eventi = await repo.get_recent_events(GUILD_ID)
    assert len(eventi) == 1
    assert eventi[0].event_type == "soundboard_sound_create"
    assert eventi[0].actor_id == 600
    assert eventi[0].details == {"name": "yay"}


@pytest.mark.asyncio
async def test_permessi_insufficienti_su_unazione_non_blocca_le_altre(contesto):
    await contesto.set_module_active_for_guild(GUILD_ID, MODULE_LOGGING_ADVANCED, True)
    guild = _FakeGuild(GUILD_ID)
    guild.set_forbidden(discord.AuditLogAction.soundboard_sound_create)
    vecchia = datetime.now(timezone.utc) - timedelta(minutes=30)
    guild.set_entries(discord.AuditLogAction.soundboard_sound_delete, [_FakeAuditEntry(1, vecchia, "x")])
    bot = _FakeBot([guild])
    service = SoundboardLogService()
    await service.tick(bot)  # stabilisce il watermark solo da "delete"

    nuova = datetime.now(timezone.utc)
    guild.set_entries(
        discord.AuditLogAction.soundboard_sound_delete,
        [_FakeAuditEntry(1, vecchia, "x"), _FakeAuditEntry(2, nuova, "z")],
    )
    await service.tick(bot)

    repo = EventLogRepository(pool_provider=lambda: contesto.pool)
    eventi = await repo.get_recent_events(GUILD_ID)
    assert len(eventi) == 1
    assert eventi[0].event_type == "soundboard_sound_delete"
    assert eventi[0].actor_id == 2
