"""
tests/test_automod_advanced_repo.py
=======================================
Test di persistenza di core.repositories.automod_advanced_repo
(SPEC.md §6.3-§6.14) contro Postgres reale — stesso schema di
tests/test_automod_repo.py: istanza dedicata del repository con
`pool_provider=lambda: clean_db`, non il singleton globale.
"""

import pytest

from core.automod_advanced_logic import AntiLinkConfig, AutomodAdvancedConfig, RateFilterConfig
from core.repositories.automod_advanced_repo import (
    AutomodAdvancedRepository,
    AutomodAdvancedSettings,
    DEFAULT_MUTE_DURATION_SECONDS,
)


@pytest.fixture
def repo(clean_db):
    return AutomodAdvancedRepository(pool_provider=lambda: clean_db)


class TestGetSettings:
    @pytest.mark.asyncio
    async def test_server_mai_configurato_restituisce_default(self, repo):
        settings = await repo.get_settings(100)
        assert settings.config.anti_link.mode == "off"
        assert settings.exempt_channel_ids == ()
        assert settings.mute_duration_seconds == DEFAULT_MUTE_DURATION_SECONDS
        assert settings.log_channel_id is None


class TestSaveAndReload:
    @pytest.mark.asyncio
    async def test_configurazione_completa_sopravvive_al_round_trip(self, repo):
        originale = AutomodAdvancedSettings(
            guild_id=100,
            config=AutomodAdvancedConfig(
                anti_link=AntiLinkConfig(mode="blacklist", blacklist=("cattivo.com",)),
                anti_spam_messages=RateFilterConfig(enabled=True, max_count=4, window_seconds=8),
            ),
            exempt_channel_ids=(111, 222),
            exempt_role_ids=(333,),
            actions={"anti_link": ("delete", "warn")},
            mute_duration_seconds=1200,
            log_channel_id=444,
        )
        await repo.save_settings(originale)

        ricaricato = await repo.get_settings(100)

        assert ricaricato.config.anti_link.mode == "blacklist"
        assert ricaricato.config.anti_link.blacklist == ("cattivo.com",)
        assert ricaricato.config.anti_spam_messages.enabled is True
        assert ricaricato.config.anti_spam_messages.max_count == 4
        assert ricaricato.exempt_channel_ids == (111, 222)
        assert ricaricato.exempt_role_ids == (333,)
        assert ricaricato.actions == {"anti_link": ("delete", "warn")}
        assert ricaricato.mute_duration_seconds == 1200
        assert ricaricato.log_channel_id == 444

    @pytest.mark.asyncio
    async def test_un_secondo_save_sovrascrive_il_primo(self, repo):
        primo = AutomodAdvancedSettings(
            guild_id=100,
            config=AutomodAdvancedConfig(),
            exempt_channel_ids=(1,),
            exempt_role_ids=(),
            actions={},
            mute_duration_seconds=600,
            log_channel_id=None,
        )
        await repo.save_settings(primo)

        secondo = AutomodAdvancedSettings(
            guild_id=100,
            config=AutomodAdvancedConfig(),
            exempt_channel_ids=(2, 3),
            exempt_role_ids=(),
            actions={},
            mute_duration_seconds=600,
            log_channel_id=None,
        )
        await repo.save_settings(secondo)

        risultato = await repo.get_settings(100)
        assert risultato.exempt_channel_ids == (2, 3)


class TestActionLog:
    @pytest.mark.asyncio
    async def test_log_action_e_get_recent_actions(self, repo):
        await repo.log_action(100, 500, 600, "anti_caps", ("delete", "warn"), "TUTTO MAIUSCOLO")

        recenti = await repo.get_recent_actions(100)

        assert len(recenti) == 1
        assert recenti[0]["user_id"] == 500
        assert recenti[0]["violation"] == "anti_caps"
        assert recenti[0]["actions_taken"] == ("delete", "warn")

    @pytest.mark.asyncio
    async def test_get_recent_actions_rispetta_il_limite(self, repo):
        for i in range(5):
            await repo.log_action(100, i, 1, "anti_zalgo", ("delete",), None)

        recenti = await repo.get_recent_actions(100, limit=2)

        assert len(recenti) == 2

    @pytest.mark.asyncio
    async def test_get_recent_actions_scoped_per_server(self, repo):
        await repo.log_action(100, 1, 1, "anti_zalgo", ("delete",), None)
        await repo.log_action(200, 1, 1, "anti_zalgo", ("delete",), None)

        recenti = await repo.get_recent_actions(100)

        assert len(recenti) == 1
