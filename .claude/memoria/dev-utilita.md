# Memoria di dev-utilita

## Aggiornata
20/11/2026 · r2ben (feat/r2ben, DB iyokai_w123) · #123: RUO-012, 045, 046, 047, 053, 069, 083; #117: SIC-041. Migrazioni usate 0740-0742 (libere 0743-0749).

## In corso
- Giro r2ben chiuso (non unito, niente push). Smoke da fare dell'orchestratore. Prossimo: RUO-005; ALR-049 (con dev-web) e VOC-020; revisione di sicurezza del diff (ruolo personale, immagini, gruppo).

## Fatto
- r2ben #123/#117: core/ruoli_extra_logic, ruoli_guidata_logic, ruoli_immagini, phishing_azione_logic; repositories/ruoli_extra_repo; cogs/utility/ruoli_extra.py (admin-menu-ruoli: ruoli-extra, gruppo, immagine, colori, guidata, personale; utility: colore, ruolo-mio; admin-benvenuto: immagini); ganci in role_menus.py (_blocchi_per, _estendi, _applica atomico, immagine nel messaggio) e greetings.py (_immagine_a_caso). Decisione D98. Test: test_ruoli_extra_cog.py, test_ruoli_extra_logica.py, test_ruoli_guidata_logica.py, test_ruoli_immagini.py, test_phishing_azione_extra.py.
- r1alert #129/#127 (0690-0693, D90-D94) e r1sta #130 (0700-0702, D87): vedi git log (gruppo /admin-alert, contatori, schede statistiche).
- r1ben #123 (0640-0650), r24util B25-B28, giri r19-r23 e r4-r11: vedi git log.

