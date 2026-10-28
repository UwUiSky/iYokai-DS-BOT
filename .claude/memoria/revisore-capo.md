# Memoria di revisore-capo

## Aggiornata
27/10/2026 · ramo `feat/r10util` (SPEC §14/§16/§23 a `[x]`, `/gestione benvenuto extra`, contatori, 0330–0331): corretti etichette finestra >45 e ban/reazioni durante un raid (666243d). Esito smoke nel rapporto.

## In corso
- `feat/r10util`: 2 basse aperte (addio + ban doppio, ban per ID annunciato; emoji di altro server accettata). Da far decidere all'owner via VERIFICA_LIVE.
- `feat/r9nsfw`: 1 bassa (tetto promemoria letto-poi-scritto).
- `feat/r8web`: «IPv4 da solo = basso» da confermare all'owner. `feat/r8uti`: 1 bassa (schede senza «vede il canale»). `feat/r8tkt`: 1 bassa accettata.
- `feat/r7mod`: aperti noti in SPEC/REGISTRO; `_shared.py:192` Mod non «il bot stesso» (bassa). `feat/r7liv`: 3 basse. `feat/r6mus`: 1 bassa.
- Rami in attesa di riconsegna (righe nel quaderno): r4-tkt, r4-uti, r4-liv, r3-mus, r3-bak, giro-mod, giro-logt, #66, #67, #147, #76, #146, #134, #135/#136. `f7-quadro` APPROVATO, manca l'unione. Alla riconsegna: solo le righe aperte.
- Aperti bassi: r6ai per dev-ai; r6mod `/antiraid segnala` senza tetto.

## Fatto
- Letti per intero: giro-mod, r3-bak, r3-mus, r4-liv, r4-tkt, r4-uti, r6ai, r6mod, r6web, r6mus, r7bak, r7mod, r7liv, r8uti, r8web, r8tkt, r9nsfw, r9mod, r10util.

## Cose imparate
- Controllare il contenuto di ogni commit, non il messaggio. Voci SPEC passate a `[x]`: cercare nel codice ogni problema dello «Stato» (LIM-x in `LIMITI.md`).
- Ambiente: `source <env>` in ogni bash; mai `$VAR` non definita nei percorsi (`$SCRATCH/..` = `/`). Postgres: mai riavviarlo se altri agenti girano.
- Finestre (Modal): titolo ed etichette ≤ 45, max 5 campi; nessun test globale lo controlla, va scritto nel test della finestra. Comando nuovo: rigenerare `COMMAND_LIST*` con `scripts/generate_command_list.py` (errore finale innocuo).
- Funzioni che mandano messaggi per evento (ingressi, ban, uscite): durante un raid (`raid_in_corso`) niente lavoro in più.
- Merge di main: conflitti nei documenti e in `comandi.en.json` (chiavi doppie); "nomi" è per SEGMENTO, globale; menu del tasto destro in sezione `menu`.
- Funzioni private `db._…` usate da un cog = manca una funzione pubblica. Chiavi `SETTING_X` in `SETTINGS_SCHEMA` (solo owner: `CHIAVI_SOLO_PROPRIETARIO`); tabelle nuove in `core/data_registry.py`; metodi di repo senza chiamanti rompono `test_repository_callers.py`.
- Migrazioni tracciate per NOME: cambi = numero nuovo; confrontare i numeri di tutti i rami (anche D di DECISIONI, con `git show main:`).
- Mutazioni: copia del file in scratchpad, `git show HEAD:file > file`, test, ripristino. Test che si blocca: `asyncio.wait(..., timeout=)`.
- Doppio clic / blocchi: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`. Test instabili: due letture dello stesso stato.
- Task per chiave: uno solo, riferimento tenuto, fermati in `cog_unload`. Stato in memoria: chi lo svuota, riavvio.
- Finti: `member.roles` vivo non prova un'istantanea vecchia; `fake_member` ha `Permissions.none()`; `Thread.permissions_for` eredita; `create_autospec(discord.Thread)`.
- `AllowedMentions(roles=...)` ha `everyone=True` di default; usare `menzioni_ammesse`. `monkeypatch.setattr(asyncio, "sleep")` è globale.
- Bot secondario (D15): cercare OGNI azione della sua area ancora sul principale.
- Azioni automatiche partite da un moderatore: tetto = ciò che lui può fare (D28, D29); ripristini: un «no» salvato come «permesso di prima» lascia bloccato.
- Suite completa: mai. Smoke in background con `nohup`, una sola volta.

## Aperto
- Domande all'owner: SPEC 23.16 (sfondo solo colore), D18 limite ticket per utente, conferma primo DM ModMail, D27, IPv4 = basso (NF-21), D29, addio + ban doppio (r10).
