# Memoria di revisore-capo

## Aggiornata
14/10/2026 · ramo `feat/r4-liv` (40e6b5e) #65/#86/#99/#111/#124/#125: DA SISTEMARE (9 righe nel quaderno, nessuna alta)

## In corso
- `feat/r4-liv` (40e6b5e): DA SISTEMARE. Media: `_acquista` senza `prezzo_atteso` (addebito al prezzo nuovo, rimborso al vecchio: leveling.py:1468, shop_repo.py:249); `save_template` senza test del blocco (30 insieme = 26-27 modelli); SPEC 23.16 `[x]` con sfondo solo colore (D18). Basse: test `fuori_gerarchia` in `da_togliere`, codice morto (AZIONI_*, GIOCHI, pick_winners, is_eligible), `allowed_mentions` annuncio vincitori, bio tagliata in silenzio, ruoli non aggiornati non detti, `/fun conteggio` senza permessi. Alla riconsegna controllare solo quelle. Smoke 876 verdi; 50 mutazioni (scratchpad/rv/mut.py, copia scratchpad/rv/copia).
- Rami precedenti ancora in attesa (vedi quaderno di ciascuno): `feat/r3-mus` 8 righe, `feat/r3-bak` 8, `giro-mod` 12, `giro-logt` 11, #66 12, #67 8, #147 6, #76 decoratore 5+7, #59/#117 2, #146, #134, #135/#136 (`remove_member` deadlock). `feat/f7-quadro` APPROVATO, manca l'unione.

## Fatto
- F1 del 05/10 unito (`7722b71`, `3758f2a`, `9db9e8a`); giro-mod (83 mutazioni), r3-bak (53), r3-mus (70), r4-liv (50, 5400 righe di diff) letti per intero.

## Cose imparate
- Cambio "giusto" può peggiorare un'altra area: controllare il contenuto di ogni commit, non il messaggio. Testo all'utente che promette una funzione va confrontato con ciò che il codice fa.
- DB per processo (`iyokai_wrevisore2`), `python3 -m pytest`, `postgres:testpass@127.0.0.1`. Senza `DATABASE_URL` i test usano `iyokai_test` (condiviso, `clean_db` lo svuota): esportarlo SEMPRE, anche per prove al volo. Mai fare `cd` dentro lo script env: i file finiscono nel ramo.
- Funzioni private `db._…` usate da un cog = manca una funzione pubblica. Più blocchi: controllare TUTTI i punti che bloccano le stesse tabelle.
- Chiavi `SETTING_X`/`KEY_*` nuove vanno in `SETTINGS_SCHEMA` (config_history.py); lo smoke non sceglie quel test se non si tocca il file. Tabelle nuove: voce in `core/data_registry.py`.
- Stato su più comandi: provare la sequenza A->B->C con un test temporaneo. Task che riprovano per sempre bloccano chi fa `gather`: provare con gestore vero.
- Mutazioni: `WHERE guild_id = $1` -> `$1::bigint IS NOT NULL` (togliere il parametro dà InterfaceError, non conta come uccisa); contare le occorrenze prima di `replace`; lavorare su una COPIA e fare `diff -rq` a fine giro.
- `Permissions(view_channel=False)` ha anche manage_messages=False: fissare l'altro permesso a True.
- Doppio clic / blocchi: serve `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`; un blocco per chiave A non protegge un vincolo su chiave B. Un blocco advisory tolto che non fa fallire nessun test = test mancante (provare con 30 chiamate insieme).
- Prezzo/importo: se il DB decide il valore, anche messaggio e rimborso devono usare QUEL valore (o rifiutare se diverso dal letto).
- Mutanti equivalenti da riconoscere: tetto già garantito a monte (`[:256]` con premio max 200; elenco 25x76 < 2000).
- Suite completa >10 min: non lanciarla. Voci già a posto sul base: `git show base:file`. `pkill -f` col testo del comando uccide la propria shell.
- Prove #76: GRUPPI globale condiviso tra test; il lookbehind dei riferimenti esclude i backtick; chiavi `KEY_*` sfuggono al test invariante.
- Migrazioni: confrontare i numeri di TUTTI i rami (`git diff main...ramo --name-only -- core/migrations`) + prova due volte su DB con i dati di main (`git archive main`).

## Aperto
- Rami elencati in "In corso" attendono le riconsegne. Domanda all'owner: SPEC 23.16 (sfondo solo colore) accettato o `[~]`?
