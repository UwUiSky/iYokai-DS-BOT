# Memoria di revisore-capo

## Aggiornata
13/10/2026 · ramo `feat/r3-mus` (2851f89) #64/#47/#48/#45/#126: DA SISTEMARE (8 righe nel quaderno)

## In corso
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

## Fatto
- F1 del 05/10 unito (`7722b71`, `3758f2a`, `9db9e8a`); giro-mod letto per intero (83 mutazioni); r3-bak letto per intero (2596 righe di codice, 53 mutazioni).

## Cose imparate
- Cambio "giusto" può peggiorare un'altra area: controllare il contenuto di ogni commit, non il messaggio.
- DB per processo (wrevisore, wrevisore2) per non avere fallimenti a caso. `python3 -m pytest`. Il DB vuole `postgres:testpass@127.0.0.1`.
- Funzioni private `db._…` usate da un cog = manca una funzione pubblica. Più blocchi: controllare TUTTI i punti che bloccano le stesse tabelle.
- Chiavi `SETTING_X`/`KEY_*` nuove vanno in `SETTINGS_SCHEMA` (config_history.py); lo smoke non sceglie quel test se non si tocca il file.
- Tabelle nuove: voce in `core/data_registry.py`; provare con clone scratch + merge dell'altro ramo.
- Stato su più comandi (isolamento): provare la sequenza A→B→C con un test temporaneo.
- Mutazione `WHERE guild_id = $1` → `$1::bigint IS NOT NULL`; `str.replace(..,1)` colpisce la prima occorrenza: contare.
- `Permissions(view_channel=False)` ha anche manage_messages=False: fissare l'altro permesso a True.
- Doppio clic / blocchi: serve `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`; un test in serie non prova il blocco. Un blocco per chiave A non protegge un vincolo unico su chiave B (r3-bak: due main, stesso backup).
- Suite completa >10 min: non lanciarla. Voci già a posto sul base: `git show base:file`.
- Prove #76: GRUPPI globale condiviso tra test; guarda se il lookbehind esclude i backtick; `autocomplete_protetto` con wraps resta valido.
- Chiavi impostazione chiamate `KEY_*` (non `SETTING_*`) sfuggono al test invariante ma servono lo stesso in SETTINGS_SCHEMA: l'export le scarta, l'import le rifiuta.
- Task di collegamento che riprovano per sempre: chi fa `gather` su di loro non finisce mai. Provare con gestore vero e nodo morto, non con lista vuota.
- Mutazioni: se il processo viene ucciso a metà il file resta mutato e falsa le prove dopo: `diff -rq` con la copia pulita prima di ogni giro. `pkill -f` col testo del comando uccide la propria shell; lanciare a blocchi in primo piano (timeout 590).
- Task che riprovano per sempre bloccano chi fa `gather`: provare con gestore vero e nodo morto.
- Mutazioni: il processo ucciso lascia il file mutato; `diff -rq` con la copia pulita prima di ogni giro; `pkill -f` col testo del comando uccide la propria shell.
- Testo all'utente che promette una funzione (es. «copia messaggi») va confrontato con ciò che il codice fa davvero.

## Aperto
- giro-mod sopravvissute: vedi quaderno di quel ramo. Altri rami attendono le righe elencate. `fix/f1-135` attende `remove_member`.
