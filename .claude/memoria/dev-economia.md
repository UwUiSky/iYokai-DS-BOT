# Memoria di dev-economia

## Aggiornata
11/10/2026 · ramo `feat/f7-gestione-livelli` (base `1e5525c`, non pushato)

## In corso
- Niente a metà. F7 passo 3a chiuso sul ramo: aspetta smoke, unione e prova dal vivo.
  #146 (D23) su `feat/boost-146`: aspetta unione.

## Fatto
- F1, livelli + economia + clan: unito su main con `9db9e8a`
  (migrazioni `0015`–`0019`, `/clan lascia`, promozione a `co_owner`,
  `_pagine.py`).
- #135 clan (boost, dona, promuovi) su `fix/f1-135`: tutti e tre in un
  commit solo (repo condiviso). Test `tests/test_clan_135_scritture_atomiche.py`.
- #135 `reset_premium_registry`: salva e ripristina `is_premium_active`.
- #136 `/config export` non scrive più le voci a `null` (strada scelta).

- F7 passo 3a (#76): /level, /clan (+ bacheca, tesoreria, boost), /gestione economia|ruoli|benvenuto
  in 4 commit su `feat/f7-gestione-livelli`; test `tests/test_f7_gestione_livelli_gruppi.py`.
- #146 boost per tipo su `feat/boost-146` (5 commit, migrazione 0020, test `tests/test_clan_146_boost_per_tipo.py`).

## Cose imparate
- Ordine dei blocchi: membro -> leveling_totals -> clans (come `apply_text_tick`);
  `set_member_role` blocca prima il membro. Il contrario dà deadlock.
- `buy_member_boost`, `donate_from_member`, `set_member_role` verificano
  clan/guild/utente; `/config export` toglie null (anche in lista) e chiavi fuori schema.
- BUG-17 non esiste: c'è il test che lo prova.
- Le scritture di saldo vanno fatte condizionate nel database.
- Pagamento + effetto (scadenza boost, tesoreria) = una transazione con
  riga bloccata (`FOR UPDATE`); la scadenza si calcola sul valore letto
  sotto blocco. Boost D23: sotto blocco si controlla che nessun beneficio del tipo sia attivo; `buy_*_boost` restituiscono `EsitoBoost` (stato, scadenza, attivi); mai somma delle durate.
- `set_member_role(..., max_with_role=)` controlla il tetto sotto blocco
  della riga gilda; restituisce `EsitoRuolo`, non più bool.
- `tests/test_repository_callers.py`: ogni metodo di repo deve avere un chiamante
  di produzione; tolti `set_*_boost_expiry` e `spend_from_treasury` (sostituiti
  da `buy_*_boost`), `donate`/`count_members_with_role` presi con `conn=`.
- `spend_coins_in(conn, ...)` (leveling_repo) si riusa dentro altre transazioni.
- Test di concorrenza: `apri_connessioni(pool)` prima di `asyncio.gather`.
- Fixture a generatore: la si pilota con `_get_wrapped_function()()`;
  `close()` non esegue il codice dopo `yield`, serve `next()`.
- Un test che registra moduli premium usa una categoria ammessa
  (es. `utility`), altrimenti `register()` solleva ValueError.

- F7: i comandi di un cog con `CogConGruppi` non sono attributi `app_commands.Command`. Nei test
  `registra_comandi_del_cog(cog, gruppi=costruisci_gruppi(), tree=None)` dà i Command in gruppi
  isolati (nome qualificato "clan boost gilda"); `cog.metodo.callback(cog, ...)` resta valido.
- `LevelingCog.cog_unload` resta sincrono (i test lo chiamano senza await): cancella il task e
  chiama `togli_comandi_del_cog`. Test che fanno `add_cog` devono finire con `remove_cog`.
- `bacheca set/disable` stanno in /clan (pubblico): `@richiedi(Livello.ADMIN)` nel codice.
- Test che caricano LevelingCog con bot non connesso: `bot.wait_until_ready = asyncio.Event().wait`.

## Aperto
- Colonne vecchie `boost_expires_at`/`guild_boost_expires_at` restano nel database, non usate.
- I test senza `DATABASE_URL` esportato usano `iyokai_test` (condiviso): esportarlo sempre.
- `tests/support/command_policy.py`: riga `"gestione"` aggiunta qui; se la aggiungono anche ticket/voice, tenerne una.
