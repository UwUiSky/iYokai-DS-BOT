"""
tests/test_restore_web_server.py
====================================
Test dell'endpoint /oauth/callback (SPEC.md §11.11). build_app()
accetta le dipendenze come parametri: i test più vecchi usano finti
minimi; quelli di BUG-21/SEC-19 e del controllo sul ruolo usano
l'orchestrator vero contro un server aiohttp locale che imita Discord
e il repository vero su PostgreSQL.
"""

import asyncio
import logging

import discord
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from core.oauth_crypto import generate_key
from core.redacted_access_log import RedactedAccessLogger
from core.repositories.restore_oauth_repo import (
    STATUS_ACTIVE,
    STATUS_BANNED_BLACKLISTED,
    RestoreOAuthRepository,
)
from core.restore_oauth_logic import encode_state, RestoreState
from core.restore_orchestrator import ExchangedToken, RestoreOrchestrator
from core.restore_web_server import build_app, start_server
from tests.support.discord_fakes import fake_guild, fake_member, fake_role

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
        return True


class _FakeVerifyConfig:
    def __init__(self, verified_role_id):
        self.verified_role_id = verified_role_id


class _FakeVerifyRepo:
    def __init__(self, verified_role_id=None) -> None:
        self._verified_role_id = verified_role_id

    async def get_config(self, guild_id: int):
        return _FakeVerifyConfig(self._verified_role_id)


def _url_di_callback(
    source_guild_id, target_guild_id, code="il-code", destinatario=UTENTE_AUTENTICATO_DEFAULT
):
    state = encode_state(RestoreState(source_guild_id, target_guild_id, destinatario), CHIAVE)
    return f"/oauth/callback?code={code}&state={state}"


def _server_con_ruolo(ruolo=None):
    """Server finto (autospec) in cui il bot è abbastanza in alto da assegnare `ruolo`."""
    bot_membro = fake_member(user_id=1, name="Yokai Bot", bot=True)
    bot_membro.top_role = fake_role(role_id=9000, name="Bot", position=50)
    server = fake_guild(guild_id=200, me=bot_membro)
    server.get_role.return_value = ruolo
    return server


def _nessun_server(guild_id):
    return None


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
        get_guild=_nessun_server,
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
        get_guild=lambda guild_id: _server_con_ruolo(fake_role(role_id=555, position=5)),
    )
    async with TestClient(TestServer(app)) as client:
        await client.get(_url_di_callback(100, 200))

    assert orchestrator.chiamate_assign_role == [(200, 999, 555)]


@pytest.mark.asyncio
async def test_callback_ruolo_verificato_pericoloso_non_viene_assegnato(caplog):
    """
    SEC-4/SEC-17: il ruolo verificato può aver preso permessi
    pericolosi dopo il /verify setup — l'utente entra lo stesso, ma
    senza il ruolo, e resta un avviso nei log.
    """
    orchestrator = _FakeOrchestrator(
        token=ExchangedToken(access_token="a", refresh_token="r", expires_at=None)
    )
    ruolo_admin = fake_role(
        role_id=555, name="Verificato", position=5, permissions=discord.Permissions(administrator=True)
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
        get_guild=lambda guild_id: _server_con_ruolo(ruolo_admin),
    )
    with caplog.at_level(logging.WARNING, logger="iyokai.restore_web_server"):
        async with TestClient(TestServer(app)) as client:
            risposta = await client.get(_url_di_callback(100, 200))

    assert risposta.status == 200
    assert orchestrator.chiamate_join == [(200, 999)]
    assert orchestrator.chiamate_assign_role == []
    assert "administrator" in caplog.text


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
        get_guild=_nessun_server,
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
        get_guild=_nessun_server,
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
        get_guild=_nessun_server,
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
        get_guild=_nessun_server,
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
        get_guild=_nessun_server,
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
        get_guild=_nessun_server,
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
        get_guild=_nessun_server,
    )
    state_vecchio = encode_state(RestoreState(100, 200, 999), CHIAVE, now=0)
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
        get_guild=_nessun_server,
    )
    url = _url_di_callback(100, 200)
    async with TestClient(TestServer(app)) as client:
        prima = await client.get(url)
        seconda = await client.get(url)

    assert prima.status == 200
    assert seconda.status == 400


