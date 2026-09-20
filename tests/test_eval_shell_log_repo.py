"""
tests/test_eval_shell_log_repo.py
=====================================
Test di EvalShellLogRepository contro PostgreSQL reale.
"""

import pytest

from core.repositories.eval_shell_log_repo import EvalShellLogRepository


@pytest.fixture
def repo(clean_db):
    return EvalShellLogRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_log_e_get_recent(repo):
    await repo.log(executor_id=1, kind="eval", code_or_command="1+1", success=True)

    voci = await repo.get_recent()
    assert len(voci) == 1
    assert voci[0].kind == "eval"
    assert voci[0].code_or_command == "1+1"
    assert voci[0].success is True


@pytest.mark.asyncio
async def test_log_registra_anche_i_fallimenti(repo):
    await repo.log(executor_id=1, kind="shell", code_or_command="rm -rf /", success=False)

    voci = await repo.get_recent()
    assert voci[0].success is False


@pytest.mark.asyncio
async def test_get_recent_ordina_dal_piu_recente(repo):
    await repo.log(1, "eval", "primo", True)
    await repo.log(1, "eval", "secondo", True)

    voci = await repo.get_recent()
    assert voci[0].code_or_command == "secondo"
    assert voci[1].code_or_command == "primo"


@pytest.mark.asyncio
async def test_get_recent_rispetta_il_limite(repo):
    for i in range(10):
        await repo.log(1, "eval", f"comando {i}", True)

    voci = await repo.get_recent(limit=3)
    assert len(voci) == 3
