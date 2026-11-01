# Memoria di revisore-capo

## Aggiornata
01/11/2026 · `feat/r12ai` (§25 AI r12, 0420–0429): merge di main (D45 del ramo → D52), cacciatore + revisione. 9 fix (bozze senza dati su GitHub, scelte owner prima di sa_fare, privacy max 10 AI, traduzione piena, cache voce, menu app senza server, prima risposta ticket in compito, D16 canale/vietate, allegati con guild_id). APPROVATO; smoke da fare (migrazioni: suite completa).
28/10/2026 · r11util, r11odio, r11eco, r10liv, r10inviti, r10aiw: APPROVATI dopo i fix (commit nel quaderno), basse aperte; smoke da fare.
Giri r6–r10: tutti APPROVATI, basse aperte nel quaderno.

## In corso
- `feat/r12ai`: 5 basse nel quaderno (bug.md e revisione.md, righe 01/11 r12ai). Migrazioni 0420–0429: suite completa a fine giro (orchestratore).
- `feat/r11eco`: 3 basse nel quaderno. Migrazione 0410: suite completa a fine giro (orchestratore).
- Rami r10/r9/r8/r7/r6: solo le righe aperte del quaderno alla riconsegna. `f7-quadro` APPROVATO, manca l'unione.

## Fatto
- Letti per intero: giro-mod, r3-*, r4-*, r6*, r7*, r8*, r9*, r10*, r11eco (commit nel quaderno).

## Cose imparate
- Jolly/glob in regex (`\S*` ripetuti) = tempo esponenziale: cercare i pezzi da sinistra (lineare). Voci `[x]` di NF-41 e simili: confrontare con «dettagli da non perdere» di VOCI_OMESSE.
- Avvisi/eventi per canale: `permissions_for` di un thread = padre; thread privato = guardare membri/owner/manage_threads; `get_channel` non trova i thread (`get_channel_or_thread`). Pagine web: niente tetto 25 (è dei menu di Discord); tipo del canale come l'opzione del comando.
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
- Due pytest insieme sullo stesso database = test rossi a caso (clean_db svuota): mai test in parallelo nella stessa copia.
- Testo degli utenti verso servizi esterni non AI (GitHub): `pulisci_dati_personali` + chiavi (`per_repo`). Menu di iYokai App: AI con `guild_id=None`.
- Cache su disco con tetto: cercare chi chiama la pulizia. Lavoro AI in un flusso Discord (apertura ticket, elenchi): in un compito a parte o con tetto di chiamate.

## Aperto
- Domande all'owner: SPEC 23.16, D18 limite ticket per utente, primo DM ModMail, D27, IPv4 = basso (NF-21), D29, SIC-045.
