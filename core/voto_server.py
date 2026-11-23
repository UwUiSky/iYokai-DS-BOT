"""
core/voto_server.py
===================
Il piccolo server web che riceve il voto al bot dal sito di elenchi (top.gg): un solo indirizzo, `POST` sul percorso «voto», con
il segreto del .env (intestazione Authorization o firma). Parte solo se il segreto c'è. I tentativi con un segreto
sbagliato sono limitati per indirizzo, e si contano prima di guardare il corpo. Niente dipendenze importate qui:
`registra` e `dopo_voto` arrivano come parametri, così i test passano funzioni finte.
Funzioni coperte: LIV-019, ECO-048, ECO-049, CFG-039
Dipende da: core/voto_logic.py, core/webhook_rate_tracker.py
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiohttp import web

from core.redacted_access_log import RedactedAccessLogger
from core.voto_logic import MAX_BYTE_CORPO, SITO_TOPGG, leggi_voto, segreto_valido, verifica
from core.webhook_rate_tracker import webhook_rate_tracker

logger = logging.getLogger("iyokai.voto_server")

MAX_TENTATIVI_SBAGLIATI = 20
FINESTRA_SECONDI = 600


def _ip(request: web.Request) -> str:
    if request.remote in ("127.0.0.1", "::1"):  # dietro il reverse proxy: l'ultimo indirizzo lo scrive il proxy
        return request.headers.get("X-Forwarded-For", "").rsplit(",", 1)[-1].strip() or "locale"
    return request.remote or "ignoto"


def build_app(*, segreto: str, registra, dopo_voto=None, sito: str = SITO_TOPGG) -> web.Application:
    """`registra(sito, user_id) -> id | None`; `dopo_voto(user_id)` (facoltativa) parte solo per un voto nuovo."""

    async def handler(request: web.Request) -> web.Response:
        chiave = f"voto-ip:{_ip(request)}"
        adesso = datetime.now(timezone.utc)
        if webhook_rate_tracker.count_recent(chiave, adesso, FINESTRA_SECONDI) >= MAX_TENTATIVI_SBAGLIATI:
            return web.json_response({"error": "troppi tentativi"}, status=429)
        corpo = await request.read()
        if not verifica(segreto, request.headers.get("Authorization"), request.headers.get("x-topgg-signature"), corpo):
            webhook_rate_tracker.allow(chiave, adesso, MAX_TENTATIVI_SBAGLIATI, FINESTRA_SECONDI)
            return web.json_response({"error": "non autorizzato"}, status=401)
        voto = leggi_voto(corpo)
        if voto is None:
            return web.json_response({"ok": True, "voto": False})
        try:
            nuovo = await registra(sito, voto.user_id) is not None
        except Exception:
            logger.exception("Voto non registrato.")
            return web.json_response({"error": "errore interno"}, status=500)  # il sito riprova più tardi
        if nuovo and dopo_voto is not None:
            try:
                await dopo_voto(voto.user_id)
            except Exception:
                logger.exception("Premio automatico del voto non dato.")
        return web.json_response({"ok": True, "voto": nuovo})

    app = web.Application(client_max_size=MAX_BYTE_CORPO)
    if segreto_valido(segreto):  # senza segreto valido nessuna rotta: il modulo è spento
        app.router.add_post("/".join(("", "voto")), handler)  # percorso del sito, non un comando
    return app


async def start_server(app: web.Application, host: str, port: int) -> web.AppRunner:
    runner = web.AppRunner(app, access_log_class=RedactedAccessLogger)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    logger.info("Server del voto in ascolto su %s:%d", host, port)
    return runner
