"""
core/custom_webhook_server.py
=================================
Il piccolo server web che riceve i webhook custom in ingresso da
servizi terzi (SPEC.md §10.8, la parte "webhook" — la parte RSS/Atom
vive già in core/feed_watcher.py, che invece fa polling). Un solo
endpoint, `POST /webhook/<token>`: il token nell'URL identifica sia
il server sia il canale di destinazione, e il corpo JSON della
richiesta diventa il messaggio pubblicato (core.custom_webhook_
logic.render_webhook_message).

Stesso principio già usato per la callback OAuth2 del restore
(SPEC.md §11.11, core/restore_web_server.py): `build_app()` accetta
le dipendenze come parametri (repository + bot), niente singleton
importati direttamente qui dentro, così i test possono passare un
bot/repository finti senza toccare config.py.
"""

from __future__ import annotations

import logging

from aiohttp import web

logger = logging.getLogger("iyokai.custom_webhook_server")


def build_app(*, webhook_repo, get_channel) -> web.Application:
    """
    `get_channel` è una funzione `(channel_id) -> canale | None` —
    passata come parametro invece del bot intero, così un test può
    fornire una funzione finta senza costruire un bot/guild veri
    (lo stesso motivo per cui build_app di restore_web_server accetta
    l'orchestrator già pronto invece del bot).
    """

    async def handler_webhook(request: web.Request) -> web.Response:
        from core.custom_webhook_logic import render_webhook_message

        token = request.match_info["token"]
        webhook = await webhook_repo.get_by_token(token)
        if webhook is None:
            return web.json_response({"error": "webhook non trovato"}, status=404)

        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"error": "corpo JSON non valido"}, status=400)

        canale = get_channel(webhook.channel_id)
        if canale is None:
            logger.warning(
                "Webhook %s (guild %s): canale %s non raggiungibile — il bot potrebbe "
                "essere stato rimosso dal server o il canale eliminato.",
                webhook.id, webhook.guild_id, webhook.channel_id,
            )
            return web.json_response(
                {"error": "il canale di destinazione non è più raggiungibile"}, status=502
            )

        messaggio = render_webhook_message(webhook.message_template, webhook.label, payload)
        await canale.send(messaggio)

        return web.json_response({"ok": True}, status=200)

    app = web.Application()
    app.router.add_post("/webhook/{token}", handler_webhook)
    return app


async def start_server(app: web.Application, host: str, port: int) -> web.AppRunner:
    """Avvia il server e restituisce il runner — il chiamante (main.py)
    lo tiene in vita e lo ferma con runner.cleanup() allo shutdown."""
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("Server webhook custom in ascolto su %s:%d", host, port)
    return runner
