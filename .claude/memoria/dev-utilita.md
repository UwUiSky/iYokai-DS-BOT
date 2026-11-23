# Memoria di dev-utilita

## Aggiornata
23/11/2026 · r3utl (feat/r3utl, DB iyokai_w128) · D111/D116: UTL-226 (0830), UTL-228 (0831), CFG-032, FUN-078, segni FUN-068/070. Non unito, niente push. Smoke da fare.
21/11/2026 · r2utl (feat/r2utl, DB iyokai_w128) · #128 controllo UTL: 85 voci segnate o realizzate, 7 senza codice (UTL-110, 121, 216 in D100; 204, 205, 226, 228 non miei). Migrazioni 0760-0764.

## In corso
- Giro r3utl chiuso (commit 46cfa302, 5185ad09, 5470b232, fc83831b, 47f26d8e). Smoke da fare dell'orchestratore: test_config_orfani, test_azzeramento_dati, test_marchio_strumenti, test_suono_ferma + test_data_registry, test_repository_callers, test_command_groups. Prova live in VERIFICA_LIVE (UTL-226, UTL-228, CFG-032, FUN-078).
- Giro r2utl chiuso (non unito, niente push). Smoke da fare. Righe in revisione/01-analisi/catalogo/CONTROLLO_AREE_CHIUSE.md (sezione 14-utility). Da far rivedere: tag (divieti, alias, embed salvato), canale_testo, esclusi.

