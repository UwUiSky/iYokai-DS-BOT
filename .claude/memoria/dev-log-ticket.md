# Memoria di dev-log-ticket

## Aggiornata
05/10/2026 · ramo `fix/f1-144` (copia /home/claude/wt/v144) · base `d31af05`

## In corso
- Niente a metà: le 2 voci di #144 sono chiuse. Resta la prova live (vedi rapporto).

## Fatto
- F1, moderazione + log + ticket + vocali: unito su main con
  `3758f2a` (nuovo `core/channel_rename.py`, migrazione `0010`).
- Voci rapide F1 (log dei ruoli, `/voice transfer`).
- #134 `/voice kick` assente: messaggio vero (`4c01028`).
- #134 `/voice lock`/`unlock`: cambiano solo "Connetti" (`523875a`).
- #134 M 3.14 log avanzati premium: `logging_avanzato_attivo` su ogni listener e sul servizio soundboard.
- #144 `/voice kick`: gerarchia con `can_moderate` + admin/moderatori protetti dai non-staff.
- #134 `db.remove_guild_setting` pubblica (la privata è sparita), ticket e rollback la usano.

## Cose imparate
- Rinomine sempre da `core/channel_rename.py`.
- Cancellazione dei ticket dallo scheduler, non da un task.
- `channel.set_permissions(x, connect=False)` SOSTITUISCE l'overwrite di x:
  per cambiare un permesso solo, `overwrites_for` + `update` + `overwrite=`.
- Nei test di un listener premium il bot finto deve avere `get_guild` -> None (un MagicMock risulta 'boost').
- Listener premium: `core.security_access.premium_sbloccato(guild_id, modulo, bot)`.
- Nei test dei vocali `Scena` (tests/test_voice_temp_correzioni.py);
  `canale.overwrites_for.return_value` va impostato dal test.

- `can_moderate` nega i ruoli pari: nei test del kick proprietario e bot vanno impostati con `top_role` (helper `_con_ruolo`).

## Aperto
- M 3.14: nessun messaggio all'utente (i log sono listener, niente interazione);
  se serve un avviso va nel comando che accende il modulo (/config, fuori area).
