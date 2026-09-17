"""
tests/test_verify_repo.py
============================
Test di VerifyRepository contro PostgreSQL reale.
"""

import pytest

from core.repositories.verify_repo import VerifyRepository, DEFAULT_METHOD


@pytest.fixture
def repo(clean_db):
    return VerifyRepository(pool_provider=lambda: clean_db)


# ====================================================================
# Configurazione
# ====================================================================
@pytest.mark.asyncio
async def test_config_di_default(repo):
    config = await repo.get_config(100)
    assert config.method == DEFAULT_METHOD
    assert config.verified_role_id is None
    assert config.min_account_age_days == 0
    assert config.min_mutual_servers == 0
    assert config.captcha_enabled is False


@pytest.mark.asyncio
async def test_set_e_get_config(repo):
    await repo.set_config(
        guild_id=100,
        method="reaction",
        verified_role_id=555,
        min_account_age_days=7,
        min_mutual_servers=2,
        captcha_enabled=True,
        log_channel_id=999,
    )
    config = await repo.get_config(100)
    assert config.method == "reaction"
    assert config.verified_role_id == 555
    assert config.min_account_age_days == 7
    assert config.min_mutual_servers == 2
    assert config.captcha_enabled is True
    assert config.log_channel_id == 999


@pytest.mark.asyncio
async def test_set_config_sovrascrive(repo):
    await repo.set_config(100, "button", 1, 0, 0, False, None)
    await repo.set_config(100, "reaction", 2, 5, 3, True, 42)
    config = await repo.get_config(100)
    assert config.method == "reaction"
    assert config.verified_role_id == 2


@pytest.mark.asyncio
async def test_set_panel_message(repo):
    await repo.set_panel_message(100, channel_id=111, message_id=222)
    config = await repo.get_config(100)
    assert config.panel_channel_id == 111
    assert config.panel_message_id == 222


@pytest.mark.asyncio
async def test_set_panel_message_non_sovrascrive_config_esistente(repo):
    await repo.set_config(100, "button", 555, 7, 2, True, 999)
    await repo.set_panel_message(100, channel_id=111, message_id=222)
    config = await repo.get_config(100)
    # I campi impostati da set_config devono restare intatti.
    assert config.verified_role_id == 555
    assert config.min_account_age_days == 7
    assert config.panel_channel_id == 111


# ====================================================================
# Whitelist
# ====================================================================
@pytest.mark.asyncio
async def test_whitelist_default_false(repo):
    assert await repo.is_whitelisted(100, 1) is False


@pytest.mark.asyncio
async def test_add_e_check_whitelist(repo):
    await repo.add_whitelist(100, 1)
    assert await repo.is_whitelisted(100, 1) is True


@pytest.mark.asyncio
async def test_add_whitelist_due_volte_non_fallisce(repo):
    await repo.add_whitelist(100, 1)
    await repo.add_whitelist(100, 1)
    assert await repo.is_whitelisted(100, 1) is True


@pytest.mark.asyncio
async def test_remove_whitelist(repo):
    await repo.add_whitelist(100, 1)
    await repo.remove_whitelist(100, 1)
    assert await repo.is_whitelisted(100, 1) is False


@pytest.mark.asyncio
async def test_whitelist_non_mischia_server(repo):
    await repo.add_whitelist(100, 1)
    assert await repo.is_whitelisted(200, 1) is False


# ====================================================================
# Blacklist
# ====================================================================
@pytest.mark.asyncio
async def test_blacklist_default_false(repo):
    assert await repo.is_blacklisted(100, 1) is False


@pytest.mark.asyncio
async def test_add_e_check_blacklist(repo):
    await repo.add_blacklist(100, 1)
    assert await repo.is_blacklisted(100, 1) is True


@pytest.mark.asyncio
async def test_remove_blacklist(repo):
    await repo.add_blacklist(100, 1)
    await repo.remove_blacklist(100, 1)
    assert await repo.is_blacklisted(100, 1) is False


@pytest.mark.asyncio
async def test_whitelist_e_blacklist_sono_indipendenti(repo):
    await repo.add_whitelist(100, 1)
    await repo.add_blacklist(100, 1)
    # Entrambe possono essere vere insieme a livello di dati — è la
    # LOGICA (decide_verify_outcome, core/verify_logic.py) a decidere
    # che la blacklist vince, non un vincolo del database.
    assert await repo.is_whitelisted(100, 1) is True
    assert await repo.is_blacklisted(100, 1) is True


# ====================================================================
# Log tentativi
# ====================================================================
@pytest.mark.asyncio
async def test_log_attempt_e_lettura(repo):
    await repo.log_attempt(100, 1, success=True, reason="All checks passed.")
    tentativi = await repo.get_recent_attempts(100, 1)
    assert len(tentativi) == 1
    success, reason, _ = tentativi[0]
    assert success is True
    assert reason == "All checks passed."


@pytest.mark.asyncio
async def test_get_recent_attempts_ordina_dal_piu_recente(repo):
    await repo.log_attempt(100, 1, success=False, reason="primo")
    await repo.log_attempt(100, 1, success=False, reason="secondo")
    await repo.log_attempt(100, 1, success=True, reason="terzo")

    tentativi = await repo.get_recent_attempts(100, 1)
    ragioni = [t[1] for t in tentativi]
    assert ragioni == ["terzo", "secondo", "primo"]


@pytest.mark.asyncio
async def test_get_recent_attempts_rispetta_il_limite(repo):
    for i in range(5):
        await repo.log_attempt(100, 1, success=True, reason=f"tentativo {i}")

    tentativi = await repo.get_recent_attempts(100, 1, limit=2)
    assert len(tentativi) == 2


@pytest.mark.asyncio
async def test_get_recent_attempts_non_mischia_utenti(repo):
    await repo.log_attempt(100, 1, success=True, reason="utente 1")
    await repo.log_attempt(100, 2, success=True, reason="utente 2")

    tentativi_utente_1 = await repo.get_recent_attempts(100, 1)
    assert len(tentativi_utente_1) == 1
    assert tentativi_utente_1[0][1] == "utente 1"
