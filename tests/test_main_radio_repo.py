"""
tests/test_main_radio_repo.py
=================================
Test di MainRadioRepository contro PostgreSQL reale.
"""

from datetime import datetime, timezone

import pytest

from core.repositories.main_radio_repo import MainRadioRepository


@pytest.fixture
def repo(clean_db):
    return MainRadioRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_add_track_e_list_tracks(repo):
    await repo.add_track("query-1", 180_000, "Traccia 1", added_by=1)

    tracce = await repo.list_tracks()
    assert len(tracce) == 1
    assert tracce[0].identifier == "query-1"
    assert tracce[0].position == 0


@pytest.mark.asyncio
async def test_le_tracce_si_accodano_in_ordine_di_aggiunta(repo):
    await repo.add_track("prima", 100, "Prima", 1)
    await repo.add_track("seconda", 200, "Seconda", 1)
    await repo.add_track("terza", 300, "Terza", 1)

    tracce = await repo.list_tracks()
    assert [t.identifier for t in tracce] == ["prima", "seconda", "terza"]
    assert [t.position for t in tracce] == [0, 1, 2]


@pytest.mark.asyncio
async def test_remove_track(repo):
    track_id = await repo.add_track("x", 100, "X", 1)

    rimossa = await repo.remove_track(track_id)

    assert rimossa is True
    assert await repo.list_tracks() == []


@pytest.mark.asyncio
async def test_remove_track_inesistente_restituisce_false(repo):
    assert await repo.remove_track(99999) is False


@pytest.mark.asyncio
async def test_get_state_senza_stato_precedente_restituisce_none(repo):
    assert await repo.get_state() is None


@pytest.mark.asyncio
async def test_set_state_e_get_state(repo):
    adesso = datetime.now(timezone.utc)
    await repo.set_state(track_index=2, track_started_at=adesso, is_active=True)

    stato = await repo.get_state()
    assert stato.track_index == 2
    assert stato.is_active is True


@pytest.mark.asyncio
async def test_set_state_due_volte_sostituisce_lo_stato_precedente(repo):
    prima = datetime(2026, 1, 1, tzinfo=timezone.utc)
    dopo = datetime(2026, 1, 2, tzinfo=timezone.utc)

    await repo.set_state(track_index=0, track_started_at=prima, is_active=True)
    await repo.set_state(track_index=5, track_started_at=dopo, is_active=False)

    stato = await repo.get_state()
    assert stato.track_index == 5
    assert stato.is_active is False
