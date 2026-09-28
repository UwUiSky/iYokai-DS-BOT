"""
tests/test_redacted_access_log.py
=====================================
Test di core/redacted_access_log.py (SEC-9) — l'access log dei
server web (webhook custom, callback OAuth2 del restore) non deve
mai scrivere un token o un codice OAuth per intero.
"""

import logging

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from core.redacted_access_log import RedactedAccessLogger, redact_path


class TestRedactPath:
    def test_percorso_webhook_viene_redatto(self):
        assert redact_path("/webhook/segreto-molto-lungo-12345") == "/webhook/***"

    def test_percorso_non_sensibile_resta_invariato(self):
        assert redact_path("/oauth/callback") == "/oauth/callback"
        assert redact_path("/") == "/"


@pytest.mark.asyncio
async def test_access_log_non_contiene_il_token_del_webhook(caplog):
    async def handler(request):
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/webhook/{token}", handler)

    server = TestServer(app)
    runner = web.AppRunner(app, access_log_class=RedactedAccessLogger)
    # TestServer normalmente gestisce da sé runner/site — qui si
    # riusa la sola app con un client reale per generare una richiesta
    # vera e osservare la riga di log che ne risulta.
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    porta = site._server.sockets[0].getsockname()[1]

    try:
        with caplog.at_level(logging.INFO, logger="aiohttp.access"):
            import aiohttp

            async with aiohttp.ClientSession() as sessione:
                async with sessione.get(
                    f"http://127.0.0.1:{porta}/webhook/token-segreto-davvero-non-deve-uscire"
                ) as risposta:
                    await risposta.text()
    finally:
        await runner.cleanup()

    righe = "\n".join(caplog.messages)
    assert "token-segreto-davvero-non-deve-uscire" not in righe
    assert "/webhook/***" in righe


@pytest.mark.asyncio
async def test_access_log_non_contiene_la_query_string(caplog):
    async def handler(request):
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/oauth/callback", handler)

    runner = web.AppRunner(app, access_log_class=RedactedAccessLogger)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    porta = site._server.sockets[0].getsockname()[1]

    try:
        with caplog.at_level(logging.INFO, logger="aiohttp.access"):
            import aiohttp

            async with aiohttp.ClientSession() as sessione:
                async with sessione.get(
                    f"http://127.0.0.1:{porta}/oauth/callback?code=codice-oauth-segreto&state=xyz"
                ) as risposta:
                    await risposta.text()
    finally:
        await runner.cleanup()

    righe = "\n".join(caplog.messages)
    assert "codice-oauth-segreto" not in righe
    assert "state=" not in righe
