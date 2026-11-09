"""
tests/test_image_search_fetcher.py
========================================
Test di ImageSearchFetcherService con un server aiohttp VERO in
locale (aiohttp.test_utils), che imita la FORMA della risposta reale
di Pixabay — non un mock della sessione HTTP.
"""

import random

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from core.image_search_fetcher import ImageSearchFetcherService


@pytest.fixture
async def server_pixabay_finto():
    stato = {"ultima_query": None, "ultima_safesearch": None}

    async def handler_search(request):
        stato["ultima_query"] = request.query.get("q")
        stato["ultima_safesearch"] = request.query.get("safesearch")
        if request.query.get("q") == "nessun-risultato":
            return web.json_response({"total": 0, "totalHits": 0, "hits": []})
        return web.json_response(
            {
                "total": 1,
                "totalHits": 1,
                "hits": [{"webformatURL": "https://esempio.invalid/a.jpg", "tags": "gatto"}],
            }
        )

    async def handler_errore(request):
        return web.Response(status=500)

    app = web.Application()
    app.router.add_get("/api/", handler_search)
    app.router.add_get("/errore", handler_errore)

    server = TestServer(app)
    await server.start_server()
    try:
        yield server, stato
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_chiave_vuota_restituisce_none_senza_contattare_il_server(server_pixabay_finto):
    server, stato = server_pixabay_finto
    base = str(server.make_url("/"))
    service = ImageSearchFetcherService(search_url=f"{base}api/")
    try:
        risultato = await service.fetch_image("", "gatto", random.Random(1))
        assert risultato is None
        assert stato["ultima_query"] is None
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_ricerca_invia_query_e_safesearch_e_scarta_host_non_ammessi(server_pixabay_finto):
    server, stato = server_pixabay_finto
    base = str(server.make_url("/"))
    service = ImageSearchFetcherService(search_url=f"{base}api/")
    try:
        risultato = await service.fetch_image("chiave-finta", "gatto", random.Random(1))
        assert risultato is None  # host non ammesso: nessun download
        assert stato["ultima_query"] == "gatto"
        assert stato["ultima_safesearch"] == "true"
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_ricerca_senza_risultati_restituisce_none(server_pixabay_finto):
    server, _ = server_pixabay_finto
    base = str(server.make_url("/"))
    service = ImageSearchFetcherService(search_url=f"{base}api/")
    try:
        risultato = await service.fetch_image(
            "chiave-finta", "nessun-risultato", random.Random(1)
        )
        assert risultato is None
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_status_non_200_restituisce_none(server_pixabay_finto):
    server, _ = server_pixabay_finto
    base = str(server.make_url("/"))
    service = ImageSearchFetcherService(search_url=f"{base}errore")
    try:
        assert await service.fetch_image("chiave-finta", "gatto", random.Random(1)) is None
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_server_irraggiungibile_restituisce_none():
    service = ImageSearchFetcherService(search_url="http://127.0.0.1:1/non-esiste")
    try:
        assert await service.fetch_image("chiave-finta", "gatto", random.Random(1)) is None
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_il_log_non_contiene_mai_la_chiave_se_la_risposta_non_e_json(caplog):
    """aiohttp mette l'indirizzo completo (con `key=`) nel testo di ContentTypeError: non va nel log."""

    async def html(request):
        return web.Response(text="<html>no</html>", content_type="text/html")

    app = web.Application()
    app.router.add_get("/api/", html)
    server = TestServer(app)
    await server.start_server()
    service = ImageSearchFetcherService(search_url=str(server.make_url("/api/")))
    try:
        with caplog.at_level("WARNING"):
            assert await service.fetch_image("CHIAVE-SEGRETA-123", "gatto", random.Random(1)) is None
        assert "CHIAVE-SEGRETA-123" not in caplog.text
        assert caplog.text  # il problema resta annotato
    finally:
        await service.close()
        await server.close()
