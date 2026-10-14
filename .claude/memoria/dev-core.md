# Memoria di dev-core

## Aggiornata
14/10/2026 · ramo `feat/r5-cor` (base main) · giro r5: per FILE

## In corso
- Giro r5 (7 gruppi): FATTI 1-3 (lingue, traduttore comandi, ricerca bilingue). Restano: (4) #122 piccole, (5) NF-22 diritti astratti,
  (6) NF-38 marchio, (7) #141 stato/controllo/riavvio in `/owner system`. Poi registro #19/#37/#46/#138, push, rapporto.
- Prossimo passo: gruppo 4 (CFG-004/005 storico filtri+CSV in config_history, CFG-019/020/021/046, CFG-038 codici premium).
- Non faccio: #140 (serve snodo AI #95 + token GitHub), 14.1 (restano cogs altrui), 21.6 (cogs altrui).

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
- Giro 12/10 bis (revisore-capo): Range privacy 2**53-1 + test limiti interi, cancellazione tiene solo lo sban programmato,
  ramo CommandOnCooldown, `esci_dettaglio` (falliti detti all'owner), token OAuth cancellato in on_guild_remove,
  bottone-link in `/admin setup attiva`, `invia_file_su_interazione` (config export, parole vietate), test mutazione.
- Giro 12/10: contatore casi ricostruito dopo la purga (`dopo_purga_server`), `sincronizza`/`segna_uscito` ripristinano
  `purged_at`, purga ricontrolla `left_at` con FOR UPDATE, sban programmato trattenuto (`conserva_server_se`),
  esportazione solo dell'utente + ORDER BY pk + `troncate`, titolare clan trasferito/sciolto, migrazione 0050
  (retain_for_security con automod_escalation e mute_role; indice ticket senza user_id=0), rinnovo OAuth (solo
  invalid_grant cancella, lock per server), state monouso + callback `/oauth/callback` condivisa (`gestisci_callback`),
  scheduler libera `claimed_at` se cancellato, cache log avanzati con numero di versione.
- Gia fatte: 13.1 (sotto-gruppi owner), 13.3, 14.5, 14.8, 14.15.

- r5 g1-3 (6d0e6f6, 4379e18, 5add20b): `locales/it|en.json`, `core/i18n.py` (lingua_risposta/interazione), `user_language` 0130,
  `/utility lingua`; `core/command_translator.py` + `locales/comandi.en.json` (447 nodi), sync con impronta tradotta, COMMAND_LIST_ITA/ENG;
  ricerca bilingue + `filtra_per_moduli`.

## Cose imparate
- Discord conta per il limite 8000 solo la traduzione PIU LUNGA per campo (base compresa). Base del codice resta italiano (scarto da D1).
- discord.py mette locale_str automatico su nomi/descrizioni: il traduttore riceve `context.data` (nodo) e risponde per percorso.
- Il DB di prova puo essere usato anche da altre copie: tabelle estranee (es. activity_*) fanno fallire test_data_registry; riprovare.
- La suite completa dura circa 9 minuti. `config` e un dataclass congelato: nei test si sostituisce `ca.config`.
- Rifiuto di accesso = `AccessoNegato` (CheckFailure) risposto da `handle_app_command_error`.
- Il defer pubblico lascia un messaggio con flag `loading`: va cancellato prima del followup effimero.
- Cache impostazioni: test con SQL grezzo su guild_config devono fare `db._settings_cache.clear()` (clean_db lo fa).
- Ogni tabella nuova va in `core/data_registry.py`: il test di completezza legge lo schema vero e fallisce.
- Ogni colonna `user_id`/`owner_id`/`*_by` nuova va dichiarata (colonne_utente o colonne_attore).
- Migrazioni gia applicate in un DB di prova non si rieseguono se le modifichi: cancella la riga da schema_migrations.
- Una chiave esterna nuova rompe i test di altre aree che inseriscono righe orfane: controllare prima.
- discord.py: per le stringhe il massimo sta in `Parameter.max_value`.
- Un test che esegue una migrazione a mano su `clean_db` sporca il DB condiviso (es. 0010 rimette l'indice vecchio): ripristinare nel finally.
- Esportazione: mai `colonne_attore`; i campi con id di staff escono None. Nuova colonna di stato in un cog che scrive casi: aggiornare 0050-style e il test AST degli action_type.
- Numeri migrazione: mod usa 0040-0041; core ha preso 0050 (verificare la scheda prima della prossima).
- Il token OAuth, gli state e i corpi delle risposte Discord non vanno mai in log o messaggi.

## Aperto
- #136 (`/config export` null), #141 e #138 (giri a parte), #135 `reset_premium_registry`.
- 14.13 codice morto (continuo), 14.14 lingue (F8). KNOWN_SENZA_MAX_LENGTH: 27 voci in cogs di altre aree.
- #148: manca solo il picker dei ruoli che chiama `imposta_ruolo` (il link e la callback ci sono).
- Clan sciolto dalla cancellazione: categoria/canali Discord restano da togliere a mano.
- Worker musicale da solo non controlla la blacklist all'ingresso (solo il principale).
