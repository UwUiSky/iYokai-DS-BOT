# Memoria di dev-utilita

## Aggiornata
09/11/2026 · ramo feat/r19util (worktree /home/claude/wt/r19util, env scratchpad/env_r19util.sh, DB iyokai_w19util) · blocco Utility #128, D69, migrazioni 0540-0545 (0543 non usata)

## In corso
- r19util B1-B7 CHIUSI e pubblicati (commit 869b056, 1af9700, 26ca2ee, 09b7fb7, 52f94c1, 49eb237, aad3116). Smoke da fare (non lanciato).
- Prossimo: B8 starboard (0546), B9-B10 giveaway (0547), B11-B13 inviti (0548-0549), B14-B16 conteggio/citazioni (0550-0553), B17 server, B18 risposte (0554), B19-B21 tag (0555-0557), B22-B24 sondaggi/eventi (0558-0560), B25-B28 script (0561-0563). Vedi scratchpad/disegno_utility.md.

## Fatto
- r19util B1 /utility caratteri|cronometro|novita + gruppo /web (wiki, dizionario, emergenza); B2 /web meteo|film|gioco|prezzo|accorcia (0540); B3 /admin-messaggi scrivi|auto, fissi elenco/modello (0541); B4 embed json|bottoni|altri|V2 (0542); B5 programmati ripeti/ora/salta (payload, niente 0543); B6 compleanni staff/prossimi, iscritti promemoria, fuso, menu Orari (0544); B7 suggerimenti opzioni (0545).
- Giri vecchi (r4-r11): autorole, starboard, tag, autoresponder, greetings, role menu, embed, contatori, compleanni, inviti, moduli, /ruoli, /utility scheda, suggerimenti decisi, poll, promemoria ripetuti, attività, benvenuto extra, link d'invito personali (git log).

## Cose imparate
- Un gruppo nuovo: _DEFINIZIONI in core/command_groups.py + AUDIENCE in tests/support/command_policy.py + nome in scripts/generate_command_list.py + descrizione in locales/en-US/comandi.json.
- Testi: locales/{it,en-US}/testi.json (indent 2, ordine libero) e comandi.json (indent 1; i nomi di parametri NON vanno in «nomi»). Aggiunta senza riscrivere: scratchpad/uti19_agg.py. Funzioni importate che iniziano per «test» le raccoglie pytest.
- Scheduler: i messaggi programmati e i promemoria stanno nel payload di scheduled_actions (nessuna tabella). Handler che non rilancia = niente doppioni; per le serie metti in coda il prossimo giro PRIMA di inviare. get_pending_action non dà execute_at (usa payload["quando"]).
- Impostazioni di moduli senza passare da config_history/config_impostazioni (non miei): tabella propria + repo con copia in memoria che si riempie solo dopo lettura riuscita (messaggi_auto, suggestions_config).
- LayoutView: BaseLayoutView in core/ui_base.py (e nella lista del test ui_base_wiring). V2: 40 componenti, 4.000 caratteri, niente content/embed.
- Menu del tasto destro: non guild_only (KNOWN_NOT_GUILD_ONLY = AUDIENCE senza gruppi) e nome in AUDIENCE; cog_load aggiunge, cog_unload toglie.
- DynamicItem per bottoni persistenti (cronometro, tag degli embed, ricordalo anche a me, chi l'ha scritto): template + add_dynamic_items in setup/cog_load.
- Servizi esterni: chiave nell'intestazione (aiohttp diretto, host fisso), mai nell'URL: safe_get logga gli URL. User-Agent di safe_http è «lettore di feed».
- Log al server: core.channel_router (destinazione + invia_a, TIPO_SERVER/MODERAZIONE). Pubblicazione annunci: 10 all'ora per canale, un solo avviso.
- clean_db + Repo(pool_provider=lambda: clean_db) per i test su DB; i test di cog che toccano un repo nuovo devono patcharlo (suggestions_limiti, embed_builder).
- Pesi: scratchpad/uti19_pesi.py <gruppo>. Dopo B1-B7: utility 18 figli (non aggiungerne: usare opzioni), admin-messaggi 5119/8, admin-bot 4220, level 3182.
- Elenchi: descrizioni parametri ≤95 caratteri; nessuna opzione obbligatoria dopo una facoltativa; Range su ogni testo libero.
- Migrazione già applicata in un DB di test: mai riscriverla, usare il numero dopo.

## Aperto
- test_command_policy::top_level_ha_un_pubblico fallisce su main per il menu «Apri ticket» (AUDIENCE, ticket): non mio.
- safe_http.USER_AGENT senza contatto: MET Norway e Wikimedia chiedono un contatto (core, non mio).
- Alternative D18 non fatte: UTL-111 (comando programmato), azioni in borsa in /web prezzo (nessuna fonte gratis).
- Pannello web: nessuna voce per le nuove impostazioni (messaggi_auto, suggestions_config, web_impostazioni).
- Fuso dell'ora fissa dei programmati: ora Europe/Rome fisso (non c'è un fuso per server); potrebbe usare utente_fuso.
- `embed modifica` su un messaggio con più embed lo riduce al primo; il menu eventi dei log (24/25) va diviso prima di nuove voci (U14).
- Scheletri (counters, forms, starboard, birthdays, autoroles, invites, activity_stats, autoresponder, custom_commands, embed_builder): F9/F13. #66: resta 10.14 (setup.py, non mio).
