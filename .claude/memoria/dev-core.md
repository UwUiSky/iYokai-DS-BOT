# Memoria di dev-core

## Aggiornata
06/10/2026 · ramo `feat/f7-quadro` · base `c64f4fb`

## In corso
- F7 passo 2 (orchestratore): spostare i comandi nei gruppi con
  `aggiungi_a_gruppo` e `registra_gruppi_usati(tree)`; `/owner` a parte.

## Fatto
- R1-bis: `core/bot_ready.py`, risolutore fissato in `safe_http`,
  scheduler con tentativi (migrazione `0003`), schema dell'import
  della configurazione (`0004`), `ENVIRONMENT` obbligatoria,
  `/owner shell` che ferma tutti i processi figli.
- `scripts/smoke.py` e il suo test.
- F7 quadro (#76): `core/command_groups.py` (16 gruppi), `core/command_access.py`
  (livelli, check, ruoli admin/mod/modban), test caratteri/nomi/permessi
  in `test_command_tree_invariants.py`. Nessun comando spostato.

## Cose imparate
- La suite completa dura circa 9 minuti (3141 test).
- `config` è un dataclass congelato: nei test si sostituisce `ca.config` con un
  SimpleNamespace. Un sotto-gruppo controlla solo il padre diretto: usare `GruppoYokai`.
- Il rifiuto di accesso è `AccessoNegato`, risposto da `handle_app_command_error`
  (core/premium.py): il check non risponde mai da solo.
- Oggi il comando più pesante è `/automod` (3028 caratteri): nessun allarme a 6800.

## Aperto
- F1 resto: #69, #70.
- #136: `/config export` scrive `null` che l'importazione rifiuta.
- #141: aggiornamento a caldo dal proprietario (D21).
- #135, ultima voce: `reset_premium_registry`.
