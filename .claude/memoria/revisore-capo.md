# Memoria di revisore-capo

## Aggiornata
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
- `locales/comandi.en.json` "nomi" è per SEGMENTO, globale: una chiave nuova rinomina ogni comando con quel nome.
- Ruoli che aprono un livello più alto: chi li sceglie deve avere quel livello (D28). Ripristini fatti dal bot: tetto = ruolo più alto di chi lancia.
- DECISIONI: i «casi» di D25 aggiunti da rami diversi vanno numerati contro `git show main:`.

## Aperto
- Domande all'owner: SPEC 23.16 (sfondo solo colore), D18 limite ticket per utente, conferma primo DM ModMail, D27.
