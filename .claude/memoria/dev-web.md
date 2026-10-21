# Memoria di dev-web

## Aggiornata
16/10/2026 · ramo `feat/r8web` · giro r8

## In corso
- Previsione r8: 5 voci, mi fermo dopo la 5.
  1. NF-21 #92 verifica web + doppi (migr. 0210) — fatto
  2. #148 nel pannello: stato, link, risincronizza, revoca — fatto
  3. NF-38 #109 pagina del marchio nel pannello — fatto
  4. #122 CFG-030/021 aspetto — comando fatto (`core/bot_aspetto.py`, `/admin premium
     aspetto` in cogs/utility/marchio.py). Prossimo: pagina `/server/{id}/aspetto` nel
     pannello (nick, bio, upload multipart letto a parti: client_max_size è 8 KB)
  5. #46 parte OAuth: controllo di ciò che resta
- Migrazioni riservate: 0210–0219.

## Fatto
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
- #148 (permessi dei comandi) sta in `core/command_permissions.py` (dev-core):
  callback sul server del restore; il pannello lo chiama soltanto.

## Aperto
- #109: il bot del marchio non risponde ai comandi (servirebbe un secondo albero
  di comandi per applicazione: lavoro grosso, da decidere con l'orchestratore).
- Pagine dell'owner (C.4), F13.
- Elenco server in home: solo dalla cache membri del bot (niente fetch).
