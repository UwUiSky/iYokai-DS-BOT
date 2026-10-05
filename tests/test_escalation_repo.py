"""
tests/test_escalation_repo.py
================================
Test di EscalationRepository contro PostgreSQL reale.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from core.escalation_ladder_logic import LadderStep
from core.repositories.escalation_repo import (
    DEFAULT_LADDER,
    DEFAULT_RESET_AFTER_DAYS,
    EscalationRepository,
)


@pytest.fixture
def repo(clean_db):
    return EscalationRepository(pool_provider=lambda: clean_db)


# ====================================================================
# Configurazione
# ====================================================================
@pytest.mark.asyncio
async def test_config_di_default(repo):
    config = await repo.get_config(100)
    assert config.enabled is False
    assert config.reset_after_days == DEFAULT_RESET_AFTER_DAYS
    assert config.ladder == DEFAULT_LADDER


@pytest.mark.asyncio
async def test_set_enabled(repo):
    await repo.set_enabled(100, True)
    config = await repo.get_config(100)
    assert config.enabled is True


@pytest.mark.asyncio
async def test_set_reset_after_days(repo):
    await repo.set_reset_after_days(100, 14)
    config = await repo.get_config(100)
    assert config.reset_after_days == 14


@pytest.mark.asyncio
async def test_set_step_personalizza_la_scala(repo):
    await repo.set_step(100, level=1, action_type="timeout", duration_seconds=120)

    config = await repo.get_config(100)
    # Con almeno un gradino personalizzato, la scala NON deve più
    # essere quella di default — è la scala dell'admin, anche se
    # incompleta (un solo livello).
    assert config.ladder == [LadderStep(1, "timeout", 120)]


@pytest.mark.asyncio
async def test_set_step_stesso_livello_due_volte_aggiorna(repo):
    await repo.set_step(100, level=1, action_type="warn", duration_seconds=None)
    await repo.set_step(100, level=1, action_type="timeout", duration_seconds=300)

    config = await repo.get_config(100)
    assert len(config.ladder) == 1
    assert config.ladder[0].action_type == "timeout"
    assert config.ladder[0].duration_seconds == 300


@pytest.mark.asyncio
async def test_get_config_ordina_i_gradini_per_livello(repo):
    await repo.set_step(100, level=3, action_type="ban", duration_seconds=None)
    await repo.set_step(100, level=1, action_type="warn", duration_seconds=None)
    await repo.set_step(100, level=2, action_type="timeout", duration_seconds=60)

    config = await repo.get_config(100)
    assert [s.level for s in config.ladder] == [1, 2, 3]


@pytest.mark.asyncio
async def test_remove_step(repo):
    await repo.set_step(100, level=1, action_type="warn", duration_seconds=None)
    rimosso = await repo.remove_step(100, level=1)
    assert rimosso is True

    config = await repo.get_config(100)
    # Nessun gradino personalizzato rimasto: torna alla scala di default.
    assert config.ladder == DEFAULT_LADDER


@pytest.mark.asyncio
async def test_remove_step_inesistente_restituisce_false(repo):
    assert await repo.remove_step(100, level=99) is False


@pytest.mark.asyncio
async def test_config_non_mischia_server(repo):
    await repo.set_enabled(100, True)
    await repo.set_enabled(200, False)

    assert (await repo.get_config(100)).enabled is True
    assert (await repo.get_config(200)).enabled is False


# ====================================================================
# Conteggio infrazioni
# ====================================================================
ORA = datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_prima_infrazione_conta_uno(repo):
    assert await repo.record_violation(100, 1, when=ORA, reset_after_days=30) == 1


@pytest.mark.asyncio
async def test_ogni_infrazione_aumenta_di_uno(repo):
    await repo.record_violation(100, 1, when=ORA, reset_after_days=30)
    secondo = await repo.record_violation(100, 1, when=ORA, reset_after_days=30)
    terzo = await repo.record_violation(100, 1, when=ORA, reset_after_days=30)

    assert (secondo, terzo) == (2, 3)


@pytest.mark.asyncio
async def test_infrazioni_insieme_non_si_perdono(repo):
    conteggi = await asyncio.gather(
        *(repo.record_violation(100, 1, when=ORA, reset_after_days=30) for _ in range(20))
    )

    assert sorted(conteggi) == list(range(1, 21))


@pytest.mark.asyncio
async def test_buona_condotta_fa_ripartire_da_uno(repo):
    await repo.record_violation(100, 1, when=ORA, reset_after_days=30)
    await repo.record_violation(100, 1, when=ORA, reset_after_days=30)

    quasi = await repo.record_violation(
        100, 1, when=ORA + timedelta(days=29), reset_after_days=30
    )
    # 30 giorni esatti dall'ultima infrazione (quella del giorno 29).
    al_confine = await repo.record_violation(
        100, 1, when=ORA + timedelta(days=59), reset_after_days=30
    )

    assert quasi == 3
    assert al_confine == 1


@pytest.mark.asyncio
async def test_reset_violations(repo):
    await repo.record_violation(100, 1, when=ORA, reset_after_days=30)
    await repo.record_violation(100, 1, when=ORA, reset_after_days=30)

    await repo.reset_violations(100, 1)

    assert await repo.record_violation(100, 1, when=ORA, reset_after_days=30) == 1


@pytest.mark.asyncio
async def test_conteggio_non_mischia_utenti_e_server(repo):
    await repo.record_violation(100, 1, when=ORA, reset_after_days=30)
    await repo.record_violation(100, 1, when=ORA, reset_after_days=30)

    assert await repo.record_violation(100, 2, when=ORA, reset_after_days=30) == 1
    assert await repo.record_violation(200, 1, when=ORA, reset_after_days=30) == 1
