# Memoria di dev-core

## Aggiornata
24/11/2026 · ramo `feat/riordino` (pubblicato) · riordino dei comandi per famiglie e 10 comandi diretti (D137, #122). Prima: r1infra, r1premium.

## In corso
- Riordino finito nel codice: migrazione 0972, `core/comandi_diretti.py`, `/help`, `/owner-radio`, `/monete balance immagine`, traduzioni en-US, elenchi dei comandi, D137, CLAUDE.md. Test dei cog toccati (512 file) girati e sistemati (resolver D137 in `tests/support/percorsi.py`). Resta la prova su Discord (`VERIFICA_LIVE.md`, voce D137). Da unire dall'orchestratore.
- Scheda successiva (NON fatta): alias a prefisso.
- Restano: r1dep (#161), r1cfg (CFG-024 con dev-moderazione, 001/002/003/006/027 dev-web), r15immagini (`/admin-automod immagini`), #67 11.11, 11.12; #70 14.10, 14.12-14.14. Rimandato: permessi per ruolo dal pannello (OAuth).

## Fatto
- Riordino D137 (24/11): 354 comandi spostati con un codemod sui decoratori `@comando_di_gruppo`; mappa 419 coppie nella 0972 (comandi spenti, ruoli richiesti, registro, ultimo comando, conteggio giornaliero); `GRUPPI_SOLO_OWNER`; peso con +30% (`caratteri_con_traduzioni`); tetto 100 globali, avviso 90; figli max 25.
- r1premium (D59, D124, D127): `core/piani.py` (livelli, concessioni, limiti, prezzi, sconti), `ai_chiavi_proprie.py`, `piani_comandi.py`, `everyone_programmati.py`, `patreon_logic/service/server.py` + cog `utility/patreon.py`; `/owner premium piano`, `/admin-bot premium chiave`; test `test_piani`, `test_patreon`, `test_everyone_programmati`.
- r1med: LOG-029 e 15 voci (0880-0888, D121). r1doc: LIV-013/046/053/061/090/091, CFG-011, VOC-017, MUS-043, FUN-030, AI-022.
- r1cfg (D96), r15immagini (D62), r14lingue (D58), r13ruoli (D60), r13gruppi (D56/D57), r1collaudo (D109): vedi `git log`.

## Cose imparate
- Comandi diretti: `ComandoDiretto` (core/comandi_diretti.py) copia permessi e livello del gruppo; ogni lettore del percorso (politica, statistiche, livelli funzione, traduttore) usa `percorso_vero(comando)`, mai `qualified_name`. Un test lo prova per la politica e le statistiche.
- Un gruppo che spostato deve restare sempre acceso va in `PREFISSI_SEMPRE_APERTI` (`admin-bot-config`, `owner-radio`).
- Codemod dei decoratori: prefissi vecchio→nuovo in una tabella, riscrittura per posizione AST; i testi nelle stringhe si riscrivono con tokenize (f-string incluse con Python 3.12+: `FSTRING_MIDDLE`).
- `locales/en-US/comandi.json` si scrive con `indent=1` e `\n` finale; `nomi` non può avere segmenti senza comando (test).
- Il livello di un server o di una persona passa solo da `piani.livello_server/livello_utente`; il limite di un modulo da `piani.limite_server_sicuro` (torna al predefinito se il database non risponde). `registra_bot` dà il bot ai repository.
- `livelli_funzione`: VIP5/VIP20 sono alias di ULTRA/VIP (valori `ultra`, `vip` nel database dalla 0910).
- `/owner` è a 6.333 su 8.000 (D132; un test lo tiene sotto 6.800). Il peso conta la traduzione più lunga: accorcia anche en-US. Gruppi di primo livello 60/60. Scelte di un'opzione: autocompletamento, non `choices` (pesano).
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
- Chiavi proprie: `MotoreAI.esegui(guild_id, user_id)` le usa (fuori da quote e pause, costo 0). Da provare live.
- `test_ticket_form::test_pubblica_due_pannelli_in_un_solo_messaggio` ha dato un `KeyError: 'view'` una volta sotto carico, passa da solo: da controllare.
- TKT-073 (Drive) non fatta. `admin-ticket` 7.142 caratteri; `/admin-ai` 19 figli; `/admin-ruoli` permesso `manage_roles` da decidere.
- Lingue: tetto richiesta giornaliero in memoria; lingua personale solo it/en; `aiuto` vuoto.
- NSFW RedGifs da controllare live; clan sciolto: categoria da togliere a mano; worker musicale senza blacklist all'ingresso.
- `tests/test_premium_invalidazione.py` assegna `db._pool`: da togliere.

## Blocco C (autonomia 24/7) — ramo fix/autonomia
- Migrazioni riservate al blocco C: 0980 e seguenti (0980 = giri_periodici).
- [1 FATTA] `core/giro_periodico.py`: `GiroPeriodico(tasks.Loop)` + decoratore `giro_periodico(...)` (stessi parametri di `tasks.loop`, più `subito=True`). Tutti i 56 loop convertiti con codemod. Errori contati, pause 5s..15min, stato in `giri_periodici`, attesa dopo riavvio (solo intervalli >= 5 min), lock `pg_try_advisory_lock` (`leadership`), ascoltatori caduta/ripresa (3 errori di fila) per gli avvisi owner, `stato_giri()`/`giri_in_difficolta()` per /salute. Cricchetto AST in `tests/test_giro_periodico.py`.
- [2 FATTA] Avvio sicuro: `load_all_cogs` -> lista dei falliti; `sincronizza_all_avvio(cog_falliti=)` non sincronizza se manca un cog; impronta salvata illeggibile -> `NON_VERIFICABILE` (niente sync, cambiato il vecchio test); `core/avvio_sicuro.py` (DM owner + giro `_riprova_avvio` che ricarica i cog e rifà la sync, silenzioso); `core/ripristino_differito.py` (view dei 4 cog con I/O nel setup in background con pause crescenti); `core/avvisi_owner.py` (voce 6 in gran parte: cadute raggruppate 30 s, pausa 5 min, "tornato" solo se avvisato; `collega_ai_giri` chiamato nel setup_hook). Chiavi `owner_*` in 10 lingue. Cricchetto no-I/O in setup() in `tests/test_avvio_sicuro.py`.
- [3 FATTA, tranne i defer] `core/pool_db.py` `PoolConCorsie` (attesa massima 10 s comandi / 15 s eventi, corsia eventi con semaforo: ne restano sempre 2+ ai comandi; `iYokaiBot._run_event` imposta `corsia_db`); `interaction_check` con tetto 2,5 s e risposta `err_bot_occupato`; stesso messaggio per TimeoutError in `handle_app_command_error`; `economia_sospensioni.attiva_in_cache` (TTL 30 s, invalidata dalle scritture; `tests/conftest.py clean_db` la svuota). NON fatto: `defer()` nei comandi pesanti (serve l'elenco dei comandi lenti dal guardiano-limiti).
- PROSSIMO: 4 musica (core/music_nodes.py, music_fleet.py, cogs/music/player.py, soundboard). Poi 5 servizio+/salute, 6 avvisi (resta: servizio di sistema/Lavalink/DB giù), 7 script, 8 spegnimento (chiamare `leadership.rilascia()` e `ferma_ripristini()`), 9 seri, 10 test di guasto.
