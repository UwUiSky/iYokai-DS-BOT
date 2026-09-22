"""
tests/test_giveaway_repo.py
===============================
Test di GiveawayRepository contro PostgreSQL reale.
"""

from datetime import datetime, timedelta, timezone

import pytest

from core.repositories.giveaway_repo import GiveawayRepository

ORA = datetime.now(timezone.utc)


@pytest.fixture
def repo(clean_db):
    return GiveawayRepository(pool_provider=lambda: clean_db)


async def _crea(repo, guild_id=100, ends_at=None, winners_count=1, min_level=0, required_role_id=None):
    return await repo.create_giveaway(
        guild_id, channel_id=500, prize="Server Boost", winners_count=winners_count,
        min_level=min_level, required_role_id=required_role_id,
        ends_at=ends_at or (ORA + timedelta(hours=1)), created_by=1,
    )


@pytest.mark.asyncio
async def test_create_e_get_giveaway(repo):
    giveaway_id = await _crea(repo)

    giveaway = await repo.get_giveaway(giveaway_id)
    assert giveaway.prize == "Server Boost"
    assert giveaway.ended is False
    assert giveaway.message_id is None


@pytest.mark.asyncio
async def test_set_message_id(repo):
    giveaway_id = await _crea(repo)

    await repo.set_message_id(giveaway_id, message_id=999)

    assert (await repo.get_giveaway(giveaway_id)).message_id == 999


@pytest.mark.asyncio
async def test_add_entry_nuova_restituisce_true(repo):
    giveaway_id = await _crea(repo)

    assert await repo.add_entry(giveaway_id, user_id=1) is True


@pytest.mark.asyncio
async def test_add_entry_ripetuta_restituisce_false(repo):
    giveaway_id = await _crea(repo)
    await repo.add_entry(giveaway_id, user_id=1)

    assert await repo.add_entry(giveaway_id, user_id=1) is False


@pytest.mark.asyncio
async def test_has_entered(repo):
    giveaway_id = await _crea(repo)
    await repo.add_entry(giveaway_id, user_id=1)

    assert await repo.has_entered(giveaway_id, user_id=1) is True
    assert await repo.has_entered(giveaway_id, user_id=2) is False


@pytest.mark.asyncio
async def test_get_entries_e_count(repo):
    giveaway_id = await _crea(repo)
    await repo.add_entry(giveaway_id, user_id=1)
    await repo.add_entry(giveaway_id, user_id=2)

    assert set(await repo.get_entries(giveaway_id)) == {1, 2}
    assert await repo.count_entries(giveaway_id) == 2


@pytest.mark.asyncio
async def test_get_due_giveaways_solo_quelli_scaduti_e_non_conclusi(repo):
    scaduto = await _crea(repo, ends_at=ORA - timedelta(hours=1))
    futuro = await _crea(repo, ends_at=ORA + timedelta(hours=1))

    dovuti = await repo.get_due_giveaways(ORA)

    assert [g.id for g in dovuti] == [scaduto]


@pytest.mark.asyncio
async def test_mark_ended_lo_esclude_dai_dovuti(repo):
    giveaway_id = await _crea(repo, ends_at=ORA - timedelta(hours=1))
    await repo.mark_ended(giveaway_id)

    assert await repo.get_due_giveaways(ORA) == []


@pytest.mark.asyncio
async def test_create_salva_i_requisiti(repo):
    giveaway_id = await _crea(repo, winners_count=3, min_level=10, required_role_id=555)

    giveaway = await repo.get_giveaway(giveaway_id)
    assert giveaway.winners_count == 3
    assert giveaway.min_level == 10
    assert giveaway.required_role_id == 555


@pytest.mark.asyncio
async def test_get_active_giveaways_esclude_i_conclusi(repo):
    attivo = await _crea(repo, ends_at=ORA + timedelta(hours=1))
    concluso = await _crea(repo, ends_at=ORA - timedelta(hours=1))
    await repo.mark_ended(concluso)

    attivi = await repo.get_active_giveaways()

    assert [g.id for g in attivi] == [attivo]


@pytest.mark.asyncio
async def test_get_active_giveaways_include_anche_i_gia_scaduti_non_ancora_elaborati(repo):
    giveaway_id = await _crea(repo, ends_at=ORA - timedelta(hours=1))

    attivi = await repo.get_active_giveaways()

    assert [g.id for g in attivi] == [giveaway_id]
