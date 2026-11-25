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

## Blocco B — Sandbox obbligatoria (25/11/2026, ramo fix/sandbox)
Fatto (commit sul ramo):
- B1 (c4ac1ad9): niente ripiego. `immagini_sandbox`: tolti `unshare`/modo ridotta; `rete_isolata()` (if_nameindex solo `lo`); `esegui_locale` risponde `non_isolata` se il processo ha rete; `analizza`/`converti` senza servizio = `non_disponibile`. conftest: servizio vero in un thread (session, autouse) + `_interfacce_di_rete` finto («lo»).
- B2 (5f5f4ac0): `core/safe_image.apri_in_sandbox` (cliente sincrono, solo in thread) sostituisce `safe_open_image` ovunque; il decoder sta in `core/immagini_decodifica.py` (solo worker); nuova richiesta del servizio `pixel <lato> <std|png> <nome>` -> pixel grezzi, il bot fa `Image.frombytes`. `SandboxNonDisponibile` gestita in `core/premium.handle_app_command_error`, `ui_base._rispondi_con_errore`, wrapper di core (raise), chiave `err_sandbox_non_disponibile` in 10 lingue; tolta `amimg_sandbox_ridotta`.
- B3: `core/allegati_cancello.py` + `cogs/logging/message_logs.py` (posto PRIMA del download; sopra soglia solo scheda).
- B4: unita systemd + `docs/immagini-sandbox.md`.
- Cricchetti: `tests/test_sandbox_obbligatoria.py` (AST: nessun Image.open/PdfReader/pillow_heif/ZipFile in lettura fuori da decodifica+worker+conversioni_worker; worker avviato solo dal servizio; gestori larghi con SandboxNonDisponibile prima; unita systemd), `tests/test_allegati_cancello.py`.
Prossimo passo: blocco finito e pubblicato; resta la prova su Discord (servizio vero su Debian/Ubuntu) e la decisione su `conserva` dei ticket.
