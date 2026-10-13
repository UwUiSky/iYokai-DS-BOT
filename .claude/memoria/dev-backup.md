# Memoria di dev-backup

## Aggiornata
13/10/2026 · ramo `feat/r3-bak` · base `c23a815` · DB `iyokai_wbak` · migrazioni 0070+

## In corso
Giro 13/10 chiuso: 8 voci su 8 del revisore-capo (previste 8). Niente a metà. Prossimo giro, in quest'ordine:
1. 12.12 + 12.14 (restore/verify): servono un dato di consenso al DM scritto dal flusso di verifica e il link
   di consenso a fine verifica in `cogs/security/verify.py` (file non mio: chiedere all'orchestratore). Non fatti: toccano verify.py.
2. 11.1/12.17 snapshot come dati con più copie datate (la copia dei messaggi D8 è fatta, ultimi 50 per canale).
3. #121: BKP-032/033/034/036/037 (export/import JSON/CSV), BKP-009/010 (stato e annullo), BKP-018/019, BKP-024/025.
4. #110 NF-39 (`core/server_sync_logic.py` esiste già: leggere prima). Guardiano dei limiti per ogni comando nuovo.

## Fatto
- Correzioni cacciatore-bug (commit dopo 1083ada): collegamento atomico + indice unico (0071), blocco e registro contatti nel restore, get_stato per i bannati, 429 sul rinnovo (LimiteDiFrequenza), ruoli Forbidden/permessi ridotti, categoria `___hidden___` coi figli, on_guild_join in main.py, data_registry.
- 12.3-12.8 clonazione su server da modello (93713e0).
- 12.1, 12.2, 12.9, 12.13 + test ordine #68 (874b0ed): `crea`/`collega`, worker sul client del Creator,
  niente create_guild/delete/cessione/10 posti/promemoria; cricchetto in `tests/test_backup_collegamento.py`.
- 12.10, 12.11, 12.13 (restore), 12.15 (commit in git log): rinnovo token, 429/pause/conteggi/riepilogo,
  chiave ruotabile + AAD + riga rovinata. #15/#46 D: il controllo c'era, ora vale anche dopo la promozione.

- 13/10 (rapporto del revisore-capo, 9 righe): copia messaggi D8 `core/backup_messages_logic.py` (50 per canale, webhook del mirror,
  uno alla volta, canale di backup già con messaggi = saltato); `collega_atomico` blocca main e backup in ordine; worker `_fallisci` anche
  con Main assente; overwrite ridotti alla maschera del Creator; test: cog collega (3+1), seconda chiave, mutazioni, F401.

## Cose imparate
- BUG-26, BUG-28, BUG-29 superati dal disegno D8: niente pulizia server del Creator.
- Migrazioni: file `core/migrations/NNNN_*.sql`; repository in `core/repositories/` (non `repositories/`).
- Il nome `test*` importato in un file di test viene raccolto da pytest: non chiamare funzioni `testo_*`.
- `#15` (verifica del backup in `/restore-users`) c'è già (`cogs/utility/restore.py:149`) ma fallisce dopo la
  promozione (BUG-34): serve `backup_repo.is_backup_of` (fatto nel repo, da usare in restore.py).
- I fake dei test clone sono minimi: dopo ogni nuova chiamata a Discord aggiungere il metodo al fake.
- collega: `collega_atomico` in una transazione (advisory lock sul main); un Creator senza Amministratore riduce i permessi dei ruoli.
- Test di concorrenza: `apri_connessioni` + `gather`, e controllare l'esito esatto (non solo «uno solo ok»). Fixture del worker: pulire anche `backup_pairs`.
- Metodi di repo senza chiamante rompono `tests/test_repository_callers.py`: toglierli con i loro test.
- Cifrato token: formato `v2.<idchiave>.<b64>`, AAD `guild:utente`; `OAUTH_ENCRYPTION_KEY` può avere più chiavi con virgola.
- `main.py` (non mio) chiama `finalize_backup_job`, `backup_queue_worker.start(creator, bot, perms)`.

## Aperto
- Snapshot dei dati (11.1/12.17: più copie datate) non fatti. Copia dei messaggi: da provare live (tempi, ordine; i messaggi arrivati durante la copia non entrano).
- Test `tests/test_command_tree_invariants.py::test_ogni_opzione_di_testo_ha_un_massimo` rosso sulla base per `fun search-image:query` (non mio).
- `main.py` on_guild_join: nel nuovo flusso Main entra nel server di backup prima del collegamento e riceve il
  trattamento "server nuovo" (dev-core).
- #113 iYokai Mod: non fatto (serve l'owner).
