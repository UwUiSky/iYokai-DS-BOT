# Memoria di revisore-capo

## Aggiornata
28/10/2026 · `feat/r10logt` (log, ticket chiusi 0302, vocali 0300–0301): fatto anche il lavoro del cacciatore. Corretti 031a2d3 (ticket chiusi), a8866f8 (D34 log ignora), ea2f070 (generatore privato), 33030a3 (indice 0303, SPEC 8.8), afee66f (elenco comandi). APPROVATO; smoke da fare dall'orchestratore.

## In corso
- `feat/r10logt`: aperti nel quaderno 1 media (`/log cerca ruolo` senza ruoli dati/tolti, per dev-log-ticket) e 3 basse. D34 da segnalare all'owner. Al merge: D34 numerato dall'orchestratore (D31–D33 riservati); COMMAND_LIST da rigenerare.
- `feat/r9nsfw`: 1 bassa (tetto promemoria letto-poi-scritto). `feat/r8web`: «IPv4 da solo = basso» da far confermare all'owner. `feat/r8uti`: 1 bassa.
- `feat/r7mod`: aperti noti in SPEC/REGISTRO; `_shared.py:192` Mod non «il bot stesso» (bassa). `feat/r7liv`: 3 basse. `feat/r6mus`: 1 bassa. `feat/r8tkt`: 1 bassa accettata.
- Rami in attesa di riconsegna (righe nel quaderno): r4-tkt, r4-uti, r4-liv, r3-mus, r3-bak, giro-mod, giro-logt, #66, #67, #147, #76, #59/#117, #146, #134, #135/#136. `f7-quadro` APPROVATO, manca l'unione.
- Aperti bassi: r6ai per dev-ai; r6mod `/antiraid segnala` senza tetto.

## Fatto
- Letti per intero: giro-mod, r3-bak, r3-mus, r4-liv, r4-tkt, r4-uti, r6ai, r6mod, r6web, r6mus, r7bak, r7mod, r7liv, r8tkt, r8uti, r8web, r9mod, r9nsfw, r10logt.

## Cose imparate
- Controllare il contenuto di ogni commit, non il messaggio. Voci passate a `[x]`: aprire il test citato e vedere che prova QUELLA voce (r10: 8.8 citava LC-6 con un testo sbagliato).
- Ambiente: `source` dello script env in ogni bash; `python3 -m pytest`; mai riavviare postgres se l'orchestratore lo vieta. Regola owner r10: niente smoke né suite, solo test dei file toccati.
- Merge di main: conflitti nei documenti e in `comandi.en.json` (chiavi doppie); `COMMAND_LIST*.md` si rigenerano (`scripts/generate_command_list.py`; gli errori dei task alla chiusura sono innocui).
- Funzioni private `db._…` usate da un cog = manca una funzione pubblica. Più blocchi: controllare TUTTI i punti sulle stesse tabelle.
- Chiavi `SETTING_X` in `SETTINGS_SCHEMA` (solo owner: `CHIAVI_SOLO_PROPRIETARIO`); `test_config_import_validation.py`. Tabelle nuove in `core/data_registry.py`; metodi di repo senza chiamanti rompono `test_repository_callers.py`.
- Migrazioni tracciate per NOME: una modificata non si riapplica. Numeri: confrontare con `git ls-tree main core/migrations/` e gli altri rami; anche le D di DECISIONI con `git show main:`.
- Mutazioni: su COPIA del file, script `python3 -I` in scratchpad con `str.replace` contato e ripristino. Test scritto prima del fix e visto rosso vale come prova.
- Test instabili di corsa: cercare DUE letture dello stesso stato nello stesso comando.
- Doppio clic / blocchi: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`.
- Task programmati per chiave: uno solo per chiave; annullarli quando lo stato torna indietro (riapertura ticket → `scheduler.cancel_for_channel`).
- Finti: `member.roles` vivo non prova un'istantanea vecchia; `Permissions.all()` per admin; `fake_member` ha `Permissions.none()`; `canale.overwrites` va impostato a mano nei finti.
- Stato/cache in memoria: chi lo svuota, cosa succede al riavvio; limite accettato → VERIFICA_LIVE.
- `AllowedMentions(roles=...)` ha `everyone=True` di default. `monkeypatch.undo()` toglie anche il pool del DB. `monkeypatch.setattr(asyncio, "sleep")` è globale.
- `locales/comandi.en.json` "nomi" è per SEGMENTO, globale.
- Ruoli che aprono un livello più alto: chi li sceglie deve avere quel livello (D28). Ripristini fatti dal bot: tetto = ruolo più alto di chi lancia.
- Bot secondario (D15): cercare OGNI azione della sua area ancora chiamata sul principale.
- Filtri «ignora» e nascondere canali: mai eventi di sicurezza fuori dal log (D34); nascondere = tutte le sovrascritture non staff.
