# Memoria dev-moderazione
## Aggiornata
2026-10-28, giro r10 (agente r10filtro, ramo feat/r10filtro, worktree /home/claude/wt/r10filtro): AMD-014 fatto, nessuna migrazione usata (0370-0379 libere). Smoke da fare (regola owner: niente smoke).
2026-10-21, ramo feat/r9mod, worktree /home/claude/wt/r9mod. Migrazioni r9: 0250 usata (0251–0259 libere). Log in scratchpad/r9mod.
## In corso
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
## Cose imparate
- D15: Mod non ha listener; azioni di sicurezza via bot_roles.banna/espelli/isola/cancella_messaggio; e_un_nostro_bot per "e' il bot"
- discord.RateLimited NON e' HTTPException: va preso a parte (bot_roles lo fa)
- Tabelle sicurezza in security_repo.run_migrations; config anti-raid/anti-nuke in JSON: campi nuovi senza migrazione (_to_json/_from_json)
- Colonne nuove su tabelle create da run_migrations dei repo: migrazione numerata (gira dopo i repo)
- Smoke e suite oltre 2 min: run_in_background su log in scratchpad/r9mod
- Pesi r9 (scratchpad/r9mod/tools/pesi.py): /mod ~4600/15, /security ~4700, /antinuke ~2800. ATTESI in test_f7_moderazione_gruppi (anche MODULI per un cog nuovo), locales/comandi.en.json (inserire a testo: indentazione mista, non riordinare)
- Il bot non puo' scrivere a un bannato/espulso: DM prima, cancellato se l'azione fallisce
- Stato su DB PRIMA dell'azione irreversibile; job di scadenza protetti con controllo nell'handler
- Opzione facoltativa nuova: va DOPO le obbligatorie (cambia l'ordine: aggiornare i test che chiamano callback per posizione)
- test_riferimenti_comandi legge anche docstring e messaggi: citare il percorso intero (/mod opzioni imposta durata_timeout:)
- KNOWN_SENZA_MAX_LENGTH e' un cricchetto: togliere la voce quando si aggiunge Range
- Nuove chiavi guild settings: SETTINGS_SCHEMA + tests/test_config_import_validation.py; chi-puo'-cosa anche CHIAVI_SOLO_PROPRIETARIO
- Stato in memoria da azzerare nei test: db._settings_cache, db._modules_cache, spam_trap_repo._config_cache, azzera_usi()
- str.replace sostituisce TUTTE le occorrenze: per i docstring controllare count==1
## Aperto
- AMD-014: la base non include 'negri', 'negra', 'zingaro', 'paki' (nomi/parole comuni): decisione dell'owner se aggiungerli
- data_registry (dev-core): scheduled_actions con action_type channel_unlock usa user_id = ID del canale; aggiungerlo alla nota
- #119 LOG-029 (testo dei messaggi su disco, privacy); #113 log via webhook, invito in /setup
- MOD-065 (motivo facoltativo) non fatto: cambia la firma di tutti i comandi
- OAuth rientro oltre 7 giorni; alt_detection (#92)
