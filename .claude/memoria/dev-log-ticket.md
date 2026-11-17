# Memoria di dev-log-ticket

## Aggiornata
17/11/2026 · ramo `feat/r160-allegati-2` (copia /home/user/wt-160b, DB iyokai_w160b) · #160 D74 parte 2b (conversioni PDF, audio, video, testo; HEIC), nessuna migrazione.
17/11/2026 · ramo `feat/r160-allegati` (copia /home/user/wt-160, DB iyokai_w160) · #160 D74 parte 2a (formati in piu', link tolti), nessuna migrazione.
16/11/2026 · stesso ramo · #160 prima parte.
10/11/2026 · ramo `feat/r152img` (copia /home/claude/wt/r152img, DB iyokai_wr152) · usata migrazione 0304 (#152, D61). Sotto: giri precedenti.
27/10/2026 · ramo `feat/r10logt` (copia /home/claude/wt/r10logt, DB iyokai_wr10logt) · migrazioni 0300-0309 (usate 0300, 0301, 0302)

## In corso
- r160 parte 3 (ramo feat/r160-allegati-3, wt-160b): voce 1 FATTA (rispondi allegato = copia sicura). Voce 2 FATTA (log_webhook_utente). Voce 4 NON fatta: il bot principale ha gia' 5 menu di tipo messaggio (limite Discord 5). Prossima: voce 3 copie 30 giorni.
- r160 parte 2b FATTA, smoke da fare (non unito, non pubblicato): `conversioni_worker` + `immagini_sandbox.converti` + `allegati_copia.copia_sicura` collegati a `esamina_allegato`, log (PDF, audio, testo), `allegati_mostra.prepara`, ticket, ModMail, backup (video solo li); HEIC con pillow-heif nel worker. Resta: PDF come pagine-immagine se la ricostruzione fallisce, copie ticket/ModMail 30 giorni, log a nome utente (`/admin-log webhook`), staff->utente di /modmail rispondi (domanda), telefono con copie rifatte (proposta), tempo giornaliero salvato in DB (ora in memoria), prova live (VERIFICA_LIVE «parte 2b»).
- r152img: fatto tutto #152 (allegati_sicuri, log, backup, ticket, spam trap, download). Resta: prova live (VERIFICA_LIVE «giro r152img»), smoke dall'orchestratore, nginx per il sotto-dominio allegati.
- r18ticket (feat/r18ticket, DB iyokai_w18tk): T4 (0534) e #156 thread privati (0526) fatti, in un commit. Resta: prova live (VERIFICA_LIVE) e smoke dall'orchestratore.
- Smoke da fare dall'orchestratore.

## Fatto
- Giri F1-r8: vedi git log (router, snipe, M 5-7, NF-01/02/03/13/33, #119/#120/#127/#139 in parte).
- r10: c210f52 /log cerca ruolo+giorni · f364d84 diff permessi canale · poi ignora esteso, VOC-010/013/016, TKT-051/063/027/026.

## Cose imparate
- Menu del tasto destro: il bot principale ha 5 menu su messaggio (Segnala, Apri ticket, Salva citazione, Riestrai, Orari): pieno. Conteggio con tests.support.full_tree (`bot.tree._context_menus`, tipo 3 = messaggio).
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
- Peso di `/gestione`: vicino a 6800; descrizioni dei parametri brevi.
- Mai `git stash` con un test in background.

## Aperto
- Router: il benvenuto non passa dal router (§18.1 `[~]`, file di utilità).
- Restano: #119 LOG-029; #127 VOC-014, 017, 021; #120 TKT-006, 029, 031, 032, 035, 045, 046, 064, 067, 068, 070, 071, 073, 074, 079, 088; #139 parole chiave AI e archivio file; 18.7 (area moderazione).
- 13.10 transcript: serve la prova live con l'intent acceso.
