"""
tests/test_music_session_repo.py
====================================
Test di MusicSessionRepository contro PostgreSQL reale.
"""

import pytest

from core.repositories.music_session_repo import MusicSessionRepository
from tests.support.music_sessioni import assegna, occupati


@pytest.fixture
def repo(clean_db):
    return MusicSessionRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_assign_e_get_worker_for_guild(repo):
    await assegna(repo, guild_id=100, channel_id=1, worker_index=3)

    assert await repo.get_worker_for_channel(100, 1) == 3


@pytest.mark.asyncio
async def test_get_worker_for_guild_senza_sessione_restituisce_none(repo):
    assert await repo.get_worker_for_channel(999, 1) is None


@pytest.mark.asyncio
async def test_assign_due_volte_sostituisce_il_worker(repo):
    await assegna(repo, 100, 1, worker_index=1)
    await assegna(repo, 100, 1, worker_index=4)

    assert await repo.get_worker_for_channel(100, 1) == 4


@pytest.mark.asyncio
async def test_release_guild_rimuove_la_sessione(repo):
    await assegna(repo, 100, 1, worker_index=2)
    await repo.release_session(100, 1)

    assert await repo.get_worker_for_channel(100, 1) is None


@pytest.mark.asyncio
async def test_release_guild_inesistente_non_solleva(repo):
    await repo.release_session(999, 1)  # non deve sollevare


@pytest.mark.asyncio
async def test_get_occupied_workers(repo):
    await assegna(repo, 100, 1, worker_index=1)
    await assegna(repo, 200, 1, worker_index=3)

    assert await occupati(repo) == {1, 3}


@pytest.mark.asyncio
async def test_get_occupied_workers_nessuna_sessione_attiva(repo):
    assert await occupati(repo) == set()


@pytest.mark.asyncio
async def test_stesso_worker_su_due_server_diversi_conta_una_sola_volta(repo):
    # Non dovrebbe capitare nella pratica (un worker può stare in un
    # solo canale vocale alla volta, quindi un solo server), ma la
    # query DISTINCT deve comunque comportarsi in modo sensato se
    # capitasse per qualche disallineamento.
    await assegna(repo, 100, 1, worker_index=2)
    await assegna(repo, 200, 1, worker_index=2)

    assert await occupati(repo) == {2}


@pytest.mark.asyncio
async def test_clear_all_svuota_le_righe_vecchie_all_avvio(repo):
    """BUG-9: dopo un riavvio i worker ripartono da zero, le righe del
    processo precedente non devono tenerli 'occupati' per sempre."""
    await assegna(repo, guild_id=100, channel_id=1, worker_index=1)
    await assegna(repo, guild_id=200, channel_id=1, worker_index=2)

    await repo.clear_all()

    assert await occupati(repo) == set()
    assert await repo.get_worker_for_channel(100, 1) is None


@pytest.mark.asyncio
async def test_move_session_sposta_la_riga_nel_canale_libero(repo):
    await assegna(repo, 100, 1, worker_index=2)
    await repo.move_session(100, 1, 5)

    assert await repo.get_worker_for_channel(100, 1) is None
    assert await repo.get_worker_for_channel(100, 5) == 2


@pytest.mark.asyncio
async def test_move_session_con_canale_di_arrivo_gia_occupato_non_duplica_e_non_viola(repo):
    await assegna(repo, 100, 1, worker_index=2)
    await assegna(repo, 100, 5, worker_index=3)  # nel canale di arrivo c'e' gia' un altro worker

    await repo.move_session(100, 1, 5)  # non deve sollevare (chiave unica)

    assert await repo.get_worker_for_channel(100, 1) is None
    assert await repo.get_worker_for_channel(100, 5) == 3  # la sessione che c'era resta
