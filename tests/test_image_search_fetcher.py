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
                "hits": [{"webformatURL": "https://pixabay.com/a.jpg", "tags": "gatto"}],
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
        risultato = await service.fetch_image_url("", "gatto", random.Random(1))
        assert risultato is None
        assert stato["ultima_query"] is None
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_ricerca_con_risultati_restituisce_un_url(server_pixabay_finto):
    server, stato = server_pixabay_finto
    base = str(server.make_url("/"))
    service = ImageSearchFetcherService(search_url=f"{base}api/")
    try:
        risultato = await service.fetch_image_url("chiave-finta", "gatto", random.Random(1))
        assert risultato == "https://pixabay.com/a.jpg"
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
        risultato = await service.fetch_image_url(
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
        assert await service.fetch_image_url("chiave-finta", "gatto", random.Random(1)) is None
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_server_irraggiungibile_restituisce_none():
    service = ImageSearchFetcherService(search_url="http://127.0.0.1:1/non-esiste")
    try:
        assert await service.fetch_image_url("chiave-finta", "gatto", random.Random(1)) is None
    finally:
        await service.close()
