# Memoria di dev-economia

## Aggiornata
13/10/2026 · ramo `feat/r4-liv` (da main `793656c`), DB `iyokai_wliv`, migrazioni da 0090. Lavoro PER FILE (richiesta owner).

## In corso
- Previsione giro: 5 gruppi (A importi+tetto, B staff XP/monete, C NF-28 giveaway, D NF-40, E voci catalogo). Ordine fisso.
- A (NF-15 resto + docstring #65 + LIV-005) e B (`/gestione economia xp|monete`, LIV-064..067/041, ECO-009/011): fatti, smoke verde.
- E (shop: 0094, 0095) e F (`/level calcola`, classifica a 100, posizione nel saldo) fatti; smoke finale poi commit e push.
  Poi: rapporto finale (<=30 righe). Non fatto: LIV-004..009/013/017.. (XP per tipo di messaggio, servono contenuto/reazioni), ECO-004 banca, ECO-006 registro, servizi esterni (voto bot), NF-12 sfondo premium.

## Fatto
- F1 livelli+economia+clan unito (`9db9e8a`); giro eco: 9.18, NF-15 (0031), NF-12 (0032) in main.
- Giro r4: A+B `1ecd983` (0090); C giveaway `203a3af` (0091); D NF-40 `0319d95` (0092/0093); E shop+F classifiche (0094/0095, commit del giro finale).

## Cose imparate
- Migrazioni: mai modificare una già applicata al DB di prova (il runner non la rilancia): una nuova per ogni aggiunta.
- Shop: scorte e coin nella stessa transazione, scorte prima dei coin anche nel rimborso (niente stallo).
- Giochi con le monete: `leveling_repo.gioca` = una UPDATE (puntata tolta, vincita data, `WHERE coins_total >= puntata`); mai nella classifica del mese.
- Conteggio: giudizio sotto `FOR UPDATE` della riga del server; un numero uguale arrivato dopo un reset può essere giusto (non è un bug).
- Giveaway: `get_entries` tolto (test_repository_callers); si usa `get_weighted_entries`. `data_registry` vuole ogni tabella nuova (giveaway_message_counts, giveaway_templates).
- Modifiche staff (xp/monete) non contano come attività del mese: `modifica_xp/monete` scrivono solo `leveling_totals`.
- `_grant_level_rewards(..., togli_superiori=True)` toglie anche i ruoli dei livelli non più raggiunti.
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

- Blocchi: sempre `ORDER BY user_id` prima di `FOR UPDATE` (batch vocale e decadimento); righe nuove si creano vuote (`ON CONFLICT DO NOTHING`) prima di scrivere.
- `id_canali_per_le_regole`: canale, origine del thread, categoria. Esclusioni valgono anche per XP clan (testo e vocale).

## Aperto
- Giro correzioni 14/10: i comandi staff di xp, monete, shop, giveaway, cassa, vincitori stanno ora in `/economia` (D25, nessun sottogruppo, `"economia": STAFF` in command_policy). `/gestione` non li ha più.
- Migrazioni mie: 0090-0095, 0097 (ultima_partita_at), 0098 (giveaway.errore), 0099 (CHECK work_min<=work_max). NON usare 0096 (di uti, forms).
- `mark_ended` ritorna bool (rivendicazione); programmato che non parte: `segna_errore` (started=false, errore=testo), il worker lo salta; `/economia giveaway-programmati` elenca/annulla.
- `level_for_xp` in formula chiusa (isqrt); `LIVELLO_MASSIMO`=1000 per l'XP a mano; `_grant_level_rewards(esecutore=...)` applica la gerarchia dello staff.
- Test di concorrenza: `apri_connessioni` prima di `asyncio.gather`; per provare il blocco advisory a chiave singola tenere `pg_advisory_xact_lock(guild_id)` in una transazione aperta.
- Scratchpad condiviso con altri agenti: `env.sh` viene sovrascritto; usare `envliv.sh` (DATABASE_URL wliv).
- Colonne `boost_expires_at`/`guild_boost_expires_at` nel database, non usate.
- Senza `DATABASE_URL` esportato i test usano `iyokai_test` (condiviso): esportarlo sempre.
- `tests/support/command_policy.py`: riga `"gestione"` (se la aggiungono altri, tenerne una).
- `core/guild_clan_voice_worker.py`: ~6 query per utente a ogni tick (PERF-4 non chiusa lì).
- `rank_card_prefs` (user_id) non è ancora nel flusso GDPR di cancellazione (non c'è ancora per `leveling_totals`).
- Rank card: sfondo con immagine propria (premium) non fatto (dev-core).
