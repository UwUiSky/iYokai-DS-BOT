# Memoria di cacciatore-bug

## Aggiornata
05/10/2026 · ramo `main` · ultimo commit `3dc9031`

## In corso
- Niente a metà.

## Fatto
- Revisione delle correzioni del 28/09–01/10: BUG-19…34, SEC-18…22
  (`revisione/01-analisi/REVIEW.md` §20). Tutti risolti in R1-bis,
  tranne BUG-26/28/29 superati dal nuovo disegno del backup (D8).

## Cose imparate
- La prima revisione non aveva visto che il worker dei backup non
  partiva mai (avviato prima dell'accesso): **controllare sempre
  l'ordine di avvio**, non solo la logica.
- Un fix scritto in un piano può essere sbagliato: tre istruzioni del
  piano lo erano (durata dello `state` OAuth per un link mandato in
  privato; fermare in `cog_unload` i task che cancellano i ticket;
  criterio di pulizia dei server del Creator). Si prova, non si copia.
- BUG-17 era un falso positivo: prima di segnalare una corsa, provarla
  con `tests/support/concorrenza.py`.
- I difetti più frequenti qui: leggi-poi-scrivi su saldi e contatori;
  risposte oltre i limiti con dati lunghi; azioni riportate come
  riuscite quando sono fallite.

## Aperto
- Giro da fare a fine F1 sulle aree toccate il 05/10 (sicurezza,
  moderazione, log, ticket, vocali, livelli, clan).
- Rilievi senza fix: issue #133–#137 (vedi `rapporti/bug.md`).
