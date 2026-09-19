"""
tests/test_event_log_retention.py
=====================================
Test di EventLogRetentionService.tick() (core/event_log_retention.py)
contro database e whitelist premium reali — verifica che due server
con età dell'evento identica ma stato Free/Premium diverso ricevano
soglie di retention diverse, il caso che conta davvero per questa
feature.
"""

from datetime import datetime, timedelta, timezone

import pytest

from core.database import Database
from core.event_log_retention import EventLogRetentionService
import core.event_log_retention as event_log_retention_module
import core.premium as premium_module
from core.repositories.event_log_repo import EventLogRepository
import cogs.logging.basic_logs as basic_logs


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


class _FakeBot:
    def __init__(self, guild_ids: list[int]) -> None:
        self.guilds = [_FakeGuild(gid) for gid in guild_ids]


@pytest.mark.asyncio
async def test_tick_applica_soglie_diverse_free_e_premium():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_free = 888900001
        guild_premium = 888900002

        await database.pool.execute(
            "DELETE FROM event_log WHERE guild_id IN ($1, $2)", guild_free, guild_premium
        )
        await database.pool.execute(
            "DELETE FROM premium_whitelist WHERE guild_id IN ($1, $2)",
            guild_free,
            guild_premium,
        )

        # Un evento di 60 giorni fa su entrambi i server: oltre la
        # soglia Free (30gg), sotto la soglia Premium (180gg).
        vecchio = datetime.now(timezone.utc) - timedelta(days=60)
        for guild_id in (guild_free, guild_premium):
            await database.pool.execute(
                "INSERT INTO event_log (guild_id, event_type, target_user_id, created_at) "
                "VALUES ($1, $2, $3, $4)",
                guild_id, "evento_di_prova", 1, vecchio,
            )

        await database.add_guild_to_whitelist(guild_premium, added_by=1, reason="test")

        original_event_repo_pool = event_log_retention_module.event_log_repo._pool_provider
        event_log_retention_module.event_log_repo._pool_provider = lambda: database.pool
        original_premium_db = premium_module.db if hasattr(premium_module, "db") else None

        # guild_has_premium_access importa core.database.db localmente
        # dentro la funzione stessa (vedi core/premium.py) — dobbiamo
        # sostituire il singleton reale, non un riferimento già
        # importato altrove.
        from core.database import db as real_db_singleton
        original_pool_attr = real_db_singleton._pool
        real_db_singleton._pool = database.pool

        try:
            service = EventLogRetentionService()
            bot = _FakeBot([guild_free, guild_premium])

            await service.tick(bot)

            repo = EventLogRepository(pool_provider=lambda: database.pool)
            eventi_free = await repo.get_recent_events(guild_free)
            eventi_premium = await repo.get_recent_events(guild_premium)

            assert eventi_free == []  # eliminato: oltre i 30gg Free
            assert len(eventi_premium) == 1  # conservato: sotto i 180gg Premium
        finally:
            event_log_retention_module.event_log_repo._pool_provider = (
                original_event_repo_pool
            )
            real_db_singleton._pool = original_pool_attr
    finally:
        await database.pool.execute(
            "DELETE FROM event_log WHERE guild_id IN (888900001, 888900002)"
        )
        await database.pool.execute(
            "DELETE FROM premium_whitelist WHERE guild_id IN (888900001, 888900002)"
        )
        await database.close()
