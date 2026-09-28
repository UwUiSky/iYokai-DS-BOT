"""
tests/test_restore_web_server.py
====================================
Test dell'endpoint /oauth/callback (SPEC.md §11.11) — dipendenze
tutte finte (orchestrator, oauth_repo, verify_repo_), nessuna vera
rete verso Discord: build_app() le accetta come parametri per
questo esatto motivo.
"""

import pytest
from aiohttp.test_utils import TestClient, TestServer

from core.oauth_crypto import generate_key
from core.restore_oauth_logic import encode_state, RestoreState
from core.restore_orchestrator import ExchangedToken
from core.restore_web_server import build_app

CHIAVE = generate_key()

# Utente "autenticato" di default nei test: SEC-3 lo scopre chiamando
# fetch_current_user con l'access_token, MAI dallo state.
UTENTE_AUTENTICATO_DEFAULT = 999


class _FakeOrchestrator:
    def __init__(
        self, token=None, join_riesce: bool = True, utente_autenticato: int | None = UTENTE_AUTENTICATO_DEFAULT
    ) -> None:
        self._token = token
        self._join_riesce = join_riesce
        self._utente_autenticato = utente_autenticato
        self.chiamate_join: list[tuple] = []
        self.chiamate_assign_role: list[tuple] = []

    async def exchange_code_for_token(self, **kwargs):
        return self._token

    async def fetch_current_user(self, access_token: str):
        return self._utente_autenticato

    async def join_user_via_oauth(self, bot_token, guild_id, user_id, access_token):
        self.chiamate_join.append((guild_id, user_id))
        return self._join_riesce

    async def assign_role(self, bot_token, guild_id, user_id, role_id):
        self.chiamate_assign_role.append((guild_id, user_id, role_id))
        return True


class _FakeOAuthRepo:
    def __init__(self) -> None:
        self.salvati: list[tuple] = []

    async def save_token(self, source_guild_id, user_id, access_token, refresh_token, expires_at):
        self.salvati.append((source_guild_id, user_id, access_token))


class _FakeVerifyConfig:
    def __init__(self, verified_role_id):
        self.verified_role_id = verified_role_id


class _FakeVerifyRepo:
    def __init__(self, verified_role_id=None) -> None:
        self._verified_role_id = verified_role_id

    async def get_config(self, guild_id: int):
        return _FakeVerifyConfig(self._verified_role_id)


def _url_di_callback(source_guild_id, target_guild_id, code="il-code"):
    state = encode_state(RestoreState(source_guild_id, target_guild_id), CHIAVE)
    return f"/oauth/callback?code={code}&state={state}"


@pytest.mark.asyncio
async def test_callback_valido_aggiunge_l_utente_e_salva_il_token():
    orchestrator = _FakeOrchestrator(
        token=ExchangedToken(access_token="a", refresh_token="r", expires_at=None)
    )
    oauth_repo = _FakeOAuthRepo()
    app = build_app(
        orchestrator=orchestrator,
        oauth_repo=oauth_repo,
        verify_repo_=_FakeVerifyRepo(verified_role_id=None),
        client_id="1",
        client_secret="s",
        redirect_uri="https://esempio.com/cb",
        bot_token="bot-token",
        oauth_encryption_key=CHIAVE,
    )
    async with TestClient(TestServer(app)) as client:
        risposta = await client.get(_url_di_callback(100, 200))

    assert risposta.status == 200
    assert oauth_repo.salvati == [(100, 999, "a")]
    assert orchestrator.chiamate_join == [(200, 999)]


@pytest.mark.asyncio
async def test_callback_assegna_il_ruolo_verificato_se_configurato():
    orchestrator = _FakeOrchestrator(
        token=ExchangedToken(access_token="a", refresh_token="r", expires_at=None)
    )
    app = build_app(
        orchestrator=orchestrator,
        oauth_repo=_FakeOAuthRepo(),
        verify_repo_=_FakeVerifyRepo(verified_role_id=555),
        client_id="1",
        client_secret="s",
        redirect_uri="https://esempio.com/cb",
        bot_token="bot-token",
        oauth_encryption_key=CHIAVE,
    )
    async with TestClient(TestServer(app)) as client:
        await client.get(_url_di_callback(100, 200))

    assert orchestrator.chiamate_assign_role == [(200, 999, 555)]


@pytest.mark.asyncio
async def test_callback_consent_only_non_chiama_join():
    orchestrator = _FakeOrchestrator(
        token=ExchangedToken(access_token="a", refresh_token="r", expires_at=None)
    )
    oauth_repo = _FakeOAuthRepo()
    app = build_app(
        orchestrator=orchestrator,
        oauth_repo=oauth_repo,
        verify_repo_=_FakeVerifyRepo(),
        client_id="1",
        client_secret="s",
        redirect_uri="https://esempio.com/cb",
        bot_token="bot-token",
        oauth_encryption_key=CHIAVE,
    )
    async with TestClient(TestServer(app)) as client:
        risposta = await client.get(_url_di_callback(100, 0))  # target=0 -> consenso puro

    assert risposta.status == 200
    assert oauth_repo.salvati == [(100, 999, "a")]
    assert orchestrator.chiamate_join == []