## Cose imparate
- Un cog nuovo che avvia un loop (watcher) lo fa in cog_load (super().cog_load() prima): così main.py non cambia. Picarto e eventi Twitch partono da cogs/utility/alert_piattaforme.py.
- Un test che importa funzioni il cui nome inizia per «test» (testo_con_menzione) le fa raccogliere a pytest: importare con alias.
- discord.Streaming: .name = dettagli (titolo), .game = stato (gioco), .platform = nome del sito.
- Aggiungere una chiamata al DB (tetto totale degli avvisi) in un comando già testato con repo finti rompe quei test: patchare `cogs.utility.feed_alerts.tetto_e_pieno` nelle loro fixture.
- Tabelle nuove: dichiararle in core/data_registry.py (test_ogni_tabella_dello_schema_e_dichiarata); voice_roles (0647) mancava: aggiunta.
- Un autocomplete in un cog con comando_di_gruppo: funzione con @autocomplete_protetto(Livello.ADMIN) sopra il comando e @app_commands.autocomplete(param=funzione).
- Un secondo messaggio nel canale vocale (pannello) fa salire a 2 i send: i test di creazione contano 2.
- Il catalogo vede i codici SOLO con il trattino (RUO-021) in codice o test: `RUO_021` nel nome non basta, `RUO-018..021` non è un intervallo. Ogni test ha un commento `# RUO-xxx`.
- Peso dei gruppi: /admin-ruoli era a 8.162: le funzioni nuove dei menu stanno in /admin-menu-ruoli (gruppo nuovo = command_groups + command_policy + generate_command_list + comandi.json nomi e descrizioni). test_command_groups.py ha 2 test già rotti su main (elenco gruppi vecchio).
- Funzioni importate che iniziano per «test» le raccoglie pytest: non chiamarle testo_*.
- comandi.json: sezioni `nomi` (nome comando -> inglese, un nome per tutti) e `descrizioni`; mai riscrivere un nome già presente (es. «svuota» = clear). Script: scratchpad/en_agg.py.
- Menu del tasto destro nel tree: get_commands() li include; command_search li rompe (vedi Aperto). Un cog con ContextMenu: cog_load chiama super().cog_load() (CogConGruppi) e poi add_command.
- Tag: opzioni in colonne di custom_commands (0557), risposte con peso in custom_command_risposte; chi usa un tag passa da _rifiuto (sync) e _rifiuto_gruppo (async). Cancellazioni future via scheduler (AZIONE_CANCELLA_RISPOSTA).
- Un gruppo nuovo: _DEFINIZIONI in core/command_groups.py + AUDIENCE in tests/support/command_policy.py + nome in scripts/generate_command_list.py + descrizione in locales/en-US/comandi.json.
- Testi: locales/{it,en-US}/testi.json (indent 2, ordine libero) e comandi.json (indent 1; i nomi di parametri NON vanno in «nomi»). Aggiunta senza riscrivere: scratchpad/uti19_agg.py. Funzioni importate che iniziano per «test» le raccoglie pytest.
- Scheduler: i messaggi programmati e i promemoria stanno nel payload di scheduled_actions (nessuna tabella). Handler che non rilancia = niente doppioni; per le serie metti in coda il prossimo giro PRIMA di inviare. get_pending_action non dà execute_at (usa payload["quando"]).
- Impostazioni di moduli senza passare da config_history/config_impostazioni (non miei): tabella propria + repo con copia in memoria che si riempie solo dopo lettura riuscita (messaggi_auto, suggestions_config).
- LayoutView: BaseLayoutView in core/ui_base.py (e nella lista del test ui_base_wiring). V2: 40 componenti, 4.000 caratteri, niente content/embed.
- DynamicItem per bottoni persistenti (cronometro, tag degli embed, ricordalo anche a me, chi l'ha scritto): template + add_dynamic_items in setup/cog_load.
- Servizi esterni: chiave nell'intestazione (aiohttp diretto, host fisso), mai nell'URL: safe_get logga gli URL. User-Agent di safe_http è «lettore di feed».
- Log al server: core.channel_router (destinazione + invia_a, TIPO_SERVER/MODERAZIONE). Pubblicazione annunci: 10 all'ora per canale, un solo avviso.
- clean_db + Repo(pool_provider=lambda: clean_db) per i test su DB; i test di cog che toccano un repo nuovo devono patcharlo (suggestions_limiti, embed_builder).

- Migrazione già applicata in un DB di test: mai riscriverla, usare il numero dopo.
- Script dei tag: core/tag_script_logic (async). {nome} sconosciuto resta testo (poi render_template). args/username sono dati: escape_mentions. Output tag 4000, ogni valore 2000. Mai eval/exec: c'è un test che lo vieta nel sorgente.
- Gruppo /admin-automazioni: sottogruppi script/inneschi/slash in SOTTOGRUPPI. Nuovo repo con metodo mai chiamato = fallisce test_repository_callers: non aggiungere metodi non usati.
- Comandi del server (B28): l'albero mirror del DB (_monta, solo i nostri nomi), sync = tree.sync(guild) con impronta delle definizioni, non dell'albero. Rows asyncpg jsonb tornano come stringa.

- Un repo nuovo che lavora sulle tabelle di un repo esistente si costruisce con `RuoliExtraRepository(role_menu_repo.pool_provider)`: i test che patchano il repo vecchio portano con sé il pool (niente patch in più).
- Cambio di ruoli + togliere un altro in un colpo: `member.edit(roles=...)` (escludere `is_default()`), non add_roles+remove_roles.
- Funzioni importate che iniziano per «test» (testo_*) le raccoglie pytest: nominarle `coppie_in_testo`, ecc.
- Timestamp in SQL con parametri: `$3::timestamptz - make_interval(secs => $4::double precision)`.

## Aperto
- #130: test_data_registry fallisce su main per 4 tabelle non mie (guild_card_sfondi, leveling_reazioni, leveling_ruoli_classifica, voice_roles). Pannello web: serve la pagina pubblica delle statistiche e l'accesso per ruoli; le API restano dopo il pannello.
- #123 resta solo RUO-005 (dimensioni libere dell'immagine). r2ben: le immagini del menu sono allegate (`menu.png`) e si rimandano a ogni modifica; il gruppo di menu usa `member.edit(roles=)` (un solo colpo); il ruolo personale non ha un tetto per chi lascia il server se il bot era spento (resta il ruolo: ripulire a mano).
- Menu: il messaggio esterno non ha contatori né bottoni; cambio tipo vale solo per menu del bot. Reazione negata da un limite: nessun avviso (le reazioni non hanno risposta).
- Sondaggi nativi programmati: non compaiono in `/sondaggi gestisci` (solo bottoni) e non si annullano; il conteggio a N voti conta i voti (non i votanti) e perde quelli arrivati col bot spento.
- UTL-184 `/mod-ban massa invito codice:` non fatto: è in cogs/moderation (r19mod). Servono: completamento sul codice + ban di massa dei membri entrati con quel codice (invite_joins.code).
- Pannello web: editor benvenuto elenca i segnaposto (templates/editor_benvenuto.html) senza i 4 nuovi.
- test_command_policy::top_level_ha_un_pubblico fallisce su main per il menu «Apri ticket» (AUDIENCE, ticket): non mio.
- safe_http.USER_AGENT senza contatto: MET Norway e Wikimedia chiedono un contatto (core, non mio).
- #129 non fatto: ALR-049 (Linked Roles: OAuth e pagine web, D92). ALR-035: alternativa D90 (frequenze da .env). #127 non fatto: VOC-020 (D91).
- Feed noti (FEED_NOTI in alert_piattaforme_logic) e Bluesky: indirizzi da provare su Discord. YouTube live da link dipende da YOUTUBE_API_KEY.
- Alternative D18 non fatte: UTL-111 (comando programmato), azioni in borsa in /web prezzo (nessuna fonte gratis).
