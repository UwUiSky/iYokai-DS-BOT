# AUDIT_SICUREZZA.md — Passaggio sulla sicurezza (ramo `feat/sicurezza-audit`)

Richiesta dell'owner: la sicurezza è stata scritta in fretta (anti-nuke, anti-raid, spam-trap, ban globale, lockdown, alt-detection, invite_sync, heatmap, security score, verify). Un solo passaggio per file: righe 3.x di #59 ancora aperte, voci piccole e medie del catalogo #117 (`catalogo/03-sicurezza-antiraid-antinuke.md`), difetti trovati leggendo.

Base `90bbeb2`. Commit: **A** `8895c79` (anti-nuke), **B** `e684371` (anti-raid), **C** `ccdc53b` (score, heatmap, ban globale), **D** `012e083` (spam-trap, verify, invite_sync, controlla).
Le tabelle di sicurezza nascono in `security_repo.run_migrations` (non in `core/migrations/`): per questo le migrazioni 0024–0026 **non sono servite** (`nuke_cases` sta lì, `global_ban_direction` e la colonna `revoked_at` in `global_ban_repo.run_migrations`).

## Log: file, difetto, correzione, commit, test

| File | Cosa non andava | Come è stato sistemato | Commit | Test |
|---|---|---|---|---|
| `core/security_logic.py` | Una sola soglia per categoria; punizione "toglie i ruoli" o ban; una sola lista di fidati senza livelli né ambito (SIC-001, 002, 018, 019, 020) | Seconda soglia di un'ora (`*_hour_max`, 0 = spenta); `punish_action` default `quarantine`; `TrustEntry` (utente/webhook, fidato/extra owner, tipo di azione, categoria di canali); `actor_is_trusted`; categoria `channel_perms`; `quarantine_hold`; `bot_role_problems` | A, B | `test_security_fiducia_117.py` |
| `core/repositories/security_repo.py` | Nessun registro degli attacchi (SIC-017); campi nuovi non salvati | Tabella `nuke_cases` (numero per server con blocco, ultimi 500), lettura/scrittura dei campi nuovi, riga vecchia ancora leggibile | A | `test_security_casi_nuke_117.py`, `test_security_fiducia_117.py` |
| `core/security_access.py` | Il file dice "chi tocca le impostazioni di sicurezza" ma non lo faceva: qualunque amministratore poteva mettersi nella lista dei fidati o spegnere l'anti-nuke | `puo_gestire_antinuke`: solo proprietario ed extra owner; l'extra owner lo nomina solo il proprietario | A | `test_anti_nuke_117.py` |
| `core/security_quarantine.py` (nuovo) | Ruolo di quarantena e permessi dentro `anti_raid.py`, non usabili dall'anti-nuke | Spostati con un blocco per server (per ciclo di eventi); `metti_in_quarantena`, `rilascia_da_quarantena`, `problemi_ruoli_del_bot` (SIC-022) | A, B | `test_anti_nuke_117.py`, `test_anti_raid_117.py`, `test_anti_raid_avviso_133.py` |
| `cogs/security/anti_nuke.py` | SIC-001/002: soglia unica, punizione dura (M 3.5); SIC-017 nessun registro; SIC-018/019/020 fiducia unica; SIC-005/006 permessi pericolosi a un ruolo, SIC-007 permessi dei canali, SIC-008 ruolo pericoloso a un membro, SIC-009 link personalizzato, SIC-010 prune, SIC-025 chi aggiunge i bot: nessuna guardia | Motore con le due soglie e il caso numerato nell'avviso; comandi `casi`, `rilascia`, `guardie`, `trusted-list`, `trusted-add` con tipo/livello/azione/categoria; listener `on_guild_role_update`, `on_guild_channel_update`, `on_member_update`, `on_guild_update`, `on_member_join`, controllo prune in `on_member_remove` | A | `test_anti_nuke_117.py`, `test_anti_nuke_guardie_117.py` |
| `cogs/security/anti_nuke.py` | `limits` accettava negativi e valori enormi; `trusted-add/remove` senza lunghezza massima; lista fidati senza tetto (LIMITI.md Parte 4, 3 e 5) | `Range` su soglie (0–1000; 0 ammesso di proposito, vedi sotto), finestra (1–3600), ora (0–10000), `Range[str,1,20]` sugli ID, tetto di 100 fidati | A | `test_security_revisione_117.py::test_limiti_di_limits_e_trusted_add_sono_rifiutati_da_discord` (legge i limiti veri dai suggerimenti di tipo del comando; il test di prima non li verificava) |
| `cogs/security/anti_raid.py` | Ruolo di quarantena modificabile a mano (SIC-004); chi è in quarantena poteva essere liberato o armato da chiunque (SIC-003); `join-rate` e `account-age` senza limiti; quarantena non assegnata taciuta; nessun avviso sui ruoli del bot (SIC-022); `status` incompleto | `on_guild_role_update`, `on_member_update` + `quarantine-hold`, `rilascia`; `Range`; avviso "senza quarantena"; avvisi su `enable` e `status` | B | `test_anti_raid_117.py` |
| `cogs/security/security_score.py` | **La 2FA non veniva mai rilevata**: `guild.mfa_level` è un enum e il confronto con 0 era sempre falso; il proprietario contava tra gli admin; membri non scaricati; campo consigli oltre 1024 | Si usa `.value`; owner escluso e soglia di tre admin; `guild.chunk()` (con `defer` se serve); consigli in più campi; SIC-022 nel punteggio | C | `test_security_score_117.py` |
| `cogs/security/permission_heatmap.py` | `@everyone` con permessi critici saltato; ordine casuale; un ruolo admin dato a 200 membri = 200 DM; proprietario non in cache = nessun avviso; nomi di ruolo con markdown/menzioni | `@everyone` in cima con avviso; ordine per posizione; 5 avvisi ogni 10 minuti poi uno solo; `fetch_user`; testo escapato | C | `test_permission_heatmap_117.py` |
| `cogs/security/global_ban.py`, `global_ban_repo.py`, `global_ban_logic.py` | Un solo interruttore per inviare e ricevere (SIC-046); un appello accolto lasciava il ban negli altri server; nessuna pausa tra i ban; registro delle propagazioni senza scadenza; niente scheda sull'utente (SIC-044) | `global_ban_direction` (invia/ricevi), `revoca_ban_propagati` (solo ban col motivo della rete), pausa di 0,2 s, pulizia a 365 giorni, `/security globalban controlla` (solo il numero di server, mai i nomi) | C, D | `test_global_ban_117.py` |
| `cogs/security/spam_trap.py` | Cinque messaggi di fila nella trappola = cinque DM, casi e propagazioni; trappola e log sullo stesso canale; nessun avviso se mancano Bannare membri, thread privati o lettura; il canale log creato dal bot poteva restare invisibile al bot; il transcript faceva una chiamata a Discord per **ogni** messaggio prima del ban; la pulizia dopo il ban si fermava su ogni errore diverso da `Forbidden`; l'appello accolto non toglieva i ban propagati | Un giro per utente (in corso + 60 s); controllo canali diversi; `_permessi_mancanti` nella risposta del setup; overwrite del bot sul canale log; tetto di 40 messaggi nel transcript, dichiarato; `HTTPException`; revoca dei ban propagati; la propagazione gira in parallelo ai passi seguenti | D | `test_spam_trap_117.py` |
| `cogs/security/verify.py` | `whitelist`/`blacklist` chiedevano un `Member` (non si poteva bloccare chi era uscito); clic sul pannello senza risposta fuori dal server o senza cog; chi aveva già il ruolo riempiva il log; pannello pubblicabile a modulo spento; `add_reaction` non gestito | `discord.User`; risposte mancanti; "già verificato"; `ensure_module_enabled`; avviso se la reazione non si può aggiungere | D | `test_verify_117.py` |
| `cogs/security/invite_sync.py` | `invite.guild` può essere `Object`/`PartialInviteGuild`: `AttributeError` nel listener; un errore su un server rompeva gli altri listener | Risoluzione dal bot e `try/except` con log | D | `test_invite_sync_117.py` |
| `tests/` esistenti | I test dell'anti-nuke davano per scontato il default "toglie i ruoli"; il finto server dello score non aveva owner/ruoli | Impostano `strip_roles` in modo esplicito; il finto ha `me`, `roles`, `owner_id` | A, C | — |

