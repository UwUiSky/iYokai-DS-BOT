# Memoria di dev-backup

## Aggiornata
12/10/2026 · ramo `feat/r3-bak` · base `c23a815` · DB `iyokai_wbak` · migrazioni 0070+

## In corso
Previsione giro: 4 voci. Fatte 2 (clone 12.3-12.8; collegamento 12.1/12.2/12.9 + 12.13 + test ordine).
Prossimo passo: pass restore, UN colpo su `cogs/utility/restore.py`, `core/restore_oauth_logic.py`,
`core/restore_orchestrator.py`, `core/oauth_crypto.py`, `core/restore_batch_logic.py`: 12.10 rinnovo token,
12.11 429+pause+conteggio dopo esito (usare `bot.http.request(Route)`), 12.12 DM solo con consenso,
12.14 link consenso a fine verifica, 12.15 prefisso versione chiave + AAD guild/utente + riga rovinata saltata;
in restore.py sostituire il check `coppia.backup_guild_id` con `backup_repo.is_backup_of` (12.13).
Poi VERIFICA_LIVE.md e rapporto. Se resta fiato: BKP-032/034 (export JSON) in file nuovo.

## Fatto
- 12.3-12.8 clonazione su server da modello (93713e0).
- 12.1, 12.2, 12.9, 12.13 (repo) + test ordine #68: `crea`/`collega`, worker sul client del Creator, niente
  create_guild/delete/cessione/10 posti/promemoria; cricchetto in `tests/test_backup_collegamento.py`.

## Cose imparate
- BUG-26, BUG-28, BUG-29 superati dal disegno D8: niente pulizia server del Creator.
- Migrazioni: file `core/migrations/NNNN_*.sql`; repository in `core/repositories/` (non `repositories/`).
- Il nome `test*` importato in un file di test viene raccolto da pytest: non chiamare funzioni `testo_*`.
- `#15` (verifica del backup in `/restore-users`) c'è già (`cogs/utility/restore.py:149`) ma fallisce dopo la
  promozione (BUG-34): serve `backup_repo.is_backup_of` (fatto nel repo, da usare in restore.py).
- I fake dei test clone sono minimi: dopo ogni nuova chiamata a Discord aggiungere il metodo al fake.
- `main.py` (non mio) chiama `finalize_backup_job`, `backup_queue_worker.start(creator, bot, perms)`.

## Aperto
- Snapshot dei dati (11.1/12.17: più copie datate, ultimi N messaggi) e copia dei messaggi (D8) non fatti.
- Test `tests/test_command_tree_invariants.py::test_ogni_opzione_di_testo_ha_un_massimo` rosso sulla base per `fun search-image:query` (non mio).
- `main.py` on_guild_join: nel nuovo flusso Main entra nel server di backup prima del collegamento e riceve il
  trattamento "server nuovo" (dev-core).
- #113 iYokai Mod: non fatto (serve l'owner).
