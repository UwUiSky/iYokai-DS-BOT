# Memoria dev-moderazione
## Aggiornata
2026-10-14, ramo feat/r6mod, worktree /home/claude/wt/r6mod. DB scheda iyokai_wr6mod (usato anche da r6ai!): io uso iyokai_wr6mod_b. Migrazioni r6: nessuna (tutto in JSON o guild settings).
## In corso
Giro r6 chiuso (smoke lanciato). Prossimo giro: SIC-036 (livelli di allerta, con AMD-067 gruppi di regole), SIC-039/040 (piu' canali trappola, punizione a scelta), MOD-007/011/013, VER-017/019/020, AMD-026/027/028 (inviti), AMD-058…066 (violazioni persistite: serve migrazione).
## Fatto
- Giri G1-G7, R5 (vedi git log): tempban modi, appelli, clear filtri, verify opzioni, lockdown/panico NF-29, phishing NF-31, captcha immagine NF-18, AMD-002/003/005/021, VER-029
- R6-1 49cee20 SIC-042: /automod filtri phishing accorciatori|inviti_adulti (fetch_invite, cache _inviti_adulti con tetto)
- R6-2 d63f5c2 anti-raid: core/security_join_logic.py; filtro-ingresso, nomi-vietati, segnali, ping-ruoli, elenco, segnala; lockdown kick/ban; retroattivo; rete
- R6-3 da5164c /modban massa ban|unban|kick, /mod massa timeout|warn (core/moderation_bulk_logic.py, bulk_ban); _dopo_unban condiviso
- R6-4 5b94357 /security verify tempi (VER-008/009/011/012/013); D25 terzo caso: /antiraid primo livello
- R6-5 5483095 /utility verifica (VER-010, avvia_verifica condivisa col bottone, niente controllo panico)
- R6-6 03ef20a /automod filtri messaggi|contenuto|canale-media, kick (AMD-001/004/006/007/019/020/022/023/024/041); registro, SPEC, VERIFICA_LIVE
## Cose imparate
- Tabelle sicurezza in security_repo.run_migrations; config anti-raid/automod in JSON: campi nuovi senza migrazione (_to_json/_from_json)
- Smoke e suite oltre 2 min: nohup su log in scratchpad/r6mod (la scratchpad e' condivisa: file fuori dalla mia cartella spariscono)
- Gruppi: /mod 13 figli+massa, /modban 6+massa, /antiraid 16, /security ~5100 dopo lo spostamento. ATTESI in test_f7_moderazione_gruppi, test_command_groups, tests/support/command_policy.py, locales/comandi.en.json (script locale.py)
- Il bot non puo scrivere a un bannato: DM e invito prima del ban; ban fallito = cancellare DM
- Stato su DB PRIMA dell'azione irreversibile; job di scadenza protetti con controllo nell'handler
- Moduli in cogs/moderation non iniziano per _ = cog. Funzioni test_* nei moduli importati vengono raccolte
- Docstring: mai "/mod e /modban" in prosa. Metodo di repo solo nei test = test_repository_callers fallisce
- Stato in memoria da azzerare nei test: security_raid_state._ultimo_ingresso, security_join_logic.azzera_ingressi, automod._inviti_adulti
- fake_member e' autospec: display_name/global_name vanno letti solo se servono (i _FakeMember dell'automod non hanno nick)
- Nuove chiavi guild settings: SETTINGS_SCHEMA in cogs/utility/config_history.py + valori in tests/test_config_import_validation.py
## Aperto
- M 1.10 soglie sui warn manuali (F9). OAuth rientro oltre 7 giorni. alt_detection (#92)
- SIC-036 livelli di allerta (dipende da AMD-067), SIC-003…022 resto, SIC-039/040/044/046
- AutoMod #116: aperte le altre (liste, regex, eccezioni per filtro, violazioni per regola); #115: resto (voce, nickname, DM personalizzati, motivi pronti)
- Un altro agente (worktree r6ai) lancia pytest su iyokai_wr6mod: segnalato all'orchestratore