@pytest.mark.asyncio
async def test_start_server_usa_l_access_log_redatto():
    # SEC-9: la query string del callback contiene "code"/"state"
    # (OAuth2), non va mai scritta per intero nei log del server.
    app = build_app(
        orchestrator=_FakeOrchestrator(),
        oauth_repo=_FakeOAuthRepo(),
        verify_repo_=_FakeVerifyRepo(),
        client_id="1",
        client_secret="s",
        redirect_uri="https://esempio.com/cb",
        bot_token="bot-token",
        oauth_encryption_key=CHIAVE,
        get_guild=_nessun_server,
    )

    runner = await start_server(app, host="127.0.0.1", port=0)
    try:
        assert runner._kwargs["access_log_class"] is RedactedAccessLogger
    finally:
        await runner.cleanup()


# ---------------------------------------------------------------------
# BUG-21 / SEC-19: orchestrator vero contro un Discord finto in locale,
# repository vero su PostgreSQL.
# ---------------------------------------------------------------------

DESTINATARIO = 42


class _DiscordFinto:
    """Imita la forma delle API di Discord usate dal restore e registra cosa riceve."""

    def __init__(self) -> None:
        self.utente_che_autorizza = DESTINATARIO
        self.scambi_falliti_da_simulare = 0
        self.join_falliti_da_simulare = 0
        self.scambi_ricevuti = 0
        self.membri_aggiunti: list[tuple[int, int]] = []
        self.ruoli_assegnati: list[tuple[int, int, int]] = []
        self.sblocca_scambio: asyncio.Event | None = None

    async def token(self, request):
        self.scambi_ricevuti += 1
        if self.sblocca_scambio is not None:
            await self.sblocca_scambio.wait()
        if self.scambi_falliti_da_simulare > 0:
            self.scambi_falliti_da_simulare -= 1
            return web.json_response({"error": "temporaneo"}, status=503)
        return web.json_response(
            {"access_token": "access-finto", "refresh_token": "refresh-finto", "expires_in": 604800}
        )

    async def users_me(self, request):
        return web.json_response({"id": str(self.utente_che_autorizza)})

    async def join(self, request):
        if self.join_falliti_da_simulare > 0:
            self.join_falliti_da_simulare -= 1
            return web.json_response({"error": "temporaneo"}, status=503)
        self.membri_aggiunti.append(
            (int(request.match_info["guild_id"]), int(request.match_info["user_id"]))
        )
        return web.json_response({}, status=201)

    async def assegna_ruolo(self, request):
        info = request.match_info
        self.ruoli_assegnati.append((int(info["guild_id"]), int(info["user_id"]), int(info["role_id"])))
        return web.Response(status=204)


@pytest.fixture
async def ambiente(clean_db):
    """(client HTTP della callback, Discord finto, repository vero dei token)."""
    discord_finto = _DiscordFinto()
    app_discord = web.Application()
    app_discord.router.add_post("/oauth2/token", discord_finto.token)
    app_discord.router.add_get("/users/@me", discord_finto.users_me)
    app_discord.router.add_put("/guilds/{guild_id}/members/{user_id}", discord_finto.join)
    app_discord.router.add_put(
        "/guilds/{guild_id}/members/{user_id}/roles/{role_id}", discord_finto.assegna_ruolo
    )
    server_discord = TestServer(app_discord)
    await server_discord.start_server()

    orchestrator = RestoreOrchestrator(
        token_url=str(server_discord.make_url("/oauth2/token")),
        api_base_url=str(server_discord.make_url("")),
    )
    oauth_repo = RestoreOAuthRepository(
        pool_provider=lambda: clean_db, encryption_key_provider=lambda: CHIAVE
    )
    app = build_app(
        orchestrator=orchestrator,
        oauth_repo=oauth_repo,
        verify_repo_=_FakeVerifyRepo(verified_role_id=None),
        client_id="1",
        client_secret="s",
        redirect_uri="https://esempio.com/cb",
        bot_token="bot-token",
        oauth_encryption_key=CHIAVE,
        get_guild=_nessun_server,
    )
    async with TestClient(TestServer(app)) as client:
        yield client, discord_finto, oauth_repo
    await orchestrator.close()
    await server_discord.close()


@pytest.mark.asyncio
async def test_link_aperto_dal_destinatario_lo_fa_entrare(ambiente):
    client, discord_finto, oauth_repo = ambiente

    risposta = await client.get(_url_di_callback(100, 200, destinatario=DESTINATARIO))

    assert risposta.status == 200
    assert discord_finto.membri_aggiunti == [(200, DESTINATARIO)]
    assert (await oauth_repo.get_token(100, DESTINATARIO)).status == STATUS_ACTIVE


