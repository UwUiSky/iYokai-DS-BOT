# Memoria di dev-core

## Aggiornata
11/10/2026 · ramo `feat/giro-core` (da main) · giro #70/#69/#145/#148/NF-04

## In corso
- Previsione: 10+ voci. Chiuse: #145, M 14.2, 14.3, 14.4, 14.6, 14.9, 14.10.
- Prossimo: M 14.7 (`core/invio_file.py`), 13.2 (blacklist: escono anche i worker musicali),
  poi NF-04 (migrazioni 0034-0037: guild_presence, retain_for_security, data_deletion_requests,
  event_log BIGINT+indici; `data_registry`, `forget_user_service`, `retention_worker`, cog `privacy`,
  hook `on_guild_remove` in main.py), 14.1 (cricchetto max_length), 14.5, 14.8, #148 (valutare).

## Fatto
- Giri precedenti: R1-bis, smoke, F7 quadro e passo 4 (gruppi, accesso, sync comandi).
- #145: `core/premium_cache.py` (punto unico), chiamato da db whitelist, abbonamenti, acquisto cassa, flag modulo.
- M 14.2/14.3: `handle_app_command_error` (rifiuti = INFO; segnaposto del defer pubblico cancellato).
- M 14.4: scheduler con prenotazione `claimed_at` (migrazione 0033), nessuna connessione durante l'handler.
- M 14.6: pool 2/5 in sviluppo. M 14.9: coda `bot_stats` con tetto, cache moduli senza gara.
- M 14.10: cache impostazioni per server (`db._settings_cache`, TTL 60 s, `clean_db` la svuota).
- Gia fatte: 13.1 (sotto-gruppi owner premium/blacklist/cog/system; mancano privacy/radio/ai), 13.3, 14.15.

## Cose imparate
- La suite completa dura circa 9 minuti. `config` e un dataclass congelato: nei test si sostituisce `ca.config`.
- Rifiuto di accesso = `AccessoNegato` (CheckFailure) risposto da `handle_app_command_error`.
- Autocomplete sotto gruppi protetti: `autocomplete_protetto(livello)`; sotto-gruppi: `GruppoYokai`.
- Test su guild_config con SQL grezzo: dopo una lettura la cache impostazioni puo essere vecchia; usare `db._settings_cache.clear()`.
- Il defer pubblico lascia un messaggio con flag `loading`: va cancellato prima del followup effimero.
- Le tabelle si dichiarano in `core/data_registry.py` (test di completezza sullo schema vero).

## Aperto
- #136 (`/config export` null), #141 e #138 (giri a parte), #135 `reset_premium_registry`.
- 14.12 chiavi esterne, 14.13 codice morto, 14.14 lingue (F8): non in questo giro.
