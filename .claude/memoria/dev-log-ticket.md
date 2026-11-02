# Memoria di dev-log-ticket

## Aggiornata
27/10/2026 · ramo `feat/r10logt` (copia /home/claude/wt/r10logt, DB iyokai_wr10logt) · migrazioni 0300-0309 (usate 0300, 0301, 0302)

## In corso
- r16ticket (ramo feat/r16ticket, DB iyokai_wticket, migrazioni 0520-0527): T1 fatto (TKT-006/009/045/046, 0520-0521). Previsione: T1, poi T2.
- Prossimo: T2 = TKT-070/071/074 (transcript HTML con jinja2 autoescape+CSP, formato, ZIP con sole immagini ricodificate da core/immagini_pipeline.py) + 0524 colonne transcript. Poi T3 (TKT-067/068/079 nel menu Gestisci `MenuGestisci` in cogs/tickets/tickets.py), T4 (029/064/035), T5/T6 = issue #156 e #157.
- Smoke da fare dall'orchestratore.

## Fatto
- Giri F1-r8: vedi git log (router, snipe, M 5-7, NF-01/02/03/13/33, #119/#120/#127/#139 in parte).
- r10: c210f52 /log cerca ruolo+giorni · f364d84 diff permessi canale · poi ignora esteso, VOC-010/013/016, TKT-051/063/027/026.

## Cose imparate
- Menu del tasto destro nel bot principale: test_command_tree_invariants conta solo `chat_input` (`_radici`); i menu hanno il nome inglese in locales/en-US/comandi.json sezione `menu`.
- Menu Gestisci = `MenuGestisci` (DynamicItem Select, tkt:gst:<id>) aggiunto al benvenuto da `_vista_benvenuto`; le azioni staff nuove vanno li, mai in /ticket.
- `owner immagini-trappola` senza descrizione inglese: test_command_translator rosso su main (non mio).
- Rinomine sempre da `core/channel_rename.py`; cancellazione dei ticket dallo scheduler, non da un task.
- `channel.set_permissions(x, connect=False)` SOSTITUISCE l'overwrite di x: `overwrites_for` + `update` + `overwrite=`.
- Listener premium: `core.security_access.premium_sbloccato(guild_id, modulo, bot)`; nei test bot finto con `get_guild` -> None.
- Nei test dei vocali `Scena` (tests/test_voice_temp_correzioni.py); `overwrites_for.return_value` dal test.
- `can_moderate` nega i ruoli pari: proprietario e bot con `top_role` (helper `_con_ruolo`).
- F7: `@comando_di_gruppo` + `CogConGruppi`; i test con `bot.add_cog` fanno `remove_cog` (GRUPPI globali).
- Router: destinazione = riga `output_channels`, altrimenti `log_channel_id`; test senza DB con `router_fakes`.
- Proprietario: `guild.get_member(guild.owner_id)`, non `guild.owner`.
- Un nome `test*` importato in un file di test viene raccolto: importare il modulo.
- Ogni log passa da un interruttore (core/log_eventi_logic.py, INTERRUTTORI); D15: chi scrive lo decide core/bot_roles.py.
- DynamicItem: `interaction_check` con `super()` + blacklist (test_ui_base_wiring).
- Metodo di repository nuovo = chiamante in produzione; tabella nuova = core/data_registry.py (figlie prima).
- Niente chiavi nuove in guild_config.settings: tabella propria.
- Misura dei gruppi: scratchpad/tkt_peso.py (stdout solo, 2>/dev/null). Traduzioni: aggiungere senza riordinare il JSON.
- Migrazione cambiata dopo l'applicazione: DROP tabelle + `DELETE FROM schema_migrations WHERE version=N`.
- Test ticket: svuotare `ticket_opzioni_repo._cache` e `rename_tracker._renames` nella fixture; `DELETE FROM scheduled_actions`.
- Peso di `/gestione`: vicino a 6800; descrizioni dei parametri brevi.
- Mai `git stash` con un test in background.

## Aperto
- Router: il benvenuto non passa dal router (§18.1 `[~]`, file di utilità).
- Restano: #119 LOG-029; #127 VOC-014, 017, 021; #120 TKT-006, 029, 031, 032, 035, 045, 046, 064, 067, 068, 070, 071, 073, 074, 079, 088; #139 parole chiave AI e archivio file; 18.7 (area moderazione).
- 13.10 transcript: serve la prova live con l'intent acceso.
