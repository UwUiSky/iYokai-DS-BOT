# Memoria di revisore-capo

## Aggiornata
09/11/2026 · `feat/r24fun` (telefono B12, #131): merge main, fix minori/allegati/squillo/segnala/cooldown/consenso; APPROVATO. Smoke da fare: telefono, intent_usage, 0579-0580, data_registry, tree_invariants, i18n.
09/11/2026 · `feat/r21util` (D69 B16–B21, UTL-184, #128): merge main (e97e2d0), 4 fix (306f4a4, ban massa conferma, CSV/gruppo, 26a1496 quote->citazioni+0558); 4 basse aperte. APPROVATO. Smoke da fare: citazioni, risposte_regex_globali, autoresponder, custom_commands, tag_gestione, strumenti_server, moderation_canali_m7, massa, migrazione_percorsi_tag_quote, 0555–0558, tree_invariants, riferimenti, data_registry, i18n.
09/11/2026 · `feat/r18mod` (D68, M6, M8, #115): merge main (8fd3bf8), 5 fix (8c754fc, 39652fc, poi defer segnalazioni e tetto 5/10min in ac5e503); 4 basse aperte. APPROVATO. Smoke da fare: moderation_motivi_severita, moderation_dm_m6, moderation_scheda_m8, report_limiti, remaining_moderation_smoke, automod_azioni, 0532, tree_invariants, i18n.
08/11/2026 · `feat/r18automod` (A10 calore/soglia canale/finestra, A11 pulizia 0509, #116): main già unito, 5 fix (b06e3df, bf9a609, fcd1452, 8fd7903, 78b289c); 5 basse aperte. APPROVATO. Smoke da fare: automod_pulizia*, automod_calore*, automod_soglia_canale, automod_innesco_logic, automod_regole_pannello, automod_eventi*, 0509, tree_invariants, data_registry, i18n.
09/11/2026 · `feat/r18ticket` (T4 #120, thread #156, 0526/0534): main già unito, 9 fix (7322d8b, 2fe4aa8, e577521, b2fc810, 4a7367b, 9875ec1, e38f54f, 9732b72, bb5bbd3) + SPEC/COMMAND_LIST; 5 basse aperte. APPROVATO. Smoke da fare: ticket*, modmail*, 0526, 0534, tree_invariants, i18n, data_registry.
08/11/2026 · `feat/r17mod` (M4, M5, M7, #115, D66): merge main (1a8447d), 6 fix (68052b8, 5e63065, 82bda8f, 3c67401, 0051d75, f45b4b2); 5 basse aperte. APPROVATO. Smoke da fare: moderation_vocale_m4, opzioni_comandi_m5, canali_m7, massa, 0512–0514, tree_invariants, f7_moderazione_gruppi, data_registry, i18n, riferimenti.
02/11/2026 · `feat/r16mod` (M1–M3, #115, D66): merge main (2d560e9), 6 fix (06021a6, 9e7dda7, d069d00, 6ac5246, 467d512, 861c0aa); 6 basse aperte. APPROVATO. Smoke da fare: clear_filtri, casi_m3, automod_azioni, escalation_*, staff_rischio, 0510, tree_invariants, f7_moderazione_gruppi, i18n, riferimenti.
08/11/2026 · `feat/r16verifica` (D67, #155): merge main (d1aebf3), 2 fix (0ddf19f, d819810), comportamento esatto delle scadenze IP scritto sotto D67; 4 basse aperte. APPROVATO. Smoke da fare: 0530, test_verify_ip, verify_vpn_soglia, verify_blocchi_discord, retention, forget, data_registry, panel_proprietario.
02/11/2026 · `feat/r15vpn` (D64, D65, 0507, 0508, #155): merge main (0b07b2f), 6 fix (e5e4774, 14568f1, a895a2c, 9ff3e96, 38ec7c5, 72e1fed); 6 basse/medie aperte nel quaderno. APPROVATO. Smoke da fare: 0507, 0508, verify_vpn*, panel_bridge, panel_proprietario, modmail, data_registry, aggiorna_vpn.
Giri r6–r14lingue: tutti APPROVATI dopo i fix (commit e basse nel quaderno). `f7-quadro` APPROVATO, manca l'unione.
08/11/2026 · `feat/r16ticket` (D66, #120, 0520–0525): merge main (fdb43c8), 5 fix (28a555d, b0d7f16, 382a541, 4de6d9e, 82ae567); 8 basse aperte. APPROVATO. Smoke da fare: ticket*, modmail*, 0520–0525, i18n, tree_invariants.
Giri r6–r14 e r15vpn/r15immagini precedenti: tutti APPROVATI dopo i fix; basse aperte nel quaderno.
08/11/2026 · `feat/r17automod` (D67 account rubato #153, A9 eventi #116, 0531): merge main (01a2b07), 6 fix (f98a408, 0586e74, c7743cf, cb3a839, ebe5050, 202e3f7) + voci chieste (7438842 minuti timeout, 7a8647b blocco per server e ticket); 4 basse aperte. APPROVATO. Smoke da fare: test_automod_account_rubato*, automod_eventi*, automod_regole_comandi, immagini_cog, verify_vpn_flusso, verify_blocchi_discord, modmail*, moderation_casi*, 0531, main_bot, intent_usage, config_import_validation, i18n.
08/11/2026 · `feat/r16verifica` (D67, #155): 2 fix (0ddf19f, d819810). APPROVATO. · `feat/r16ticket` (D66, #120): 5 fix. APPROVATO.
02/11/2026 · `feat/r16mod` (#115): 6 fix. · `feat/r15automod` (#116): 10 fix. · `feat/r15immagini` (#153): 10 fix. · `feat/r15vpn` (#155): 6 fix. Tutti APPROVATI.
Giri r6–r14: tutti APPROVATI dopo i fix (commit e basse nel quaderno).

## In corso
- Niente. Al prossimo giro: righe aperte del quaderno per il ramo riconsegnato.

## Fatto
- Letti per intero: giro-mod, r3–r13 (commit nel quaderno).

## Cose imparate
- Chiave di impostazione nuova: SETTINGS_SCHEMA + SCHEDE (config_impostazioni) + `imposta_impostazione`; senza schema l'export del server non si re-importa. Test del dizionario SETTINGS_VALIDE in test_config_import_validation.
- Viste che chiamano `comando.callback(...)`: i controlli del gruppo (Livello) saltano; ricontrollare il livello di OGNI azione alla conferma e non scrivere «fatto» dopo la callback (può aver rifiutato). Modali con lavoro lento: defer prima.
- Ticket a thread: `guild.get_channel` non vede i thread (usare `get_channel_or_thread`), la cancellazione arriva da `on_raw_thread_delete`; i finti con `get_channel` vanno allineati. Giri con tetto: cursore per id. Riserve di canali: ogni uscita dalla tabella senza uso = eliminare il canale.
- Ticket: ogni percorso che rimette permessi ai ruoli staff (presa, rilascio, sposta, riapri) deve passare da `ruoli_con_accesso` (solo admin); i permessi personali (reperibili, titolare) vanno guardati a parte. Completamenti: stesso controllo del comando, non un Livello a caso.
- Stati decisi dallo staff (attesa/rifiuto) si leggono PRIMA di ogni uscita anticipata (dato mancante = porta aperta). Soglie a conteggio: salvare poi contare. Il ramo senza issue: `Refs D<n>`, mai un numero a caso.
- Riordino a regex: tabelle di percorsi SENZA `/` (es. COMANDI_VICINI) e sotto-comandi già vecchi sfuggono; confronto albero base/HEAD (livello, permesso, autocomplete) con uno script di dump; scansione `/percorso` contro l'albero vero.
- Riordino dei comandi: i test cercano i percorsi in molti modi (`get_command` a catena, `comando_nel_gruppo(g, f"…")`, `percorsi_del_gruppo`, insiemi ATTESI). Scansione con la tabella della migrazione su tutti i test, poi le corse. Controlli scritti nel corpo (`puo_usare`) sfuggono ai test che leggono solo `.checks`.
- Corse lunghe: `-v --tb=no -rf` (righe man mano), mai `timeout` esterno (niente riepilogo); due metà su due database propri; `pkill -f` col proprio comando: usare `[.]`.
- Lingue: `testo_per` senza `pubblica=True` = lingua personale; embed costruiti a pezzi li trova `tests/test_i18n_pubblica.py`. `comandi.en.json`: "nomi" per SEGMENTO, "descrizioni" per percorso; modificarlo a testo (json.dumps cambia il rientro).
- Controllare il contenuto di ogni commit, non il messaggio; testi che promettono una funzione vanno confrontati col codice; voci `[x]` col catalogo e col test citato (D18).
- Ambiente: `source` dello script env in ogni bash, mai riavviare postgres, database proprio per ramo. Regola owner: niente smoke né suite, «smoke da fare» nel rapporto. Commit senza righe di attribuzione (CLAUDE.md del ramo).
- Database di test condiviso con altri agenti = fallimenti a caso (tabelle di altri rami, righe sparite): rifare la corsa su un database proprio creato e poi tolto.
- Elenchi scaricati: reindirizzamenti https→http (urllib li segue) e reti enormi (0.0.0.0/0) da scartare. Righe aggiunte a messaggi pubblici: `testo_guild`.
- Diff di `.gitignore` e file di configurazione: leggerli sempre (una riga fusa coi commenti smette di ignorare `.env`); test con `git check-ignore --no-index`.
- Merge di main: conflitti nei documenti e in `comandi.en.json`; `COMMAND_LIST*` con `scripts/generate_command_list.py` (errore finale innocuo; se cambia solo la data, scartare).
- Migrazioni per NOME: mai modificarle; numeri confrontati su tutti i rami (`git ls-tree`). Test di una migrazione: `read_text()` ed `execute`, due volte (rilancio).
- `db._…` usate da un cog = manca una funzione pubblica. `SETTING_X` in `SETTINGS_SCHEMA`; tabelle in `core/data_registry.py`; metodi senza chiamanti rompono `test_repository_callers.py`.
- Mutazioni: test scritto prima del fix e visto rosso; script con `str.replace` contato. Test appeso: `asyncio.wait_for`.
- Doppio clic: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`; segno sincrono prima del primo await. Compiti differiti: un cambio durante il lavoro in corso deve chiedere un altro giro.
- Validare tutto PRIMA del primo salvataggio. Task per chiave: uno solo, fermato in `cog_unload`. Giri con `LIMIT`: righe mai chiuse bloccano le altre.
- Finti: `member.roles` vivo; `fake_member` ha `Permissions.none()`; `Thread.permissions_for` = padre; `monkeypatch.setattr(asyncio, "sleep")` è globale.
- `AllowedMentions(roles=...)` ha `everyone=True`. Azioni automatiche: tetto = ciò che può fare il moderatore (D28, D29). Bot secondari (D15); App utente: `guild_id=None`.
- Sandbox: ogni attesa del figlio dentro il tempo vero; dopo che il servizio ha preso il lavoro, niente ripiego più debole; uscita >0 da interprete rotto ≠ malevola. Unità systemd: mai il gruppo del bot al servizio (il PNG torna nei log = canale di fuga).
- Cache in memoria caricata «una volta»: segno messo DOPO la lettura riuscita, con un Lock; insiemi per chiave con scadenza: togliere le scadute (chi non torna resta per sempre). Tabelle per canale: listener on_guild_channel_delete.
- Regex native Discord 10×260; jolly ripetuti = tempo esponenziale. Soglie a conteggio condivise (canale): dopo lo scatto serve quiete, non solo azzerare. Cicli che «segnano prima»: try per voce, o le altre perdono il giro. Campi ID scritti a mano: ogni voce validata (un nome non deve diventare «qualsiasi»).
- `purge` di discord.py: dopo il primo messaggio oltre 14 giorni passa a cancellare uno per uno TUTTO il resto; con `after` legge dal più vecchio: serve `oldest_first=False`. Scadenze automatiche dei casi: mai su sanzioni in corso (active = in corso per ban/tempban/timeout/mute).
- Motore azioni: 403 su chi Discord non lascia toccare (proprietario, ruolo ≥ bot) non è un permesso mancato: niente sospensione per server. Finti: posizione 0 = raggiungibile. «Applica» dello staff = il bot agisce per lui: permessi di ogni sanzione + gerarchia. Soglie: scatta solo chi consuma (UPDATE conta righe).
- Scadenze legate all'uscita del bot: usare `guild_presence.left_at` (punto unico, sincronizzato all'avvio), mai listener on_guild_join/remove che riscrivono `scade_il` (il rientro le allunga). `LEAST` in Postgres ignora i NULL.
- Ascoltatori in RAM per difese a raffica (spam): serratura per persona prima di avviso/timeout; una sintesi deve portare solo i messaggi nuovi. Code con `maxlen` fisso < soglia ammessa = regola muta. Funzioni «chiede_intent» vanno cercate in main.py.
- AI: `pulisci_dati_personali` verso servizi non AI; filtro «addestra» in `scegli_fornitori` (D55). File di esempio con segnaposto: il caricatore li scarta.

## Aperto
- Domande all'owner: SPEC 23.16, D18 limite ticket per utente, primo DM ModMail, D27, IPv4 = basso (NF-21), D29, SIC-045.
- r13: due sistemi premium (core/premium.py e livelli_funzione), da decidere (D16).
