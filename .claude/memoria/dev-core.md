# Memoria di dev-core

## Aggiornata
05/10/2026 · ramo `main` · ultimo commit `3dc9031`

## In corso
- Niente a metà.

## Fatto
- R1-bis: `core/bot_ready.py`, risolutore fissato in `safe_http`,
  scheduler con tentativi (migrazione `0003`), schema dell'import
  della configurazione (`0004`), `ENVIRONMENT` obbligatoria,
  `/owner shell` che ferma tutti i processi figli.
- `scripts/smoke.py` e il suo test.

## Cose imparate
- La suite completa dura circa 9 minuti (3141 test).

## Aperto
- F1 resto: #69, #70.
- #136: `/config export` scrive `null` che l'importazione rifiuta.
- #141: aggiornamento a caldo dal proprietario (D21).
- #135, ultima voce: `reset_premium_registry`.
