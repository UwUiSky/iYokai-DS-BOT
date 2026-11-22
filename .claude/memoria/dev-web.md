# Memoria di dev-web

## Aggiornata
22/11/2026 · ramo `feat/r2web` · giro r2web (migrazione 0753; D107)

## In corso
- Giro r2web chiuso (5 voci su 5). Ramo `feat/r2web`, nessun push. Smoke da fare (lo lancia l'orchestratore).
- Prossimo passo: aggiornamento periodico del tipo di canale Twitch (oggi si ricollega a mano); produttori di avvisi per sicurezza e log; `leveling` e i moduli log non hanno un gruppo in `GRUPPO_PER_MODULO` (la politica dei comandi non li tocca).
- Migrazioni usate: 0753. Libere: 0754-0759.

## Fatto
- r2web: AI-017 `/ai/interruttori`; BKP-041 `core/web_panel_backup.py`; TKT-085 `core/web_panel_ticket.py`; ALR-049 `core/web_panel_ruoli_collegati.py`, `ruoli_collegati_logic/rete`, repo, 0753; 24.2 schede log e livelli. Test: `tests/test_panel_backup|ticket|ruoli_collegati.py`.
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

- Pagine che portano un `guild_id`: la scheda del ticket e della copia si cerca per id e si confronta con `guild.id` (stessa 404 per «non esiste» e «non puoi»).
- I `state` OAuth di ruoli collegati sono monouso in memoria (un solo processo) e portano l'utente della sessione.

## Aperto
- Da attivare: Activities nel Portal + mappa URL, `SUPPORT_CHANNEL_ID`, `RADIO_STREAM_URL`, ID app della rich presence, scope rpc.
- Produttori di avvisi per Desktop non collegati (giveaway vinti, dirette, avvisi staff): chiamare `core/desktop_eventi.avvisa_utente`.
- ALR-049 fatta in r2web con rete finta nei test: la prova dal vivo (console Twitch, Developer Portal) è in VERIFICA_LIVE. Email degli avvisi: nessun servizio di posta.
- `tests/test_riferimenti_comandi.py` fallisce già su main per `cogs/leveling/negozio_extra.py:5` (non mio).
- Giveaway non esiste come cog: il pannello rapido dello staff non lo include.
- #109: il bot del marchio non risponde ai comandi (secondo albero per applicazione: da decidere).
