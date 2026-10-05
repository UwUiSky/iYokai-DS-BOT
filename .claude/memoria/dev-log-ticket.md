# Memoria di dev-log-ticket

## Aggiornata
05/10/2026 · ramo `main` · ultimo commit `3dc9031`

## In corso
- Niente a metà.

## Fatto
- F1, moderazione + log + ticket + vocali: unito su main con
  `3758f2a` (nuovo `core/channel_rename.py`, migrazione `0010`).
- Voci rapide F1 (log dei ruoli, `/voice transfer`).

## Cose imparate
- Rinomine sempre da `core/channel_rename.py`.
- Cancellazione dei ticket dallo scheduler, non da un task.

## Aperto
- #134 (le quattro voci che seguono).
- `/voice kick` dice "espulso" anche se l'utente non è nel canale.
- `/voice lock` riscrive tutti i permessi di @everyone.
- I ticket usano `db._remove_guild_setting` (funzione privata).
- M 3.14: i log avanzati devono chiedere il premium.
