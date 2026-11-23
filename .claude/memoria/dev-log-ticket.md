# Memoria di dev-log-ticket

## Aggiornata
23/11/2026 · ramo `feat/r3tkt` (wt-120, DB iyokai_w120) · #120 TKT-072 trascrizioni (D111, D114), migrazione 0774: FATTO. Resta: smoke dall'orchestratore, prova live (VERIFICA_LIVE «giro r3tkt»), chiave `TICKET_TRASCRIZIONI_KEY` nel .env.
21/11/2026 · ramo `feat/r2tkt` (wt-120, DB iyokai_w120) · #120 controllo voce per voce, migrazioni 0770-0773: FATTO (vedi CONTROLLO_AREE_CHIUSE.md, D101). Resta: smoke dall'orchestratore e prova live.
18/11/2026 · ramo `feat/r2log` (copia /home/user/wt-119, DB iyokai_w119) · #119 catalogo log, migrazioni 0710-0719.
10-17/11/2026 · giri r152img (0304), r160 (D74 parti 1-3), r18ticket (0526, 0534), r10logt (0300-0302): vedi sotto e git log.

## In corso
- r2log (ramo feat/r2log, wt-119, DB iyokai_w119, migrazioni 0710-0719, usate 0710 e 0711) #119: FATTO (4 blocchi, vedi git log): LOG-001..004, 010, 011, 014, 015, 016, 018..020, 025, 026, 028. Resta solo: smoke dall'orchestratore, prova live (VERIFICA_LIVE «giro r2log»), COMMAND_LIST rigenerata. Aperto: timeout di Discord che scade da solo non lascia riga (serve un timer nella moderazione); il benvenuto non passa dal router.
- Precedenti, smoke da fare e prove live in VERIFICA_LIVE: r160 parti 2b-3 (allegati sicuri D74, conversioni, `/admin-log webhook` a nome utente), r152img (D61, download allegati), r18ticket (T4 autochiusura, thread privati).

