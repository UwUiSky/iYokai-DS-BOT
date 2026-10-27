# Memoria di revisore-capo

## Aggiornata
27/10/2026 · ramo `feat/r10bak` (#68 backup: espressioni, forum/stage, aggiornamento 6 h 0320, mirror in coda, promuovi, webhook con immagine). Fatto anche il giro del cacciatore. Corretti: mirror con `wait=True` e coda che si ferma se il mirror è tolto (b3d6288), riallineamento che non toglie overwrite/etichette e ruoli solo sotto il Creator (4efd6df), mappa mirror scritta solo se la coppia è ancora legata (278c107), VERIFICA_LIVE (f1a8116).

## In corso
- `feat/r10bak`: nessuna riga aperta; esito smoke nel rapporto. Giro di aggiornamento lasciato nel loop dei job apposta (mai due copie insieme).
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
