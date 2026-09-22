"""
tests/test_backup_cog_behavior.py
=====================================
Test del comportamento REALE di /define-main e /define-backup —
contro PostgreSQL vero.
"""

import pytest

from cogs.utility.backup import BackupCog
from core.database import Database


class _FakeResponse:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []

    async def send_message(self, content: str, ephemeral: bool = False) -> None:
        self.sent_messages.append(content)


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


class _FakeInteraction:
    def __init__(self, guild_id: int | None) -> None:
        self.guild = _FakeGuild(guild_id) if guild_id is not None else None
        self.response = _FakeResponse()


@pytest.mark.asyncio
async def test_define_main_registra_il_server(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        import cogs.utility.backup as backup_module
        from core.repositories.backup_repo import BackupRepository

        repo = BackupRepository(pool_provider=lambda: database.pool)
        monkeypatch.setattr(backup_module, "backup_repo", repo)

        cog = BackupCog(bot=None)
        interaction = _FakeInteraction(guild_id=100)

        await cog.define_main.callback(cog, interaction)

        assert "registrato come 'main'" in interaction.response.sent_messages[0]
        coppia = await repo.get_pair(100)
        assert coppia is not None
    finally:
        await database.pool.execute("DELETE FROM backup_pairs")
        await database.close()


@pytest.mark.asyncio
async def test_define_backup_senza_define_main_prima_avvisa(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        import cogs.utility.backup as backup_module
        from core.repositories.backup_repo import BackupRepository

        repo = BackupRepository(pool_provider=lambda: database.pool)
        monkeypatch.setattr(backup_module, "backup_repo", repo)

        cog = BackupCog(bot=None)
        interaction = _FakeInteraction(guild_id=999)

        await cog.define_backup.callback(cog, interaction)

        assert "prima registrare" in interaction.response.sent_messages[0]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_define_backup_dopo_define_main_accoda_un_job(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        import cogs.utility.backup as backup_module
        from core.repositories.backup_repo import BackupRepository

        repo = BackupRepository(pool_provider=lambda: database.pool)
        monkeypatch.setattr(backup_module, "backup_repo", repo)

        cog = BackupCog(bot=None)

        interaction_main = _FakeInteraction(guild_id=100)
        await cog.define_main.callback(cog, interaction_main)

        interaction_backup = _FakeInteraction(guild_id=100)
        await cog.define_backup.callback(cog, interaction_backup)

        assert "Backup accodato" in interaction_backup.response.sent_messages[0]

        job = await repo.get_next_pending_job()
        assert job is not None
        assert job.main_guild_id == 100
    finally:
        await database.pool.execute("DELETE FROM backup_pairs")
        await database.pool.execute("DELETE FROM backup_jobs")
        await database.close()


@pytest.mark.asyncio
async def test_define_main_fuori_da_un_server_rifiuta():
    cog = BackupCog(bot=None)
    interaction = _FakeInteraction(guild_id=None)

    await cog.define_main.callback(cog, interaction)

    assert "solo dentro un server" in interaction.response.sent_messages[0]
