# Memoria dev-moderazione
## Aggiornata
2026-10-12, ramo feat/giro-mod (main bdc5fb1 unito), worktree /home/claude/wt/mod, DB iyokai_wmod, migrazioni da 0040.
## In corso
Cacciatore (P1-P12) e revisore (10 punti) fatti; unito feat/giro-core. Nessun file a meta.
## Fatto
- G1 #138: /modban tempban modo (fuori|rientro|isolamento), core/tempban_logic.py, cogs/moderation/_tempban_modes.py, migrazione 0040 tempban_stato, unban libera l'isolamento
- G2 #57: M 1.8 (log lock/unlock/slowmode/clear/untimeout/unmute/scadenza), caso (motivo/elimina/classifica-staff/storico per tipo), nota (rimuovi/modifica/svuota), avvisi (togli/azzera/classifica), clear con 12 filtri (core/clear_filter_logic.py)
- G3 #101: appelli ban manuali (ban_appeal.py, ban_appeal_logic.py, migrazione 0041 ban_appelli, /modban appelli canale|elenco, DM con bottone)
- G4 #118/#60: verify opzioni (non verificato, 3 ruoli extra via guild settings), manuale, tentativi, statistiche (verify_repo.attempt_stats)
- G5 #116: AMD-021 messaggi modificati ricontrollati (on_message_edit, build_message_signals conta_nel_tempo)
- Gia fatte prima del giro: M 1.1-1.7, 1.9 (test_moderation_*), #60 4.1 (test_verify_risposta_subito)
- G6 bug-hunt: isolamento/tempban su gia isolato (ruoli veri tenuti, mai ruolo iso), stato PRIMA dell'azione + ripristino se fallisce, cancel_tempban_jobs (tempban/unban/appello) + guardia case_number nel job, invito al mod se DM chiuso, appello: unban poi 'accettato', solo il caso dell'appello, 24 h atomico (advisory lock), clear channel con permessi utente, verify non-verificato/ruolo sopra bot, Range INT4 su caso/nota, get_member->fetch, warn automod non ripetuto, set_permissions in parallelo (8)
- G7 revisore: ban/kick su isolato puliscono stato/job/caso/invito; unban isolato solo se membro presente; rientro senza invito ne OAuth = niente ban; canali non nascosti contati; appello su caso non attivo chiuso 'accettato' senza unban; unban chiude appelli aperti; rientro OAuth (migrazione 0042 oauth_rientro, join_user_via_oauth); ban_appelli/tempban_stato in data_registry (365 g decisi / 30 g dopo la fine); inviti cancellati (client.delete_invite); 5 chiavi in SETTINGS_SCHEMA; test per le mutazioni
## Cose imparate
- Tabelle sicurezza in security_repo.run_migrations; le nuove di moderazione in core/migrations/NNNN (clean_db le svuota da information_schema)
- Smoke oltre 2 min: lanciarlo con nohup su log; mai due pytest sullo stesso DB
- Gruppo /mod: 11 figli diretti + sottogruppi caso(5), nota(5), avvisi(3); tetto 25. test_f7_moderazione_gruppi.py ATTESI va aggiornato a ogni comando nuovo
- Il bot non puo scrivere a un bannato: DM e invito prima del ban; ban fallito = cancellare DM e invito
- Isolamento: member.edit(roles=...) una sola chiamata; ruoli gestiti o sopra il bot restano; salvati solo i tolti
- Moduli in cogs/moderation non iniziano per _ = cog: gli aiuti si chiamano _nome.py. Funzioni che iniziano per test_ nei moduli importati dai test vengono raccolte da pytest
- Comandi distruttivi (elimina caso, svuota note, azzera warn) controllano manage_guild nel codice
- Stato su DB PRIMA dell'azione irreversibile; UPSERT di stato da membro gia in stato = perdita dati. Job di scadenza: cancellare a ogni cambio di caso e proteggere l'handler con case_number
- Test di corsa: apri_connessioni, poi mutazione con git stash push -- cogs core
- Fake messaggi AutoMod ora hanno id
## Aperto
- M 1.10 soglie sui warn manuali (F9). OAuth: il token deve durare fino alla fine del ban (niente refresh): oltre ~7 giorni resta l'invito. Inviti di stati scaduti senza rientro restano fino a unban
- Appelli: bottone nel DM di un bannato da provare live; spam-trap ha un suo sistema (non toccato). alt_detection, lockdown (#100)
- AutoMod #116: restano quasi tutte (nuovi filtri chiedono colonne in automod_advanced_repo; violazioni per regola non persistite)
- Catalogo #115 ancora aperto per il resto (bulk, voce, nickname, DM personalizzati, motivi pronti)
