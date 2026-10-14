# Memoria di revisore-capo

## Aggiornata
14/10/2026 · ramo `feat/r4-uti` (66055f9) #66,#78-#82,#85,#87,#88,#97,#98,#105: DA SISTEMARE (21 righe nel quaderno)

## In corso
- `feat/r4-uti` (66055f9): DA SISTEMARE. Media: benvenuto perso se manca Allegare file (`greetings.py:145`), starboard e thread privati (`starboard.py:90`), role menu senza defer, `allow_nsfw`/`self_star` senza comando, trigger autoresponder vuoto, retention di inviti/compleanni/starboard, 5 gruppi di test che non falliscono senza il fix. Alla riconsegna controllare solo quelle. Smoke 610 verdi; 66 mutazioni, 12 sopravvissute (scratchpad/d/mut.py). `/gestione` 6738 car.: all'unione con liv+tkt supera 8000.
- #64 `feat/r3-mus` (2851f89): DA SISTEMARE. Alta: 4 chiavi `music_*` (KEY_*) fuori da SETTINGS_SCHEMA (export le perde); avviso nodo locale mai emesso con nodo morto (gather infinito); `/music remove` contro SPEC 9.4 (serve ok owner). Media: SSRF URL a Lavalink (`url_e_sicuro`), `skipto`/`previous` senza defer, ~10 mutazioni sopravvissute. Alla riconsegna controllare solo quelle. Smoke 430 + 305 test musica verdi; 70 mutazioni (scratchpad/rm64). Migrazione 0060 libera, provata 2 volte su DB vecchio; unione con r3-bak: solo documenti.
- #68 `feat/r3-bak` (abf27fb): DA SISTEMARE. Alta: copia dei messaggi D8 non fatta (testo di `collega` falso, SPEC 11.2 `[x]`). Media: worker `main_guild None` senza `_fallisci`; test cog `collega` senza utente_id/puo_collegare; chiave vecchia seconda; collegamenti paralleli + UniqueViolation. Alla riconsegna controllare solo quelle. 387 test del ramo verdi; 53 mutazioni (scratchpad/rv2/mut.py, copia r3).
- `feat/giro-mod` (47c7fc6): DA SISTEMARE, 12 righe nel quaderno (settings fuori da SETTINGS_SCHEMA = test rosso, /ban su isolato + /unban non sbanna, rientro senza invito banna lo stesso, appello bloccato se il caso non è attivo, OAuth di #138 non fatto, registry dati all'unione con giro-core, test mancanti). Alla riconsegna: controllare solo quelle. Smoke 58 verdi + 133 test del ramo verdi.
- `feat/giro-logt` (6b50b7a): 11 righe (cache `_post_noti`, audit letto due volte, `/log stato`, test snipe/message_logs/router, codice morto soundboard). Smoke 447.
- #66 `feat/66-utility` (6e18a89): 12 righe (ramo `if not deciso`, emoji test, test greetings/role menu/owner, duplicato PagineView, VERIFICA_LIVE, ruff). Smoke 420.
- #59/#117 `feat/sicurezza-audit` (797b6ce): solo 2 ritocchi ai test.
- #67 `feat/67-feed-alert` (f3f90f5): 8 righe (test gruppi videos.list, pop ETag, parse_search_live_response morto, SPEC/config/VERIFICA_LIVE).
- #147 `feat/147-cerca-comando` (e669c36): 6 righe (invalida_id, test sinonimi/taglio/url/esatto/serve/cog_load, bonus sottostringa, search_commands morto, ruff).
- #76 `feat/f7-decoratore` (d39e1ea) revisori A e B: 5 + 7 righe in quaderno. `feat/f7-quadro` (6cfe06b): APPROVATO, manca l'unione.
- #146 `feat/boost-146`: solo `COMMAND_LIST.md:67-68`. #134 `fix/f1-134`: solo 2 righe di documentazione. #135/#136: `remove_member` deadlock.
13/10/2026 · ramo `feat/r3-bak` (abf27fb) #68 voci 12.x: DA SISTEMARE (8 righe nel quaderno)

## In corso
- #68 `feat/r3-bak` (abf27fb): DA SISTEMARE. Alta: testo di `/admin backup collega` dice «struttura e messaggi» ma i messaggi non si copiano (D8, SPEC 11.2 `[x]`). Media: `collega_atomico` due main sullo stesso backup = UniqueViolation non presa; worker `main_guild None` senza `_fallisci`; test cog `collega` senza utente_id/puo_collegare; 2ª chiave del formato vecchio. Basso: overwrite oltre i permessi del Creator (da provare live), 5 F401. Alla riconsegna controllare solo quelle. Smoke 486 + 375 test backup/restore/registro verdi; 53 mutazioni (13 sopravvissute, nel quaderno).
- Altri rami (`feat/r3-mus` 8 righe, `giro-mod` 12, `giro-logt` 11, #66 12, #67 8, #147 6, #76 5+7, #59/#117 2, #146, #134, #135/#136): invariati, vedi quaderno `.claude/rapporti/revisione.md` sul ramo di ciascuno.
14/10/2026 · ramo `feat/r4-liv`: 9 righe corrette dal dev su richiesta del coordinatore, smoke 886 verde; da riapprovare

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

- Thread privati: `Thread.permissions_for` eredita dal padre, non basta per «pubblico». Finti che condividono `member.roles` vivo non provano un'istantanea vecchia dell'interazione: servono copie congelate.
- Harness mutazioni: script con `str.replace` contato + `git checkout` finale; lanciare con timeout 595000 sul tool (non `pkill -f` col nome dello script: uccide la propria shell).
- Con lavoro non committato NON ripristinare le mutazioni con `git checkout -- file` (perde le correzioni): fare `git stash` + `stash apply` prima, o copia del file.

## Aperto
- Rami elencati in "In corso" attendono le riconsegne. Domanda all'owner: SPEC 23.16 (sfondo solo colore) accettato o `[~]`?
