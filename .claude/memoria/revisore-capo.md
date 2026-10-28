# Memoria di revisore-capo

## Aggiornata
28/10/2026 · `feat/r10aiw` (#95 AI r10, 0350–0351): APPROVATO dopo i fix: comandi AI aperti in prova (b302da0, `richiede_ai`), prova non ripetibile dopo la purga (0be178a, `ai_prove`), elenco comandi (c2b8c98). Smoke da fare (regola owner: lo lancia l'orchestratore). Aperte 2 basse nei quaderni.
21/10/2026 · ramo `feat/r8tkt` (#120 opzioni ticket, #139 AI, migrazione 0220): merge di main (991f977); corretti presa esclusiva/passa/rilascia e note archiviate (bd26b6d), cache opzioni (ad83893), reperibili ricontrollati; test instabile dei due close = doppia lettura in `close`. Esito smoke nel rapporto.
16/10/2026 · r7mod, r7bak (3be8a40), r7liv.

## In corso
- `feat/r8tkt`: aperto basso accettato (`_ruolo_secondo_ai` spingibile verso «amministratore").
- `feat/r7mod`: aperti noti in SPEC/REGISTRO (log via webhook, invito in /setup, LOG-029). `_shared.py:192` non riconosce Mod come «il bot stesso» (bassa).
- `feat/r7liv`: 3 righe basse nel quaderno; scelta sfondo per tutti in VERIFICA_LIVE da far confermare all'owner.
- `feat/r6mus`: 1 riga bassa (nome playlist non normalizzato) per dev-musica.
- Rami in attesa di riconsegna (righe nel quaderno di ciascuno): `feat/r4-tkt` 23, `feat/r4-uti` 21, `feat/r4-liv` 9, `feat/r3-mus` 8, `feat/r3-bak` 8, `giro-mod` 12, `giro-logt` 11, #66 12, #67 8, #147 6, #76 5+7, #59/#117 2, #146, #134, #135/#136. `f7-quadro`: APPROVATO, manca l'unione. Alla riconsegna: solo le righe aperte.
- Aperti bassi: r6ai (ticket staff, pacchetto, riassumi doppio, vietate) per dev-ai; r6mod `/antiraid segnala` senza tetto.

## Fatto
- F1 del 05/10 unito. Letti per intero: giro-mod, r3-bak, r3-mus, r4-liv, r4-tkt, r4-uti, r6ai, r6mod, r6web, r6mus, r7mod, r7bak, r7liv, r8tkt.
22/10/2026 · ramo `feat/r9nsfw` (#94 NSFW 0240–0241, #107 App, #145, #141): corretti politica comandi per l'app fuori server (229f086), «Segnala» differito (2d41f96), menu in inglese (742b61b), documenti (baca393). Smoke --base main: 809 passati.

## In corso
- `feat/r9nsfw`: aperta 1 bassa (tetto promemoria letto-poi-scritto).
- `feat/r8web`: da confermare all'owner «IPv4 da solo = basso». `feat/r8uti`: 1 bassa (schede senza «vede il canale»).
- `feat/r7mod`: aperti noti in SPEC/REGISTRO; `_shared.py:192` Mod non «il bot stesso» (bassa). `feat/r7liv`: 3 basse. `feat/r6mus`: 1 bassa.
- Rami in attesa di riconsegna (righe nel quaderno): r4-tkt, r4-uti, r4-liv, r3-mus, r3-bak, giro-mod, giro-logt, #66, #67, #147, #76, #59/#117, #146, #134, #135/#136. `f7-quadro` APPROVATO, manca l'unione.
- Aperti bassi: r6ai per dev-ai; r6mod `/antiraid segnala` senza tetto.

## Fatto
- Letti per intero: giro-mod, r3-bak, r3-mus, r4-liv, r4-tkt, r4-uti, r6ai, r6mod, r6web, r6mus, r7bak, r7mod, r7liv, r8web, r8uti, r9nsfw.
22/10/2026 · ramo `feat/r9mod` (#59 ripiego, M 1.10 warn manuali 0250, `/mod opzioni`, lock a tempo, `/mod caso attive`, SIC-040): corretti i 3 lasciati del cacciatore (D29: scala dei warn manuali solo con permessi e gerarchia del moderatore, mai kick/ban in massa; timeout mai accorciato; lock fisso + lock a tempo si sblocca). Esito smoke nel rapporto.

## In corso
- `feat/r9mod`: nessuna riga aperta. D29 da segnalare all'owner.
- `feat/r8web`: da far confermare all'owner «IPv4 da solo = basso» (VERIFICA_LIVE r8).
- `feat/r8uti`: 1 bassa (schede canale/permessi senza controllo «vede il canale»).
- `feat/r7mod`: aperti noti in SPEC/REGISTRO (log via webhook, invito in /setup, LOG-029). `_shared.py:192` non riconosce Mod come «il bot stesso» (bassa).
- `feat/r7liv`: 3 basse nel quaderno; sfondo per tutti da confermare all'owner.
- `feat/r6mus`: 1 bassa (nome playlist non normalizzato).
- Rami in attesa di riconsegna (righe nel quaderno): `feat/r4-tkt` 23, `feat/r4-uti` 21, `feat/r4-liv` 9, `feat/r3-mus` 8, `feat/r3-bak` 8, `giro-mod` 12, `giro-logt` 11, #66 12, #67 8, #147 6, #76 5+7, #146, #134, #135/#136. `f7-quadro`: APPROVATO, manca l'unione. Alla riconsegna: solo le righe aperte.
- Aperti bassi: r6ai (ticket staff, pacchetto, riassumi doppio, vietate); r6mod `/antiraid segnala` senza tetto.

## Fatto
- Letti per intero: giro-mod, r3-bak, r3-mus, r4-liv, r4-tkt, r4-uti, r6ai, r6mod, r6web, r6mus, r7bak, r7mod, r7liv, r8uti, r8web, r9mod.

## Cose imparate
- Controllare il contenuto di ogni commit, non il messaggio. Testo all'utente che promette una funzione va confrontato col codice.
- Ambiente: `source /tmp/claude-0/env_<ramo>.sh` in ogni bash; `python3 -m pytest`; mai `cd` dentro lo script env; mai `cat > $VAR_VUOTA` (aspetta stdin). Postgres giù dopo un riavvio: `service postgresql start` e attendere il recupero (`pg_isready`).
- Merge di main: conflitti a due lati nei documenti e in `comandi.en.json` (unire, controllare chiavi doppie); `COMMAND_LIST*.md` si rigenerano.
- Funzioni private `db._…` usate da un cog = manca una funzione pubblica. Più blocchi: controllare TUTTI i punti sulle stesse tabelle.
- Chiavi `SETTING_X` in `SETTINGS_SCHEMA` (quelle di permessi anche in `CHIAVI_SOLO_PROPRIETARIO`); tabelle nuove in `core/data_registry.py`; metodi di repo senza chiamanti rompono `test_repository_callers.py`. Migrazioni: confrontare i numeri di tutti i rami.
- Mutazioni: su COPIA del file (cp in scratchpad, `python3 -I` con `str.replace`, poi ripristino).
- Test instabili di corsa: cercare DUE letture dello stesso stato nello stesso comando; test deterministico con una lettura finta che cambia lo stato dopo la prima.
- Doppio clic / blocchi: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`; blocco tolto senza test rosso = test mancante.
- Presa esclusiva / ruoli self-service / reperibili: ricontrollare i permessi al momento dell'uso; chi perde la presa perde i permessi personali.
- Task programmati per chiave: uno solo per chiave, il nuovo annulla il vecchio.
- Finti: `member.roles` vivo non prova un'istantanea vecchia; `Thread.permissions_for` eredita dal padre; thread archiviati non in `get_thread`; `create_autospec(discord.Thread)` per `isinstance`. `Pool.fetchrow` è sola lettura: finto sul `_pool_provider`.
- Suite completa >10 min: mai. Smoke in background con `nohup` e poll ≤119 s; `pkill -f` col testo del comando uccide la propria shell.
- Stato/cache in memoria: chi lo svuota, versione contro leggi-poi-set, cosa succede al riavvio. `AllowedMentions(roles=...)` ha `everyone=True` di default.
- Bot secondario (D15): cercare OGNI azione della sua area ancora chiamata sul principale.
- Prove gratuite/sblocchi temporanei: controllare TUTTI i cancelli (decoratori `requires_module` compresi) e cosa sopravvive alla purga del server.
- `locales/comandi.en.json` "nomi" è per SEGMENTO, globale: una chiave nuova rinomina ogni comando con quel nome.
- Ruoli che aprono un livello più alto: chi li sceglie deve avere quel livello (D28). Ripristini fatti dal bot: tetto = ruolo più alto di chi lancia.
- DECISIONI: i «casi» di D25 aggiunti da rami diversi vanno numerati contro `git show main:`.
- Stato in memoria: chi lo ripulisce, cosa succede al riavvio; se limite accettato -> VERIFICA_LIVE.
- `AllowedMentions(roles=...)` ha `everyone=True` di default. `monkeypatch.undo()` toglie anche il pool del DB.
- `locales/comandi.en.json` "nomi" è per SEGMENTO, globale: una chiave nuova rinomina ogni comando con quel nome.
- Ruoli che aprono un livello più alto: chi li sceglie deve avere il permesso di quel livello (D28). Caricamenti fatti dal bot: tetto = ruolo più alto di chi lancia.
- Limiti per IP del pannello: un secchio per funzione (accesso, verifica), non condiviso.
- Chiavi `SETTING_X` in `SETTINGS_SCHEMA` (o `SETTINGS_SOLO_OWNER` se solo l'owner le cambia: mai importabili); far girare `test_config_import_validation.py`. Tabelle nuove in `core/data_registry.py`; metodi di repo senza chiamanti rompono `test_repository_callers.py`. Migrazioni: confrontare i numeri di tutti i rami.
- Mutazioni: su COPIA del file, script con `python3 -I`, `str.replace` contato. Un test che con la mutazione si blocca va reso finito (`asyncio.wait(..., timeout=)`), non lasciato appeso.
- `monkeypatch.setattr(modulo.asyncio, "sleep", ...)` cambia asyncio.sleep per tutti: per cedere il turno, future + `call_soon`.
- Tetti in memoria globali (`prenota_uso`): azzerarli nella fixture, o i test dopo il secondo falliscono.
- Bot secondario (D15): cercare OGNI azione della sua area ancora chiamata sul principale.
- DECISIONI: i «casi» di D25 vanno numerati e datati contro `git show main:`.
- Chiavi `SETTING_X` in `SETTINGS_SCHEMA` (o solo owner: `CHIAVI_SOLO_PROPRIETARIO`); `test_config_import_validation.py`. Tabelle nuove in `core/data_registry.py`; metodi di repo senza chiamanti rompono `test_repository_callers.py`.
- Migrazioni tracciate per NOME: una modificata non si riapplica. Cambi = migrazione nuova; confrontare i numeri di tutti i rami (anche le D di DECISIONI, con `git show <ramo>:`).
- Mutazioni: su COPIA del file, script `python3 -I` in scratchpad con `str.replace` contato e ripristino. Test che si blocca con la mutazione: `asyncio.wait(..., timeout=)`.
- Test con id piccoli e `str(x) in str(righe)`: falsi rossi da timestamp. Confrontare i valori.
- Doppio clic / blocchi: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`; blocco tolto senza test rosso = test mancante.
- Task programmati per chiave: uno solo per chiave, riferimento tenuto, fermati in `cog_unload`.
- Finti: `member.roles` vivo non prova un'istantanea vecchia; `Permissions.all()` per admin; `fake_member` ha `Permissions.none()` di base; `timed_out_until` va letto con `getattr` + `isinstance`.
- Suite completa >10 min: mai. Smoke in background con `nohup` e ciclo `until`; `pkill -f` col testo del comando uccide la propria shell.
- `AllowedMentions(roles=...)` ha `everyone=True` di default. `monkeypatch.undo()` toglie anche il pool del DB. `monkeypatch.setattr(asyncio, "sleep")` è globale.
- Bot secondario (D15): cercare OGNI azione della sua area ancora chiamata sul principale.
- `locales/comandi.en.json` "nomi" è per SEGMENTO, globale; categorie nuove in `etichette_categoria`.
- Azioni automatiche partite da un moderatore (scala, ruoli che aprono livelli): tetto = ciò che lui può fare (D28, D29). Le azioni in massa non devono sfuggire ai tetti MOD-002.
- Ripristini (unlock, scadenze): un «no» salvato come «permesso di prima» lascia bloccato. Stessa regola per unlock a mano e scheduler.

- App utente: `is_guild_integration()` falso = server senza l'app. Ogni cosa del server (politica, moduli, quote) va saltata. Menu del tasto destro: nomi inglesi in sezione `menu`, non `nomi`.
## Aperto
- Domande all'owner: SPEC 23.16 (sfondo solo colore), D18 limite ticket per utente, conferma primo DM ModMail, D27.
- Domande all'owner: SPEC 23.16 (sfondo solo colore), D18 limite ticket per utente, conferma primo DM ModMail, D27, IPv4 = basso (NF-21), D29.
