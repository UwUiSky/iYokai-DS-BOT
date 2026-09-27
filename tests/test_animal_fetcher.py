"""
tests/test_animal_fetcher.py
==================================
Test di AnimalFetcherService con un server aiohttp VERO in locale
(aiohttp.test_utils), che imita la FORMA delle tre API reali — non
un mock della sessione HTTP. Stesso schema di
tests/test_youtube_watcher.py.
"""

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from core.animal_fetcher import AnimalFetcherService


@pytest.fixture
async def server_animali_finto():
    async def handler_dog(request):
        return web.json_response(
            {"status": "success", "message": "https://images.dog.ceo/x.jpg"}
        )

    async def handler_cat(request):
        return web.json_response([{"url": "https://cdn2.thecatapi.com/x.jpg"}])

    async def handler_fox(request):
        return web.json_response({"image": "https://randomfox.ca/images/x.jpg"})

    async def handler_errore(request):
        return web.Response(status=500)

    app = web.Application()
    app.router.add_get("/dog", handler_dog)
    app.router.add_get("/cat", handler_cat)
    app.router.add_get("/fox", handler_fox)
    app.router.add_get("/errore", handler_errore)

    server = TestServer(app)
    await server.start_server()
    try:
        yield server
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_fetch_image_url_dog(server_animali_finto):
    base = str(server_animali_finto.make_url("/"))
    service = AnimalFetcherService(dog_url=f"{base}dog")
    try:
        assert await service.fetch_image_url("dog") == "https://images.dog.ceo/x.jpg"
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_fetch_image_url_cat(server_animali_finto):
    base = str(server_animali_finto.make_url("/"))
    service = AnimalFetcherService(cat_url=f"{base}cat")
    try:
        assert await service.fetch_image_url("cat") == "https://cdn2.thecatapi.com/x.jpg"
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_fetch_image_url_fox(server_animali_finto):
    base = str(server_animali_finto.make_url("/"))
    service = AnimalFetcherService(fox_url=f"{base}fox")
    try:
        assert await service.fetch_image_url("fox") == "https://randomfox.ca/images/x.jpg"
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_specie_non_supportata_restituisce_none():
    service = AnimalFetcherService()
    try:
        assert await service.fetch_image_url("dinosauro") is None
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_status_non_200_restituisce_none(server_animali_finto):
    base = str(server_animali_finto.make_url("/"))
    service = AnimalFetcherService(dog_url=f"{base}errore")
    try:
        assert await service.fetch_image_url("dog") is None
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_server_irraggiungibile_restituisce_none():
    service = AnimalFetcherService(dog_url="http://127.0.0.1:1/non-esiste")
    try:
        assert await service.fetch_image_url("dog") is None
    finally:
        await service.close()
