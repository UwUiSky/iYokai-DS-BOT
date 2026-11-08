# Memoria dev-moderazione
## Aggiornata
2026-11-08, giro r17automod (ramo feat/r17automod, worktree /home/claude/wt/r17automod, DB iyokai_w17am, migrazioni da 0509 e da 0531 mie). Smoke da fare. Prima: r15automod (A1-A8), r16verifica (0530), r15vpn.
## In corso
Previsione giro r17: D67 fatto, poi A9, poi stop con rapporto. Prossimo: A10 calore e gruppi (AMD-068/069/072: campo Regola.calore gia' nel modello; valore in memoria per server+utente, calo lineare letto al bisogno), poi A11 (migr. 0509, tabella automod_pulizie, pulizia 073/074, AMD-008 soglie per canale). main.py deve usare core.automod_eventi.chiede_intent_presenze() per intents.presences (non mio).
Comando: DATABASE_URL=postgresql://postgres:testpass@127.0.0.1:5432/iyokai_w17am in ogni comando (mai iyokai_test).
## Fatto
- r17 D67 account rubato (#153): core/account_rubato_logic.py (registro invii: malevola o stessa firma in 3 canali/120 s), core/account_rubato.py (avviso unico aggiornato, timeout 1h/24h, cancella invii contati, DM, verify_blocchi.registra_limitazione), cogs/automod/account_rubato.py, opzione account_rubato_attivo (accesa) in /admin-automod immagini; il filtro immagini gli passa le malevole. test_automod_account_rubato(_logic). Smoke da fare
- r15 A7 liste con nome (core/automod_liste_service.py, repo, pannello core/automod_liste_pannello.py, /admin-automod liste), liste di sistema in data/automod/, innesco personale (core/automod_innesco_logic.py), modelli (core/automod_modelli.py), finestra Innesco. A8 migr. 0503 + core/automod_decisioni.py (decide lo staff, bottoni persistenti). test_automod_liste/_innesco_logic/_decisioni. Smoke da fare
- r15 A6 pannello regole (core/automod_regole_pannello.py + core/automod_pannello_logic.py), comandi /admin-automod regole, gruppo, immagini; 100 testi amregole_*; test_automod_pannello_logic/_regole_pannello/_regole_comandi. Smoke da fare
- r15 A4 core/automod_azioni.py (20 azioni, ordine D63, scudo protetti, 403=sospesa 10 min, fine a tempo via scheduler, webhook), A5 migr. 0502, contatori (core/automod_contatori.py), /admin-automod riepilogo e azzera (cogs/automod/regole.py), test_automod_azioni/_contatori. Smoke da fare
- r15 A3 core/automod_contesto.py, _controlla con regola attiva/condizioni/esenzioni per regola/bot solo se la regola li accetta; service fail-open se la tabella non si legge; test_automod_regole_filtri. Smoke da fare
- r15 A1 core/automod_regole_logic.py (regole, condizioni_ok, azioni, tetti, re2), A2 migr. 0500/0501, automod_regole_repo, automod_regole_service (punto unico, cache), data_registry; test_automod_regole_logic/_repo. Smoke da fare
- R16 D67 verifica: soglia 3 approvazioni (verify_vpn_logic.storico_basta, founder_id/admin_id in verify_vpn_storico), IP cifrati (core/verify_ip.py, repo verify_ip_repo, tabella verify_ip, VERIFY_IP_ENCRYPTION_KEY, scadenze nei listener di cogs/security/verify.py, solo owner), invito al ticket per captcha/bottone/reazione (run_checks_and_finalize con_invito); test_verify_vpn_soglia/_ip/_blocchi_discord. Smoke da fare
- R15 D64/D65 (VPN/proxy, ticket, storico): core/verify_vpn{,_logic,_dati,_esterno,_staff}.py, verify_blocchi.py, repo verify_vpn/verify_blocchi (0507/0508), scripts/aggiorna_vpn.py, data/vpn/, docs/verifica_vpn.md, /owner system storico-vpn, test_verify_vpn_*. Smoke da fare. Ramo feat/r15vpn
- R14 D53 (paese nella verifica web): core/geoip_paesi, verify_paese_logic, verify_paese_staff (DynamicItem), repo verify_paese (0490), 4 chiavi in SETTINGS_SCHEMA/SCHEDE verify, tests/test_verify_paese.py. Smoke da fare. Ramo feat/r14paese
- Giri G1-G7, R5-R10 (git log e REGISTRO_RISOLTE): tempban, appelli, verify, lockdown, phishing, captcha, anti-raid, massa, filtri automod, iYokai Mod, catalogo log, ripiego anti-nuke, warn manuali, opzioni mod, lock a tempo, punizione trappola, mute a tempo, casi esterni, VER-017/019/020/030/031, SIC-036/039, AMD-013/014/026/027/062/065/070
- R11 D35: core/odio_*.py (giudizio, libreria, richiami, opzioni, moderazione), core/automod_odio_nativo_logic.py (regex nativa), core/automod_odio_azioni.py (Discord), repo odio_libreria_repo (0390), comandi /automod odio blocco|richiami|libreria, data/automod_parole_sospette.txt, docs/parole_bandite.md, test tests/test_automod_odio_d35.py
## Cose imparate
- Testi: locales/it e en-US testi.json, riga in coda (no json.dump); un test che mette un'opzione nuova letta da db va patchato (db non connesso nei test di cog)
- Scadenze IP (verify_ip): il ban vince sempre (on_member_remove arriva anche dopo il ban); kick riconosciuto dal registro audit, senza permesso = uscita volontaria; log IP: mai exc_info, solo type(errore)
- data_registry: test_riferimenti_comandi legge anche le note: mai «/privacy», scrivere «/utility privacy cancella»
- Sostituendo un blocco di codice con slice (index..index) controlla cosa c'e' in mezzo: ho cancellato riepilogo/azzera (lo ha trovato test_repository_callers)
- Regole AutoMod: azioni vecchie (delete,warn,mute,kick,ban) -> azioni_dai_nomi_vecchi (ordine di prima); actions-set/mute-duration scrivono anche via servizio (doppia scrittura fino ad A4)
- Verifica web: i segnali delle intestazioni si ignorano se il socket e' privato o proxy fidato (reverse proxy non dichiarato bloccherebbe tutti); IP non globali mai bloccati (is_global)
- Locales comandi.json: mai riscrivere con json.dump (chiavi ordinate/escape): inserire la riga di testo
- CSP del pannello: script solo su /verifica/ (CSP_VERIFICA); resto default-src none
- Chiavi guild nuove con tipo nuovo: CONTROLLI_PER_TIPO in config_history; i campi in SCHEDE di core/config_impostazioni.py (pannello)
- D15: Mod non ha listener; azioni di sicurezza via bot_roles; e_un_nostro_bot per "e' il bot"
- discord.RateLimited NON e' HTTPException: va preso a parte
- Tabelle sicurezza e verify in run_migrations dei repo; config anti-raid/anti-nuke in JSON: campi nuovi senza migrazione
- Colonne nuove su tabelle dei repo: migrazione numerata (gira dopo i repo). Tabella nuova: anche in core/data_registry.py
- Smoke e suite oltre 2 min: run_in_background su log in scratchpad (grep sul log, mai pipe con tail nel foreground)
- Il bot non puo' scrivere a un bannato/espulso: DM prima, cancellato se l'azione fallisce
- Stato su DB PRIMA dell'azione irreversibile; job di scadenza protetti con controllo nell'handler
- Opzione facoltativa nuova: va DOPO le obbligatorie (test che chiamano callback per posizione)
- test_riferimenti_comandi legge anche docstring e messaggi: citare il percorso intero
- Nuove chiavi guild settings: SETTINGS_SCHEMA + CONTROLLI_PER_TIPO + tests/test_config_import_validation.py; chi-puo'-cosa anche CHIAVI_SOLO_PROPRIETARIO
- Comando nuovo: ATTESI in test_f7_moderazione_gruppi e locales/comandi.en.json (nome e descrizione)
- Ogni modulo in cogs/ ha setup(): codice senza cog va in core/ (test_command_tree_invariants lo controlla)
- Tabelle senza chiamante in produzione = cricchetto di test_repository_callers: meglio cancellare il metodo
- normalizza() del filtro legge "!" come i: per le chiavi di cache usare parole+casefold, non normalizza
- Test del cog automod: db finto passato come `archivio` alle funzioni (mai db._pool); libreria_odio va finta (AsyncMock) senza pool
- Str.replace sostituisce TUTTE le occorrenze; con piu' decorator uguali cercare l'indice dopo il nome del comando
## Aperto
- D67: verify_blocchi ha UNA riga per persona (PK user_id): con account limitato in piu' server il ticket si apre solo nell'ultimo; per tutti serve cambiare PK (migr. 0531) e cogs/tickets/modmail.py (non mio, in revisione r16ticket)
- Codice con View/Modal senza cog va in core/ (ogni file in cogs/ vuole setup())
- AMD-018 (stato/attivita) non fatto: serve intent Presenze, decide l'owner
- decide_staff (A8, 0503) non ancora: l'azione e' nel JSON ma il motore la ignora
- Test con _FakeMessage senza webhook_id: nel cog usare sempre getattr per gli attributi nuovi
- D67: chiave VERIFY_IP_ENCRYPTION_KEY da mettere nel .env di produzione (senza, nessun IP salvato); i listener di scadenza IP girano anche a modulo Verify spento
- D64: Tor/reti da aggiornare a mano con scripts/aggiorna_vpn.py (nessun job); licenza elenco Tor da confermare
- MOD-065 (motivo facoltativo): cambia la firma di tutti i comandi
- #119 LOG-029; #113 log via webhook; OAuth rientro oltre 7 giorni; alt_detection (#92)
- Eccezioni allow_list anti-invito: tetto 25 voci = 8 inviti
- SIC-045, AMD-067, SIC-016/021
- data_registry (dev-core): scheduled_actions con channel_unlock usa user_id = ID del canale
- D35: pagina /proprietario per la libreria (dev-web); le candidate valgono solo nei server che le hanno segnalate
