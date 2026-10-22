# Memoria di revisore-capo

## Aggiornata
22/10/2026 · ramo `feat/r9nsfw` (#94 NSFW 0240–0241, #107 App, #145, #141): corretti politica comandi per l'app fuori server (229f086), «Segnala» differito (2d41f96), menu in inglese (742b61b), documenti (baca393). Smoke --base main: 809 passati.

## In corso
- `feat/r9nsfw`: aperta 1 bassa (tetto promemoria letto-poi-scritto).
- `feat/r8web`: da confermare all'owner «IPv4 da solo = basso». `feat/r8uti`: 1 bassa (schede senza «vede il canale»).
- `feat/r7mod`: aperti noti in SPEC/REGISTRO; `_shared.py:192` Mod non «il bot stesso» (bassa). `feat/r7liv`: 3 basse. `feat/r6mus`: 1 bassa.
- Rami in attesa di riconsegna (righe nel quaderno): r4-tkt, r4-uti, r4-liv, r3-mus, r3-bak, giro-mod, giro-logt, #66, #67, #147, #76, #59/#117, #146, #134, #135/#136. `f7-quadro` APPROVATO, manca l'unione.
- Aperti bassi: r6ai per dev-ai; r6mod `/antiraid segnala` senza tetto.

## Fatto
- Letti per intero: giro-mod, r3-bak, r3-mus, r4-liv, r4-tkt, r4-uti, r6ai, r6mod, r6web, r6mus, r7bak, r7mod, r7liv, r8web, r8uti, r9nsfw.

## Cose imparate
- Controllare il contenuto di ogni commit, non il messaggio. Testo all'utente che promette una funzione va confrontato col codice.
- Ambiente: `source /tmp/claude-0/env_<ramo>.sh` in ogni bash; `python3 -m pytest`; mai `cd` dentro lo script env.
- Funzioni private `db._…` usate da un cog = manca una funzione pubblica. Più blocchi: controllare TUTTI i punti sulle stesse tabelle.
- Chiavi `SETTING_X`/`KEY_*` in `SETTINGS_SCHEMA`; tabelle nuove in `core/data_registry.py`; metodi di repo senza chiamanti rompono `test_repository_callers.py`. Migrazioni: confrontare i numeri di tutti i rami.
- Migrazioni tracciate per NOME in `schema_migrations`: anche una del ramo già applicata ai DB di prova non si riapplica se modificata. Cambi = migrazione nuova.
- Mutazioni: su COPIA del file (cp in scratchpad, poi ripristino), `str.replace` contato.
- Test con id piccoli (41, 42) e `str(x) in str(righe)`: falsi rossi da timestamp. Confrontare i valori.
- Doppio clic / blocchi: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`; blocco tolto senza test rosso = test mancante.
- Task programmati per chiave: uno solo per chiave, il nuovo annulla il vecchio.
- Finti con `member.roles` vivo non provano un'istantanea vecchia; `Permissions.all()` per admin finto.
- Suite completa >10 min: mai. Smoke in background con `nohup` e poll ≤119 s; `pkill -f` col testo del comando uccide la propria shell.
- Stato in memoria: chi lo ripulisce, cosa succede al riavvio; se limite accettato -> VERIFICA_LIVE.
- `AllowedMentions(roles=...)` ha `everyone=True` di default. `monkeypatch.undo()` toglie anche il pool del DB.
- `locales/comandi.en.json` "nomi" è per SEGMENTO, globale: una chiave nuova rinomina ogni comando con quel nome.
- Ruoli che aprono un livello più alto: chi li sceglie deve avere il permesso di quel livello (D28). Caricamenti fatti dal bot: tetto = ruolo più alto di chi lancia.
- Limiti per IP del pannello: un secchio per funzione (accesso, verifica), non condiviso.
- Chiavi `SETTING_X` in `SETTINGS_SCHEMA` (o `SETTINGS_SOLO_OWNER` se solo l'owner le cambia: mai importabili); far girare `test_config_import_validation.py`. Tabelle nuove in `core/data_registry.py`; metodi di repo senza chiamanti rompono `test_repository_callers.py`. Migrazioni: confrontare i numeri di tutti i rami.
- Mutazioni: su COPIA del file, script con `python3 -I`, `str.replace` contato. Un test che con la mutazione si blocca va reso finito (`asyncio.wait(..., timeout=)`), non lasciato appeso.
- `monkeypatch.setattr(modulo.asyncio, "sleep", ...)` cambia asyncio.sleep per tutti: per cedere il turno, future + `call_soon`.
- Tetti in memoria globali (`prenota_uso`): azzerarli nella fixture, o i test dopo il secondo falliscono.
- Bot secondario (D15): cercare OGNI azione della sua area ancora chiamata sul principale.
- DECISIONI: i «casi» di D25 vanno numerati e datati contro `git show main:`.

- App utente: `is_guild_integration()` falso = server senza l'app. Ogni cosa del server (politica, moduli, quote) va saltata. Menu del tasto destro: nomi inglesi in sezione `menu`, non `nomi`.
## Aperto
- Domande all'owner: SPEC 23.16 (sfondo solo colore), D18 limite ticket per utente, conferma primo DM ModMail, D27, IPv4 = basso (NF-21).
