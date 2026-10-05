# Memoria di revisore-capo

## Aggiornata
06/10/2026 · ramo `feat/f7-quadro` (copia /home/claude/wt/f7a) · riconsegna riletta: APPROVATO

## In corso
- #76 (`feat/f7-quadro`, HEAD 6cfe06b): APPROVATO alla riconsegna (06/10). Manca solo l'unione.
- #146 (`feat/boost-146`): DA SISTEMARE solo `COMMAND_LIST.md:67-68` (opzione `tipo`). Alla riconsegna: controllare solo quella.
- #134 (`fix/f1-134`, base `4b42ada`): DA SISTEMARE solo documentazione (VERIFICA_LIVE, docstring). Alla riconsegna: controllare solo quelle due righe.
- Revisione #135/#136: DA SISTEMARE (remove_member deadlock). Alla riconsegna: rivedere solo quel punto.

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
- `feat/f7-quadro`: approvato, attende unione.
- `feat/boost-146`: attende riga in COMMAND_LIST.
- `fix/f1-134`: attende due righe di documentazione.
- `fix/f1-135`: attende correzione di `remove_member`.

- #76 riconsegna: prove senza fix su copia (tar in scratchpad/rc): senza check in add_command 1 fallisce (il test sull'albero vero passa comunque: oggi nessun Group semplice sotto gruppi protetti); vecchio leggi_ruolo 9; autocomplete senza check 2; import senza controllo 6; rollback senza controllo 1; contatore sempre attivo 1. Smoke 256 verdi. `autocomplete_protetto` con functools.wraps: la firma resta (inspect segue __wrapped__) e discord.py lo accetta su metodo di cog.
