# Memoria di cacciatore-bug

## Aggiornata
05/10/2026 · ultimo giro: ramo `fix/f1-135` (base 5c04cf5)

## In corso
- Niente a metà. Giro #133 chiuso (rapporto dato).

## Fatto
- Revisione delle correzioni del 28/09–01/10: BUG-19…34, SEC-18…22
  (`revisione/01-analisi/REVIEW.md` §20). Tutti risolti in R1-bis,
  tranne BUG-26/28/29 superati dal nuovo disegno del backup (D8).

- Giro fix/f1-135 (#135/#136): un solo rilievo vero, deadlock `set_member_role` vs `apply_text_tick`. Chiamanti di `EsitoRuolo`: uno solo (leveling.py), a posto. Funzioni rimosse: nessun uso residuo.

- 05/10 revisione ramo fix/f1-133: 4 rilievi (cache verifica con corsa, avviso anti-raid doppio, `_in_attesa` senza scadenza, `raid_in_corso` senza chiamanti).

## Cose imparate
- Ordine dei blocchi nel clan: riga membro, poi `leveling_totals`, poi `clans`. Un fix che blocca `clans` per primo e poi tocca il membro va in deadlock con `apply_text_tick`. Si prova con due cicli in parallelo e si confronta con la base (`git archive`).
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

- Cache "leggi, poi set" con await in mezzo: la scrittura che fa `delete` non basta, serve un numero di versione. Per provare: `ENVIRONMENT=development MAIN_GUILD_ID=1` e token finti.

## Aperto
- Giro da fare a fine F1 sulle aree toccate il 05/10 (sicurezza,
  moderazione, log, ticket, vocali, livelli, clan).
- Rilievi senza fix: issue #133–#137 (vedi `rapporti/bug.md`).
