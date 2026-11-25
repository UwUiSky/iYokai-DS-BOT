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

## Blocco A (sicurezza, ramo fix/sicurezza) — 25/11/2026
Scheda: /home/user/consiglio/schede/A_sicurezza.md. DB di prova iyokai_wsicurezza. Migrazioni mie: 0980-0989 (0980 fatta).
- FATTA voce 1 (ban globale con affidabilità, D140): `core/global_ban_logic.py`, `cogs/security/global_ban.py` (propagate_ban unito alla rete: proposte `rete_ban_proposte`, categoria `ban_globale`), mig. 0980, `security_raid_state.segna_nuke`. Test: `test_global_ban_affidabilita`, `test_global_ban_rete_unica` + vecchi riscritti.
- FATTE voci 2 e 3: tabella rotte `TABELLA_ROTTE` in `core/web_panel_accesso.py` + middleware `controllo_rotta` + `_server` che non scende sotto la tabella; `errore_ruolo_bot`/`RuoloBotNegato` in `core/command_access.py`; `imposta_modulo` chiede livello SECURITY per i 6 moduli di sicurezza e avvisa il proprietario. Test: `test_web_panel_tabella_rotte`, `test_config_schema_sicurezza`, `test_ruoli_bot_import`, aggiunte a `test_command_access`.
- FATTA voce 4 (Patreon, D141): stato legato alla sessione, conferma spostamento (`patreon_spostamenti`, mig. 0981), webhook vecchi ignorati, D96 annotata. Test: `test_patreon`, `test_web_panel_patreon`.
- FATTA voce 5: scadenza 90 giorni di `restore_oauth_tokens` nel registro dati (applicata da `pulisci_scaduti`); tolto il metodo morto `purge_expired_voluntary_leaves` e la voce da KNOWN_UNCALLED. Test in `test_restore_oauth_repo`.
- FATTA voce 6: nonce del ripristino in `restore_nonce` (mig. 0982, async), limiti marchio/sincronia/esporta in `pannello_limiti` (`LimitePersistente`). Test: `test_restore_oauth_logic`, `test_pannello_limiti`.
- FATTA voce 7 (Desktop): token a 90 giorni (mig. 0983), revoca se la persona non è più in nessun server, azioni dello staff con i cancelli dei comandi (modulo, panico, politica, caso del timeout), last_used_at ogni 10 minuti. Test in `test_desktop_api`, `test_desktop_staff`. Nota: il blocco/sblocco canale non scrive caso né programma lo sblocco (il comando sì).
- FATTA voce 8 (marchio): `collega_e_avvia` solo per il proprietario (`mar_solo_proprietario`), traccia nello storico + avviso `sicurezza` (`registra_modifica`), AAD `marchio:{guild_id}` con lettura delle righe vecchie e riscrittura. Test in `test_whitelabel_bot`, `test_panel_marchio`.
- FATTA voce 9 (SSRF Lavalink, D142): `link_diretto_ammesso` + `HOST_LINK_DIRETTI`, anche per brani `http` di playlist importate.
- FATTA voce 10: `ip_del_client` unica (voto, Patreon, webhook custom), default proxy `127.0.0.1,::1`, `nessuno` + bind locale = il bot non parte. Test `test_ip_client_unico`.
- FATTA voce 11 (D143): avviso VPN con solo il numero; tolta `verify_condividi_nome`.
- FATTE voci 12 e 13: 7 `assert` di produzione -> ValueError, 5 `or True` tolti (i test passano), secondo fattore TOTP (`core/secondo_fattore.py`, `OWNER_TOTP_SECRET`, opzione `codice` di eval/shell/load/reload-hotpatch), cricchetti `test_cricchetti_sicurezza` (assert, or True) e `test_web_panel_tabella_rotte`.
- BLOCCO A FINITO: resta il riepilogo all'orchestratore. Smoke da fare dopo il merge: albero comandi, migrazioni 0980-0983.
- Appunti: testi del pannello (ESITI) e `_assistente.py` restano in italiano nel codice (nessuna i18n del pannello); script chiavi lingue: scratchpad `chiavi.py`.

## Aperto
- Chiavi proprie: `MotoreAI.esegui(guild_id, user_id)` le usa (fuori da quote e pause, costo 0). Da provare live.
- `test_ticket_form::test_pubblica_due_pannelli_in_un_solo_messaggio` ha dato un `KeyError: 'view'` una volta sotto carico, passa da solo: da controllare.
- TKT-073 (Drive) non fatta. `admin-ticket` 7.142 caratteri; `/admin-ai` 19 figli; `/admin-ruoli` permesso `manage_roles` da decidere.
- Lingue: tetto richiesta giornaliero in memoria; lingua personale solo it/en; `aiuto` vuoto.
- NSFW RedGifs da controllare live; clan sciolto: categoria da togliere a mano; worker musicale senza blacklist all'ingresso.
- `tests/test_premium_invalidazione.py` assegna `db._pool`: da togliere.
