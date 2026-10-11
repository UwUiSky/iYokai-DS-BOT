# Memoria dev-moderazione
## Aggiornata
2026-10-11 (notte), ramo feat/giro-mod (da main), worktree /home/claude/wt/mod, DB iyokai_wmod, migrazioni da 0040.
## In corso
Previsione: 5 gruppi (tempban #138, caso/note/warn+clear+log, appelli, verify, filtri AutoMod).
Fatti cinque (G5 AMD-021). Smoke fatto (4 test adattati, ora verdi); pushato; rapporto consegnato. Nessun file a meta. 1.10 resta aperta.
## Fatto
- G1 #138: /modban tempban modo (fuori|rientro|isolamento), core/tempban_logic.py, cogs/moderation/_tempban_modes.py, migrazione 0040 tempban_stato, unban libera l'isolamento
- G2 #57: M 1.8 (log lock/unlock/slowmode/clear/untimeout/unmute/scadenza), caso (motivo/elimina/classifica-staff/storico per tipo), nota (rimuovi/modifica/svuota), avvisi (togli/azzera/classifica), clear con 12 filtri (core/clear_filter_logic.py)
- G3 #101: appelli ban manuali (ban_appeal.py, ban_appeal_logic.py, migrazione 0041 ban_appelli, /modban appelli canale|elenco, DM con bottone)
- G4 #118/#60: verify opzioni (non verificato, 3 ruoli extra via guild settings), manuale, tentativi, statistiche (verify_repo.attempt_stats)
- G5 #116: AMD-021 messaggi modificati ricontrollati (on_message_edit, build_message_signals conta_nel_tempo)
- Gia fatte prima del giro: M 1.1-1.7, 1.9 (test_moderation_*), #60 4.1 (test_verify_risposta_subito)
## Cose imparate
- Tabelle sicurezza in security_repo.run_migrations; le nuove di moderazione in core/migrations/NNNN (clean_db le svuota da information_schema)
- Smoke oltre 2 min: lanciarlo con nohup su log; mai due pytest sullo stesso DB
- Gruppo /mod: 11 figli diretti + sottogruppi caso(5), nota(5), avvisi(3); tetto 25. test_f7_moderazione_gruppi.py ATTESI va aggiornato a ogni comando nuovo
- Il bot non puo scrivere a un bannato: DM e invito prima del ban; ban fallito = cancellare DM e invito
- Isolamento: member.edit(roles=...) una sola chiamata; ruoli gestiti o sopra il bot restano; salvati solo i tolti
- Moduli in cogs/moderation non iniziano per _ = cog: gli aiuti si chiamano _nome.py. Funzioni che iniziano per test_ nei moduli importati dai test vengono raccolte da pytest
- Comandi distruttivi (elimina caso, svuota note, azzera warn) controllano manage_guild nel codice
## Aperto
- M 1.10 soglie sui warn manuali (F9); rientro automatico OAuth di #138 (serve #92)
- Appelli: bottone nel DM di un bannato da provare live; spam-trap ha un suo sistema (non toccato). alt_detection, lockdown (#100)
- AutoMod #116: restano quasi tutte (nuovi filtri chiedono colonne in automod_advanced_repo; violazioni per regola non persistite)
- Catalogo #115 ancora aperto per il resto (bulk, voce, nickname, DM personalizzati, motivi pronti)
