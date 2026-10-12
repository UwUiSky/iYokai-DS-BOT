"""
tests/support/fake_lavalink.py
==================================
Un Lavalink finto (solo gli endpoint che il bot usa: `/v4/websocket`,
`/v4/info` e un 200 vuoto per il resto), per provare il collegamento dei
nodi con una vera connessione WebSocket invece di un mock.
"""

import asyncio

from aiohttp import web

_versione = "4.2.0"


async def _websocket(request):
    risposta = web.WebSocketResponse()
    await risposta.prepare(request)
    await risposta.send_json({"op": "ready", "resumed": False, "sessionId": "abc"})
    async for _ in risposta:
        pass
    return risposta


async def _info(request):
    semver = _versione
    major, minor, patch = (int(p) for p in semver.split("."))
    return web.json_response(
        {
            "version": {
                "semver": semver,
                "major": major,
                "minor": minor,
                "patch": patch,
                "preRelease": None,
                "build": None,
            },
            "buildTime": 1700000000000,
            "git": {"branch": "m", "commit": "c", "commitTime": 1700000000000},
            "jvm": "21",
            "lavaplayer": "2",
            "sourceManagers": ["youtube"],
            "filters": [],
            "plugins": [],
        }
    )


async def _vuota(request):
    return web.json_response({})


def crea_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/v4/websocket", _websocket)
    app.router.add_get("/v4/info", _info)
    app.router.add_route("*", "/{tail:.*}", _vuota)
    return app


async def start(port: int, version: str = "4.2.0") -> web.AppRunner:
    """Avvia il finto su 127.0.0.1:<port>; chiudere con `await runner.cleanup()`."""
    global _versione
    _versione = version
    runner = web.AppRunner(crea_app())
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", port).start()
    await asyncio.sleep(0)
    return runner
