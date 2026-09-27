"""
tests/test_restore_oauth_repo.py
====================================
Test di RestoreOAuthRepository contro PostgreSQL reale — verifica
anche che i token siano DAVVERO cifrati nella colonna (mai il
plaintext in chiaro).
"""

from datetime import datetime, timedelta, timezone

import pytest

from core.oauth_crypto import generate_key
from core.repositories.restore_oauth_repo import (
    STATUS_ACTIVE,
    STATUS_BANNED_BLACKLISTED,
    STATUS_KICKED_FLAGGED,
    RestoreOAuthRepository,
)

CHIAVE = generate_key()


@pytest.fixture
def repo(clean_db):
    return RestoreOAuthRepository(pool_provider=lambda: clean_db, encryption_key_provider=lambda: CHIAVE)


def _scadenza(giorni: int = 7):
    return datetime.now(timezone.utc) + timedelta(days=giorni)


@pytest.mark.asyncio
async def test_save_token_e_get_token(repo):
    await repo.save_token(100, 1, "access-abc", "refresh-xyz", _scadenza())

    token = await repo.get_token(100, 1)
    assert token.access_token == "access-abc"
    assert token.refresh_token == "refresh-xyz"
    assert token.status == STATUS_ACTIVE


@pytest.mark.asyncio
async def test_il_token_e_cifrato_nella_colonna_grezza(repo, clean_db):
    await repo.save_token(100, 1, "access-in-chiaro-segreto", "refresh-in-chiaro", _scadenza())

    riga = await clean_db.fetchrow(
        "SELECT encrypted_access_token FROM restore_oauth_tokens WHERE source_guild_id = $1 AND user_id = $2",
        100,
        1,
    )
    assert "access-in-chiaro-segreto" not in riga["encrypted_access_token"]


@pytest.mark.asyncio
async def test_get_token_inesistente_restituisce_none(repo):
    assert await repo.get_token(999, 999) is None


@pytest.mark.asyncio
async def test_mark_left_voluntarily_imposta_left_at(repo, clean_db):
    await repo.save_token(100, 1, "a", "r", _scadenza())
    await repo.mark_left_voluntarily(100, 1)

    token = await repo.get_token(100, 1)
    assert token.left_at is not None
    assert token.status == STATUS_ACTIVE


@pytest.mark.asyncio
async def test_mark_kicked_cambia_lo_stato_senza_scadenza(repo):
    await repo.save_token(100, 1, "a", "r", _scadenza())
    await repo.mark_kicked(100, 1)

    token = await repo.get_token(100, 1)
    assert token.status == STATUS_KICKED_FLAGGED
    assert token.left_at is None


@pytest.mark.asyncio
async def test_mark_banned_cambia_lo_stato_senza_scadenza(repo):
    await repo.save_token(100, 1, "a", "r", _scadenza())
    await repo.mark_banned(100, 1)

    token = await repo.get_token(100, 1)
    assert token.status == STATUS_BANNED_BLACKLISTED
    assert token.left_at is None


@pytest.mark.asyncio
async def test_delete_token(repo):
    await repo.save_token(100, 1, "a", "r", _scadenza())
    await repo.delete_token(100, 1)

    assert await repo.get_token(100, 1) is None


@pytest.mark.asyncio
async def test_purge_expired_voluntary_leaves_cancella_solo_i_vecchi(repo, clean_db):
    await repo.save_token(100, 1, "vecchio", "r", _scadenza())
    await repo.mark_left_voluntarily(100, 1)
    await clean_db.execute(
        "UPDATE restore_oauth_tokens SET left_at = now() - interval '91 days' "
        "WHERE source_guild_id = 100 AND user_id = 1"
    )

    await repo.save_token(100, 2, "recente", "r", _scadenza())
    await repo.mark_left_voluntarily(100, 2)  # uscito oggi, ancora dentro i 90gg

    cancellati = await repo.purge_expired_voluntary_leaves(retention_days=90)

    assert cancellati == 1
    assert await repo.get_token(100, 1) is None
    assert await repo.get_token(100, 2) is not None


@pytest.mark.asyncio
async def test_purge_non_tocca_kickati_o_bannati_anche_se_vecchi(repo, clean_db):
    await repo.save_token(100, 1, "a", "r", _scadenza())
    await repo.mark_kicked(100, 1)
    await repo.save_token(100, 2, "b", "r", _scadenza())
    await repo.mark_banned(100, 2)

    # Anche forzando una left_at vecchissima (caso limite), la
    # condizione status='active' esclude kickati/bannati dalla purge.
    await clean_db.execute(
        "UPDATE restore_oauth_tokens SET left_at = now() - interval '9999 days' "
        "WHERE source_guild_id = 100"
    )

    cancellati = await repo.purge_expired_voluntary_leaves(retention_days=90)

    assert cancellati == 0
    assert await repo.get_token(100, 1) is not None
    assert await repo.get_token(100, 2) is not None


@pytest.mark.asyncio
async def test_save_token_su_utente_esistente_azzera_left_at_e_stato(repo):
    await repo.save_token(100, 1, "vecchio", "r", _scadenza())
    await repo.mark_left_voluntarily(100, 1)

    # Nuovo consenso: rientra e ri-autorizza.
    await repo.save_token(100, 1, "nuovo", "r2", _scadenza())

    token = await repo.get_token(100, 1)
    assert token.access_token == "nuovo"
    assert token.left_at is None
    assert token.status == STATUS_ACTIVE
