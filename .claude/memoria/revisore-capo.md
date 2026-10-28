# Memoria di revisore-capo

## Aggiornata
27/10/2026 · ramo `feat/r10amod` (#58/#116 AutoMod: parole con modo, inviti permessi/propri, violazioni, escalation che cresce; 0280–0282). Fatto anche il lavoro del cacciatore. Corretti: eccezioni proprie tenute se `guild.invites()` fallisce + invito personalizzato + indice violazioni (7ac974a); fixture con monkeypatch e COMMAND_LIST (95f0902); documenti nel commit dopo. APPROVATO.

## In corso
- `feat/r10amod`: 3 basse aperte nel quaderno (oltre 8 inviti propri, attesa 3 s non annullata, test sic042 dipendente dall'ordine). Migrazione 0282 nuova: suite completa a scelta dell'orchestratore.
- `feat/r9nsfw`: 1 bassa (tetto promemoria letto-poi-scritto). `feat/r9mod`: D29 da segnalare all'owner.
- `feat/r8web`: «IPv4 da solo = basso» da far confermare. `feat/r8uti`: 1 bassa. `feat/r8tkt`: 1 bassa accettata.
27/10/2026 · ramo `feat/r10util` (SPEC §14/§16/§23 a `[x]`, `/gestione benvenuto extra`, contatori, 0330–0331): corretti etichette finestra >45 e ban/reazioni durante un raid (666243d). Esito smoke nel rapporto.

## In corso
- `feat/r10util`: 2 basse aperte (addio + ban doppio, ban per ID annunciato; emoji di altro server accettata). Da far decidere all'owner via VERIFICA_LIVE.
- `feat/r9nsfw`: 1 bassa (tetto promemoria letto-poi-scritto).
- `feat/r8web`: «IPv4 da solo = basso» da confermare all'owner. `feat/r8uti`: 1 bassa (schede senza «vede il canale»). `feat/r8tkt`: 1 bassa accettata.
- `feat/r7mod`: aperti noti in SPEC/REGISTRO; `_shared.py:192` Mod non «il bot stesso» (bassa). `feat/r7liv`: 3 basse. `feat/r6mus`: 1 bassa.
- Rami in attesa di riconsegna (righe nel quaderno): r4-tkt, r4-uti, r4-liv, r3-mus, r3-bak, giro-mod, giro-logt, #66, #67, #147, #76, #146, #134, #135/#136. `f7-quadro` APPROVATO, manca l'unione. Alla riconsegna: solo le righe aperte.
- Aperti bassi: r6ai per dev-ai; r6mod `/antiraid segnala` senza tetto.

## Fatto
- Letti per intero: giro-mod, r3-bak, r3-mus, r4-liv, r4-tkt, r4-uti, r6ai, r6mod, r6web, r6mus, r7bak, r7mod, r7liv, r8tkt, r8uti, r8web, r9mod, r9nsfw, r10amod.

## Cose imparate
- Controllare il contenuto di ogni commit, non il messaggio; testo all'utente che promette una funzione va confrontato col codice. REGISTRO/SPEC: confrontare con ciò che il ramo fa davvero.
- Ambiente: script env in ogni bash; mai riavviare postgres. Lo smoke dello sviluppatore usa lo STESSO database: per i miei test creare un database mio (`CREATE DATABASE iyokai_wrev<ramo>`), o i test si rompono a vicenda.
- Merge di main: conflitti nei documenti e in `comandi.en.json`; `COMMAND_LIST*.md` si rigenerano con `scripts/generate_command_list.py` (l'errore finale del client è innocuo).
- Funzioni `db._…` usate da un cog = manca una funzione pubblica. Chiavi `SETTING_X` in `SETTINGS_SCHEMA`; tabelle nuove in `core/data_registry.py`; metodi senza chiamanti rompono `test_repository_callers.py`.
- Migrazioni tracciate per NOME; numeri da confrontare su tutti i rami (`git ls-tree <ramo> core/migrations/`). Query nuove su tabelle di log: indice.
- Mutazioni: su COPIA, script `python3 -I` con `str.replace` contato, poi ripristino. Test che si blocca: `asyncio.wait(..., timeout=)`.
- Leggi-poi-scrivi e doppio clic: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`. Test instabili: due letture dello stesso stato.
- Task programmati per chiave: uno solo per chiave, fermati in `cog_unload`. Stato in memoria: chi lo svuota, riavvio.
- Finti: `member.roles` vivo; `Permissions.all()` per admin; `Pool.fetchrow` sola lettura (finto sul `_pool_provider`); `create_autospec(Guild)` dà MagicMock per gli attributi: controllare con `isinstance`.
- `AllowedMentions(roles=...)` ha `everyone=True`. `monkeypatch.setattr(asyncio, "sleep")` è globale.
- Bot secondario (D15): ogni azione della sua area. Azioni automatiche partite da un moderatore: tetto = ciò che lui può fare (D28, D29).
- `locales/comandi.en.json` "nomi" è per SEGMENTO, globale; menu del tasto destro in sezione `menu`.
- AutoMod nativo: un errore nel leggere un dato esterno (inviti) non deve svuotare le eccezioni: tenere l'ultimo sync. Vanity non è in `guild.invites()`.
- App utente: `is_guild_integration()` falso = server senza l'app; saltare politica, moduli, quote.

## Aperto
- Domande all'owner: SPEC 23.16 (sfondo solo colore), D18 limite ticket per utente, conferma primo DM ModMail, D27, IPv4 = basso (NF-21), D29.
27/10/2026 · ramo `feat/r10bak` (#68 backup: espressioni, forum/stage, aggiornamento 6 h 0320, mirror in coda, promuovi, webhook con immagine). Fatto anche il giro del cacciatore. Corretti: mirror con `wait=True` e coda che si ferma se il mirror è tolto (b3d6288), riallineamento che non toglie overwrite/etichette e ruoli solo sotto il Creator (4efd6df), mappa mirror scritta solo se la coppia è ancora legata (278c107), VERIFICA_LIVE (f1a8116).

## In corso
- `feat/r10bak`: PAUSA. Fix e test tutti committati e spinti (b04f286). Prossimo passo: leggere lo smoke (`<scratchpad>/revisore/smoke_revisore_r10bak.log`; se incompleto rilanciare UNA volta `python3 scripts/smoke.py --base main`), poi esito APPROVATO se verde. Nessuna riga aperta. Giro di aggiornamento lasciato nel loop dei job apposta (mai due copie insieme).
- `feat/r9nsfw`: 1 bassa (tetto promemoria letto-poi-scritto). `feat/r8uti`: 1 bassa (schede senza «vede il canale»). `feat/r8web`: «IPv4 da solo = basso» da far confermare all'owner.
- `feat/r9mod`: D29 da segnalare all'owner. `feat/r7mod`: aperti in SPEC/REGISTRO; `_shared.py:192` Mod non «il bot stesso» (bassa). `feat/r7liv`: 3 basse. `feat/r6mus`: 1 bassa. `feat/r8tkt`: 1 bassa accettata.
- Rami in attesa di riconsegna (righe nel quaderno): r4-tkt, r4-uti, r4-liv, r3-mus, r3-bak, giro-mod, giro-logt, #66, #67, #147, #76, #146, #134, #135/#136. `f7-quadro` APPROVATO, manca l'unione. Alla riconsegna: solo le righe aperte.
- Aperti bassi: r6ai per dev-ai; r6mod `/antiraid segnala` senza tetto.

## Fatto
- Letti per intero: giro-mod, r3-bak, r3-mus, r4-liv, r4-tkt, r4-uti, r6ai, r6mod, r6web, r6mus, r7bak, r7mod, r7liv, r8tkt, r8uti, r8web, r9nsfw, r9mod, r10bak.

## Cose imparate
- Controllare il contenuto di ogni commit, non il messaggio. Testo all'utente che promette una funzione va confrontato col codice.
- Ambiente: `source <scratchpad>/env_<ramo>.sh` in ogni bash; `python3 -m pytest`; mai riavviare postgres se lo dice la scheda. Smoke una volta sola, in background.
- Merge di main: conflitti nei documenti e in `comandi.en.json` (unire, chiavi doppie); `COMMAND_LIST*.md` si rigenerano.
- Funzioni private importate da un altro modulo = manca un nome pubblico. Più blocchi: controllare TUTTI i punti sulle stesse tabelle.
- Chiavi `SETTING_X` in `SETTINGS_SCHEMA`; tabelle nuove in `core/data_registry.py`; metodi di repo senza chiamanti rompono `test_repository_callers.py`. Migrazioni: confrontare i numeri di tutti i rami (`git ls-tree` per ramo).
- Mutazioni: su COPIA del file (cp in scratchpad, `python3 -I` con `str.replace`, poi ripristino). Meglio: test scritto prima del fix e visto rosso.
- Test instabili: cercare DUE letture dello stesso stato nello stesso comando.
- Doppio clic: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`.
- Permessi/presa esclusiva: ricontrollare al momento dell'uso. Ruoli che aprono un livello più alto: chi li sceglie deve averlo (D28).
- Task per chiave: uno solo, il nuovo annulla il vecchio. Code in memoria: tetto, e si fermano quando la destinazione sparisce (rileggere lo stato a ogni passo).
- Finti: `Thread.permissions_for` eredita dal padre; `create_autospec(discord.Thread)` per `isinstance`. Webhook: con `wait=True` discord.py manda `?wait=1` e vuole 200 con il messaggio.
- Backup/riallineamenti: solo aggiungere/aggiornare (overwrite uniti, etichette forum con id); `edit_role_positions` con un ruolo sopra il bot fallisce tutto; scritture finali di un giro lungo condizionate allo stato attuale (promozione nel mezzo).
- Bot secondario (D15): cercare OGNI azione della sua area ancora chiamata sul principale.
- `locales/comandi.en.json` "nomi" è per SEGMENTO, globale. `AllowedMentions(roles=...)` ha `everyone=True` di default.
- DECISIONI: i «casi» di D25 aggiunti da rami diversi vanno numerati contro `git show main:`.
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
