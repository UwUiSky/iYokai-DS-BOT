"""
core/web_panel_server.py
========================
Il pannello web (iYokai Panel): accesso con Discord (OAuth2 `identify`,
`state` legato al browser), sessioni nel database, permessi controllati
a ogni richiesta, configurazione dei moduli, dei ruoli del bot, dei gruppi di comandi nascosti
per ruolo (#148), del bot con marchio proprio (NF-38), dell'aspetto del bot (CFG-030) e della
lingua dai punti unici dei comandi (D16), storico, premium e wiki dei comandi, «I miei dati»
(copia e richiesta di cancellazione, #46), verifica dei membri dalla pagina web (link firmato,
impronte senza IP), link d'invito personali e inviti (`core/web_panel_inviti.py`),
informativa privacy e termini (pubbliche) e pagina del proprietario del bot
(moduli premium, server, AI in manutenzione).
Pagine HTML semplici (Jinja2 con escape automatico, nessuno script). Unica eccezione: la pagina «radio iYokai»
dentro Discord (`core/web_panel_attivita.py`, B.8), con script propri e il suo riquadro ammesso solo a Discord.
Funzioni coperte: SPEC §24.1–24.4, §24.6, §24.7, C.1–C.5, §4.2–4.3, §23.15, B.8 (NF-20, issue #91; NF-22, #93; NF-21, #92; NF-38, #109; CFG-030, #122; #46; NF-27 r10)
Dipende da: core/panel_bridge.py, core/web_panel_logic.py,
core/redacted_access_log.py (la query del callback non va nei log)

`build_app()` riceve le dipendenze come parametri: i test usano un
OAuth finto e un bot finto, senza rete.
"""

from __future__ import annotations

import hmac
import logging
import pathlib
from datetime import datetime, timedelta, timezone
from itertools import groupby

import jinja2
from aiohttp import BodyPartReader, MultipartReader, web

from core import alt_detection_logic as verifica, panel_bridge, web_panel_attivita, web_panel_inviti, web_panel_logic as regole
from core.bot_aspetto import MAX_IMMAGINE
from core.command_access import RuoloAdminNegato
from core.command_search_logic import cerca
from core.config_history_logic import TIPI_MODIFICA
from core.config_schema import ImpostazioneNonValida
from core.i18n import t
from core.premium_flags import ModuloNonCambiabile
from core.redacted_access_log import RedactedAccessLogger
from core.repositories.data_deletion_request_repo import MOTIVO_MAX

logger = logging.getLogger("iyokai.web_panel")

CARTELLA = pathlib.Path(__file__).resolve().parent.parent / "pannello_web"
DIMENSIONE_MASSIMA_RICHIESTA = 8 * 1024
# Solo il caricamento di un'immagine del profilo: letto a parti, mai con `post()`.
DIMENSIONE_MASSIMA_CARICAMENTO = MAX_IMMAGINE + 64 * 1024
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
    "serve_amministratore": (
        "Per scegliere il ruolo admin del bot serve il permesso «Amministratore» "
        "(o essere il proprietario del server): niente è stato salvato.",
        True,
    ),
    "permessi_ok": ("Permessi dei gruppi di comandi riscritti su Discord.", False),
    "permessi_nessun_ruolo": ("Nessun ruolo del bot scelto: non c'è niente da scrivere.", True),
    "permessi_non_autorizzato": ("Il bot non è autorizzato (o l'autorizzazione è scaduta): premi «Autorizza».", True),
    "permessi_parziale": ("Discord ha rifiutato una parte dei permessi: riprova tra poco.", True),
    "permessi_attendi": ("Una risincronizzazione al minuto per server: aspetta e riprova.", True),
    "permessi_revocati": (
        "Autorizzazione tolta: il bot non scrive più i permessi dei comandi. Per annullarla anche su "
        "Discord, chi l'ha data la toglie da Impostazioni utente → App autorizzate.",
        False,
    ),
    "marchio_collegato": ("Bot collegato. Se non è ancora nel server, usa il link d'invito qui sotto.", False),
    "marchio_non_disponibile": ("Il bot con marchio non è attivo su questo bot: avvisa il proprietario.", True),
    "marchio_attendi": ("Tre collegamenti al minuto per server: aspetta e riprova.", True),
    "ai_consenso": ("Per accendere l'AI devi leggere e accettare il consenso: niente è stato salvato.", True),
    "dati_attendi": ("Una copia dei dati al minuto: aspetta e riprova.", True),
}


