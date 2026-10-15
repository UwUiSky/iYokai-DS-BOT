# Memoria dev-moderazione
## Aggiornata
2026-10-15, ramo feat/r7mod, worktree /home/claude/wt/r7mod, DB iyokai_wr7mod. Migrazioni r7: 0180–0189.
## In corso
Giro r7 (previsione 3 voci): #113 iYokai Mod (fatto) → #119 catalogo log + residui #61 → #101 NF-30 appello ban. Mi fermo dopo #101.
Prossimo passo: #101 NF-30, partire da cogs/moderation/ban_appeal.py (esiste gia') e core/ban_appeal_logic.py.
## Fatto
- Giri G1-G7, R5, R6 (vedi git log e REGISTRO_RISOLTE): tempban modi, appelli spam-trap, verify, lockdown, phishing, captcha, anti-raid r6, massa, automod filtri
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
