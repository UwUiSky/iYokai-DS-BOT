# Memoria dev-moderazione
## Aggiornata
2026-11-09, giro r19mod (ramo feat/r19mod, wt /home/claude/wt/r19mod, DB iyokai_w19mod; migr. 0511 usata per le prove). Blocco Moderazione #115 chiuso a livello di codice. Smoke da fare.
## In corso
Nessun lavoro aperto sul blocco #115. Prossimo (se serve): scarico di PDF/TXT delle prove dal pannello (dev-web), poi i controlli (cacciatore-bug, revisore-capo) e lo smoke dopo il merge. Comando: DATABASE_URL=...iyokai_w19mod (scratchpad/envw19.sh); testi: scratchpad/addt19.py file.json (chiave -> [it, en]).
## Fatto
- r19 M6 resto, M9, MOD-102: core/moderation_conferma.py (conferma 2 tasti, risposte compatte/cancella-dopo, GIA_CONFERMATA per /mod-sanzioni applica), moderation_risposte.py; ricerca ban/membri/invito (cogs/moderation/ricerca.py, moderation_ricerca_logic.py); prove (0511, moderation_prove.py, prove.py); dehoist/simboli (automod_nomi_logic.py, parole_odio.py); test_moderation_risposte_m6, test_moderation_ricerca_m9, test_automod_nomi_pulizia
- r18 D68: core/moderation_motivi.py (PREIMPOSTATI 14 motivi, Proposta, modifica, semina alla prima lettura), migr. 0532 (+ moderation_motivi_semina), repo motivi, /mod-casi motivi aggiungi/modifica con severita/azione/durata, cogs/moderation/motivo_pronto.py (/mod-sanzioni applica: menu + durata + Conferma; kick/ban solo con livello MODBAN); test_moderation_motivi_severita
- r18 M6 (MOD-050, 059): core/moderation_dm.py unico punto del DM (comandi + core/automod_azioni.py warn/kick/ban/tempban), mod_anonimo, mod_dm_testo_<azione>, finestra ModuloTestoDm; test_moderation_dm_m6. NON fatti: MOD-066, MOD-067
- r18 M8: core/moderation_scheda.py, cogs/moderation/scheda.py (/mod-casi scheda, menu «Scheda moderazione» con 5 tasti, «Segnala messaggio», /utility mie-sanzioni, mod_utente_vede_casi), report.invia_segnalazione; test_moderation_scheda_m8
- r17 M4 voce, M5 opzioni e motivi pronti (0512), M7 canali/nick/entrati (0513, 0514); r17 A9 eventi e D67 account rubato; r15-r16 A1-A8 AutoMod, verifica VPN/IP, giri G1-G7 e R5-R14 (git log, REGISTRO_RISOLTE)
## Cose imparate
- Anti-giri-a-vuoto (A9): esegui_azioni segna in automod_eventi_logic.effetti ruolo/nome/uscita PRIMA di agire; casi con origine automod ignorati; thread creati dal bot ignorati (e_un_nostro_bot sull'autore)
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
- Migrazioni: girano in ordine di numero: un ALTER su una tabella creata da 0512 deve avere numero maggiore (0532, non 0511)
- Sostituire un blocco con slice: ancorare sul sottogruppo (SOTTOGRUPPO_MOTIVI), mai sul solo nome=«aggiungi» (ce ne sono due): ho cancellato 3 comandi e l'ha visto test_f7
- Un comando che esegue un altro comando (applica, tasti scheda) deve ricontrollare il livello: /mod-sanzioni e /mod-ban hanno livelli diversi (D2)
- Test che chiamano il callback di un cog: get_member deve conoscere sia il moderatore sia il bersaglio (side_effect per id), se no «su te stesso»
- Il DM delle sanzioni legge le opzioni dal db: i test dei cog senza db vanno patchati (core.moderation_dm.costruisci)
## Aperto
- Cose imparate r19: i moduli in cogs/ senza setup() rompono test_command_tree_invariants: il codice senza cog va in core/ (conferma e` core/moderation_conferma.py)
- re2 non ha re2.IGNORECASE: usare il prefisso (?i). Comando che deve continuare dopo una conferma: ritorna l'interazione del tasto e il comando sostituisce `interaction` (la prima e` gia` risposta)
- Mai lanciare pytest di altri file sullo stesso DB mentre ne gira uno in background: e anche modificare cog durante la run falsa i test dell'albero comandi
- Aperto: scarico PDF/TXT delle prove solo dal pannello (non fatto, dev-web); /mod-casi caso vedi non elenca le prove; le prove si leggono con /mod-casi caso prova numero senza file
- MOD-066, MOD-067, MOD-102 e M9 da fare. Custom_id dei tasti della scheda non sono persistenti (vista a tempo, 10 min): scelta mia.
- M5: _prepara_massa dà (ids, motivo); nel DM il nome locale del messaggio inviato è dm_inviato (il parametro dm del comando è un bool)
- M5: durata nel motivo pronto: fatta in D68