## Fatto
- r3utl D111/D116: pulizia a 7 giorni (core/config_orfani_logic, repositories/config_orfani_repo, /admin-bot config pulisci al posto di pulizia, giro 6 ore in config_strumenti); azzeramento dati a 30 giorni (core/azzeramento_dati_logic, azzeramento_repo, cogs/utility/azzeramento_dati.py, reset anche_i_dati/annulla_dati in config_history); strumenti marchio (core/marchio_errori, GestoreMarchio.risincronizza, azioni risincronizza/errori in marchio.py); /music suono-ferma (core/music_sound_logic SuoniInCorso, soundboard.py).
- r2ben/r1/r24 e giri precedenti (#123 #127 #129 #130, D87-D98): vedi git log; ruoli extra in core/ruoli_extra_logic e cogs/utility/ruoli_extra.py.
- r2utl #128: tag (in coda, alias, divieti, ambito pausa, embed, info), risposte (finisce, maiuscole, esclusi, modifica, mostra), canale scorciatoia, orario guidato, embed (autore, link, data, colore, pausa), giveaway (chiudi, annulla, elenco), bacheca (esclusi, stato), compleanni stato, inviti per periodo, avatar. D100. Test: test_*_r2utl.py.
- r2ben #123/#117: core/ruoli_extra_logic, ruoli_guidata_logic, ruoli_immagini, phishing_azione_logic; repositories/ruoli_extra_repo; cogs/utility/ruoli_extra.py (admin-menu-ruoli: ruoli-extra, gruppo, immagine, colori, guidata, personale; utility: colore, ruolo-mio; admin-benvenuto: immagini); ganci in role_menus.py (_blocchi_per, _estendi, _applica atomico, immagine nel messaggio) e greetings.py (_immagine_a_caso). Decisione D98. Test: test_ruoli_extra_cog.py, test_ruoli_extra_logica.py, test_ruoli_guidata_logica.py, test_ruoli_immagini.py, test_phishing_azione_extra.py.

## Cose imparate
- Cancellazione per server senza presenza: `azzeramento_dati_logic._cancella_dati` ripete il ciclo di `retention_worker.purga_server` (REGISTRO) senza controllare guild_presence. Tabella nuova con colonna utente: dichiararla in data_registry (colonne_attore + azzera_attore=False se è solo staff).
- Gli handler dello scheduler hanno firma (guild_id, user_id, payload): la verità sta nel database, non nel payload; handler idempotente. Frozen config: nei test sostituire il nome del modulo (`monkeypatch.setattr(modulo, "config_bot", SimpleNamespace(...))`).
- Un suono di soundboard non si interrompe con l'API: FUN-078 fa uscire il bot entrato solo per il suono. /music ha 24 figli (limite 25).
- Test su DB: `DATABASE_URL=...iyokai_w128` va messo davanti a ogni comando (l'export non resta tra le chiamate).
- Il catalogo vede UTL-047..050 solo con virgole (UTL-047, 048, 049): «..» non è un intervallo. Un test che costruisce tag finti (SimpleNamespace) deve avere i campi nuovi della dataclass (pausa_ambito, vietati, embed_nome).
- Un valore di innesco «ruolo/canale» passa da regex di 15-20 cifre: nei test usare id lunghi.
- Un cog nuovo che avvia un loop (watcher) lo fa in cog_load (super().cog_load() prima): così main.py non cambia. Picarto e eventi Twitch partono da cogs/utility/alert_piattaforme.py.
- Funzioni importate il cui nome inizia per «test» (testo_*) le raccoglie pytest: importarle con alias o nominarle altrimenti.
- discord.Streaming: .name = dettagli (titolo), .game = stato (gioco), .platform = nome del sito.
- Aggiungere una chiamata al DB (tetto totale degli avvisi) in un comando già testato con repo finti rompe quei test: patchare `cogs.utility.feed_alerts.tetto_e_pieno` nelle loro fixture.
- Tabelle nuove: dichiararle in core/data_registry.py (test_ogni_tabella_dello_schema_e_dichiarata); voice_roles (0647) mancava: aggiunta.
- Un autocomplete in un cog con comando_di_gruppo: funzione con @autocomplete_protetto(Livello.ADMIN) sopra il comando e @app_commands.autocomplete(param=funzione).
- Il catalogo vede i codici SOLO con il trattino (RUO-021) in codice o test: `RUO_021` nel nome non basta, `RUO-018..021` non è un intervallo. Ogni test ha un commento `# RUO-xxx`.
- Peso dei gruppi: /admin-ruoli era a 8.162: le funzioni nuove dei menu stanno in /admin-menu-ruoli (gruppo nuovo = command_groups + command_policy + generate_command_list + comandi.json nomi e descrizioni). test_command_groups.py ha 2 test già rotti su main (elenco gruppi vecchio).
- comandi.json: sezioni `nomi` (nome comando -> inglese, un nome per tutti) e `descrizioni`; mai riscrivere un nome già presente (es. «svuota» = clear). Script: scratchpad/en_agg.py.
- Tag: opzioni in colonne di custom_commands (0557), risposte con peso in custom_command_risposte; chi usa un tag passa da _rifiuto (sync) e _rifiuto_gruppo (async). Cancellazioni future via scheduler (AZIONE_CANCELLA_RISPOSTA).
- Un gruppo nuovo: _DEFINIZIONI in core/command_groups.py + AUDIENCE in tests/support/command_policy.py + nome in scripts/generate_command_list.py + descrizione in locales/en-US/comandi.json.
- Testi: locales/{it,en-US}/testi.json (indent 2, ordine libero) e comandi.json (indent 1; i nomi di parametri NON vanno in «nomi»). Aggiunta senza riscrivere: scratchpad/uti19_agg.py. 
- Scheduler: i messaggi programmati e i promemoria stanno nel payload di scheduled_actions (nessuna tabella). Handler che non rilancia = niente doppioni; per le serie metti in coda il prossimo giro PRIMA di inviare. get_pending_action non dà execute_at (usa payload["quando"]).
- Impostazioni di moduli senza passare da config_history/config_impostazioni (non miei): tabella propria + repo con copia in memoria che si riempie solo dopo lettura riuscita (messaggi_auto, suggestions_config).
- LayoutView: BaseLayoutView in core/ui_base.py (e nella lista del test ui_base_wiring). V2: 40 componenti, 4.000 caratteri, niente content/embed.
- DynamicItem per bottoni persistenti (cronometro, tag degli embed, ricordalo anche a me, chi l'ha scritto): template + add_dynamic_items in setup/cog_load.
- clean_db + Repo(pool_provider=lambda: clean_db) per i test su DB; i test di cog che toccano un repo nuovo devono patcharlo (suggestions_limiti, embed_builder).

- Migrazione già applicata in un DB di test: mai riscriverla, usare il numero dopo.
- Script dei tag: core/tag_script_logic (async). {nome} sconosciuto resta testo (poi render_template). args/username sono dati: escape_mentions. Output tag 4000, ogni valore 2000. Mai eval/exec: c'è un test che lo vieta nel sorgente.
- Gruppo /admin-automazioni: sottogruppi script/inneschi/slash in SOTTOGRUPPI. Nuovo repo con metodo mai chiamato = fallisce test_repository_callers: non aggiungere metodi non usati.
- Comandi del server (B28): l'albero mirror del DB (_monta, solo i nostri nomi), sync = tree.sync(guild) con impronta delle definizioni, non dell'albero. Rows asyncpg jsonb tornano come stringa.


## Aperto
- r3utl: da provare dal vivo che uscire dal canale interrompa il suono (FUN-078). Il pannello web non ha ancora gli strumenti del marchio né lo stato dell'azzeramento (D16). Il registro errori del marchio è in memoria (si svuota al riavvio). `reset anche_i_dati` non azzera la configurazione subito (D116).
- #123 resta solo RUO-005 (dimensioni libere dell'immagine). r2ben: le immagini del menu sono allegate (`menu.png`) e si rimandano a ogni modifica; il gruppo di menu usa `member.edit(roles=)` (un solo colpo); il ruolo personale non ha un tetto per chi lascia il server se il bot era spento (resta il ruolo: ripulire a mano).
- UTL-184 `/mod-ban massa invito codice:` non fatto: è in cogs/moderation (r19mod). Servono: completamento sul codice + ban di massa dei membri entrati con quel codice (invite_joins.code).
- #129 non fatto: ALR-049 (Linked Roles: OAuth e pagine web, D92). ALR-035: alternativa D90 (frequenze da .env). #127 non fatto: VOC-020 (D91).
- Feed noti (FEED_NOTI in alert_piattaforme_logic) e Bluesky: indirizzi da provare su Discord. YouTube live da link dipende da YOUTUBE_API_KEY.
- Alternative D18 non fatte: UTL-111 (comando programmato), azioni in borsa in /web prezzo (nessuna fonte gratis).
