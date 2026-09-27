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
