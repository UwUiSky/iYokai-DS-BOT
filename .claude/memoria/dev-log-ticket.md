# Memoria di dev-log-ticket

## Aggiornata
05/10/2026 · ramo `fix/f1-134` (copia /home/claude/wt/t134) · base `4b42ada`

## In corso
- Previsione: 4 voci di #134, mi fermo dopo M 3.14.
- Fatte kick, lock/unlock, `remove_guild_setting`. Prossima: gate premium
  in cogs/logging/advanced_logs.py (tutti i listener + `advanced_log_channel`)
  con `premium_sbloccato`, test in tests/test_advanced_logs_premium.py.

## Fatto
- F1, moderazione + log + ticket + vocali: unito su main con
  `3758f2a` (nuovo `core/channel_rename.py`, migrazione `0010`).
- Voci rapide F1 (log dei ruoli, `/voice transfer`).
- #134 `/voice kick` assente: messaggio vero (`4c01028`).
- #134 `/voice lock`/`unlock`: cambiano solo "Connetti" (`523875a`).
- #134 `db.remove_guild_setting` pubblica (la privata è sparita), ticket e rollback la usano.

## Cose imparate
- Rinomine sempre da `core/channel_rename.py`.
- Cancellazione dei ticket dallo scheduler, non da un task.
- `channel.set_permissions(x, connect=False)` SOSTITUISCE l'overwrite di x:
  per cambiare un permesso solo, `overwrites_for` + `update` + `overwrite=`.
- Listener premium: `core.security_access.premium_sbloccato(guild_id, modulo, bot)`.
- Nei test dei vocali `Scena` (tests/test_voice_temp_correzioni.py);
  `canale.overwrites_for.return_value` va impostato dal test.

## Aperto
- #134: resta M 3.14.
