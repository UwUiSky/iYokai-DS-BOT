# Memoria di dev-web

## Aggiornata
20/11/2026 · ramo `feat/r1web` · giro r1web (migrazioni 0750-0752; D99)

## In corso
- Giro r1web chiuso (9 voci su 10; ALR-049 non fatta, D99). Ramo `feat/r1web`, nessun push. Smoke da fare (lo lancia l'orchestratore).
- Prossimo passo: se serve, collegare produttori di avvisi (`core/web_panel_avvisi.avvisa`) alle aree sicurezza e log; portare `/admin-vocali opzioni` su `core/web_panel_vocali.applica` (area vocali).
- Migrazioni usate: 0750 (ruoli del pannello), 0751 (pubblico: statistiche, indirizzo, chiave API), 0752 (avvisi). Prossima libera: 0753 (riservate 0750-0759).

## Fatto
- r1web: CFG-001/002/003/027, VOC-020 (commit 4eca075c); STA-012, LIV-062, STA-061 (5e768769); CFG-006 e carte. File: `core/web_panel_accesso.py`, `web_panel_panoramica.py`, `web_panel_vocali.py`, `web_panel_pubblico.py`, `web_panel_avvisi.py`, `web_panel_pagine.py`, repo `web_panel_ruoli_repo`, `web_panel_pubblico_repo`, `web_panel_avvisi_repo`.
- r12: A) 0450, intent_usage, privacy; B) `cogs/user_app/*`, `core/user_app_*`, `AlberoApp`; Activity radio; D) `desktop/iyokai_desktop` + `core/desktop_*`; 24.2 `core/config_impostazioni.py`; 24.5 `core/web_editor.py`; #147 wiki statica; 21.6 chiavi `rm_*`, `verify_*`, `trap_*`, `greet_base_*`.
- r10 AI/manutenzione; r8 NF-21, #148, marchio, aspetto, «I miei dati»; r6 pannello (`web_panel_server.py`, `panel_bridge.py`, `config_schema.py`), D27.

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

- `_server(request, solo_admin=, personale=)`: GET = lettura, POST = scrittura (+ politica dei comandi); pagine che rendono pubblico qualcosa = solo_admin; preferenze personali = personale.
- Pagine pubbliche e API: limite per IP proprio, 404/401 uguali per «non esiste» e «non puoi»; CSP senza `style=` in linea (barre con `<progress>`).
- Test dei moduli nuovi: importare `ambiente`, `_come`, `_imposta` da `tests/test_panel_accesso.py` (fixture con ruoli e membri finti).

## Aperto
- Da attivare: Activities nel Portal + mappa URL, `SUPPORT_CHANNEL_ID`, `RADIO_STREAM_URL`, ID app della rich presence, scope rpc.
- Produttori di avvisi per Desktop non collegati (giveaway vinti, dirette, avvisi staff): chiamare `core/desktop_eventi.avvisa_utente`.
- ALR-049 (Linked Roles Twitch) non fatta: manca l'OAuth di Twitch (D99). Email degli avvisi: nessun servizio di posta.
- Giveaway non esiste come cog: il pannello rapido dello staff non lo include.
- #109: il bot del marchio non risponde ai comandi (secondo albero per applicazione: da decidere).
