# Memoria dev-moderazione
## Aggiornata
2026-10-28, giro r11 (agente r11odio, ramo feat/r11odio, worktree /home/claude/wt/r11odio). Migrazione 0390 usata (0391-0399 libere). Smoke da fare (regola owner: niente smoke).
## In corso
r11 D35 (parole d'odio a livelli) FATTO e pubblicato: manca solo la pagina nel pannello /proprietario (dev-web; il comando /automod odio libreria basta, D39).
Prossimo giro: SIC-045 (serve /privacy di dev-utilita + scelta owner), SIC-016, SIC-021, AMD-067, MOD-065.
## Fatto
- Giri G1-G7, R5-R10 (git log e REGISTRO_RISOLTE): tempban, appelli, verify, lockdown, phishing, captcha, anti-raid, massa, filtri automod, iYokai Mod, catalogo log, ripiego anti-nuke, warn manuali, opzioni mod, lock a tempo, punizione trappola, mute a tempo, casi esterni, VER-017/019/020/030/031, SIC-036/039, AMD-013/014/026/027/062/065/070
- R11 D35: core/odio_*.py (giudizio, libreria, richiami, opzioni, moderazione), core/automod_odio_nativo_logic.py (regex nativa), core/automod_odio_azioni.py (Discord), repo odio_libreria_repo (0390), comandi /automod odio blocco|richiami|libreria, data/automod_parole_sospette.txt, docs/parole_bandite.md, test tests/test_automod_odio_d35.py
## Cose imparate
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
- MOD-065 (motivo facoltativo): cambia la firma di tutti i comandi
- #119 LOG-029; #113 log via webhook; OAuth rientro oltre 7 giorni; alt_detection (#92)
- Eccezioni allow_list anti-invito: tetto 25 voci = 8 inviti
- SIC-045, AMD-067, SIC-016/021
- data_registry (dev-core): scheduled_actions con channel_unlock usa user_id = ID del canale
- D35: pagina /proprietario per la libreria (dev-web); le candidate valgono solo nei server che le hanno segnalate
