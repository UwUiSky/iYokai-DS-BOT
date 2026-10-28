# Memoria di revisore-capo

## Aggiornata
28/10/2026 · `feat/r11eco` (D30 MUSIC_TOKEN_6..20, D38 immagine moneta 0410, D41): cacciatore + revisione. 2 test rossi = test non adeguati all'embed/file (corretti). Fix token music in fila e senza doppioni (5c69d2b). APPROVATO con 3 basse; smoke da fare.
Giri r10 (liv, inviti, aiw, sec, filtro, logt, core, mod) e r8/r9: tutti APPROVATI, basse aperte nel quaderno.

## In corso
- `feat/r11eco`: 3 basse nel quaderno. Migrazione 0410: suite completa a fine giro (orchestratore).
- Rami r10/r9/r8/r7/r6: solo le righe aperte del quaderno alla riconsegna. `f7-quadro` APPROVATO, manca l'unione.

## Fatto
- Letti per intero: giro-mod, r3-*, r4-*, r6*, r7*, r8*, r9*, r10*, r11eco (commit nel quaderno).

## Cose imparate
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
