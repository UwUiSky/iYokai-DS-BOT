# Memoria di dev-web

## Aggiornata
28/10/2026 · ramo `feat/r12piatt` · giro r12 (lotto piattaforme, 34 voci; migrazioni 0450-0479, D45-D47)

## In corso
- Ordine: A core/privacy [fatto: 2.4, 19.7-19.9, 24.6, C.5] -> B iYokai App (B.2, B.5-B.10) -> D Desktop
  (`desktop/` + API server `core/desktop_*`) -> 24.2/24.5/#147 genera_wiki -> 21.1/21.6 catalogo it/en.
- Fine giro: SPEC (simboli), REGISTRO_RISOLTE, VERIFICA_LIVE («giro r12 — piattaforme»), «smoke da fare».
- Migrazioni usate: 0450 (token webhook come impronta). Prossima libera: 0451.

## Fatto
- r12: 0450 webhook hash, `core/intent_usage.py` + `docs/INTENT_PRIVILEGIATI.md`, SPEC 2.4/19.7-19.9/24.6/C.5.
- r10 9306d42 manutenzione/coda/prova AI; pagine legali, /proprietario; pagina AI e bottone pannello.
- r8 59f6215 NF-21, dede8e2 #148, d3cbd81 marchio, 3b57822 + 8b8decc aspetto, 0d8fbe9 «I miei dati» (#46).
- r6 650d4a2, 7b27a1f, 0d94f23: punto unico `core/config_schema.py`; pannello `core/web_panel_server.py`,
  `web_panel_logic.py`, `panel_bridge.py`, pagine in `pannello_web/`, sessioni 0150, wiki, premium (#93); D27.

## Cose imparate
- `OWNER_ID` e `config` sono congelati: nei test si sostituisce `panel_bridge.e_proprietario`.
- Percorsi di pagine (`/privacy`...) vanno in ECCEZIONI di test_riferimenti_comandi; niente stringhe `/parola` nel codice.
- I test di setup sostituiscono `setup_module.db` e `config_schema_module.db`.
- aiohttp: chiavi della richiesta con `web.RequestKey`; redirect come `web.Response(status=302)`.
- `_pagina(..., **dati)`: nessun parametro chiamato come una variabile del template.
- TestClient su 127.0.0.1: `aiohttp.CookieJar(unsafe=True)`.
- Caricamenti nel pannello: `request.multipart()`, Content-Length controllato prima.
- Le migrazioni numerate girano DOPO le `run_migrations` dei repository: il repo crea la tabella, il file numerato la altera.
- Script di aiuto: `.../scratchpad/spec_set.py ID SIMBOLO "testo"` aggiorna la riga SPEC.

## Aperto
- #109: il bot del marchio non risponde ai comandi (secondo albero per applicazione: da decidere).
- Elenco server in home: solo dalla cache membri del bot (niente fetch).
