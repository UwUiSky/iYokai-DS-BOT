# Memoria di dev-musica

## Aggiornata
11/10/2026 · ramo `feat/f7-ticket-musica` (copia /home/claude/wt/f7e) · base `1e5525c`

## In corso
- Niente a metà. F7 passo 3b chiuso per musica e radio.

## Fatto
- F7 3b (#76): `/music` con sotto-gruppi loop/volume/nonstop, `/nonstop-main` -> `/owner radio` (`6d8894f`).

## Cose imparate
- D10: un nodo per bot. È la prima cosa da fare in F2.
- F7: il controllo owner lo dà il gruppo `/owner` (non c'è più `_is_owner`); il cog toglie `owner` dall'albero globale in `cog_load` (lo aggiunge main.py solo nel server dell'owner).
- Sotto-gruppi come costanti (`SG_LOOP`, `RADIO`): descrizioni con apostrofo rompono le regex.

## Aperto
- Tutta la fase F2 (#64, #45, #47, #48, #126).
- Provare dal vivo `/owner radio`, `/music loop|volume|nonstop`.
