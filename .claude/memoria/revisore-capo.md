# Memoria di revisore-capo

## Aggiornata
28/10/2026 · `feat/r10musa`: revisione finita, 5 fix (ffe5cda, 20ab14b, dc12194, 86b9dcf, b3a4d4a), D30 nuova (24/7 in canale vuoto solo premium). APPROVATO; smoke da fare (regola owner: niente smoke dagli agenti).

## In corso
- `feat/r10musa`: 4 basse aperte nel quaderno. D30 da segnalare all'owner. `_torna_sordo` già chiuso (e339198).
- Altri rami: aperti noti in quaderno (r9nsfw 1 bassa, r8web IPv4 da confermare, r8uti 1 bassa, r7mod `_shared.py:192`, r7liv 3 basse, r6mus 1 bassa, r6ai, r6mod). Rami in attesa di riconsegna: righe nel quaderno. `f7-quadro` APPROVATO, manca l'unione.

## Fatto
- Letti per intero: giro-mod, r3-*, r4-*, r6*, r7*, r8tkt, r8web, r8uti, r9nsfw, r9mod, r10musa (dettagli e commit nel quaderno).

## Cose imparate
- Controllare il contenuto di ogni commit, non il messaggio; testo all'utente che promette una funzione va confrontato col codice.
- Ambiente: `source` dello script env in ogni bash; mai riavviare postgres se condiviso; mai `cat > $VAR_VUOTA`.
- Merge di main: conflitti nei documenti e in `comandi.en.json` (chiavi doppie); `COMMAND_LIST*.md` si rigenerano.
- `db._…` usate da un cog = manca una funzione pubblica. Più blocchi: controllare TUTTI i punti sulle stesse tabelle.
- Chiavi `SETTING_X` in `SETTINGS_SCHEMA` (solo owner: `CHIAVI_SOLO_PROPRIETARIO`) + `test_config_import_validation.py`; tabelle nuove in `core/data_registry.py`; metodi di repo senza chiamanti rompono `test_repository_callers.py`.
- Migrazioni tracciate per numero/nome: mai modificarne una; confrontare i numeri di tutti i rami (anche le D di DECISIONI).
- Mutazioni: su COPIA, script `python3 -I` con `str.replace` contato e ripristino; test che si blocca: `asyncio.wait(..., timeout=)`.
- Test instabili: due letture dello stesso stato nello stesso comando.
- Doppio clic: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`.
- Task programmati per chiave: uno solo per chiave (il nuovo annulla il vecchio), fermati in `cog_unload`.
- Finti: `member.roles` vivo non prova un'istantanea; `Thread.permissions_for` = padre; `monkeypatch.setattr(asyncio, "sleep")` è globale; `monkeypatch.undo()` toglie il pool.
- Suite completa: mai. Smoke in background con ciclo `until`; `pkill -f` col testo del comando uccide la propria shell.
- `AllowedMentions(roles=...)` ha `everyone=True` di default. `comandi.en.json` "nomi" è per SEGMENTO, globale.
- Azioni automatiche da un moderatore: tetto = ciò che lui può fare (D28, D29). Ripristini: un «no» salvato come «prima» lascia bloccato.
- Risorse condivise tra server (5 worker): ogni modo di tenerle senza uso va limitato (tetto o premium).
- Opzioni testo «vuoto = togli»: Discord non manda testi vuoti, serve «-».
- Bot secondario (D15) e App utente (`is_guild_integration()` falso = salta tutto ciò che è del server).

## Aperto
- Domande all'owner: SPEC 23.16, D18 limite ticket per utente, primo DM ModMail, D27, IPv4 = basso (NF-21), D29.
