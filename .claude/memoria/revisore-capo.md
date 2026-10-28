# Memoria di revisore-capo

## Aggiornata
28/10/2026 · ramo `feat/r10core` (wizard a passi, premium sblocca, marchio #109, inviti, 21.1, App B.3/B.4 0360, log webhook D33 0361): cacciatore + revisione. Corretti 42e71d4, c636cb1, 294a604, 3a036cb, 3a56c23, f0513ef. APPROVATO con 5 basse aperte nel quaderno. Smoke da fare (regola owner).

## In corso
- `feat/r10core`: 5 basse aperte (round, nomi inglesi /strumenti, livello con modulo spento, sblocca su modulo già incluso, webhook orfano) per dev-core.
- `feat/r9nsfw`: 1 bassa (tetto promemoria letto-poi-scritto). `feat/r8uti`: 1 bassa. `feat/r8web`: «IPv4 = basso» da far confermare.
- `feat/r7mod`: `_shared.py:192` Mod non «il bot stesso» (bassa). `feat/r7liv`: 3 basse. `feat/r6mus`: 1 bassa. r6ai e r6mod: basse per dev-ai/dev-mod.
- Rami in attesa di riconsegna (righe nel quaderno): r4-tkt, r4-uti, r4-liv, r3-mus, r3-bak, giro-mod, giro-logt, #66, #67, #147, #76, #146, #134, #135/#136. `f7-quadro` APPROVATO, manca l'unione. Alla riconsegna: solo le righe aperte.

## Fatto
- Letti per intero: giro-mod, r3-*, r4-*, r6ai, r6mod, r6web, r6mus, r7*, r8*, r9nsfw, r9mod, r10core.

## Cose imparate
- Controllare il contenuto di ogni commit, non il messaggio; testo che promette una funzione va confrontato col codice. Docstring contro test: un test può fissare il bug (file via webhook).
- Ambiente: `source <env>` in ogni bash; mai riavviare postgres se l'orchestratore lo vieta; mai `cd` nello script env.
- Mutazioni: `git stash -q -- <file>` del solo fix, test, `git stash pop`; oppure copia in scratchpad + `python3 -I` con `str.replace` contato.
- Doppio clic su una vista: `BaseView.interaction_check` attende il DB, quindi `stop()` nel callback NON basta. Segno sincrono prima del primo await; test con `asyncio.gather` di due callback.
- Leggi-poi-scrivi e creazioni (webhook, post) per chiave: blocco per chiave; i blocchi asyncio vanno svuotati nella fixture.
- Bot secondari (Mod, marchio, app): cercare OGNI azione chiamata sul principale; interazioni inoltrate vanno filtrate per server.
- discord.py: un `commands.Bot` non collegato ha `_connection.user` None, un'interazione con `guild_id` lo vuole (impostare un `ClientUser`). Il webhook chiude i `File` anche quando fallisce.
- Chiavi `SETTING_X` in `SETTINGS_SCHEMA` (solo owner: `CHIAVI_SOLO_PROPRIETARIO`); tabelle nuove in `core/data_registry.py`; metodi di repo senza chiamanti rompono `test_repository_callers.py`.
- Migrazioni tracciate per NOME: mai modificarle; numeri confrontati con tutti i rami (anche le D di DECISIONI, `git show main:`).
- `COMMAND_LIST*.md`: `scripts/generate_command_list.py` (l'errore finale «not initialised» è innocuo).
- `locales/comandi.en.json` "nomi" è per SEGMENTO, globale; menu del tasto destro in sezione `menu`.
- Azioni automatiche partite da un moderatore: tetto = ciò che lui può fare (D28, D29).
- App utente: `is_guild_integration()` falso = server senza l'app; le cose del server vanno saltate.
- `AllowedMentions(roles=...)` ha `everyone=True` di default. `monkeypatch.setattr(asyncio, "sleep")` è globale.
- Elenchi con tetto alto (100) in un embed: righe intere e «e altre N», mai un taglio a metà.

## Aperto
- Domande all'owner: SPEC 23.16 (sfondo solo colore), D18 limite ticket per utente, primo DM ModMail, D27, IPv4 = basso (NF-21), D29.
