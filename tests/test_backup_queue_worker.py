"""
tests/test_backup_queue_worker.py
=====================================
Test di BackupQueueWorker.tick() contro PostgreSQL reale per la
coda, con popola_server_backup() sostituita da una versione finta
(la copia vera è in tests/test_backup_clone_*.py): quale job viene
preso, come reagisce a successo e fallimento, che la copia usi il
server visto dal Creator (D8).
"""

import discord
import pytest

from core.backup_queue_worker import BackupQueueWorker
from core.database import Database
from core.repositories.backup_mirror_repo import BackupMirrorRepository
from core.repositories.backup_repo import STATUS_COMPLETED, STATUS_FAILED, BackupRepository
from core.backup_clone_logic import RiepilogoCopia


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


class _FakeBackupGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id
        self.name = "Backup"


class _FakeCreatorClient:
    """Il Creator vede i server in cui è entrato: get_guild() li restituisce."""

    def __init__(self, guild_ids=()) -> None:
        self._guilds = {i: _FakeBackupGuild(i) for i in guild_ids}

    def get_guild(self, guild_id: int):
        return self._guilds.get(guild_id)


@pytest.fixture
async def database_e_repo():
    database = Database()
    await database.connect()
    await database.run_migrations()
    await database.pool.execute("DELETE FROM backup_jobs")
    await database.pool.execute("DELETE FROM backup_mirror_webhooks")
    repo = BackupRepository(pool_provider=lambda: database.pool)
    mirror_repo = BackupMirrorRepository(pool_provider=lambda: database.pool)
    yield database, repo, mirror_repo
    await database.pool.execute("DELETE FROM backup_jobs")
    await database.pool.execute("DELETE FROM backup_mirror_webhooks")
    await database.close()


def _con(worker_module, monkeypatch, repo, mirror_repo, copia=None):
    monkeypatch.setattr(worker_module, "backup_repo", repo)
    monkeypatch.setattr(worker_module, "backup_mirror_repo", mirror_repo)
    if copia is not None:
        monkeypatch.setattr(worker_module, "popola_server_backup", copia)


@pytest.mark.asyncio
async def test_tick_senza_job_non_fa_nulla(database_e_repo, monkeypatch):
    _database, repo, mirror_repo = database_e_repo
    import core.backup_queue_worker as worker_module
    _con(worker_module, monkeypatch, repo, mirror_repo)

    owner = _FakeOwner()
    main_bot = _FakeMainBot(_FakeMainGuild(100, owner))

    await BackupQueueWorker().tick(_FakeCreatorClient(), main_bot)

    assert owner.dm_ricevuti == []


@pytest.mark.asyncio
async def test_tick_copia_sul_server_del_creator_e_notifica(database_e_repo, monkeypatch):
    _database, repo, mirror_repo = database_e_repo
    import core.backup_queue_worker as worker_module

    chiamate = []

    async def _copia(main_guild, backup_guild):
        chiamate.append((main_guild, backup_guild))
        return {5: "https://discord.com/api/webhooks/1/x"}, RiepilogoCopia(canali_offuscati=1)

    _con(worker_module, monkeypatch, repo, mirror_repo, _copia)
    owner = _FakeOwner()
    main_guild = _FakeMainGuild(100, owner)
    creator = _FakeCreatorClient([777])
    job_id = await repo.enqueue_linked_job(100, 777)

    await BackupQueueWorker().tick(creator, _FakeMainBot(main_guild))

    assert chiamate[0][0] is main_guild
    assert chiamate[0][1] is creator.get_guild(777)  # D8: server visto dal Creator
    assert (await repo.get_job(job_id)).status == STATUS_COMPLETED
    assert await mirror_repo.get_webhook_url(5) == "https://discord.com/api/webhooks/1/x"
    assert len(owner.dm_ricevuti) == 1
    assert "offuscati" in owner.dm_ricevuti[0].description


@pytest.mark.asyncio
async def test_tick_creator_non_nel_server_di_backup_fallisce_con_messaggio(database_e_repo, monkeypatch):
    _database, repo, mirror_repo = database_e_repo
    import core.backup_queue_worker as worker_module
    _con(worker_module, monkeypatch, repo, mirror_repo)
    main_bot = _FakeMainBot(_FakeMainGuild(100, _FakeOwner()))
    job_id = await repo.enqueue_linked_job(100, 777)

    await BackupQueueWorker().tick(_FakeCreatorClient(), main_bot)

    job = await repo.get_job(job_id)
    assert job.status == STATUS_FAILED
    assert "Creator" in job.error_message


@pytest.mark.asyncio
async def test_tick_job_senza_server_di_backup_fallisce(database_e_repo, monkeypatch):
    _database, repo, mirror_repo = database_e_repo
    import core.backup_queue_worker as worker_module
    _con(worker_module, monkeypatch, repo, mirror_repo)
    job_id = await repo.enqueue_job(main_guild_id=100)

    await BackupQueueWorker().tick(_FakeCreatorClient(), _FakeMainBot(_FakeMainGuild(100, _FakeOwner())))

    assert (await repo.get_job(job_id)).status == STATUS_FAILED


@pytest.mark.asyncio
async def test_tick_main_non_nel_server_marca_il_job_fallito(database_e_repo, monkeypatch):
    _database, repo, mirror_repo = database_e_repo
    import core.backup_queue_worker as worker_module
    _con(worker_module, monkeypatch, repo, mirror_repo)
    job_id = await repo.enqueue_linked_job(555, 777)

    await BackupQueueWorker().tick(_FakeCreatorClient([777]), _FakeMainBot(_FakeMainGuild(100, _FakeOwner())))

    assert (await repo.get_job(job_id)).status == STATUS_FAILED


@pytest.mark.asyncio
async def test_tick_errore_durante_la_copia_marca_fallito_senza_sollevare(database_e_repo, monkeypatch):
    _database, repo, mirror_repo = database_e_repo
    import core.backup_queue_worker as worker_module

    async def _copia(main_guild, backup_guild):
        raise RuntimeError("Discord ha rifiutato")

    _con(worker_module, monkeypatch, repo, mirror_repo, _copia)
    job_id = await repo.enqueue_linked_job(100, 777)

    await BackupQueueWorker().tick(_FakeCreatorClient([777]), _FakeMainBot(_FakeMainGuild(100, _FakeOwner())))

    job = await repo.get_job(job_id)
    assert job.status == STATUS_FAILED and "rifiutato" in job.error_message


@pytest.mark.asyncio
async def test_tick_prende_solo_un_job_alla_volta(database_e_repo, monkeypatch):
    _database, repo, mirror_repo = database_e_repo
    import core.backup_queue_worker as worker_module

    async def _copia(main_guild, backup_guild):
        return {}, RiepilogoCopia()

    _con(worker_module, monkeypatch, repo, mirror_repo, _copia)
    primo = await repo.enqueue_linked_job(100, 777)
    secondo = await repo.enqueue_linked_job(100, 778)

    await BackupQueueWorker().tick(_FakeCreatorClient([777, 778]), _FakeMainBot(_FakeMainGuild(100, _FakeOwner())))

    assert (await repo.get_job(primo)).status == STATUS_COMPLETED
    assert (await repo.get_job(secondo)).status == "pending"


@pytest.mark.asyncio
async def test_il_worker_non_crea_ne_cancella_server():
    """M 12.2: nessun controllo di capacità (10 posti) né pulizia dei server."""
    import core.backup_queue_worker as worker_module

    assert not hasattr(worker_module, "elimina_server_creato")
    assert not hasattr(worker_module, "MAX_CREATOR_GUILDS")
