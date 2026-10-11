# Memoria di revisore-capo

## Aggiornata
11/10/2026 · ramo `feat/giro-logt` (6b50b7a) · #72/#73/#74/#61/#145: DA SISTEMARE

## In corso
- `feat/giro-logt` (6b50b7a): DA SISTEMARE, 11 righe nel quaderno (cache `_post_noti` al cambio forum, audit letto due volte con snipe+ghost, `/log stato` esplicito, test mancanti snipe/message_logs/router, codice morto soundboard). Smoke 447 verdi. Alla riconsegna: controllare solo quelle.
- #66 `feat/66-utility` (6e18a89): DA SISTEMARE, 12 righe nel quaderno (ramo `if not deciso` non provato, emoji test, test mancanti greetings/role menu/owner, reaction/menu svuotato, duplicato PagineView, VERIFICA_LIVE percorsi, ruff). Alla riconsegna: controllare solo quelle. Smoke 420 verdi.
- #59/#117 `feat/sicurezza-audit` (797b6ce): 2ª revisione 11/10: tutte le righe del quaderno e N1-4/R1-2/G1-4 risolte e provate; DA SISTEMARE solo 2 ritocchi ai test (riga nel quaderno). Alla riconsegna: controllare solo quelli.
- #67 `feat/67-feed-alert` (f3f90f5): DA SISTEMARE, 8 righe nel quaderno (test gruppi videos.list, test pop ETag, codice morto parse_search_live_response, SPEC/config/VERIFICA_LIVE). Alla riconsegna: controllare solo quelle.
- #147 `feat/147-cerca-comando` (e669c36): DA SISTEMARE, 6 righe nel quaderno (invalida_id senza chiamanti, test sinonimi/taglio/url/esatto/serve/cog_load, bonus sottostringa sulle varianti, search_commands morto + docstring, ruff). Alla riconsegna: controllare solo quelle.
- #76 integrazione `feat/f7-decoratore` (d39e1ea), revisore B: DA SISTEMARE, 7 righe nel quaderno (main.py:415 `/setup`, test riferimenti cieco ai backtick, codice morto music cog_load, test d'ordine). Alla riconsegna: controllare solo quelle.
- #76 (`feat/f7-quadro`, HEAD 6cfe06b): APPROVATO alla riconsegna (06/10). Manca solo l'unione.
- #146 (`feat/boost-146`): DA SISTEMARE solo `COMMAND_LIST.md:67-68` (opzione `tipo`). Alla riconsegna: controllare solo quella.
- #134 (`fix/f1-134`, base `4b42ada`): DA SISTEMARE solo documentazione (VERIFICA_LIVE, docstring). Alla riconsegna: controllare solo quelle due righe.
- Revisione #135/#136: DA SISTEMARE (remove_member deadlock). Alla riconsegna: rivedere solo quel punto.
- #76 `feat/f7-decoratore` revisore A (moderation/security/automod/logging/utility): DA SISTEMARE, 5 rilievi in quaderno. Alla riconsegna controllare solo quelli.

## Fatto
- Revisione e unione dei tre rami F1 del 05/10: `7722b71`, `3758f2a`,
  `9db9e8a`. Suite completa verde (3141 test).
- `fix/f1-133` letto per intero; 5 prove senza fix: 4 falliscono giuste, 1 no (invalida dopo scrittura).

