# Memoria di dev-backup

## Aggiornata
12/10/2026 · ramo `feat/r3-bak` · base `c23a815` · DB `iyokai_wbak` · migrazioni 0070+

## In corso
Previsione giro: 4 voci (clone 12.3-12.8, collegamento 12.1/12.2/12.9 + test ordine, restore 12.10-12.15, BKP se resta fiato).
Prossimo passo: pass "orchestrazione" (file tutti in un colpo): `core/backup_orchestrator.py`
(sostituire `start_backup_job` con `popola_server_backup(main, backup)` che usa `RiepilogoCopia`;
`finalize_backup_job` resta solo come "il server è atteso?" per `main.py:400`; togliere elimina/pulisci),
`core/backup_queue_worker.py` (job pending con backup_guild_id, `creator_client.get_guild`, niente slot/promemoria;
firma `tick`/`start` invariata perché `main.py` la chiama), `cogs/utility/backup.py` (`crea` = codice + modello +
link inviti; nuovo `collega codice`), cancellare `core/backup_reminder_logic.py` e suo test, riscrivere i test
vecchi (orchestrator, queue_worker, creator_cleanup, main_bot:~375). Già pronti: `core/backup_link_logic.py`,
migrazione 0070, metodi in `backup_repo.py`, `tests/test_backup_collegamento.py` (cricchetto rosso finché c'è create_guild).

## Fatto
- 12.3-12.8 clonazione su server da modello: riuso per nome, posizioni ruoli, bitrate, webhook max 14,
  mirror riusato, nome sicuro, `___hidden___` (commit in git log, Refs #68).

## Cose imparate
- BUG-26, BUG-28, BUG-29 superati dal disegno D8: niente pulizia server del Creator.
- Migrazioni: file `core/migrations/NNNN_*.sql`; repository in `core/repositories/` (non `repositories/`).
- `#15` (verifica del backup in `/restore-users`) c'è già (`cogs/utility/restore.py:149`) ma fallisce dopo la
  promozione (BUG-34): serve `backup_repo.is_backup_of` (fatto nel repo, da usare in restore.py).
- I fake dei test clone sono minimi: dopo ogni nuova chiamata a Discord aggiungere il metodo al fake.
- `main.py` (non mio) chiama `finalize_backup_job`, `backup_queue_worker.start(creator, bot, perms)`.

## Aperto
- `tests/test_backup_orchestrator.py`: test 3 lascia la coppia (100,555) nel DB; fixture di pulizia da mettere.
- `main.py` on_guild_join: nel nuovo flusso Main entra nel server di backup prima del collegamento e riceve il
  trattamento "server nuovo" (dev-core).
- #113 iYokai Mod: non fatto (serve l'owner).
