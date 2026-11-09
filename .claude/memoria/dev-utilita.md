# Memoria di dev-utilita

## Aggiornata
09/11/2026 · ramo feat/r20util (worktree /home/claude/wt/r20util, env scratchpad/env_r20util.sh, DB iyokai_w20util) · blocco Utility #128 B8-B15, D69. Migrazioni da 0547 (0546 presa da B7).

## In corso
- r22util (feat/r22util): B22 fatto (0559). Prossimo: B23 in cogs/utility/sondaggi_bottoni.py (`inizia_tra` su bottoni con stato programmato + repo.apri + azione scheduler di apertura; `/sondaggi gestisci azione:elenco|riepilogo|chiudi`; poll.py nativo: inizia_tra, chiudi_a_voti con on_raw_poll_vote_add + Poll.end, migrazione 0560 sondaggi_nativi), poi B24 /eventi (0561 eventi, eventi_iscritti; gruppo nuovo in command_groups + AUDIENCE + generate_command_list + comandi.json). Smoke da fare (non lanciato).
- Aperto per altri: tests/test_command_search_bilingue.py e _bug147 falliscono anche su origin/main.

## Fatto
- r22util B22 sondaggio a bottoni: repo con advisory lock, DynamicItem sb:<id>:<n>, pesi, modifica, chiusura (0559). Migrazioni libere da 0559 a 0569.
- r21util B20 tag reazioni/si_cancella_dopo (scheduler)/cancella_messaggi/anche_modificati; B21 /tag crea|modifica|elimina|prendi, /admin-tag tag creatori|sostituisci|esporta|importa|gruppi (0557 ha tutte le colonne); UTL-184 /mod-ban massa invito.
- r21util B16 citazioni+uso comandi+registro staff (0555); B17 emoji/sticker/thread/voice vai/massa esporta; B18 regex/inizia/svuota/globali (0556); B19 gruppi /tag e /admin-tag, opzioni, pesi, 4000 (0557). /fun quote NON spostato (cogs/fun e di r21fun).
- r20util B15 conteggio: traguardo, importa, avvisami (0553). togli_canale cancella anche punteggi, traguardi e avvisi del canale.
- r20util B14 conteggio: cog nuovo cogs/utility/conteggio.py, /admin-giochi conteggio canale|regole, /giochi conteggio classifica (0552); tolto da coin_games.
- r20util B13 inviti: riallinea/azzera/esporta/statistiche + segnaposto benvenuto (0551). UTL-184 non fatto (cogs/moderation, non mio).
- r20util B12 inviti: codici, etichetta+ruolo, crea, cancella (0550). Ruolo solo se codice riconosciuto, non pending, gerarchia di bot e staff.
- r20util B11 inviti: /admin-inviti impostazioni|bonus|escludi, ingressi finti (0549). Rientro rilevato solo entro 90 giorni (le righe degli usciti scadono).
- r20util B9-B10 giveaway: partecipanti, riepilogo, opzioni, ruoli escluso/premio, immagine, modifica, riestrai, /fun casuale membro (0548).
- r20util B8 starboard: classifica/caso/blocca/canale_auto (0547).
- r19util B1 /utility caratteri|cronometro|novita + gruppo /web (wiki, dizionario, emergenza); B2 /web meteo|film|gioco|prezzo|accorcia (0540); B3 /admin-messaggi scrivi|auto, fissi elenco/modello (0541); B4 embed json|bottoni|altri|V2 (0542); B5 programmati ripeti/ora/salta (payload, niente 0543); B6 compleanni staff/prossimi, iscritti promemoria, fuso, menu Orari (0544); B7 suggerimenti opzioni (0545).
- Giri vecchi (r4-r11): autorole, starboard, tag, autoresponder, greetings, role menu, embed, contatori, compleanni, inviti, moduli, /ruoli, /utility scheda, suggerimenti decisi, poll, promemoria ripetuti, attività, benvenuto extra, link d'invito personali (git log).

## Cose imparate
- Menu del tasto destro nel tree: get_commands() li include; command_search li rompe (vedi Aperto). Un cog con ContextMenu: cog_load chiama super().cog_load() (CogConGruppi) e poi add_command.
- Tag: opzioni in colonne di custom_commands (0557), risposte con peso in custom_command_risposte; chi usa un tag passa da _rifiuto (sync) e _rifiuto_gruppo (async). Cancellazioni future via scheduler (AZIONE_CANCELLA_RISPOSTA).
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
- UTL-184 `/mod-ban massa invito codice:` non fatto: è in cogs/moderation (r19mod). Servono: completamento sul codice + ban di massa dei membri entrati con quel codice (invite_joins.code).
- Pannello web: editor benvenuto elenca i segnaposto (templates/editor_benvenuto.html) senza i 4 nuovi.
- Giveaway: immagine = URL dell'allegato (i link CDN di Discord scadono): da provare dopo un giorno. Test «cricchetto» test_repository_callers: tolto count_entries.
- Starboard: se la bacheca cambia canale con blocca acceso, il vecchio resta bloccato (non si sblocca da solo).
- test_command_policy::top_level_ha_un_pubblico fallisce su main per il menu «Apri ticket» (AUDIENCE, ticket): non mio.
- safe_http.USER_AGENT senza contatto: MET Norway e Wikimedia chiedono un contatto (core, non mio).
- Alternative D18 non fatte: UTL-111 (comando programmato), azioni in borsa in /web prezzo (nessuna fonte gratis).
- Pannello web: nessuna voce per le nuove impostazioni (messaggi_auto, suggestions_config, web_impostazioni).
- Fuso dell'ora fissa dei programmati: ora Europe/Rome fisso (non c'è un fuso per server); potrebbe usare utente_fuso.
- `embed modifica` su un messaggio con più embed lo riduce al primo; il menu eventi dei log (24/25) va diviso prima di nuove voci (U14).
- Scheletri (counters, forms, starboard, birthdays, autoroles, invites, activity_stats, autoresponder, custom_commands, embed_builder): F9/F13. #66: resta 10.14 (setup.py, non mio).
