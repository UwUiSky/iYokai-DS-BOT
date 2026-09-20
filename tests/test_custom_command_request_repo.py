"""
tests/test_custom_command_request_repo.py
=============================================
Test di CustomCommandRequestRepository contro PostgreSQL reale.
"""

from datetime import datetime, timezone

import pytest

from core.repositories.custom_command_request_repo import CustomCommandRequestRepository
from core.suggestion_logic import APPROVED, PENDING, REJECTED


@pytest.fixture
def repo(clean_db):
    return CustomCommandRequestRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_create_e_get_request(repo):
    request_id = await repo.create_request(
        requester_guild_id=100,
        requester_guild_name="Server di prova",
        user_id=1,
        username_snapshot="Mario",
        command_name="/meteo",
        description="Mostra il meteo locale",
        example="/meteo Roma",
    )
    request = await repo.get_request(request_id)

    assert request is not None
    assert request.requester_guild_name == "Server di prova"
    assert request.username_snapshot == "Mario"
    assert request.command_name == "/meteo"
    assert request.status == PENDING
    assert request.message_id is None


@pytest.mark.asyncio
async def test_get_request_inesistente_restituisce_none(repo):
    assert await repo.get_request(999999) is None


@pytest.mark.asyncio
async def test_set_message_id(repo):
    request_id = await repo.create_request(100, "Server", 1, "Mario", "/cmd", "desc", "es")
    await repo.set_message_id(request_id, message_id=12345)

    request = await repo.get_request(request_id)
    assert request.message_id == 12345


@pytest.mark.asyncio
async def test_set_status_approva(repo):
    request_id = await repo.create_request(100, "Server", 1, "Mario", "/cmd", "desc", "es")
    ora = datetime.now(timezone.utc)

    await repo.set_status(request_id, APPROVED, decided_by=99, decided_at=ora)

    request = await repo.get_request(request_id)
    assert request.status == APPROVED
    assert request.decided_by == 99


@pytest.mark.asyncio
async def test_set_status_rifiuta(repo):
    request_id = await repo.create_request(100, "Server", 1, "Mario", "/cmd", "desc", "es")
    await repo.set_status(
        request_id, REJECTED, decided_by=99, decided_at=datetime.now(timezone.utc)
    )

    request = await repo.get_request(request_id)
    assert request.status == REJECTED


@pytest.mark.asyncio
async def test_list_pending_esclude_quelle_gia_decise(repo):
    id_pending = await repo.create_request(100, "Server", 1, "Mario", "/cmd1", "d", "e")
    id_pending2 = await repo.create_request(100, "Server", 1, "Mario", "/cmd1", "d", "e")
    await repo.set_message_id(id_pending, message_id=111)
    await repo.set_message_id(id_pending2, message_id=222)
    await repo.set_status(id_pending2, APPROVED, decided_by=99, decided_at=datetime.now(timezone.utc))

    risultato = await repo.list_pending()
    assert len(risultato) == 1
    assert risultato[0].id == id_pending


@pytest.mark.asyncio
async def test_list_pending_esclude_senza_message_id(repo):
    # Una richiesta creata ma non ancora pubblicata (message_id NULL)
    # non deve comparire: non c'è un messaggio a cui agganciare una
    # View all'avvio del bot.
    await repo.create_request(100, "Server", 1, "Mario", "/cmd", "d", "e")

    assert await repo.list_pending() == []