## Righe 3.x di #59

| Riga | Stato | Dove |
|---|---|---|
| 3.1, 3.2, 3.3, 3.4 | già fatte (prima di questo giro) | test `test_anti_nuke_f1.py`, `_recovery_133.py` |
| **3.5** | **fatta qui**: due soglie, quarantena di default, filtro su chi aggiunge i bot | A (SIC-001, 002, 025) |
| 3.6, 3.7, 3.8 | già fatte; 3.8 ora anche sul permesso del ruolo (SIC-004) | `test_anti_raid_*`, B |
| 3.9–3.13 | già fatte | `test_spam_trap_*` |
| 3.14 | già fatta; verificato anche per i listener (`premium_sbloccato`). `globalban disable` resta senza `requires_module` di proposito (si deve poter uscire dalla rete) | `test_security_premium_f1.py` |
| 3.15, 3.16, 3.17 | già fatte | `test_permission_heatmap_limiti.py`, `test_security_score_effimero.py`, `test_invite_sync_solo_dove_serve.py` |
| **3.18** | **non fatta**: serve il router dei canali (NF-01, `core/channel_router.py` è ancora uno scheletro) | — |

## Voci #117 fatte

SIC-001, 002, 003, 004, 005, 006, 007, 008, 009, 010, 017, 018, 019, 020, 022, 025 (completo: il bot aggiunto da chi non è fidato viene espulso e c'è il caso; il filtro sui bot **non verificati** è un'altra voce, SIC-026, non fatta), 044, 046.

