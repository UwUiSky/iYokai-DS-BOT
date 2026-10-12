# Memoria di revisore-capo

## Aggiornata
12/10/2026 · ramo `feat/giro-mod` (47c7fc6) · #138/#101/#57/#60/#116: DA SISTEMARE

## In corso
- `feat/giro-mod` (47c7fc6): DA SISTEMARE, 12 righe nel quaderno (settings fuori da SETTINGS_SCHEMA = test rosso, /ban su isolato + /unban non sbanna, rientro senza invito banna lo stesso, appello bloccato se il caso non è attivo, OAuth di #138 non fatto, registry dati all'unione con giro-core, test mancanti). Alla riconsegna: controllare solo quelle. Smoke 58 verdi + 133 test del ramo verdi.
- `feat/giro-logt` (6b50b7a): 11 righe (cache `_post_noti`, audit letto due volte, `/log stato`, test snipe/message_logs/router, codice morto soundboard). Smoke 447.
- #66 `feat/66-utility` (6e18a89): 12 righe (ramo `if not deciso`, emoji test, test greetings/role menu/owner, duplicato PagineView, VERIFICA_LIVE, ruff). Smoke 420.
- #59/#117 `feat/sicurezza-audit` (797b6ce): solo 2 ritocchi ai test.
- #67 `feat/67-feed-alert` (f3f90f5): 8 righe (test gruppi videos.list, pop ETag, parse_search_live_response morto, SPEC/config/VERIFICA_LIVE).
- #147 `feat/147-cerca-comando` (e669c36): 6 righe (invalida_id, test sinonimi/taglio/url/esatto/serve/cog_load, bonus sottostringa, search_commands morto, ruff).
- #76 `feat/f7-decoratore` (d39e1ea) revisori A e B: 5 + 7 righe in quaderno. `feat/f7-quadro` (6cfe06b): APPROVATO, manca l'unione.
- #146 `feat/boost-146`: solo `COMMAND_LIST.md:67-68`. #134 `fix/f1-134`: solo 2 righe di documentazione. #135/#136: `remove_member` deadlock.

## Fatto
- Revisione e unione dei tre rami F1 del 05/10: `7722b71`, `3758f2a`, `9db9e8a`. Suite completa verde (3141).
- giro-mod letto per intero (3292 righe): 43+40 mutazioni su copia tar (scratchpad/rm, mut.py + genmut*.py); unione di prova con giro-core in clone (solo conflitti nei documenti).

## Cose imparate
- Cambio "giusto" può peggiorare un'altra area: chiedersi cosa vede l'utente dopo. Controllare il contenuto di ogni commit, non il messaggio.
- Agenti sulla stessa cartella temporanea si sovrascrivono: sotto-cartella propria. Test paralleli sullo stesso DB danno fallimenti a caso: un DB per processo (wrevisore, wrevisore2). Interprete: `python3 -m pytest`. Mai `echo ... ->exp`.
- Funzioni private `db._…` usate da un cog = manca una funzione pubblica. Con più blocchi su righe controllare TUTTI i punti che bloccano le stesse tabelle (anche non nel diff).
- Chiavi `SETTING_X = "..."` nuove vanno in `SETTINGS_SCHEMA` (cogs/utility/config_history.py): `tests/test_config_import_validation.py::test_ogni_setting_usata_nel_codice_e_nello_schema` fallisce; lo smoke NON lo sceglie se non si tocca config_history.
- Tabelle nuove: da giro-core serve la voce in `core/data_registry.py` (`tests/test_data_registry.py`). Provarlo sempre con un clone scratch: `git clone`, merge dell'altro ramo, pytest del test (documenti in conflitto: `--ours`).
- Stato su più rami di codice: se un comando lascia una riga di stato (isolamento) altri comandi (ban, kick, antiraid) devono pulirla; provare la sequenza A→B→C con un test temporaneo (cp2).
- Mutazione `WHERE guild_id = $1` → `WHERE $1::bigint IS NOT NULL` prova il filtro di server senza errori di parametri. `str.replace(..,1)` colpisce la PRIMA occorrenza: contare le occorrenze (mut.py salta se != 1).
- Fixture import (`scenario`, `contesto`) danno F811 in ruff: è il modello del progetto, ignorare; contano F401 veri.
- `Permissions(view_channel=False)` ha anche manage_messages=False: il test non prova la condizione `view_channel`. Fissare l'altro permesso a True.
- Doppio clic: due controlli ridondanti (stato letto prima + UPDATE condizionato) si coprono a vicenda; serve `asyncio.gather` con connessioni vere (`tests/support/concorrenza.apri_connessioni`).
- Suite completa >10 min: non lanciarla. Voci già a posto sul base: `git show base:file`.
- Prove #76: GRUPPI globale condiviso tra test; guarda se il lookbehind esclude i backtick; `autocomplete_protetto` con wraps resta valido.

## Aperto
- giro-mod sopravvissute (mutazioni): scadenza senza log, /unban isolato (cancel jobs, member None, mark expired), canale nuovo = iso, send_messages, unique invito, fallback canali invito, ripristino scaduto, ricollega isolato al join, revoca caso precedente, delete stato fuori; appelli: lunghezza, canale None, guild diverso, doppio clic, log, cmd canale, tempban; case: filtri guild repo (6), validate_reason, già tolto; clear: view_channel, bot+umani, role_mentions, lower, lock HTTP; verify: `options_cmd` mai chiamato, bot/modulo al join, extra saltati, manuale senza config, tetto 3; automod: tetto e move_to_end.
- Altri rami: attendono le righe elencate sopra. `fix/f1-135` attende `remove_member`.
