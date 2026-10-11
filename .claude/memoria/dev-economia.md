# Memoria di dev-economia

## Aggiornata
11/10/2026 · ramo `feat/giro-eco` (da main `0e7753a`), DB `iyokai_weco`, migrazioni usate 0030, 0031

## In corso
- Giro eco chiuso a 3 voci (9.18, NF-15, NF-12). Resta: smoke con nohup, push del ramo, rapporto.
- Prossimo giro: voci piccole #124/#125 (LIV-064..067 XP a mano, LIV-005 livello massimo,
  ECO-009 monete a mano, ECO-069 conferma acquisto), `/clan` voce worker batch, GDPR rank_card_prefs.

## Fatto
- F1 livelli+economia+clan: unito (`9db9e8a`, migrazioni 0015-0019). 9.1-9.17 verificate fatte.
- #135 clan atomico, #136 config export, F7 passo 3a (/level, /clan), #146 boost per tipo (0020): uniti o in attesa.
- Giro eco: 9.18 (PERF-4/6) `589c29c`; NF-15 #86 `7ff9990` (0030, `/level impostazioni`);
  NF-12 #83 rank card (0031, `core/rank_card_image.py`, `/level rank` con defer).

## Cose imparate
- Ordine dei blocchi: membro -> leveling_totals -> clans; `set_member_role` blocca prima il membro.
- Saldi condizionati nel database; pagamento + effetto = una transazione con `FOR UPDATE`.
- Boost D23: `buy_*_boost` restituiscono `EsitoBoost`; mai somma delle durate.
- `set_member_role(..., max_with_role=)` controlla il tetto sotto blocco; restituisce `EsitoRuolo`.
- `tests/test_repository_callers.py`: ogni metodo di repo ha un chiamante di produzione (anche
  interno al repo); tolto il vecchio, si aggiorna il test. `spend_coins_in(conn, ...)` si riusa.
- Test di concorrenza: `apri_connessioni(pool)` prima di `asyncio.gather`.
- Fixture a generatore: `_get_wrapped_function()()`; test che registrano moduli premium usano `utility`.
- F7: comandi di `CogConGruppi` non sono `app_commands.Command`: nei test
  `registra_comandi_del_cog(cog, gruppi=costruisci_gruppi(), tree=None)` (nome "level impostazioni xp").
  `cog.metodo.callback(cog, ...)` vale. `cog_unload` sincrono; test con `add_cog` finiscono con `remove_cog`.
- Fixture che crea `LevelingCog(bot=None)` deve essere `async def` (il task parte nel costruttore).
- SQL `round()` arrotonda il mezzo in su, Python `round()` al pari: il decadimento in SQL usa
  `2*round(x/20)` se `x%10=5`; il test confronta con la funzione pura su 600 saldi.
- `leveling_repo` importa la cassa solo dentro il metodo (la cassa importa `add_coins_in`).
- NF-15: `leveling_settings_repo.get_config` ha cache di 60 s, invalidata da `set_*`/`remove_rule`;
  il cog usa `_config()` che ricade sui valori di base se il database non risponde. Tetto 25 regole per tipo.
- Un listener che legge `message.channel.id` rompe i finti senza `id`: i test con `_FakeChannel` lo aggiungono.
- Rank card: Pillow in `run_image_task`, avatar con `safe_open_image`, ricade sull'embed se il disegno fallisce.

## Aperto
- Colonne `boost_expires_at`/`guild_boost_expires_at` nel database, non usate.
- Senza `DATABASE_URL` esportato i test usano `iyokai_test` (condiviso): esportarlo sempre.
- `tests/support/command_policy.py`: riga `"gestione"` (se la aggiungono altri, tenerne una).
- `core/guild_clan_voice_worker.py`: ~6 query per utente a ogni tick (PERF-4 non chiusa lì).
- `rank_card_prefs` (user_id) non è ancora nel flusso GDPR di cancellazione (non c'è ancora per `leveling_totals`).
- Rank card: sfondo con immagine propria (premium) non fatto; `/daily` e `/work` hanno importi fissi.
