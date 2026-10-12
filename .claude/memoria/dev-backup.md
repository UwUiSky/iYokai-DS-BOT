# Memoria di dev-backup

## Aggiornata
12/10/2026 · ramo `feat/r3-bak` · base `c23a815` · DB `iyokai_wbak` · migrazioni 0070+

## In corso
Giro chiuso a 3 voci (previste 4). Niente a metà. Prossimo giro, in quest'ordine:
1. 12.12 + 12.14 (restore/verify): servono un dato di consenso al DM scritto dal flusso di verifica e il link
   di consenso a fine verifica in `cogs/security/verify.py` (file non mio: chiedere all'orchestratore).
2. 12.17 + BKP-026/027 (ultimi N messaggi per canale) e copia dei messaggi del D8 (webhook, uno alla volta):
   nuovo `core/backup_messages_logic.py`; snapshot come dati (11.1) con più copie datate.
3. #121: BKP-032/033/034/036/037 (export/import JSON/CSV), BKP-009/010 (stato e annullo), BKP-018/019, BKP-024/025.
4. #110 NF-39 (`core/server_sync_logic.py` esiste già: leggere prima). Guardiano dei limiti per ogni comando nuovo.

## Fatto
- 12.3-12.8 clonazione su server da modello (93713e0).
- 12.1, 12.2, 12.9, 12.13 + test ordine #68 (874b0ed): `crea`/`collega`, worker sul client del Creator,
  niente create_guild/delete/cessione/10 posti/promemoria; cricchetto in `tests/test_backup_collegamento.py`.
- 12.10, 12.11, 12.13 (restore), 12.15 (commit in git log): rinnovo token, 429/pause/conteggi/riepilogo,
  chiave ruotabile + AAD + riga rovinata. #15/#46 D: il controllo c'era, ora vale anche dopo la promozione.

## Cose imparate
- BUG-26, BUG-28, BUG-29 superati dal disegno D8: niente pulizia server del Creator.
- Migrazioni: file `core/migrations/NNNN_*.sql`; repository in `core/repositories/` (non `repositories/`).
- Il nome `test*` importato in un file di test viene raccolto da pytest: non chiamare funzioni `testo_*`.
- `#15` (verifica del backup in `/restore-users`) c'è già (`cogs/utility/restore.py:149`) ma fallisce dopo la
  promozione (BUG-34): serve `backup_repo.is_backup_of` (fatto nel repo, da usare in restore.py).
- I fake dei test clone sono minimi: dopo ogni nuova chiamata a Discord aggiungere il metodo al fake.
- Cifrato token: formato `v2.<idchiave>.<b64>`, AAD `guild:utente`; `OAUTH_ENCRYPTION_KEY` può avere più chiavi con virgola.
- `main.py` (non mio) chiama `finalize_backup_job`, `backup_queue_worker.start(creator, bot, perms)`.

## Aperto
- Snapshot dei dati (11.1/12.17: più copie datate, ultimi N messaggi) e copia dei messaggi (D8) non fatti.
- Test `tests/test_command_tree_invariants.py::test_ogni_opzione_di_testo_ha_un_massimo` rosso sulla base per `fun search-image:query` (non mio).
- `main.py` on_guild_join: nel nuovo flusso Main entra nel server di backup prima del collegamento e riceve il
  trattamento "server nuovo" (dev-core).
- #113 iYokai Mod: non fatto (serve l'owner).
