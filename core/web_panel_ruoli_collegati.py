"""
core/web_panel_ruoli_collegati.py
=================================
Pagina «Ruoli collegati» del pannello (ALR-049, VER-027): ognuno collega il proprio canale Twitch a Discord, così i server
possono chiedere «affiliato» o «partner» come requisito di un ruolo (Impostazioni del server → Ruoli → Collegamenti), e
collega la verifica (verifica superata, età dell'account, avatar presente) con un solo passo su Discord.
Flusso: accesso al pannello → Twitch (senza permessi in più, `state` firmato) → Discord (scope `role_connections.write`,
`state` firmato) → collegamento scritto con il token di quella persona. La verifica salta il passo di Twitch e usa lo
stesso indirizzo di ritorno di Discord, con un `state` di altro scopo. I token stanno solo cifrati. L'utente del
`state` deve essere quello della sessione; ogni `state` vale una volta. Senza le chiavi di Twitch la pagina lo dice
e il resto del pannello non cambia. Il bot non automatizza account: è il normale OAuth2 di Discord.
Funzioni coperte: SPEC §24.9 (ALR-049, issue #129), §24.11 (VER-027, issue #118)
Dipende da: core/ruoli_collegati_logic.py, core/ruoli_collegati_rete.py, core/ruoli_collegati_verifica.py, core/repositories/ruoli_collegati_repo.py
"""

from __future__ import annotations

import logging
import time

from aiohttp import web
from cryptography.exceptions import InvalidTag

from core import ruoli_collegati_logic as logica, web_panel_logic as regole
from core.oauth_crypto import OAuthEncryptionNotConfigured
from core.repositories.ruoli_collegati_repo import ruoli_collegati_repo
from core.repositories.ruoli_collegati_verifica_repo import CollegamentoVerifica, ruoli_collegati_verifica_repo
from core.ruoli_collegati_verifica import corpo_unico
from core.ruoli_collegati_logic import leggi_configurazione  # noqa: F401 - si sostituisce nei test
from core.ruoli_collegati_rete import ReteRuoliCollegati

logger = logging.getLogger("iyokai.web_panel_ruoli_collegati")

ETICHETTE_TIPO = {"affiliate": "affiliato", "partner": "partner", "": "nessun tipo (né affiliato né partner)"}
PAUSA_METADATI = 600  # secondi tra due tentativi di registrare i metadati


def crea_rete(cfg: logica.Configurazione, client_id: str, client_secret: str) -> ReteRuoliCollegati:
    return ReteRuoliCollegati(
        twitch_id=cfg.twitch_id, twitch_segreto=cfg.twitch_segreto, discord_id=client_id,
        discord_segreto=client_secret, token_bot=cfg.token_bot,
    )


