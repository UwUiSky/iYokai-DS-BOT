"""
tests/test_safe_http_condiviso.py
=====================================
Issue #67, voce 11.9 (LIM-51, PERF-7) per core/safe_http.py: sessione
condivisa, User-Agent con il nome del bot, ETag (If-None-Match / 304).
"""

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

import core.safe_http as safe_http
from core.safe_http import safe_get, safe_get_con_etag


@pytest.fixture
async def server(monkeypatch):
    monkeypatch.setattr(safe_http, "_ip_e_bloccato", lambda ip: False)
    monkeypatch.setattr(safe_http, "_schema_e_porta_ammessi", lambda url: True)
    visti = {"ua": [], "porte": [], "if_none_match": []}

    async def pagina(request):
        visti["ua"].append(request.headers.get("User-Agent", ""))
        visti["porte"].append(request.transport.get_extra_info("peername")[1])
        visti["if_none_match"].append(request.headers.get("If-None-Match"))
        if request.headers.get("If-None-Match") == '"v1"':
            return web.Response(status=304, headers={"ETag": '"v1"'})
        return web.Response(text="ciao", headers={"ETag": '"v1"'})

    app = web.Application()
    app.router.add_get("/p", pagina)
    srv = TestServer(app)
    await srv.start_server()
    yield f"http://{srv.host}:{srv.port}/p", visti
    await safe_http.chiudi_sessione_condivisa()
    await srv.close()


@pytest.mark.asyncio
async def test_user_agent_con_il_nome_del_bot(server):
    url, visti = server
    assert await safe_get(url) == "ciao"
    assert "iYokai" in visti["ua"][0]


@pytest.mark.asyncio
async def test_due_scarichi_riusano_la_stessa_connessione(server):
    url, visti = server
    await safe_get(url)
    await safe_get(url)
    assert visti["porte"][0] == visti["porte"][1]


@pytest.mark.asyncio
async def test_etag_poi_304_non_modificato(server):
    url, visti = server
    primo = await safe_get_con_etag(url)
    assert primo.testo == "ciao" and primo.etag == '"v1"' and not primo.non_modificato

    secondo = await safe_get_con_etag(url, etag=primo.etag)
    assert secondo.non_modificato and secondo.testo is None
    assert visti["if_none_match"] == [None, '"v1"']