## Cose imparate
- Un cambio "giusto" in un'area può peggiorarne un'altra: il messaggio
  privato spostato dopo il ban non arriva più (#137). Chiedersi sempre
  cosa vede l'utente dopo la modifica.
- Controllare il **contenuto** di ogni commit, non il messaggio:
  `fff108a` ha il messaggio di un altro lavoro e contiene solo un test.
- Gli agenti che condividono la cartella temporanea si sovrascrivono i
  file: ognuno usa una sotto-cartella sua.
- Le funzioni private (`db._…`) usate da un cog sono un segnale: manca
  una funzione pubblica.
- Con più blocchi su righe, controllare TUTTI i punti che bloccano le stesse tabelle, non solo quelli nel diff: `remove_member` (non toccato) contraddiceva il nuovo ordine. Si prova con un test temporaneo in parallelo.
- Test che girano in parallelo sullo stesso DB di prova (iyokai_wt1xx) danno fallimenti a caso: prima `ps aux | grep "[p]ython -m pytest"`, poi rilancia. Non usare `pgrep -f pytest` (trova se stesso). Interprete giusto: `python3 -m pytest`, non `pytest`.
- Prove senza fix su #146: tolto il controllo GIA_ATTIVO (20 falliscono), scambio coin/exp nel worker (3), fattore coin (7). `tipi_acquistabili` serve solo al testo del messaggio: non è la regola.
- Mai `echo ... ->exp` nei comandi: `>` crea un file `exp` nella copia di lavoro.
- Prove su copia in scratchpad (tar senza .git, poi pytest): senza le 3 chiavi in SETTINGS_SCHEMA 3 test falliscono; senza ramo AccessoNegato 1; senza catena al padre 1; senza condizione error_counter 0. Serve DATABASE_URL e le variabili di pytest: non importare i moduli con python -c.

## Aperto
- giro-logt prove senza fix (copia tar scratchpad/rl, script mut.py): ~85 mutazioni; 2 bug veri provati con test temporaneo (cache post forum, doppia lettura audit). Sopravvivono: vedi quaderno. Trappola: `str.replace(..,1)` colpisce la PRIMA occorrenza (3 gate uguali in advanced_logs): controllare con `sed -n` che la mutazione sia sul punto giusto.
- `feat/67-feed-alert`: attende 2 test e documentazione.
- `feat/147-cerca-comando`: attende i 6 rilievi.
- `feat/f7-quadro`: approvato, attende unione.
- `feat/boost-146`: attende riga in COMMAND_LIST.
- `fix/f1-134`: attende due righe di documentazione.
- `fix/f1-135`: attende correzione di `remove_member`.
- #76 riconsegna: prove senza fix su copia (tar in scratchpad/rc): senza check in add_command 1 fallisce (il test sull'albero vero passa comunque: oggi nessun Group semplice sotto gruppi protetti); vecchio leggi_ruolo 9; autocomplete senza check 2; import senza controllo 6; rollback senza controllo 1; contatore sempre attivo 1. Smoke 256 verdi. `autocomplete_protetto` con functools.wraps: la firma resta (inspect segue __wrapped__) e discord.py lo accetta su metodo di cog.
- F7 decoratore: confronto corpo comandi con `git show 4903ef0:file` = solo decoratori/messaggi (più: owner check tolto perché dato da GruppoYokai; describe accorciati <100). Mutazioni in copia tar: senza controllo modulo/chiave in `log canale sanzioni` 2 falliscono; senza livello OWNER 1; senza guild_only 1; senza `super().cog_load` anti_raid 1; senza `super().cog_unload` 0; senza rimozione owner globale 0. Riordino test `ruff --select F401` sui file toccati trova import orfani dopo la conversione.
- F7d prove senza fix (copia in scratchpad/rb/cp): command_sync sempre-sync 1, salva-su-errore 1, senza sorted 1, owner senza guild 1, senza copy_global 1 falliscono; senza togli_comandi in LevelingCog.cog_unload 1; senza richiedi ADMIN su bacheca 3; /owner senza Livello.OWNER 1. Il controllo `/owner radio` sta nel gruppo, non nei comandi: provato con _check_can_run su tutto l'albero (gestione e owner tutti NEGATO a un membro semplice).
- Test dei riferimenti ai comandi: guarda se il lookbehind esclude i backtick e se legge main.py. Il globale GRUPPI è condiviso tra test: asserzioni di 'gruppo vuoto' dipendono dall'ordine.
- #147 prove senza fix (copia tar in scratchpad/rv147/cp, DB iyokai_wrevisore): senza predicate.livello 1, filtro menu 1, upsert 1, guild 0 1, cache unica 1, defer 1, any/all 1, 25 categorie 1, footer DM 1, pulizia ogni N 1 falliscono; NON falliscono: sinonimi, esatto, taglio -chiedi, url>512, serve, cog_load. Con test di ricerca: la frase intera trova già per parole, serve una query di UNA parola per provare i sinonimi. Bonus sottostringa su varianti corte (ban) dà falsi positivi.
- #67 prove senza fix (copia tar in scratchpad/rc2, script mut.sh): lock advisory, tetto, gate modulo (3 watcher), first=100, 401, dedupe login, ETag/If-None-Match, User-Agent, elenco tagliato falliscono giusti; NON falliscono: `pop` ETag e `all(i in gruppi_riusciti)`. Voci già a posto sul base (11.7, 11.10) senza diff: verifica con `git show base:file`. Suite completa >10 min: non lanciarla, la decide l'orchestratore.
- #59/#117 prove senza fix (copia tar scratchpad/rev/cp, script mut.py): 67 mutazioni uccise; sopravvivono Range di limits/trusted-add, guardia owner, rilascia_da_quarantena (corpo), fallback add_roles, 3 avvisi permessi spam-trap, prune dedupe. Una mutazione con `if` e rientro sbagliato dà errore di raccolta (non è uccisione).

- #66 prove senza fix (copia tar in scratchpad/rc66, script mut66.py, DB iyokai_wrevisore2): 60 mutazioni, falliscono giuste le principali (lock sticky, atomic UPDATE, defer, Range programmati/promemoria/role menu, pubblica-prima-di-salvare, toggle, wizard/import/reset/rollback); PASSANO: `if not deciso` in suggestions/custom requests, get_emoji, mentions addio/boost/DM, taglia, HTTP tendina/reazioni, avvio menu vuoto, pagine subscriptions/status-all. Trappola: `asyncio.gather` di due handler con repo vero non intreccia: il ramo del perdente non si prova.