## Fatto
- Giri F1-r8: vedi git log (router, snipe, M 5-7, NF-01/02/03/13/33, #119/#120/#127/#139 in parte).
- r10: c210f52 /log cerca ruolo+giorni · f364d84 diff permessi canale · poi ignora esteso, VOC-010/013/016, TKT-051/063/027/026.

## Cose imparate
- Trascrizioni (TKT-072): contenuto cifrato in `ticket_trascrizioni.cifrato` (AAD = server + ticket, `core/ticket_trascrizioni_logic.py`); scadenza e pulizia dal registro dati (`Scadenza("scade_il", 0)`); la pagina servita ha CSP sua passando da `CHIAVE_DOWNLOAD` (il middleware sovrascrive le intestazioni). `_file_transcript(..., parti_out=[])` raccoglie le pagine HTML per la conservazione. Formato di base ora «entrambi»: i test di testo puro usano `Opzioni(transcript_formato="testo")`.
- `discord.AllowedMentions(users=[...])` lascia everyone e roles accesi: sempre `everyone=False, roles=False` espliciti. Un log di azione non deve mai far fallire una chiusura (try/except dentro l'hook).
- Menu nelle finestre: `discord.ui.Label(text, component=Select/UserSelect/...)`; i valori si leggono da `label.component.values`; nei test `component._values = [...]`.
- Log azioni ticket: `tickets.registra_azione(guild, azione, ticket, ...)` (interruttori in `ticket_log_azioni`, tutti spenti di base, tipo router `ticket`). Benvenuto e risposte pronte: `form.testo_benvenuto` (elenco chiuso) e `form.nome_sicuro`.
- Rotte e formati dei log: un solo punto `core/log_personalizza.personalizza(guild, tipo, evento, dest, embed)`, chiamato da `_send_log` (basic), `send_event_embed` (advanced), `_scrivi` (messaggi). Un log nuovo che non passa da li' non ha ne' rotta ne' formato. Rotta = solo TextChannel (un forum riscriverebbe `output_channels` del tipo); il tipo `rotta_<interruttore>` serve solo per l'avviso al proprietario.
- Istantanee (LOG-028): segreto mai salvato (impronta SHA-256), stessa risposta per link sbagliato/scaduto/negato; tetto 5 per server con `pg_advisory_xact_lock`. Un test che usa `test_web_panel_server`-style costruisce una mini `web.Application` e passa `pagina`/`errore` finti.
- Test dei log con `clean_db`: se un comando legge `log_personalizza_repo`, il test deve sostituire il repo con uno sul pool del test (`monkeypatch.setattr(modulo, 'log_personalizza_repo', ...)`).
- Comandi.json en-US: sezioni a 1 spazio (`"nomi": {`), voci a 2; il test `test_nessuna_voce_inglese_resta_senza_comando` boccia un nome tradotto senza comando: aggiungerlo insieme al comando.
- Menu del tasto destro: Discord ne ammette 15 per tipo, discord.py 5: il tetto 15 sta in BlacklistAwareCommandTree (anche i test full_tree). Conteggio con tests.support.full_tree (`bot.tree._context_menus`, tipo 3 = messaggio).
- Cache dei verdetti immagine: nei test che ripetono la stessa immagine `immagini_pipeline.svuota_cache()`.
- D74 parte 2b: le conversioni passano SOLO dal servizio (`sb.converti`, nessun modo B); nei test si avvia `immagini_servizio.serve(socket)` nello stesso processo (fixture `attivo` in test_allegati_copia). ffmpeg: `-safe 1` non esiste fuori da concat (errore), si usa formato esplicito + `-protocol_whitelist file,pipe`. pypdf 7: niente `add_js`; si ripulisce la pagina del lettore prima di `add_page`. Un test di testo con NUL/ESC deve avere un primo blocco di testo vero (il rilevatore e' sui primi 4096 byte).
- D74 parte 2a: ogni allegato utente mostrato dal bot passa da `allegati_mostra.prepara` (copia PNG o riga di scheda, mai l'URL). Formati nuovi: lettori dei byte in `immagini_byte_logic`, apertura in sandbox con `safe_image.FORMATI_SANDBOX` (FORMATI_AMMESSI resta per avatar e benvenuti). La cache dei verdetti non tiene il PNG: la stessa immagine entro la durata della cache da' solo scheda (da sistemare, i fake di `analizza_immagine` nei test hanno firma fissa).
- D74: decisione unica = `allegati_tipo_logic.decidi` (immagine/scheda/rifiuta); `immagini_pipeline.esamina_allegato` la applica e da' la copia PNG solo alle immagini vere; mai piu' file non immagine rimandati. Nomi: `nome_pulito` (toglie U+202E ecc.), mai `nome_file_sicuro` nuovo.
- D61: tipo sempre da `immagini_byte_logic.riconosci_tipo`; `immagini_pipeline.copia_ricaricabile` e' l'unico punto per ricaricare un allegato (backup, ticket). Il bot non decodifica mai byte utente: miniature solo dalla PNG della sandbox.
- Download allegati: `/allegato/<token firmato>` solo su `WEB_ALLEGATI_PUBLIC_URL`; il middleware `sicurezza` sovrascrive le intestazioni: le proprie passano da `CHIAVE_DOWNLOAD`. `config` e' frozen: nei test si sostituisce `modulo.config`.
- Thread ticket: `guild.get_channel` NON vede i thread (usa `get_channel_or_thread`); in un DynamicItem l'etichetta sta in `.item`; con il thread niente overwrites/categorie (guardie `isinstance(..., discord.Thread)` in tickets.py).
- T4: logica pura in core/ticket_autoclose_worker.py, giro ogni 2 min in cogs/tickets/inattivita.py (stato nel DB); la riserva si usa in `_canale_dalla_riserva` (tickets.py). `create_ticket` restituisce il NUMERO, non l'id: nei test `get_ticket_by_channel(...).id`.
- Ogni chiamata Bash e nuova: `. scratchpad/env18.sh` (DATABASE_URL w18tk) in OGNI comando pytest, se no conftest usa iyokai_test.
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
- Mai `git stash` con un test in background.

## Aperto
- Router: il benvenuto non passa dal router (§18.1 `[~]`, file di utilità).
- Restano: #119 LOG-029; #127 VOC-014, 017, 021; #120 TKT-006, 029, 031, 032, 035, 045, 046, 064, 067, 068, 070, 071, 073, 074, 079, 088; #139 parole chiave AI e archivio file; 18.7 (area moderazione).
- 13.10 transcript: serve la prova live con l'intent acceso.
