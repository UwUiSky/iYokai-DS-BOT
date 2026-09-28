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

from core.custom_webhook_server import build_app, start_server
from core.redacted_access_log import RedactedAccessLogger
from core.webhook_rate_tracker import webhook_rate_tracker


@pytest.fixture(autouse=True)
def _svuota_il_limite_di_frequenza():
    """webhook_rate_tracker è un singleton condiviso da tutto il
    processo (SEC-14) — senza svuotarlo tra un test e l'altro, le
    richieste con lo stesso token "il-token" usato da più test si
    sommerebbero e farebbero scattare il 429 nei test che non
    stanno testando il limite."""
    webhook_rate_tracker._data.clear()
    yield
    webhook_rate_tracker._data.clear()


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


class TestLimiteDiFrequenzaPerToken:
    """SEC-14: senza un limite, un token compromesso (o un servizio
    terzo mal configurato) può inondare il canale Discord di
    destinazione senza nessun freno."""

    @pytest.mark.asyncio
    async def test_oltre_il_limite_risponde_429(self):
        from core.webhook_rate_tracker import WEBHOOK_RATE_LIMIT_MAX_REQUESTS

        canale = _FakeChannel()
        webhook = _FakeWebhook(1, 100, 500, "il-token", "Monitor", "{message}")
        app = _build_app_con_canale(webhook, canale)

        async with TestClient(TestServer(app)) as client:
            for _ in range(WEBHOOK_RATE_LIMIT_MAX_REQUESTS):
                risposta = await client.post("/webhook/il-token", json={"message": "ciao"})
                assert risposta.status == 200

            risposta_in_piu = await client.post("/webhook/il-token", json={"message": "ciao"})

        assert risposta_in_piu.status == 429
        assert len(canale.sent_messages) == WEBHOOK_RATE_LIMIT_MAX_REQUESTS

    @pytest.mark.asyncio
    async def test_un_token_diverso_non_risente_del_limite_di_un_altro(self):
        from core.webhook_rate_tracker import WEBHOOK_RATE_LIMIT_MAX_REQUESTS

        canale = _FakeChannel()

        async def get_channel(channel_id):
            return canale

        def _fake_repo():
            class _Repo:
                async def get_by_token(self, token):
                    return _FakeWebhook(1, 100, 500, token, "Monitor", "{message}")

            return _Repo()

        app = build_app(webhook_repo=_fake_repo(), get_channel=lambda channel_id: canale)

        async with TestClient(TestServer(app)) as client:
            for _ in range(WEBHOOK_RATE_LIMIT_MAX_REQUESTS):
                await client.post("/webhook/token-a", json={"message": "ciao"})

            risposta_altro_token = await client.post("/webhook/token-b", json={"message": "ciao"})

        assert risposta_altro_token.status == 200


@pytest.mark.asyncio
async def test_start_server_usa_l_access_log_redatto():
    # SEC-9: il token del webhook è nel PERCORSO dell'URL, non va mai
    # scritto per intero nei log del server.
    app = build_app(webhook_repo=_FakeWebhookRepo(), get_channel=lambda channel_id: None)

    runner = await start_server(app, host="127.0.0.1", port=0)
    try:
        assert runner._kwargs["access_log_class"] is RedactedAccessLogger
    finally:
        await runner.cleanup()
