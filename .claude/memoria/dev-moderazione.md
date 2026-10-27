# Memoria dev-moderazione
## Aggiornata
2026-10-27, ramo feat/r10sec (agente r10sec), worktree /home/claude/wt/r10sec. Migrazioni r10: nessuna usata (0290-0299 libere): le tabelle verify nascono in verify_repo.run_migrations. Log in scratchpad/r10sec_*.
## In corso
Giro r10 (voci [~] di §4 e §7, #59 #60 #117 #118): fatte VER-017/019/020/030/031, SIC-036, SIC-039, PERF-3. Prossimo: batch di test finale, smoke --base main, rapporto.
Resta fuori: SIC-045 (serve /privacy di dev-utilita + scelta owner), SIC-016, SIC-021, AMD-067 (profili automod per i livelli).
## Fatto
- Giri G1-G7, R5-R9 (vedi git log e REGISTRO_RISOLTE): tempban, appelli, verify, lockdown, phishing, captcha, anti-raid, massa, filtri automod, iYokai Mod, catalogo log, ripiego anti-nuke, warn manuali, opzioni mod, lock a tempo, punizione trappola
- R10-1 VER-017/019/020/030/031 (063e20b): /security verify invia, tempi azione_eta e sospendi_ore, statistiche complete (tabella verify_eventi), tentativi csv
- R10-2 SIC-036 /antiraid livello (core/security_logic.config_con_livello), SIC-039 canali trappola extra, PERF-3 retention dell'indice messaggi
- SPEC §4 e §7: tutti i [~] sono [x] (le note del 04/10 erano superate)
## Cose imparate
- D15: Mod non ha listener; azioni di sicurezza via bot_roles; e_un_nostro_bot per "e' il bot"
- discord.RateLimited NON e' HTTPException: va preso a parte
- Tabelle sicurezza e verify in run_migrations dei repo; config anti-raid/anti-nuke in JSON: campi nuovi senza migrazione (_to_json/_from_json)
- Colonne nuove su tabelle dei repo: migrazione numerata (gira dopo i repo)
- Smoke e suite oltre 2 min: run_in_background su log in scratchpad; con 10 agenti anche 3 file di test durano minuti
- Il bot non puo' scrivere a un bannato/espulso: DM prima, cancellato se l'azione fallisce
- Stato su DB PRIMA dell'azione irreversibile; job di scadenza protetti con controllo nell'handler
- Opzione facoltativa nuova: va DOPO le obbligatorie (test che chiamano callback per posizione)
- test_riferimenti_comandi legge anche docstring e messaggi: citare il percorso intero
- Nuove chiavi guild settings: SETTINGS_SCHEMA (+ tipo in VALIDATORI) + tests/test_config_import_validation.py; chi-puo'-cosa anche CHIAVI_SOLO_PROPRIETARIO
- Comando nuovo: ATTESI in test_f7_moderazione_gruppi e locales/comandi.en.json (nome e descrizione)
- Un repo senza chiamante in produzione e' nel cricchetto di test_repository_callers: meglio cancellare il metodo (e la pulizia passa dal registro dati con Scadenza)
- Livello di allerta anti-raid: stringe soltanto; i segnali di gruppo (nomi simili, account vicini) scattano con test che usano membri tutti uguali
- Str.replace sostituisce TUTTE le occorrenze; con piu' decorator uguali (describe) cercare l'indice dopo il nome del comando
## Aperto
- SIC-045 opt-out di rete (privacy), AMD-067, SIC-016/021
- data_registry (dev-core): scheduled_actions con action_type channel_unlock usa user_id = ID del canale
- #119 LOG-029; #113 log via webhook; MOD-065; OAuth rientro oltre 7 giorni
