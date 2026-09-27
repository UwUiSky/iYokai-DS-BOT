"""
tests/test_restore_orchestrator.py
======================================
Test di RestoreOrchestrator con un server aiohttp VERO in locale
(aiohttp.test_utils), che imita la FORMA delle due API di Discord
usate qui — stesso principio già impiegato per Twitch in
tests/test_twitch_watcher.py.
"""

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from core.restore_orchestrator import RestoreOrchestrator


@pytest.fixture
async def server_discord_finto():
    stato = {"membri_aggiunti": [], "access_token_valido": "token-oauth-finto"}

    async def handler_token(request):
        dati = await request.post()
        if dati.get("code") != "code-valido":
            return web.json_response({"error": "invalid_grant"}, status=400)
        return web.json_response(
            {
                "access_token": stato["access_token_valido"],
                "refresh_token": "refresh-finto",
                "expires_in": 604800,
                "token_type": "bearer",
            }
        )

    async def handler_join(request):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bot "):
            return web.json_response({"error": "unauthorized"}, status=401)

        payload = await request.json()
        guild_id = int(request.match_info["guild_id"])
        user_id = int(request.match_info["user_id"])

        if payload.get("access_token") != stato["access_token_valido"]:
            return web.json_response({"error": "invalid access_token"}, status=403)

        if user_id in {m[1] for m in stato["membri_aggiunti"] if m[0] == guild_id}:
            return web.Response(status=204)  # già membro

        stato["membri_aggiunti"].append((guild_id, user_id))
        return web.json_response({"user": {"id": str(user_id)}}, status=201)

    async def handler_assign_role(request):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bot "):
            return web.json_response({"error": "unauthorized"}, status=401)
        role_id = int(request.match_info["role_id"])
        if role_id == 999999:
            return web.json_response({"error": "unknown role"}, status=404)
        return web.Response(status=204)

    app = web.Application()
    app.router.add_post("/oauth2/token", handler_token)
    app.router.add_put("/guilds/{guild_id}/members/{user_id}", handler_join)
    app.router.add_put("/guilds/{guild_id}/members/{user_id}/roles/{role_id}", handler_assign_role)
    server = TestServer(app)
    await server.start_server()
    yield server, stato
    await server.close()


@pytest.mark.asyncio
async def test_exchange_code_for_token_con_code_valido(server_discord_finto):
    server, _stato = server_discord_finto
    orchestrator = RestoreOrchestrator(
        token_url=str(server.make_url("/oauth2/token")),
        api_base_url=str(server.make_url("")),
    )
    try:
        risultato = await orchestrator.exchange_code_for_token(
            client_id="1", client_secret="s", redirect_uri="https://esempio.com/cb", code="code-valido"
        )
        assert risultato is not None
        assert risultato.access_token == "token-oauth-finto"
        assert risultato.refresh_token == "refresh-finto"
    finally:
        await orchestrator.close()


@pytest.mark.asyncio
async def test_exchange_code_for_token_con_code_invalido_restituisce_none(server_discord_finto):
    server, _stato = server_discord_finto
    orchestrator = RestoreOrchestrator(token_url=str(server.make_url("/oauth2/token")))
    try:
        risultato = await orchestrator.exchange_code_for_token(
            client_id="1", client_secret="s", redirect_uri="https://esempio.com/cb", code="code-scaduto"
        )
        assert risultato is None
    finally:
        await orchestrator.close()


@pytest.mark.asyncio
async def test_join_user_via_oauth_aggiunge_il_membro(server_discord_finto):
    server, stato = server_discord_finto
    orchestrator = RestoreOrchestrator(api_base_url=str(server.make_url("")))
    try:
        riuscito = await orchestrator.join_user_via_oauth(
            bot_token="bot-token", guild_id=100, user_id=1, access_token="token-oauth-finto"
        )
        assert riuscito is True
        assert (100, 1) in stato["membri_aggiunti"]
    finally:
        await orchestrator.close()


@pytest.mark.asyncio
async def test_join_user_via_oauth_gia_membro_e_comunque_successo(server_discord_finto):
    server, stato = server_discord_finto
    orchestrator = RestoreOrchestrator(api_base_url=str(server.make_url("")))
    try:
        await orchestrator.join_user_via_oauth(
            bot_token="bot-token", guild_id=100, user_id=1, access_token="token-oauth-finto"
        )
        riuscito_di_nuovo = await orchestrator.join_user_via_oauth(
            bot_token="bot-token", guild_id=100, user_id=1, access_token="token-oauth-finto"
        )
        assert riuscito_di_nuovo is True
    finally:
        await orchestrator.close()


@pytest.mark.asyncio
async def test_join_user_via_oauth_access_token_invalido_restituisce_false(server_discord_finto):
    server, _stato = server_discord_finto
    orchestrator = RestoreOrchestrator(api_base_url=str(server.make_url("")))
    try:
        riuscito = await orchestrator.join_user_via_oauth(
            bot_token="bot-token", guild_id=100, user_id=1, access_token="token-scaduto-o-falso"
        )
        assert riuscito is False
    finally:
        await orchestrator.close()


@pytest.mark.asyncio
async def test_assign_role_riuscito(server_discord_finto):
    server, _stato = server_discord_finto
    orchestrator = RestoreOrchestrator(api_base_url=str(server.make_url("")))
    try:
        riuscito = await orchestrator.assign_role(
            bot_token="bot-token", guild_id=100, user_id=1, role_id=555
        )
        assert riuscito is True
    finally:
        await orchestrator.close()


@pytest.mark.asyncio
async def test_assign_role_ruolo_sconosciuto_restituisce_false(server_discord_finto):
    server, _stato = server_discord_finto
    orchestrator = RestoreOrchestrator(api_base_url=str(server.make_url("")))
    try:
        riuscito = await orchestrator.assign_role(
            bot_token="bot-token", guild_id=100, user_id=1, role_id=999999
        )
        assert riuscito is False
    finally:
        await orchestrator.close()
