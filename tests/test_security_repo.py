"""
tests/test_security_repo.py
===============================
Test di persistenza di core.repositories.security_repo (SPEC.md
§7.1/§7.2) — stesso schema di tests/test_automod_advanced_repo.py:
istanza dedicata del repository con `pool_provider=lambda: clean_db`.
"""

import pytest

from core.repositories.security_repo import SecurityRepository, SecuritySettings
from core.security_logic import AntiNukeConfig, AntiRaidConfig


@pytest.fixture
def repo(clean_db):
    return SecurityRepository(pool_provider=lambda: clean_db)


class TestGetSettings:
    @pytest.mark.asyncio
    async def test_server_mai_configurato_restituisce_default(self, repo):
        settings = await repo.get_settings(100)
        assert settings.anti_raid.enabled is False
        assert settings.anti_nuke.enabled is False
        assert settings.quarantine_role_id is None
        assert settings.alert_channel_id is None


class TestSaveAndReload:
    @pytest.mark.asyncio
    async def test_configurazione_completa_sopravvive_al_round_trip(self, repo):
        originale = SecuritySettings(
            guild_id=100,
            anti_raid=AntiRaidConfig(enabled=True, join_rate_max=7, min_account_age_seconds=3600),
            anti_nuke=AntiNukeConfig(enabled=True, channel_max=2, trusted_ids=(1, 2, 3)),
            quarantine_role_id=111,
            alert_channel_id=222,
        )
        await repo.save_settings(originale)

        ricaricato = await repo.get_settings(100)

        assert ricaricato.anti_raid.enabled is True
        assert ricaricato.anti_raid.join_rate_max == 7
        assert ricaricato.anti_raid.min_account_age_seconds == 3600
        assert ricaricato.anti_nuke.enabled is True
        assert ricaricato.anti_nuke.channel_max == 2
        assert ricaricato.anti_nuke.trusted_ids == (1, 2, 3)
        assert ricaricato.quarantine_role_id == 111
        assert ricaricato.alert_channel_id == 222

    @pytest.mark.asyncio
    async def test_un_secondo_save_sovrascrive_il_primo(self, repo):
        await repo.save_settings(
            SecuritySettings(
                guild_id=100,
                anti_raid=AntiRaidConfig(),
                anti_nuke=AntiNukeConfig(trusted_ids=(1,)),
                quarantine_role_id=None,
                alert_channel_id=None,
            )
        )
        await repo.save_settings(
            SecuritySettings(
                guild_id=100,
                anti_raid=AntiRaidConfig(),
                anti_nuke=AntiNukeConfig(trusted_ids=(2, 3)),
                quarantine_role_id=None,
                alert_channel_id=None,
            )
        )

        risultato = await repo.get_settings(100)
        assert risultato.anti_nuke.trusted_ids == (2, 3)


class TestActionLog:
    @pytest.mark.asyncio
    async def test_log_action_e_get_recent_actions(self, repo):
        await repo.log_action(100, "nuke_channel", 500, "3 canali cancellati in 10s")

        recenti = await repo.get_recent_actions(100)

        assert len(recenti) == 1
        assert recenti[0]["category"] == "nuke_channel"
        assert recenti[0]["actor_id"] == 500

    @pytest.mark.asyncio
    async def test_get_recent_actions_rispetta_il_limite(self, repo):
        for i in range(5):
            await repo.log_action(100, "raid_join", i, None)

        recenti = await repo.get_recent_actions(100, limit=2)
        assert len(recenti) == 2

    @pytest.mark.asyncio
    async def test_get_recent_actions_scoped_per_server(self, repo):
        await repo.log_action(100, "raid_join", 1, None)
        await repo.log_action(200, "raid_join", 1, None)

        recenti = await repo.get_recent_actions(100)
        assert len(recenti) == 1