@pytest.mark.asyncio
async def test_link_aperto_da_un_altro_account_viene_rifiutato(ambiente):
    """SEC-19: il link è legato a chi lo ha ricevuto in DM."""
    client, discord_finto, oauth_repo = ambiente
    discord_finto.utente_che_autorizza = 666  # non è il destinatario
    url = _url_di_callback(100, 200, destinatario=DESTINATARIO)

    risposta = await client.get(url)

    assert risposta.status == 403
    assert discord_finto.membri_aggiunti == []
    assert await oauth_repo.get_token(100, 666) is None
    assert await oauth_repo.get_token(100, DESTINATARIO) is None

    # Il tentativo di un estraneo non brucia il link del destinatario vero.
    discord_finto.utente_che_autorizza = DESTINATARIO
    assert (await client.get(url)).status == 200
    assert discord_finto.membri_aggiunti == [(200, DESTINATARIO)]


@pytest.mark.asyncio
async def test_utente_in_blacklist_viene_rifiutato_e_resta_in_blacklist(ambiente):
    """SEC-19: chi è stato bannato non rientra e non torna 'active'."""
    client, discord_finto, oauth_repo = ambiente
    # Aveva dato il consenso, poi è stato bannato dal server di origine
    # (stesso percorso del listener on_member_ban).
    assert (await client.get(_url_di_callback(100, 0, destinatario=DESTINATARIO))).status == 200
    await oauth_repo.mark_banned(100, DESTINATARIO)

    risposta = await client.get(_url_di_callback(100, 200, destinatario=DESTINATARIO))

    assert risposta.status == 403
    assert discord_finto.membri_aggiunti == []
    assert (await oauth_repo.get_token(100, DESTINATARIO)).status == STATUS_BANNED_BLACKLISTED


@pytest.mark.asyncio
async def test_errore_temporaneo_nello_scambio_non_brucia_il_link(ambiente):
    """BUG-21: se Discord non risponde, lo stesso link funziona al tentativo dopo."""
    client, discord_finto, _oauth_repo = ambiente
    discord_finto.scambi_falliti_da_simulare = 1
    url = _url_di_callback(100, 200, destinatario=DESTINATARIO)

    prima = await client.get(url)
    seconda = await client.get(url)

    assert prima.status == 400
    assert seconda.status == 200
    assert discord_finto.membri_aggiunti == [(200, DESTINATARIO)]


@pytest.mark.asyncio
async def test_errore_temporaneo_nell_ingresso_non_brucia_il_link(ambiente):
    client, discord_finto, _oauth_repo = ambiente
    discord_finto.join_falliti_da_simulare = 1
    url = _url_di_callback(100, 200, destinatario=DESTINATARIO)

    prima = await client.get(url)
    seconda = await client.get(url)

    assert prima.status == 502
    assert seconda.status == 200


@pytest.mark.asyncio
async def test_link_riuscito_non_funziona_una_seconda_volta(ambiente):
    client, discord_finto, _oauth_repo = ambiente
    url = _url_di_callback(100, 200, destinatario=DESTINATARIO)

    assert (await client.get(url)).status == 200
    assert (await client.get(url)).status == 400
    assert discord_finto.scambi_ricevuti == 1


@pytest.mark.asyncio
async def test_due_callback_in_parallelo_con_lo_stesso_link_ne_passa_una_sola(ambiente):
    client, discord_finto, _oauth_repo = ambiente
    discord_finto.sblocca_scambio = asyncio.Event()
    url = _url_di_callback(100, 200, destinatario=DESTINATARIO)

    prima = asyncio.create_task(client.get(url))
    while discord_finto.scambi_ricevuti == 0:  # la prima è arrivata fino a Discord
        await asyncio.sleep(0.01)
    seconda = await client.get(url)  # arriva mentre la prima è ancora in corso
    discord_finto.sblocca_scambio.set()

    assert seconda.status == 400
    assert (await prima).status == 200
    assert discord_finto.scambi_ricevuti == 1
    assert discord_finto.membri_aggiunti == [(200, DESTINATARIO)]


@pytest.mark.asyncio
async def test_firma_non_ascii_mostra_la_pagina_di_link_non_valido(ambiente):
    """BUG-21: prima una firma con caratteri non ASCII dava HTTP 500."""
    client, _discord_finto, _oauth_repo = ambiente
    state = encode_state(RestoreState(100, 200, DESTINATARIO), CHIAVE)
    payload_b64, _, _firma = state.partition(".")

    risposta = await client.get(
        "/oauth/callback", params={"code": "x", "state": f"{payload_b64}.firma-è-finta"}
    )

    assert risposta.status == 400
    assert "Link non valido" in await risposta.text()
