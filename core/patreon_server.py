"""
core/patreon_server.py
======================
Il piccolo server web di Patreon: `POST /patreon/webhook` (eventi firmati) e `GET /patreon/callback` (ritorno da OAuth).
Senza le tre chiavi nel .env l'applicazione non ha nessuna rotta e il cog non apre nessuna porta. Un corpo con firma
sbagliata si rifiuta prima di leggerlo come JSON; i tentativi sbagliati sono limitati per indirizzo.
Funzioni coperte: CFG-036
Dipende da: core/patreon_logic.py, core/patreon_service.py, core/webhook_rate_tracker.py
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiohttp import web

from core import patreon_logic as logica
from core import web_panel_logic
from core.redacted_access_log import RedactedAccessLogger
from core.webhook_rate_tracker import webhook_rate_tracker

logger = logging.getLogger("iyokai.patreon_server")

MAX_TENTATIVI_SBAGLIATI = 20
FINESTRA_SECONDI = 600


def _ip(request: web.Request) -> str:
    if request.remote in ("127.0.0.1", "::1"):  # dietro il reverse proxy
        return request.headers.get("X-Forwarded-For", "").rsplit(",", 1)[-1].strip() or "locale"
    return request.remote or "ignoto"


def build_app(*, client_id: str, client_secret: str, webhook_secret: str, applica_evento, completa_collegamento,
              url_dopo: str = "", url_conferma: str = "", cookie_sessione: str = "iyokai_sessione") -> web.Application:
    """
    `applica_evento(evento, corpo)` e `completa_collegamento(stato, codice, impronta_sessione)` arrivano come parametri
    (test). `cookie_sessione`: il nome del cookie del pannello (con `__Host-` su https): il ritorno da Patreon vale solo
    se il browser porta la stessa sessione che ha cominciato il collegamento. `url_conferma`: dove mandare chi deve
    confermare lo spostamento di un account Patreon già collegato a un'altra persona.
    """
    app = web.Application(client_max_size=logica.MAX_BYTE_CORPO)
    if not logica.chiavi_presenti(client_id, client_secret, webhook_secret):
        return app  # spento: nessuna rotta

    def troppi(request: web.Request) -> bool:
        return webhook_rate_tracker.count_recent(f"patreon-ip:{_ip(request)}", datetime.now(timezone.utc), FINESTRA_SECONDI) >= MAX_TENTATIVI_SBAGLIATI

    def sbagliato(request: web.Request) -> None:
        webhook_rate_tracker.allow(f"patreon-ip:{_ip(request)}", datetime.now(timezone.utc), MAX_TENTATIVI_SBAGLIATI, FINESTRA_SECONDI)

    async def webhook(request: web.Request) -> web.Response:
        if troppi(request):
            return web.json_response({"error": "troppi tentativi"}, status=429)
        corpo = await request.read()
        if not logica.firma_valida(webhook_secret, corpo, request.headers.get("X-Patreon-Signature")):
            sbagliato(request)
            return web.json_response({"error": "non autorizzato"}, status=401)
        evento = logica.leggi_evento(request.headers.get("X-Patreon-Event"), corpo)
        if evento is None:
            return web.json_response({"ok": True, "evento": False})
        try:
            nuovo = await applica_evento(evento, corpo)
        except Exception:
            logger.exception("Evento Patreon non applicato.")
            return web.json_response({"error": "errore interno"}, status=500)  # Patreon riprova più tardi
        return web.json_response({"ok": True, "nuovo": bool(nuovo)})

    async def callback(request: web.Request) -> web.Response:
        if troppi(request):
            return web.Response(status=429, text="Troppi tentativi.")
        stato, codice = request.query.get("state", ""), request.query.get("code", "")
        if not stato or not codice or len(stato) > 200 or len(codice) > 400:
            sbagliato(request)
            return web.Response(status=400, text="Richiesta non valida.")
        cookie = request.cookies.get(cookie_sessione, "")
        impronta_sessione = web_panel_logic.impronta(cookie) if cookie and len(cookie) <= 128 else ""
        try:
            await completa_collegamento(stato, codice, impronta_sessione)
        except logica.DaConfermare:
            if url_conferma:
                raise web.HTTPFound(url_conferma) from None
            return web.Response(text="Questo account Patreon è già collegato a un'altra persona: conferma dal pannello.")
        except Exception:  # stato scaduto o usato, codice rifiutato: nessun dettaglio all'esterno
            sbagliato(request)
            logger.warning("Collegamento Patreon rifiutato.", exc_info=True)
            return web.Response(status=400, text="Collegamento non riuscito. Riprova dal pannello.")
        if url_dopo:
            raise web.HTTPFound(url_dopo)
        return web.Response(text="Account Patreon collegato. Puoi chiudere questa pagina.")

    app.router.add_post("/patreon/webhook", webhook)
    app.router.add_get("/patreon/callback", callback)
    return app


async def start_server(app: web.Application, host: str, port: int) -> web.AppRunner:
    runner = web.AppRunner(app, access_log_class=RedactedAccessLogger)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    logger.info("Server Patreon in ascolto su %s:%d", host, port)
    return runner
