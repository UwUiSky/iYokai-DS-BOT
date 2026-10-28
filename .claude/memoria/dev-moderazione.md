# Memoria dev-moderazione
## Aggiornata
2026-10-27, ramo feat/r10amod, worktree /home/claude/wt/r10amod. Migrazioni r10 (0280–0289): 0280, 0281 usate. Log in scratchpad.
2026-10-28, giro r10 (agente r10filtro, ramo feat/r10filtro, worktree /home/claude/wt/r10filtro): AMD-014 fatto, nessuna migrazione usata (0370-0379 libere). Smoke da fare (regola owner: niente smoke).
2026-10-21, ramo feat/r9mod, worktree /home/claude/wt/r9mod. Migrazioni r9: 0250 usata (0251–0259 libere). Log in scratchpad/r9mod.
## In corso
Giro r10 AutoMod: fatti AMD-013, 026, 027, 062, 065, 070 e SPEC 6.1–6.10, 6.15 a [x]. Prossimo: AMD-014 (normalizzazione, serve filtro parole lato bot), poi smoke --base main.
r10 (feat/r10mod): 0270 usata (0271-0279 libere). Fatto: mute a tempo/hardmute/rientro, caso registra, casi esterni, avvisi staff, SPEC 5.1-5.10 [x]. Prossimo: MOD-012/043/045, voce MOD-022..026, MOD-058/059, smoke --base main.
Giro r9 chiuso (5 voci su 5). Smoke --base main: 1079 verdi.
Prossimo giro, in ordine di valore: SIC-039 (piu' trappole), VER-017/019/020, SIC-036 livelli di allerta (con AMD-067), MOD-014/015 (mute a tempo, hardmute), MOD-046/047 (casi a mano e da azioni esterne), AMD-013/026/027/070.
## Fatto
- R10 AMD-014: core/automod_parole_logic.py + automod_parole_opzioni.py + cogs/automod/parole_odio.py (/automod odio ...), hook in automod._controlla (3 righe), evento automod_parole_vietate contato da escalation.py, dati in data/automod_parole_odio.txt
- Giri G1-G7, R5-R7 (vedi git log e REGISTRO_RISOLTE): tempban modi, appelli, verify, lockdown, phishing, captcha, anti-raid, massa, filtri automod, iYokai Mod, catalogo log
- R9-1 #59 ripiego kick/ban (be45348): AntiNukeConfig.ripiego_quarantena, opzione ripiego di /antinuke punish-action
- R9-2 M 1.10 (1988cd6): escalation.scala_per_warn_manuale, /security escalation enable warn_manuali, migr. 0250
- R9-3 MOD-010/017/057/068 (f97dbee): /mod opzioni imposta|dm|immuni, core/moderation_opzioni.py; mod_ruoli_immuni solo proprietario
- R9-4 MOD-090 + MOD-013 (7c8887f): /mod lock durata: (scheduler channel_unlock, user_id = ID canale), /mod caso attive
- R9-5 SIC-040: /security spamtrap punizione: (ban|kick|timeout|cancella|staff), StaffDecisionButton persistente
- Verificate in codice: M 1.1–1.9, 2.1–2.7, 3.x, 4.x gia' fatte; tolti i DA FARE #57/#58/#101
- R10 AutoMod: parole add modo (core/automod_native_logic.py), invites permetti/togli/propri + allow_list a tre vie (0280), timeout che cresce (0281)
2026-10-27, ramo feat/r10sec (agente r10sec), worktree /home/claude/wt/r10sec. Migrazioni r10: nessuna usata (0290-0299 libere): le tabelle verify nascono in verify_repo.run_migrations. Log in scratchpad/r10sec_*.
## In corso
Giro r10 (voci [~] di §4 e §7, #59 #60 #117 #118): fatte VER-017/019/020/030/031, SIC-036, SIC-039, PERF-3. Tutto committato e pubblicato (d713ea0). Prossimo passo esatto: lanciare UNA volta in background python3 scripts/smoke.py --base main (log scratchpad/r10sec_smoke.log; interrotto a meta' per la pausa), poi rapporto finale. Batch mirato gia' verde (533 + 68 test).
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
- AMD-014: la base non include 'negri', 'negra', 'zingaro', 'paki' (nomi/parole comuni): decisione dell'owner se aggiungerli
- data_registry (dev-core): scheduled_actions con action_type channel_unlock usa user_id = ID del canale; aggiungerlo alla nota
- #119 LOG-029 (testo dei messaggi su disco, privacy); #113 log via webhook, invito in /setup
- MOD-065 (motivo facoltativo) non fatto: cambia la firma di tutti i comandi
- OAuth rientro oltre 7 giorni; alt_detection (#92)
- Eccezioni (allow_list) della regola anti-invito: 3 voci per codice (gg, com/invite, discordapp), tetto 25 voci = 8 inviti
- SIC-045 opt-out di rete (privacy), AMD-067, SIC-016/021
- data_registry (dev-core): scheduled_actions con action_type channel_unlock usa user_id = ID del canale
- #119 LOG-029; #113 log via webhook; MOD-065; OAuth rientro oltre 7 giorni
