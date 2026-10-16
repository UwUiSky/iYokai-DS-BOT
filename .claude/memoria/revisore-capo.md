# Memoria di revisore-capo

## Aggiornata
16/10/2026 · ramo `feat/r7mod` (#113 D15, #119, #101): corretti dal revisore sban da Discord (NF-30), cancellati in memoria (LOG-027/NF-04), fine isolamento via Mod. Esito smoke nel rapporto.
16/10/2026 · ramo `feat/r7bak` (/backup D25, #68, #110, #121): corretti dal revisore consenso persistente, gerarchia al caricamento, D25 quarto caso (3be8a40). Smoke --base main: 1071 verdi.

## In corso
- `feat/r7mod`: aperti noti in SPEC/REGISTRO (log via webhook, invito in /setup, LOG-029). `_shared.py:192` non riconosce Mod come «il bot stesso» (bassa).
16/10/2026 · ramo `feat/r7liv` (#127/#144 vocali, #83/#111 card e profilo, #65 M 9.18, #124/#125): corretti nome inglese `pause` globale (ora `/level attese`) e unlock fallito su canale mai bloccato. Esito smoke nel rapporto.

## In corso
- `feat/r7liv`: 3 righe basse aperte nel quaderno (invita a metà, sfondo con card spente, registro senza controllo permessi). Scelta sfondo per tutti in VERIFICA_LIVE da far confermare all'owner.
- `feat/r6mus`: aperta 1 riga bassa (nome playlist non normalizzato in carica/elimina/esporta) per dev-musica.
- Rami in attesa di riconsegna (righe nel quaderno di ciascuno): `feat/r4-tkt` 23, `feat/r4-uti` 21, `feat/r4-liv` 9 (corrette, da riapprovare), `feat/r3-mus` 8, `feat/r3-bak` 8, `giro-mod` 12, `giro-logt` 11, #66 12, #67 8, #147 6, #76 5+7, #59/#117 2, #146, #134, #135/#136 (`remove_member` deadlock). `f7-quadro`: APPROVATO, manca l'unione. Alla riconsegna: solo le righe aperte.
- Aperti bassi: r6ai (ticket staff, pacchetto, riassumi doppio, vietate) per dev-ai; r6mod `/antiraid segnala` senza tetto.

## Fatto
- F1 del 05/10 unito. Letti per intero: giro-mod, r3-bak, r3-mus, r4-liv, r4-tkt, r4-uti, r6ai (9f323ca), r6mod (e420745), r6web (f1829fc), r6mus (e339198), r7mod.
- F1 del 05/10 unito. Letti per intero: giro-mod, r3-bak, r3-mus, r4-liv, r4-tkt, r4-uti, r6ai (9f323ca), r6mod (e420745), r6web (f1829fc), r6mus (e339198), r7bak (3be8a40).
- F1 del 05/10 unito. Letti per intero: giro-mod, r3-bak, r3-mus, r4-liv, r4-tkt, r4-uti, r6ai (9f323ca), r6mod (e420745), r6web (f1829fc), r6mus (e339198), r7liv.

## Cose imparate
- Controllare il contenuto di ogni commit, non il messaggio. Testo all'utente che promette una funzione va confrontato col codice.
- Ambiente: `source /tmp/claude-0/env_<ramo>.sh` in ogni bash; `python3 -m pytest`; mai `cd` dentro lo script env.
- Funzioni private `db._…` usate da un cog = manca una funzione pubblica. Più blocchi: controllare TUTTI i punti sulle stesse tabelle.
- Chiavi `SETTING_X`/`KEY_*` in `SETTINGS_SCHEMA`; tabelle nuove in `core/data_registry.py`; metodi di repo senza chiamanti rompono `test_repository_callers.py`. Migrazioni: confrontare i numeri di tutti i rami.
- Mutazioni: su COPIA del file (cp in scratchpad, poi ripristino), script con `python3 -I`, `str.replace` contato; `WHERE guild_id = $1` -> `$1::bigint IS NOT NULL`.
- Doppio clic / blocchi: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`; blocco tolto senza test rosso = test mancante.
- Task programmati per chiave (uscita, ritorno "sordo"): uno solo per chiave, il nuovo annulla il vecchio; provare due eventi ravvicinati con tempi corti.
- Finti con `member.roles` vivo non provano un'istantanea vecchia; `Thread.permissions_for` eredita dal padre; `Permissions.all()` per admin finto.
- Prezzo/importo: se il DB decide il valore, messaggio e rimborso usano QUEL valore.
- Suite completa >10 min: mai. Smoke in background con `nohup` e poll ≤119 s; `pkill -f` col testo del comando uccide la propria shell.
- Stato in memoria: chi lo ripulisce, cosa succede al riavvio; se limite accettato -> VERIFICA_LIVE.
- `AllowedMentions(roles=...)` ha `everyone=True` di default. `monkeypatch.undo()` toglie anche il pool del DB.
- URL controllati dal bot e scaricati da un altro (Lavalink): DNS rebinding e redirect restano (LIM-58), si blocca la rete dell'altro.
- Bot secondario (D15): cercare OGNI azione della sua area ancora chiamata sul principale (anche dentro funzioni di aiuto, es. fine isolamento).
- `locales/comandi.en.json` "nomi" è per SEGMENTO, globale: una chiave nuova rinomina ogni comando con quel nome (guardare COMMAND_LIST_ENG nel diff).
- Ruoli che aprono un livello più alto: chi li sceglie deve avere il permesso di quel livello (D28).
- Ruoli che aprono un livello più alto: chi li sceglie deve avere il permesso di quel livello (D28). Caricamenti/ripristini fatti dal bot: tetto = ruolo più alto di chi lancia (salvo owner).
- DECISIONI: i «casi» di D25 aggiunti da rami diversi vanno numerati contro `git show main:`; paragrafi finiti fuori sezione si riportano dentro.

## Aperto
- Domande all'owner: SPEC 23.16 (sfondo solo colore), D18 limite ticket per utente, conferma primo DM ModMail, D27.
