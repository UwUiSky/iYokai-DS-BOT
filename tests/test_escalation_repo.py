"""
tests/test_escalation_repo.py
================================
Test di EscalationRepository contro PostgreSQL reale.
"""

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
@pytest.mark.asyncio
async def test_violation_state_di_default(repo):
    count, last = await repo.get_violation_state(100, 1)
    assert count == 0
    assert last is None


@pytest.mark.asyncio
async def test_record_e_get_violation_state(repo):
    from datetime import datetime, timezone
    ora = datetime.now(timezone.utc)

    await repo.record_violation(100, 1, new_count=1, when=ora)

    count, last = await repo.get_violation_state(100, 1)
    assert count == 1
    assert last is not None


@pytest.mark.asyncio
async def test_record_violation_sovrascrive(repo):
    from datetime import datetime, timezone
    ora = datetime.now(timezone.utc)

    await repo.record_violation(100, 1, new_count=1, when=ora)
    await repo.record_violation(100, 1, new_count=2, when=ora)

    count, _ = await repo.get_violation_state(100, 1)
    assert count == 2


@pytest.mark.asyncio
async def test_reset_violations(repo):
    from datetime import datetime, timezone
    await repo.record_violation(100, 1, new_count=3, when=datetime.now(timezone.utc))

    await repo.reset_violations(100, 1)

    count, last = await repo.get_violation_state(100, 1)
    assert count == 0
    assert last is None


@pytest.mark.asyncio
async def test_violation_state_non_mischia_utenti(repo):
    from datetime import datetime, timezone
    ora = datetime.now(timezone.utc)
    await repo.record_violation(100, 1, new_count=5, when=ora)
    await repo.record_violation(100, 2, new_count=1, when=ora)

    count_1, _ = await repo.get_violation_state(100, 1)
    count_2, _ = await repo.get_violation_state(100, 2)
    assert count_1 == 5
    assert count_2 == 1
