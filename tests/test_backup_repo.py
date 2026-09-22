"""
tests/test_backup_repo.py
=============================
Test di BackupRepository contro PostgreSQL reale.
"""

import pytest

from core.repositories.backup_repo import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_TIMED_OUT,
    BackupRepository,
)


@pytest.fixture
def repo(clean_db):
    return BackupRepository(pool_provider=lambda: clean_db)


# ----------------------------------------------------------------------
# Abbinamenti main/backup
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_define_main_crea_una_coppia_senza_backup(repo):
    await repo.define_main(100)

    coppia = await repo.get_pair(100)
    assert coppia.main_guild_id == 100
    assert coppia.backup_guild_id is None


@pytest.mark.asyncio
async def test_define_backup_imposta_il_backup(repo):
    await repo.define_main(100)
    await repo.define_backup(100, 200)

    coppia = await repo.get_pair(100)
    assert coppia.backup_guild_id == 200


@pytest.mark.asyncio
async def test_define_main_due_volte_non_cancella_il_backup_esistente(repo):
    await repo.define_main(100)
    await repo.define_backup(100, 200)

    await repo.define_main(100)  # richiamato per errore/di nuovo

    coppia = await repo.get_pair(100)
    assert coppia.backup_guild_id == 200  # non azzerato


@pytest.mark.asyncio
async def test_get_pair_inesistente_restituisce_none(repo):
    assert await repo.get_pair(999) is None


# ----------------------------------------------------------------------
# Coda job
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_enqueue_e_get_next_pending_job(repo):
    job_id = await repo.enqueue_job(main_guild_id=100)

    job = await repo.get_next_pending_job()
    assert job.id == job_id
    assert job.main_guild_id == 100
    assert job.status == STATUS_PENDING


@pytest.mark.asyncio
async def test_get_next_pending_job_rispetta_l_ordine_fifo(repo):
    primo = await repo.enqueue_job(100)
    await repo.enqueue_job(200)

    job = await repo.get_next_pending_job()
    assert job.id == primo


@pytest.mark.asyncio
async def test_get_next_pending_job_ignora_job_non_pending(repo):
    job_id = await repo.enqueue_job(100)
    await repo.mark_running(job_id)

    assert await repo.get_next_pending_job() is None


@pytest.mark.asyncio
async def test_mark_running_cambia_lo_stato(repo):
    job_id = await repo.enqueue_job(100)
    await repo.mark_running(job_id)

    job = await repo.get_job(job_id)
    assert job.status == STATUS_RUNNING


@pytest.mark.asyncio
async def test_mark_completed_salva_il_backup_guild_id(repo):
    job_id = await repo.enqueue_job(100)
    await repo.mark_completed(job_id, backup_guild_id=555)

    job = await repo.get_job(job_id)
    assert job.status == STATUS_COMPLETED
    assert job.backup_guild_id == 555


@pytest.mark.asyncio
async def test_mark_failed_salva_il_messaggio_di_errore(repo):
    job_id = await repo.enqueue_job(100)
    await repo.mark_failed(job_id, "qualcosa è andato storto")

    job = await repo.get_job(job_id)
    assert job.status == STATUS_FAILED
    assert job.error_message == "qualcosa è andato storto"


@pytest.mark.asyncio
async def test_expire_stale_jobs_marca_i_job_vecchi(repo, clean_db):
    job_id = await repo.enqueue_job(100)
    # Retrodatiamo manualmente created_at oltre le 24h — enqueue_job
    # usa sempre now(), non c'è un modo pubblico di simulare il
    # passare del tempo se non toccando direttamente la riga.
    await clean_db.execute(
        "UPDATE backup_jobs SET created_at = now() - interval '25 hours' WHERE id = $1",
        job_id,
    )

    scaduti = await repo.expire_stale_jobs()

    assert scaduti == 1
    job = await repo.get_job(job_id)
    assert job.status == STATUS_TIMED_OUT


@pytest.mark.asyncio
async def test_expire_stale_jobs_non_tocca_job_recenti(repo):
    job_id = await repo.enqueue_job(100)

    scaduti = await repo.expire_stale_jobs()

    assert scaduti == 0
    job = await repo.get_job(job_id)
    assert job.status == STATUS_PENDING


@pytest.mark.asyncio
async def test_expire_stale_jobs_scade_anche_i_job_running_bloccati(repo, clean_db):
    job_id = await repo.enqueue_job(100)
    await repo.mark_running(job_id)
    await clean_db.execute(
        "UPDATE backup_jobs SET created_at = now() - interval '25 hours' WHERE id = $1",
        job_id,
    )

    scaduti = await repo.expire_stale_jobs()

    assert scaduti == 1
    job = await repo.get_job(job_id)
    assert job.status == STATUS_TIMED_OUT


@pytest.mark.asyncio
async def test_expire_stale_jobs_non_tocca_job_gia_completati(repo, clean_db):
    job_id = await repo.enqueue_job(100)
    await repo.mark_completed(job_id, backup_guild_id=555)
    await clean_db.execute(
        "UPDATE backup_jobs SET created_at = now() - interval '25 hours' WHERE id = $1",
        job_id,
    )

    scaduti = await repo.expire_stale_jobs()

    assert scaduti == 0
    job = await repo.get_job(job_id)
    assert job.status == STATUS_COMPLETED  # non alterato


@pytest.mark.asyncio
async def test_get_job_inesistente_restituisce_none(repo):
    assert await repo.get_job(99999) is None


@pytest.mark.asyncio
async def test_set_backup_guild_id_prima_del_completamento(repo):
    job_id = await repo.enqueue_job(100)
    await repo.mark_running(job_id)

    await repo.set_backup_guild_id(job_id, backup_guild_id=777)

    job = await repo.get_job(job_id)
    assert job.backup_guild_id == 777
    assert job.status == STATUS_RUNNING  # non ancora completato


@pytest.mark.asyncio
async def test_get_job_by_backup_guild_id(repo):
    job_id = await repo.enqueue_job(100)
    await repo.set_backup_guild_id(job_id, backup_guild_id=777)

    job = await repo.get_job_by_backup_guild_id(777)
    assert job.id == job_id


@pytest.mark.asyncio
async def test_get_job_by_backup_guild_id_sconosciuto_restituisce_none(repo):
    assert await repo.get_job_by_backup_guild_id(999999) is None


@pytest.mark.asyncio
async def test_get_running_jobs_restituisce_solo_i_running(repo):
    job_pending = await repo.enqueue_job(100)
    job_running = await repo.enqueue_job(200)
    await repo.mark_running(job_running)

    running = await repo.get_running_jobs()

    assert [j.id for j in running] == [job_running]


@pytest.mark.asyncio
async def test_get_running_jobs_lista_vuota_se_nessuno_in_corso(repo):
    await repo.enqueue_job(100)  # resta pending
    assert await repo.get_running_jobs() == []


@pytest.mark.asyncio
async def test_mark_reminder_sent_imposta_il_timestamp(repo):
    job_id = await repo.enqueue_job(100)

    job_prima = await repo.get_job(job_id)
    assert job_prima.reminder_sent_at is None

    await repo.mark_reminder_sent(job_id)

    job_dopo = await repo.get_job(job_id)
    assert job_dopo.reminder_sent_at is not None
