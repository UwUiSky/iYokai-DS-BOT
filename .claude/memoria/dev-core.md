# Memoria di dev-core

## Aggiornata
01/11/2026 · ramo `feat/r13ruoli` · D60 applicata; revisione fatta (fix del revisore: comandi vicini, nomi vecchi in cerca-comando, riferimenti).

## In corso
- r13ruoli chiuso e pubblicato. Smoke da fare dopo l'unione (0488, command_permissions/access/groups/policy).
- Rimandato: persistenza/pannello dei livelli (D57), permessi per ruolo dal pannello (OAuth), nascondere `/founder` agli admin.

## Fatto
- r13ruoli (D60): 25 gruppi staff (`admin-*` 20, `mod-*` 4, `founder`), 377 percorsi spostati; `Livello.FOUNDER`;
  `PREFISSI_SEMPRE_APERTI=("admin-bot","owner")`; migrazione 0488; `GRUPPI_DEL_RUOLO` dai prefissi; traduzioni en.
- r13gruppi (D56/D57): 152 comandi spostati, 11 gruppi, 0485-0487, `core/livelli_funzione.py`.
- Giri precedenti (r12, r10, r9, r5, F5/F7, R1-bis): vedi `git log`.

## Cose imparate
- Riordino per script: regex dei riferimenti con `(?![\w/])` dopo il nome (altrimenti riscrive gli URL `/ai/altro`);
  offset AST in byte. I riferimenti senza `/` (tabelle di percorsi come `COMANDI_VICINI`, chiavi, `get_command("x")`)
  e i sotto-comandi già vecchi prima (es. `/security antinuke`) non li trova nessun test: grep a parte, poi i test di quei file.
- Nomi di prima di D60: tabella unica nella migrazione 0488 (letta da `command_search_logic` e `tests/support/percorsi.py`).
- Un cog con `CogConGruppi` e `cog_load`/`cog_unload` propri chiama `super()`: senza, i comandi spariscono.
- Comando staff in un gruppo pubblico: `@richiedi(Livello.X)` + `@autocomplete_protetto` con lo stesso livello.
- Discord conta per gli 8.000 solo la traduzione più lunga per campo; discord.py passa `context.data` al traduttore.
- Ogni tabella nuova in `core/data_registry.py`; ogni colonna `user_id`/`*_by` dichiarata; id di un bot = `bot_account_id`.
- Migrazione già applicata nel DB di prova: non si riesegue se cambia; togliere la riga da `schema_migrations`.
- Test che eseguono una migrazione a mano su `clean_db` sporcano il DB condiviso: ripristinare nel finally.
- Cache impostazioni: SQL grezzo su guild_config richiede `db._settings_cache.clear()`.
- `monkeypatch.undo()` con `clean_db` annulla anche il pool: ripristinare il singolo attributo.
- Server senza il bot (app utente): `is_guild_integration()` falso; `guild` None anche per cache mancante (#147).
- `View.clear_items()` stacca i figli: tenere `vista = self.view` prima di ricostruire.
- Viste con select: `interaction.data = {"values": [...]}`; `fake_member.premium_since` va messo a None.
- Rifiuto di accesso = `AccessoNegato` risposto da `handle_app_command_error`; il defer pubblico lascia un `loading`.
- Test a metà su due DB: `iyokai_wruoli` e `iyokai_wruoli2`.

## Aperto
- `/admin-ai` 19 figli (KNOWN_OLTRE_18), `/admin-antiraid` 17: al prossimo comando si dividono.
- `/admin-ruoli`: Discord `manage_roles`, codice `Livello.ADMIN` (`manage_guild`): chi ha solo «Gestisci ruoli» lo vede
  ma è rifiutato (D60 punto 4, da decidere).
- NSFW: risposta RedGifs scritta a memoria, da controllare live; server con solo il bot NSFW non scade mai.
- `tests/test_premium_invalidazione.py` assegna `db._pool`: da togliere.
- #136, #141, #138, #135. 14.13 codice morto, 14.14 lingue (F8). KNOWN_SENZA_MAX_LENGTH: 27 voci di altre aree.
- Clan sciolto: categoria/canali restano da togliere a mano. Worker musicale non controlla la blacklist all'ingresso.
- `/assistente` esiste anche in iYokai App: i test dei riferimenti danno la precedenza al principale.
