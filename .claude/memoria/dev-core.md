# Memoria di dev-core

## Aggiornata
23/11/2026 · ramo `feat/r1doc` · controllo delle 89 voci solo nei documenti (D119): 44 esistono o fatte, 10 non fatte con motivo, 35 da fare (18 «grandi»).

## In corso
- r1doc (ramo `feat/r1doc`, da unire): tocca `core/migrations/0850-0852`, `core/data_registry.py`, `core/risposte_server.py`, `core/monthly_winners_announcer.py`, `cogs/leveling/leveling.py`, `cogs/voice_temp/voice_temp.py`, `cogs/music/player.py`. Smoke da fare dopo l'unione: tree_invariants (peso `admin-livelli`), risposte_server, config_import, leveling_repo/classifica/card/settings, progressi, profiles, top_settimanale, voice_azioni_ruoli, music_queue_cmds, citazioni, user_app, data_registry, migrazioni 0850-0852, i18n.
- Prossimo passo r1doc (tabella in `CONTROLLO_AREE_CHIUSE.md`): ECO-006, ECO-050, ECO-160, VOC-014, MUS-016, RUO-005, CFG-044, UTL-111, SIC-021 (medie); poi i «grandi»: reputazione LIV-076…088, modulo voto (LIV-019, ECO-048/049, CFG-039), SIC-016, UTL-024, TKT-073/088, ECO-080.
- Restano da giri vecchi (smoke già in coda): r1dep (#161), r1cfg (#122: CFG-024 con dev-moderazione, 036/039/040/041 scelte dell'owner, 001/002/003/006/027 dev-web, 032 marchio), r15immagini (`/admin-automod immagini` da agganciare a `core/automod_azioni.py`), r14lingue, r14lunghezze, r13ruoli. #67: 11.11, 11.12. #70: 14.10, 14.12-14.14.
- Rimandato: persistenza/pannello dei livelli (D57), permessi per ruolo dal pannello (OAuth), nascondere `/founder` agli admin.

## Fatto
- r1doc (D119): LIV-013 (0850 `xp_testo`/`xp_vocale`), 046 (0852), 053 (`core/sfondi_pronti.py`), 061 (0851, `tick_settimanale`), 090, 091; CFG-011; VOC-017 (`core/voice_azioni_ruoli.py`); MUS-043; FUN-030; AI-022; 33 voci già fatte segnate col codice nel test.
- r1cfg (D96, #122): `core/risposte_server.py` (+ `config_risposte.py`), `policy_ruoli_richiesti` in `command_policy.py` (+ `politica ruolo-richiesto`), `core/permessi_vista.py` (+ `config_permessi.py`), `lingua_iniziale_del_server`, `core/premium_posti_service.py` (0720, `/owner premium grant utente: posti:`, `premium assegna|togli-posto`), `core/config_trasloco.py` (import senza ID stranieri).
- r15immagini (D62, #153): `core/immagini_*` (byte, quarantena, sandbox un processo per immagine, coda 100/20, dHash, QR zxing-cpp 3.1.1, libreria trappola D39, pipeline, opzioni D16, azioni), cog `cogs/automod/immagini.py`, `/owner immagini-trappola`, 0504-0506, `deploy/systemd/iyokai-sandbox.service`, `docs/immagini-sandbox.md`, testi `amimg_*`.
- r14lingue (D58, #77): `locales/<lingua>/testi.json`+`comandi.json` (10 lingue Discord, 8 vuote), ripiego lingua->en-US->it, `core/lingue_controllo.py` + 2 script, bottone «Chiedi una lingua» in `/utility lingua` (`core/lingua_richieste.py`), `aiuto` in comandi.json letto da cerca-comando, peso 8000 su tutte le lingue.
- r13ruoli (D60): 25 gruppi staff (`admin-*` 20, `mod-*` 4, `founder`), 377 percorsi spostati; `Livello.FOUNDER`;
  `PREFISSI_SEMPRE_APERTI=("admin-bot","owner")`; migrazione 0488; `GRUPPI_DEL_RUOLO` dai prefissi; traduzioni en.
- r13gruppi (D56/D57): 152 comandi spostati, 11 gruppi, 0485-0487, `core/livelli_funzione.py`.
- Giri precedenti (r12, r10, r9, r5, F5/F7, R1-bis): vedi `git log`.

- r1collaudo (#94, D109): `scripts/collaudo.py` (assistente prove dal vivo, terminale separato), `core/collaudo_avviso.py`, avviso in `main.py` con COLLAUDO=1; test `tests/test_collaudo.py`.
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
- Il codice di una voce nel test conta come «fatta» per `scripts/stato_catalogo.py`: mai metterlo su una voce non fatta. Una descrizione di opzione ≤ 95 caratteri (test tree_invariants). Scelte lunghe: autocompletamento, non `choices` (pesa nel gruppo, D56).
- Con tanti test su DB condiviso una prova di 25 file dura 30+ minuti: lanciarla in background e scrivere i documenti nel frattempo; non attendere con `pgrep -f` (si trova da solo).

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
