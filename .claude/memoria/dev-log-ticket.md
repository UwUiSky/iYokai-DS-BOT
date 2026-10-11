# Memoria di dev-log-ticket

## Aggiornata
11/10/2026 · ramo `feat/giro-logt` (copia /home/claude/wt/logt) · base `0e7753a`

## In corso
- Giro finito: gruppo 1 (log+router) e gruppo 2 (snipe, 5.9) chiusi. Restano fuori: NF-13/6.9 (F9), #145 lato premium.
- Prossimo: smoke del ramo (`scripts/smoke.py --base 0e7753a`, in background), push, rapporto.

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

- Giro logt, gruppo 1: NF-01 router (`core/channel_router.py`, migr. 0028, tipi eventi/messaggi/voce/server), `/log crea-canali|crea-forum|ignora`, NF-02 `message_logs.py` (migr. 0029), 5.5 avviso unico, 5.6 spostamenti raggruppati + mute proprio, 5.7 soundboard da eventi (servizio ora segnaposto), 5.8 `___hidden___`, #145 `invalida_verdetto_premium`.

- Giro logt, gruppo 2: NF-03 `/utility snipe|editsnipe` (modulo `snipe`, 5 min, solo memoria), M 5.9 ghost ping non scatta se cancella un moderatore (registro), ghost ping via router.

- Giro logt, correzioni del cacciatore-bug: righe del router `esplicito` (migr. 0030: le righe nate dal ripiego seguono il generale), blocco+ricerca post archiviati nel forum, avviso segnato dopo il DM, registro di controllo per voce (id/conteggio), snipe con potatura/tetto per server/ignora/moderatori, transcript ticket via router, permessi forum, tetto 1/min per mute propri.

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

- Router: destinazione = riga `output_channels` del tipo, altrimenti `log_channel_id`. I test dei log senza DB usano `tests/support/router_fakes.router_senza_scelte`; il canale finto deve avere `.guild = server`.
- Il log dei messaggi usa `logging_avanzato_attivo` (premium); ignora i bot; la modifica di un messaggio fuori cache non si vede (si usa `on_message_edit`).
- Il proprietario si trova con `guild.get_member(guild.owner_id)`, non con `guild.owner`.

- Un nome `test*` importato in un file di test viene raccolto da pytest: importare il modulo, non la funzione.

## Aperto
- main.py (non mio) importa ancora `soundboard_log_service`: si può togliere (il servizio non ha più ciclo).
- #145: serve che chi cambia whitelist/cassa/abbonamenti (core/premium.py, dev-core) chiami `advanced_logs.invalida_verdetto_premium(guild_id)`.
- Router: moderazione (sanzioni), automod, allarmi e benvenuto non passano ancora dal router (§18.1 resta `[~]`).
- M 3.14: nessun messaggio all'utente (i log sono listener, niente interazione);
  se serve un avviso va nel comando che accende il modulo (/config, fuori area).
- #144: unlock dopo riavvio del bot col canale ancora bloccato rimette None (perde un connect=True originale). Per renderlo persistente serve una colonna in voice_temp_channels (run_migrations idempotente): decide l'orchestratore.
