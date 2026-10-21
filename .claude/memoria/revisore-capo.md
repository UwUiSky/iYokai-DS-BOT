# Memoria di revisore-capo

## Aggiornata
21/10/2026 · ramo `feat/r8uti` (/ruoli D25 quinto caso, scheda, ruoli auto, suggerimenti, promemoria, sondaggio; 0230–0232): corretti chiave fuori schema (anche `backup_livello_permessi` rosso su main), lasciati del cacciatore (azzera, auto-sincronizza, tetto massa, thread sondaggio). Esito smoke nel rapporto.

## In corso
- `feat/r8uti`: aperta 1 bassa (schede canale/permessi senza controllo «vede il canale»).
- `feat/r7mod`: aperti noti in SPEC/REGISTRO (log via webhook, invito in /setup, LOG-029). `_shared.py:192` non riconosce Mod come «il bot stesso» (bassa).
- `feat/r7liv`: 3 basse aperte nel quaderno. Sfondo per tutti in VERIFICA_LIVE da confermare all'owner.
- `feat/r6mus`: 1 bassa (nome playlist non normalizzato) per dev-musica.
- Rami in attesa di riconsegna (righe nel quaderno): `feat/r4-tkt` 23, `feat/r4-uti` 21, `feat/r4-liv` 9, `feat/r3-mus` 8, `feat/r3-bak` 8, `giro-mod` 12, `giro-logt` 11, #66 12, #67 8, #147 6, #76 5+7, #59/#117 2, #146, #134, #135/#136. `f7-quadro`: APPROVATO, manca l'unione. Alla riconsegna: solo le righe aperte.
- Aperti bassi: r6ai (ticket staff, pacchetto, riassumi doppio, vietate) per dev-ai; r6mod `/antiraid segnala` senza tetto.

## Fatto
- Letti per intero: giro-mod, r3-bak, r3-mus, r4-liv, r4-tkt, r4-uti, r6ai, r6mod, r6web, r6mus, r7bak (3be8a40), r7mod, r7liv, r8uti.

## Cose imparate
- Controllare il contenuto di ogni commit, non il messaggio. Testo all'utente che promette una funzione va confrontato col codice.
- Ambiente: `source /tmp/claude-0/env_<ramo>.sh` in ogni bash; `python3 -m pytest`; mai `cd` dentro lo script env.
- Funzioni private `db._…` usate da un cog = manca una funzione pubblica. Più blocchi: controllare TUTTI i punti sulle stesse tabelle.
- Chiavi `SETTING_X` in `SETTINGS_SCHEMA` (o `SETTINGS_SOLO_OWNER` se solo l'owner le cambia: mai importabili); far girare `test_config_import_validation.py`. Tabelle nuove in `core/data_registry.py`; metodi di repo senza chiamanti rompono `test_repository_callers.py`. Migrazioni: confrontare i numeri di tutti i rami.
- Mutazioni: su COPIA del file, script con `python3 -I`, `str.replace` contato. Un test che con la mutazione si blocca va reso finito (`asyncio.wait(..., timeout=)`), non lasciato appeso.
- `monkeypatch.setattr(modulo.asyncio, "sleep", ...)` cambia asyncio.sleep per tutti: per cedere il turno, future + `call_soon`.
- Tetti in memoria globali (`prenota_uso`): azzerarli nella fixture, o i test dopo il secondo falliscono.
- Doppio clic / blocchi: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`; blocco tolto senza test rosso = test mancante.
- Task programmati per chiave: uno solo per chiave, riferimento tenuto, fermati in `cog_unload`.
- Finti con `member.roles` vivo non provano un'istantanea vecchia; `Permissions.all()` per admin finto. Viste con timeout lungo: gerarchia ricontrollata al click.
- Suite completa >10 min: mai. Smoke in background con `nohup` e ciclo `until`; `pkill -f` col testo del comando uccide la propria shell.
- `AllowedMentions(roles=...)` ha `everyone=True` di default. `monkeypatch.undo()` toglie anche il pool del DB.
- Bot secondario (D15): cercare OGNI azione della sua area ancora chiamata sul principale.
- `locales/comandi.en.json` "nomi" è per SEGMENTO, globale (guardare COMMAND_LIST_ENG nel diff); categorie nuove vanno in `etichette_categoria` inglese.
- Ruoli che aprono un livello più alto: chi li sceglie deve avere il permesso di quel livello (D28). Caricamenti fatti dal bot: tetto = ruolo più alto di chi lancia (salvo owner).
- DECISIONI: i «casi» di D25 vanno numerati e datati contro `git show main:`.

## Aperto
- Domande all'owner: SPEC 23.16 (sfondo solo colore), D18 limite ticket per utente, conferma primo DM ModMail, D27.
