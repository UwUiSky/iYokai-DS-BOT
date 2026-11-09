# Memoria di dev-utilita

## Aggiornata
09/11/2026 · r24util (feat/r24util, DB iyokai_wr24util, env /tmp/env_wr24util.sh) · #128 B25-B28 fatti (parte C: tag con script). Migrazioni libere 0565-0569.

## In corso
- #128 parte C finita. Prossimo: blocchi successivi del disegno (se ce ne sono), poi smoke da fare (non lanciato) dell'orchestratore.
- Aperto per altri: tests/test_command_search_bilingue.py e _bug147 falliscono anche su origin/main.

## Fatto
- r24util B25: core/tag_script_logic.py (async, interprete proprio, tetti 200 op/prof 10/uscita 4000/valore 2000/tempo 1s, regex re2), solo se ha_script() in CustomCommandsCog._prepara.
- r24util B26: 0562 tag_dati/tag_errori, tag_script_repo, {dati:} (ArchivioMemoria/ArchivioProva), cogs/utility/automazioni.py (/tag prova, /admin-automazioni script errori).
- r24util B27: 0563 tag_inneschi, tag_inneschi_logic (cron proprio), inneschi.py (reazione/ruolo/intervallo/orario/bottone), CustomCommandsCog.esegui_innesco, hook in BottoneTag.
- r24util B28: 0564 comandi_server/menu_server/slash_server_stato, slash_server_logic + repo, cogs/utility/slash_server.py (albero per server, sync 1 ogni 5 min, 200/giorno, scheduler slash_server_sync).
- r23util B23-B24 sondaggi programmati/nativi (0560), eventi (0561). r22util B22 sondaggio a bottoni (0559). r21util B16-B21 citazioni, emoji/sticker, regex, tag opzioni/reazioni, /tag crea (0555-0557).
- r20util B8-B15 starboard, giveaway, inviti, conteggio (0547-0553). r19util B1-B7 /utility, /web, messaggi auto, embed, programmati, compleanni, suggerimenti (0540-0545).
- Giri vecchi (r4-r11): autorole, starboard, tag, autoresponder, greetings, role menu, embed, contatori, compleanni, inviti, moduli, /ruoli, attività (git log).

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
- Script dei tag: core/tag_script_logic (async). {nome} sconosciuto resta testo (poi render_template). args/username sono dati: escape_mentions. Output tag 4000, ogni valore 2000. Mai eval/exec: c'è un test che lo vieta nel sorgente.
- Gruppo /admin-automazioni: sottogruppi script/inneschi/slash in SOTTOGRUPPI. Nuovo repo con metodo mai chiamato = fallisce test_repository_callers: non aggiungere metodi non usati.
- Comandi del server (B28): l'albero mirror del DB (_monta, solo i nostri nomi), sync = tree.sync(guild) con impronta delle definizioni, non dell'albero. Rows asyncpg jsonb tornano come stringa.
- Range[int,...] ≤ 2**31 (test limiti a 53 bit). Un test che passa dal cog con un repo nuovo deve patcharlo (tag_script_repo, tag_inneschi_repo).

## Aperto
- Sondaggi nativi programmati: non compaiono in `/sondaggi gestisci` (solo bottoni) e non si annullano; il conteggio a N voti conta i voti (non i votanti) e perde quelli arrivati col bot spento.
- Eventi: promemoria solo per chi ha detto «sì»; i bottoni dei messaggi finiti restano ma rispondono «chiuso».
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
- B25-B28: creatori di tag (non staff) possono usare {dati:set|...} nei loro tag (tetto 1.000 chiavi per server, condiviso). Ora degli script e dei cron: Europe/Rome fisso.
- B28: se il server è quello di sviluppo/owner, la sync all'avvio (core/command_sync) non conosce i comandi del server e potrebbe sovrascriverli: pubblicare in un server normale. Eliminare un tag non toglie il comando del server (risponde «non disponibile»).
- B27: il bottone con innesco risponde in canale a tutti; l'innesco a tempo parla come il bot (`{user}` = bot). Reazione: nessun filtro sul messaggio, solo canale.