## Non fatto, e perché

- **`alt_detection.py` (#92, SIC non applicabile)**: serve la verifica su web (OAuth `identify`, impronte, informativa privacy). Infrastruttura grossa, resta scheletro.
- **`lockdown.py` (#100) e SIC-011…015 (panico)**: funzione nuova intera (blocco di tutti i canali, stato salvato per riaprire, categorie escluse, ping ai ruoli, pause su 500 canali). Non è una correzione; ha la sua issue e le sue regole di test.
- **`ban_appeal_logic.py` (#101)**: appello per i ban normali; funzione nuova (View persistente, tabella, comando in `/admin config`).
- **SIC-016** (recupero da snapshot): dipende dal backup (D8, `dev-backup`).
- **SIC-021** (chiave di soccorso): serve il flusso `/owner` con controllo a mano.
- **SIC-023…038** (filtri all'ingresso per azione, kick/ban al raid, azione su chi è entrato prima, ping dei ruoli, elenco degli account, livelli di allerta, segnale condiviso): ampliamenti dell'anti-raid, non correzioni; restano a catalogo.
- **SIC-039, 040** (più canali trappola, punizione a scelta), **SIC-041…043** (phishing), **SIC-045** (opt-out di rete dal comando privacy, dipende da NF-04): non fatte.
- **3.18** (canale allarmi dell'anti-nuke tramite router, NF-01): vedi sopra.

## Problemi fuori dai miei file (da girare)

- `cogs/moderation/actions.py`: `/modban unban` non toglieva i ban propagati — **sistemato nella revisione** (vedi sotto).
- `cogs/utility/greetings.py`: manca ancora l'aggancio `raid_in_corso` (M 10.16, già in memoria).
- Il `/security heatmap` e l'avviso all'owner restano dentro il modulo premium `permission_heatmap`; `security_score` resta gratuito.

## Revisione (cacciatore e revisore), commit **E** `d81b48b`

Difetti trovati dopo il passaggio, tutti con test scritto prima (rossi senza la correzione, 15 mutazioni delle correzioni nuove uccise dai test).

| File | Cosa non andava | Come è stato sistemato | Test |
|---|---|---|---|
| `cogs/security/anti_nuke.py`, `anti_raid.py`, `core/security_access.py` | `limits`, `punish-action`, `recovery`, `quarantine-hold` e `rilascia` (col blocco acceso) li cambiava qualunque amministratore: si abbassava le soglie da solo | `solo_chi_gestisce` (proprietario ed extra owner) unica, in `core/security_access.py`, chiamata da tutti | `test_security_revisione_117.py` (chiamate da non-owner, extra owner ammesso) |
| `core/security_logic.py`, `anti_nuke.py` | Un extra owner poteva declassare o sostituire un altro extra owner con `trusted-add` (`trusted-remove` lo impediva); due fonti per i fidati (`trusted_ids` e `trust_entries`) | `aggiungi_fiducia` / `rimuovi_fiducia` / `voci_fiducia` nel core (D16); la prima modifica fonde i `trusted_ids` vecchi in `trust_entries` | `test_aggiungi_fiducia_regole_nel_core`, `test_la_lista_dei_fidati_ha_una_fonte_sola`, `test_extra_owner_non_declassa…` |
| `anti_nuke.py` | Ogni evento oltre soglia ripuniva, apriva un caso, mandava DM e avviso (6 eventi = 6 casi); il proprietario come autore apriva comunque un caso "nessuna azione" | Una punizione per episodio (un'ora): blocco per (server, autore), caso unico; ripete solo se la punizione non tiene e sullo stesso caso (ruoli uniti); il proprietario non si conta | `test_un_attacco_un_caso_un_dm_un_avviso`, `test_eventi_insieme…`, `test_se_la_punizione_non_tiene…`, `test_dopo_il_rilascio…`, `test_il_proprietario_non_viene_contato…` |
| `core/security_quarantine.py`, `anti_nuke.py`, `anti_raid.py` | Due `rilascia` diversi; il rilascio del caso più recente non rimetteva i ruoli (finivano nel caso 1); rilasciare toglieva la quarantena anche con altri casi attivi; i contatori restavano | Un solo `rilascia_utente` nel core: per caso, rimette i ruoli di quel caso, tiene la quarantena se ci sono altri casi attivi, segna rilasciato solo a successo; l'anti-nuke azzera i contatori | `test_rilasciare_un_caso_non_toglie…`, `test_rilascio_non_rimette_ruoli_cancellati…`, `test_rilascio_fallito…`, `test_dopo_il_rilascio_i_contatori…`, `test_antiraid_rilascia_non_toglie…` |
| `core/security_quarantine.py`, `anti_nuke.py` | Se `edit(roles=)` falliva si diceva comunque "messo in quarantena" (l'autore restava admin); il ruolo di quarantena si creava durante l'attacco; un "Quarantined" fatto a mano teneva i suoi permessi | `EsitoQuarantena` (`completo`, `ruoli_non_tolti`): l'avviso e il caso dicono "ruoli NON tolti, autore ancora potente"; il ruolo si prepara a `enable` (anti-nuke e anti-raid) con avviso se non si può; permessi azzerati su un ruolo trovato | `test_quarantena_senza_ruoli_tolti…`, `test_l_avviso_dice…`, `test_il_caso_registra_l_esito_parziale`, `test_antinuke_enable_…`, `test_antiraid_enable_crea_il_ruolo_subito`, `test_ruolo_quarantined_fatto_a_mano…` |
| `cogs/security/anti_nuke.py` | Il recupero guardava solo la finestra breve: un attacco lento (soglia oraria) perdeva quasi tutti i canali | Finestra di recupero = un'ora se la soglia oraria è accesa; le voci più vecchie di un'ora si scartano subito | `test_attacco_lento_si_recupera_per_intero` |
| `cogs/security/global_ban.py`, `global_ban_repo.py` | `mark_revoked` chiudeva tutte le righe anche se l'unban falliva; un appello a metà propagazione lasciava ban nuovi; il ban di un'altra sorgente veniva tolto; lo staff dei server di destinazione veniva bannato; un `DELETE` a ogni riga; nessun indice | Revoca per server riuscito (le altre restano da ritentare); blocco per (sorgente, utente) con flag "revocato" (nessun ban dopo la revoca, ban+riga indivisibili); `banned_by_other_source`; `is_staff_exempt` (core) anche nei server di arrivo; `purge_old` una volta per giro; 3 indici | `test_global_ban_revisione_117.py` |
| `cogs/moderation/actions.py` | `/modban unban` non toglieva i ban propagati | Chiama `revoca_ban_propagati` dopo la risposta (con una rete grande supera i 3 secondi) | `test_modban_unban_toglie_anche_i_ban_propagati` |
| `cogs/security/spam_trap.py` | Se la sequenza saltava a metà, il task di propagazione restava in giro | Annullato e atteso; `_is_staff_exempt` ora è `core.security_access.is_staff_exempt` (anche bot e chi ha Bannare membri) | `test_se_la_sequenza_salta_la_propagazione_non_resta_orfana` |
| `cogs/security/verify.py` | Chi era già verificato vedeva prima il captcha | Controllo del ruolo prima del modulo | `test_chi_e_gia_verificato_vede_l_avviso_prima_del_captcha` |
| `core/security_audit.py` (nuovo), `anti_nuke.py`, `anti_raid.py` | `_resolve_voce` viveva nell'anti-nuke e l'anti-raid la importava dal cog; costanti e import inutili (`ALL_TRUST_ACTIONS`, `ROLE_PERM_GUARD_MODES`, `_resolve_actor`, `field`, `timedelta`…) | Spostata in `core/security_audit.py` (`resolve_voce`); codice morto tolto | i test esistenti (patchano `core.security_audit._aspetta`) |

Test aggiunti dove le mutazioni sopravvivevano: owner esente, ruoli gestiti/cancellati/sopra al bot nel rilascio, fallback `add_roles`, ruolo di quarantena sopra al bot, avvisi in `status` dell'anti-raid, i tre avvisi dei permessi della spam-trap (+ thread e caso senza avvisi), `whitelist`/`blacklist` a modulo spento, `revoked_at` fuori dal conteggio della rete, escape dei nomi nella mappa dei permessi, `Range` veri.

**Decisione aperta (da proporre all'owner):** ripiego su kick/ban quando la quarantena non riesce a togliere i ruoli. Oggi la punizione configurata è "quarantena", che non lo prevede; con `punish-action Banna` il ban parte già e un bot si espelle già. Finché l'owner non decide, l'esito parziale è solo dichiarato nell'avviso e nel caso.


## Completamenti del 14/10

Giro r5 (ramo `feat/r5-mod`). Che cosa l'Advisor aveva lasciato a metà e come è stato sistemato.

| Voce | Cosa era parziale | Come è sistemato | Test |
|---|---|---|---|
| **3.5** (due soglie e quarantena) | Le due soglie, la quarantena di partenza e il filtro su chi aggiunge i bot c'erano (A). Mancava una scelta dichiarata per il caso in cui la quarantena non riesce a togliere i ruoli: l'esito parziale era solo scritto nell'avviso | Invariato il comportamento (decisione sul ripiego kick/ban ancora aperta con l'owner); verificato che il caso e l'avviso dicano «ruoli NON tolti» e che il panico automatico parta comunque dopo l'attacco | `test_anti_nuke_117.py`, `test_anti_nuke_allarmi.py` |
| **3.18** (canale allarmi anti-nuke) | «Non fatta»: serviva il router | Il canale proprio passa dal router (`TIPO_ALLARMI`, anche forum); senza scelta vale quello dell'anti-raid. `/security antinuke` è diventato il gruppo `/antinuke` (D25: `/security` era a 6.824 caratteri) | `test_anti_nuke_allarmi.py` |
| **NF-29 / #100, SIC-011…015** (blocco e panico) | «Funzione nuova intera», non iniziata | `/mod blocco attiva\|togli` e `/security panico attiva\|togli\|configura\|stato`. Stato e permessi di prima salvati **prima** di toccare ogni canale (riapre anche dopo un riavvio a metà); si rimette solo ciò che il blocco ha negato; categorie escluse (25), ruoli avvisati (10), sblocco automatico (fino a un giorno), moderazione riservata a proprietario e fidati, panico automatico dopo anti-nuke e anti-raid (una volta per episodio). Migrazione 0110 e tre tabelle nel registro dei dati | `test_lockdown.py` |
| **SIC-041…043 / NF-31 / #102** (phishing) | Non fatta | `/automod filtri phishing`: lista locale `data/phishing_domains.txt`, download opzionale (`PHISHING_LIST_URL`, https, 6 ore, 2 MB, 10 s, la lista di prima resta se fallisce), segni da sito truffa (marca + parola da regalo, marca scritta storta), domini ufficiali mai segnalati, whitelist anti-link che sblocca. Di partenza: cancella e timeout | `test_phishing_logic.py` |
| **NF-18 / #89** (captcha a immagine) | Solo la somma scritta | Opzione `captcha_tipo` in `/security verify setup`: immagine PNG 200x80 con lettere storte, bottone che apre il modulo (etichetta sotto 45 caratteri), 3 minuti e 3 tentativi, un codice per utente in memoria con tetto | `test_captcha_image.py` |

Resta fuori: SIC-016 (backup), SIC-021 (chiave di soccorso), SIC-023…038 (ampliamenti dell'anti-raid), SIC-039/040, SIC-045, SIC-026. Il ripiego su kick/ban quando la quarantena non toglie i ruoli aspetta ancora la scelta dell'owner.
