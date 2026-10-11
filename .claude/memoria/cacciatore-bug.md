# Memoria di cacciatore-bug

## Aggiornata
11/10/2026 · ultimo giro: ramo `feat/147-cerca-comando` (pannello, -chiedi, command_usage)

## In corso
- Niente a metà. Giro 147 chiuso (rapporto dato).

## Fatto
- Revisione delle correzioni del 28/09–01/10: BUG-19…34, SEC-18…22
  (`revisione/01-analisi/REVIEW.md` §20). Tutti risolti in R1-bis,
  tranne BUG-26/28/29 superati dal nuovo disegno del backup (D8).

- Giro fix/f1-135 (#135/#136): un solo rilievo vero, deadlock `set_member_role` vs `apply_text_tick`. Chiamanti di `EsitoRuolo`: uno solo (leveling.py), a posto. Funzioni rimosse: nessun uso residuo.

- 05/10 revisione ramo fix/f1-133: 4 rilievi (cache verifica con corsa, avviso anti-raid doppio, `_in_attesa` senza scadenza, `raid_in_corso` senza chiamanti).

- Giro fix/f1-134: nome rinominato senza chiamanti residui; lock/unlock/kick a posto (errori Discord presi); 3 test falliscono sulla base, 44/44 sul ramo. Unico rilievo: 3 query per evento col premium acceso.

- Giro feat/boost-146 (#146/D23): nessun bug vero. Migrazione 0020 tracciata in schema_migrations (una volta, in transazione); chiamanti vecchi: nessuno; blocchi membro→coin, gilda solo `clans`: niente deadlock (stress ok); tick con ×2 separato ok. 3 note basse.

- Giro feat/f7-quadro (command_access): 1 alto latente (sotto-gruppo `Group` semplice non eredita il check), @everyone via import config, ruolo admin vale per security. Albero a 2 livelli con `aggiungi_a_gruppo` protetto davvero.

- Giro feat/f7-decoratore (permessi): matrice 252 foglie x 8 profili vs 4903ef0, nessuna regressione di permesso; `/owner` rientra nell'albero globale se si ricarica custom_command_requests; ruolo bot vs default_permissions; messaggi con `/setup` e `/verify` vecchi.

- Giro feat/147-cerca-comando: 0 alti. Cache ID sotto lock senza timeout + nessun defer (media); `invalida()` perso se la fetch fallisce, `invalida_id` senza chiamanti; ricerca mostra `/clan bacheca` ai membri; `guild` None con `guild_id` pieno = trattato da DM. Upsert/pulizia/embed/componenti/migrazione 0022 a posto. Prove in scratchpad/cb147.

## Cose imparate
- Ordine dei blocchi nel clan: riga membro, poi `leveling_totals`, poi `clans`. Un fix che blocca `clans` per primo e poi tocca il membro va in deadlock con `apply_text_tick`. Si prova con due cicli in parallelo e si confronta con la base (`git archive`).
- La prima revisione non aveva visto che il worker dei backup non
  partiva mai (avviato prima dell'accesso): **controllare sempre
  l'ordine di avvio**, non solo la logica.
- Un fix scritto in un piano può essere sbagliato: tre istruzioni del
  piano lo erano (durata dello `state` OAuth per un link mandato in
  privato; fermare in `cog_unload` i task che cancellano i ticket;
  criterio di pulizia dei server del Creator). Si prova, non si copia.
- BUG-17 era un falso positivo: prima di segnalare una corsa, provarla
  con `tests/support/concorrenza.py`.
- I difetti più frequenti qui: leggi-poi-scrivi su saldi e contatori;
  risposte oltre i limiti con dati lunghi; azioni riportate come
  riuscite quando sono fallite.

- Cache "leggi, poi set" con await in mezzo: la scrittura che fa `delete` non basta, serve un numero di versione. Per provare: `ENVIRONMENT=development MAIN_GUILD_ID=1` e token finti.

- Il DB di prova è condiviso: due pytest insieme (clean_db) danno fallimenti a caso. Controllare `pgrep pytest` prima di fidarsi di un rosso.
- Per importare `core.config` fuori dai test: esportare le righe di `.env.example` e `PREMIUM_ALPHA_UNLOCK_ALL=false` (altrimenti il premium è sempre sbloccato).

- Script fuori dal ramo: `python -m pytest -c pytest.ini --rootdir=. -p tests.conftest <file in scratchpad>` dalla copia di lavoro (serve anche `-p no:cacheprovider`).

- Check dei gruppi: si prova con `cmd._check_can_run(interaction)` su un albero vero (`costruisci_gruppi` + `aggiungi_a_gruppo`), non chiamando `interaction_check` a mano. discord.py guarda solo il genitore diretto e non controlla l'autocomplete.

- Su main (4903ef0) i comandi staff NON avevano controlli (warn/kick/ban/status...): 'prima' = aperto; confrontare con `Command._check_can_run` su albero vecchio estratto con `git archive` in scratchpad (cb-f7b/matrice.py, msgs.py).

- Per provare un cog sull'albero VERO: `generate_command_list.py` mostra come caricare i cog con `BlacklistAwareCommandTree`; db.connect()+run_migrations(). Nome DB con maiuscole: `CREATE DATABASE "iyokai_wcacciaA"` tra virgolette, altrimenti Postgres lo mette minuscolo. I test del cerca-comando mockano `puo_usare` e `ottieni`: non vedono i permessi veri.

## Aperto
- Giro da fare a fine F1 sulle aree toccate il 05/10 (sicurezza,
  moderazione, log, ticket, vocali, livelli, clan).
- Rilievi senza fix: issue #133–#137 (vedi `rapporti/bug.md`).
