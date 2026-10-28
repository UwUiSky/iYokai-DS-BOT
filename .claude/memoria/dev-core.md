# Memoria di dev-core

## Aggiornata
27/10/2026 · ramo `feat/r10core` · giro r10 (chiudere le voci [~]; migrazioni 0360-0369)

## In corso
- Giro r10 chiuso (B.3, B.4, #113 webhook D33, 0360-0361). Test dei file toccati verdi. Smoke da fare (regola owner: non lanciato).
- Prossimo: owner radio max_length (file musica, altra area); 21.1 per cog di altre aree; #70 voci continuo/F8.

## Fatto
- Giri precedenti (R1-bis, smoke, F7 quadro, NF-04 privacy/GDPR 0034-0036/0050, #148 permessi 0039, #145 premium_cache, M 13.1-13.3,
  M 14.1-14.12, 14.15): vedi `git log` e il registro delle risolte. Giro 12/10 bis e 12/10: revisioni su privacy, scheduler, OAuth.
- r5 g1-3 (6d0e6f6, 4379e18, 5add20b): `locales/it|en.json`, `core/i18n.py`, `user_language` 0130, `/utility lingua`;
  `core/command_translator.py` + `locales/comandi.en.json`; ricerca bilingue + `filtra_per_moduli`.
- r5 g4-7 (0ecc8ff, 8a38d4e, c5033ef, 0c08903): `core/command_policy.py` + `/utility politica`; `config_history` filtri/CSV;
  `/admin config pulizia|sincronizza|nickname-bot`, `/utility info`; NF-22 `premium_entitlements` 0131 + `/admin premium stato`;
  codici 0132 (`/owner premium grant` senza server crea il codice, `/admin premium riscatta`); NF-38 0133 `whitelabel_bots` +
  `/admin premium marchio`; #141 `core/hot_patch.py` 0134 (`/owner cog reload commit|file|registro`, `ENABLE_HOT_PATCH`).

- r9 #94 NSFW: `core/nsfw_*` (filtro, fonti RedGifs, servizio D16, worker, bot), cogs/nsfw/ricerca.py, 0240, test_nsfw_*.
  #107: `core/user_app_bot.py`, `core/user_app_logic.py`, cogs/user_app/personal.py; -cerca-comando/-chiedi user-install.

- r10 g1: wizard `cogs/utility/_setup_wizard_views.py` + `core/setup_wizard_logic.py` (costruisci_passi): passo ruoli (imposta_ruolo) e una categoria per passo, bottone «Crea i canali dei log» = callback di `/log crea-canali`.

- r10: `core/premium_modulo_service.py`, `core/bot_inviti.py`, marchio: `inoltra_interazioni` (parsers INTERACTION_CREATE -> stato del principale).
- r10 g2: B.3/B.4 (`core/user_app_strumenti.py`, 0360); log via webhook `core/log_webhook.py` + 0361 + hook in `channel_router.destinazione` (D33).

## Cose imparate
- `View.clear_items()` stacca i figli: dentro un callback tenere `vista = self.view` prima di ricostruire.
- Alberi separati (NSFW, App): `tests/support/full_tree.build_separate_trees`; cogs con setup no-op se non e la loro istanza.
- Server senza il bot (app utente): `interaction.is_guild_integration()` falso; `guild` None anche per cache mancante (#147).
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
- Colonna con id di un bot (non persona) non si chiama `*_user_id`: il test del registro dati la vuole dichiarata (usa `bot_account_id`).
- Comando staff dentro un gruppo pubblico (`utility`): `@richiedi(Livello.ADMIN)` su ogni comando + `@autocomplete_protetto`.
- Migrazione applicata e poi rinominata: `delete from schema_migrations where version=N` e drop della tabella nel DB di prova.
- `monkeypatch.undo()` in un test con `clean_db` annulla anche il pool: ripristinare il singolo attributo.
- Il token OAuth, gli state e i corpi delle risposte Discord non vanno mai in log o messaggi.

## Aperto
- NSFW: risposta RedGifs scritta a memoria (verified/tags/niches/urls.poster), da controllare live. nsfw_* si puliscono
  solo se il server ha `guild_presence` del principale: un server con solo il bot NSFW non scade mai.
- `tests/test_premium_invalidazione.py` (vecchio) assegna `db._pool` in un test: da togliere.
- Conteggio caratteri: `admin` 6.4xx su 6.800 (soglia): il prossimo comando admin richiede un nuovo gruppo (D25) o va in un gruppo piu leggero.
- #136 (`/config export` null), #141 e #138 (giri a parte), #135 `reset_premium_registry`.
- 14.13 codice morto (continuo), 14.14 lingue (F8). KNOWN_SENZA_MAX_LENGTH: 27 voci in cogs di altre aree.
- Clan sciolto dalla cancellazione: categoria/canali Discord restano da togliere a mano.
- Worker musicale da solo non controlla la blacklist all'ingresso (solo il principale).