@pytest.mark.asyncio
async def test_callback_senza_code_restituisce_errore():
    app = build_app(
        orchestrator=_FakeOrchestrator(),
        oauth_repo=_FakeOAuthRepo(),
        verify_repo_=_FakeVerifyRepo(),
        client_id="1",
        client_secret="s",
        redirect_uri="https://esempio.com/cb",
        bot_token="bot-token",
        oauth_encryption_key=CHIAVE,
    )
    async with TestClient(TestServer(app)) as client:
        risposta = await client.get("/oauth/callback?state=abc")

    assert risposta.status == 400


@pytest.mark.asyncio
async def test_callback_state_malformato_restituisce_errore():
    app = build_app(
        orchestrator=_FakeOrchestrator(),
        oauth_repo=_FakeOAuthRepo(),
        verify_repo_=_FakeVerifyRepo(),
        client_id="1",
        client_secret="s",
        redirect_uri="https://esempio.com/cb",
        bot_token="bot-token",
        oauth_encryption_key=CHIAVE,
    )
    async with TestClient(TestServer(app)) as client:
        risposta = await client.get("/oauth/callback?code=x&state=stato-non-valido")

    assert risposta.status == 400


@pytest.mark.asyncio
async def test_callback_scambio_token_fallito_restituisce_errore_senza_salvare():
    orchestrator = _FakeOrchestrator(token=None)  # Discord rifiuta il code
    oauth_repo = _FakeOAuthRepo()
    app = build_app(
        orchestrator=orchestrator,
        oauth_repo=oauth_repo,
        verify_repo_=_FakeVerifyRepo(),
        client_id="1",
        client_secret="s",
        redirect_uri="https://esempio.com/cb",
        bot_token="bot-token",
        oauth_encryption_key=CHIAVE,
    )
    async with TestClient(TestServer(app)) as client:
        risposta = await client.get(_url_di_callback(100, 200))

    assert risposta.status == 400
    assert oauth_repo.salvati == []


@pytest.mark.asyncio
async def test_callback_join_fallito_restituisce_errore_502():
    orchestrator = _FakeOrchestrator(
        token=ExchangedToken(access_token="a", refresh_token="r", expires_at=None),
        join_riesce=False,
    )
    app = build_app(
        orchestrator=orchestrator,
        oauth_repo=_FakeOAuthRepo(),
        verify_repo_=_FakeVerifyRepo(),
        client_id="1",
        client_secret="s",
        redirect_uri="https://esempio.com/cb",
        bot_token="bot-token",
        oauth_encryption_key=CHIAVE,
    )
    async with TestClient(TestServer(app)) as client:
        risposta = await client.get(_url_di_callback(100, 200))

    assert risposta.status == 502


@pytest.mark.asyncio
async def test_callback_identita_non_verificabile_restituisce_errore_senza_salvare():
    """
    SEC-3: se /users/@me non risponde (token revocato nel frattempo,
    rete Discord giù), il callback si ferma prima di salvare
    qualunque cosa — mai usare un ID non confermato da Discord.
    """
    orchestrator = _FakeOrchestrator(
        token=ExchangedToken(access_token="a", refresh_token="r", expires_at=None),
        utente_autenticato=None,
    )
    oauth_repo = _FakeOAuthRepo()
    app = build_app(
        orchestrator=orchestrator,
        oauth_repo=oauth_repo,
        verify_repo_=_FakeVerifyRepo(),
        client_id="1",
        client_secret="s",
        redirect_uri="https://esempio.com/cb",
        bot_token="bot-token",
        oauth_encryption_key=CHIAVE,
    )
    async with TestClient(TestServer(app)) as client:
        risposta = await client.get(_url_di_callback(100, 200))

    assert risposta.status == 400
    assert oauth_repo.salvati == []
    assert orchestrator.chiamate_join == []


@pytest.mark.asyncio
async def test_callback_state_scaduto_restituisce_errore():
    app = build_app(
        orchestrator=_FakeOrchestrator(),
        oauth_repo=_FakeOAuthRepo(),
        verify_repo_=_FakeVerifyRepo(),
        client_id="1",
        client_secret="s",
        redirect_uri="https://esempio.com/cb",
        bot_token="bot-token",
        oauth_encryption_key=CHIAVE,
    )
    state_vecchio = encode_state(RestoreState(100, 200), CHIAVE, now=0)
    async with TestClient(TestServer(app)) as client:
        risposta = await client.get(f"/oauth/callback?code=x&state={state_vecchio}")

    assert risposta.status == 400


@pytest.mark.asyncio
async def test_callback_state_riusato_restituisce_errore_la_seconda_volta():
    orchestrator = _FakeOrchestrator(
        token=ExchangedToken(access_token="a", refresh_token="r", expires_at=None)
    )
    app = build_app(
        orchestrator=orchestrator,
        oauth_repo=_FakeOAuthRepo(),
        verify_repo_=_FakeVerifyRepo(),
        client_id="1",
        client_secret="s",
        redirect_uri="https://esempio.com/cb",
        bot_token="bot-token",
        oauth_encryption_key=CHIAVE,
    )
    url = _url_di_callback(100, 200)
    async with TestClient(TestServer(app)) as client:
        prima = await client.get(url)
        seconda = await client.get(url)

    assert prima.status == 200
    assert seconda.status == 400
