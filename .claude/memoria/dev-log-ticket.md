# Memoria di dev-log-ticket

## Aggiornata
21/10/2026 · ramo `feat/r8tkt` (copia /home/claude/wt/r8tkt, DB iyokai_wr8tkt) · base fa3f4a5 · migrazioni 0220–0229

## In corso
- Giro r8 (per FILE). Previsione 5 gruppi: A apertura/accesso (#120 007-009, 017-024), B canale e avvisi
  (025, 030, 033, 037-044), C presa e chiusura (028, 034, 050, 052-055, 057, 075), D #139 AI, E #62 residui.
- Comandi nuovi in `/ticket` (peso 1149/6800, 13 figli) con `@richiedi(Livello.ADMIN)` per le opzioni;
  `/admin` è a 5502 (non toccarlo: lo usano anche gli altri agenti).
- A fatto: cogs/tickets/opzioni.py (/ticket opzioni 10 comandi, lista-nera, sospendi, azzera-pausa, reperibile, apri);
  /ticket = 19 figli, 4329/6800. TKT-009 come `/ticket apri messaggio:<link>` (nessun menu contestuale nel bot).
- C fatto: presa (028/050/052/053), chiusura (054/057), fine ticket (039/043/075), /ticket note (034),
  /ticket chiedi-chiusura (055, azione `ticket_richiesta_chiusura`), «Torna all'inizio» (040). /ticket = 21 figli.
- D fatto: #139 AI in risposte.py + core/ticket_ai_logic.py (sollecito tradotto, scelta tra approvate, ruolo mod/admin);
  AI ferma = strada per parole. Test tests/test_ticket_ai.py.
- Prossimo passo: E #62 residui (leggi issue 62, MODIFICHE_ESISTENTE «M 6.»), poi documenti
  (SPEC §13.14–20 e §25.97/98, VERIFICA_LIVE, REGISTRO_RISOLTE, COMMAND_LIST) e smoke.

## Fatto
- Giri F1–r4: router NF-01/02, snipe NF-03, M 5.x, M 6.1-6.8, #145, NF-13 (0100), NF-33 ModMail (0101),
  #139 senza AI (0102, 0105), catalogo log #119 (0103), #120 TKT-047/048/049/056/058/069, #127 VOC-001…005; tutto su main.

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
- Misura dei gruppi: tests/test_command_tree_invariants (`_albero_vero`, `conta_caratteri`); script in scratchpad.
- Migrazione cambiata dopo l'applicazione: DROP tabelle + `DELETE FROM schema_migrations WHERE version=N`.

## Aperto
- Router: sanzioni, automod, allarmi e benvenuto non passano ancora dal router (§18.1 `[~]`).
- #144: /voice lock dopo un riavvio perde un connect=True originale (serve colonna: decide l'orchestratore).
