"""
tests/test_basic_logs_event_integration.py
===============================================
Test di integrazione reale: verifica che i listener di
cogs/logging/basic_logs.py scrivano DAVVERO nel log eventi unificato
(core/repositories/event_log_repo.py), non solo che non sollevino
eccezioni. Il punto centrale da provare: la scrittura nel DB avviene
ANCHE SENZA un canale live configurato — a differenza dell'embed, che
richiede un canale, il log unificato serve proprio a funzionare
indipendentemente da quello.
"""

import pytest

from core.database import Database
from core.repositories.event_log_repo import EventLogRepository
import cogs.logging.basic_logs as basic_logs


class _FakeAvatar:
    url = "https://example.com/avatar.png"


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id

    def get_channel(self, channel_id: int):
        return None  # nessun canale configurato, di proposito


class _FakeMember:
    def __init__(self, guild: _FakeGuild, user_id: int) -> None:
        self.guild = guild
        self.id = user_id
        self.mention = f"<@{user_id}>"
        self.display_avatar = _FakeAvatar()
        import datetime
        self.created_at = datetime.datetime.now(datetime.timezone.utc)


@pytest.mark.asyncio
async def test_on_member_join_scrive_nel_log_anche_senza_canale_configurato():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 888800001
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = $1", guild_id
        )
        await database.pool.execute(
            "DELETE FROM event_log WHERE guild_id = $1", guild_id
        )
        await database.set_module_active_for_guild(guild_id, "logging_basic", True)
        # NESSUN canale configurato — questo è il punto del test.

        original_db = basic_logs.db
        basic_logs.db = database
        original_repo_pool = basic_logs.event_log_repo._pool_provider
        basic_logs.event_log_repo._pool_provider = lambda: database.pool

        try:
            cog = basic_logs.BasicLogsCog(bot=None)
            guild = _FakeGuild(guild_id)
            member = _FakeMember(guild, user_id=1)

            await cog.on_member_join(member)

            repo = EventLogRepository(pool_provider=lambda: database.pool)
            eventi = await repo.get_events_by_user(guild_id, 1)
            assert len(eventi) == 1
            assert eventi[0].event_type == "member_join"
        finally:
            basic_logs.db = original_db
            basic_logs.event_log_repo._pool_provider = original_repo_pool
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 888800001"
        )
        await database.pool.execute(
            "DELETE FROM event_log WHERE guild_id = 888800001"
        )
        await database.close()


@pytest.mark.asyncio
async def test_on_member_join_non_scrive_se_modulo_disattivato():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 888800002
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = $1", guild_id
        )
        await database.pool.execute(
            "DELETE FROM event_log WHERE guild_id = $1", guild_id
        )
        # Modulo NON attivato — non chiamiamo set_module_active_for_guild.

        original_db = basic_logs.db
        basic_logs.db = database
        original_repo_pool = basic_logs.event_log_repo._pool_provider
        basic_logs.event_log_repo._pool_provider = lambda: database.pool

        try:
            cog = basic_logs.BasicLogsCog(bot=None)
            guild = _FakeGuild(guild_id)
            member = _FakeMember(guild, user_id=1)

            await cog.on_member_join(member)

            repo = EventLogRepository(pool_provider=lambda: database.pool)
            eventi = await repo.get_events_by_user(guild_id, 1)
            assert eventi == []
        finally:
            basic_logs.db = original_db
            basic_logs.event_log_repo._pool_provider = original_repo_pool
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 888800002"
        )
        await database.pool.execute(
            "DELETE FROM event_log WHERE guild_id = 888800002"
        )
        await database.close()
