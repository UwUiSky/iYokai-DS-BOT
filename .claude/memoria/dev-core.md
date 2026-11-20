# Memoria di dev-core

## Aggiornata
18/11/2026 · ramo `feat/r1cfg` · #122 catalogo configurazione (D96): fatte 013, 014, 033, 012, 022, 023, 025, 026, 029, 034, 035, 043 (+ provate 007, 028, 031, 037, 042, 045).

## In corso
- r1cfg pubblicato (Refs #122). Tocca `main.py` (on_guild_join), `core/database.py` (ensure_guild_exists con lingua), `core/blacklist_tree.py`, `core/premium.py`, import/export: serve la suite completa dell'orchestratore. Smoke da fare dopo l'unione (risposte, politica, permessi_vista, premium_posti, config_trasloco, import, migrazione 0720, data_registry, tree_invariants, i18n). Restano per #122: CFG-024 (con dev-moderazione), 015/016/017/044 (altre aree), 036/039/040/041 (scelte dell'owner), 001/002/003/006/027 (dev-web), 032 (marchio: resincronizza e registro errori).
- r15immagini pubblicato. Smoke da fare dopo l'unione (test_immagini_*, tree_invariants, data_registry, migrazioni 0504-0506, i18n, config_import). Da fare dopo il merge col filone A: `/admin-automod immagini` e aggancio a `core/automod_azioni.py` (oggi `cogs/automod/immagini.py::_applica` usa bot_roles/try_dm/post_to_mod_log).
- r14lingue (D58) pubblicato. Smoke da fare dopo l'unione (i18n, translator, command_sync, tree_invariants, riferimenti, cog utility/lingua).
- r14lunghezze pubblicato. Smoke da fare dopo l'unione (tree_invariants, cog feed_alerts, fun, mod-ban, messaggi programmati, radio).
- Restano #67: 11.11 (hash token webhook, migrazione, F5), 11.12 (F13). #70: 14.10, 14.12, 14.13, 14.14 (non piccoli).
- r13ruoli chiuso e pubblicato. Smoke da fare dopo l'unione (0488, command_permissions/access/groups/policy).
- Rimandato: persistenza/pannello dei livelli (D57), permessi per ruolo dal pannello (OAuth), nascondere `/founder` agli admin.

## Fatto
- r1cfg (D96, #122): `core/risposte_server.py` (+ `config_risposte.py`), `policy_ruoli_richiesti` in `command_policy.py` (+ `politica ruolo-richiesto`), `core/permessi_vista.py` (+ `config_permessi.py`), `lingua_iniziale_del_server`, `core/premium_posti_service.py` (0720, `/owner premium grant utente: posti:`, `premium assegna|togli-posto`), `core/config_trasloco.py` (import senza ID stranieri).
- r15immagini (D62, #153): `core/immagini_*` (byte, quarantena, sandbox un processo per immagine, coda 100/20, dHash, QR zxing-cpp 3.1.1, libreria trappola D39, pipeline, opzioni D16, azioni), cog `cogs/automod/immagini.py`, `/owner immagini-trappola`, 0504-0506, `deploy/systemd/iyokai-sandbox.service`, `docs/immagini-sandbox.md`, testi `amimg_*`.
- r14lingue (D58, #77): `locales/<lingua>/testi.json`+`comandi.json` (10 lingue Discord, 8 vuote), ripiego lingua->en-US->it, `core/lingue_controllo.py` + 2 script, bottone «Chiedi una lingua» in `/utility lingua` (`core/lingua_richieste.py`), `aiuto` in comandi.json letto da cerca-comando, peso 8000 su tutte le lingue.
- r13ruoli (D60): 25 gruppi staff (`admin-*` 20, `mod-*` 4, `founder`), 377 percorsi spostati; `Livello.FOUNDER`;
  `PREFISSI_SEMPRE_APERTI=("admin-bot","owner")`; migrazione 0488; `GRUPPI_DEL_RUOLO` dai prefissi; traduzioni en.
- r13gruppi (D56/D57): 152 comandi spostati, 11 gruppi, 0485-0487, `core/livelli_funzione.py`.
- Giri precedenti (r12, r10, r9, r5, F5/F7, R1-bis): vedi `git log`.

## Cose imparate
- `interaction.response` e `followup` sono `cached_slot_property`: si sostituiscono con `interaction._cs_response` / `_cs_followup` (sottoclassi di `InteractionResponse` e `Webhook`); le `__slots__` vietano altri attributi.
- `SETTINGS_SCHEMA` nuovo = anche `SETTINGS_VALIDE` in `tests/test_config_import_validation.py`. L'import ora scarta gli ID che non esistono nel server (guild finto: `roles` e `get_channel`).
- In sviluppo `PREMIUM_ALPHA_UNLOCK_ALL` è vero: i test del premium sostituiscono `core.premium.config` (vedi `test_premium_posti.py`).
- La macchina è condivisa con altri agenti: le prove di `tree_invariants` e i18n possono durare 3-4 minuti. `test_riferimenti_comandi` fallisce per `/rss` in `core/alert_piattaforme_logic.py` (non è di quest'area).
- Sandbox: con `-I` la cartella dello script non è in sys.path (il worker la aggiunge); RLIMIT_FSIZE=0 manda SIGXFSZ (ignorato + `-B`); `unshare -rn` provato una volta. Un test non usa `tests/test_data_registry` su DB sporco: tabelle di altri rami (`verify_*`) lo fanno fallire.
- Lingue: codice salvato nel DB `it`/`en` (CHECK 0130); `en`/`en-GB` sono alias di `en-US`; testo vuoto = da tradurre (ignorato). `lingua_valida` = solo lingue con testi.
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
- Lingue: tetto richiesta giornaliero in memoria (si azzera al riavvio); lingua personale ammette solo it/en finché una migrazione non allarga il CHECK di `user_language`; `aiuto` vuoto in tutte le lingue.
- `/admin-ai` 19 figli (KNOWN_OLTRE_18), `/admin-antiraid` 17: al prossimo comando si dividono.
- `/admin-ruoli`: Discord `manage_roles`, codice `Livello.ADMIN` (`manage_guild`): chi ha solo «Gestisci ruoli» lo vede
  ma è rifiutato (D60 punto 4, da decidere).
- NSFW: risposta RedGifs scritta a memoria, da controllare live; server con solo il bot NSFW non scade mai.
- `tests/test_premium_invalidazione.py` assegna `db._pool`: da togliere.
- #136, #141, #138, #135. 14.13 codice morto, 14.14 lingue (F8). KNOWN_SENZA_MAX_LENGTH vuoto: ogni opzione nuova senza Range fa fallire il test.
- Clan sciolto: categoria/canali restano da togliere a mano. Worker musicale non controlla la blacklist all'ingresso.
- `/assistente` esiste anche in iYokai App: i test dei riferimenti danno la precedenza al principale.
