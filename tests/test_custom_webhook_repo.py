"""
tests/test_custom_webhook_repo.py
=====================================
Test di CustomWebhookRepository contro PostgreSQL reale.
"""

import pytest

from core.custom_webhook_logic import DEFAULT_MESSAGE_TEMPLATE
from core.repositories.custom_webhook_repo import CustomWebhookRepository


@pytest.fixture
def repo(clean_db):
    return CustomWebhookRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_create_webhook_genera_un_token(repo):
    webhook = await repo.create_webhook(guild_id=100, channel_id=500, label="Monitor", created_by=1)

    assert webhook.id is not None
    assert isinstance(webhook.token, str) and len(webhook.token) > 0
    assert webhook.label == "Monitor"
    assert webhook.message_template == DEFAULT_MESSAGE_TEMPLATE


@pytest.mark.asyncio
async def test_create_webhook_con_template_personalizzato(repo):
    webhook = await repo.create_webhook(
        100, 500, "Monitor", 1, message_template="🔔 {label}: {message}"
    )
    assert webhook.message_template == "🔔 {label}: {message}"


@pytest.mark.asyncio
async def test_due_webhook_hanno_token_diversi(repo):
    primo = await repo.create_webhook(100, 500, "A", 1)
    secondo = await repo.create_webhook(100, 501, "B", 1)
    assert primo.token != secondo.token


@pytest.mark.asyncio
async def test_get_by_token_trova_il_webhook_giusto(repo):
    creato = await repo.create_webhook(100, 500, "Monitor", 1)

    trovato = await repo.get_by_token(creato.token)

    assert trovato is not None
    assert trovato.id == creato.id
    assert trovato.channel_id == 500


@pytest.mark.asyncio
async def test_get_by_token_inesistente_restituisce_none(repo):
    assert await repo.get_by_token("token-che-non-esiste") is None


@pytest.mark.asyncio
async def test_list_webhooks_filtra_per_server(repo):
    await repo.create_webhook(100, 500, "Server 100", 1)
    await repo.create_webhook(200, 600, "Server 200", 1)

    lista_100 = await repo.list_webhooks(100)

    assert len(lista_100) == 1
    assert lista_100[0].label == "Server 100"


@pytest.mark.asyncio
async def test_list_webhooks_server_senza_webhook_restituisce_lista_vuota(repo):
    assert await repo.list_webhooks(999) == []


@pytest.mark.asyncio
async def test_remove_webhook_lo_elimina(repo):
    creato = await repo.create_webhook(100, 500, "Monitor", 1)

    rimosso = await repo.remove_webhook(creato.id, guild_id=100)

    assert rimosso is True
    assert await repo.get_by_token(creato.token) is None


@pytest.mark.asyncio
async def test_remove_webhook_di_un_altro_server_fallisce(repo):
    creato = await repo.create_webhook(100, 500, "Monitor", 1)

    rimosso = await repo.remove_webhook(creato.id, guild_id=999)

    assert rimosso is False
    assert await repo.get_by_token(creato.token) is not None


@pytest.mark.asyncio
async def test_remove_webhook_inesistente_restituisce_false(repo):
    assert await repo.remove_webhook(999999, guild_id=100) is False


class TestHasAnyWebhook:
    """SEC-14: main.py usa questo per decidere se avviare il server
    webhook — nessun motivo di tenerlo in ascolto se nessun server
    ha mai creato un webhook custom."""

    @pytest.mark.asyncio
    async def test_falso_quando_non_ce_ne_sono(self, repo):
        assert await repo.has_any_webhook() is False

    @pytest.mark.asyncio
    async def test_vero_appena_ce_ne_e_uno(self, repo):
        await repo.create_webhook(100, 500, "Monitor", 1)

        assert await repo.has_any_webhook() is True

    @pytest.mark.asyncio
    async def test_resta_vero_anche_dopo_averne_rimossi_altri(self, repo):
        a = await repo.create_webhook(100, 500, "A", 1)
        await repo.create_webhook(100, 501, "B", 1)
        await repo.remove_webhook(a.id, guild_id=100)

        assert await repo.has_any_webhook() is True


class TestTokenSalvatoComeImpronta:
    """SEC-16 / 19.9: nel database c'è solo l'impronta del token, mai il token."""

    @pytest.mark.asyncio
    async def test_il_token_in_chiaro_non_e_nel_database(self, repo, clean_db):
        from core.custom_webhook_logic import hash_webhook_token

        creato = await repo.create_webhook(100, 500, "Monitor", 1)

        riga = await clean_db.fetchrow("SELECT * FROM custom_webhooks WHERE id = $1", creato.id)
        assert riga["token"] is None
        assert riga["token_hash"] == hash_webhook_token(creato.token)
        assert creato.token not in str(dict(riga))

    @pytest.mark.asyncio
    async def test_l_elenco_non_ha_il_token(self, repo):
        await repo.create_webhook(100, 500, "Monitor", 1)

        assert (await repo.list_webhooks(100))[0].token is None

    @pytest.mark.asyncio
    async def test_un_webhook_vecchio_in_chiaro_diventa_impronta_e_funziona(self, repo, clean_db):
        from core.custom_webhook_logic import hash_webhook_token
        from core.migrations import MIGRATIONS_DIR

        await clean_db.execute(
            "INSERT INTO custom_webhooks (guild_id, channel_id, token, label, message_template, created_by)"
            " VALUES (100, 500, 'vecchio-token', 'Vecchio', 'x', 1)"
        )
        await clean_db.execute((MIGRATIONS_DIR / "0450_webhook_token_hash.sql").read_text(encoding="utf-8"))

        riga = await clean_db.fetchrow("SELECT * FROM custom_webhooks WHERE label = 'Vecchio'")
        assert riga["token"] is None
        assert riga["token_hash"] == hash_webhook_token("vecchio-token")
        assert (await repo.get_by_token("vecchio-token")).label == "Vecchio"
