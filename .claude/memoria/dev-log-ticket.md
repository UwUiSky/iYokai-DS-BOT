# Memoria di dev-log-ticket

## Aggiornata
27/10/2026 · ramo `feat/r10logt` (copia /home/claude/wt/r10logt, DB iyokai_wr10logt) · migrazioni 0300-0309 (usate 0300, 0301, 0302)

## In corso
- Giro r10: fatti log (cerca ruolo/giorni, diff permessi, ignora esteso), vocali (aspetto, copia, generatori), ticket (due passi).
- WIP committato: test di controllo in corso, leggere scratchpad/r10logt_t2.log (cercare FAILED) e correggere; poi lo smoke `python3 scripts/smoke.py --base main` una volta; poi #139 (parole chiave AI, archivio file), LOG-029, VOC-014/017/021, TKT-070/071/079.

## Fatto
- Giri F1-r8: vedi git log (router, snipe, M 5-7, NF-01/02/03/13/33, #119/#120/#127/#139 in parte).
- r10: c210f52 /log cerca ruolo+giorni · f364d84 diff permessi canale · poi ignora esteso, VOC-010/013/016, TKT-051/063/027/026.

## Cose imparate
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
