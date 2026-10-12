import asyncio, json
from aiohttp import web
VERSION="4.2.0"
async def ws(request):
    w = web.WebSocketResponse(); await w.prepare(request)
    await w.send_json({"op":"ready","resumed":False,"sessionId":"abc"})
    async for _ in w: pass
    return w
async def info(request):
    return web.json_response({"version":{"semver":VERSION,"major":4,"minor":2,"patch":0,"preRelease":None,"build":None},
      "buildTime":1700000000000,"git":{"branch":"m","commit":"c","commitTime":1700000000000},"jvm":"21","lavaplayer":"2","sourceManagers":["youtube"],"filters":[],"plugins":[]})
async def any_(request): return web.json_response({})
def make_app():
    a = web.Application()
    a.router.add_get("/v4/websocket", ws); a.router.add_get("/v4/info", info)
    a.router.add_route("*","/{tail:.*}", any_)
    return a
async def start(port, version="4.2.0"):
    global VERSION; VERSION=version
    r = web.AppRunner(make_app()); await r.setup()
    await web.TCPSite(r,"127.0.0.1",port).start(); return r
