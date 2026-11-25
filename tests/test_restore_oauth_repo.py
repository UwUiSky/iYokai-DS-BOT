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
    RestoreOAuthToken,
)

CHIAVE = generate_key()


class TestRestoreOAuthTokenReprNonSvelaISegreti:
    """SEC-16: access_token/refresh_token (decifrati in memoria dopo
    la lettura dal repository) non devono comparire in un repr()
    dell'oggetto."""

    def test_repr_non_contiene_i_token(self):
        token = RestoreOAuthToken(
            source_guild_id=100,
            user_id=1,
            access_token="access-segreto",
            refresh_token="refresh-segreto",
            expires_at=datetime.now(timezone.utc),
            status=STATUS_ACTIVE,
            granted_at=datetime.now(timezone.utc),
            left_at=None,
        )

        testo = repr(token)

        assert "access-segreto" not in testo
        assert "refresh-segreto" not in testo


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
async def test_la_pulizia_del_registro_toglie_i_token_di_chi_e_uscito_da_91_giorni(repo, clean_db):
    """La promessa dei 90 giorni (SPEC §11.11) la mantiene la pulizia generale del registro dei dati."""
    from core import retention_worker

    await repo.save_token(100, 1, "vecchio", "r", _scadenza())
    await repo.mark_left_voluntarily(100, 1)
    await clean_db.execute(
        "UPDATE restore_oauth_tokens SET left_at = now() - interval '91 days' "
        "WHERE source_guild_id = 100 AND user_id = 1"
    )
    await repo.save_token(100, 2, "recente", "r", _scadenza())
    await repo.mark_left_voluntarily(100, 2)  # uscito oggi, ancora dentro i 90 giorni
    await repo.save_token(100, 3, "ancora_dentro", "r", _scadenza())  # non è mai uscito

    tolte = await retention_worker.pulisci_scaduti(clean_db)

    assert tolte.get("restore_oauth_tokens") == 1
    assert await repo.get_token(100, 1) is None
    assert await repo.get_token(100, 2) is not None
    assert await repo.get_token(100, 3) is not None


@pytest.mark.asyncio
async def test_la_pulizia_non_tocca_kickati_o_bannati_anche_se_vecchi(repo, clean_db):
    from core import retention_worker

    await repo.save_token(100, 1, "a", "r", _scadenza())
    await repo.mark_kicked(100, 1)
    await repo.save_token(100, 2, "b", "r", _scadenza())
    await repo.mark_banned(100, 2)
    # Anche forzando una left_at vecchissima (caso limite), la condizione status='active' li esclude.
    await clean_db.execute(
        "UPDATE restore_oauth_tokens SET left_at = now() - interval '9999 days' WHERE source_guild_id = 100"
    )

    assert "restore_oauth_tokens" not in await retention_worker.pulisci_scaduti(clean_db)
    assert await repo.get_token(100, 1) is not None
    assert await repo.get_token(100, 2) is not None


def test_il_registro_dichiara_i_90_giorni_per_i_token_di_ripristino():
    """Cricchetto: la scadenza sta nel registro (da lì la applica la pulizia e la legge l'informativa privacy)."""
    from core.data_registry import REGISTRO

    voce = next(t for t in REGISTRO if t.nome == "restore_oauth_tokens")
    assert voce.scadenza is not None and voce.scadenza.giorni == 90 and voce.scadenza.colonna == "left_at"
    assert "status = 'active'" in voce.scadenza.solo_se
    # L'informativa privacy nasce dal registro: dice i 90 giorni e che è un token guilds.join.
    from core.web_panel_logic import voci_privacy

    riga = next(v for v in voci_privacy(REGISTRO, 90) if "guilds.join" in v["cosa"])
    assert riga["durata"] == "tolto dopo 90 giorni"


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


# ---------------------------------------------------------------------
# SEC-19: un nuovo consenso non cancella un ban.
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_token_su_utente_bannato_non_scrive_e_restituisce_false(repo):
    assert await repo.save_token(100, 1, "vecchio", "r", _scadenza()) is True
    await repo.mark_banned(100, 1)

    salvato = await repo.save_token(100, 1, "nuovo", "r2", _scadenza())

    assert salvato is False
    token = await repo.get_token(100, 1)
    assert token.status == STATUS_BANNED_BLACKLISTED
    assert token.access_token == "vecchio"


@pytest.mark.asyncio
async def test_save_token_su_utente_kickato_lo_riporta_attivo(repo):
    await repo.save_token(100, 1, "vecchio", "r", _scadenza())
    await repo.mark_kicked(100, 1)

    assert await repo.save_token(100, 1, "nuovo", "r2", _scadenza()) is True
    assert (await repo.get_token(100, 1)).status == STATUS_ACTIVE


@pytest.mark.asyncio
# BKP-040
async def test_il_ripristino_non_raccoglie_indirizzi_ip(clean_db):
    """BKP-040: nessuna colonna di IP o paese nelle tabelle di restore e backup (D108: regole per paese/VPN restano alla verifica)."""
    colonne = await clean_db.fetch(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND (table_name LIKE 'restore\\_%' OR table_name LIKE 'backup\\_%')"
    )
    sospette = [(r["table_name"], r["column_name"]) for r in colonne
                if r["column_name"] in ("ip", "ip_address", "ip_hash", "paese", "country", "asn")]
    assert sospette == []
