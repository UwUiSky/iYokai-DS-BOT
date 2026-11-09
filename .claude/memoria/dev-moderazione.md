# Memoria dev-moderazione
## Aggiornata
2026-11-08, giro r18mod (ramo feat/r18mod, wt /home/claude/wt/r18mod, DB iyokai_w18mod, migr. 0532 usata per D68; 0511 libera per M9 prove). Smoke da fare.
## In corso
r18mod previsione 3 voci: D68, M6 (parziale), M8: fatte. Prossimo giro, in ordine: M6 resto (MOD-066 conferma con 2 tasti, MOD-067 risposte compatte/cancella-dopo, opzioni nuove in core/moderation_opzioni.py), M9 (MOD-107 /mod-ban cerca, 108 /mod-casi membri, 110 /mod-casi invito, 038 prove con migr. 0511), MOD-102 dehoist/simboli (D66, spento: sta in cogs/automod, aspetta il merge).
Comando: DATABASE_URL=postgresql://postgres:testpass@127.0.0.1:5432/iyokai_w18mod in ogni comando (scratchpad/envw18.sh). Testi: scratchpad/addt18.py file.json (chiave -> [it, en]).
## Fatto
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
- MOD-066, MOD-067, MOD-102 e M9 da fare. Custom_id dei tasti della scheda non sono persistenti (vista a tempo, 10 min): scelta mia.
- M5: _prepara_massa dà (ids, motivo); nel DM il nome locale del messaggio inviato è dm_inviato (il parametro dm del comando è un bool)
- M5: durata nel motivo pronto: fatta in D68
