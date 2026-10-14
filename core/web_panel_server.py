"""
core/web_panel_server.py
========================
Il pannello web (iYokai Panel): accesso con Discord (OAuth2 `identify`,
`state` legato al browser), sessioni nel database, permessi controllati
a ogni richiesta, configurazione dei moduli, dei ruoli del bot e della
lingua dai punti unici dei comandi (D16), storico, premium e wiki dei
comandi. Pagine HTML semplici (Jinja2 con escape automatico, nessuno script).
Funzioni coperte: SPEC §24.1–24.4, §24.7, C.4 (NF-20, issue #91; NF-22, #93)
Dipende da: core/panel_bridge.py, core/web_panel_logic.py,
core/redacted_access_log.py (la query del callback non va nei log)

`build_app()` riceve le dipendenze come parametri: i test usano un
OAuth finto e un bot finto, senza rete.
"""

from __future__ import annotations

import logging
import pathlib
from datetime import datetime, timedelta, timezone
from itertools import groupby

import jinja2
from aiohttp import web

from core import panel_bridge, web_panel_logic as regole
from core.command_search_logic import cerca
from core.config_history_logic import TIPI_MODIFICA
from core.config_schema import ImpostazioneNonValida
from core.redacted_access_log import RedactedAccessLogger

logger = logging.getLogger("iyokai.web_panel")

CARTELLA = pathlib.Path(__file__).resolve().parent.parent / "pannello_web"
DIMENSIONE_MASSIMA_RICHIESTA = 8 * 1024
MAX_RISULTATI_WIKI = 50
CHIAVE_UTENTE = web.RequestKey("utente_id", int)
CHIAVE_TOKEN = web.RequestKey("token", str)
LINGUE = (("it", "Italiano"), ("en", "English"))
ETICHETTE_CATEGORIE = {
    "moderation": "Moderazione", "security": "Sicurezza", "automod": "AutoMod", "logging": "Log",
    "utility": "Utility", "community": "Community", "tickets": "Ticket", "voice": "Vocali",
    "music": "Musica", "leveling": "Livelli ed economia", "fun": "Fun",
}
# Messaggi dopo un salvataggio: si passa solo il codice nell'URL, mai un testo.
ESITI = {
    "salvato": ("Salvato. Il bot usa già la nuova impostazione.", False),
    "invariato": ("Nessun cambiamento: era già così.", False),
    "non_valido": ("Valore non valido: niente è stato salvato.", True),
}


