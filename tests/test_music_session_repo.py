"""
tests/test_music_session_repo.py
====================================
Test di MusicSessionRepository contro PostgreSQL reale.
"""

import pytest

from core.repositories.music_session_repo import MusicSessionRepository


@pytest.fixture
def repo(clean_db):
    return MusicSessionRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_assign_e_get_worker_for_guild(repo):
    await repo.assign_worker(guild_id=100, worker_index=3)

    assert await repo.get_worker_for_guild(100) == 3


@pytest.mark.asyncio
async def test_get_worker_for_guild_senza_sessione_restituisce_none(repo):
    assert await repo.get_worker_for_guild(999) is None


@pytest.mark.asyncio
async def test_assign_due_volte_sostituisce_il_worker(repo):
    await repo.assign_worker(100, worker_index=1)
    await repo.assign_worker(100, worker_index=4)

    assert await repo.get_worker_for_guild(100) == 4


@pytest.mark.asyncio
async def test_release_guild_rimuove_la_sessione(repo):
    await repo.assign_worker(100, worker_index=2)
    await repo.release_guild(100)

    assert await repo.get_worker_for_guild(100) is None


@pytest.mark.asyncio
async def test_release_guild_inesistente_non_solleva(repo):
    await repo.release_guild(999)  # non deve sollevare


@pytest.mark.asyncio
async def test_get_occupied_workers(repo):
    await repo.assign_worker(100, worker_index=1)
    await repo.assign_worker(200, worker_index=3)

    assert await repo.get_occupied_workers() == {1, 3}


@pytest.mark.asyncio
async def test_get_occupied_workers_nessuna_sessione_attiva(repo):
    assert await repo.get_occupied_workers() == set()


@pytest.mark.asyncio
async def test_stesso_worker_su_due_server_diversi_conta_una_sola_volta(repo):
    # Non dovrebbe capitare nella pratica (un worker può stare in un
    # solo canale vocale alla volta, quindi un solo server), ma la
    # query DISTINCT deve comunque comportarsi in modo sensato se
    # capitasse per qualche disallineamento.
    await repo.assign_worker(100, worker_index=2)
    await repo.assign_worker(200, worker_index=2)

    assert await repo.get_occupied_workers() == {2}
