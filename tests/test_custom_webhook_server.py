"""
tests/test_custom_webhook_server.py
=======================================
Test dell'endpoint POST /webhook/<token> (SPEC.md §10.8) — repository
e canale Discord finti, nessuna vera rete verso Discord: build_app()
li accetta come parametri per questo esatto motivo (stesso pattern di
test_restore_web_server.py).
"""

from datetime import datetime, timedelta, timezone

import discord
import pytest
from aiohttp.test_utils import TestClient, TestServer

import core.custom_webhook_server as custom_webhook_server_module
from core.custom_webhook_server import build_app, start_server
from core.redacted_access_log import RedactedAccessLogger
from core.webhook_rate_tracker import WEBHOOK_RATE_LIMIT_MAX_REQUESTS, webhook_rate_tracker
from tests.support.discord_fakes import fake_text_channel


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


# ---------------------------------------------------------------------
# BUG-33: il limite conta solo le richieste accettate, la coda è
# limitata, e il controllo avviene prima della query sul database.
# ---------------------------------------------------------------------


class _OrologioFinto:
    """Sostituisce `datetime` nel modulo del server: l'ora la decide il test."""

    adesso = datetime(2026, 1, 1, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        return cls.adesso


@pytest.fixture
def orologio(monkeypatch):
    monkeypatch.setattr(_OrologioFinto, "adesso", datetime(2026, 1, 1, tzinfo=timezone.utc))
    monkeypatch.setattr(custom_webhook_server_module, "datetime", _OrologioFinto)
    return _OrologioFinto


class _RepoCheContaLeQuery:
    """Conosce un solo token valido e conta quante volte viene interrogato."""

    def __init__(self, token_valido: str = "il-token") -> None:
        self._webhook = _FakeWebhook(1, 100, 500, token_valido, "Monitor", "{message}")
        self.query = 0

    async def get_by_token(self, token):
        self.query += 1
        return self._webhook if token == self._webhook.token else None


@pytest.mark.asyncio
async def test_traffico_costante_sopra_il_limite_non_blocca_per_sempre(orologio):
    """12 richieste al minuto per 10 minuti: ne passano circa 10 al minuto, non 10 in tutto."""
    canale = _FakeChannel()
    app = build_app(webhook_repo=_RepoCheContaLeQuery(), get_channel=lambda channel_id: canale)

    async with TestClient(TestServer(app)) as client:
        for _ in range(120):
            await client.post("/webhook/il-token", json={"message": "ciao"})
            orologio.adesso += timedelta(seconds=5)

    # Mai più di 10 al minuto (100 in tutto), e non molte meno.
    assert 90 <= len(canale.sent_messages) <= 100


@pytest.mark.asyncio
async def test_le_richieste_rifiutate_non_fanno_crescere_la_coda():
    canale = _FakeChannel()
    app = build_app(webhook_repo=_RepoCheContaLeQuery(), get_channel=lambda channel_id: canale)

    async with TestClient(TestServer(app)) as client:
        for _ in range(200):
            await client.post("/webhook/il-token", json={"message": "ciao"})

    istanti_in_memoria = sum(len(coda) for coda in webhook_rate_tracker._data._data.values())
    assert istanti_in_memoria <= WEBHOOK_RATE_LIMIT_MAX_REQUESTS


@pytest.mark.asyncio
async def test_oltre_il_limite_il_database_non_viene_interrogato():
    repo = _RepoCheContaLeQuery()
    app = build_app(webhook_repo=repo, get_channel=lambda channel_id: _FakeChannel())

    async with TestClient(TestServer(app)) as client:
        for _ in range(WEBHOOK_RATE_LIMIT_MAX_REQUESTS):
            await client.post("/webhook/il-token", json={"message": "ciao"})
        query_prima = repo.query
        for _ in range(50):
            risposta = await client.post("/webhook/il-token", json={"message": "ciao"})
            assert risposta.status == 429

    assert repo.query == query_prima


@pytest.mark.asyncio
async def test_token_sconosciuti_a_raffica_dallo_stesso_ip_non_arrivano_al_database():
    from core.webhook_rate_tracker import WEBHOOK_UNKNOWN_TOKEN_LIMIT_PER_IP

    repo = _RepoCheContaLeQuery()
    app = build_app(webhook_repo=repo, get_channel=lambda channel_id: _FakeChannel())

    async with TestClient(TestServer(app)) as client:
        stati = [
            (
                await client.post(
                    f"/webhook/token-a-caso-{i}",
                    json={"message": "x"},
                    headers={"X-Forwarded-For": "203.0.113.7"},
                )
            ).status
            for i in range(100)
        ]

    assert repo.query == WEBHOOK_UNKNOWN_TOKEN_LIMIT_PER_IP
    assert stati.count(404) == WEBHOOK_UNKNOWN_TOKEN_LIMIT_PER_IP
    assert stati.count(429) == 100 - WEBHOOK_UNKNOWN_TOKEN_LIMIT_PER_IP


def _richiesta_da(ip_connessione: str, inoltrati: str | None = None):
    from unittest.mock import Mock

    from aiohttp.test_utils import make_mocked_request

    trasporto = Mock()
    trasporto.get_extra_info.return_value = (ip_connessione, 12345)
    headers = {"X-Forwarded-For": inoltrati} if inoltrati is not None else {}
    return make_mocked_request("POST", "/webhook/x", headers=headers, transport=trasporto)


def test_ip_del_client_connessione_diretta_usa_l_ip_della_connessione():
    from core.custom_webhook_server import _ip_del_client

    # Senza proxy locale l'header lo scrive il client: non ci si fida.
    assert _ip_del_client(_richiesta_da("203.0.113.7", inoltrati="10.0.0.1")) == "203.0.113.7"


def test_ip_del_client_dietro_il_proxy_locale_usa_l_ultimo_inoltrato():
    from core.custom_webhook_server import _ip_del_client

    richiesta = _richiesta_da("127.0.0.1", inoltrati="198.51.100.99, 203.0.113.7")
    assert _ip_del_client(richiesta) == "203.0.113.7"


def test_ip_del_client_dietro_il_proxy_locale_senza_header_e_sconosciuto():
    from core.custom_webhook_server import _ip_del_client

    # Meglio nessun limite per IP che un limite unico condiviso da tutti.
    assert _ip_del_client(_richiesta_da("127.0.0.1")) is None


@pytest.mark.asyncio
async def test_dietro_il_proxy_locale_il_limite_per_ip_usa_l_ip_inoltrato():
    """
    Con il reverse proxy sulla stessa macchina tutte le richieste
    arrivano da 127.0.0.1: i tentativi a vuoto di un client non devono
    bloccare un altro client.
    """
    from core.webhook_rate_tracker import WEBHOOK_UNKNOWN_TOKEN_LIMIT_PER_IP

    canale = _FakeChannel()
    app = build_app(webhook_repo=_RepoCheContaLeQuery(), get_channel=lambda channel_id: canale)

    async with TestClient(TestServer(app)) as client:
        for i in range(WEBHOOK_UNKNOWN_TOKEN_LIMIT_PER_IP + 5):
            await client.post(
                f"/webhook/token-a-caso-{i}",
                json={"message": "x"},
                # Il client può scrivere quello che vuole all'inizio:
                # conta l'ultimo indirizzo, aggiunto dal proxy.
                headers={"X-Forwarded-For": "198.51.100.99, 203.0.113.7"},
            )
        bloccato = await client.post(
            "/webhook/il-token", json={"message": "x"}, headers={"X-Forwarded-For": "203.0.113.7"}
        )
        altro_client = await client.post(
            "/webhook/il-token", json={"message": "ciao"}, headers={"X-Forwarded-For": "198.51.100.99"}
        )

    assert bloccato.status == 429
    assert altro_client.status == 200
    assert canale.sent_messages == ["ciao"]


# ---------------------------------------------------------------------
# BUG-33: l'invio su Discord non deve mai finire in un 500 non gestito.
# ---------------------------------------------------------------------


def _app_con_canale_autospec(template: str):
    canale = fake_text_channel(500)
    webhook = _FakeWebhook(1, 100, 500, "il-token", "Monitor", template)
    return build_app(webhook_repo=_FakeWebhookRepo(webhook), get_channel=lambda channel_id: canale), canale


class _RispostaHttpFinta:
    status = 403
    reason = "Forbidden"


@pytest.mark.asyncio
async def test_messaggio_vuoto_restituisce_422_senza_inviare():
    app, canale = _app_con_canale_autospec("{message}")

    async with TestClient(TestServer(app)) as client:
        risposta = await client.post("/webhook/il-token", json={})
        corpo = await risposta.json()

    assert risposta.status == 422
    assert "error" in corpo
    canale.send.assert_not_called()


@pytest.mark.asyncio
async def test_bot_senza_permesso_nel_canale_restituisce_502_json():
    app, canale = _app_con_canale_autospec("{message}")
    canale.send.side_effect = discord.Forbidden(_RispostaHttpFinta(), "Missing Permissions")

    async with TestClient(TestServer(app)) as client:
        risposta = await client.post("/webhook/il-token", json={"message": "ciao"})
        corpo = await risposta.json()

    assert risposta.status == 502
    assert "error" in corpo

