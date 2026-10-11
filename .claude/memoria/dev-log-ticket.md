# Memoria di dev-log-ticket

## Aggiornata
11/10/2026 · ramo `feat/f7-ticket-musica` (copia /home/claude/wt/f7e) · base `1e5525c`

## In corso
- Niente a metà: F7 passo 3b chiuso per ticket e vocali. Resta la prova live.

## Fatto
- F1, moderazione + log + ticket + vocali: unito su main con
  `3758f2a` (nuovo `core/channel_rename.py`, migrazione `0010`).
- Voci rapide F1 (log dei ruoli, `/voice transfer`).
- #134 `/voice kick` assente: messaggio vero (`4c01028`).
- #134 `/voice lock`/`unlock`: cambiano solo "Connetti" (`523875a`).
- #134 M 3.14 log avanzati premium: `logging_avanzato_attivo` su ogni listener e sul servizio soundboard.
- #144 `/voice kick`: gerarchia con `can_moderate` + admin/moderatori protetti dai non-staff.
- #144 `/voice unlock`: ripristina il Connetti di prima del lock (memoria in-process `_connect_prima_del_lock`, senza migrazione).
- #134 `db.remove_guild_setting` pubblica (la privata è sparita), ticket e rollback la usano.

- F7 3b (#76): ticket in `/ticket` + `/gestione ticket`, vocali in `/voice` + `/gestione voice` (commit `65a80ed`, `99e23ce`).

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
- F7: `@comando_di_gruppo` + `CogConGruppi`; i test dei cog caricati con `bot.add_cog` devono fare `remove_cog` (i GRUPPI sono globali). Sotto-gruppo di /gestione = costante `GESTIONE_TICKET`/`GESTIONE_VOICE`.
- Stato in-process dei vocali: i test riusano gli id canale (2000+), azzerarlo nella fixture.

## Aperto
- M 3.14: nessun messaggio all'utente (i log sono listener, niente interazione);
  se serve un avviso va nel comando che accende il modulo (/config, fuori area).
- #144: unlock dopo riavvio del bot col canale ancora bloccato rimette None (perde un connect=True originale). Per renderlo persistente serve una colonna in voice_temp_channels (run_migrations idempotente): decide l'orchestratore.
