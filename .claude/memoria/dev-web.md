# Memoria di dev-web

## Aggiornata
29/10/2026 · ramo `feat/r12piatt` · giro r12 (lotto piattaforme; migrazioni 0450-0452; D45-D47)

## In corso
- Giro r12 chiuso a parte: 21.1 (circa 1.100 frasi in 73 cog altrui), 24.2 (moduli senza scheda), 24.5 (immagine di
  benvenuto, rank card, moduli ticket), 21.6 (frasi interne di verifica e canale-trappola).
- Prossimo passo: se serve, schede per altri moduli in `core/config_impostazioni.py::SCHEDE`; poi editor rank card.
- Migrazioni usate: 0450 (hash token webhook), 0451 (app utente), 0452 (desktop). Prossima libera: 0453.
- Smoke da fare (lo lancia l'orchestratore a giro chiuso).

## Fatto
- r12: A) 0450, intent_usage, privacy; B) `cogs/user_app/*` (messaggi, risposte, supporto, impostazioni, divertimento,
  radio, desktop), `core/user_app_*`, `AlberoApp` (15 menu); Activity radio `core/web_panel_attivita.py`;
  D) `desktop/iyokai_desktop` + `core/desktop_*` + `cogs/utility/desktop_menzioni.py`; 24.2 `core/config_impostazioni.py`;
  24.5 `core/web_editor.py`; #147 `scripts/genera_wiki.py` + `core/wiki_statica.py`; 21.6 chiavi `rm_*`, `verify_*`, `trap_*`, `greet_base_*`.
- r10 9306d42 AI/manutenzione; r8 59f6215 NF-21, dede8e2 #148, d3cbd81 marchio, 3b57822 aspetto, 0d8fbe9 «I miei dati»;
  r6 pannello (`core/web_panel_server.py`, `panel_bridge.py`, `config_schema.py`), D27.

## Cose imparate
- `OWNER_ID` e `config` sono congelati: nei test si sostituisce `panel_bridge.e_proprietario`.
- Percorsi di pagine (`/privacy`...) vanno in ECCEZIONI di test_riferimenti_comandi; niente stringhe `/parola` nel codice.
- aiohttp: chiavi della richiesta con `web.RequestKey`; redirect come `web.Response(status=302)`; TestClient su 127.0.0.1 vuole `CookieJar(unsafe=True)`.
- `_pagina(..., **dati)`: nessun parametro chiamato come una variabile del template.
- Le migrazioni numerate girano DOPO le `run_migrations` dei repository.
- discord.py 2.7.1 conta 5 menu per tipo e non crea il comando d'ingresso delle Activity.
- `lingua_utente` solleva senza database: nei cog usare `lingua_risposta(None, user_id)` (tollerante).
- Funzioni passate come argomento predefinito (`apri=webbrowser.open`) non si sostituiscono con monkeypatch: risolvere alla chiamata.
- Mai due pytest insieme sullo stesso database di test: i fallimenti sono falsi.
- Script di aiuto: `.../scratchpad/spec_set.py ID SIMBOLO "testo"` aggiorna la riga SPEC (niente backtick nei testi da shell).

## Aperto
- Da attivare: Activities nel Portal + mappa URL, `SUPPORT_CHANNEL_ID`, `RADIO_STREAM_URL`, ID app della rich presence, scope rpc.
- Produttori di avvisi per Desktop non collegati (giveaway vinti, dirette, avvisi staff): chiamare `core/desktop_eventi.avvisa_utente`.
- Giveaway non esiste come cog: il pannello rapido dello staff non lo include.
- #109: il bot del marchio non risponde ai comandi (secondo albero per applicazione: da decidere).
