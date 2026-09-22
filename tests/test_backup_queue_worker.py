"""
tests/test_backup_queue_worker.py
=====================================
Test di BackupQueueWorker.tick() contro PostgreSQL reale per la
coda, con start_backup_job() sostituita da una versione finta
(già testata a fondo in tests/test_backup_orchestrator.py — qui si
verifica solo l'ORCHESTRAZIONE della coda: quale job viene preso,
come reagisce a successo/fallimento).
"""

import discord
import pytest

from core.backup_queue_worker import BackupQueueWorker
from core.database import Database
from core.repositories.backup_repo import STATUS_FAILED, BackupRepository


class _FakeOwner:
    def __init__(self) -> None:
        self.dm_ricevuti: list = []

    async def send(self, embed=None) -> None:
        self.dm_ricevuti.append(embed)


class _FakeMainGuild:
    def __init__(self, guild_id: int, owner) -> None:
        self.id = guild_id
        self.name = "Server Principale"
        self.owner = owner
        self.owner_id = 1


class _FakeMainBotUser:
    id = 999


class _FakeMainBot:
    def __init__(self, guild) -> None:
        self._guild = guild
        self.user = _FakeMainBotUser()

    def get_guild(self, guild_id: int):
        return self._guild if guild_id == self._guild.id else None


class _FakeCreatedGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


@pytest.fixture
async def database_e_repo():
    database = Database()
    await database.connect()
    await database.run_migrations()
    repo = BackupRepository(pool_provider=lambda: database.pool)
    yield database, repo
    await database.pool.execute("DELETE FROM backup_jobs")
    await database.close()


@pytest.mark.asyncio
async def test_tick_senza_job_non_fa_nulla(database_e_repo, monkeypatch):
    database, repo = database_e_repo
    import core.backup_queue_worker as worker_module
    monkeypatch.setattr(worker_module, "backup_repo", repo)

    owner = _FakeOwner()
    main_guild = _FakeMainGuild(100, owner)
    main_bot = _FakeMainBot(main_guild)

    worker = BackupQueueWorker()
    await worker.tick(creator_client=object(), main_bot=main_bot, main_permissions=discord.Permissions.none())

    assert owner.dm_ricevuti == []


@pytest.mark.asyncio
async def test_tick_job_completato_con_successo_notifica_il_proprietario(database_e_repo, monkeypatch):
    database, repo = database_e_repo
    import core.backup_queue_worker as worker_module
    monkeypatch.setattr(worker_module, "backup_repo", repo)

    async def _start_backup_job_finto(creator_client, main_guild, main_client_id, main_permissions):
        return _FakeCreatedGuild(777), "https://discord.com/oauth2/authorize?client_id=999"

    monkeypatch.setattr(worker_module, "start_backup_job", _start_backup_job_finto)

    owner = _FakeOwner()
    main_guild = _FakeMainGuild(100, owner)
    main_bot = _FakeMainBot(main_guild)

    job_id = await repo.enqueue_job(main_guild_id=100)

    worker = BackupQueueWorker()
    await worker.tick(creator_client=object(), main_bot=main_bot, main_permissions=discord.Permissions.none())

    job = await repo.get_job(job_id)
    assert job.backup_guild_id == 777
    assert len(owner.dm_ricevuti) == 1
    assert "oauth2/authorize" in owner.dm_ricevuti[0].description


@pytest.mark.asyncio
async def test_tick_main_non_nel_server_marca_il_job_fallito(database_e_repo, monkeypatch):
    database, repo = database_e_repo
    import core.backup_queue_worker as worker_module
    monkeypatch.setattr(worker_module, "backup_repo", repo)

    owner = _FakeOwner()
    main_guild = _FakeMainGuild(100, owner)
    main_bot = _FakeMainBot(main_guild)

    job_id = await repo.enqueue_job(main_guild_id=999999)  # NON è il guild che main_bot ha

    worker = BackupQueueWorker()
    await worker.tick(creator_client=object(), main_bot=main_bot, main_permissions=discord.Permissions.none())

    job = await repo.get_job(job_id)
    assert job.status == STATUS_FAILED


@pytest.mark.asyncio
async def test_tick_eccezione_durante_start_backup_job_marca_fallito_senza_sollevare(
    database_e_repo, monkeypatch
):
    database, repo = database_e_repo
    import core.backup_queue_worker as worker_module
    monkeypatch.setattr(worker_module, "backup_repo", repo)

    async def _start_backup_job_che_fallisce(*args, **kwargs):
        raise RuntimeError("Discord non ha voluto creare il server")

    monkeypatch.setattr(worker_module, "start_backup_job", _start_backup_job_che_fallisce)

    owner = _FakeOwner()
    main_guild = _FakeMainGuild(100, owner)
    main_bot = _FakeMainBot(main_guild)

    job_id = await repo.enqueue_job(main_guild_id=100)

    worker = BackupQueueWorker()
    await worker.tick(creator_client=object(), main_bot=main_bot, main_permissions=discord.Permissions.none())  # non deve sollevare

    job = await repo.get_job(job_id)
    assert job.status == STATUS_FAILED
    assert "Discord non ha voluto" in job.error_message


@pytest.mark.asyncio
async def test_tick_prende_solo_un_job_alla_volta(database_e_repo, monkeypatch):
    database, repo = database_e_repo
    import core.backup_queue_worker as worker_module
    monkeypatch.setattr(worker_module, "backup_repo", repo)

    chiamate = []

    async def _start_backup_job_finto(creator_client, main_guild, main_client_id, main_permissions):
        chiamate.append(main_guild.id)
        return _FakeCreatedGuild(777), "https://discord.com/oauth2/authorize?client_id=999"

    monkeypatch.setattr(worker_module, "start_backup_job", _start_backup_job_finto)

    owner = _FakeOwner()
    main_guild = _FakeMainGuild(100, owner)
    main_bot = _FakeMainBot(main_guild)

    await repo.enqueue_job(main_guild_id=100)
    await repo.enqueue_job(main_guild_id=100)  # un secondo job in coda

    worker = BackupQueueWorker()
    await worker.tick(creator_client=object(), main_bot=main_bot, main_permissions=discord.Permissions.none())

    # Un SOLO job elaborato in questo tick - coda serializzata, non
    # tutti insieme.
    assert len(chiamate) == 1