def _esito(codice: str) -> tuple[str, bool] | None:
    """Il messaggio di un codice d'esito: quelli del pannello o i testi del bot (gli stessi dei comandi)."""
    if codice in ESITI:
        return ESITI[codice]
    if codice in panel_bridge.ESITI_TESTI:
        return t(codice, "it"), codice not in panel_bridge.ESITI_TESTI_OK
    return None


def build_app(
    *,
    bot,
    sessioni,
    oauth,
    client_id: str,
    client_secret: str,
    url_pubblico: str,
    chiave: str,
    proxy_fidati: frozenset[str] = frozenset(),
    ponte=panel_bridge,
    radio_flusso: str = "",
) -> web.Application:
    """
    `sessioni`: `WebPanelSessionRepository`. `oauth`: oggetto con
    `exchange_code_for_token(client_id=, client_secret=, redirect_uri=, code=)`
    e `fetch_current_user(access_token)` (in produzione `restore_orchestrator`).
    `proxy_fidati`: IP dei reverse proxy di cui si legge `X-Forwarded-For`.
    """
    https = regole.cookie_sicuro(url_pubblico)
    prefisso = "__Host-" if https else ""
    cookie_sessione = prefisso + "iyokai_sessione"
    cookie_state = prefisso + "iyokai_state"
    redirect_uri = regole.url_redirect(url_pubblico)
    origine_ammessa = regole.origine(url_pubblico)
    intestazioni = regole.intestazioni_sicurezza(https)
    limite_generale = regole.LimiteFrequenza(120, 60)
    limite_accesso = regole.LimiteFrequenza(10, 60)  # /accedi e /callback
    # La pagina di verifica ha il suo conto: un raid sulla verifica (o tanti membri dietro lo stesso
    # CGNAT) non deve bloccare l'accesso degli admin al pannello, né il contrario.
    limite_verifica = regole.LimiteFrequenza(30, 60)
    limite_scritture = regole.LimiteFrequenza(30, 60)
    limite_sincronia = regole.LimiteFrequenza(1, 60)  # ogni sincronia sono più chiamate a Discord
    limite_marchio = regole.LimiteFrequenza(3, 60)  # ogni collegamento prova il token con Discord
    limite_esporta = regole.LimiteFrequenza(1, 60)  # come il comando: una copia al minuto per utente
    ambiente = jinja2.Environment(
        loader=jinja2.FileSystemLoader(CARTELLA / "templates"), autoescape=True, enable_async=False
    )
    foglio_stile = (CARTELLA / "static" / "pannello.css").read_bytes()
    file_radio = {  # i soli altri file statici: la pagina «radio iYokai» dentro Discord
        nome: ((CARTELLA / "static" / nome).read_bytes(), tipo)
        for nome, tipo in (("discord-sdk.js", "text/javascript"), ("radio.js", "text/javascript"))
    }
    intestazioni_radio = web_panel_attivita.intestazioni_attivita(https)

    # ------------------------------------------------------------ aiuti
    def _cookie(risposta: web.StreamResponse, nome: str, valore: str, durata: int) -> None:
        risposta.set_cookie(
            nome, valore, max_age=durata, path="/", httponly=True, secure=https, samesite="Lax"
        )

    def _cancella_cookie(risposta: web.StreamResponse, nome: str) -> None:
        # Stessi attributi della creazione: un `__Host-` senza Secure il browser lo ignora.
        risposta.del_cookie(nome, path="/", secure=https, httponly=True, samesite="Lax")

    def _pagina(request: web.Request, modello: str, codice_http: int = 200, **dati) -> web.Response:
        esito = _esito(request.query.get("esito", ""))
        contesto = {
            "utente_id": request.get(CHIAVE_UTENTE),
            "proprietario": ponte.e_proprietario(request.get(CHIAVE_UTENTE)),
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
        return regole.ip_cliente(request.remote, request.headers.get("X-Forwarded-For"), proxy_fidati)

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
        in_discord = web_panel_attivita.e_apertura_attivita(request.path, request.query)
        if in_discord:  # solo qui la pagina può stare in un riquadro di Discord
            risposta.headers.pop("X-Frame-Options", None)
        risposta.headers.update(intestazioni_radio if in_discord else intestazioni)
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

    async def file_statico(request: web.Request) -> web.Response:
        corpo, tipo = file_radio[request.match_info["nome"]]
        return web.Response(body=corpo, content_type=tipo, headers={"Cache-Control": "max-age=3600"})

    async def home(request: web.Request) -> web.Response:
        if web_panel_attivita.e_apertura_attivita(request.path, request.query):
            return pagina_radio()
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
            _cancella_cookie(risposta, cookie_state)
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
        _cancella_cookie(risposta, cookie_state)
        return risposta

    async def esci(request: web.Request) -> web.StreamResponse:
        form = await request.post()
        token = request.get(CHIAVE_TOKEN)
        if token and regole.csrf_valido(chiave, token, form.get("csrf")):
            await sessioni.elimina(regole.impronta(token))
        risposta = _vai("/")
        _cancella_cookie(risposta, cookie_sessione)
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
        permessi = await ponte.stato_permessi_comandi(guild, request[CHIAVE_UTENTE])
        return _pagina(
            request, "server.html", guild=guild, stato=stato, categorie=categorie, lingue=LINGUE, permessi=permessi
        )

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
        except RuoloAdminNegato:
            return _torna(guild.id, "serve_amministratore")
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

    async def salva_permessi(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await _server(request)
        if rifiuto is not None:
            return rifiuto
        form, rifiuto = await _modulo_scrittura(request)
        if rifiuto is not None:
            return rifiuto
        azione = form.get("azione")
        if azione == "revoca":
            await ponte.revoca_permessi_comandi(guild, request[CHIAVE_UTENTE])
            return _torna(guild.id, "permessi_revocati")
        if azione != "sincronizza":
            return _torna(guild.id, "non_valido")
        if not limite_sincronia.consenti(f"g:{guild.id}"):
            return _torna(guild.id, "permessi_attendi")
        return _torna(guild.id, await ponte.risincronizza_permessi(bot, guild))

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

    # ------------------------------------------------- marchio (NF-38)
    async def pagina_marchio(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await _server(request)
        if rifiuto is not None:
            return rifiuto
        return _pagina(request, "marchio.html", guild=guild, marchio=await ponte.stato_marchio(bot, guild))

    async def salva_marchio(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await _server(request)
        if rifiuto is not None:
            return rifiuto
        form, rifiuto = await _modulo_scrittura(request)
        if rifiuto is not None:
            return rifiuto
        indietro = f"/server/{guild.id}/marchio?esito="
        azione = str(form.get("azione", ""))
        if azione == "collega":
            token = str(form.get("token", "")).strip()
            if not 20 <= len(token) <= 120:
                return _vai(indietro + "non_valido")
            if not limite_marchio.consenti(f"g:{guild.id}"):
                return _vai(indietro + "marchio_attendi")
            return _vai(indietro + await ponte.collega_marchio_web(bot, guild, token, request[CHIAVE_UTENTE]))
        testo = str(form.get("testo", "")) if azione == "testo" else None
        return _vai(indietro + await ponte.applica_marchio(bot, guild, azione, testo, request[CHIAVE_UTENTE]))

    # ------------------------------------------- aspetto del bot (CFG-030)
    async def pagina_aspetto(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await _server(request)
        if rifiuto is not None:
            return rifiuto
        return _pagina(request, "aspetto.html", guild=guild, aspetto=await ponte.stato_aspetto(bot, guild))

    async def salva_aspetto(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await _server(request)
        if rifiuto is not None:
            return rifiuto
        form, rifiuto = await _modulo_scrittura(request)
        if rifiuto is not None:
            return rifiuto
        campi = {
            "nick": {"nick": str(form.get("valore", ""))},
            "bio": {"bio": str(form.get("valore", ""))},
            "togli_avatar": {"avatar": None},
            "togli_banner": {"banner": None},
        }.get(str(form.get("azione", "")))
        if campi is None:
            return _vai(f"/server/{guild.id}/aspetto?esito=non_valido")
        esito = await ponte.applica_aspetto(bot, guild, request[CHIAVE_UTENTE], **campi)
        return _vai(f"/server/{guild.id}/aspetto?esito={esito}")

    async def _leggi_caricamento(request: web.Request) -> dict:
        """Le parti del modulo di caricamento. La dimensione totale è già controllata dal chiamante."""
        campi: dict = {}
        # Non `request.multipart()`: aiohttp applicherebbe a ogni parte `client_max_size` (8 KB).
        lettore = MultipartReader(
            request.headers, request.content,
            client_max_size=DIMENSIONE_MASSIMA_CARICAMENTO, max_size_error_cls=web.HTTPRequestEntityTooLarge,
        )
        async for parte in lettore:
            if not isinstance(parte, BodyPartReader) or parte.name not in ("csrf", "tipo", "immagine"):
                raise ValueError("Parte inattesa.")
            dati = await parte.read()
            campi[parte.name] = dati if parte.name == "immagine" else dati[:256].decode("utf-8", "replace")
        return campi

    async def carica_immagine(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await _server(request)
        if rifiuto is not None:
            return rifiuto
        if request.content_length is None or request.content_length > DIMENSIONE_MASSIMA_CARICAMENTO:
            return _errore(request, 413, "File troppo grande", "L'immagine può essere al massimo di 8 MB.")
        try:
            campi = await _leggi_caricamento(request)
        except (ValueError, AssertionError, KeyError):
            return _errore(request, 400, "Richiesta non valida", "Il modulo non è valido: ricarica la pagina.")
        if not regole.csrf_valido(chiave, request.get(CHIAVE_TOKEN) or "", campi.get("csrf")):
            return _errore(request, 403, "Richiesta rifiutata", "Il modulo è scaduto: ricarica la pagina.")
        if not limite_scritture.consenti(f"u:{request[CHIAVE_UTENTE]}"):
            return _errore(request, 429, "Troppe modifiche", "Aspetta un minuto e riprova.")
        tipo, dati = campi.get("tipo"), campi.get("immagine")
        if tipo not in ("avatar", "banner") or not dati:
            return _vai(f"/server/{guild.id}/aspetto?esito=non_valido")
        esito = await ponte.applica_aspetto(bot, guild, request[CHIAVE_UTENTE], **{tipo: dati})
        return _vai(f"/server/{guild.id}/aspetto?esito={esito}")

    # ------------------------------------------------ i miei dati (#46)
    async def pagina_dati(request: web.Request) -> web.StreamResponse:
        if request.get(CHIAVE_UTENTE) is None:
            return _vai("/accedi")
        numero = request.query.get("richiesta", "")
        testo = None
        if numero.isascii() and numero.isdigit() and len(numero) <= 9:  # sta in un INTEGER
            testo = await ponte.testo_richiesta(request[CHIAVE_UTENTE], int(numero))
        return _pagina(request, "dati.html", motivo_max=MOTIVO_MAX, testo_richiesta=testo)

    async def azione_dati(request: web.Request) -> web.StreamResponse:
        if request.get(CHIAVE_UTENTE) is None:
            return _vai("/accedi")
        form, rifiuto = await _modulo_scrittura(request)
        if rifiuto is not None:
            return rifiuto
        utente_id = request[CHIAVE_UTENTE]
        if form.get("azione") == "esporta":
            if not limite_esporta.consenti(f"u:{utente_id}"):
                return _vai("/miei-dati?esito=dati_attendi")
            contenuto, _, _ = await ponte.esporta_dati(utente_id)
            return web.Response(
                body=contenuto, content_type="application/json",
                headers={
                    "Content-Disposition": f'attachment; filename="iyokai-dati-{utente_id}.json"',
                    "Cache-Control": "no-store",
                },
            )
        if form.get("azione") != "cancella":
            return _vai("/miei-dati?esito=non_valido")
        motivo = str(form.get("motivo", "")).strip()[:MOTIVO_MAX] or None
        numero, _ = await ponte.chiedi_cancellazione(utente_id, motivo)
        return _vai(f"/miei-dati?richiesta={numero}")

    # ------------------------------------------------- verifica (NF-21)
    def _token_verifica(request: web.Request):
        token = request.match_info["token"]
        return token, verifica.leggi_token(chiave, token)

    async def pagina_verifica(request: web.Request) -> web.Response:
        if not limite_verifica.consenti(_ip(request)):
            return _errore(request, 429, "Troppi tentativi", "Aspetta un minuto e riprova.")
        token, chi = _token_verifica(request)
        if chi is None:
            return _errore(request, 400, "Link scaduto", "Il link vale 15 minuti: chiedine uno nuovo su Discord.")
        nome, motivo = await ponte.pagina_verifica(bot, *chi)
        if nome is None:
            return _errore(request, 400, "Verifica non disponibile", motivo)
        return _pagina(
            request, "verifica.html", server_nome=nome, token=token,
            campo=verifica.csrf_verifica(chiave, token), giorni=verifica.GIORNI_IMPRONTE,
        )

    async def conferma_verifica(request: web.Request) -> web.Response:
        if not limite_verifica.consenti(_ip(request)):
            return _errore(request, 429, "Troppi tentativi", "Aspetta un minuto e riprova.")
        token, chi = _token_verifica(request)
        form = await request.post()
        if chi is None or not hmac.compare_digest(
            verifica.csrf_verifica(chiave, token), str(form.get("campo", ""))
        ):
            return _errore(request, 400, "Link scaduto", "Il link vale 15 minuti: chiedine uno nuovo su Discord.")
        riuscita, testo = await ponte.verifica_web(
            bot, chiave, *chi, _ip(request),
            request.headers.get("User-Agent"), request.headers.get("Accept-Language"),
        )
        return _pagina(request, "verifica_esito.html", riuscita=riuscita, testo=testo)

    async def pagina_ai(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await _server(request)
        if rifiuto is not None:
            return rifiuto
        return _pagina(request, "ai.html", guild=guild, ai=await ponte.stato_ai(guild))

    async def salva_ai(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await _server(request)
        if rifiuto is not None:
            return rifiuto
        form, rifiuto = await _modulo_scrittura(request)
        if rifiuto is not None:
            return rifiuto
        azione = form.get("azione")
        campi: dict = {}
        if azione == "accendi":
            if form.get("consenso") != "1":  # il testo del consenso va letto e accettato
                return _vai(f"/server/{guild.id}/ai?esito=ai_consenso")
        elif azione == "scelte":
            try:
                campi = {"privacy": str(form.get("privacy", "")), "lunghezza": str(form.get("lunghezza", "")),
                         "conservazione_minuti": int(str(form.get("conservazione_minuti", "")))}
            except ValueError:
                return _vai(f"/server/{guild.id}/ai?esito=non_valido")
        elif azione != "spegni":
            return _vai(f"/server/{guild.id}/ai?esito=non_valido")
        try:
            await ponte.applica_ai(guild, request[CHIAVE_UTENTE], azione, campi)
        except ImpostazioneNonValida:
            return _vai(f"/server/{guild.id}/ai?esito=non_valido")
        return _vai(f"/server/{guild.id}/ai?esito=salvato")

    # ------------------------------------------------ pagine legali e dell'owner
    async def privacy(request: web.Request) -> web.Response:
        return _pagina(request, "privacy.html", **ponte.info_legali())

    async def termini(request: web.Request) -> web.Response:
        return _pagina(request, "termini.html", supporto=ponte.info_legali()["supporto"])

    def _solo_proprietario(request: web.Request):
        """Una risposta di rifiuto se chi chiede non è il proprietario del bot (controllo a ogni richiesta)."""
        utente_id = request.get(CHIAVE_UTENTE)
        if utente_id is None:
            return _vai("/accedi")
        if not ponte.e_proprietario(utente_id):
            return _errore(request, 403, "Accesso negato", "Questa pagina è solo del proprietario del bot.")
        return None

    async def pagina_proprietario(request: web.Request) -> web.StreamResponse:
        rifiuto = _solo_proprietario(request)
        if rifiuto is not None:
            return rifiuto
        return _pagina(request, "proprietario.html", stato=await ponte.stato_proprietario(bot))

    async def salva_premium_proprietario(request: web.Request) -> web.StreamResponse:
        rifiuto = _solo_proprietario(request)
        if rifiuto is not None:
            return rifiuto
        form, rifiuto = await _modulo_scrittura(request)
        if rifiuto is not None:
            return rifiuto
        if form.get("attivo") not in ("0", "1"):
            return _vai("/proprietario?esito=non_valido")
        try:
            await ponte.applica_premium_modulo(str(form.get("nome", ""))[:100], form["attivo"] == "1", request[CHIAVE_UTENTE])
        except ModuloNonCambiabile:
            return _vai("/proprietario?esito=non_valido")
        return _vai("/proprietario?esito=salvato")

    async def salva_ai_proprietario(request: web.Request) -> web.StreamResponse:
        rifiuto = _solo_proprietario(request)
        if rifiuto is not None:
            return rifiuto
        form, rifiuto = await _modulo_scrittura(request)
        if rifiuto is not None:
            return rifiuto
        if form.get("attivo") not in ("0", "1"):
            return _vai("/proprietario?esito=non_valido")
        await ponte.applica_manutenzione_ai(form["attivo"] == "1", str(form.get("messaggio", ""))[:300], request[CHIAVE_UTENTE])
        return _vai("/proprietario?esito=salvato")

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
    app.router.add_get(r"/static/{nome:discord-sdk\.js|radio\.js}", file_statico)
    pagina_radio = web_panel_attivita.registra_rotte(
        app, ambiente=ambiente, client_id=client_id, flusso=radio_flusso, testo_spenta="La radio è spenta."
    )
    app.router.add_get("/", home)
    app.router.add_get("/accedi", accedi)
    app.router.add_get("/callback", callback)
    app.router.add_post("/esci", esci)
    app.router.add_get(r"/server/{guild_id:\d{1,20}}", pagina_server)
    app.router.add_post(r"/server/{guild_id:\d{1,20}}/modulo", salva_modulo)
    app.router.add_post(r"/server/{guild_id:\d{1,20}}/ruolo", salva_ruolo)
    app.router.add_post(r"/server/{guild_id:\d{1,20}}/lingua", salva_lingua)
    app.router.add_post(r"/server/{guild_id:\d{1,20}}/permessi", salva_permessi)
    app.router.add_get(r"/server/{guild_id:\d{1,20}}/storico", pagina_storico)
    app.router.add_get(r"/server/{guild_id:\d{1,20}}/premium", pagina_premium)
    app.router.add_get(r"/server/{guild_id:\d{1,20}}/marchio", pagina_marchio)
    app.router.add_post(r"/server/{guild_id:\d{1,20}}/marchio", salva_marchio)
    app.router.add_get(r"/server/{guild_id:\d{1,20}}/aspetto", pagina_aspetto)
    app.router.add_post(r"/server/{guild_id:\d{1,20}}/aspetto", salva_aspetto)
    app.router.add_post(r"/server/{guild_id:\d{1,20}}/aspetto/immagine", carica_immagine)
    app.router.add_get("/miei-dati", pagina_dati)
    app.router.add_post("/miei-dati", azione_dati)
    app.router.add_get(r"/verifica/{token:[0-9a-f\-]{1,200}}", pagina_verifica)
    app.router.add_post(r"/verifica/{token:[0-9a-f\-]{1,200}}", conferma_verifica)
    app.router.add_get(r"/server/{guild_id:\d{1,20}}/ai", pagina_ai)
    app.router.add_post(r"/server/{guild_id:\d{1,20}}/ai", salva_ai)
    app.router.add_get("/privacy", privacy)
    app.router.add_get("/termini", termini)
    app.router.add_get("/proprietario", pagina_proprietario)
    app.router.add_post("/proprietario/premium", salva_premium_proprietario)
    app.router.add_post("/proprietario/ai", salva_ai_proprietario)
    app.router.add_get("/wiki", wiki)
    app.router.add_get(r"/wiki/{percorso:[a-z0-9_\-/]{1,120}}", wiki_comando)
    web_panel_inviti.registra_rotte(
        app, bot=bot, pagina=_pagina, errore=_errore, server=_server, scrittura=_modulo_scrittura, ip=_ip,
        chiave_utente=CHIAVE_UTENTE,
    )
    return app


async def start_server(app: web.Application, host: str, port: int) -> web.AppRunner:
    """Avvia il pannello; il chiamante (main.py) lo ferma con runner.cleanup()."""
    runner = web.AppRunner(app, access_log_class=RedactedAccessLogger)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    logger.info("Pannello web in ascolto su %s:%d", host, port)
    return runner
