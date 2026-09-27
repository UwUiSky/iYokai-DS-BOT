"""
tests/test_backup_user_snapshot_repo.py
============================================
Test di BackupUserSnapshotRepository contro PostgreSQL reale.
"""

import pytest

from core.repositories.backup_user_snapshot_repo import BackupUserSnapshotRepository


@pytest.fixture
def repo(clean_db):
    return BackupUserSnapshotRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_save_snapshot_e_get_snapshot(repo):
    await repo.save_snapshot(100, [(1, "Utente Uno", "https://cdn.example/a.png"), (2, "Utente Due", None)])

    snapshot = await repo.get_snapshot(100)
    assert {e.user_id for e in snapshot} == {1, 2}
    entry_uno = next(e for e in snapshot if e.user_id == 1)
    assert entry_uno.username == "Utente Uno"
    assert entry_uno.avatar_url == "https://cdn.example/a.png"


@pytest.mark.asyncio
async def test_get_snapshot_di_un_main_senza_snapshot_e_vuoto(repo):
    assert await repo.get_snapshot(999) == []


@pytest.mark.asyncio
async def test_save_snapshot_sostituisce_interamente_quello_precedente(repo):
    await repo.save_snapshot(100, [(1, "Vecchio", None), (2, "Vecchio2", None)])
    await repo.save_snapshot(100, [(3, "Nuovo", None)])

    snapshot = await repo.get_snapshot(100)
    assert {e.user_id for e in snapshot} == {3}


@pytest.mark.asyncio
async def test_save_snapshot_vuoto_non_solleva(repo):
    await repo.save_snapshot(100, [(1, "Utente", None)])
    await repo.save_snapshot(100, [])

    assert await repo.get_snapshot(100) == []


@pytest.mark.asyncio
async def test_get_snapshot_count(repo):
    await repo.save_snapshot(100, [(1, "A", None), (2, "B", None), (3, "C", None)])
    assert await repo.get_snapshot_count(100) == 3


@pytest.mark.asyncio
async def test_delete_for_main_guild(repo):
    await repo.save_snapshot(100, [(1, "A", None)])
    await repo.delete_for_main_guild(100)

    assert await repo.get_snapshot(100) == []


@pytest.mark.asyncio
async def test_main_diversi_hanno_snapshot_indipendenti(repo):
    await repo.save_snapshot(100, [(1, "A", None)])
    await repo.save_snapshot(200, [(2, "B", None)])

    assert len(await repo.get_snapshot(100)) == 1
    assert len(await repo.get_snapshot(200)) == 1
