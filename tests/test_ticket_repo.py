"""
tests/test_ticket_repo.py
============================
Test di TicketRepository contro PostgreSQL reale.
"""

import asyncio

import pytest

from core.repositories.ticket_repo import TicketRepository, run_migrations


@pytest.fixture
def repo(clean_db):
    return TicketRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_migrations_sono_idempotenti(clean_db):
    await run_migrations(clean_db)
    await run_migrations(clean_db)
    for tabella in ("ticket_counters", "tickets"):
        exists = await clean_db.fetchval(
            "SELECT to_regclass($1) IS NOT NULL", f"public.{tabella}"
        )
        assert exists is True


@pytest.mark.asyncio
async def test_primo_ticket_e_il_numero_1(repo):
    numero = await repo.create_ticket(guild_id=100, user_id=1, channel_id=5000)
    assert numero == 1


@pytest.mark.asyncio
async def test_numerazione_progressiva_per_server(repo):
    n1 = await repo.create_ticket(100, 1, 5001)
    n2 = await repo.create_ticket(100, 2, 5002)
    assert (n1, n2) == (1, 2)


@pytest.mark.asyncio
async def test_numerazione_indipendente_tra_server(repo):
    n_a = await repo.create_ticket(guild_id=100, user_id=1, channel_id=5001)
    n_b = await repo.create_ticket(guild_id=200, user_id=1, channel_id=5002)
    assert n_a == 1
    assert n_b == 1


@pytest.mark.asyncio
async def test_numerazione_corretta_con_creazioni_concorrenti(repo):
    # Stesso test critico di concorrenza già fatto per il case system
    # di moderazione: 15 creazioni in parallelo devono produrre 15
    # numeri tutti diversi, senza buchi.
    risultati = await asyncio.gather(
        *[
            repo.create_ticket(guild_id=300, user_id=i, channel_id=6000 + i)
            for i in range(15)
        ]
    )
    assert sorted(risultati) == list(range(1, 16))


@pytest.mark.asyncio
async def test_get_ticket_by_channel(repo):
    await repo.create_ticket(100, 42, 5001)
    ticket = await repo.get_ticket_by_channel(5001)
    assert ticket is not None
    assert ticket.user_id == 42
    assert ticket.status == "open"
    assert ticket.priority == "normal"
    assert ticket.claimed_by is None


@pytest.mark.asyncio
async def test_get_ticket_by_channel_inesistente(repo):
    ticket = await repo.get_ticket_by_channel(999999)
    assert ticket is None


@pytest.mark.asyncio
async def test_count_open_tickets_for_user(repo):
    assert await repo.count_open_tickets_for_user(100, 1) == 0
    await repo.create_ticket(100, 1, 5001)
    assert await repo.count_open_tickets_for_user(100, 1) == 1


@pytest.mark.asyncio
async def test_count_open_tickets_ignora_quelli_chiusi(repo):
    await repo.create_ticket(100, 1, 5001)
    await repo.close_ticket(5001, closed_by=99)
    assert await repo.count_open_tickets_for_user(100, 1) == 0


@pytest.mark.asyncio
async def test_claim_ticket(repo):
    await repo.create_ticket(100, 1, 5001)
    claimed = await repo.claim_ticket(5001, staff_id=42)
    assert claimed is True

    ticket = await repo.get_ticket_by_channel(5001)
    assert ticket.claimed_by == 42


@pytest.mark.asyncio
async def test_claim_ticket_inesistente_restituisce_false(repo):
    claimed = await repo.claim_ticket(999999, staff_id=42)
    assert claimed is False


@pytest.mark.asyncio
async def test_claim_ticket_gia_chiuso_restituisce_false(repo):
    await repo.create_ticket(100, 1, 5001)
    await repo.close_ticket(5001, closed_by=99)
    claimed = await repo.claim_ticket(5001, staff_id=42)
    assert claimed is False


@pytest.mark.asyncio
async def test_close_ticket(repo):
    await repo.create_ticket(100, 1, 5001)
    chiuso = await repo.close_ticket(5001, closed_by=42)
    assert chiuso is True

    ticket = await repo.get_ticket_by_channel(5001)
    assert ticket.status == "closed"
    assert ticket.closed_by == 42
    assert ticket.closed_at is not None


@pytest.mark.asyncio
async def test_close_ticket_gia_chiuso_restituisce_false(repo):
    await repo.create_ticket(100, 1, 5001)
    await repo.close_ticket(5001, closed_by=42)
    chiuso_di_nuovo = await repo.close_ticket(5001, closed_by=42)
    assert chiuso_di_nuovo is False


@pytest.mark.asyncio
async def test_set_priority(repo):
    await repo.create_ticket(100, 1, 5001)
    aggiornato = await repo.set_priority(5001, "urgent")
    assert aggiornato is True

    ticket = await repo.get_ticket_by_channel(5001)
    assert ticket.priority == "urgent"


@pytest.mark.asyncio
async def test_set_priority_non_valida_solleva_errore(repo):
    await repo.create_ticket(100, 1, 5001)
    with pytest.raises(ValueError):
        await repo.set_priority(5001, "altissima")


@pytest.mark.asyncio
async def test_set_priority_su_ticket_chiuso_restituisce_false(repo):
    await repo.create_ticket(100, 1, 5001)
    await repo.close_ticket(5001, closed_by=42)
    aggiornato = await repo.set_priority(5001, "urgent")
    assert aggiornato is False
