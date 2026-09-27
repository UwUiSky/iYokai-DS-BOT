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
    for tabella in ("ticket_counters", "tickets", "ticket_categories"):
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


# ================================================================
# §13.2: categorie ticket
# ================================================================
@pytest.mark.asyncio
async def test_nessuna_categoria_di_default(repo):
    assert await repo.list_categories(100) == []


@pytest.mark.asyncio
async def test_add_e_list_categories(repo):
    await repo.add_category(100, "Supporto tecnico", category_id=10, emoji="🛠️")
    await repo.add_category(100, "Fatturazione", category_id=11)

    categorie = await repo.list_categories(100)
    assert {c.label for c in categorie} == {"Supporto tecnico", "Fatturazione"}


@pytest.mark.asyncio
async def test_add_category_sulla_stessa_label_la_aggiorna(repo):
    await repo.add_category(100, "Supporto", category_id=10)
    await repo.add_category(100, "Supporto", category_id=20)

    categorie = await repo.list_categories(100)
    assert len(categorie) == 1
    assert categorie[0].category_id == 20


@pytest.mark.asyncio
async def test_remove_category(repo):
    await repo.add_category(100, "Supporto", category_id=10)
    rimossa = await repo.remove_category(100, "Supporto")
    assert rimossa is True
    assert await repo.list_categories(100) == []


@pytest.mark.asyncio
async def test_remove_category_inesistente_restituisce_false(repo):
    assert await repo.remove_category(100, "Non esiste") is False


@pytest.mark.asyncio
async def test_create_ticket_con_category_label(repo):
    await repo.create_ticket(100, 1, 5001, category_label="Supporto tecnico")
    ticket = await repo.get_ticket_by_channel(5001)
    assert ticket.category_label == "Supporto tecnico"


# ================================================================
# §13.9: force close
# ================================================================
@pytest.mark.asyncio
async def test_close_ticket_normale_non_e_force_closed(repo):
    await repo.create_ticket(100, 1, 5001)
    await repo.close_ticket(5001, closed_by=42)
    ticket = await repo.get_ticket_by_channel(5001)
    assert ticket.force_closed is False


@pytest.mark.asyncio
async def test_force_close_registra_il_flag(repo):
    await repo.create_ticket(100, 1, 5001)
    await repo.close_ticket(5001, closed_by=42, force=True)
    ticket = await repo.get_ticket_by_channel(5001)
    assert ticket.force_closed is True


# ================================================================
# §13.12: tempo di prima risposta + statistiche
# ================================================================
@pytest.mark.asyncio
async def test_nessuna_prima_risposta_di_default(repo):
    await repo.create_ticket(100, 1, 5001)
    ticket = await repo.get_ticket_by_channel(5001)
    assert ticket.first_response_at is None


@pytest.mark.asyncio
async def test_record_first_response(repo):
    import datetime as dt

    await repo.create_ticket(100, 1, 5001)
    quando = dt.datetime.now(dt.timezone.utc)
    registrata = await repo.record_first_response(5001, quando)
    assert registrata is True

    ticket = await repo.get_ticket_by_channel(5001)
    assert ticket.first_response_at is not None


@pytest.mark.asyncio
async def test_record_first_response_non_sovrascrive_la_prima(repo):
    import datetime as dt

    await repo.create_ticket(100, 1, 5001)
    prima = dt.datetime.now(dt.timezone.utc)
    await repo.record_first_response(5001, prima)

    seconda_registrazione = await repo.record_first_response(
        5001, prima + dt.timedelta(minutes=5)
    )
    assert seconda_registrazione is False

    ticket = await repo.get_ticket_by_channel(5001)
    assert ticket.first_response_at == prima


@pytest.mark.asyncio
async def test_get_operator_stats_senza_ticket(repo):
    stats = await repo.get_operator_stats(100, 42)
    assert stats.claimed_count == 0
    assert stats.closed_count == 0
    assert stats.avg_response_seconds is None


@pytest.mark.asyncio
async def test_get_operator_stats_conta_claim_e_close(repo):
    await repo.create_ticket(100, 1, 5001)
    await repo.create_ticket(100, 2, 5002)
    await repo.claim_ticket(5001, staff_id=42)
    await repo.claim_ticket(5002, staff_id=42)
    await repo.close_ticket(5001, closed_by=42)

    stats = await repo.get_operator_stats(100, 42)
    assert stats.claimed_count == 2
    assert stats.closed_count == 1


@pytest.mark.asyncio
async def test_get_operator_stats_tempo_di_risposta_medio(repo):
    import datetime as dt

    await repo.create_ticket(100, 1, 5001)
    await repo.claim_ticket(5001, staff_id=42)
    ticket = await repo.get_ticket_by_channel(5001)
    await repo.record_first_response(5001, ticket.created_at + dt.timedelta(seconds=60))

    stats = await repo.get_operator_stats(100, 42)
    assert stats.avg_response_seconds is not None
    assert 55 <= stats.avg_response_seconds <= 65


@pytest.mark.asyncio
async def test_get_guild_stats_senza_ticket(repo):
    stats = await repo.get_guild_stats(100)
    assert stats.total_count == 0
    assert stats.open_count == 0
    assert stats.closed_count == 0
    assert stats.avg_response_seconds is None


@pytest.mark.asyncio
async def test_get_guild_stats_conta_aperti_e_chiusi(repo):
    await repo.create_ticket(100, 1, 5001)
    await repo.create_ticket(100, 2, 5002)
    await repo.close_ticket(5002, closed_by=42)

    stats = await repo.get_guild_stats(100)
    assert stats.total_count == 2
    assert stats.open_count == 1
    assert stats.closed_count == 1
