# Memoria di dev-web

## Aggiornata
27/10/2026 · ramo `feat/r10aiw` · giro r10 in corso

## In corso
- Giro r10 (agente r10aiw, anche custode-ai): previsione 6 voci. Fatte: 25.20, 25.22, 25.23
  (0350: ai_globale + ai_config.prova_inizio). Prossimi: allineare SPEC C.1-C.5/§24 al codice,
  pagine legali (24.6/C.5), pagina owner (C.4), 25.27 bottone «apri nel pannello».
- Migrazioni riservate r10: 0350-0359.

## Fatto
- r8 59f6215 NF-21, dede8e2 #148, d3cbd81 marchio nel pannello, 3b57822 + 8b8decc
  aspetto (CFG-030/021), 0d8fbe9 «I miei dati» (#46). Nessuna migrazione dopo 0210.
- r6 650d4a2, 7b27a1f, 0d94f23: punto unico `core/config_schema.py`; pannello
  `core/web_panel_server.py` + `web_panel_logic.py` + `panel_bridge.py`,
  pagine in `pannello_web/`, sessioni 0150, wiki, premium (#93); D27.

## Cose imparate
- I test di setup sostituiscono `setup_module.db`: ora anche
  `config_schema_module.db`, e i moduli finti vanno registrati.
- `test_riferimenti_comandi` legge ogni stringa di core: i percorsi del
  pannello (`/accedi`, `/wiki`…) stanno in ECCEZIONI con il motivo.
- aiohttp: chiavi della richiesta con `web.RequestKey`; redirect come
  `web.Response(status=302)`, non restituire `HTTPFound`.
- `_pagina(..., **dati)`: nessun parametro chiamato come una variabile
  del template (`stato` collideva).
- TestClient su 127.0.0.1: `aiohttp.CookieJar(unsafe=True)`.
- Marchio: azioni in `core/whitelabel_bot.py` (`applica_azione`, `collega_e_avvia`),
  gestore dal cog `MarchioCog`; esiti `mar_*` solo da `ESITI_MARCHIO` del ponte.
- Caricamenti nel pannello: `request.multipart()` (non `post()`, che ha il tetto di
  8 KB), Content-Length controllato prima; esiti dei testi del bot in `ESITI_TESTI`.
- #148 (permessi dei comandi) sta in `core/command_permissions.py` (dev-core):
  callback sul server del restore; il pannello lo chiama soltanto.

## Aperto
- #109: il bot del marchio non risponde ai comandi (servirebbe un secondo albero
  di comandi per applicazione: lavoro grosso, da decidere con l'orchestratore).
- Pagine dell'owner (C.4), F13.
- Elenco server in home: solo dalla cache membri del bot (niente fetch).
