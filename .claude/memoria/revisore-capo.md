# Memoria di revisore-capo

## Aggiornata
27/10/2026 · `feat/r10musa` (musica 24/7, impostazioni musicali, filtri alert 0310): IN PAUSA per l'orchestratore, nessun fix ancora fatto.

## In corso
- `feat/r10musa`, worktree /home/claude/wt/r10musa, env `scratchpad/env_r10musa.sh`. Letto tutto il diff di cogs/ e core/ (non ancora tests/ e documenti).
- Prossimo passo esatto: 1) `cogs/fun/soundboard.py` `_programma_sordo` (r.79): non annulla il task in `_sordi` già presente, e un secondo suono partito mentre il primo è in `send_sound` vede `era_sordo` falso e non sposta il ritorno sordo → fix: annullare il vecchio in `_programma_sordo` e nel `finally` riprogrammare anche se `chiave in self._sordi`; test con due suoni in parallelo in `tests/test_soundboard_play.py`.
- 2) Nonstop (`cogs/music/player.py:1281`): chiunque in vocale tiene un worker per sempre a canale vuoto (memory_guard r.96 e `handle_inactive_player` saltati) → serve tetto (es. uscita dopo N minuti a canale vuoto) o premium/admin; decidere con D nuova.
- 3) `core/music_settings_logic.py` `title_blocked`: solo `.lower()`, aggirabile con accenti/fullwidth/maiuscole Unicode → usare il normalizzatore del filtro r9nsfw (cercare con Grep «normalizz»).
- 4) `core/live_alert_flow.py:73`: filtro/pausa senza avanzare stato; controllare chiamanti nei watcher (lavoro per giro, log) e pausa che non blocca «fine diretta». `feed_watcher` pausa: ok a lettura.
- 5) Poi: `site_not_allowed` con allegati/prefissi, `idle_seconds` solo su player nuovo, voci SPEC passate a [x] (9.1–9.5, 9.11, 9.12, 10.1–10.4, 10.7–10.9) con test, smoke `--base main` una volta.
- Altri rami: aperti noti in quaderno (r9nsfw 1 bassa, r8web IPv4 da confermare, r8uti 1 bassa, r7mod `_shared.py:192`, r7liv 3 basse, r6mus 1 bassa, r6ai, r6mod). Rami in attesa di riconsegna: righe nel quaderno. `f7-quadro` APPROVATO, manca l'unione.

## Fatto
- Letti per intero: giro-mod, r3-*, r4-*, r6*, r7*, r8tkt, r8web, r8uti, r9nsfw, r9mod (dettagli e commit nel quaderno).

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
- Bot secondario (D15) e App utente (`is_guild_integration()` falso = salta tutto ciò che è del server).

## Aperto
- Domande all'owner: SPEC 23.16, D18 limite ticket per utente, primo DM ModMail, D27, IPv4 = basso (NF-21), D29.
