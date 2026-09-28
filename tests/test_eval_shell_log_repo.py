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


async def _log(repo, executor_id, kind, code_or_command, success):
    """Helper di test: registra una riga completa in un colpo solo,
    componendo le due fasi reali (log_started + mark_result) — il
    flusso di produzione in cogs/utility/owner_premium.py le usa
    separate apposta (SEC-13, vedi TestLogStartedEMarkResult sotto),
    ma qui non serve testarle ogni volta per una riga già conclusa."""
    log_id = await repo.log_started(executor_id, kind, code_or_command)
    await repo.mark_result(log_id, success)
    return log_id


@pytest.mark.asyncio
async def test_log_e_get_recent(repo):
    await _log(repo, executor_id=1, kind="eval", code_or_command="1+1", success=True)

    voci = await repo.get_recent()
    assert len(voci) == 1
    assert voci[0].kind == "eval"
    assert voci[0].code_or_command == "1+1"
    assert voci[0].success is True


@pytest.mark.asyncio
async def test_log_registra_anche_i_fallimenti(repo):
    await _log(repo, executor_id=1, kind="shell", code_or_command="rm -rf /", success=False)

    voci = await repo.get_recent()
    assert voci[0].success is False


@pytest.mark.asyncio
async def test_get_recent_ordina_dal_piu_recente(repo):
    await _log(repo, 1, "eval", "primo", True)
    await _log(repo, 1, "eval", "secondo", True)

    voci = await repo.get_recent()
    assert voci[0].code_or_command == "secondo"
    assert voci[1].code_or_command == "primo"


@pytest.mark.asyncio
async def test_get_recent_rispetta_il_limite(repo):
    for i in range(10):
        await _log(repo, 1, "eval", f"comando {i}", True)

    voci = await repo.get_recent(limit=3)
    assert len(voci) == 3


class TestLogStartedEMarkResult:
    """SEC-13 (bug minore §5): la riga va scritta PRIMA di eseguire,
    non dopo — un hang non deve lasciare zero traccia."""

    @pytest.mark.asyncio
    async def test_log_started_scrive_subito_con_esito_sconosciuto(self, repo):
        log_id = await repo.log_started(1, "eval", "while True: pass")

        voci = await repo.get_recent()
        assert len(voci) == 1
        assert voci[0].id == log_id
        assert voci[0].success is None

    @pytest.mark.asyncio
    async def test_mark_result_aggiorna_la_stessa_riga(self, repo):
        log_id = await repo.log_started(1, "shell", "echo ciao")
        await repo.mark_result(log_id, True)

        voci = await repo.get_recent()
        assert len(voci) == 1
        assert voci[0].success is True

    @pytest.mark.asyncio
    async def test_riga_mai_conclusa_resta_con_esito_sconosciuto(self, repo):
        # Simula un hang: log_started() senza mai chiamare
        # mark_result() — la riga deve comunque esistere, a
        # differenza del comportamento precedente (log() dopo
        # l'esecuzione), che non avrebbe scritto nulla.
        await repo.log_started(1, "shell", "sleep 999999")

        voci = await repo.get_recent()
        assert len(voci) == 1
        assert voci[0].success is None
