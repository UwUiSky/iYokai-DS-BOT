# Memoria di dev-utilita

## Aggiornata
17/11/2026 · r1ben (feat/r1ben, DB iyokai_w123) · #123: 65 voci nuove o provate; restano RUO-005, 012, 045, 046, 047, 053, 069, 083. Migrazioni usate 0640-0650 (libere 0651-0659).

## In corso
- Giro r1ben chiuso (non unito, niente push). Smoke da fare dell'orchestratore. Prossimo: le 8 voci rimaste (vedi Aperto) e il nuovo parere del revisore.

## Fatto
- r1ben #123: benvenuto ({math:}, {se_nuovo:}/{se_ruolo:}, immagine opacità/testo/ordine/allineamento, embed salvato per benvenuto/DM/addio, reazione al primo messaggio, avviso topic), ruoli (ricordati ammessi/esclusi 0640, vocali 0647), menu (limiti 0641, azzera 0642, immagine extra 0643, embed 0644, primo msg 0645, topic 0646, esterno 0648, scadenza 0649, contatori 0650), gruppo /admin-menu-ruoli (D75). Codici provati: tests/test_catalogo_ruoli_gia_fatti.py + test_role_menu_limiti_ruoli.py.
- r24util B25-B28: script dei tag, dati e errori (0562), inneschi (0563), comandi del server (0564, 0565); dettagli in git log e nel codice.
- Giri r19-r23 (B1-B24): /utility, /web, messaggi auto, embed, programmati, compleanni, suggerimenti, starboard, giveaway, inviti, conteggio, citazioni, emoji, regex, tag, sondaggi, eventi (0540-0561). Giri r4-r11: autorole, tag, autoresponder, greetings, role menu, moduli (git log).
- r24util correzioni: monta_per_avvio (slash_server.py) chiamato da main.setup_hook prima di ogni sync; owner riservato; _monta salta le collisioni; core/tag_eliminazione.pulisci_tag_eliminato (unica pulizia); 0565 tag_dati.autore + 200 chiavi per autore (staff no); asyncio.timeout in esegui; togli_per_ruolo; blacklist e pausa 3 s negli inneschi; regex a pezzi.

## Cose imparate
- Il catalogo vede i codici SOLO con il trattino (RUO-021) in codice o test: `RUO_021` nel nome non basta, `RUO-018..021` non è un intervallo. Ogni test ha un commento `# RUO-xxx`.
- Peso dei gruppi: /admin-ruoli era a 8.162: le funzioni nuove dei menu stanno in /admin-menu-ruoli (gruppo nuovo = command_groups + command_policy + generate_command_list + comandi.json nomi e descrizioni). test_command_groups.py ha 2 test già rotti su main (elenco gruppi vecchio).
- Funzioni importate che iniziano per «test» le raccoglie pytest: non chiamarle testo_*.
- comandi.json: sezioni `nomi` (nome comando -> inglese, un nome per tutti) e `descrizioni`; mai riscrivere un nome già presente (es. «svuota» = clear). Script: scratchpad/en_agg.py.
- Generare COMMAND_LIST serve variabili finte per token e ID (da .env.example, mai quelle vere).
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
- #123 restano: RUO-005 (dimensioni libere), 012 (immagini a caso), 045/046 (ruolo personale e colore: /utility è pieno, serve un sotto-gruppo), 047 (creazione guidata), 053 (immagine nel menu), 069 (menu collegati), 083 (più ruoli per opzione).
- Menu: il messaggio esterno non ha contatori né bottoni; cambio tipo vale solo per menu del bot. Reazione negata da un limite: nessun avviso (le reazioni non hanno risposta).
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
- B25-B28: {dati:set} ha anche il tetto per autore (200, righe vecchie senza autore non contano). Ora degli script e dei cron: Europe/Rome fisso.
- B28: la sync d'avvio ora monta prima i comandi del server (da provare su Discord nel server MAIN dopo un riavvio).
- B27: il bottone con innesco risponde in canale a tutti; l'innesco a tempo parla come il bot (`{user}` = bot). Reazione: nessun filtro sul messaggio, solo canale.
