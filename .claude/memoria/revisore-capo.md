# Memoria di revisore-capo

## Aggiornata
05/10/2026 · ramo `fix/f1-135` (base `5c04cf5`) · revisione fatta

## In corso
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

## Aperto
- `fix/f1-135`: attende correzione di `remove_member`.
