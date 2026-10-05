# Memoria di dev-economia

## Aggiornata
05/10/2026 · ramo `fix/f1-135` (base `5c04cf5`, non unito, non pushato)

## In corso
- Niente a metà. #135 e #136 chiusi sul ramo: aspettano unione e prova dal vivo.
- Previsione del giro: 2 voci (#135 con 4 punti, #136). Fatte.

## Fatto
- F1, livelli + economia + clan: unito su main con `9db9e8a`
  (migrazioni `0015`–`0019`, `/clan lascia`, promozione a `co_owner`,
  `_pagine.py`).
- #135 clan (boost, dona, promuovi) su `fix/f1-135`: tutti e tre in un
  commit solo (repo condiviso). Test `tests/test_clan_135_scritture_atomiche.py`.
- #135 `reset_premium_registry`: salva e ripristina `is_premium_active`.
- #136 `/config export` non scrive più le voci a `null` (strada scelta).

## Cose imparate
- Ordine dei blocchi: membro -> leveling_totals -> clans (come `apply_text_tick`);
  `set_member_role` blocca prima il membro. Il contrario dà deadlock.
- `buy_member_boost`, `donate_from_member`, `set_member_role` verificano
  clan/guild/utente; `/config export` toglie null (anche in lista) e chiavi fuori schema.
- BUG-17 non esiste: c'è il test che lo prova.
- Le scritture di saldo vanno fatte condizionate nel database.
- Pagamento + effetto (scadenza boost, tesoreria) = una transazione con
  riga bloccata (`FOR UPDATE`); la scadenza si calcola sul valore letto
  sotto blocco. Due boost insieme si sommano (non uno solo).
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

## Aperto
- Boost cumulativi (48h): decisione dell'owner, chiesta dal coordinatore.
