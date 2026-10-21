# Memoria di revisore-capo

## Aggiornata
21/10/2026 · ramo `feat/r8web` (NF-21 #92, #148, NF-38 #109, CFG-030 #122, #46): corretti dal revisore i lasciati del cacciatore (limiti per IP separati, YOKAI_MOD_TOKEN, testi di revoca, allegato.read, IPv4 da solo = basso con 0211). Esito smoke nel rapporto.

## In corso
- `feat/r8web`: da far confermare all'owner la scelta «IPv4 da solo = basso» (VERIFICA_LIVE, giro r8).
- `feat/r7mod`: aperti noti in SPEC/REGISTRO (log via webhook, invito in /setup, LOG-029). `_shared.py:192` non riconosce Mod come «il bot stesso» (bassa).
- `feat/r7liv`: 3 righe basse aperte nel quaderno (invita a metà, sfondo con card spente, registro senza controllo permessi).
- `feat/r6mus`: 1 riga bassa (nome playlist non normalizzato) per dev-musica.
- Rami in attesa di riconsegna (righe nel quaderno di ciascuno): `feat/r4-tkt` 23, `feat/r4-uti` 21, `feat/r4-liv` 9, `feat/r3-mus` 8, `feat/r3-bak` 8, `giro-mod` 12, `giro-logt` 11, #66 12, #67 8, #147 6, #76 5+7, #59/#117 2, #146, #134, #135/#136. `f7-quadro`: APPROVATO, manca l'unione. Alla riconsegna: solo le righe aperte.
- Aperti bassi: r6ai (ticket staff, pacchetto, riassumi doppio, vietate) per dev-ai; r6mod `/antiraid segnala` senza tetto.

## Fatto
- Letti per intero: giro-mod, r3-bak, r3-mus, r4-liv, r4-tkt, r4-uti, r6ai, r6mod, r6web, r6mus, r7mod, r7bak (3be8a40), r7liv, r8web.

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

## Aperto
- Domande all'owner: SPEC 23.16 (sfondo solo colore), D18 limite ticket per utente, conferma primo DM ModMail, D27, IPv4 = basso (NF-21).
