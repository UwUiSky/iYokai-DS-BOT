# Memoria dev-moderazione
## Aggiornata
2026-11-01, giro r15automod (ramo feat/r15automod, worktree /home/claude/wt/r15automod, filone A di #116, D63). Migrazioni 0500-0503 mie. Smoke da fare.
2026-11-02, giro r16verifica (ramo feat/r16verifica, D67 parte verifica, migrazione 0530, #155). Smoke da fare. Prima: giro r15vpn (D64+D65, 0507/0508); 2026-10-28, giro r11 (agente r11odio, ramo feat/r11odio, worktree /home/claude/wt/r11odio). Migrazione 0390 usata (0391-0399 libere). Smoke da fare (regola owner: niente smoke).
## In corso
r17mod (ramo feat/r17mod, wt /home/claude/wt/r17mod, DB iyokai_w17mod, migr. 0511-0514, #115): previsione 3 blocchi (M4, M5, M7). M4 e M5 fatti. Prossimo: M7 (MOD-098, 099, 100, 101, 102, 007; migr. 0513; /mod-canali slowmode, nick, dehoist in admin-automod odio nomi, massa entrati). M6 NON mio. Testi: scratchpad/r17/addt.py (aggiunge righe senza json.dump).
A1-A8 fatti + merge di main (immagini): `/admin-automod immagini` usa core.immagini_opzioni; cogs/automod/immagini.py::_applica passa da esegui_azioni (regola di sistema "immagini_sospette", senza_scudo=True). Prossimo: A9 (eventi non-messaggio: 009 vocali, 010 thread a raffica, 017 nomi, 075 ruolo/ingresso/uscita/caso; AMD-018 solo dietro interruttore spento), A10 (calore/gruppi 067-069/072), A11 (migr. 0509, pulizia 073/074).
SEMPRE: DATABASE_URL=postgresql://postgres:testpass@127.0.0.1:5432/iyokai_wautomod esplicito (env non persiste fra comandi: scratchpad/envw.sh).
## Fatto
- r17 M5: core/moderation_motivi.py (+ migr. 0512, tabella moderation_motivi), _shared.risolvi_motivo/completa_motivo/forza nel DM, reason facoltativo in 14 comandi, dm/giorni_messaggi/cancella_messaggi, /mod-casi motivi, setting mod_motivo_obbligatorio; test_moderation_opzioni_comandi_m5. Smoke da fare
- r17 M4 voce: core/moderazione_vocale_logic.py, cogs/moderation/voce.py (/mod-canali vocale muta|sordina|scollega|sposta|sposta-tutti|dove, sorveglianza 24h), mute con vocale:/canale_vocale: (softban_mute), migr. 0514 + 5 metodi moderation_repo, data_registry; test_moderation_vocale_m4. Tolto is_case_hidden (senza chiamante). Smoke da fare
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
- M5: _prepara_massa ora dà (ids, motivo); nel DM il nome locale del messaggio inviato e' dm_inviato (il parametro dm del comando e' un bool)
- M5: durata nel motivo pronto non fatta (decidere)
- Cog nuovo in cogs/moderation: aggiungerlo a MODULI di tests/test_f7_moderazione_gruppi.py oltre ad ATTESI, e il testo en dei comandi in locales/en-US/comandi.json
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