def registra_rotte(
    app: web.Application, *, pagina, errore, scrittura, chiave_utente, ip, client_id: str, client_secret: str, url_pubblico: str,
) -> None:
    limite = regole.LimiteFrequenza(20, 60)  # per persona: ogni passo parla con Twitch o con Discord
    base_url = url_pubblico.rstrip("/") + "/ruoli-collegati"
    uri_twitch, uri_discord = base_url + "/twitch", base_url + "/discord"
    ultimo_tentativo = {"quando": 0.0, "fatto": False}

    def vai(url: str) -> web.Response:
        return web.Response(status=302, headers={"Location": url})

    def riprova(request: web.Request) -> web.Response:
        return errore(request, 400, "Collegamento non riuscito", "Il collegamento è scaduto o non è valido: riparti da «Collega Twitch».")

    async def registra_metadati(cfg: logica.Configurazione, rete) -> None:
        """Una volta per avvio, e se non va si riprova dopo dieci minuti; un errore non rompe la pagina."""
        adesso = time.monotonic()
        if ultimo_tentativo["fatto"] or adesso - ultimo_tentativo["quando"] < PAUSA_METADATI:
            return
        ultimo_tentativo["quando"] = adesso
        try:
            ultimo_tentativo["fatto"] = await rete.registra_metadati(logica.metadati_applicazione(con_twitch=cfg.pronta))
        except Exception:  # noqa: BLE001
            logger.warning("Ruoli collegati: registrazione dei metadati non riuscita.", exc_info=True)

    def utente_o_accesso(request: web.Request):
        utente = request.get(chiave_utente)
        return (utente, None) if utente is not None else (None, vai("/accedi"))

    async def mostra(request: web.Request) -> web.StreamResponse:
        utente, rifiuto = utente_o_accesso(request)
        if rifiuto is not None:
            return rifiuto
        cfg = leggi_configurazione()
        collegamento = verifica = None
        if cfg.pronta or cfg.verifica_pronta:
            await registra_metadati(cfg, crea_rete(cfg, client_id, client_secret))
        if cfg.pronta:
            collegamento = await ruoli_collegati_repo.stato(utente)
        if cfg.verifica_pronta:
            verifica = await ruoli_collegati_verifica_repo.leggi(utente)
        return pagina(
            request, "ruoli_collegati.html", pronta=cfg.pronta, mancanti=cfg.mancanti(), c=collegamento,
            etichetta=ETICHETTE_TIPO.get(collegamento.tipo if collegamento else "", ""),
            verifica_pronta=cfg.verifica_pronta, v=verifica, eta=logica.eta_giorni(utente),
        )

    async def avvia(request: web.Request) -> web.StreamResponse:
        utente, rifiuto = utente_o_accesso(request)
        if rifiuto is not None:
            return rifiuto
        _, rifiuto = await scrittura(request)
        if rifiuto is not None:
            return rifiuto
        cfg = leggi_configurazione()
        if not cfg.pronta:
            return vai(base_url + "?esito=rc_non_configurato")
        if not limite.consenti(f"rc:{utente}"):
            return errore(request, 429, "Troppi tentativi", "Aspetta un minuto e riprova.")
        state = logica.crea_state(cfg.chiave_cifratura, utente, logica.SCOPO_TWITCH)
        return vai(logica.url_twitch(cfg.twitch_id, uri_twitch, state))

    async def avvia_verifica(request: web.Request) -> web.StreamResponse:
        utente, rifiuto = utente_o_accesso(request)
        if rifiuto is not None:
            return rifiuto
        _, rifiuto = await scrittura(request)
        if rifiuto is not None:
            return rifiuto
        cfg = leggi_configurazione()
        if not cfg.verifica_pronta:
            return vai(base_url + "?esito=rc_verifica_non_configurata")
        if not limite.consenti(f"rc:{utente}"):
            return errore(request, 429, "Troppi tentativi", "Aspetta un minuto e riprova.")
        state = logica.crea_state(cfg.chiave_cifratura, utente, logica.SCOPO_VERIFICA)
        return vai(logica.url_discord(client_id, uri_discord, state))

    async def _controlli(request: web.Request, scopo: str):
        """(utente, cfg, rifiuto): sessione, limite, configurazione, `code` e `state` giusti e dell'utente di questa sessione."""
        utente, rifiuto = utente_o_accesso(request)
        if rifiuto is not None:
            return None, None, rifiuto
        if not limite.consenti(f"rc:{utente}"):
            return None, None, errore(request, 429, "Troppi tentativi", "Aspetta un minuto e riprova.")
        cfg = leggi_configurazione()
        code = request.query.get("code", "")
        pronta = cfg.verifica_pronta if scopo == logica.SCOPO_VERIFICA else cfg.pronta
        if not pronta or not code or len(code) > 512:
            return None, None, riprova(request)
        try:
            dello_state = logica.verifica_state(cfg.chiave_cifratura, request.query.get("state"), scopo)
        except OAuthEncryptionNotConfigured:
            dello_state = None
        if dello_state is None or dello_state != utente:
            return None, None, riprova(request)
        return utente, cfg, None

    async def da_twitch(request: web.Request) -> web.StreamResponse:
        utente, cfg, rifiuto = await _controlli(request, logica.SCOPO_TWITCH)
        if rifiuto is not None:
            return rifiuto
        rete = crea_rete(cfg, client_id, client_secret)
        token = await rete.twitch_scambia(request.query["code"], uri_twitch)
        profilo = logica.leggi_utente_twitch(await rete.twitch_utente(token.access_token)) if token else None
        if token is None or profilo is None:
            return riprova(request)
        twitch_id, login, tipo = profilo
        k = cfg.chiave_cifratura
        await ruoli_collegati_repo.salva_twitch(
            utente, twitch_id, login, tipo, logica.cifra(k, utente, "twitch_token", token.access_token),
            logica.cifra(k, utente, "twitch_refresh", token.refresh_token), token.scade_il,
        )
        del token  # il token non serve oltre: sta cifrato nel database
        return vai(logica.url_discord(client_id, uri_discord, logica.crea_state(k, utente, logica.SCOPO_DISCORD)))

    def _e_della_verifica(request: web.Request) -> bool:
        """Lo `state` è di una collegamento della verifica? (si guarda senza consumarlo: lo consuma `_controlli`)."""
        cfg = leggi_configurazione()
        if not cfg.verifica_pronta:
            return False
        try:
            return logica.verifica_state(cfg.chiave_cifratura, request.query.get("state"), logica.SCOPO_VERIFICA, consuma=False) is not None
        except OAuthEncryptionNotConfigured:
            return False

    async def da_discord_verifica(request: web.Request) -> web.StreamResponse:
        utente, cfg, rifiuto = await _controlli(request, logica.SCOPO_VERIFICA)
        if rifiuto is not None:
            return rifiuto
        rete = crea_rete(cfg, client_id, client_secret)
        token = await rete.discord_scambia(request.query["code"], uri_discord)
        profilo = await rete.discord_profilo(token.access_token) if token else None
        if token is None or profilo is None or profilo[0] != utente:
            return riprova(request)  # il token Discord deve essere di chi è nella sessione
        nuovo = CollegamentoVerifica(utente, await ruoli_collegati_verifica_repo.ha_superato_la_verifica(utente), profilo[1])
        if not await rete.discord_scrivi_collegamento(token.access_token, await corpo_unico(utente, verifica=nuovo)):
            return vai(base_url + "?esito=rc_non_riuscito")
        k = cfg.chiave_cifratura
        await ruoli_collegati_verifica_repo.salva(
            utente, logica.cifra(k, utente, "verifica_token", token.access_token),
            logica.cifra(k, utente, "verifica_refresh", token.refresh_token), token.scade_il, nuovo.verificato, nuovo.avatar_presente,
        )
        logger.info("Ruoli collegati: verifica collegata (utente %s).", utente)
        return vai(base_url + "?esito=rc_verifica_collegata")

    async def da_discord(request: web.Request) -> web.StreamResponse:
        if _e_della_verifica(request):
            return await da_discord_verifica(request)
        utente, cfg, rifiuto = await _controlli(request, logica.SCOPO_DISCORD)
        if rifiuto is not None:
            return rifiuto
        primo = await ruoli_collegati_repo.leggi_twitch(utente)
        if primo is None:
            return riprova(request)
        rete = crea_rete(cfg, client_id, client_secret)
        token = await rete.discord_scambia(request.query["code"], uri_discord)
        if token is None or await rete.discord_utente(token.access_token) != utente:
            return riprova(request)  # il token Discord deve essere di chi è nella sessione
        _, login, tipo = primo
        if not await rete.discord_scrivi_collegamento(token.access_token, await corpo_unico(utente)):
            return vai(base_url + "?esito=rc_non_riuscito")
        k = cfg.chiave_cifratura
        await ruoli_collegati_repo.segna_collegato(
            utente, logica.cifra(k, utente, "discord_token", token.access_token),
            logica.cifra(k, utente, "discord_refresh", token.refresh_token), token.scade_il,
        )
        logger.info("Ruoli collegati: utente %s collegato (%s).", utente, tipo or "nessun tipo")
        return vai(base_url + "?esito=rc_collegato")

    async def scollega(request: web.Request) -> web.StreamResponse:
        utente, rifiuto = utente_o_accesso(request)
        if rifiuto is not None:
            return rifiuto
        _, rifiuto = await scrittura(request)
        if rifiuto is not None:
            return rifiuto
        cfg = leggi_configurazione()
        if cfg.pronta:  # se il token vale ancora, Discord torna a «nessun requisito»; altrimenti basta cancellare
            try:
                cifrato = await ruoli_collegati_repo.leggi_token_discord(utente)
                if cifrato:
                    token = logica.decifra(cfg.chiave_cifratura, utente, "discord_token", cifrato)
                    await crea_rete(cfg, client_id, client_secret).discord_scrivi_collegamento(token, await corpo_unico(utente, escludi_twitch=True))
            except (InvalidTag, OAuthEncryptionNotConfigured, ValueError):
                logger.info("Ruoli collegati: token non leggibile, si cancella solo il collegamento (utente %s).", utente)
        await ruoli_collegati_repo.elimina(utente)
        return vai(base_url + "?esito=rc_scollegato")

    async def scollega_verifica(request: web.Request) -> web.StreamResponse:
        utente, rifiuto = utente_o_accesso(request)
        if rifiuto is not None:
            return rifiuto
        _, rifiuto = await scrittura(request)
        if rifiuto is not None:
            return rifiuto
        cfg = leggi_configurazione()
        riga = await ruoli_collegati_verifica_repo.leggi(utente)
        if riga is not None and cfg.verifica_pronta:  # se il token vale ancora, i valori della verifica spariscono da Discord
            try:
                token = logica.decifra(cfg.chiave_cifratura, utente, "verifica_token", riga.token)
                twitch = await ruoli_collegati_repo.leggi_twitch(utente)
                corpo = logica.corpo_collegamento(twitch[1], twitch[2]) if twitch else logica.corpo_collegamento("", "", con_twitch=False)
                await crea_rete(cfg, client_id, client_secret).discord_scrivi_collegamento(token, corpo)
            except (InvalidTag, OAuthEncryptionNotConfigured, ValueError):
                logger.info("Ruoli collegati: token della verifica non leggibile, si cancella solo il collegamento (utente %s).", utente)
        await ruoli_collegati_verifica_repo.elimina(utente)
        return vai(base_url + "?esito=rc_verifica_scollegata")

    app.router.add_get("/ruoli-collegati", mostra)
    app.router.add_post("/ruoli-collegati/verifica/avvia", avvia_verifica)
    app.router.add_post("/ruoli-collegati/verifica/scollega", scollega_verifica)
    app.router.add_post("/ruoli-collegati/avvia", avvia)
    app.router.add_get("/ruoli-collegati/twitch", da_twitch)
    app.router.add_get("/ruoli-collegati/discord", da_discord)
    app.router.add_post("/ruoli-collegati/scollega", scollega)
