# Memoria di dev-web

## Aggiornata
14/10/2026 · ramo `feat/r6web` · giro r6 (#91 pannello web)

## In corso
- Niente a metà. Prossimo passo (r7): impostazioni interne dei moduli
  nel pannello, una alla volta, ognuna prima portata in un punto unico
  di `core/` (D16), poi editor visuali (24.5) e pagine legali (24.6).

## Fatto
- r6 (1) 650d4a2: `core/config_schema.py` (imposta_modulo, imposta_lingua_server);
  setup.py e /admin lingua set lo usano.
- r6 (2) 7b27a1f, 0d94f23: pannello `core/web_panel_server.py` + `web_panel_logic.py` +
  `panel_bridge.py`, pagine in `pannello_web/`, sessioni 0150, wiki
  `/wiki`, pagina premium (#93); D27 (pannello nel processo del bot).

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

## Aperto
- Pagine dell'owner (C.4), verify avanzato (C.1–C.3), F13.
- Elenco server in home: solo dalla cache membri del bot (niente fetch).