def build_app(
    *,
    bot,
    sessioni,
    oauth,
    client_id: str,
    client_secret: str,
    url_pubblico: str,
    chiave: str,
    ponte=panel_bridge,
) -> web.Application:
    """
    `sessioni`: `WebPanelSessionRepository`. `oauth`: oggetto con
    `exchange_code_for_token(client_id=, client_secret=, redirect_uri=, code=)`
    e `fetch_current_user(access_token)` (in produzione `restore_orchestrator`).
    """
    https = regole.cookie_sicuro(url_pubblico)
    prefisso = "__Host-" if https else ""
    cookie_sessione = prefisso + "iyokai_sessione"
    cookie_state = prefisso + "iyokai_state"
    redirect_uri = regole.url_redirect(url_pubblico)
    origine_ammessa = regole.origine(url_pubblico)
    intestazioni = regole.intestazioni_sicurezza(https)
    limite_generale = regole.LimiteFrequenza(120, 60)
    limite_accesso = regole.LimiteFrequenza(10, 60)
    limite_scritture = regole.LimiteFrequenza(30, 60)
    ambiente = jinja2.Environment(
        loader=jinja2.FileSystemLoader(CARTELLA / "templates"), autoescape=True, enable_async=False
    )
    foglio_stile = (CARTELLA / "static" / "pannello.css").read_bytes()

    # ------------------------------------------------------------ aiuti
    def _cookie(risposta: web.StreamResponse, nome: str, valore: str, durata: int) -> None:
        risposta.set_cookie(
            nome, valore, max_age=durata, path="/", httponly=True, secure=https, samesite="Lax"
        )

    def _pagina(request: web.Request, modello: str, codice_http: int = 200, **dati) -> web.Response:
        esito = ESITI.get(request.query.get("esito", ""))
        contesto = {
            "utente_id": request.get(CHIAVE_UTENTE),
            "csrf": regole.csrf_per(chiave, request[CHIAVE_TOKEN]) if request.get(CHIAVE_TOKEN) else "",
            "messaggio": esito[0] if esito else None,
            "errore": esito[1] if esito else False,
            **dati,
        }
        testo = ambiente.get_template(modello).render(**contesto)
        return web.Response(text=testo, content_type="text/html", status=codice_http)

    def _errore(request: web.Request, codice_http: int, titolo: str, testo: str) -> web.Response:
        return _pagina(request, "errore.html", codice_http, titolo=titolo, testo=testo)

    def _ip(request: web.Request) -> str:
        return regole.ip_cliente(request.remote, request.headers.get("X-Forwarded-For"))

    async def _server(request: web.Request):
        """Il server della richiesta, se l'utente lo può gestire ADESSO. Altrimenti una risposta d'errore."""
        utente_id = request.get(CHIAVE_UTENTE)
        if utente_id is None:
            return None, _vai("/accedi")
        try:
            guild_id = int(request.match_info["guild_id"])
        except ValueError:
            return None, _errore(request, 404, "Server non trovato", "Indirizzo non valido.")
        guild = await ponte.server_gestibile(bot, guild_id, utente_id)
        if guild is None:
            return None, _errore(
                request, 403, "Accesso negato",
                "Non puoi gestire questo server: servono il permesso «Gestisci server» o il ruolo admin del bot, "
                "e il bot deve essere nel server.",
            )
        return guild, None

    async def _modulo_scrittura(request: web.Request):
        """Legge il modulo HTML di una scrittura dopo i controlli: CSRF e limite per utente."""
        form = await request.post()
        if not regole.csrf_valido(chiave, request.get(CHIAVE_TOKEN) or "", form.get("csrf")):
            return None, _errore(request, 403, "Richiesta rifiutata", "Il modulo è scaduto: ricarica la pagina.")
        if not limite_scritture.consenti(f"u:{request[CHIAVE_UTENTE]}"):
            return None, _errore(request, 429, "Troppe modifiche", "Aspetta un minuto e riprova.")
        return form, None

    def _vai(url: str) -> web.Response:
        return web.Response(status=302, headers={"Location": url})

    def _torna(guild_id: int, esito: str) -> web.Response:
        return _vai(f"/server/{guild_id}?esito={esito}")

    # ------------------------------------------------------- middleware
    @web.middleware
    async def sicurezza(request: web.Request, handler):
        try:
            if not limite_generale.consenti(_ip(request)):
                risposta = web.Response(text="Troppe richieste.", status=429)
            elif request.method == "POST" and request.headers.get("Origin") not in (None, origine_ammessa):
                risposta = web.Response(text="Origine non ammessa.", status=403)
            else:
                risposta = await handler(request)
        except web.HTTPException as eccezione:  # 404, 405, 413 di aiohttp
            eccezione.headers.update(intestazioni)
            raise
        except Exception:  # noqa: BLE001 - una pagina d'errore, mai il dettaglio all'utente
            logger.exception("Errore nel pannello web su %s %s", request.method, request.path)
            risposta = web.Response(text="Errore interno.", status=500)
        risposta.headers.update(intestazioni)
        return risposta

    @web.middleware
    async def sessione(request: web.Request, handler):
        token = request.cookies.get(cookie_sessione)
        if token and len(token) <= 128:
            utente_id = await sessioni.utente_della_sessione(regole.impronta(token))
            if utente_id is not None:
                request[CHIAVE_UTENTE] = utente_id
                request[CHIAVE_TOKEN] = token
        return await handler(request)

    # ---------------------------------------------------------- accesso
    async def stile(request: web.Request) -> web.Response:
        return web.Response(body=foglio_stile, content_type="text/css", headers={"Cache-Control": "max-age=3600"})

    async def home(request: web.Request) -> web.Response:
        server = await ponte.server_gestibili(bot, request[CHIAVE_UTENTE]) if request.get(CHIAVE_UTENTE) else []
        return _pagina(request, "home.html", server=server)

    async def accedi(request: web.Request) -> web.StreamResponse:
        if not limite_accesso.consenti(_ip(request)):
            return _errore(request, 429, "Troppi tentativi", "Aspetta un minuto e riprova.")
        state, valore_cookie = regole.nuovo_state(chiave)
        risposta = _vai(regole.url_autorizzazione(client_id, redirect_uri, state))
        _cookie(risposta, cookie_state, valore_cookie, regole.DURATA_STATE_SECONDI)
        return risposta

    async def callback(request: web.Request) -> web.StreamResponse:
        if not limite_accesso.consenti(_ip(request)):
            return _errore(request, 429, "Troppi tentativi", "Aspetta un minuto e riprova.")
        state_ok = regole.state_valido(chiave, request.cookies.get(cookie_state), request.query.get("state"))
        code = request.query.get("code")
        if not state_ok or not code or len(code) > 256:
            risposta = _errore(request, 400, "Accesso non riuscito", "Link scaduto o non valido: riprova da «Accedi».")
            risposta.del_cookie(cookie_state, path="/")
            return risposta
        token = await oauth.exchange_code_for_token(
            client_id=client_id, client_secret=client_secret, redirect_uri=redirect_uri, code=code
        )
        utente_id = await oauth.fetch_current_user(token.access_token) if token is not None else None
        del token  # il token di Discord non si salva: serve solo a sapere chi sei
        if utente_id is None:
            return _errore(request, 400, "Accesso non riuscito", "Discord non ha confermato chi sei: riprova.")
        vecchio = request.cookies.get(cookie_sessione)
        if vecchio:
            await sessioni.elimina(regole.impronta(vecchio))
        nuovo = regole.nuovo_token()
        scade = datetime.now(timezone.utc) + timedelta(seconds=regole.DURATA_SESSIONE_SECONDI)
        await sessioni.crea(regole.impronta(nuovo), utente_id, scade)
        logger.info("Accesso al pannello web dell'utente %s.", utente_id)
        risposta = _vai("/")
        _cookie(risposta, cookie_sessione, nuovo, regole.DURATA_SESSIONE_SECONDI)
        risposta.del_cookie(cookie_state, path="/")
        return risposta

    async def esci(request: web.Request) -> web.StreamResponse:
        form = await request.post()
        token = request.get(CHIAVE_TOKEN)
        if token and regole.csrf_valido(chiave, token, form.get("csrf")):
            await sessioni.elimina(regole.impronta(token))
        risposta = _vai("/")
        risposta.del_cookie(cookie_sessione, path="/")
        return risposta

    # ------------------------------------------------------------ server
    async def pagina_server(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await _server(request)
        if rifiuto is not None:
            return rifiuto
        stato = await ponte.stato_server(guild)
        ordinati = sorted(stato["moduli"], key=lambda m: (m["categoria"], m["titolo"].lower()))
        categorie = [
            (ETICHETTE_CATEGORIE.get(nome, nome or "Altro"), list(moduli))
            for nome, moduli in groupby(ordinati, key=lambda m: m["categoria"])
        ]
        return _pagina(request, "server.html", guild=guild, stato=stato, categorie=categorie, lingue=LINGUE)

    async def salva_modulo(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await _server(request)
        if rifiuto is not None:
            return rifiuto
        form, rifiuto = await _modulo_scrittura(request)
        if rifiuto is not None:
            return rifiuto
        if form.get("attivo") not in ("0", "1"):
            return _torna(guild.id, "non_valido")
        try:
            cambiato = await ponte.applica_modulo(
                bot, guild, str(form.get("nome", "")), form["attivo"] == "1", request[CHIAVE_UTENTE]
            )
        except ImpostazioneNonValida:
            return _torna(guild.id, "non_valido")
        return _torna(guild.id, "salvato" if cambiato else "invariato")

    async def salva_ruolo(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await _server(request)
        if rifiuto is not None:
            return rifiuto
        form, rifiuto = await _modulo_scrittura(request)
        if rifiuto is not None:
            return rifiuto
        testo = str(form.get("ruolo_id", ""))
        if testo and (not testo.isdigit() or len(testo) > 20):
            return _torna(guild.id, "non_valido")
        try:
            await ponte.applica_ruolo(guild, str(form.get("tipo", "")), int(testo) if testo else None, request[CHIAVE_UTENTE])
        except ImpostazioneNonValida:
            return _torna(guild.id, "non_valido")
        return _torna(guild.id, "salvato")

    async def salva_lingua(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await _server(request)
        if rifiuto is not None:
            return rifiuto
        form, rifiuto = await _modulo_scrittura(request)
        if rifiuto is not None:
            return rifiuto
        try:
            await ponte.applica_lingua(guild, str(form.get("lingua", "")), request[CHIAVE_UTENTE])
        except ImpostazioneNonValida:
            return _torna(guild.id, "non_valido")
        return _torna(guild.id, "salvato")

    async def pagina_storico(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await _server(request)
        if rifiuto is not None:
            return rifiuto
        tipo = request.query.get("tipo") if request.query.get("tipo") in TIPI_MODIFICA else None
        voci = await ponte.storico(guild.id, tipo)
        return _pagina(request, "storico.html", guild=guild, voci=voci, tipi=TIPI_MODIFICA, tipo=tipo)

    async def pagina_premium(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await _server(request)
        if rifiuto is not None:
            return rifiuto
        return _pagina(request, "premium.html", guild=guild, premium=await ponte.stato_premium(bot, guild))

    # -------------------------------------------------------------- wiki
    async def wiki(request: web.Request) -> web.Response:
        q = request.query.get("q", "").strip()[:100]
        comandi = ponte.comandi_del_bot(bot)
        if q:
            comandi = cerca(q, comandi, limite=MAX_RISULTATI_WIKI)
        return _pagina(request, "wiki.html", comandi=comandi, q=q)

    async def wiki_comando(request: web.Request) -> web.Response:
        percorso = request.match_info["percorso"].strip("/").replace("/", " ")
        for comando in ponte.comandi_del_bot(bot):
            if comando.percorso == percorso:
                return _pagina(request, "comando.html", c=comando)
        return _errore(request, 404, "Comando non trovato", "Questo comando non esiste (più).")

    app = web.Application(middlewares=[sicurezza, sessione], client_max_size=DIMENSIONE_MASSIMA_RICHIESTA)
    app.router.add_get("/static/pannello.css", stile)
    app.router.add_get("/", home)
    app.router.add_get("/accedi", accedi)
    app.router.add_get("/callback", callback)
    app.router.add_post("/esci", esci)
    app.router.add_get(r"/server/{guild_id:\d{1,20}}", pagina_server)
    app.router.add_post(r"/server/{guild_id:\d{1,20}}/modulo", salva_modulo)
    app.router.add_post(r"/server/{guild_id:\d{1,20}}/ruolo", salva_ruolo)
    app.router.add_post(r"/server/{guild_id:\d{1,20}}/lingua", salva_lingua)
    app.router.add_get(r"/server/{guild_id:\d{1,20}}/storico", pagina_storico)
    app.router.add_get(r"/server/{guild_id:\d{1,20}}/premium", pagina_premium)
    app.router.add_get("/wiki", wiki)
    app.router.add_get(r"/wiki/{percorso:[a-z0-9_\-/]{1,120}}", wiki_comando)
    return app


async def start_server(app: web.Application, host: str, port: int) -> web.AppRunner:
    """Avvia il pannello; il chiamante (main.py) lo ferma con runner.cleanup()."""
    runner = web.AppRunner(app, access_log_class=RedactedAccessLogger)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    logger.info("Pannello web in ascolto su %s:%d", host, port)
    return runner
