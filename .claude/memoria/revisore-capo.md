# Memoria di revisore-capo

## Aggiornata
28/10/2026 · `feat/r11util` (D36 modalità link, D37 ban/addio, 0400). Fatto anche il cacciatore. Corretti: martello prima dell'addio, PNG RGBA grandi, «ruolo» senza ruolo (d4d1e0a); COMMAND_LIST (a56ef5e). APPROVATO, 3 basse nel quaderno; smoke da fare. /gestione 6742/6800.
28/10/2026 · `feat/r11odio` (D35/D39, 0390+0391): fatto anche il cacciatore. Corretti: regex native con varianti e prefissi comuni, testo intero all'AI e niente AI per testi manipolati, risposta rigida, AI ferma senza richiamo, blocco fallito non resta acceso, libreria a proprietari diversi + parole comuni (vedi commit). APPROVATO, smoke da fare (migrazione 0391: suite completa).
28/10/2026 · `feat/r10liv` (livelli/economia r10: SPEC §15 a `[x]`, shop 0340, classifica settimanale, moneta e tassa 0341). Fatto anche il cacciatore. Corretti: minimo pay (0342) e tassa per eccesso (b1c1f45); righe shop controllate prima, codice in DM, scadenze solo server del bot (f92d597); registro (485e139). APPROVATO, smoke da fare.
28/10/2026 · ramo `feat/r10inviti` (link personali, D32, 0380): fatti anche i controlli del cacciatore; fix 8b9426b (permesso del membro, canale pubblico, tetto 500, verifica invito vivo, race tracker), d45c4f2 (COMMAND_LIST). APPROVATO con 4 basse nel quaderno; smoke da fare.
28/10/2026 · `feat/r10aiw` (#95 AI r10, 0350–0351): APPROVATO dopo i fix: comandi AI aperti in prova (b302da0, `richiede_ai`), prova non ripetibile dopo la purga (0be178a, `ai_prove`), elenco comandi (c2b8c98). Smoke da fare (regola owner: lo lancia l'orchestratore). Aperte 2 basse nei quaderni.
21/10/2026 · ramo `feat/r8tkt` (#120 opzioni ticket, #139 AI, migrazione 0220): merge di main (991f977); corretti presa esclusiva/passa/rilascia e note archiviate (bd26b6d), cache opzioni (ad83893), reperibili ricontrollati; test instabile dei due close = doppia lettura in `close`. Esito smoke nel rapporto.
16/10/2026 · r7mod, r7bak (3be8a40), r7liv.
28/10/2026 · `feat/r11eco` (D30 MUSIC_TOKEN_6..20, D38 immagine moneta 0410, D41): cacciatore + revisione. 2 test rossi = test non adeguati all'embed/file (corretti). Fix token music in fila e senza doppioni (5c69d2b). APPROVATO con 3 basse; smoke da fare.
Giri r10 (liv, inviti, aiw, sec, filtro, logt, core, mod) e r8/r9: tutti APPROVATI, basse aperte nel quaderno.

## In corso
- `feat/r11eco`: 3 basse nel quaderno. Migrazione 0410: suite completa a fine giro (orchestratore).
- Rami r10/r9/r8/r7/r6: solo le righe aperte del quaderno alla riconsegna. `f7-quadro` APPROVATO, manca l'unione.

## Fatto
- Letti per intero: giro-mod, r3-*, r4-*, r6*, r7*, r8*, r9*, r10*, r11eco (commit nel quaderno).

## Cose imparate
- Stato globale per (server, utente) in un modulo: nei test va pulito (fixture autouse), altrimenti passa da un test all'altro. Segnali «fatto» si danno DOPO l'invio, non prima.
- safe_open_image può restituire un'immagine senza `format` (RGBA ridotta): il formato si legge dal file.
- Regex native Discord: 10×260 caratteri; prefissi comuni (albero) e niente `\w*` finale fanno spazio; `\b` non scatta dopo un simbolo in fondo. AI come giudice: niente testo tagliato (insulto in coda), JSON rigido, soglie «N server» = N proprietari.
- Controllare il contenuto di ogni commit, non il messaggio. Voci SPEC a `[x]`: confrontare con il catalogo (`revisione/01-analisi/catalogo/`, riga del codice ECO/LIV) se la funzione è completa (D18).
- Ambiente: `source` dello script env in ogni bash; mai riavviare postgres; database proprio per ramo. Regola owner: niente smoke né suite dagli agenti, solo i test dei file toccati, «smoke da fare» nel rapporto.
- Merge di main: conflitti nei documenti e in `comandi.en.json` ("nomi" per SEGMENTO, globale; menu in `menu`); `COMMAND_LIST*` con `scripts/generate_command_list.py`.
- `db._…` usate da un cog = manca una funzione pubblica. Chiavi `SETTING_X` in `SETTINGS_SCHEMA`; tabelle nuove in `core/data_registry.py`; metodi di repo senza chiamanti rompono `test_repository_callers.py`.
- Migrazioni per NOME: mai modificarne una; numeri confrontati su tutti i rami (`git ls-tree` per ramo remoto).
- Peso dei gruppi (D25): script con `_albero_vero`/`conta_caratteri` di `tests/test_command_tree_invariants.py`.
- Mutazioni: su copia; meglio test scritto prima del fix e visto rosso. Test che si blocca: `asyncio.wait(..., timeout=)`.
- Doppio clic: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`. Test instabili: due letture dello stesso stato.
- Giri periodici con `LIMIT`: righe che non si chiudono mai (server lasciato) bloccano le altre; filtrare o chiudere.
- Creazione in due passi (oggetto, poi dati): validare tutto PRIMA del primo passo.
- Arrotondamenti di tasse/percentuali: per difetto si evitano spezzando; per eccesso.
- Task per chiave: uno solo, fermati in `cog_unload`. Finti: `member.roles` vivo; `_FakeGuild` senza `name`; `monkeypatch.setattr(asyncio, "sleep")` è globale.
- `AllowedMentions(roles=...)` ha `everyone=True` di default. Azioni automatiche da un moderatore: tetto = ciò che lui può fare (D28, D29).
- Bot secondario (D15); App utente (`is_guild_integration()` falso = salta ciò che è del server).
- Controllare il contenuto di ogni commit, non il messaggio; testo all'utente che promette una funzione va confrontato col codice. Voci `[x]`: aprire il test citato.
- Ambiente: `source` dello script env in ogni bash; mai riavviare postgres; mai `cd` nello script env. Regola owner: niente smoke né suite, solo test dei file toccati; comandi pytest lunghi in background.
- Risposta cambiata da testo a embed/file: cercare TUTTI i test e i finti `send_message` dei comandi toccati (r11: 2 rossi così).
- `tests/conftest.py` usa lo stesso token finto per tutti: un controllo doppioni sui token obbligatori romperebbe ogni test (e toccare conftest = suite completa).
- Merge di main: conflitti nei documenti e in `comandi.en.json` ("nomi" per SEGMENTO, globale; menu in `menu`); `COMMAND_LIST*` con `scripts/generate_command_list.py` (errore finale innocuo).
- `db._…` usate da un cog = manca una funzione pubblica. Chiavi `SETTING_X` in `SETTINGS_SCHEMA` (solo owner: `CHIAVI_SOLO_PROPRIETARIO`) + `test_config_import_validation.py`. Tabelle nuove in `core/data_registry.py`; metodi senza chiamanti rompono `test_repository_callers.py`.
- Migrazioni per NOME: mai modificarle; numeri e D di DECISIONI confrontati su tutti i rami (`git ls-tree`/`git show <ramo>:`).
- Mutazioni: copia in scratchpad, `python3 -I` con `str.replace` contato, ripristino; meglio test scritto prima del fix e visto rosso. Test appeso: `asyncio.wait(..., timeout=)`.
- Doppio clic: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`; segno sincrono prima del primo await. Test instabili: due letture dello stesso stato.
- Task per chiave: uno solo, fermato in `cog_unload`. Stato in memoria: chi lo svuota, riavvio (es. `music_sessions` svuotata all'avvio).
- Finti: `member.roles` vivo; `fake_member` ha `Permissions.none()`; `Thread.permissions_for` = padre; `monkeypatch.setattr(asyncio, "sleep")` è globale; `monkeypatch.undo()` toglie il pool.
- `AllowedMentions(roles=...)` ha `everyone=True`. Azioni automatiche da un moderatore: tetto = ciò che lui può fare (D28, D29).
- Bot secondari (D15, Mod, marchio, app): cercare OGNI azione chiamata sul principale. App utente: `is_guild_integration()` falso = saltare le cose del server.
- Comandi con più opzioni: tutti i controlli PRIMA del primo salvataggio. Opzioni «vuoto = togli»: Discord non manda testi vuoti.
- Liste/inviti da mostrare: tetto e «e altre N»; inviti del bot per un membro = permesso del membro.

## Aperto
- Domande all'owner: SPEC 23.16, D18 limite ticket per utente, primo DM ModMail, D27, IPv4 = basso (NF-21), D29, SIC-045.
