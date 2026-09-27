"""
tests/test_custom_webhook_server.py
=======================================
Test dell'endpoint POST /webhook/<token> (SPEC.md §10.8) — repository
e canale Discord finti, nessuna vera rete verso Discord: build_app()
li accetta come parametri per questo esatto motivo (stesso pattern di
test_restore_web_server.py).
"""

import pytest
from aiohttp.test_utils import TestClient, TestServer

from core.custom_webhook_server import build_app


class _FakeWebhook:
    def __init__(self, id, guild_id, channel_id, token, label, message_template):
        self.id = id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.token = token
        self.label = label
        self.message_template = message_template


class _FakeWebhookRepo:
    def __init__(self, webhook=None):
        self._webhook = webhook

    async def get_by_token(self, token):
        if self._webhook is not None and self._webhook.token == token:
            return self._webhook
        return None


class _FakeChannel:
    def __init__(self):
        self.sent_messages: list[str] = []

    async def send(self, content: str) -> None:
        self.sent_messages.append(content)


def _build_app_con_canale(webhook, canale):
    def get_channel(channel_id):
        if canale is not None and webhook is not None and channel_id == webhook.channel_id:
            return canale
        return None

    return build_app(webhook_repo=_FakeWebhookRepo(webhook), get_channel=get_channel)


@pytest.mark.asyncio
async def test_webhook_valido_pubblica_nel_canale():
    canale = _FakeChannel()
    webhook = _FakeWebhook(1, 100, 500, "il-token", "Monitor", "📩 **{label}**: {message}")
    app = _build_app_con_canale(webhook, canale)

    async with TestClient(TestServer(app)) as client:
        risposta = await client.post(
            "/webhook/il-token", json={"message": "Il server è tornato online"}
        )

    assert risposta.status == 200
    assert canale.sent_messages == ["📩 **Monitor**: Il server è tornato online"]


@pytest.mark.asyncio
async def test_token_inesistente_restituisce_404():
    app = _build_app_con_canale(None, None)

    async with TestClient(TestServer(app)) as client:
        risposta = await client.post("/webhook/token-sbagliato", json={"message": "ciao"})

    assert risposta.status == 404


@pytest.mark.asyncio
async def test_corpo_non_json_restituisce_400():
    canale = _FakeChannel()
    webhook = _FakeWebhook(1, 100, 500, "il-token", "Monitor", "{message}")
    app = _build_app_con_canale(webhook, canale)

    async with TestClient(TestServer(app)) as client:
        risposta = await client.post(
            "/webhook/il-token", data="questo non è JSON", headers={"Content-Type": "text/plain"}
        )

    assert risposta.status == 400
    assert canale.sent_messages == []


@pytest.mark.asyncio
async def test_canale_non_raggiungibile_restituisce_502():
    webhook = _FakeWebhook(1, 100, 500, "il-token", "Monitor", "{message}")
    # get_channel restituisce sempre None: il canale non esiste più,
    # o il bot non ci ha più accesso.
    app = build_app(webhook_repo=_FakeWebhookRepo(webhook), get_channel=lambda channel_id: None)

    async with TestClient(TestServer(app)) as client:
        risposta = await client.post("/webhook/il-token", json={"message": "ciao"})

    assert risposta.status == 502


@pytest.mark.asyncio
async def test_payload_vuoto_non_solleva():
    canale = _FakeChannel()
    webhook = _FakeWebhook(1, 100, 500, "il-token", "Monitor", "📩 **{label}**")
    app = _build_app_con_canale(webhook, canale)

    async with TestClient(TestServer(app)) as client:
        risposta = await client.post("/webhook/il-token", json={})

    assert risposta.status == 200
    assert canale.sent_messages == ["📩 **Monitor**"]
