# Memoria dev-moderazione
## Aggiornata
2026-10-21, ramo feat/r9mod, worktree /home/claude/wt/r9mod. Migrazioni r9: 0250–0259. Log in scratchpad/r9mod.
## In corso
Giro r9 (previsione 5 voci; prossima: 4): 1) #59 ripiego kick/ban se la quarantena non riesce (AntiNukeConfig, /antinuke punish-action) → 2) M 1.10 warn manuali nella scala (escalation) → 3) /mod opzioni (MOD-010, 017, 057, 065, 068) → 4) MOD-013 sanzioni a tempo attive + MOD-090 lock a tempo → 5) SIC-040 punizione del canale trappola. Mi fermo dopo la 5.
Residui gia' fatti in codice (verificati r9): M 1.1–1.9, 2.1–2.7, 3.1–3.18 (tranne ripiego), 4.1–4.3.
Pesi r9 (script scratchpad/r9mod/tools/pesi.py): antinuke 2674/12, antiraid 2756/16, automod 5015/7, mod 3953/14, modban 1683/7, security 4536/8.
## Fatto
- R9-1 #59 ripiego kick/ban (be45348): AntiNukeConfig.ripiego_quarantena, opzione ripiego di /antinuke punish-action
- R9-3 /mod opzioni imposta|dm|immuni (MOD-010/017/057/068): core/moderation_opzioni.py, chiavi mod_* in SETTINGS_SCHEMA, mod_ruoli_immuni solo proprietario
- R9-2 M 1.10 (1988cd6): escalation.scala_per_warn_manuale, /security escalation enable warn_manuali, migr. 0250
- Giri G1-G7, R5, R6 (vedi git log e REGISTRO_RISOLTE): tempban modi, appelli spam-trap, verify, lockdown, phishing, captcha, anti-raid r6, massa, automod filtri
- R7-3 #101 NF-30: era gia' fatto; aggiunto il bottone di appello a chi scrive al bot in DM (offri_appello_in_dm, chiamato dallo spam-trap)
- R7-2 #119 LOG-005/006/012/017/027/030 (/log eventi, /log archivio-canale, migr. 0180); mod-log e log AutoMod dal router (§18.1); tolti DA FARE #61
- R7-1 #113 iYokai Mod: core/bot_roles.py (unico punto), core/mod_bot.py, router, mod-log, automod, escalation, anti-raid, anti-nuke, spam-trap, scadenza tempban; invito in /utility info
## Cose imparate
- D15: Mod non ha listener; eventi solo dal principale → niente doppioni. Azioni nuove di sicurezza: passare da bot_roles.banna/espelli/isola/... o bot_roles.scrivi (log). Messaggi con view: sempre il principale
- discord.RateLimited NON e' HTTPException: va preso a parte (bot_roles lo fa)
- Confronti "e' il bot stesso" nella sicurezza: bot_roles.e_un_nostro_bot (conta anche Mod)
- Tabelle sicurezza in security_repo.run_migrations; config anti-raid/automod in JSON: campi nuovi senza migrazione (_to_json/_from_json)
- Smoke e suite oltre 2 min: nohup su log in scratchpad/r7mod
- Gruppi: /mod 13 figli+massa, /modban 6+massa, /antiraid 16, /security ~5100. ATTESI in test_f7_moderazione_gruppi, test_command_groups, tests/support/command_policy.py, locales/comandi.en.json
- Il bot non puo scrivere a un bannato: DM e invito prima del ban; ban fallito = cancellare DM
- Stato su DB PRIMA dell'azione irreversibile; job di scadenza protetti con controllo nell'handler
- Moduli in cogs/moderation non iniziano per _ = cog. Funzioni test_* nei moduli importati vengono raccolte
- Docstring: mai "/mod e /modban" in prosa. Metodo di repo solo nei test = test_repository_callers fallisce
- Stato in memoria da azzerare nei test: security_raid_state._ultimo_ingresso, security_join_logic.azzera_ingressi, automod._inviti_adulti, bot_roles.registra_mod(None)
- fake_member e' autospec: display_name/global_name vanno letti solo se servono
- Nuove chiavi guild settings: SETTINGS_SCHEMA in cogs/utility/config_history.py + tests/test_config_import_validation.py
- Test lenti (CPU condivisa): 700 test d'area ~10 min
## Aperto
- #119 LOG-029 (archivio utente 3 giorni): serve testo dei messaggi su disco, decisione di privacy
- #113: canali di log via webhook non fatti (Mod ha limiti suoi); /setup non mostra l'invito (sta in /utility info); Mod da solo in un server senza principale non fa nulla
- M 1.10 soglie sui warn manuali (F9). OAuth rientro oltre 7 giorni. alt_detection (#92)
- SIC-036 livelli di allerta (con AMD-067), SIC-003…022, SIC-039/040/044/046; #116 e #115 resto
