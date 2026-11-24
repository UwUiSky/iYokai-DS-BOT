"""FUN-075 (D129): scelta del server sui suoni condivisi. Di base: non condivide, usa gli altri."""
import pytest

from core.repositories.suoni_condivisi_repo import suoni_condivisi_repo


@pytest.fixture
async def repo(monkeypatch, clean_db):
    import core.database as dm

    monkeypatch.setattr(dm.db, "_pool", clean_db)
    return suoni_condivisi_repo


async def test_di_base_non_condivide_e_usa_gli_altri(repo):
    assert await repo.leggi(1) == (False, True)
    assert await repo.server_che_condividono([1, 2]) == set()


async def test_imposta_solo_cio_che_e_dato(repo):
    assert await repo.imposta(1, condividi=True) == (True, True)
    assert await repo.imposta(1, usa_esterni=False) == (True, False)
    assert await repo.imposta(1) == (True, False)  # niente da cambiare
    assert await repo.imposta(2, usa_esterni=False) == (False, False)
    assert await repo.server_che_condividono([1, 2, 3]) == {1}
    assert await repo.server_che_condividono([]) == set()
    assert await repo.imposta(1, condividi=False) == (False, False)
    assert await repo.server_che_condividono([1]) == set()
