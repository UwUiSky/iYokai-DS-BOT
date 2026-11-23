# Memoria di dev-core

## Aggiornata
23/11/2026 · ramo `feat/r1premium` (da main, NON pushato) · giro r1premium chiuso: CFG-036, 040, 041, AI-003 (D127), UTL-110.

## In corso
- r1premium finito: da unire. Tocca `core/migrations/0910-0913`, `core/data_registry.py`, `core/config.py`, `core/premium.py`, `core/livelli_funzione.py`, `core/repositories/backup_struttura_repo.py` e `ticket_form_repo.py`, `cogs/utility/scheduled_messages.py`, `backup.py`, `cogs/tickets/tickets.py`, `locales/*/testi.json`. Smoke da fare: tree_invariants (`/owner` pesa 7.898 su 8.000), data_registry, i18n, migrazioni 0910-0913, premium_*, livelli_funzione, ticket_form, backup, scheduled_messages.
- Prossimo numero migrazione libero nel blocco: 0914 (il blocco finisce a 0919). Prossimo passo: collegare il router AI a `ai_chiavi_proprie.chiave_per` (custode-ai); pannello web: collegamento Patreon (`patreon_service.crea_stato`, `url_collegamento`, `scollega`) e livelli/limiti/prezzi.
- r1med (`feat/r1med`, da unire): resta TKT-073 (Drive). r1doc (`feat/r1doc`, da unire): vedi `git log`; smoke in coda.
- Restano: r1dep (#161), r1cfg (CFG-024 con dev-moderazione, 001/002/003/006/027 dev-web), r15immagini (`/admin-automod immagini` da agganciare), #67 11.11, 11.12; #70 14.10, 14.12-14.14.
- Rimandato: permessi per ruolo dal pannello (OAuth), nascondere `/founder` agli admin.

## Fatto
- r1premium (D59, D124, D127): `core/piani.py` (livelli, concessioni, limiti, prezzi, sconti), `ai_chiavi_proprie.py`, `piani_comandi.py`, `everyone_programmati.py`, `patreon_logic/service/server.py` + cog `utility/patreon.py`; `/owner premium piano`, `/admin-bot premium chiave`; test `test_piani`, `test_patreon`, `test_everyone_programmati`.
- r1med: LOG-029 e 15 voci (0880-0888, D121). r1doc: LIV-013/046/053/061/090/091, CFG-011, VOC-017, MUS-043, FUN-030, AI-022.
- r1cfg (D96), r15immagini (D62), r14lingue (D58), r13ruoli (D60), r13gruppi (D56/D57), r1collaudo (D109): vedi `git log`.

## Cose imparate
- Il livello di un server o di una persona passa solo da `piani.livello_server/livello_utente`; il limite di un modulo da `piani.limite_server_sicuro` (torna al predefinito se il database non risponde). `registra_bot` dà il bot ai repository.
- `livelli_funzione`: VIP5/VIP20 sono alias di ULTRA/VIP (valori `ultra`, `vip` nel database dalla 0910).
- `/owner` è a 7.898 su 8.000: un comando nuovo lì va dentro `piani` o in un altro gruppo. Scelte di un'opzione: autocompletamento, non `choices` (pesano).
- Un testo per l'utente fuori dai cog passa da `t(chiave, ...)` passato come parametro (come `esegui_chiave`): il test i18n cerca frasi nei cog.
- Test del webhook: `webhook_rate_tracker._data.clear()` prima, il contatore è globale.
- `interaction.response` e `followup` sono `cached_slot_property`: si sostituiscono con `interaction._cs_response` / `_cs_followup`.
- `SETTINGS_SCHEMA` nuovo = anche `SETTINGS_VALIDE` in `tests/test_config_import_validation.py`.
- In sviluppo `PREMIUM_ALPHA_UNLOCK_ALL` è vero: i test premium sostituiscono `core.premium.config`.
- La macchina è condivisa: tree_invariants e i18n durano 3-4 minuti; `/rss` in `alert_piattaforme_logic` fa fallire `test_riferimenti_comandi` (non nostro).
- Lingue: `en`/`en-GB` alias di `en-US`; `testi.json` si riscrive con `json.dumps(indent=2, ensure_ascii=False)`; un testo inglese uguale all'italiano fa fallire `test_i18n_completo`.
- Ogni tabella nuova in `core/data_registry.py`; colonne `user_id`/`*_by` dichiarate; tabelle con id di utente o server: `filtro_server`.
- Il codice di una voce nel test conta come «fatta» per `scripts/stato_catalogo.py`: mai su una voce non fatta.
- Config è congelata: nei test si sostituisce `modulo.config` con un `SimpleNamespace`. `monkeypatch.undo()` con `clean_db` annulla il pool.
- Migrazione già applicata nel DB di prova: non si riesegue se cambia.

## Aperto
- Il router AI non usa ancora le chiavi proprie (area custode-ai). Il livello VIP da chiave vale già.
- `test_ticket_form::test_pubblica_due_pannelli_in_un_solo_messaggio` ha dato un `KeyError: 'view'` una volta sotto carico, passa da solo: da controllare.
- `tests/test_i18n_pubblica` fallisce per `cogs/fun/giochi_sospensioni.py:114` (r1med, non nostro).
- TKT-073 (Drive) non fatta. `admin-ticket` 7.142 caratteri; `/admin-ai` 19 figli; `/admin-ruoli` permesso `manage_roles` da decidere.
- Lingue: tetto richiesta giornaliero in memoria; lingua personale solo it/en; `aiuto` vuoto.
- NSFW RedGifs da controllare live; clan sciolto: categoria da togliere a mano; worker musicale senza blacklist all'ingresso.
- `tests/test_premium_invalidazione.py` assegna `db._pool`: da togliere.
