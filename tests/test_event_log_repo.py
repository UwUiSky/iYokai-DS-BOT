"""
tests/test_event_log_repo.py
===============================
Test di EventLogRepository contro PostgreSQL reale.
"""

from datetime import datetime, timedelta, timezone

import pytest

from core.repositories.event_log_repo import EventLogRepository


@pytest.fixture
def repo(clean_db):
    return EventLogRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_log_event_e_get_recent_events(repo):
    await repo.log_event(100, "member_join", target_user_id=1)
    eventi = await repo.get_recent_events(100)
    assert len(eventi) == 1
    assert eventi[0].event_type == "member_join"
    assert eventi[0].target_user_id == 1


@pytest.mark.asyncio
async def test_log_event_con_details_serializzati_correttamente(repo):
    await repo.log_event(
        100, "nickname_update", target_user_id=1,
        details={"before": "Mario", "after": "Luigi"},
    )
    eventi = await repo.get_recent_events(100)
    assert eventi[0].details == {"before": "Mario", "after": "Luigi"}


@pytest.mark.asyncio
async def test_log_event_senza_details_restituisce_none(repo):
    await repo.log_event(100, "member_join", target_user_id=1)
    eventi = await repo.get_recent_events(100)
    assert eventi[0].details is None


@pytest.mark.asyncio
async def test_get_events_by_user_filtra_correttamente(repo):
    await repo.log_event(100, "member_join", target_user_id=1)
    await repo.log_event(100, "member_join", target_user_id=2)
    eventi = await repo.get_events_by_user(100, 1)
    assert len(eventi) == 1
    assert eventi[0].target_user_id == 1


@pytest.mark.asyncio
async def test_get_events_by_channel_filtra_correttamente(repo):
    await repo.log_event(100, "channel_message", channel_id=500)
    await repo.log_event(100, "channel_message", channel_id=600)
    eventi = await repo.get_events_by_channel(100, 500)
    assert len(eventi) == 1
    assert eventi[0].channel_id == 500


@pytest.mark.asyncio
async def test_eventi_ordinati_dal_piu_recente(repo):
    await repo.log_event(100, "primo", target_user_id=1)
    await repo.log_event(100, "secondo", target_user_id=1)
    await repo.log_event(100, "terzo", target_user_id=1)

    eventi = await repo.get_events_by_user(100, 1)
    assert [e.event_type for e in eventi] == ["terzo", "secondo", "primo"]


@pytest.mark.asyncio
async def test_get_events_rispetta_il_limite(repo):
    for i in range(5):
        await repo.log_event(100, f"evento{i}", target_user_id=1)

    eventi = await repo.get_events_by_user(100, 1, limit=2)
    assert len(eventi) == 2


@pytest.mark.asyncio
async def test_eventi_non_mischiano_server(repo):
    await repo.log_event(100, "member_join", target_user_id=1)
    await repo.log_event(200, "member_join", target_user_id=1)

    eventi_100 = await repo.get_events_by_user(100, 1)
    eventi_200 = await repo.get_events_by_user(200, 1)
    assert len(eventi_100) == 1
    assert len(eventi_200) == 1


@pytest.mark.asyncio
async def test_export_events_senza_filtro_data(repo):
    await repo.log_event(100, "member_join", target_user_id=1)
    await repo.log_event(100, "member_leave", target_user_id=1)

    esportati = await repo.export_events(100)
    assert len(esportati) == 2


@pytest.mark.asyncio
async def test_export_events_con_filtro_data(repo):
    vecchio = datetime.now(timezone.utc) - timedelta(days=60)
    await repo._pool.execute(
        "INSERT INTO event_log (guild_id, event_type, target_user_id, created_at) "
        "VALUES ($1, $2, $3, $4)",
        100, "evento_vecchio", 1, vecchio,
    )
    await repo.log_event(100, "evento_recente", target_user_id=1)

    esportati = await repo.export_events(100, since=datetime.now(timezone.utc) - timedelta(days=1))
    assert len(esportati) == 1
    assert esportati[0].event_type == "evento_recente"


@pytest.mark.asyncio
async def test_prune_old_events(repo):
    vecchio = datetime.now(timezone.utc) - timedelta(days=200)
    await repo._pool.execute(
        "INSERT INTO event_log (guild_id, event_type, target_user_id, created_at) "
        "VALUES ($1, $2, $3, $4)",
        100, "evento_vecchio", 1, vecchio,
    )
    await repo.log_event(100, "evento_recente", target_user_id=1)

    eliminati = await repo.prune_old_events(older_than=datetime.now(timezone.utc) - timedelta(days=30))

    assert eliminati == 1
    rimasti = await repo.get_recent_events(100)
    assert len(rimasti) == 1
    assert rimasti[0].event_type == "evento_recente"


@pytest.mark.asyncio
async def test_prune_old_events_for_guild_rispetta_soglie_diverse_per_server(repo):
    # Il caso che conta per la retention differenziata Free/Premium:
    # due server, stessa età dell'evento, soglie diverse — solo uno
    # dei due deve perdere l'evento.
    vecchio = datetime.now(timezone.utc) - timedelta(days=60)
    await repo._pool.execute(
        "INSERT INTO event_log (guild_id, event_type, target_user_id, created_at) "
        "VALUES ($1, $2, $3, $4)",
        100, "evento", 1, vecchio,
    )
    await repo._pool.execute(
        "INSERT INTO event_log (guild_id, event_type, target_user_id, created_at) "
        "VALUES ($1, $2, $3, $4)",
        200, "evento", 1, vecchio,
    )

    # Server 100: soglia Free (30gg) -> l'evento di 60gg fa va eliminato.
    eliminati_100 = await repo.prune_old_events_for_guild(
        100, older_than=datetime.now(timezone.utc) - timedelta(days=30)
    )
    # Server 200: soglia Premium (180gg) -> l'evento di 60gg fa resta.
    eliminati_200 = await repo.prune_old_events_for_guild(
        200, older_than=datetime.now(timezone.utc) - timedelta(days=180)
    )

    assert eliminati_100 == 1
    assert eliminati_200 == 0
    assert len(await repo.get_recent_events(100)) == 0
    assert len(await repo.get_recent_events(200)) == 1


@pytest.mark.asyncio
async def test_prune_old_events_for_guild_non_tocca_altri_server(repo):
    vecchio = datetime.now(timezone.utc) - timedelta(days=200)
    await repo._pool.execute(
        "INSERT INTO event_log (guild_id, event_type, target_user_id, created_at) "
        "VALUES ($1, $2, $3, $4)",
        100, "evento", 1, vecchio,
    )
    await repo._pool.execute(
        "INSERT INTO event_log (guild_id, event_type, target_user_id, created_at) "
        "VALUES ($1, $2, $3, $4)",
        200, "evento", 1, vecchio,
    )

    await repo.prune_old_events_for_guild(
        100, older_than=datetime.now(timezone.utc) - timedelta(days=30)
    )

    # Il server 200 non è mai stato toccato dalla chiamata sopra.
    assert len(await repo.get_recent_events(200)) == 1


@pytest.mark.asyncio
async def test_log_event_con_case_number_e_role_id(repo):
    await repo.log_event(
        100, "moderation_case", target_user_id=1, actor_id=2, case_number=5, role_id=None
    )
    eventi = await repo.get_recent_events(100)
    assert eventi[0].case_number == 5
    assert eventi[0].actor_id == 2
