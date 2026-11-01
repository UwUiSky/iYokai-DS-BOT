# Memoria di dev-core

## Aggiornata
01/11/2026 · ramo `feat/r13ruoli` (agente r13ruoli) · D60 applicata, merge di origin/main fatto

## In corso
- r13ruoli chiuso e pubblicato. Smoke/suite da fare (migrazione 0488, `core/command_permissions.py`, `core/command_access.py`, `core/command_groups.py`, `core/command_policy.py`).
- Rimandato: alias dei nomi vecchi in `/-cerca-comando` (mappa rischio 12), persistenza/pannello dei livelli (D57), permessi per ruolo dal pannello (OAuth), nascondere `/founder` agli admin.

## Fatto
- r13ruoli (D60): 25 gruppi staff `admin-*` (20), `mod-*` (4), `founder`; 377 percorsi spostati con script AST sui decoratori (un commit per gruppo);
  `Livello.FOUNDER` (solo `guild.owner_id`); `PREFISSI_SEMPRE_APERTI=("admin-bot","owner")`; migrazione 0488 (policy, history, usage);
  `GRUPPI_DEL_RUOLO` derivato dai prefissi; traduzioni en (prefisso non tradotto); test invarianti prefisso/livello; docs (MAPPA, LIMITI, SPEC 20.9, VERIFICA_LIVE, COMMAND_LIST).
- r13gruppi (D56/D57): 152 comandi spostati, 11 gruppi nuovi, migrazioni 0485-0487, `core/livelli_funzione.py`.
- r12 (resto): jolly autoresponder, benvenuto nel router, log della scala, wizard canali, `/log vista-forum` (0480), progressi (0481-0483), rischio staff (D50).
- Giri precedenti: r10, r9, r5, F5/F7, R1-bis: vedi `git log`.

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
- Un cog con `CogConGruppi` che definisce `cog_load`/`cog_unload` deve chiamare `await super().cog_load()`: senza, i suoi comandi spariscono dall'albero (test_command_translator lo vede).
- Punti di aggancio nei repo (`event_log_repo`, `moderation_repo`, `leveling_repo`): import tardivo del servizio per evitare cicli, servizio che non solleva mai.
- Gruppo `moduli` a 6.793/6.800 caratteri: ogni parola in più nelle descrizioni lo manda sopra l'allarme.
- Gruppo `level` a 6.444/6.800: `/level progressi` e senza parametri (menu in una finestra); non aggiungere parametri a `/level`.
- Un select in una `BaseView` con bottoni che cambiano per sezione: si ricostruisce la vista a ogni cambio (`costruisci`) e si usa `edit_message`.
- Nel test di una vista con select: `interaction.data = {"values": [...]}`; `fake_member` ha `premium_since` come mock: va messo a None.
- 23.17 chiusa (D51, migrazioni 0482-0483): pass di 90 giorni da 1/1/2026, XP del pass nella colonna `progress_stagione.xp`.

- Riordino per script: la regex dei riferimenti DEVE avere `(?![\w/])` dopo il nome (senza, riscrive gli URL `/ai/altro`); l'AST usa offset in byte;
  i riferimenti senza `/` (tabelle di percorsi, chiavi di dizionari, `get_command("x")`) non li trova nessun test: grep a parte.
- `tests/support/percorsi.py` risolve i nomi di gruppo di prima di D60 dalla migrazione 0488 (compat nei test vecchi).
- Un gruppo con una sola foglia: il prefisso comune dei percorsi e la foglia intera; per le descrizioni dei sotto-gruppi serve la profondita.
- Lancio test a meta (due DB di prova in parallelo): `iyokai_wruoli` e `iyokai_wruoli_b`.

## Aperto
- NSFW: risposta RedGifs scritta a memoria (verified/tags/niches/urls.poster), da controllare live. nsfw_* si puliscono
  solo se il server ha `guild_presence` del principale: un server con solo il bot NSFW non scade mai.
- `tests/test_premium_invalidazione.py` (vecchio) assegna `db._pool` in un test: da togliere.
- Conteggio caratteri: `admin` 6.4xx su 6.800 (soglia): il prossimo comando admin richiede un nuovo gruppo (D25) o va in un gruppo piu leggero.
- #136 (`/config export` null), #141 e #138 (giri a parte), #135 `reset_premium_registry`.
- 14.13 codice morto (continuo), 14.14 lingue (F8). KNOWN_SENZA_MAX_LENGTH: 27 voci in cogs di altre aree.
- Clan sciolto dalla cancellazione: categoria/canali Discord restano da togliere a mano.
- Worker musicale da solo non controlla la blacklist all'ingresso (solo il principale).
- Riordino gruppi: i percorsi si cambiano con script sulla mappa M.json; gli offset AST sono in byte (attenzione alle lettere accentate).
- `/assistente` esiste anche in iYokai App (app diversa): i test dei riferimenti danno la precedenza al principale.
- Tra i gruppi per tutti non entra mai un comando con `@richiedi`: lo controlla test_command_groups.
- `/admin-ai` 19 figli (in KNOWN_OLTRE_18), `/admin-antiraid` 17: al prossimo comando va diviso. `/mod-ban` cercato per "ban" ora vale come parola (trattino).
