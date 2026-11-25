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
- [4 FATTA] Musica: `MusicNodeManager.su_nodo_chiuso` (evento wavelink `on_wavelink_node_closed`, NON esiste `node_disconnected` in wavelink 3.x), `riparti_nodi_caduti`, `stato_per_servizio`; `core/music_sorveglianza.py` (giri 30 s nodi + 60 s slot, DM owner se un Lavalink che aveva funzionato resta giu' 120 s); `MusicFleet.sessione()` (rilascio in finally, usato in `play`), `indice_di`, `libera_slot_persi`; `release_session(..., worker_index)` con WHERE sul worker; rimossi i 11 rilasci a mano da `_play_nel_canale` e il parametro `rilascia` di `_con_jukebox`; metodi pubblici del player (`blocco_canale`, `controlli_base`, `ascoltatori_umani`, `privilegi`, `trova_worker`, `rilascia_se_libero`, `entra_in_canale`: rinominati ovunque, test compresi). Fake dei test: `tests/support/flotta_finta.py`.
- [5 FATTA] `deploy/systemd/iyokai-bot.service` (+README, `scripts/installa_servizio.sh --prova`), `core/salute.py` (/salute su `SALUTE_PORT` 8424, `MisuraCiclo`, metriche nei log ogni 5 min, avviato in main). Lavalink facoltativo nell'unita'. before_loop dei giri ora si riprova (non uccide il giro).
- [6 FATTA] avvisi: `core/avvisi_owner.py` + bot secondari riavviati in `bot_supervisor._supervisore` (5 s..15 min, un solo avviso per serie, LoginFailure non si riprova, chiavi `owner_bot_*`).
- [7 FATTA] avvia.sh/ps1: Lavalink assente = AVVISO, attesa 90 s, password via `curl --config -`; test `tests/test_avvia_script.py`.
- Falliti preesistenti (non nostri): `test_config_schema::test_imposta_lingua_server` (fallisce anche su main); `test_config_rollback_bug6` flaky sotto carico.
- [8 FATTA] `spegni_ordinatamente`: `_con_limite` per ogni passo (servizi 8 s, bot insieme 15 s, sessioni 8 s, db 8 s), poi `db.terminate()` (nuovo) se il pool non si chiude; `ferma_tutti_i_giri()` + `leadership.rilascia()` + `ferma_ripristini()`. TimeoutStopSec=75 nell'unita'. Il test `main_con_due_sigterm` ha il close a 0.3 s (i bot ora si chiudono in parallelo).
- [9 FATTA, in parte] retention a lotti (`LOTTO_RIGHE`, `TempoFinito`, ordine casuale, `sql_*_a_lotti` in data_registry); giveaway a stati (migrazione 0981 `fase_fine`, `prendi_fine` lock advisory, `concludi(solleva_se_discord_non_risponde)`); feed: `FreniInvio` (403/404 -> pausa, 5 rifiuti -> paused); log: `core/log_coda.py` (QueueHandler + thread); marchi: pause crescenti e spegnimento dopo 10 cadute; anti-nuke: `on_audit_log_entry_create` -> `security_audit.registra_voce`; `core/blocchi_deboli.py` al posto di tutti i dizionari/cache di Lock; transcript ticket: una lettura (tetto 10.000) e rendering in thread; cricchetto "giro senza try/except globale".
  NON fatto: `defer()` nei comandi pesanti; conversione in BoundedCache degli altri ~60 dizionari senza tetto (elenco: `grep -rnE "self\._[a-z_]+: dict\[" core cogs`); ban globale (blocco A).
- [10 FATTA] `tests/test_guasti.py` + `tests/support/proxy_guasto.py` (proxy TCP che si stacca): PostgreSQL giu'/su', Lavalink giu'/su'. NOTA: il test Lavalink end-to-end non e' discriminante col controllo negativo (wavelink a volte si ricollega da solo a proxy ripristinato); il gestore e' provato dal test unitario `test_music_autonomia::test_nodo_caduto_riparte...` (fallisce senza il gestore).
- Decisione D138 scritta; prova live `C-AUTONOMIA` in VERIFICA_LIVE.md.
- Migrazioni del blocco C: 0980 (giri_periodici), 0981 (giveaway fase_fine). Edit a `tests/conftest.py`: `clean_db` svuota la cache delle sospensioni.
- PROSSIMO: leggere l'esito di /tmp/claude-0/run_finale.txt (516 file, DB iyokai_wautonomia2) e correggere; poi rapporto.
