# Memoria di dev-economia

## Aggiornata
05/10/2026 · ramo `main` · ultimo commit `3dc9031`

## In corso
- Niente a metà.

## Fatto
- F1, livelli + economia + clan: unito su main con `9db9e8a`
  (migrazioni `0015`–`0019`, `/clan lascia`, promozione a `co_owner`,
  `_pagine.py`).

## Cose imparate
- BUG-17 non esiste: c'è il test che lo prova.
- Le scritture di saldo vanno fatte condizionate nel database.

## Aperto
- #135 (le quattro voci che seguono).
- `/clan boost`: due clic insieme pagano due volte.
- `/clan tesoreria dona`: due transazioni invece di una.
- `/clan promuovi`: conta e poi scrive (tetto superabile).
- `reset_premium_registry` non ripristina `is_premium_active`.
