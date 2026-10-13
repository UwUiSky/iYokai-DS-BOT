# Memoria di revisore-capo

## Aggiornata
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
- Task che riprovano per sempre bloccano chi fa `gather`: provare con gestore vero e nodo morto.
- Mutazioni: il processo ucciso lascia il file mutato; `diff -rq` con la copia pulita prima di ogni giro; `pkill -f` col testo del comando uccide la propria shell.
- Testo all'utente che promette una funzione (es. «copia messaggi») va confrontato con ciò che il codice fa davvero.

## Aperto
- giro-mod sopravvissute: vedi quaderno di quel ramo. Altri rami attendono le righe elencate. `fix/f1-135` attende `remove_member`.
