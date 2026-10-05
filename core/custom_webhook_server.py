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

SEC-14/BUG-33: ogni token ha un limite di richieste per finestra
mobile (core/webhook_rate_tracker.py), e ogni IP un limite di
tentativi con token inesistenti; entrambi controllati prima di
interrogare il database.
Dipende da: core/redacted_access_log.py (SEC-9), core/webhook_rate_tracker.py (SEC-14)
"""

# DA FARE (issue #67, fase F1): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §11 (Feed e alert).

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from aiohttp import web

from core.redacted_access_log import RedactedAccessLogger
from core.webhook_rate_tracker import (
    WEBHOOK_RATE_LIMIT_MAX_REQUESTS,
    WEBHOOK_RATE_LIMIT_WINDOW_SECONDS,
    WEBHOOK_UNKNOWN_TOKEN_LIMIT_PER_IP,
    webhook_rate_tracker,
)

logger = logging.getLogger("iyokai.custom_webhook_server")

_INDIRIZZI_LOCALI = ("127.0.0.1", "::1")


def _ip_del_client(request: web.Request) -> str | None:
    """
    L'IP da usare per il limite sui token inesistenti. Con il reverse
    proxy sulla stessa macchina (installazione prevista: WEB_BIND_HOST
    = 127.0.0.1) la connessione arriva sempre da 127.0.0.1, quindi si
    prende l'ULTIMO indirizzo di X-Forwarded-For: è quello aggiunto dal
    proxy, i precedenti li può scrivere il client. Se il proxy non
    manda l'header restituisce None (nessun limite per IP): un limite
    unico condiviso da tutti i client permetterebbe a uno solo di
    bloccare gli altri.
    """
    if request.remote not in _INDIRIZZI_LOCALI:
        return request.remote
    inoltrati = request.headers.get("X-Forwarded-For", "")
    return inoltrati.rsplit(",", 1)[-1].strip() or None


def _troppe_richieste(messaggio: str) -> web.Response:
    return web.json_response({"error": messaggio}, status=429)


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
        ora = datetime.now(timezone.utc)
        finestra = WEBHOOK_RATE_LIMIT_WINDOW_SECONDS
        chiave_token = f"token:{token}"
        ip = _ip_del_client(request)
        chiave_ip = f"ip:{ip}" if ip else None

        # BUG-33: i due controlli economici PRIMA della query. Un token
        # già oltre il limite, o un IP che ha già sbagliato token
        # troppe volte, non arriva al database.
        if (
            webhook_rate_tracker.count_recent(chiave_token, ora, finestra)
            >= WEBHOOK_RATE_LIMIT_MAX_REQUESTS
        ):
            return _troppe_richieste("troppe richieste per questo webhook, riprova più tardi")
        if (
            chiave_ip is not None
            and webhook_rate_tracker.count_recent(chiave_ip, ora, finestra)
            >= WEBHOOK_UNKNOWN_TOKEN_LIMIT_PER_IP
        ):
            return _troppe_richieste("troppi tentativi con token non validi, riprova più tardi")

        webhook = await webhook_repo.get_by_token(token)
        if webhook is None:
            if chiave_ip is not None:
                webhook_rate_tracker.allow(
                    chiave_ip, ora, WEBHOOK_UNKNOWN_TOKEN_LIMIT_PER_IP, finestra
                )
            return web.json_response({"error": "webhook non trovato"}, status=404)

        # SEC-14: limite per token. Si registra solo ora che il token
        # è valido e solo se la richiesta viene accettata (BUG-33):
        # un token sbagliato o una richiesta rifiutata non consumano
        # "credito" di un token vero.
        if not webhook_rate_tracker.allow(
            chiave_token, ora, WEBHOOK_RATE_LIMIT_MAX_REQUESTS, finestra
        ):
            return _troppe_richieste("troppe richieste per questo webhook, riprova più tardi")

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
        if not messaggio.strip():
            return web.json_response(
                {"error": "il messaggio risulta vuoto: manda almeno un campo di testo"},
                status=422,
            )

        try:
            await canale.send(messaggio)
        except discord.HTTPException as exc:
            # Forbidden (il bot non può scrivere nel canale) o un
            # rifiuto di Discord: risposta JSON pulita, mai un 500.
            logger.warning(
                "Webhook %s (guild %s): invio nel canale %s non riuscito: %s",
                webhook.id, webhook.guild_id, webhook.channel_id, exc,
            )
            return web.json_response(
                {"error": "Discord non ha accettato il messaggio nel canale di destinazione"},
                status=502,
            )

        return web.json_response({"ok": True}, status=200)

    app = web.Application()
    app.router.add_post("/webhook/{token}", handler_webhook)
    return app


async def start_server(app: web.Application, host: str, port: int) -> web.AppRunner:
    """Avvia il server e restituisce il runner — il chiamante (main.py)
    lo tiene in vita e lo ferma con runner.cleanup() allo shutdown."""
    # SEC-9: access_log_class redatto — l'URL contiene il token
    # segreto del webhook (/webhook/<token>), non va mai scritto per
    # intero nei log.
    runner = web.AppRunner(app, access_log_class=RedactedAccessLogger)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("Server webhook custom in ascolto su %s:%d", host, port)
    return runner
