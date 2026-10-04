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
Dipende da: core/redacted_access_log.py (SEC-9), core/role_safety.py (SEC-4/SEC-17)
"""

from __future__ import annotations

import logging

from aiohttp import web

from core.redacted_access_log import RedactedAccessLogger
from core.restore_oauth_logic import (
    RestoreState,
    decode_and_verify_state,
    rilascia_nonce,
    riserva_nonce,
)
from core.restore_orchestrator import RestoreOrchestrator
from core.role_safety import motivo_ruolo_automatico_non_assegnabile

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


def _pagina_errore(messaggio: str, status: int) -> web.Response:
    return web.Response(
        text=PAGINA_ERRORE.format(messaggio=messaggio), content_type="text/html", status=status
    )


def _pagina_ok(messaggio: str) -> web.Response:
    return web.Response(text=PAGINA_OK.format(messaggio=messaggio), content_type="text/html")


def build_app(
    *,
    orchestrator: RestoreOrchestrator,
    oauth_repo,
    verify_repo_,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    bot_token: str,
    oauth_encryption_key: str,
    get_guild,
) -> web.Application:
    """
    `get_guild` è una funzione `(guild_id) -> discord.Guild | None`
    (in produzione `bot.get_guild`): serve solo a ricontrollare il
    ruolo verificato prima di assegnarlo.
    """

    async def handler_callback(request: web.Request) -> web.Response:
        code = request.query.get("code")
        raw_state = request.query.get("state")
        if not code or not raw_state:
            return _pagina_errore("Link incompleto o scaduto.", 400)

        # SEC-3: state firmato e con scadenza — vedi
        # core/restore_oauth_logic.py.
        stato = decode_and_verify_state(raw_state, oauth_encryption_key)
        if stato is None or not riserva_nonce(stato):
            return _pagina_errore(
                "Link non valido, scaduto o già usato — richiedine uno nuovo.", 400
            )

        # BUG-21: il link si consuma solo se tutto è riuscito. Un
        # errore temporaneo (o un account sbagliato) lo lascia valido.
        riuscito = False
        try:
            risposta = await _completa_restore(stato, code)
            riuscito = risposta.status == 200
            return risposta
        finally:
            rilascia_nonce(stato, consumato=riuscito)

    async def _completa_restore(stato: RestoreState, code: str) -> web.Response:
        token = await orchestrator.exchange_code_for_token(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            code=code,
        )
        if token is None:
            return _pagina_errore(
                "L'autorizzazione con Discord non è riuscita — riprova dal link che hai ricevuto.",
                400,
            )

        # SEC-3: l'identità si scopre SOLO ora, chiedendola a Discord
        # con l'access_token appena ottenuto.
        user_id = await orchestrator.fetch_current_user(token.access_token)
        if user_id is None:
            return _pagina_errore(
                "Non sono riuscito a verificare la tua identità con Discord — riprova.", 400
            )

        # SEC-19: lo state dice a chi era destinato il link; se ha
        # autorizzato un altro account, non entra nessuno.
        if user_id != stato.user_id:
            logger.warning(
                "Link di restore destinato a %s aperto dall'account %s: rifiutato.",
                stato.user_id,
                user_id,
            )
            return _pagina_errore(
                "Questo link è stato inviato a un altro account Discord. "
                "Aprilo con l'account che ha ricevuto il messaggio.",
                403,
            )

        # SEC-19: save_token non tocca un utente in blacklist da ban e
        # restituisce False — non entra e non torna "active".
        salvato = await oauth_repo.save_token(
            stato.source_guild_id, user_id, token.access_token, token.refresh_token, token.expires_at
        )
        if not salvato:
            logger.warning(
                "Restore rifiutato per %s: è in blacklist nel server %s.",
                user_id,
                stato.source_guild_id,
            )
            return _pagina_errore(
                "Non puoi essere ripristinato in questo server — contatta un amministratore.", 403
            )

        if stato.target_guild_id == CONSENT_ONLY_TARGET:
            return _pagina_ok(
                "Autorizzazione salvata: se un giorno servirà un restore, sarai aggiunto automaticamente."
            )

        aggiunto = await orchestrator.join_user_via_oauth(
            bot_token=bot_token,
            guild_id=stato.target_guild_id,
            user_id=user_id,
            access_token=token.access_token,
        )
        if not aggiunto:
            return _pagina_errore(
                "Non sono riuscito ad aggiungerti al nuovo server — riprova tra poco dallo "
                "stesso link, e se non funziona contatta un amministratore.",
                502,
            )

        await _assegna_ruolo_verificato(stato.target_guild_id, user_id)
        return _pagina_ok("Sei stato aggiunto al nuovo server!")

    async def _assegna_ruolo_verificato(guild_id: int, user_id: int) -> None:
        config_verifica = await verify_repo_.get_config(guild_id)
        if config_verifica is None or config_verifica.verified_role_id is None:
            return

        # SEC-4/SEC-17: il ruolo può aver preso permessi pericolosi
        # dopo il /verify setup — si ricontrolla al momento
        # dell'assegnazione. Se non va bene l'utente resta nel server,
        # senza il ruolo.
        motivo_rifiuto = motivo_ruolo_automatico_non_assegnabile(
            get_guild(guild_id), config_verifica.verified_role_id
        )
        if motivo_rifiuto is not None:
            logger.warning(
                "Ruolo verificato %s non assegnato a %s nel server %s dopo il restore: %s",
                config_verifica.verified_role_id,
                user_id,
                guild_id,
                motivo_rifiuto,
            )
            return

        await orchestrator.assign_role(
            bot_token=bot_token,
            guild_id=guild_id,
            user_id=user_id,
            role_id=config_verifica.verified_role_id,
        )

    app = web.Application()
    app.router.add_get("/oauth/callback", handler_callback)
    return app


async def start_server(app: web.Application, host: str, port: int) -> web.AppRunner:
    """Avvia il server e restituisce il runner — il chiamante (main.py)
    lo tiene in vita e lo ferma con runner.cleanup() allo shutdown."""
    # SEC-9: access_log_class redatto — la query string del callback
    # contiene "code"/"state" (OAuth2), non va mai scritta nei log.
    runner = web.AppRunner(app, access_log_class=RedactedAccessLogger)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("Server callback OAuth2 restore in ascolto su %s:%d", host, port)
    return runner
