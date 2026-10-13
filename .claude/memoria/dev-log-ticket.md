# Memoria di dev-log-ticket

## Aggiornata
13/10/2026 · ramo `feat/r4-tkt` (copia /home/claude/wt/tkt) · base `main` 793656c · migrazioni da 0100

## In corso
- Giro r4-tkt (per FILE): ordine correzioni → NF-13 → NF-33 → #139 non-AI → cataloghi. Previsione: 4 gruppi.
- Fatto: correzioni, NF-13, NF-33, #139 non-AI (gruppo 3). Prossimo: cataloghi #119/#120/#127 voci piccole
  (log: LOG-023 ignora bot, LOG-009 timeout; ticket: TKT-054 conferma chiusura, TKT-056 motivo, TKT-058 chiudi tutti; vocali: VOC-001 prendi proprietà, VOC-005 bitrate). Migr. libera da 0103.

## Fatto
- Giri precedenti (F1, F7, router NF-01/02, snipe NF-03, M 5.x, M 6.1-6.8, #145): tutti su main.
- Verifica 13/10: #62 e #61 chiuse dal codice (M 6.1-6.8, M 5.1-5.9 con test); #145 chiusa
  (`core/premium_cache.py` + test_premium_invalidazione). Resta solo M 6.9 = NF-13.
- NF-13 (#84): migr. 0100 (ticket_panels, ticket_form_questions, tickets.panel_id/last_activity_at/rating),
  `/gestione ticket pannello-crea|rimuovi|lista|pubblica`, `modulo-aggiungi|rimuovi|mostra`, `chiusura-auto`, `voto`;
  bottoni DynamicItem `tkt:pan:<id>` e `tkt:voto:<id>:<n>`; chiusura per inattività (scheduler `ticket_autoclose`)
  e per uscita utente; test_ticket_form.py, test_ticket_autoclose.py.
- NF-33 (#104): migr. 0101 (modmail_threads, modmail_blocks), `cogs/tickets/modmail.py`, `/gestione ticket dm|dm-blocca`,
  `/ticket rispondi|dm-chiudi`; un solo thread aperto per utente (indice unico globale); test_modmail.py.
- #139 non-AI: migr. 0102 (ticket_standard_replies, colonne in panels/tickets), `cogs/tickets/risposte.py`,
  `core/ticket_standard_logic.py`, `/gestione ticket-auto standard|sollecito|lista|modifica|elimina`, scheduler `ticket_sollecito`;
  hook in tickets.py (on_message, _transcript_senza_bloccare, _crea_ticket); test_ticket_standard.py.

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
- #145: serve che chi cambia whitelist/cassa/abbonamenti (core/premium.py, dev-core) chiami `advanced_logs.invalida_verdetto_premium(guild_id)`.
- Router: moderazione (sanzioni), automod, allarmi e benvenuto non passano ancora dal router (§18.1 resta `[~]`).
- M 3.14: nessun messaggio all'utente (i log sono listener, niente interazione);
  se serve un avviso va nel comando che accende il modulo (/config, fuori area).
- #144: unlock dopo riavvio del bot col canale ancora bloccato rimette None (perde un connect=True originale). Per renderlo persistente serve una colonna in voice_temp_channels (run_migrations idempotente): decide l'orchestratore.
- Test con DB: se cambi una migrazione già applicata a iyokai_wtkt, `DROP` delle tabelle e `DELETE FROM schema_migrations WHERE version=N`.
- Un DynamicItem non passa da BaseView: serve `interaction_check` con `super()` + blacklist (test_ui_base_wiring lo impone).
- Ogni metodo di repository nuovo deve avere un chiamante in produzione (test_repository_callers).
- Tabelle nuove vanno in `core/data_registry.py` (figlie prima delle madri).
- Non mettere chiavi nuove in guild_config.settings (SETTING_*): vanno in cogs/utility/config_history.py (non mio): tabella propria (es. modmail_config).
- I tre dataclass del pannello dopo `imposta_*` sono vecchi: rileggere con `pannello_per_id` nei test.
