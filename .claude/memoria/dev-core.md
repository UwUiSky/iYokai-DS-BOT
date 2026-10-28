# Memoria di dev-core

## Aggiornata
28/10/2026 · ramo `feat/r12resto` (agente r12resto) · giro r12 (lotto «resto», migrazioni 0480-0499, D48-D50)

## In corso
- Lotto r12 chiuso nel codice; resta solo: lanciare i test degli invarianti, commit e push. Smoke da fare (lo lancia l'orchestratore).
- Rimandata a r12ai: 14.19 (voce di Yokai). Migrazioni usate: 0480 (log_forum), 0481 (progressi).
- Prossimo giro: owner radio max_length (musica); 21.1 per cog di altre aree; #70 voci continuo/F8.

## Fatto
- r12 (resto): 14.7 jolly `*` autoresponder; 18.1 benvenuto nel router (forum, `TIPO_BENVENUTO`); 18.7 log della scala (`_scrivi_nel_log`);
  22.16 wizard con bottone «Crea il canale» (`CANALI_PER_CATEGORIA`, `crea_e_collega`); 8.17 `/log vista-forum` (`core/log_forum_*`, 0480, D48);
  10.5/10.6/10.13 profili social rifiutati nei feed; 23.17 `/level progressi` + `/economia progressi` (`core/progressi_*`, 0481, D49) e
  `/mod rischio` + `/mod carico` (`core/staff_rischio_logic.py`, `staff_carico_repo`, D50). SPEC allineata (22.17, 23.8, 23.11, 13.10, 16.6, 16.10, §4, §7).
- Giri precedenti: r10 (wizard, #113 webhook, B.3/B.4), r9 (NSFW, App utente), r5 (lingue, policy, premium), F5/F7 (privacy, gruppi), R1-bis: vedi `git log`.

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
- Un cog con `CogConGruppi` che definisce `cog_load`/`cog_unload` deve chiamare `await super().cog_load()`: senza, i suoi comandi spariscono dall'albero (test_command_translator lo vede).
- Funzioni importate che iniziano con `test` (es. `testo_x`) vengono raccolte da pytest: importarle con un alias.
- Punti di aggancio nei repo (`event_log_repo`, `moderation_repo`, `leveling_repo`): import tardivo del servizio per evitare cicli, servizio che non solleva mai.
- Gruppo `moduli` a 6.793/6.800 caratteri: ogni parola in più nelle descrizioni lo manda sopra l'allarme.

## Aperto
- NSFW: risposta RedGifs scritta a memoria (verified/tags/niches/urls.poster), da controllare live. nsfw_* si puliscono
  solo se il server ha `guild_presence` del principale: un server con solo il bot NSFW non scade mai.
- `tests/test_premium_invalidazione.py` (vecchio) assegna `db._pool` in un test: da togliere.
- Conteggio caratteri: `admin` 6.4xx su 6.800 (soglia): il prossimo comando admin richiede un nuovo gruppo (D25) o va in un gruppo piu leggero.
- #136 (`/config export` null), #141 e #138 (giri a parte), #135 `reset_premium_registry`.
- 14.13 codice morto (continuo), 14.14 lingue (F8). KNOWN_SENZA_MAX_LENGTH: 27 voci in cogs di altre aree.
- Clan sciolto dalla cancellazione: categoria/canali Discord restano da togliere a mano.
- Worker musicale da solo non controlla la blacklist all'ingresso (solo il principale).
