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
| `cogs/security/anti_nuke.py` | `limits` accettava 0, negativi, valori enormi; `trusted-add/remove` senza lunghezza massima; lista fidati senza tetto (LIMITI.md Parte 4, 3 e 5) | `Range` su soglie e finestra, `Range[str,1,20]` sugli ID, tetto di 100 fidati | A | `test_anti_nuke_117.py` |
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

SIC-001, 002, 003, 004, 005, 006, 007, 008, 009, 010, 017, 018, 019, 020, 022, 025 (solo "chi ha aggiunto il bot"; non il filtro sui bot non verificati, SIC-026), 044, 046.

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

- `cogs/moderation/actions.py:441`: `/modban unban` revoca i casi della trappola ma **non** i ban propagati agli altri server. Va chiamata `cogs.security.global_ban.revoca_ban_propagati(bot, guild.id, user_id)` come in `spam_trap.py`.
- `cogs/utility/greetings.py`: manca ancora l'aggancio `raid_in_corso` (M 10.16, già in memoria).
- Il `/security heatmap` e l'avviso all'owner restano dentro il modulo premium `permission_heatmap`; `security_score` resta gratuito.
