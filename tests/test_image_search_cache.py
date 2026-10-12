"""
tests/test_image_search_cache.py
================================
M 15.2 (LIM-48): ricerca Pixabay con cache di 24 ore, immagine scaricata
e restituita come byte, link alla pagina Pixabay per il credito.
Server aiohttp vero in locale, nessun mock della sessione.
"""

import random

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from core.image_search_fetcher import (
    DURATA_CACHE_SECONDI,
    ImageSearchFetcherService,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 20


@pytest.fixture
async def server():
    stato = {"chiamate_api": 0, "chiamate_img": 0, "query": []}

    async def api(request):
        stato["chiamate_api"] += 1
        stato["query"].append(request.query.get("q"))
        base = f"http://127.0.0.1:{request.url.port}"
        return web.json_response(
            {
                "hits": [
                    {
                        "webformatURL": f"{base}/img/a.png",
                        "pageURL": "https://pixabay.com/photos/gatto-123/",
                    }
                ]
            }
        )

    async def img(request):
        stato["chiamate_img"] += 1
        return web.Response(body=PNG, content_type="image/png")

    async def non_immagine(request):
        return web.Response(body=b"<html>", content_type="text/html")

    app = web.Application()
    app.router.add_get("/api/", api)
    app.router.add_get("/img/a.png", img)
    app.router.add_get("/img/html", non_immagine)
    srv = TestServer(app)
    await srv.start_server()
    try:
        yield srv, stato
    finally:
        await srv.close()


def _servizio(srv, orologio=None):
    return ImageSearchFetcherService(
        search_url=str(srv.make_url("/api/")),
        domini_immagine=("127.0.0.1",),
        adesso=orologio or (lambda: 0.0),
    )


@pytest.mark.asyncio
async def test_stessa_ricerca_due_volte_una_sola_chiamata(server):
    srv, stato = server
    servizio = _servizio(srv)
    try:
        a = await servizio.fetch_image("k", "Gatto", random.Random(1))
        b = await servizio.fetch_image("k", "  gatto ", random.Random(2))
        assert a is not None and b is not None
        assert stato["chiamate_api"] == 1
    finally:
        await servizio.close()


@pytest.mark.asyncio
async def test_la_cache_scade_dopo_24_ore(server):
    srv, stato = server
    ora = {"t": 0.0}
    servizio = _servizio(srv, lambda: ora["t"])
    try:
        await servizio.fetch_image("k", "gatto", random.Random(1))
        ora["t"] = DURATA_CACHE_SECONDI - 1
        await servizio.fetch_image("k", "gatto", random.Random(1))
        assert stato["chiamate_api"] == 1
        ora["t"] = DURATA_CACHE_SECONDI + 1
        await servizio.fetch_image("k", "gatto", random.Random(1))
        assert stato["chiamate_api"] == 2
    finally:
        await servizio.close()


@pytest.mark.asyncio
async def test_restituisce_i_byte_e_il_link_di_credito(server):
    srv, _ = server
    servizio = _servizio(srv)
    try:
        r = await servizio.fetch_image("k", "gatto", random.Random(1))
        assert r.dati == PNG
        assert r.estensione == "png"
        assert r.pagina == "https://pixabay.com/photos/gatto-123/"
    finally:
        await servizio.close()


@pytest.mark.asyncio
async def test_dominio_non_ammesso_non_viene_scaricato(server):
    srv, stato = server
    servizio = ImageSearchFetcherService(
        search_url=str(srv.make_url("/api/")), domini_immagine=("pixabay.com",)
    )
    try:
        assert await servizio.fetch_image("k", "gatto", random.Random(1)) is None
        assert stato["chiamate_img"] == 0
    finally:
        await servizio.close()


@pytest.mark.asyncio
async def test_chiave_vuota_non_chiama_nulla(server):
    srv, stato = server
    servizio = _servizio(srv)
    try:
        assert await servizio.fetch_image("", "gatto", random.Random(1)) is None
        assert stato["chiamate_api"] == 0
    finally:
        await servizio.close()
