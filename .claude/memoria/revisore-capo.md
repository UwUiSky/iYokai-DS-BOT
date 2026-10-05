# Memoria di revisore-capo

## Aggiornata
05/10/2026 · ramo `main` · ultimo commit `3dc9031`

## In corso
- Niente a metà.

## Fatto
- Revisione e unione dei tre rami F1 del 05/10: `7722b71`, `3758f2a`,
  `9db9e8a`. Suite completa verde (3141 test).

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

## Aperto
- Nessun ramo in attesa.
