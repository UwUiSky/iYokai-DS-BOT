"""
tests/test_global_ban_repo.py
=================================
Test di persistenza di core.repositories.global_ban_repo (SPEC.md
§7.3) — stesso schema di tests/test_security_repo.py.
"""

import pytest

from core.repositories.global_ban_repo import GlobalBanRepository


@pytest.fixture
def repo(clean_db):
    return GlobalBanRepository(pool_provider=lambda: clean_db)


class TestLogPropagation:
    @pytest.mark.asyncio
    async def test_log_propagation_e_get_recent_outgoing(self, repo):
        await repo.log_propagation(100, 200, 999, "Spam trap triggered")

        outgoing = await repo.get_recent_outgoing(100)

        assert len(outgoing) == 1
        assert outgoing[0].source_guild_id == 100
        assert outgoing[0].target_guild_id == 200
        assert outgoing[0].user_id == 999
        assert outgoing[0].reason == "Spam trap triggered"

    @pytest.mark.asyncio
    async def test_get_recent_incoming_scoped_sul_target(self, repo):
        await repo.log_propagation(100, 200, 999, "motivo")

        incoming = await repo.get_recent_incoming(200)

        assert len(incoming) == 1
        assert incoming[0].source_guild_id == 100
        assert incoming[0].target_guild_id == 200

    @pytest.mark.asyncio
    async def test_outgoing_non_include_le_voci_di_un_altro_server(self, repo):
        await repo.log_propagation(100, 200, 999, "motivo")
        await repo.log_propagation(300, 400, 111, "altro motivo")

        outgoing = await repo.get_recent_outgoing(100)
        assert len(outgoing) == 1

    @pytest.mark.asyncio
    async def test_get_recent_outgoing_rispetta_il_limite(self, repo):
        for i in range(5):
            await repo.log_propagation(100, 200 + i, 999, None)

        outgoing = await repo.get_recent_outgoing(100, limit=2)
        assert len(outgoing) == 2

    @pytest.mark.asyncio
    async def test_nessuna_propagazione_restituisce_liste_vuote(self, repo):
        assert await repo.get_recent_outgoing(999) == []
        assert await repo.get_recent_incoming(999) == []
