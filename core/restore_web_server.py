"""
core/restore_web_server.py
==============================
Il piccolo server web che riceve la callback OAuth2 di Discord dopo
che un utente autorizza il restore (SPEC.md §11.11) — un solo
endpoint, `GET /oauth/callback`, niente di più (nessun pannello,
nessuna sessione: lo "state" nella query string porta già tutto il
contesto necessario, vedi core/restore_oauth_logic.py).

Costruito con `build_app()` che accetta le dipendenze come parametri
(dependency injection) — permette ai test di puntare a un server
Discord finto e a repository in-memory/di test, senza toccare
config.py o i singleton globali.
"""

from __future__ import annotations

import logging

from aiohttp import web

from core.restore_oauth_logic import decode_state
from core.restore_orchestrator import RestoreOrchestrator

logger = logging.getLogger("iyokai.restore_web_server")

# target_guild_id=0 nello stato significa "solo consenso, nessun
# restore da fare ora" (SPEC.md §11.11 modalità A — raccolta del
# token al momento della verifica in un server nuovo, prima che
# esista un qualunque server di destinazione verso cui fare
# guilds.join): l'utente è già dove deve essere, si salva solo il
# token per un eventuale restore futuro.
CONSENT_ONLY_TARGET = 0

PAGINA_OK = """<!doctype html><html><body style="font-family:sans-serif;text-align:center;padding:3em">
<h2>✅ Fatto!</h2><p>{messaggio}</p><p>Puoi chiudere questa pagina.</p></body></html>"""

PAGINA_ERRORE = """<!doctype html><html><body style="font-family:sans-serif;text-align:center;padding:3em">
<h2>⚠️ Qualcosa è andato storto</h2><p>{messaggio}</p></body></html>"""


def build_app(
    *,
    orchestrator: RestoreOrchestrator,
    oauth_repo,
    verify_repo_,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    bot_token: str,
) -> web.Application:
    async def handler_callback(request: web.Request) -> web.Response:
        code = request.query.get("code")
        raw_state = request.query.get("state")
        if not code or not raw_state:
            return web.Response(
                text=PAGINA_ERRORE.format(messaggio="Link incompleto o scaduto."),
                content_type="text/html",
                status=400,
            )

        stato = decode_state(raw_state)
        if stato is None:
            return web.Response(
                text=PAGINA_ERRORE.format(messaggio="Link non valido."),
                content_type="text/html",
                status=400,
            )

        token = await orchestrator.exchange_code_for_token(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            code=code,
        )
        if token is None:
            return web.Response(
                text=PAGINA_ERRORE.format(
                    messaggio="L'autorizzazione con Discord non è riuscita — riprova dal link che hai ricevuto."
                ),
                content_type="text/html",
                status=400,
            )

        await oauth_repo.save_token(
            stato.source_guild_id, stato.user_id, token.access_token, token.refresh_token, token.expires_at
        )

        if stato.target_guild_id == CONSENT_ONLY_TARGET:
            return web.Response(
                text=PAGINA_OK.format(
                    messaggio="Autorizzazione salvata: se un giorno servirà un restore, sarai aggiunto automaticamente."
                ),
                content_type="text/html",
            )

        aggiunto = await orchestrator.join_user_via_oauth(
            bot_token=bot_token,
            guild_id=stato.target_guild_id,
            user_id=stato.user_id,
            access_token=token.access_token,
        )
        if not aggiunto:
            return web.Response(
                text=PAGINA_ERRORE.format(
                    messaggio="Non sono riuscito ad aggiungerti al nuovo server — contatta un amministratore."
                ),
                content_type="text/html",
                status=502,
            )

        config_verifica = await verify_repo_.get_config(stato.target_guild_id)
        if config_verifica is not None and config_verifica.verified_role_id is not None:
            await orchestrator.assign_role(
                bot_token=bot_token,
                guild_id=stato.target_guild_id,
                user_id=stato.user_id,
                role_id=config_verifica.verified_role_id,
            )

        return web.Response(
            text=PAGINA_OK.format(messaggio="Sei stato aggiunto al nuovo server!"),
            content_type="text/html",
        )

    app = web.Application()
    app.router.add_get("/oauth/callback", handler_callback)
    return app


async def start_server(app: web.Application, host: str, port: int) -> web.AppRunner:
    """Avvia il server e restituisce il runner — il chiamante (main.py)
    lo tiene in vita e lo ferma con runner.cleanup() allo shutdown."""
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("Server callback OAuth2 restore in ascolto su %s:%d", host, port)
    return runner
