# Memoria di dev-core

## Aggiornata
11/10/2026 · ramo `feat/giro-core` (da main) · giro #70/#69/#145/#148/NF-04

## In corso
- Giro quasi chiuso. Resta: suite completa (la fa l'orchestratore), rapporto, push del ramo.
- Se si riprende: #148 manca l'indirizzo di ritorno OAuth2 (web) e il bottone nel setup (prova live).

## Fatto
- Giri precedenti: R1-bis, smoke, F7 quadro e passo 4 (gruppi, accesso, sync comandi).
- #145 `core/premium_cache.py` (db whitelist, abbonamenti, acquisto cassa, flag modulo).
- M 14.2/14.3 gestore errori. M 14.4 scheduler con `claimed_at` (0033). M 14.6 pool 2/5 in sviluppo.
- M 14.7 `core/invio_file.py`. M 14.9 coda `bot_stats` con tetto, cache moduli senza gara.
- M 14.10 cache impostazioni (`db._settings_cache`, TTL 60 s). M 14.1 cricchetto `KNOWN_SENZA_MAX_LENGTH`
  (27 rimasti, 16 owner sistemati). M 14.11 `event_log.id` BIGINT + indici (0037). M 14.12 chiavi esterne clan/giveaway (0038).
- M 13.2 `core/blacklist_exit.py` (escono i worker musicali).
- NF-04: `data_registry` (87 tabelle), `forget_user_service`, `retention_worker`, repo presenza/richieste, cog `privacy`,
  migrazioni 0034-0036, `on_guild_remove`. #19/#37/#46 chiusi dallo stesso codice.
- #148 parte senza token: `core/command_permissions.py`, tabella `command_permission_tokens` (0039), hook `imposta_ruolo`.
- Gia fatte: 13.1 (sotto-gruppi owner), 13.3, 14.5, 14.8, 14.15.

## Cose imparate
- La suite completa dura circa 9 minuti. `config` e un dataclass congelato: nei test si sostituisce `ca.config`.
- Rifiuto di accesso = `AccessoNegato` (CheckFailure) risposto da `handle_app_command_error`.
- Il defer pubblico lascia un messaggio con flag `loading`: va cancellato prima del followup effimero.
- Cache impostazioni: test con SQL grezzo su guild_config devono fare `db._settings_cache.clear()` (clean_db lo fa).
- Ogni tabella nuova va in `core/data_registry.py`: il test di completezza legge lo schema vero e fallisce.
- Ogni colonna `user_id`/`owner_id`/`*_by` nuova va dichiarata (colonne_utente o colonne_attore).
- Migrazioni gia applicate in un DB di prova non si rieseguono se le modifichi: cancella la riga da schema_migrations.
- Una chiave esterna nuova rompe i test di altre aree che inseriscono righe orfane: controllare prima.
- discord.py: per le stringhe il massimo sta in `Parameter.max_value`.
- Il token OAuth, gli state e i corpi delle risposte Discord non vanno mai in log o messaggi.

## Aperto
- #136 (`/config export` null), #141 e #138 (giri a parte), #135 `reset_premium_registry`.
- 14.13 codice morto (continuo), 14.14 lingue (F8). KNOWN_SENZA_MAX_LENGTH: 27 voci in cogs di altre aree.
- Worker musicale da solo non controlla la blacklist all'ingresso (solo il principale).
