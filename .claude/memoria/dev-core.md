# Memoria di dev-core

## Aggiornata
11/10/2026 · ramo `feat/f7-rifiniture` · base `4fe0765`

## In corso
- F7 passo 4 chiuso (6 voci su 6): resta la prova smoke e l'unione fatta dall'orchestratore.

## Fatto
- R1-bis: `core/bot_ready.py`, risolutore fissato in `safe_http`,
  scheduler con tentativi (migrazione `0003`), schema dell'import
  della configurazione (`0004`), `ENVIRONMENT` obbligatoria,
  `/owner shell` che ferma tutti i processi figli.
- `scripts/smoke.py` e il suo test.
- F7 quadro (#76): `core/command_groups.py` (16 gruppi), `core/command_access.py`
  (livelli, check, ruoli admin/mod/modban), test caratteri/nomi/permessi
  in `test_command_tree_invariants.py`. Nessun comando spostato.
- F7 passo 4 (#76): test dei `/comando` citati nelle stringhe (`test_riferimenti_comandi.py`),
  `/owner` mai nell'albero globale, `-cerca-comando` guild_only, descrizioni ≤95,
  prova `/clan bacheca` livello admin, sync solo se cambia (`core/command_sync.py`,
  migrazione `0021_command_sync_state`).

## Cose imparate
- La suite completa dura circa 9 minuti (3141 test).
- `config` è un dataclass congelato: nei test si sostituisce `ca.config` con un
  SimpleNamespace. Un sotto-gruppo controlla solo il padre diretto: usare `GruppoYokai`.
- Il rifiuto di accesso è `AccessoNegato`, risposto da `handle_app_command_error`
  (core/premium.py): il check non risponde mai da solo.
- Autocomplete: i check non si applicano; usare `autocomplete_protetto(livello)`.
  Un `Group` semplice sotto un gruppo protetto dà TypeError: usare `GruppoYokai`.
- Ruoli del bot: id == guild.id o non numerico = non configurato; import/rollback
  li validano (`errore_ruoli_del_bot`).
- Oggi il comando più pesante è `/automod` (3028 caratteri): nessun allarme a 6800.
- `/owner` vive solo in `GRUPPI["owner"]`: i test dell'albero lo leggono da lì (`_radici(bot)`).
- Sync comandi: impronta per ambito (`global`, `guild:<id>`); errore = impronta non salvata.
  Se si cancellano comandi a mano su Discord l'impronta non lo sa: cancellare la riga.

## Aperto
- F1 resto: #69, #70.
- #136: `/config export` scrive `null` che l'importazione rifiuta.
- #141: aggiornamento a caldo dal proprietario (D21).
- #135, ultima voce: `reset_premium_registry`.
