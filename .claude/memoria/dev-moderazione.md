# Memoria dev-moderazione
## Aggiornata
2026-10-11 (notte), ramo feat/giro-mod (da main), worktree /home/claude/wt/mod, DB iyokai_wmod, migrazioni da 0040.
## In corso
Previsione: 5 gruppi (tempban #138, caso/note/warn+clear+log, appelli, verify, filtri AutoMod).
Fatti i primi due. Prossimo: appelli NF-30 (cogs/moderation/ban_appeal.py, core/ban_appeal_logic.py: scheletri) oppure 1.10 (soglie warn manuali: serve flag in escalation_repo + migrazione 0041).
## Fatto
- G1 #138: /modban tempban modo (fuori|rientro|isolamento), core/tempban_logic.py, cogs/moderation/tempban_modes.py, migrazione 0040 tempban_stato, unban libera l'isolamento
- G2 #57: M 1.8 (log lock/unlock/slowmode/clear/untimeout/unmute/scadenza), caso (motivo/elimina/classifica-staff/storico per tipo), nota (rimuovi/modifica/svuota), avvisi (togli/azzera/classifica), clear con 12 filtri (core/clear_filter_logic.py)
- Gia fatte prima del giro: M 1.1-1.7, 1.9 (test_moderation_*), #60 4.1 (test_verify_risposta_subito)
## Cose imparate
- Tabelle sicurezza in security_repo.run_migrations; le nuove di moderazione in core/migrations/NNNN (clean_db le svuota da information_schema)
- Smoke oltre 2 min: lanciarlo con nohup su log; mai due pytest sullo stesso DB
- Gruppo /mod: 11 figli diretti + sottogruppi caso(5), nota(5), avvisi(3); tetto 25. test_f7_moderazione_gruppi.py ATTESI va aggiornato a ogni comando nuovo
- Il bot non puo scrivere a un bannato: DM e invito prima del ban; ban fallito = cancellare DM e invito
- Isolamento: member.edit(roles=...) una sola chiamata; ruoli gestiti o sopra il bot restano; salvati solo i tolti
- Comandi distruttivi (elimina caso, svuota note, azzera warn) controllano manage_guild nel codice
## Aperto
- M 1.10 soglie sui warn manuali (F9); rientro automatico OAuth di #138 (serve #92)
- Appelli NF-30/#101 (scheletri), alt_detection, lockdown (#100)
- Catalogo #115 ancora aperto per il resto (bulk, voce, nickname, DM personalizzati, motivi pronti)
