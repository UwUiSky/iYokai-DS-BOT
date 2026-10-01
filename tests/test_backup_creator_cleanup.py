"""
tests/test_backup_creator_cleanup.py
=======================================
BUG-4 (#21): gli slot del Creator (max 10 server) si esaurivano per sempre
perché un server creato per un backup fallito o scaduto non veniva mai
cancellato. Ora: un job che fallisce durante la clonazione, un job
scaduto e un server orfano all'avvio vengono ripuliti.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import core.backup_orchestrator as orchestrator
from core.backup_orchestrator import elimina_server_creato, pulisci_server_orfani, start_backup_job
from core.backup_queue_worker import BackupQueueWorker
from core.repositories.backup_repo import BackupRepository
from tests.support.discord_fakes import fake_guild

CREATOR_ID = 4242


def _creator(*guilds):
    creator = MagicMock()
    creator.user = MagicMock(id=CREATOR_ID)
    creator.guilds = list(guilds)
    creator.get_guild = lambda gid: next((g for g in guilds if g.id == gid), None)
    return creator


def _server(guild_id, *, owner_id=CREATOR_ID, eta=timedelta(hours=3)):
    g = fake_guild(guild_id=guild_id, owner_id=owner_id)
    g.created_at = datetime.now(timezone.utc) - eta
    return g


@pytest.fixture
def repo(clean_db):
    return BackupRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_start_backup_job_cancella_il_server_se_la_clonazione_fallisce(monkeypatch):
    creato = _server(555)
    creator = _creator()
    creator.create_guild = AsyncMock(return_value=creato)
    monkeypatch.setattr(orchestrator, "clone_roles", AsyncMock(side_effect=RuntimeError("boom")))

    with pytest.raises(RuntimeError):
        await start_backup_job(creator, MagicMock(name="main"), 1, discord.Permissions.none())

    creato.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_elimina_server_creato_lo_cancella_se_il_creator_e_proprietario():
    server = _server(555)
    await elimina_server_creato(_creator(server), 555)
    server.delete.assert_awaited_once()
    server.leave.assert_not_awaited()


@pytest.mark.asyncio
async def test_elimina_server_creato_esce_se_la_proprieta_e_stata_trasferita():
    server = _server(555, owner_id=999)
    await elimina_server_creato(_creator(server), 555)
    server.leave.assert_awaited_once()
    server.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_elimina_server_creato_non_solleva_se_discord_rifiuta():
    server = _server(555)
    server.delete.side_effect = discord.Forbidden(MagicMock(status=403, reason="x"), "no")
    await elimina_server_creato(_creator(server), 555)  # non deve sollevare


@pytest.mark.asyncio
async def test_pulizia_all_avvio_cancella_solo_i_server_orfani_vecchi(repo):
    orfano_vecchio = _server(1, eta=timedelta(hours=3))
    orfano_recente = _server(2, eta=timedelta(minutes=10))
    legato_a_job = _server(3, eta=timedelta(hours=3))
    job_id = await repo.enqueue_job(main_guild_id=100)
    await repo.mark_running(job_id)
    await repo.set_backup_guild_id(job_id, 3)

    await pulisci_server_orfani(_creator(orfano_vecchio, orfano_recente, legato_a_job), repo)

    orfano_vecchio.delete.assert_awaited_once()
    orfano_recente.delete.assert_not_awaited()
    legato_a_job.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_job_scaduto_libera_lo_slot_cancellando_il_server(repo, clean_db, monkeypatch):
    import core.backup_queue_worker as modulo

    monkeypatch.setattr(modulo, "backup_repo", repo)
    server = _server(555)
    job_id = await repo.enqueue_job(main_guild_id=100)
    await repo.mark_running(job_id)
    await repo.set_backup_guild_id(job_id, 555)
    await clean_db.execute(
        "UPDATE backup_jobs SET created_at = now() - interval '25 hours' WHERE id = $1", job_id
    )

    await BackupQueueWorker()._libera_server_scaduti(_creator(server))

    server.delete.assert_awaited_once()
    assert (await repo.get_job(job_id)).status == "timed_out"
