# SPEC.md — Specifica canonica iYokai + audit dello stato reale

**Questo file è la FONTE DI VERITÀ del progetto.**

Trascritto dallo schema ultra-dettagliato originale della conversazione
di progettazione, foglia per foglia, con a fianco lo stato verificato
contro il codice reale (non contro una roadmap riassunta).

## Perché questo file esiste

Le prime fasi di sviluppo sono state guidate da una roadmap
*riassunta* che io (Claude) avevo derivato dallo schema originale.
Quella compressione ha fatto sparire intere sezioni senza segnalarle
come rimandate, e ogni successivo "controllo" l'ho fatto ricostruendo
a memoria invece di rileggere lo schema — ripetendo lo stesso errore
tre volte di fila. Da qui in avanti: **ogni sessione parte da questo
file, non da un riassunto.**

## Legenda e stato

<!-- LEGENDA-STATO: generata da grep, non modificare a mano i numeri -->

Aggiornato il **04/10/2026**, dopo la fase R1-bis e la riorganizzazione
dei documenti. Il **05/10/2026** §25 è passato da 9 a 93 voci: sono le
funzioni AI discusse con l'owner e con le altre AI che non erano mai
entrate in una lista (`revisione/01-analisi/FUNZIONI_AI.md`). Lo stesso
giorno l'owner ha chiesto altre 16 voci (5.11, 5.12, 14.19, 17.11,
25.94–25.105).

| Simbolo | Significato |
|---|---|
| `[x]` | Fatto, coperto dai test e non rotto da nessun problema aperto |
| `[~]` | Esiste ma è incompleto o rotto. Accanto c'è il codice del problema (BUG-, SEC-, LC-, LIM-, REVIEW §) |
| `[ ]` | Non fatto. Accanto c'è il codice della funzione (NF-) e la fase |
| `[✗]` | Scartato dall'owner o impossibile, con il motivo e l'alternativa |

- **"→ Stato 04/10:"** sotto una voce spiega perché ha quel simbolo.
- **"(da verificare live)"** = i test passano, ma solo una prova su
  Discord vero può dare la certezza.
- I codici si trovano in `revisione/01-analisi/REVIEW.md`,
  `revisione/01-analisi/LIMITI.md` e
  `revisione/02-piano/NUOVE_FUNZIONI.md`.
- Cosa fare e in che ordine: le **issue di GitHub**, una milestone per
  fase (F1, F2, …).
- **Nessuna voce è stata tolta.** Dove Discord rende impossibile una
  funzione così com'era pensata, c'è scritta l'alternativa pianificata.
- Nessun `[x]` è ancora stato provato su Discord vero: il bot è in zero
  server.

### Conteggio per sezione

Numeri calcolati contando i simboli nel file (non a occhio).

| Sezione | `[x]` | `[~]` | `[ ]` | `[✗]` |
|---|---|---|---|---|
| §1 CORE SYSTEM | 14 | 5 | 0 | 1 |
| §2 SETUP & DASHBOARD | 6 | 1 | 1 | 0 |
| §3 PREMIUM SYSTEM | 10 | 2 | 0 | 0 |
| §4 VERIFY + FINGERPRINT + ANTI-ALT | 14 | 5 | 1 | 0 |
| §5 MODERATION | 3 | 12 | 0 | 0 |
| §6 AUTOMOD | 7 | 10 | 0 | 0 |
| §7 SECURITY SUITE | 6 | 27 | 1 | 0 |
| §8 LOGGING | 14 | 6 | 0 | 0 |
| §9 MUSIC | 7 | 7 | 0 | 3 |
| §10 ALERTS & SOCIAL | 0 | 7 | 3 | 0 |
| §11 BACKUP SYSTEM | 2 | 14 | 1 | 0 |
| §12 TEMPORARY VOICE CHANNELS | 5 | 3 | 0 | 0 |
| §13 TICKET SYSTEM | 18 | 2 | 0 | 0 |
| §14 UTILITY & SERVER MANAGEMENT | 7 | 12 | 2 | 0 |
| §15 LEVELS / ECONOMY / GILDE / CLASSIFICHE | 15 | 20 | 0 | 0 |
| §16 FUN & IMMAGINI | 12 | 3 | 2 | 0 |
| §17 OWNER / GLOBAL ADMIN | 9 | 2 | 0 | 0 |
| §18 ROUTER DEI CANALI E LOG SU FORUM | 4 | 2 | 1 | 0 |
| §19 DATI, PRIVACY E GDPR | 6 | 0 | 3 | 0 |
| §20 NUOVA STRUTTURA DEI COMANDI | 8 | 0 | 0 | 0 |
| §21 LINGUE E RICERCA DEI COMANDI | 4 | 1 | 1 | 0 |
| §22 FUNZIONI NUOVE, PRIMO GRUPPO | 15 | 0 | 2 | 0 |
| §23 FUNZIONI NUOVE, SECONDO GRUPPO | 12 | 2 | 3 | 0 |
| §24 PANNELLO WEB: CONFIGURAZIONE DEI SERVER | 0 | 5 | 2 | 0 |
| §25 MOTORE AI | 46 | 14 | 45 | 0 |
| B iYOKAI APPLICATION (user-installable) | 1 | 2 | 7 | 0 |
| C WEB PANEL (iYokai Panel) | 0 | 0 | 5 | 0 |
| D iYOKAI DESKTOP | 0 | 0 | 11 | 2 |
| E APPLICAZIONI DEL PROGETTO | 0 | 6 | 2 | 0 |
| **Totale** | **245** | **170** | **93** | **6** |

Totale voci: **514**.

---

# A. iYOKAI BOT (guild-installed)

## §1 CORE SYSTEM

- `[x]` 1.1 Multi-Tenant Engine — isolamento config per Guild ID
- `[~]` 1.1 Attivazione/disattivazione feature per server (check runtime)
  → **Stato 04/10:** funziona; resta una gara nella cache dei moduli (REVIEW §4 Core).
- `[✗]` 1.1 "Scaricamento moduli non utilizzati dalla memoria" — non
  fattibile: `load_extension` è per-processo, non per-guild. Sostituito
  dal check runtime. Vedi § Decisioni in PROGRESS.md
  → **Stato 04/10:** impossibile per come funziona discord.py; l'alternativa (controllo a runtime) è già fatta.
- `[x]` 1.2 Cog Manager — load / unload / reload
- `[x]` 1.2 Controllo stato attivazione modulo per server
- `[~]` 1.2 Evento `modules_updated` — `SetupView.save()` ora emette
  `interaction.client.dispatch("modules_updated", guild_id,
  module_name, active, changed_by)` per ogni modulo il cui stato è
  DAVVERO cambiato (stesso criterio già usato per lo storico Config
  Diff & Rollback) — infrastruttura pronta, nessun consumatore
  ancora (stesso schema di invite_tracker prima di Spam Trap): un
  futuro listener si registra con `@commands.Cog.listener()` su
  `on_modules_updated`
  → **Stato 04/10:** lo emette solo `/setup`; wizard, import, reset e rollback no (REVIEW §12).
- `[~]` **1.3 Memory Guard**
  → **Stato 04/10:** vedi la voce sui VoiceClient.
  - `[x]` Monitoraggio RAM ogni 60 secondi (psutil) — `core/memory_guard.py`, letto per davvero con `psutil.Process().memory_info().rss`, verificato con un test che legge la RAM vera del processo di test (nessun mock)
  - `[x]` Garbage collection forzata su soglia — evoluta a **quattro
    livelli** (NORMAL/WARNING/CRITICAL/EMERGENCY, BACKLOG.md §4):
    GC da WARNING in su, DM solo da CRITICAL (col cooldown di 30 min
    di prima), EMERGENCY bypassa sempre il cooldown
  - `[x]` Limitazione dimensione cache — `core/bounded_cache.py`
    (LRU vera, §1.5), collegata come consumatore reale a
    `core/invite_tracker.py`, che prima cresceva senza limiti con il
    numero di server
  - `[~]` Distruzione VoiceClient inutilizzati (canale rimasto senza
    membri umani)
    → **Stato 04/10:** scollega anche la radio 24/7 dai canali vuoti (LIM-44).
  - `[x]` Alert DM al proprietario al superamento soglia (con
    cooldown di 30 minuti tra un alert e l'altro, per non spammare
    l'owner ad ogni tick se la RAM resta alta)
- `[x]` 1.4 Database Layer — pool asyncpg, localhost, query asincrone
- `[x]` 1.5 Cache Layer (LRU con dimensione massima) —
  `core/bounded_cache.py`, politica LRU vera verificata esplicitamente
  (un GET conta come uso recente quanto un SET)
- `[~]` 1.6 Error Handler Globale — `on_error` in `main.py` ora copre
  anche le eccezioni non catturate nei listener di eventi (non solo
  gli slash command), con alert DM all'owner e cooldown per
  event_method
  → **Stato 11/10:** corretto (M 14.2, 14.3): permessi e controlli falliti → messaggio effimero chiaro e log INFO; errore dopo un `defer()` pubblico → segnaposto cancellato e followup effimero. (da verificare live)
- `[x]` 1.7 Logger Strutturato — JSON con rotazione
  (`core/json_log_formatter.py` + `RotatingFileHandler`, 10MB×5),
  nessuna nuova dipendenza. Convive con l'output testuale su stdout,
  non lo sostituisce
- `[x]` 1.8 Auto-Setup Engine
  - `[x]` Trigger `on_guild_join` + creazione record DB
  - `[x]` **Invio del messaggio di benvenuto all'ingresso** con
    fallback a catena (system_channel → primo canale scrivibile → DM
    owner). Bug reale trovato scrivendo il test: se l'invio sul
    system_channel falliva, la ricerca del canale alternativo poteva
    ritrovare lo stesso identico canale (quasi sempre incluso anche
    in `guild.text_channels`) e ritentarlo invece di passarne uno
    diverso — corretto escludendolo esplicitamente dalla ricerca
- `[x]` 1.9 Sharding (AutoShardedBot)
  → **Stato 04/10:** vale per il bot principale; i 5 bot musicali non hanno shard (LIM-33).

## §2 SETUP & DASHBOARD

- `[x]` 2.1 Pannello interattivo — select menu moduli per categoria (10 categorie, `/setup categoria:`), conferma, annulla (da verificare live)
  → **Stato 04/10:** BUG-2 corretto (`c9534fb`).
- `[x]` 2.1 Bottone "Reset configurazione" — `/config reset`, conferma
  a due passaggi (stesso schema di `/config rollback`), disattiva
  tutti i moduli e azzera tutte le settings, annullabile con
  `/config rollback` come qualunque altra voce di storico
  → **Stato 04/10:** reset ed esportazione toccano solo `guild_config`, non le tabelle dei singoli moduli (REVIEW §12). (da verificare live)
- `[x]` 2.2 Wizard di configurazione guidata passo-passo —
  `/setup-wizard`, un modulo curato alla volta (Moderazione, AutoMod,
  Logging, Greetings, Vocali temporanei, Ticket) con Attiva/Disattiva
  + Avanti/Indietro, a differenza di `/setup` (tutti i moduli in un
  solo select menu)
- `[~]` 2.3 Lingua per server — comando (`/config language show|set`)
  e colonna `language` ora collegati, con un piccolo registro di
  traduzioni (`core/i18n.py`) per un insieme limitato di stringhe
  generiche condivise. **Non un sistema i18n applicato a tutto il
  bot**: la stragrande maggioranza dei messaggi resta in italiano nei
  singoli cog — tradurre l'intero bot è un lavoro enormemente più
  grande di questa singola voce, onestamente non dichiarato completo
  → **Stato 04/10:** il comando salva la lingua ma nessun messaggio la legge. Lavoro completo: §21 (NF-06, D1).
- `[ ]` 2.4 Prefisso personalizzato — scartato: slash-command-only per
  non richiedere il Message Content Intent. **La colonna `prefix` in
  `guild_config` è morta e va rimossa o documentata come deprecata**
  → **Stato 04/10:** il motivo dello scarto non vale più: l'intent `message_content` è acceso. Alternativa pianificata: prefisso scelto dal server **solo per i comandi personalizzati** (§22, NF-09). I comandi del bot restano slash.
- `[x]` 2.5 Esporta configurazione — `/config export`, file `.json`
  con moduli/settings/lingua
  → **Stato 04/10:** esporta solo `guild_config` (REVIEW §12).
- `[x]` 2.6 Importa configurazione — `/config import`, sovrascrive IN
  BLOCCO (non un merge), validazione del formato prima di applicare
  → **Stato 04/10:** validazione completa dal 04/10 (`80322ff`, `965ab35`).
- `[x]` 2.7 Log delle modifiche di setup (audit trail: chi ha
  attivato/disattivato cosa e quando) — esteso oltre la richiesta
  originale con il **rollback**: `/config history` + `/config
  rollback <id>` con conferma a due passaggi (BACKLOG.md §11)
  → **Stato 04/10:** BUG-6 e BUG-32 corretti (`071504a`, `c2a9582`). (da verificare live)

## §3 PREMIUM SYSTEM

- `[x]` 3.1 Registry moduli + flag premium per modulo, tutto OFF di default
- `[x]` 3.2 Whitelist manuale per Server ID (add / remove)
- `[x]` 3.2 Punto unico di invalidazione del verdetto premium in memoria (#145) —
  `core/premium_cache.py`: whitelist, cassa, abbonamenti e flag del modulo lo
  chiamano; i log avanzati si registrano e dimenticano il verdetto subito (non
  dopo i 60 s). Il boost del server principale resta sul TTL.
- `[x]` 3.2 Comando per **elencare** i server in whitelist —
  `/owner whitelist-list`
- `[x]` 3.2 Attiva/disattiva natura premium di un singolo modulo
- `[x]` 3.2 Visualizza stato premium di **tutti** i server —
  `/owner premium-status-all`, un meccanismo di sblocco (whitelist/
  nitro boost/premium via cassa/abbonamenti per modulo) per riga, non
  solo un True/False complessivo
- `[~]` 3.3 Controllo runtime (`requires_module`)
  → **Stato 04/10:** 6 moduli "premium" (log avanzati, spam-trap, anti-nuke, anti-raid, global-ban, heatmap) non controllano il premium (REVIEW §12).
- `[x]` 3.1 Metodo sblocco: **Boost Nitro** sul server principale
  (`Member.premium_since`) — richiesto esplicitamente dall'utente
  ("per ora attivi solo... nitro boost..."). `core.premium.
  _guild_owner_boosts_main_guild`: l'OWNER del server richiedente
  deve avere un boost attivo su `config.MAIN_GUILD_ID` — sblocca
  TUTTI i moduli premium per quel server (come whitelist), non uno
  specifico. Assunzione presa per inferenza (nessun dettaglio più
  fine specificato): controlla l'owner del server, non un admin
  qualsiasi — da correggere se non è quello che si intendeva
- `[~]` 3.1 Metodo sblocco: 1.000.000 coin per modulo — **rimandato**
  su richiesta esplicita dell'utente ("per ora attivi solo... nitro
  boost, pagamento mensile|annuale"), non scartato: resta un metodo
  di sblocco previsto, solo non prioritario ora
  → **Stato 04/10:** in piano con il pagamento vero: §3 e NF-22.
- `[x]` 3.1 Metodo sblocco: pagamento **mensile o annuale** per
  modulo — l'utente ha aggiunto "mensile" a quanto originariamente
  previsto ("annuale" da solo). Nessun gateway di pagamento reale
  integrato (Discord non ne fornisce uno nativo utilizzabile da un
  bot normale, e questo progetto non processa mai pagamenti — stesso
  principio già in `core/premium_purchase_service.py` per il premium
  via cassa): il pagamento avviene FUORI dal bot, l'OWNER concede
  l'abbonamento a mano con `/owner premium-grant <server> <modulo>
  <mensile|annuale>` dopo averlo incassato — `/owner premium-revoke`
  e `/owner premium-subscriptions` completano il ciclo.
  `core.repositories.module_subscription_repo`, una riga per
  (server, modulo): a differenza di nitro boost/whitelist (sbloccano
  TUTTO), questo resta scoped al singolo modulo per design, come
  esplicitamente previsto dallo schema originale ("per modulo")
  → **Stato 04/10:** resta la concessione a mano; il pagamento vero è NF-22.
- `[x]` **Override temporaneo di fase ALPHA** — **voce nuova**, non
  nello schema originale, aggiunta su richiesta esplicita
  dell'utente: "mi raccomando per ora (dato che è in alpha, tutte le
  feature premium sono sbloccate per tutti)". `config.
  PREMIUM_ALPHA_UNLOCK_ALL` (default **true**): quando attivo,
  `guild_has_premium_access` sblocca SEMPRE tutto per tutti, a
  prescindere da whitelist/boost/abbonamento — controllato PRIMA di
  ogni altra condizione. Va impostato a `false` in `.env` quando
  l'alpha finisce, per far valere davvero i metodi di sblocco sopra
  → **Stato 04/10:** in produzione il default è spento (`576f155`, `2596734`).
- `[x]` 3.3 Ricarica delle flag premium dal DB all'avvio — **debito
  reale trovato in questa sessione**: `premium_module_flags` esiste
  già (`_apply_premium_toggle` in `cogs/utility/owner_premium.py`
  la scrive), ma nessun consumatore la rileggeva mai all'avvio, quindi
  lo stato premium impostato con `/owner premium-toggle` si perdeva
  ad ogni riavvio del bot anche restando persistito in tabella.
  Corretto con `core.premium.reload_premium_flags_from_database()`,
  chiamata da `main.py.setup_hook` **subito dopo** `load_all_cogs()`
  (non durante `Database.run_migrations`: a quel punto i moduli non
  sono ancora registrati e `registry.set_module_premium` solleverebbe
  `ValueError` "non registrato"). Righe di moduli non (più) registrati
  o diventati sempre-gratuiti vengono ignorate in silenzio, mai un
  crash all'avvio

## §4 VERIFY + FINGERPRINT + ANTI-ALT — Verify Base presente, il resto dipende dal Web Panel (fase F10)

- `[~]` 4.1 Verify Base
  → **Stato 04/10:** vedi le voci sotto.
  - `[~]` Button verify — `VerifyPanelView`, persistente (stesso
    pattern di ticket/vocali temporanei)
    → **Stato 11/10:** `defer` o modulo come prima risposta (LIM-9) — fatto.
    Aggiunti (#118): `/security verify opzioni` (ruolo «non verificato» all'ingresso, fino a 3 ruoli extra), `manuale`, `tentativi`, `statistiche` (VER-014, 015, 016, 030, 031).
    → **Stato 14/10 (r6, #118):** `/security verify tempi` (promemoria in DM con avviso di 15 s nel canale se i DM sono chiusi, tempo massimo con kick o ban, azione su chi non passa, verifica solo per account sospetti: VER-008, 009, 011, 012, 013); `/utility verifica` per il membro (VER-010).
  - `[x]` Reaction verify — `on_raw_reaction_add`. **Non supporta il
    captcha**: una reazione non è un'Interaction, non può aprire un
    Modal — combinazione rifiutata esplicitamente a `/verify setup`
    con un messaggio chiaro, non implementata a metà
  - `[x]` Captcha — testuale (domanda di somma generata al click,
    diversa ogni volta), solo in modalità button per il motivo sopra.
    Nessuna immagine: evita Pillow come nuova dipendenza solo per
    questo
    → **Stato 04/10:** debole contro i bot: captcha a immagine in §22 (NF-18).
  - `[x]` Controllo età account
  - `[x]` Controllo mutual servers — confermato il limite già noto:
    il bot vede solo quanti server IN CUI SI TROVA LUI contengono
    anche l'utente, non tutti i server dell'utente in assoluto
  - `[~]` Invite tracker (cache inviti + diff al join) — costruito
    come infrastruttura condivisa in `core/invite_tracker.py`
    (durante lo sviluppo di Spam Trap §7.3, che ne aveva bisogno per
    primo)
    → **Stato 04/10:** attribuzione sbagliata con ingressi simultanei; scarica gli inviti di tutti i server (LC-6).
- `[~]` 4.2 Verify Avanzato — modalità «Pagina web» di `/security verify setup` (NF-21, #92)
  → **Stato 16/10 (r8):** fatto. Il bottone dà un link personale firmato (15 minuti) alla pagina
  `/verifica/…` del pannello; lì gli stessi controlli e ruoli del bottone (`core/panel_bridge.py`).
  - `[x]` Impronta della rete (IPv4, /64 per IPv6): HMAC con sale segreto e id del server, mai l'IP
  - `[x]` Impronta del browser (User-Agent e lingua), stesso HMAC
  - `[~]` OAuth2 `identify`: non serve, il link è legato al membro dal bot (firma)
  - `[ ]` ISP / localizzazione: non raccolti (privacy, D19)
  - `[x]` Salvataggio: `verify_impronte` (0210), 30 giorni, nel registro dei dati
- `[x]` 4.3 Sistema Anti-Alt — NF-21 (#92), solo nello stesso server
  - `[x]` Database delle impronte e dei doppi (`verify_doppi`, 90 giorni)
  - `[x]` Match → avviso allo staff nel log della verifica, NESSUN ban automatico;
    `/security alt elenco`
  - `[x]` Livello: stessa rete e stesso browser = alto; stesso /64 IPv6 = medio; stesso IPv4 da solo = basso
    (CGNAT, scuole, famiglie: da solo non dice che è la stessa persona; 0211)
- `[x]` 4.4 Whitelist utenti — bypassa tutti i controlli, verificato
  che vinca anche in combinazione con la blacklist (vedi 4.5)
- `[x]` 4.5 Blacklist utenti — **vince sempre**, anche su un utente
  erroneamente anche whitelistato: verificato esplicitamente con un
  test dedicato, non assunto
- `[x]` 4.6 Log completo di ogni tentativo di verify — tabella
  `verify_attempts` + embed nel canale log configurato, per ogni
  esito (successo o fallimento)

## §5 MODERATION

- `[~]` 5.1 Warn, Kick, Ban, Tempban, Timeout, Unban, Untimeout
  → **Stato 04/10:** nessun controllo dei permessi (SEC-1); motivo senza massimo e caso creato prima dell'azione (LIM-8).
  → **Stato 14/10 (r6, #115):** azioni in massa `/modban massa ban|unban|kick`, `/mod massa timeout|warn` (fino a 50 utenti; ban anche per ID fuori dal server: MOD-001…006).
- `[~]` 5.1 **Softban** (ban+unban immediato per cancellare i messaggi)
  → **Stato 04/10:** SEC-1, LIM-8.
- `[~]` 5.1 **Mute via ruolo** — ruolo "Muted" auto-creato con
  overwrite su ogni canale esistente al momento della creazione
  (canali creati dopo non ereditano l'overwrite, limite noto)
  → **Stato 04/10:** SEC-1; il ruolo non copre thread, forum e canali nuovi (LIM-30).
- `[~]` 5.2 Case system — numerazione atomica per server, ricerca per
  numero, storico per utente
  → **Stato 11/10:** ordine azione→caso→log→DM e liste entro 4000 fatti. Aggiunti: storico per tipo, `/mod caso motivo|elimina|classifica-staff` (MOD-037, 039, 041, 042, 044).
  → **Stato 21/10 (r9):** `/mod caso attive` (MOD-013): tempban, timeout e lock a tempo in corso, dal primo che scade.
- `[~]` 5.3 Note utente
  → **Stato 11/10:** `/mod nota rimuovi|modifica|svuota` (MOD-054..056); l'elenco mostra il numero. Warn: `/mod avvisi togli|azzera|classifica` (MOD-028, 029, 031).
- `[~]` 5.4 Report system
  → **Stato 04/10:** motivo oltre 1024 caratteri: segnalazione persa (LIM-4).
- `[~]` 5.5 Lock / Unlock canale
  → **Stato 11/10:** ora scrive nel log di moderazione; motivo al massimo 512 caratteri.
  → **Stato 21/10 (r9):** `/mod lock durata:` (MOD-090, max 30 giorni): sblocco dallo scheduler, anche dopo un riavvio, con il permesso di prima; `unlock` o un nuovo lock annullano l'attesa.
- `[~]` 5.6 Slowmode
  → **Stato 11/10:** ora scrive nel log di moderazione.
- `[~]` 5.7 Clear avanzato con filtri
  → **Stato 11/10:** filtri nuovi (testo, link, inviti, embed, menzioni, ruolo, persone, fissati), canale a scelta, riga di log (MOD-069, 071, 073-079, 083, 084, 086, 088). Filtro allegati da riprovare con l'intent acceso (BUG-5).
- `[~]` 5.8 DM all'utente moderato
  → **Stato 04/10:** il DM parte prima dell'azione (LIM-8).
- `[~]` 5.9 **"Reason obbligatorio"** — `reason: str` (non più
  `str | None`) su warn/kick/ban/tempban/unban/timeout/softban/
  mute-role/unmute-role, con validazione minimo 3 caratteri.
  `/untimeout` (revoca, non azione punitiva) e `/lock` (stato del
  canale, non azione su un utente) restano con reason opzionale per
  scelta dichiarata, non nella lista esplicita dello schema
  → **Stato 04/10:** manca il massimo di 512 caratteri (LIM-8). Correzione al testo: `/untimeout` non ha il parametro motivo.
- `[~]` 5.10 Moderation logs su canale dedicato — `/mod-log-setup`,
  ogni azione pubblica una copia del case embed lì, oltre alla
  risposta nel canale del comando
  → **Stato 11/10:** `/lock`, `/unlock`, `/slowmode`, `/clear`, `/untimeout`, `/unmute` e la scadenza dei tempban scrivono nel log (M 1.8).
- `[x]` 5.11 **Ban temporaneo con rientro** — alla scadenza l'utente
  riceve l'invito per tornare e, al rientro, riprende i ruoli che
  aveva. L'invito e la data di fine si mandano in privato **prima**
  del ban (dopo, il bot non può più scrivergli); chi ha autorizzato il
  ripristino utenti viene riportato dentro in automatico (issue #138,
  fase F9)
  → **Fatto:** `/modban tempban modo:Fuori, con invito e ruoli al rientro` (invito
  senza scadenza e a un uso, DM prima del ban, ruoli ridati al rientro sotto il
  ruolo del bot). **Rientro automatico:** chi ha autorizzato il ripristino utenti (token valido fino alla fine del ban) rientra da solo alla scadenza con `join_user_via_oauth` (`tempban_stato.oauth_rientro`); gli altri usano l'invito. Un tempban con rientro non parte se non c'è né invito né autorizzazione. **Da provare live.**
- `[x]` 5.12 **Ban in isolamento** — per il tempo scelto l'utente resta
  nel server ma vede un solo canale, che dice quando finisce; alla
  scadenza riprende i ruoli di prima (issue #138, fase F9)
  → **Fatto:** `/modban tempban modo:Isolamento` (ruolo e canale «isolamento», canali
  nuovi nascosti, uscita e rientro non liberano, `/modban unban` libera prima).
- `[x]` 5.13 **Opzioni di moderazione** (MOD-010, 017, 057, 068) — `/mod opzioni
  imposta|dm|immuni`, un solo punto in `core/moderation_opzioni.py`: giorni di
  messaggi cancellati quando il ban non li dice; durata del timeout quando non
  la si scrive; DM spento per tipo di azione; ruoli immuni alla moderazione
  manuale (al massimo 25; li sceglie solo il proprietario, che resta libero di
  agire; anche nell'import della configurazione).

## §6 AUTOMOD

- `[~]` 6.1 Anti-badwords (via AutoMod nativo Discord, con merge a tre vie)
  → **Stato 04/10:** una parola oltre 60 caratteri rompe la sincronizzazione; `edit()` cancella le eccezioni messe a mano (LIM-29).
- `[~]` 6.2 Anti-invite (via AutoMod nativo, regex)
  → **Stato 04/10:** LIM-29.
- `[x]` 6.3b Messaggi modificati controllati di nuovo dai filtri lato bot (AMD-021, #116); la modifica non conta per l'anti-spam
- `[~]` 6.3 Anti-link generico (whitelist/blacklist domini) — lato
  bot (`core/automod_advanced_logic.py`), non regola nativa: Discord
  non supporta un elenco whitelist/blacklist di domini come trigger
  nativo. Modalità `off`/`whitelist`/`blacklist` per server,
  `/automod anti-link-mode` + `/automod anti-link-domain`
  → **Stato 04/10:** da riprovare con l'intent acceso (BUG-5); lista nera aggirabile (REVIEW §4).
- `[~]` 6.4 Anti-spam messaggi — soglia messaggi/finestra
  configurabile, finestra mobile in memoria
  (`core/automod_rate_tracker.py`, mai persistita: stato "caldo" di
  pochi secondi, stesso principio di `core/invite_tracker.py`),
  `/automod anti-spam-messages`
  → **Stato 04/10:** il valore `seconds` viene salvato e ignorato (REVIEW §4).
- `[~]` 6.5 Anti-spam emoji — soglia per SINGOLO messaggio (non nel
  tempo, a differenza di 6.4/6.6/6.10): conta emoji custom Discord +
  un intervallo unicode ampio (nessuna libreria `emoji` aggiunta come
  dipendenza — sotto-conteggio occasionale su emoji unicode rare
  accettato), `/automod anti-spam-emoji`
  → **Stato 04/10:** da riprovare con l'intent acceso (BUG-5).
- `[~]` 6.6 Anti-spam sticker — soglia sticker/finestra, stesso motore
  a finestra mobile di 6.4, `/automod anti-spam-sticker`
  → **Stato 04/10:** `seconds` ignorato (REVIEW §4).
- `[~]` 6.7 Anti-caps — percentuale di lettere maiuscole SUL TOTALE
  DELLE LETTERE (non sul totale caratteri: punteggiatura/numeri non
  contano né a favore né contro), soglia + lunghezza minima
  configurabili, `/automod anti-caps`
  → **Stato 04/10:** da riprovare con l'intent acceso (BUG-5).
- `[~]` 6.8 Anti-zalgo — conteggio segni diacritici unicode
  combinanti (categoria Mn/Me/Mc) oltre una soglia fissa (8, per
  inferenza: il testo normale — accenti italiani compresi — non la
  supera mai), `/automod anti-zalgo`
  → **Stato 04/10:** da riprovare con l'intent acceso (BUG-5).
- `[x]` 6.9 Anti-mass-mention — soglia di menzioni (utenti+ruoli) per
  messaggio, `@everyone`/`@here` contano sempre come sopra soglia,
  `/automod anti-mention`
  → **Stato 04/10:** (da verificare live)
- `[~]` 6.10 Anti-attachment-spam — soglia allegati/finestra, stesso
  motore a finestra mobile di 6.4/6.6, `/automod anti-attachment`
  → **Stato 04/10:** da riprovare con l'intent acceso (BUG-5); `seconds` ignorato.
- `[x]` 6.11 Filtri personalizzati per canale — **eccezione**
  (bypassa TUTTI i filtri avanzati insieme, non uno specifico per
  canale: altrimenti servirebbero N eccezioni per N filtri, complessità
  non richiesta), `/automod exempt-channel-add|remove`
- `[x]` 6.12 Filtri personalizzati per ruolo — stessa logica di 6.11,
  per ruolo, `/automod exempt-role-add|remove`
- `[x]` 6.13 Azioni multiple configurabili (delete + warn + mute +
  ban) — per violazione, con "delete" sempre eseguito per primo se
  presente; rete di sicurezza: mute/ban non si applicano mai
  all'owner o a chi ha `manage_guild`/administrator (delete/warn
  restano, poco invasivi) — scelta di sicurezza per inferenza, non
  richiesta esplicitamente. `/automod actions-set` + `/automod
  mute-duration` (durata del timeout, condivisa da ogni azione
  "mute")
- `[x]` 6.14 Log delle azioni automod — riga persistente per ogni
  violazione (`automod_action_log`) + embed opzionale in un canale
  dedicato, `/automod log-channel` + `/automod status` (riepilogo
  configurazione)
- `[x]` 6.16 Filtri in più (#116, r6): messaggi ripetuti, troppo corti, link e menzioni nel tempo (`/automod filtri messaggi`, AMD-001, 004, 006, 007), embed e inoltri letti dai filtri e tipi di file vietati (`contenuto`, AMD-019, 020, 022), canali solo media o senza allegati (`canale-media`, AMD-023, 024), azione kick in `actions-set` (AMD-041)
- `[x]` 6.17 Parole vietate con varianti (#116, r10, AMD-014): filtro lato bot con normalizzazione (maiuscole, cifre e simboli al posto delle lettere, lettere simili di altri alfabeti, accenti, caratteri invisibili, markdown, separatori, lettere ripetute, lettere censurate con `*`/`█`, parola spezzata a metà, testo girato con U+202E, parola divisa in più messaggi brevi di fila), lista di base di insulti d'odio it/en in `data/automod_parole_odio.txt` accesa di base (spegnerla chiede `conferma`), parole proprie e lecite dell'admin (una voce di base non può diventare lecita) (`/automod odio base|parola|nomi|prova|stato`), cancella il messaggio, conta nella scala di escalation e scrive nel log AutoMod; nickname e nomi visualizzati ripuliti all'ingresso e al cambio (`core/automod_parole_logic.py`, `cogs/automod/parole_odio.py`)
- `[~]` 6.15 Smart AutoMod Escalation Ladder (BACKLOG.md §11) — scala
  di severità crescente **nel tempo** in base a quante volte un
  utente ha già triggerato l'AutoMod nativo, con reset dopo un
  periodo configurabile di buona condotta. Concettualmente diversa
  da 6.13 (che è più azioni insieme su UN trigger, non su trigger
  ripetuti nel tempo) — voce nuova, non una ridefinizione di 6.13
  → **Stato 04/10:** una violazione conta più volte (LIM-32).
  → **Stato 21/10 (M 1.10, r9):** conteggio corretto (M 2.7); con
  `/security escalation enable warn_manuali:True` anche i warn dati a mano
  (`/mod warn`, anche in massa) salgono la scala (migrazione 0250); solo con
  azioni che il moderatore può fare da sé, mai kick o ban dai warn in massa (D29).

## §7 SECURITY SUITE — presente, con bug aperti su anti-raid, anti-nuke e spam-trap (fase F1)

- `[~]` 7.1 Anti-Raid — `cogs/security/anti_raid.py`, modulo CANDIDATO
  PREMIUM (come Spam Trap). Logica di valutazione pura in
  `core/security_logic.py` (`evaluate_join`), finestra mobile in
  memoria per il join rate (`core/security_rate_tracker.py`, mai
  persistita — stesso principio di `core/automod_rate_tracker.py`).
  Comandi: `/antiraid enable|join-rate|account-age|username-check|
  avatar-check|lockdown-action|alert-channel|status|quarantine-hold|rilascia`
  → **Stato 14/10 (r6, #117):** gruppo di primo livello `/antiraid` (D25). Filtri all'ingresso con azione propria anche fuori dal raid (`filtro-ingresso`, `nomi-vietati`: SIC-023, 024, 026, 027, 028; il bio del profilo non è leggibile dai bot, si guardano nome e nome visualizzato), soglia sui soli sospetti, account creati vicini e nomi simili (`join-rate conta`, `segnali`: SIC-029, 030, 031), kick o ban al raid anche su chi è entrato prima (SIC-032, 033), `ping-ruoli` (SIC-034), `elenco` (SIC-035), segnale di rete (SIC-037), `segnala` (SIC-038). Resta SIC-036.
  → **Stato 04/10:** BUG-12.
  → **Stato 11/10 (#59, #117, ramo `feat/sicurezza-audit`):** un avviso
  solo per episodio; ruolo "Quarantined" preparato all'attivazione e
  sempre senza permessi (SIC-004, anche se esisteva già a mano); blocco
  della quarantena (SIC-003) e `rilascia` (unico, in
  `core/security_quarantine.py`: per caso, tiene la quarantena se
  l'utente ha altri casi); soglie con limiti; avvisi sui ruoli del bot
  (SIC-022). `quarantine-hold` e il rilascio col blocco acceso li cambia
  solo chi gestisce (proprietario ed extra owner).
  - `[~]` Join rate limit (finestra scorrevole) — conteggio join
    guild-wide (non per singolo utente: una `chiave fittizia
    user_id=0`, mai un ID reale su Discord) nella finestra configurata
    → **Stato 04/10:** conta anche i bot aggiunti dagli admin (BUG-12, LC-6).
  - `[~]` Account age check all'ingresso — età minima configurabile
    → **Stato 04/10:** un solo ingresso fa scattare il blocco completo (BUG-12).
  - `[~]` Rilevamento pattern username — regex per inferenza
    (lettere+4 o più cifre finali, tipico di un account generato in
    massa da un raid-bot), disattivabile
    → **Stato 04/10:** BUG-12.
  - `[~]` Rilevamento pattern avatar — assenza di un avatar
    personalizzato, disattivabile (nessun confronto tra avatar
    diversi: solo "ha/non ha un avatar", per semplicità)
    → **Stato 04/10:** BUG-12.
  - `[~]` Lockdown automatico — tre modalità configurabili:
    quarantena, innalzamento del `verification_level` del server, o
    entrambe
    → **Stato 04/10:** il livello di verifica resta alto per sempre (BUG-12).
  - `[~]` Quarantine role — creato automaticamente al primo utilizzo
    (overwrite su ogni canale, stesso schema del ruolo Muted di
    `cogs/moderation/softban_mute.py`, ma un ruolo SEPARATO — un
    sospetto raider appena entrato non è lo stesso caso di un membro
    esistente sanzionato)
    → **Stato 04/10:** più ruoli creati con ingressi simultanei (BUG-12); buchi del ruolo (LIM-30).
  - `[~]` Alert staff — DM all'owner + canale di alert opzionale
    (condiviso con Anti-Nuke)
    → **Stato 04/10:** un DM per ogni ingresso (BUG-12).
- `[~]` 7.2 Anti-Nuke — `cogs/security/anti_nuke.py`, modulo
  CANDIDATO PREMIUM. L'autore di un evento non è mai nel payload
  dell'evento gateway: risolto sempre via audit log
  (`guild.audit_logs`, stesso approccio già usato per il cleanup
  webhook/inviti di Spam Trap), con una finestra di tolleranza di 10s
  tra evento e voce di audit log (`core/security_audit.py`). Comandi:
  `/security antinuke enable|limits|trusted-add|trusted-remove|
  trusted-list|punish-action|recovery|status|guardie|casi|rilascia`
  → **Stato 04/10:** può punire il bot stesso (BUG-11).
  → **Stato 21/10 (#59, r9):** `punish-action ripiego:` espelle o banna chi
  quarantena o ruoli tolti non hanno fermato (spento di base).
  → **Stato 11/10 (#59 riga 3.5, #117):** due soglie per categoria (breve
  e oraria, SIC-001); punizione di default la quarantena (SIC-002); una
  sola punizione per attacco, con un caso numerato (`casi`, SIC-017); fiducia
  a livelli: fidato o extra owner, per azione, per categoria di canali, per
  webhook (SIC-018/019/020), con UNA fonte (`trust_entries`) e regole nel core;
  guardie su permessi dei ruoli, ruoli ai membri, link, bot aggiunti, prune
  (SIC-005…010, 025). Soglie, punizione, recovery e fiducia le cambia solo
  chi gestisce.
  - `[~]` Protezione canali (create/delete di massa) — soglia/finestra
    configurabile per categoria
    → **Stato 04/10:** BUG-11; registro letto una volta sola (LIM-31).
  - `[~]` Protezione ruoli — stessa logica, categoria separata
    → **Stato 04/10:** BUG-11, LIM-31.
  - `[~]` Protezione webhook — `on_webhooks_update`, stessa logica
    → **Stato 04/10:** BUG-11, LIM-31.
  - `[~]` Protezione emoji / sticker — `on_guild_emojis_update` +
    `on_guild_stickers_update`. **Soundboard escluso**: limite reale
    della libreria discord.py 2.7 in uso (nessun evento gateway
    dedicato esposto), non una scelta di scope
    → **Stato 04/10:** BUG-11, LIM-31. Correzione al testo: discord.py 2.7.1 **ha** gli eventi soundboard (REVIEW §12).
  - `[~]` Rilevamento mass ban / mass kick — `on_member_ban` diretto;
    per il kick, `on_member_remove` verifica PRIMA nell'audit log se
    si tratta davvero di un'espulsione (altrimenti ogni leave
    volontario alimenterebbe per errore il contatore)
    → **Stato 04/10:** BUG-11, LIM-31.
  - `[~]` Recovery automatico (ricreazione canali/ruoli) — best-effort,
    senza uno snapshot separato persistito: `on_guild_channel_delete`/
    `on_guild_role_delete` ricevono l'oggetto Discord com'era
    nell'ultima cache del client PRIMA della rimozione, quindi
    nome/permessi/posizione sono ancora leggibili al momento della
    ricreazione
    → **Stato 04/10:** ricrea solo canali testuali, senza posizione; le prime 3 cancellazioni non vengono recuperate (REVIEW §12, #30); canali offuscati (LIM-38).
  - `[x]` Whitelist utenti/bot fidati — `trusted_ids`, esenta
    completamente dai controlli (nessuna azione, nessun log)
  - **Rete di sicurezza**: l'autore non viene MAI punito se è il
    proprietario del server (stessa filosofia della rete di sicurezza
    già in AutoMod §6.13, ma invertita: lì è la vittima potenziale ad
    essere protetta, qui l'owner non può mai essere il "nuke" da
    contrastare per errore)
- `[~]` 7.3 **Spam Trap** — completo (solo il ban globale via
  fingerprint resta escluso, per la dipendenza esplicita da §4 sotto)
  → **Stato 04/10:** vedi le voci sotto. BUG-22, BUG-24, BUG-25 corretti il 04/10.
  → **Stato 11/10 (#59 righe 3.9–3.13, #117):** un solo giro per utente
  (nessun DM, caso o propagazione doppi); trappola e log su canali diversi;
  avvisi su Bannare membri, thread e lettura; transcript con tetto di 40
  messaggi; un appello accolto toglie anche i ban propagati; se la sequenza
  salta la propagazione non resta orfana.
  → **Stato 21/10 (SIC-040, r9):** `/security spamtrap punizione:` ban (di base,
  sequenza completa), kick (DM prima), timeout di un giorno, solo cancellazione,
  o «decide lo staff» (log con bottoni Ban e Kick persistenti, permesso e
  gerarchia controllati, caso a nome di chi preme).
  - `[x]` `/setup` con selezione canale trappola e canale log — via
    parametri `discord.TextChannel` opzionali (rendono nativamente
    come selettore canale di Discord, non un menù a tendina
    testuale, ma stessa funzione)
  - `[~]` Creazione automatica `#spam-trap` (visibile a everyone, no
    inviti, no webhook) se non selezionato
    → **Stato 04/10:** tetto dei canali non gestito (LIM-36).
  - `[~]` Creazione automatica `#spam-log` (solo administrator) se
    non selezionato
    → **Stato 04/10:** LIM-36.
  - `[x]` Embed di presidio in `#spam-trap`, rosso, in inglese, con
    header grande "DO NOT WRITE IN THIS CHANNEL"
  - `[x]` Embed informativo in `#spam-log`, colore tenue, in inglese
  - `[~]` Sequenza fissa: cattura contenuto → **DM PRIMA del ban** →
    ban con `delete_message_seconds` → purge supplementare → cleanup →
    log
    → **Stato 04/10:** da riprovare con l'intent acceso (BUG-5).
  - `[~]` Cancellazione messaggi 30 giorni (indicizzazione
    `message_id` in DB; nativo copre max 7 giorni, la purge
    supplementare copre 7-30)
    → **Stato 04/10:** la tabella degli indici cresce: la pulizia esiste ma non viene mai chiamata (PERF-3).
  - `[~]` Log con: tag, user ID, data creazione account, data join,
    data ban, codice invito usato, **creatore dell'invito**, contenuto
    che ha fatto scattare la trappola, numero messaggi cancellati per canale
    → **Stato 04/10:** manca la data del ban; la data di ingresso è quasi sempre assente (REVIEW §12); campo oltre 1024 (LIM-20).
  - `[x]` Cleanup webhook creati dall'utente (via audit log)
  - `[x]` Cleanup inviti creati dall'utente (via audit log)
  - `[~]` Ban appeal: DM → thread privato in `#spam-log`, con bottoni
    staff (Unban/Reject/Reply), rate limit 1 appello/24h. Bottoni su
    una `View` NON persistente (timeout 7 giorni) — scelta dichiarata,
    non equivalente ai pannelli persistenti di ticket/vocali: un
    appeal è per natura più breve, non vale la complessità di bottoni
    persistenti per-caso dinamici
    → **Stato 04/10:** i bottoni muoiono a ogni riavvio (LC-5).
  - `[~]` **Transcript HTML** — timestamp, nome+nickname, contenuto
    con escaping rigoroso anti-XSS, allegati immagine rigenerati come
    thumbnail WebP (Pillow, `core/image_thumbnail.py`), avatar
    dell'utente mostrato una volta per report nell'intestazione. Le
    thumbnail sono incorporate come data URI dentro l'HTML stesso —
    non riospitate da nessuna parte, coerente con "mai riospitare il
    file originale"
    → **Stato 04/10:** da riprovare con l'intent acceso (BUG-5); nessun controllo di peso (LIM-20).
  - `[ ]` Opzione ban globale via fingerprint/alt-detection — dipende
    da §4.2/§4.3 Anti-Alt (raccolta OAuth2 "identify" + IP al momento
    del VERIFY, prima che l'account si comporti male), non costruito.
    Resta bloccato per un motivo strutturale, non solo di tempo: un
    account appena bannato dalla trappola non collaborerebbe mai a un
    flusso OAuth2 dopo il fatto, quindi il fingerprint andrebbe
    comunque raccolto prima, al verify — la stessa dipendenza di
    sempre
    → **Stato 04/10:** in piano con NF-21.
  - `[~]` **Ban globale via propagazione cross-server** — SPEC.md
    §7.6 sotto: NON è il ban globale via fingerprint di cui sopra
    (nessuna euristica su account diversi/alt), ma la propagazione
    reale di un ban Spam Trap sullo STESSO account Discord verso ogni
    altro server aderente. Costruito su richiesta esplicita
    dell'utente, come sostituto concretamente realizzabile oggi
    → **Stato 04/10:** vedi 7.6.
- `[~]` 7.4 Permission Auditor + alert permessi pericolosi —
  `/permission-heatmap` (ruoli con permessi critici + quanti membri
  li possiedono) + DM diretto all'owner quando un membro riceve un
  ruolo con permesso critico
  → **Stato 04/10:** embed oltre 4096 caratteri con molti ruoli (LIM-14).
- `[~]` 7.5 Security Score / health check configurazione server —
  `cogs/security/security_score.py`, comando `/security-score`.
  Modulo SEMPRE GRATUITO (è un check di lettura, non una protezione
  attiva). Punteggio 0-100 (`core.security_logic.
  compute_security_score`, logica pura testata a sé) con pesi scelti
  per inferenza — nessuna formula "ufficiale" esiste per un security
  score di un server Discord: 2FA staff, livello di verifica, quota
  di membri amministratori, Anti-Raid/Anti-Nuke attivi, AutoMod
  attivo — ognuno con un consiglio azionabile in caso di penalità
  → **Stato 04/10:** la risposta è pubblica nel canale (LC-8).
- `[~]` 7.6 **Ban globale via propagazione cross-server** —
  `cogs/security/global_ban.py` (`/global-ban enable|disable|status`),
  richiesto esplicitamente dall'utente come soluzione al gap di 7.3
  sopra. Modulo CANDIDATO PREMIUM.
  → **Stato 04/10:** `/global-ban enable` salta il controllo premium (REVIEW §4).
  → **Stato 11/10 (#117 SIC-044, 046):** due direzioni (invia, ricevi);
  `/security globalban controlla` (solo il numero di server); la revoca
  (`revoca_ban_propagati`, anche da `/modban unban`) chiude solo le righe
  degli unban riusciti, lascia il ban che un'altra sorgente tiene ancora e
  ferma una propagazione in corso; lo staff (amministratore, moderatore, bot,
  ruolo staff della Spam Trap) del server di arrivo non viene bannato;
  pulizia del registro una volta per giro, con indici.

  **Perché non è "il" ban globale via fingerprint di §4.3**: quello
  risolve un problema diverso — riconoscere che due ACCOUNT DIVERSI
  sono la stessa persona (un alt), cosa che richiede una raccolta
  IP/OAuth2 "identify" fatta al momento del VERIFY, prima che
  l'account si comporti male (§4.2, non costruito). Un account appena
  bannato dalla Spam Trap non collaborerebbe mai a un flusso OAuth2
  dopo il fatto — quella raccolta non potrebbe mai avvenire a ban
  avvenuto, quindi il vero fingerprint resta strutturalmente bloccato
  su §4.2, non solo per mancanza di tempo.

  **Cosa fa invece, concretamente realizzabile oggi**: propaga un ban
  scattato dalla Spam Trap (§7.3) sullo STESSO account Discord (stesso
  user ID, nessuna euristica di somiglianza) verso ogni altro server
  che condivide il bot E ha aderito alla stessa rete — reciprocità
  esplicita: un server che non ha attivato il modulo non riceve mai
  un ban deciso altrove, né i suoi ban vengono propagati. L'opt-in
  riusa l'attivazione modulo già esistente
  (`db.is_module_active_for_guild`/`set_module_active_for_guild` su
  `guild_config`) — nessuna nuova tabella di configurazione, solo un
  log di propagazione (`core/repositories/global_ban_repo.py`,
  `global_ban_log`) per `/global-ban status`. Logica pura di
  decisione isolata in `core/global_ban_logic.py`
  (`should_propagate_ban`), stesso pattern di ogni altro modulo di
  questa sezione. Ban con `discord.Object(id=user_id)` (funziona anche
  se l'utente non è mai stato membro del server target — un ban
  preventivo legittimo). Best-effort per server: un `Forbidden`/
  `HTTPException` su UN target (permessi insufficienti, già bannato
  lì) non blocca la propagazione verso gli altri. Integrato nella
  sequenza di ban della Spam Trap (subito dopo il ban reale, prima
  della creazione del case) con un campo aggiuntivo nell'embed di log
  quando la propagazione avviene.

## §8 LOGGING — eventi presenti; log dei messaggi e canali divisi da fare (fase F6)

- `[x]` 8.1 Member join
- `[x]` 8.2 Member leave
- `[x]` 8.3 Member ban / unban
- `[~]` 8.4 Member update — ruoli e nickname, nello stesso evento
  senza uscire in anticipo se solo uno dei due cambia
  → **Stato 04/10:** 42 ruoli cambiati insieme rompono l'embed (LIM-19).
- `[x]` 8.5 Role create / delete
- `[x]` 8.6 Role **update** (nome, colore, permessi, hoist,
  mentionable) — `cogs/logging/advanced_logs.py`, livello Premium
  (vedi 8.18 sotto)
- `[~]` 8.7 Channel create / delete / update — update copre nome,
  categoria, topic, nsfw, slowmode, posizione; il diff degli
  overwrite di permesso canale-per-canale resta escluso per scelta
  di scope (complessità non richiesta per un log, non un limite
  tecnico)
  → **Stato 04/10:** spostare un canale genera N messaggi (REVIEW §4); canali offuscati (LIM-38).
- `[~]` 8.8 Invite create / delete / use — "use" risolto con un nuovo
  metodo, `invite_tracker.resolve_join_invite(guild, member_id)`
  (`core/invite_tracker.py`), non con `find_used_invite()`
  direttamente: quest'ultimo muta la propria cache ad ogni chiamata
  (aggiorna l'istantanea per il prossimo confronto), quindi due
  moduli indipendenti (Spam Trap e il Logging Avanzato) che lo
  chiamassero ciascuno per proprio conto sullo stesso evento di join
  darebbero `None` a chi arriva secondo. `resolve_join_invite()`
  risolve la corsa con un lock + cache per coppia (server, membro):
  la prima chiamata per un dato join fa il lavoro reale, ogni altra
  chiamata per lo stesso join — da qualunque modulo, in qualunque
  ordine (`discord.py` non garantisce un ordine tra i listener di
  Cog diversi sullo stesso evento) — riceve la stessa risposta senza
  un secondo fetch/diff. Spam Trap aggiornato per usare lo stesso
  metodo
  → **Stato 04/10:** LC-6.
- `[~]` 8.9 **Voice state**: join / leave / move / mute / deafen —
  "mute"/"deafen" semplificato allo stato EFFETTIVO (server-mute/
  deafen oppure self-mute/self-deafen), non le quattro variabili
  distinte di discord.py, scelta dichiarata per un log leggibile
  → **Stato 04/10:** il mute volontario è scritto come "mutato dal server" (REVIEW §4).
- `[x]` 8.10 Webhook create / update / delete — l'evento gateway
  nativo (`on_webhooks_update`) non distingue le tre azioni né dice
  l'autore: risolto via audit log entro una finestra di tolleranza,
  stesso principio già usato per l'autore in Anti-Nuke (§7.2)
- `[x]` 8.11 Emoji create / delete / update
- `[x]` 8.12 Sticker create / delete / update
- `[x]` 8.13 Soundboard create / delete / update — dagli eventi gateway
  di discord.py 2.7.1 (`on_soundboard_sound_create/update/delete`),
  ascoltati da `cogs/logging/advanced_logs.py`. Il giro periodico
  sull'audit log e il servizio `soundboard_log_service` sono tolti (M 5.7, LIM-31)
- `[x]` 8.14 Thread events — create/delete/update (nome, archiviato,
  bloccato)
- `[x]` 8.15 Server update (impostazioni guild) — nome, icona,
  livello di verifica, canale AFK, canale di sistema, filtro
  contenuti espliciti
- `[x]` 8.16 Message delete / bulk delete / edit — `cogs/logging/message_logs.py`
  (NF-02, issue #73): embed con autore, canale e testo (campi 1024,
  descrizione 4096); cancellazione in blocco = un riepilogo con un
  file `.txt` sotto i 10 MiB; messaggi dei bot, canali, utenti e
  prefissi, ruoli ed espressioni regolari (al massimo 5, solo schemi a
  basso costo: una sola ripetizione senza limite, niente `{n,m}`, al massimo 4 `?`; uno schema che supera 50 ms si disattiva) ignorabili con `/log ignora` (LOG-022, LOG-024, migrazione
  0103); una modifica non si scrive se il testo di prima va ignorato; categorie, thread e bot già ignorati (LOG-021, LOG-023). Fa parte del Logging
  Avanzato (premium). Un messaggio fuori dalla cache di discord.py si
  segnala senza contenuto; la modifica di un messaggio fuori cache non
  si vede
- `[x]` 8.18 Catalogo log (#119): timeout dati e tolti anche dal menu di Discord (`basic_logs.py`,
  LOG-009); cambio di nome utente, nome visualizzato e avatar (`on_user_update`, LOG-007, LOG-008);
  palchi aperti, modificati, chiusi nel tipo «voce» (`advanced_logs.py`, LOG-013).
  Giro r7: inviti Discord scritti nei messaggi (`message_logs.py`, LOG-005); messaggi fissati e
  tolti, chi scollega o sposta a forza in vocale (`on_audit_log_entry_create`, serve «Visualizzare
  il registro»; Discord unisce gli spostamenti ripetuti dello stesso moderatore e si scrive solo il
  primo; il registro non dice chi è stato spostato, lo dice il log della voce) (LOG-006, LOG-012);
  `/log archivio-canale canale: messaggi:` (fino a 20.000, file sotto i 10 MiB, con i cancellati
  dell'ultima ora tenuti solo in memoria, 100 per canale; serve poter leggere il canale) (LOG-027,
  LOG-030). Resta: LOG-029 (archivio di un utente su 3 giorni a ogni sanzione: servirebbe tenere
  su disco il testo di tutti i messaggi, scelta di privacy da fare)
- `[x]` 8.19 Ogni evento acceso o spento (LOG-017): `/log eventi`, un menu con 24 interruttori
  e le scelte rapide «Tutto», «Niente», «Predefinito» (tutto tranne microfono e audio spenti da
  soli); senza scelte tutto acceso come prima. Migrazione 0180 (`log_eventi_spenti`)
- `[~]` 8.17 Log eventi unificato multi-indice (BACKLOG.md §3) — ogni
  evento (8.1-8.5, 8.6-8.15 ora costruiti) salvato UNA VOLTA nel DB,
  consultabile da più angolazioni (membro, canale, ruolo, tempo).
  `/logs user`, `/logs channel`, `/logs export` (JSON completo).
  Retention differenziata: 30gg Free, 180gg Premium, pulizia
  giornaliera automatica. **Proiezione su Forum Discord per
  canali/case NON costruita** — decisione esplicita nell'analisi
  (BACKLOG.md §3): "membri" è l'unica dimensione ad alta cardinalità
  che avrebbe fatto esplodere i thread durante un raid, "canali" e
  "case" restano un'estensione futura separata
  → **Stato 04/10:** `/logs user|channel` oltre 4096 caratteri (LIM-15). Correzione al testo: la ricerca "per ruolo e per tempo" non esiste (REVIEW §12).
- `[~]` 8.18 Distinzione log semplificato `[Free]` vs completo
  `[Premium]` — due moduli distinti: `cogs/logging/basic_logs.py`
  (`MODULE_LOGGING`, 8.1-8.5, SEMPRE GRATUITO) e
  `cogs/logging/advanced_logs.py` (`MODULE_LOGGING_ADVANCED`,
  8.6-8.15, CANDIDATO PREMIUM). Stesso canale di log configurato una
  volta con `/logs-setup` — è l'attivazione del secondo modulo a
  decidere se gli eventi avanzati iniziano ad arrivarci, non un
  secondo comando di setup
  → **Stato 04/10:** il modulo avanzato non controlla il premium (REVIEW §12).

## §9 MUSIC — da correggere secondo la decisione D10 (fase F2); comandi ridotti (deliberatamente)

**Stato al 04/10/2026 e disegno deciso (D10).** Leggendo il codice e
wavelink si è visto che oggi **tutti i nodi Lavalink sono collegati con
il bot principale** (`cogs/music/player.py`). I 5 bot musicali usano
quella sessione, quindi Lavalink si presenta a Discord con l'identità
sbagliata: quasi certamente i worker non producono audio (LIM-40). Va
provato live, ma il disegno cambia comunque così:

- un `wavelink.Node` **per ogni bot** e per ogni server Lavalink, con
  identificatore proprio;
- ogni player nasce sul nodo del suo bot (scelta esplicita, mai
  automatica);
- ogni nodo si collega in un task suo, con tentativi limitati;
- un bot per **canale vocale**, non per server;
- Lavalink 4.2.0 o successivo (cifratura vocale DAVE, obbligatoria dal
  01/03/2026) e `wavelink>=3.5.1`;
- i brani locali della radio passano solo dal nodo locale;
- la radio non viene scollegata dai canali vuoti.

Dettaglio e ordine: milestone "F2 — Musica" su GitHub,
`revisione/02-piano/MODIFICHE_ESISTENTE.md` §8.

**Nota storica** (stato prima del 04/10): costruita l'architettura multi-istanza (bot
principale + 5 worker nello stesso processo, instradamento
automatico) e un set di comandi RIDOTTO rispetto allo schema
originale — deliberatamente, su richiesta esplicita dell'utente:
"non voglio filtri audio, non voglio appesantire il bot per niente,
tanto la gente ormai raramente li usa". **Aggiornamento**: l'utente
ha poi chiesto esplicitamente di completare comunque clear, shuffle,
i due loop (traccia/coda) e nowplaying con barra di avanzamento —
fatti in questa sessione. Restano invece **permanentemente
descoperti** (non solo rimandati — richiesta esplicita, mai da
rimettere in lista): search distinta da play, forceskip, remove,
move, seek, lyrics. Filtri audio/DJ-role/voteskip restano scartati
per lo stesso motivo di sempre (9.6/9.7/9.8). Comandi finiti oggi:
play, skip, stop, pause, resume, queue, clear-queue, shuffle, loop
track/queue, nowplaying (con barra), volume (con up/down oltre a
impostare un valore), disconnect, nonstop. **Bug reale trovato e
corretto qui**: il primo tentativo chiamava il nuovo comando
`/clear` — nome già usato da `/clear` di moderation (cancellazione
messaggi) — e un comando slash duplicato fa fallire la
REGISTRAZIONE dell'intero cog, non solo di quel comando;
`core/cog_manager.load_all_cogs` cattura e LOGGA ogni eccezione di
`setup()` per singolo cog senza farla risalire, quindi l'intero
modulo Music si sarebbe disattivato in silenzio, notato solo
rilanciando `scripts/generate_command_list.py` sull'intero albero
comandi reale (il conteggio è sceso da 171 a 153 comandi e la
categoria Music è sparita del tutto) — mai scoperto dai test perché
i test unitari istanziano `MusicCog` da solo, senza mai unire il suo
albero comandi a quello di TUTTI gli altri cog insieme come fa il
bot vero. Rinominato in `/clear-queue`.

**Correzione di comprensione dell'utente su YouTube/Spotify (§9.5)**:
i nodi Lavalink pubblici hanno comunque Spotify (plugin LavaSrc
spesso già presente); è YouTube che su molti nodi pubblici non
funziona più/è spesso rotto — il fallback pinnato sul nodo locale
esisteva finora solo per query Spotify (`is_spotify_query`), non per
YouTube: **nessuna modifica di codice fatta qui**, resta un punto da
eventualmente rivalutare se emergono segnalazioni concrete di
ricerche YouTube vuote sui nodi pubblici, non affrontato in questa
sessione perché non richiesto esplicitamente.

- `[~]` 9.1 Multi-VoiceClient manager (5 applicazioni separate) —
  `core/music_worker_bot.py`, 5 istanze nello stesso processo
  (non 5 processi separati — vedi PROGRESS.md per il perché)
  → **Stato 04/10:** i worker usano la sessione Lavalink del bot principale: quasi certamente nessun audio (LIM-40). (da verificare live)
- `[~]` 9.2 Assegnazione istanza libera per canale (tabella
  `music_sessions`, logica "se bot1 occupato → bot2") —
  `core/music_fleet.py` + `core/repositories/music_session_repo.py`
  → **Stato 04/10:** oggi è un bot per **server**, non per canale (REVIEW §12).
- `[~]` 9.3 Coda indipendente per canale vocale — ogni `wavelink.
  Player` (uno per worker/server) ha la propria coda, indipendente
  dalle altre per costruzione
  → **Stato 04/10:** un secondo canale nello stesso server condivide bot e coda (REVIEW §12).
- `[x]` 9.4 Comandi: play, skip, stop, pause, resume, queue,
  clear-queue, shuffle, loop track, loop queue, nowplaying (con
  barra di progresso), volume, disconnect. **Limite playlist**:
  `/play` su un
  link a una playlist (es. Spotify) aggiunge al massimo
  `MAX_PLAYLIST_TRACKS` = 750 tracce per singolo link (richiesto
  esplicitamente dall'utente — una playlist enorme non deve poter
  riempire la coda di un server all'infinito in un colpo), il resto
  viene scartato con un avviso esplicito nel messaggio di conferma.
  **Shuffle genuinamente randomico**: `/shuffle` delega direttamente
  a `wavelink.Queue.shuffle()`, che usa `random.shuffle` della
  libreria standard di Python (Fisher-Yates non polarizzato) — non
  un "mix" con pattern nascosti come capita con alcuni bot musicali
  (preoccupazione esplicita dell'utente), verificato leggendo il
  sorgente di wavelink e bloccato con un test di regressione che
  fallirebbe se una futura versione cambiasse questo comportamento.
  **Permanentemente descoperti** (richiesta esplicita dell'utente,
  NON da rimettere in lista in futuro): search distinta da play
  (nemmeno `/music queue cerca:`), forceskip, `/music remove`, move,
  seek, lyrics. (13/10: `/music remove` e `queue cerca` erano stati
  scritti in F2 per errore e sono stati tolti; domanda per l'owner in
  VERIFICA_LIVE.)
  → **Stato 14/10:** sistemati canale diverso (M 8.7), `defer` prima di Lavalink (M 8.16), titolo tagliato (M 8.15). `/music play` accetta anche un file allegato (MUS-009); il bot entra "sordo" (MUS-056). Da verificare live.
- `[~]` 9.5 Sorgenti: YouTube, Spotify (solo risoluzione titolo),
  SoundCloud, URL, file locali — **un nodo wavelink per bot** (D10): il
  bot principale e ogni worker hanno i propri nodi, uno per server in
  `LAVALINK_NODES` (nessun nodo pubblico nel codice) più il nodo
  locale/self-hostato (`LAVALINK_HOST/PORT/PASSWORD`, identificatore
  `iyokai-local-node@<bot>`). La ricerca gira sul nodo del bot che
  suonerà (`MusicCog._cerca`): testo libero → sempre `ytmsearch:`;
  URL http(s) solo se `core.safe_http.url_e_sicuro` li ammette (niente
  reti interne); URI `spotify:` passano così come sono (servono
  LavaSrc sul nodo, che oggi non è attivo: senza risultati si ritenta
  una volta sul nodo locale se c'è); `local:`, percorsi e `file:` sono
  rifiutati (`classify_query`). **File locali** solo per la radio
  condivisa (`/owner radio add-local`), instradati al nodo locale
  (Lavalink >= 4.2.0, `LAVALINK_LOCAL_ROOT`); i nodi pubblici non
  hanno accesso al filesystem della macchina
  → **Stato 04/10:** scelta del nodo al contrario (LIM-42); `local:` e `spotify:` diventano ricerche YouTube (LIM-43, BUG-10).
- `[✗]` 9.6 Filtri audio (bassboost, nightcore, vaporwave, 8D) —
  scartato su richiesta esplicita dell'utente, non un limite tecnico
- `[✗]` 9.7 DJ role — scartato, stesso motivo di 9.6
- `[✗]` 9.8 Voteskip — scartato, stesso motivo di 9.6
- `[x]` 9.9 Auto-leave a canale vuoto — `core/music_fleet.
  handle_inactive_player()`, agganciato identicamente su tutti e 6 i
  bot (main + 5 worker). Il timeout (300s di default) è gestito
  internamente da wavelink/Lavalink; qui solo la reazione:
  disconnette e libera il worker nella flotta
  → **Stato 04/10:** Correzione al testo: la disconnessione avviene dopo 300 secondi, non subito.
- `[~]` 9.10 Modalità 24/7 con cap istanze concorrenti — `/nonstop
  on|off` (loop continuo sulla coda del worker attivo) fatto; il cap
  di 5 istanze (TOTAL_WORKERS) resta un vincolo dell'infrastruttura
  (5 token bot worker configurati), non un numero arbitrario da poter
  cambiare via comando — chiarito esplicitamente dall'utente. "Gestito"
  ora significa: `/play` assegna solo un worker EFFETTIVAMENTE
  invitato in quel server (mai uno assente, corretto un bug reale che
  avrebbe altrimenti occupato per sempre uno slot inutilizzabile), e
  quando nessuna istanza è disponibile il messaggio distingue i due
  casi reali — questo server non ha ancora invitato tutte le 5
  istanze (link d'invito generati al volo, mostrati solo a chi ha
  `manage_guild`, un non-admin viene invitato a chiedere all'admin) o
  tutte e 5 sono già presenti ma occupate altrove in questo momento
  (serve un'estensione del limite GLOBALE, indirizzato ad aprire un
  ticket nel server ufficiale iYokai — nessun link fabbricato, il
  server è già raggiungibile pubblicamente)
  → **Stato 04/10:** dopo 3 brani a canale vuoto il player viene scollegato (LIM-44).
- `[~]` 9.11 Stream 24/7 con musica di proprietà (singolo decoder
  condiviso) — `/nonstop-main add-track|add-local|remove-track|
  list-tracks|start|stop`. "Condiviso" ottenuto con un orologio
  logico (`core/main_radio_logic.py`): non un unico decode audio
  fisicamente multicast a più canali (impossibile con l'architettura
  Lavalink — ogni bot ha la propria connessione voce), ma ogni
  server che entra calcola dove dovrebbe essere la riproduzione ORA
  (stessa traccia, stessa posizione, in base al tempo reale
  trascorso) e joina seekando esattamente lì — stesso risultato
  percepito dall'ascoltatore: tutti sentono la stessa cosa nello
  stesso punto. Verificato con un test end-to-end: un secondo server
  che entra 90 secondi dopo riceve la posizione corretta, non
  riparte da zero
  → **Stato 04/10:** file locali non trovati (BUG-10); radio scollegata dai canali vuoti (LIM-44); avvio automatico da fare (#45).
- `[~]` 9.12 Backend Lavalink — l'intero cog si basa su Lavalink via
  wavelink, nodi pubblici in cascata + nodo locale (vedi PROGRESS.md)
  → **Stato 04/10:** un nodo morto blocca gli altri (LIM-41); versione del nodo non controllata (LIM-54).

- `[x]` 9.13 Un nodo wavelink per ogni bot per ogni server Lavalink,
  con scelta esplicita del nodo (D10, LIM-40, LIM-42)
- `[x]` 9.14 Controllo della versione di Lavalink all'avvio (4.2.0 o
  successiva) e nodi pubblici solo da `.env` (LIM-54)
- `[x]` 9.15 Cartella `deploy/lavalink/` con `docker-compose.yml`,
  `application.yml` e guida (#47, #48)
- `[x]` 9.16 Radio che parte da sola quando il bot principale entra in
  un canale vocale (#45)
- `[x]` 9.17 Canale richieste con messaggio "player" e bottoni, playlist
  salvate degli utenti (§23, NF-19)
  → **Stato 14/10:** 9.13–9.16 fatte in F2 (#64, #45, #47, #48); 9.17 vedi 23.1. Da verificare live.

## §10 ALERTS & SOCIAL — presente, con limiti di quota da correggere (fase F1)

- `[~]` 10.1 Twitch live — via polling Twitch Helix "Get Streams"
  (non EventSub webhook, vedi nota tecnica sotto). Testato con
  credenziali fittizie su richiesta esplicita dell'utente (server
  locale finto che imita l'API reale); funzionerà con le sue
  credenziali vere una volta registrate su dev.twitch.tv
  → **Stato 04/10:** oltre 100 iscrizioni e oltre 20 dirette insieme (LIM-46); pubblica anche a modulo spento (LC-7).
- `[~]` 10.2 Twitch offline — stesso meccanismo di 10.1
  → **Stato 04/10:** LIM-46, LC-7.
- `[~]` 10.3 YouTube nuovo video — via il feed Atom nativo di YouTube
  (`youtube.com/feeds/videos.xml?channel_id=...`), nessuna chiave API
  → **Stato 04/10:** LC-7; se sparisce l'ultimo elemento ripubblica tutto (REVIEW §4).
- `[~]` 10.4 YouTube live — via il feed RSS del canale (ID dei video
  recenti, nessuna quota) e una `videos.list` della YouTube Data API v3 per
  gruppo di 50 ID, guardando `liveBroadcastContent` (D5; `search.list`
  costava 100 unita' per canale, BUG-16). Come
  Twitch (§10.1/§10.2), env-gated: `YOUTUBE_API_KEY` opzionale,
  `core/youtube_watcher.py` resta inattivo finché non è configurata,
  nessun fallimento all'avvio. Intervallo di controllo più lungo di
  Twitch apposta (300s contro 90s): questo endpoint costa 100 unità
  di quota PER CANALE sottoscritto su una quota giornaliera gratuita
  di 10.000, la stessa ragione per cui questa voce era stata rimandata
  — chi la abilita deve gestire la propria quota. `/alerts
  add-youtube-live` crea la sottoscrizione (prefisso `YT-` in
  `/alerts list`/`/alerts remove`) anche senza la chiave configurata
  (resta semplicemente inattiva, un avviso lo dice chiaramente),
  così non va ripetuta quando l'owner del bot la aggiunge in seguito
  → **Stato 04/10:** quota finita in poche ore (BUG-16, LIM-45). Soluzione decisa: D5.
- `[ ]` 10.5 TikTok nuovi video — scartato: nessuna API ufficiale
  gratuita per leggere le pubblicazioni di terzi, solo scraping
  fragile. Confermato dall'utente come vincolo accettato, non un
  limite di sforzo
  → **Stato 04/10:** nessuna API gratuita. Alternativa pianificata (D14, NF-32): feed "ponte" e webhook in ingresso, più chiave a pagamento facoltativa.
- `[ ]` 10.6 Instagram — nessuna API permette di monitorare account
  di terzi. Scartato, vedi audit di fattibilità
  → **Stato 04/10:** alternativa pianificata (D14, NF-32).
  → **Stato 14/10 (NF-32, #103):** fatto con le alternative regolari.
  `/moduli alert guida-social` spiega TikTok, Instagram e X (feed
  «ponte» RSS e webhook in ingresso, chiave a pagamento facoltativa).
  `/moduli alert kick` (`KK-<id>`, 0121, tetto 25 per server come
  Twitch e YouTube) con `core/kick_watcher.py` (API pubblica,
  `KICK_CLIENT_ID/SECRET`). `/moduli alert ruolo-live` + campo
  `membro` di `/moduli alert opzioni`: il ruolo «in diretta» si dà a
  inizio diretta e si toglie alla fine (Twitch, YouTube, Kick).
  `/moduli alert opzioni` (#129): ruolo da avvisare (solo se
  menzionabile o se chi configura può pingare), bottone «Guarda»,
  messaggio di fine sì/no, avviso cancellato a fine diretta,
  pubblicazione nei canali annunci; segnaposto `{game}` per Twitch e Kick.
- `[~]` 10.7 Reddit — via il feed RSS nativo di Reddit
  (`reddit.com/r/nome/new/.rss`), nessuna chiave API
  → **Stato 04/10:** LC-7; REVIEW §4 (ripubblica tutto).
- `[~]` 10.8 Custom RSS / webhook — la parte RSS è fatta (`/alerts
  add`, qualsiasi URL RSS/Atom). La parte "webhook" è fatta come
  endpoint proprio (non EventSub/PubSubHubbub, vedi Nota tecnica
  sotto): `/alerts webhook-create` crea un URL segreto
  (`/webhook/<token>`, token opaco da 32 byte, mostrato una sola
  volta e non più recuperabile — stesso modello dei webhook in
  ricezione di Discord/Slack/GitHub); un server HTTP dedicato
  (`core/custom_webhook_server.py`, aiohttp, parte solo se esiste già
  almeno un webhook configurato — SEC-14 — indirizzo/porta
  configurabili via `WEB_BIND_HOST`/`ALERTS_WEBHOOK_PORT/PUBLIC_BASE_URL`,
  limite di richieste per token in finestra mobile)
  riceve richieste POST con un corpo JSON (`title`/`message` o
  `content`/`text`, `url` o `link`, troncati rispettivamente a
  256/1500/500 caratteri) e pubblica nel canale scelto usando lo
  stesso sistema di template di 10.9. `/alerts list` mostra il
  webhook (`WH-<id>`) senza mai il token; `/alerts remove WH-<id>`
  lo elimina
  → **Stato 04/10:** LC-7; nessun tetto di feed per server (LIM-16). BUG-20 e BUG-33 corretti il 04/10.
- `[~]` 10.9 Messaggi personalizzabili per ogni alert — placeholder
  `{label}` `{title}` `{link}` nel template (RSS), `{label}` `{title}`
  `{login}` (Twitch)
  → **Stato 04/10:** solo RSS e webhook accettano un modello (REVIEW §12).
- `[ ]` 10.13 X/Twitter — **voce nuova**, non nello schema originale,
  aggiunta su richiesta esplicita dell'utente. Scartata: la lettura
  via API richiede un abbonamento a pagamento nel tier utile (il
  tier gratuito non permette di leggere i post di terzi in modo
  utilizzabile per il monitoraggio). Nessuna alternativa gratuita
  affidabile nota (i bridge non ufficiali tipo Nitter sono instabili
  e spesso bloccati da X). Confermato dall'utente come vincolo
  accettato
  → **Stato 04/10:** alternativa pianificata (D14, NF-32).

**Nota tecnica, vale per Twitch/YouTube/Reddit/RSS**: lo schema
originale chiedeva EventSub (Twitch) e PubSubHubbub (YouTube),
entrambi webhook PUSH — richiedono un endpoint HTTPS pubblico
raggiungibile da Twitch/Google, che questo bot non ha (nessun server
web, solo un client Gateway Discord). Aggiungerlo significherebbe
dominio, certificato TLS, apertura di una porta sulla VM — un cambio
di infrastruttura, non solo di codice. Sostituito con **polling**
periodico (`core/feed_watcher.py` ogni 5 minuti, `core/twitch_
watcher.py` ogni 90s), che raggiunge lo stesso risultato per
l'utente finale senza cambiare il deployment.

**Nota tecnica separata, riguarda solo 10.8 "webhook custom"**: qui
non serve integrarsi con un protocollo esterno specifico
(EventSub/PubSubHubbub sono legati a Twitch/Google, non generici) —
serve solo un endpoint HTTP generico *nostro*, dove chiunque (n8n,
Zapier, IFTTT, un piccolo script) può inviare un POST. Per questo il
vincolo di infrastruttura sopra non si applica allo stesso modo:
serve comunque una porta aperta sulla VM (già presente e riusata
dal server OAuth2 di §11.11, porta diversa per evitare collisioni),
ma non un dominio/TLS/certificazione con un servizio terzo — chi usa
il webhook porta il proprio URL pubblico se vuole esporlo dietro un
reverse proxy (`ALERTS_WEBHOOK_PUBLIC_BASE_URL`), altrimenti il
token va usato con l'IP diretto della VM.

## §11 BACKUP SYSTEM — da rifare secondo la decisione D8 (fase F3)

**Stato al 04/10/2026.** Il disegno originale non può più funzionare:
Discord ha tolto ai bot la possibilità di creare server (luglio 2025) e
discord.py 2.6 segna deprecati `create_guild` e `Guild.delete`. Senza
il server creato dal Creator non nasce la coppia main→backup, e senza
coppia non partono mirror, snapshot dei membri, `/restore-users` e
`/promuovi-backup`. Il token del Creator è ancora obbligatorio
all'avvio (LIM-39).

**Disegno nuovo (D8, seconda versione): il server lo crea un admin, il
Creator lo porta e lo tiene allo stato corrente.**

1. Un admin **crea il server di backup** (anche da un link "modello di
   server" generato dal bot con `Guild.create_template`).
2. Invita lì **iYokai Creator** e il bot principale, poi lancia il
   comando di collegamento con il codice generato nel server principale.
3. Il Creator copia ruoli, canali, permessi, emoji, sticker e suoni, e
   i messaggi **in ordine cronologico** tramite webhook, uno dopo
   l'altro (discord.py aspetta da solo quando interviene il rate limit,
   quindi l'ordine resta giusto).
4. Poi tiene il server aggiornato: mirror dei messaggi nuovi e
   controllo periodico delle differenze.
5. Snapshot settimanale dei membri, `/restore-users` e promozione
   lavorano su quella coppia.

Il lavoro pesante gira sul token del Creator, così non consuma i limiti
di frequenza del bot principale né di iYokai Mod (D15).

**Limiti di Discord che restano veri:** un bot non può entrare da solo
in un server (serve il clic di un umano sull'invito); `guilds.join`
funziona solo per chi ha dato il consenso prima; i token degli utenti
durano circa 7 giorni e vanno rinnovati; al massimo 15 webhook per
canale.

**Cosa viene tolto:** la creazione del server da parte del bot, il
passaggio di proprietà, la cancellazione dei server, la coda con i "10
posti", la pulizia dei server orfani (già disattivata il 04/10 in
`fba882e`). I bug BUG-26, BUG-28 e BUG-29 riguardavano quel flusso:
superati. **iYokai Creator e `YOKAI_CREATOR_TOKEN` restano.**

- `[~]` 11.1 Snapshot del server salvato come dati nel database, con
  più copie datate per server (D8, LIM-39): `/backup salva` e `lista`,
  tabella `backup_strutture` (0191), vedi 11.15
- `[x]` 11.2 Collegamento di un server creato a mano: `/backup
  crea` genera il codice (24 ore, monouso, salvato come impronta) e, a
  richiesta, il link "modello" (`Guild.create_template`); `/backup
  collega` lo usa nel server nuovo (`core/backup_link_logic.py`); la copia
  gira sul client del Creator; nessuna cessione di proprietà (D8); copia
  anche gli ultimi 50 messaggi per canale con il webhook, uno alla volta
  (`core/backup_messages_logic.py`; prova live: ordine e tempi)
- `[x]` 11.3 Clonazione ruoli + permessi — `clone_roles()` in
  `core/backup_clone_logic.py`: salta @everyone ma ne applica i
  permessi, salta i ruoli "managed", riusa per nome quelli già presenti
  (modello) e imposta le posizioni alla fine (gerarchia: prova live)
- `[~]` 11.4 Clonazione categorie + canali — `clone_categories_and_
  channels()`: categorie prima dei canali, permessi rimappati. Riusa per
  nome canali e categorie già presenti; qualità audio limitata a quella
  del server di destinazione (LIM-28); canali `___hidden___` saltati e
  contati (LIM-38)
- `[~]` 11.5 Clonazione emoji — `clone_emoji()`, con controllo dei
  limiti del server di destinazione (`e502c1f`). Senza essere
  proprietario serve il permesso `CREATE_GUILD_EXPRESSIONS`.
  Raggiungibile solo dopo 11.2
- `[~]` 11.6 Clonazione sticker — `clone_stickers()`, come 11.5
- `[~]` 11.7 Clonazione soundboard — `clone_soundboard()`, come 11.5
- `[~]` 11.8 Clonazione webhook — `clone_webhooks()`: nome e canale
  rimappato (l'URL non è copiabile). Al massimo 14 per canale: uno dei 15
  resta per il mirror (LIM-28)
- `[~]` 11.9 Mirror messaggi in tempo reale via webhook con identità
  utente (scarto sui picchi, 5 messaggi ogni 5 secondi per canale) —
  `core/backup_mirror_logic.py`, `core/backup_mirror_dispatch.py`,
  `cogs/utility/backup_mirror.py`. SEC-22 corretto (`690a5b6`). Da
  riprovare con l'intent acceso (BUG-5); il nome del mittente non
  contiene "discord" né "clyde" (LIM-27); il webhook "iYokai Mirror" si
  riusa se esiste. Raggiungibile dopo 11.2
- `[~]` 11.10 User backup: snapshot periodico (settimanale) dei
  verificati non bannati/kickati — `core/backup_snapshot_logic.py`,
  `core/backup_snapshot_worker.py`. Il worker ora parte (BUG-19,
  `fba882e`), ma non trova coppie finché non c'è 11.2
- `[~]` 11.11 Restore massivo utenti via OAuth2 `guilds.join` — token
  cifrati AES-256-GCM (`core/oauth_crypto.py`), tre modalità per
  server (`/configura-restore`), conservazione diversa per uscita,
  kick e ban. Corretti il 04/10: link valido 7 giorni e legato al
  destinatario (BUG-21, SEC-19, `8590e89`); ruolo verificato
  controllato (`67e5771`). Fatti (M 12.10, 12.11, 12.13, 12.15): token
  rinnovati con il refresh token (LIM-37); attesa del `Retry-After` sui
  429, pausa tra i DM, conteggi dopo l'esito, riepilogo nel canale se la
  risposta è scaduta (LIM-7); coppia storica dopo la promozione (BUG-34);
  chiave ruotabile con prefisso di versione, cifrato legato a server e
  utente, riga rovinata saltata (LIM-52, SEC-16). Fatti il 15/10 (M 12.12,
  12.14): a fine verifica, in un server con backup, bottoni «Sì, avvisami /
  No» (tabella `restore_consensi`; bottoni persistenti, anche nel DM e dopo
  un riavvio) e, in modalità "OAuth alla verifica", il
  link OAuth di solo consenso; il restore manda DM solo a chi ha accettato
  o ha già un token
- `[~]` 11.12 Comandi del gruppo `/backup` (D25, 15/10: il blocco intero
  esce da `/admin`): `main`, `crea`, `collega`, `promuovi`, `restore-modo`,
  `restore-utenti`. Ogni uso finisce nel registro (`/backup registro`,
  365 giorni, BKP-019); `/backup permessi` sceglie fra tre livelli chi crea
  e chi carica (BKP-018, predefinito: gli admin creano, solo l'owner carica)
- `[~]` 11.13 Promozione del backup a nuovo main — `/backup promuovi`; la
  coppia storica resta per `/backup restore-utenti` (BUG-34, M 12.13)
- `[~]` 11.14 Il Creator non crea, non cede e non cancella server: entra nel
  server creato dall'admin e lo porta allo stato corrente, messaggi in
  ordine compresi (D8, M 12.1/12.2). Gli allegati tornano come file entro
  10 MiB per messaggio e i fissati si rifissano (BKP-013/016, 15/10)
- `[ ]` 11.17 Aggiornamento continuo del server di backup: controllo
  periodico delle differenze di ruoli, canali e permessi (D8)
- `[~]` 11.15 Copie datate della struttura (M 12.17, 15/10): `/backup salva`
  (al massimo 10 per server; a scelta ban, membri e gli ultimi 0-100
  messaggi di ogni canale), `lista`, `carica` (si scelgono le parti in un
  menu; si riusa per nome, tetti di 250 ruoli, 500 canali, 50 per
  categoria, bitrate; chi non è l'owner non modifica, non sposta e non dà
  ruoli pari o sopra il suo più alto), `elimina`, `stato` e `annulla` (BKP-009/010);
  `esporta` in JSON o CSV di struttura, canali, ruoli, un canale, un
  ruolo, ban, reazioni (BKP-032…036); `importa` controlla il file prima di
  toccare il server (BKP-037); `chat-salva` (fino a 1000 messaggi) e
  `chat-carica` anche in un altro canale (BKP-026/027); `copia-canale` e
  `copia-ruolo` (BKP-024/025). Logica in `core/backup_struttura_logic.py`,
  `core/backup_messages_logic.py`, `core/backup_copia_logic.py`
- `[~]` 11.16 Modelli e sincronia (§23, NF-39, 15/10): `/backup modello`
  pubblica una copia con un codice (senza ban, membri, messaggi e permessi
  dei singoli; mai una chat) e la carica in un altro server;
  `/backup sincronia` tiene uguali ban e ruoli (per nome) tra due server
  dello stesso owner, al massimo 5 per server, senza eco
  (`core/server_sync_logic.py`). Il ban fra tutti i server resta il ban
  globale (`cogs/security/global_ban.py`, stesso ID utente): il restore
  OAuth non ripristina chi è bannato (#46)

## §12 TEMPORARY VOICE CHANNELS

- `[x]` 12.1 Modalità automatica (generatore → crea + sposta)
- `[x]` 12.2 Modalità manuale (pannello + bottone persistente)
- `[x]` 12.3 Entrambe sempre visibili a tutti
- `[x]` 12.4 Notifica personale alla creazione del canale — un
  embed nella chat testuale del canale vocale stesso (un
  `VoiceChannel` è Messageable), inviato sia dalla modalità
  automatica (che prima spostava in totale silenzio) sia da quella
  manuale
- `[~]` 12.5 Selezione piattaforma all'ingresso (PC / Console /
  Mobile) — bottoni SOLO informativi (nessun filtro di visibilità,
  come da decisione finale già registrata) mostrati insieme alla
  notifica 12.4 se il server ha configurato almeno un ruolo
  piattaforma (`/voicetemp-platform-setup`)
  → **Stato 04/10:** i bottoni muoiono dopo 5 minuti (LIM-26).
- `[~]` 12.6 Gestione canale: rename, limite utenti, lock, unlock, kick, transfer, claim (proprietario assente), permit, deny, bitrate, nascondi, invita, stato (#127); il blocco resta dopo un riavvio (#144); `/gestione voice opzioni`: nome da modello `{utente}`/`{numero}`, canali che nascono bloccati, canale di registro (#127)
  → **Stato 04/10:** rinomina senza limiti (LIM-3); `transfer` accetta chiunque (BUG-18).
- `[~]` 12.7 Eliminazione automatica a canale vuoto
  → **Stato 04/10:** canali orfani dopo un riavvio (REVIEW §4).
- `[x]` 12.8 Cap configurabile canali per categoria (`/voicetemp-cap`),
  sempre troncato al limite hard di Discord di 50

## §13 TICKET SYSTEM

- `[x]` 13.1 Pannello apertura con bottone persistente
- `[~]` 13.2 Select menu categorie (`/ticket-category add|remove|list`)
  — se il server ne ha configurato almeno una, il pannello mostra il
  select menu invece del bottone unico; retrocompatibile (nessuna
  categoria configurata -> bottone unico storico)
  → **Stato 04/10:** oltre 25 categorie, o con un'etichetta o un'emoji non valida, il menu si rompe per tutti (LIM-6).
- `[x]` 13.3 Creazione canale privato
  → **Stato 21/10:** corretto con #62 (M 6.3 canale nato col numero, M 6.4 un solo ticket aperto sotto blocco).
- `[x]` 13.4 Claim
  → **Stato 21/10:** solo staff (M 6.6); con le opzioni del pannello sposta, rende esclusiva e scrive il testo (§13.19).
- `[x]` 13.5 Add / Remove utente
  → **Stato 21/10:** solo staff (M 6.6), anche un ruolo intero (TKT-047).
- `[x]` 13.6 Rename
  → **Stato 21/10:** nome fino a 100 e limite delle rinomine (M 6.2, M 6.3).
- `[x]` 13.7 Priorità
  → **Stato 21/10:** solo staff (M 6.6).
- `[x]` 13.8 Close
  → **Stato 04/10:** BUG-1 e BUG-30 corretti (`6c724d3`, `10d16f1`). (da verificare live)
- `[x]` 13.9 Force close (`/ticket forceclose`, riservato allo staff
  — Manage Server o un ruolo di supporto configurato — elimina il
  canale subito, senza i 10s di preavviso di close normale)
- `[~]` 13.10 Transcript automatico alla chiusura — letto via
  `channel.history()` PRIMA della cancellazione. **Non richiede il
  Message Content Intent**: quell'intent riguarda solo gli eventi
  GATEWAY in tempo reale, non la history REST (governata dal normale
  permesso Read Message History) — stessa verifica già fatta per lo
  Spam Trap in `core/spam_trap_logic.py`
  → **Stato 04/10:** Correzione al testo: senza l'intent anche la lettura REST dà messaggi vuoti (REVIEW L8). L'intent ora è acceso: da riprovare (BUG-5).
  → **Stato 21/10:** M 6.8 (transcript con testo, file sotto 10 MiB); il DM all'utente si può spegnere per pannello (TKT-075). (da verificare live)
- `[x]` 13.11 Invio transcript nel canale log configurato (riusa
  `SETTING_LOG_CHANNEL` di §8) + DM all'utente che ha aperto il
  ticket (silenzioso se i DM sono chiusi)
  → **Stato 04/10:** (da verificare live)
- `[x]` 13.12 Statistiche ticket (`/ticket-stats [operatore]`) — prese
  in carico, chiuse, tempo medio di prima risposta (per operatore o
  per l'intero server)
- `[x]` 13.13 Configurazione ruoli di supporto multipli
  (`/gestione ticket ruolo-add|ruolo-remove|ruolo-list`) — combinati con il ruolo
  legacy singolo per retrocompatibilità, nessuna migrazione richiesta
  → **Stato 21/10:** `remove` toglie anche il ruolo storico (M 6.7).
- `[x]` 13.14 Apertura da comando (`/ticket apri`): pannello o motivo, lo staff anche per conto di un
  utente, con il link di un messaggio citato e, a scelta, il suo autore (TKT-007/008/009; il menu col
  tasto destro sarebbe un comando di primo livello in più: si usa il link). (da verificare live)
- `[x]` 13.15 Regole di apertura per pannello e per server: tetto di ticket aperti, ruoli esenti, pausa
  tra due aperture con azzeramento, regole di accesso per ruolo, lista nera, orari con fuso e
  comportamento fuori orario, sospensione con motivo (TKT-017…024; `/ticket opzioni limiti|orari|accesso`,
  `/ticket lista-nera`, `/ticket sospendi`, `/ticket azzera-pausa`; migrazione 0220). (da verificare live)
- `[x]` 13.16 Canale: nome da modello (`{numero}` `{num}` `{utente}` `{nickname}`), categorie di riserva
  sopra i 50 canali (TKT-025, 030; `/ticket opzioni canale`).
- `[x]` 13.17 Avvisi all'apertura: ruoli, `@here`, staff reperibile (`/ticket reperibile`), ping cancellato,
  primo messaggio fissato, DM di apertura e di chiusura (TKT-033, 037, 038, 039; `/ticket opzioni avvisi|messaggi`). (da verificare live)
- `[x]` 13.18 Permessi: permessi tolti all'utente, ruoli osservatori, ruoli dati durante il ticket e tolti
  alla chiusura, squadra di staff per pannello (TKT-041…044; `/ticket opzioni permessi`).
- `[x]` 13.19 Presa in carico: categoria dei presi, esclusiva (gli altri non scrivono o non vedono),
  al primo dello staff che risponde, testi di presa e rilascio, thread privato delle note
  (`/ticket note`), bottone «Torna all'inizio» (TKT-028, 034, 040, 050, 052, 053; `/ticket opzioni presa`). (da verificare live)
- `[x]` 13.20 Chiusura: conferma, chi può chiudere, richiesta all'utente con Accetta/Rifiuta e chiusura
  dopo N ore (`/ticket chiedi-chiusura`, azione `ticket_richiesta_chiusura`), transcript in DM a scelta
  (TKT-054, 055, 057, 075; `/ticket opzioni chiusura|messaggi`). (da verificare live)

## §14 UTILITY & SERVER MANAGEMENT

- `[~]` 14.1 Reaction Roles — `on_raw_reaction_add`/`remove`
  → **Stato 04/10:** LIM-17.
- `[~]` 14.2 Button Roles — View dinamica persistente per-messaggio
  (`bot.add_view(view, message_id=...)`, pattern nuovo rispetto ai
  pannelli "bottone fisso" già in uso altrove)
  → **Stato 04/10:** `toggle=False` ignorato (REVIEW §4); LIM-17.
- `[~]` 14.3 Select Menu Roles — multi-selezione con sincronizzazione
  che non tocca mai ruoli del membro estranei al menu (verificato
  esplicitamente con un test dedicato)
  → **Stato 04/10:** menu rotto quando resta senza opzioni (LIM-17).
- `[~]` 14.4 Welcome messages — canale + DM opzionale, segnaposto
  `{user}`/`{username}`/`{server}`/`{membercount}`
  → **Stato 04/10:** testo accettato e poi rifiutato in silenzio (LIM-10); DM senza pausa durante un raid (LIM-35).
- `[~]` 14.5 Goodbye messages
  → **Stato 04/10:** LIM-10.
- `[~]` 14.6 Boost messages — rilevato su `premium_since` che passa
  da `None` a valorizzato, non il caso opposto
  → **Stato 04/10:** LIM-10.
- `[ ]` 14.7 Autoresponder (con wildcards e condizioni) — **rimandato
  deliberatamente, stesso motivo di §8.16**: decidere se una parola
  chiave presente nel testo di un messaggio deve far scattare una
  risposta richiede di LEGGERE il contenuto del messaggio in tempo
  reale (`on_message`), che è esattamente il campo azzerato dal
  Message Content Intent quando non attivo — non c'è modo di
  aggirarlo con un poller o una cache come fatto per §8.13/§13.10,
  perché qui il contenuto serve SUBITO, al momento dell'evento, non
  recuperabile in un secondo momento via REST (il messaggio non è
  ancora stato cancellato, ma il gateway lo consegna già vuoto)
  → **Stato 04/10:** l'intent è acceso dal 04/10. In piano: NF-10, fase F9.
- `[~]` 14.8 **Custom Commands — sistema di RICHIESTA** (progettato in
  dettaglio): modal con nome comando + descrizione + esempio → embed
  automatico nel canale `#suggestions` del server principale con nome
  server, ID server, nome utente, **ID utente** (perché il nome può
  cambiare), descrizione, timestamp → bottoni staff approva/rifiuta →
  notifica di ritorno al richiedente
  → **Stato 04/10:** due staff possono decidere insieme (REVIEW §5). I comandi creati dal server sono in §22 (NF-09).
- `[x]` 14.9 Snipe — `/utility snipe`: l'ultimo messaggio cancellato nel
  canale (testo tagliato a 4096, allegati per nome), ricordato 5
  minuti solo in memoria, solo se il server accende il modulo `snipe`
  (privacy). Niente menzioni vere nella risposta (NF-03, issue #74)
- `[x]` 14.10 Editsnipe — `/utility editsnipe`: ultima modifica con
  prima e dopo (campi 1024), stesse regole di 14.9
- `[x]` 14.11 Reactionsnipe — `/reactionsnipe`, NON richiede il
  Message Content Intent: `on_raw_reaction_remove` restituisce
  emoji/autore/messaggio senza bisogno del contenuto del messaggio.
  Stato in memoria (non persistito, come tutti i bot "snipe")
- `[x]` 14.12 Ghost ping detection — traccia in memoria i messaggi
  con menzioni (`Message.mentions`, popolato da un campo gateway a
  parte dal contenuto — non azzerato dall'intent, verificato
  leggendo `Message._handle_mentions` nella libreria installata) e
  segnala nel canale log se vengono cancellati, senza mai leggere il
  testo del messaggio. Non segnala se il registro di controllo dice che
  l'ha cancellato un moderatore (M 5.9; se il registro non è leggibile
  vale la regola di prima); scrive nella destinazione «messaggi» del router
- `[~]` 14.13 Sticky messages — `/sticky set|remove`, debounce minimo
  (5s) per non cancellare+reinviare ad ogni singolo messaggio in un
  canale attivo
  → **Stato 04/10:** messaggi persi o doppi (REVIEW §4); errore non gestito (LIM-11).
- `[~]` 14.14 Suggestion system (per i server clienti, distinto da
  14.8) — `/suggestion-setup`, `/suggest`, bottoni persistenti
  approva/rifiuta + reazioni native 👍👎 per il voto
  → **Stato 04/10:** nessun `defer` (LIM-25); due staff decidono insieme (REVIEW §5).
  → **Stato 21/10 (catalogo #128, giro r8):** stati «in valutazione» e «realizzato», motivo dello staff in una finestra
  (512, colonna `decision_reason`, migrazione 0232), DM all'autore, canale dei suggerimenti decisi (UTL-135…138).
- `[~]` 14.15 Poll — Poll nativo di Discord (`discord.Poll`), fino a
  5 opzioni, nessuna logica propria: voto/conteggio/chiusura gestiti
  interamente da Discord
  → **Stato 04/10:** risposta oltre 55 caratteri: errore (LIM-2).
  → **Stato 21/10 (catalogo #128, giro r8):** 10 opzioni; senza opzioni è un sì/no rapido (UTL-087, con il Poll nativo
  invece delle reazioni); `discussione:` apre un thread sul sondaggio (UTL-095).
- `[~]` 14.16 Reminder — `/reminder set|list|cancel`, riusa lo
  scheduler generico esistente (nessuna tabella nuova). Consegna via
  DM, fallback nel canale se i DM sono chiusi
  → **Stato 04/10:** promemoria lunghi persi in silenzio (LIM-13).
  → **Stato 21/10 (catalogo #128, giro r8):** promemoria ripetuti (minimo 30 minuti, riprogrammati prima della consegna),
  pubblicati in un canale, «annulla tutti», elenco e annullamento del server per lo staff (`/utility reminder server`)
  (UTL-098, 099, 102, 103).
- `[~]` 14.17 Scheduled messages — `/schedule-message set|list|cancel`,
  riusa lo stesso scheduler dei Reminder (nessuna tabella nuova).
  Diversamente dal Reminder (personale, via DM), pubblica in un
  CANALE del server
  → **Stato 04/10:** messaggi lunghi persi in silenzio (LIM-12); ping di ruolo muti (D12).
- `[x]` 14.18 Server stats (+ grafici) — `/serverstats`: numeri del
  server + grafico a barre della crescita giornaliera (disegnato con
  Pillow, non matplotlib — nessuna nuova dipendenza pesante)
  → **Stato 04/10:** Correzione al testo: il grafico dipende dal modulo logging (REVIEW §12).
- `[x]` 14.20 Schede informative — `/utility scheda` con utente, server, canale, ruolo, ruoli, membri di un ruolo,
  anzianità e permessi; elenchi lunghi a pagine, membri scaricati dopo `defer` (UTL-195, 197–200, 202; RUO-110…112;
  giro r8, 21/10)
- `[x]` 14.21 Strumenti sui ruoli — gruppo `/ruoli` (D25, quinto caso): dai, togli, a tempo (ripristino dallo
  scheduler), azzera, operazioni di massa (una per server, stima, stop, arresto dopo 10 errori di fila), crea, modifica,
  diagnosi, ruoli a scelta (tetto 25, migrazione 0231) presi dai membri con `/utility ruolo` (RUO-042, 043, 090–109, 113;
  giro r8, 21/10)
- `[ ]` 14.19 **Voce di Yokai: messaggi vocali** — il bot manda veri
  messaggi vocali di Discord da un testo, nella lingua del testo. Sotto
  ogni vocale un messaggio con due bottoni: "Trascrivi" e "Nella mia
  lingua" (li vede solo chi preme, nella lingua del suo client). Si usa
  per i vocali a comando, nei ticket, nei saluti, negli annunci e nel
  resto dell'elenco della issue. discord.py 2.7.1 non li invia: serve
  la chiamata diretta all'API (D22, issue #142, fase F12)

## §15 LEVELS / ECONOMY / GILDE / CLASSIFICHE

- `[~]` 15.1 XP e livelli (testuale + vocale)
  → **Stato 04/10:** anche i messaggi di sistema danno XP (LC-6).
- `[x]` 15.2 Anti-farm XP vocale (self_deaf, soli nel canale, AFK, 2h
  stesso canale, cap giornaliero)
- `[~]` 15.3 Economy: daily, work, pay, balance
  → **Stato 04/10:** `/daily` e `/work` riscuotibili due volte (BUG-14).
- `[~]` 15.4 Shop — `/shop list|buy|add-item|remove-item`, oggetti
  con prezzo e un ruolo opzionale da concedere all'acquisto
  → **Stato 04/10:** toglie le monete anche se il ruolo non viene dato (BUG-14); lista senza tetto (LIM-18).
  → **Stato 13/10:** sistemati (9.2, 9.12). Aggiunti scorte limitate, ruolo richiesto per comprare,
  `/economia shop-edit` e conferma prima dell'acquisto (`/level impostazioni negozio`, spenta di base);
  migrazioni 0094 e 0095. Resta fuori: ruolo comprato che scade, categorie, ordine, oggetti «a elenco» (ECO-063, 065..068).
  → **Stato 14/10 (giro correzioni):** la conferma vale per il prezzo mostrato (se cambia, `buy_item` con
  `prezzo_atteso` rifiuta senza addebito; il prezzo si legge con la riga bloccata); `item_id` va da 1 a 2147483647;
  il nome di soli spazi è rifiutato.
- `[~]` 15.5 Giveaway (con requisiti di ruolo/livello) — `/giveaway`,
  pulsante persistente "Partecipa" (sopravvive a un riavvio del bot,
  registrato di nuovo per ogni giveaway ancora attivo), requisiti di
  livello E ruolo verificati insieme al momento dell'iscrizione
  → **Stato 04/10:** in thread e forum i vincitori non vengono avvisati (REVIEW §4); premio oltre 243 caratteri (LIM-18).
- `[x]` 15.6 Drop messages — piccola probabilità (0.5%) per
  messaggio idoneo, pulsante "primo che clicca vince", coin
  accreditati atomicamente
  → **Stato 04/10:** BUG-17 è un probabile falso allarme: va confermato con un test.
- `[x]` 15.7 Classifica mensile (via `period_key`, senza reset schedulato)
- `[x]` 15.8 Classifica totale all-time
- `[x]` 15.9 Top 3 con medaglie, XP e/o coin a scelta
- `[x]` 15.10 **Classifica Gilde** (mensile + totale) — `/clan
  classifica` con scelta `period` ("Questo mese"/"Di sempre", stesso
  schema di `/leaderboard` personale): la variante totale ordina per
  `clans.total_xp` (cumulativo, mai azzerato); la variante MENSILE
  (era la voce mancante) ordina per `clan_monthly_xp`, una tabella
  per-periodo (`clan_id, period_key, xp_gained`) alimentata da
  `add_xp`/`apply_text_tick` insieme al totale — stesso pattern
  `period_key` senza reset schedulato di 15.7 per la classifica
  personale, non duplicato: `core.leveling_logic.period_key()`
  riusato direttamente. **ANNUNCIO AUTOMATICO in "bacheca clan"**
  aggiunto su richiesta esplicita dell'utente ("ogni mese, il bot
  pubblica in bacheca clan la top 3"): `/clan bacheca set|disable`
  configura un canale per server, tick orario idempotente (uno
  annuncio per mese anche con riavvii) — stesso schema di 15.11
  sotto, tabella di configurazione separata
  (`clan_leaderboard_config`, non condivisa con quella personale:
  due bacheche indipendenti)
- `[x]` 15.11 Annuncio automatico dei vincitori a fine mese —
  `/monthly-winners set|disable`, podio XP e coin del mese appena
  concluso, tick orario idempotente (uno solo per mese anche con
  riavvii); la prima configurazione non annuncia retroattivamente il
  mese già passato
- `[x]` 15.12 Notifica di level-up per XP vocale — mandata nel canale
  vocale stesso (i canali vocali moderni hanno la propria chat
  integrata), l'unico posto sensato per un task periodico su più
  server
- `[~]` 15.13 Ruoli-premio per livello raggiunto — `/level-roles
  add|remove|list`, cumulativo (ogni ruolo fino al nuovo livello,
  non solo il più alto), agganciato sia a XP testuale sia vocale
  → **Stato 04/10:** lista oltre 80 righe (LIM-18).
- `[~]` **15.14 SISTEMA GILDE / CLAN — intera sottosezione**
  → **Stato 15/10:** il tick vocale delle gilde raggruppa letture e scritture per server e per clan (M 9.18, PERF-4): due letture dei clan, una transazione per i tick, tre scritture per clan; una riga del registro di tesoreria per clan a ogni tick invece di una per membro.
  (motore economico di backend calibrato e testato — 10 XP + 4 coin
  a tick/minuto in vocale di gilda (×2 letterale del vocale normale),
  decadimento lineare dopo 3h filate
  nello stesso canale, tetto 720 tick/giorno, deficit di creazione
  15.000 coin/24h, costi canale 25k/50k/200k/800k — comandi Discord
  `/clan crea|info|membri|classifica|sciogli|tesoreria dona|
  tesoreria trasferisci|invita|espelli|promuovi|compra-canale|boost
  individuale|boost gilda`, il worker di eliminazione automatica per
  chi non colma il deficit in tempo, i ruoli Discord Capo Clan/Admin
  Clan, l'acquisto di canali extra con doppio requisito coin + ore
  vocali accumulate dalla gilda, i boost XP/coin ×2/24h individuali e
  di gilda, e ORA anche il trasferimento tesoreria→tesoreria tra due
  gilde dello STESSO owner, ANCHE cross-server — un debito di
  documentazione trovato e chiuso: il repository esisteva già da
  prima, non era mai stato collegato a nessun comando)
  → **Stato 04/10:** vedi le voci sotto.
  - `[~]` Creazione gilda + categoria privata dedicata — `/clan crea`
    valida il tag, crea la categoria Discord (view negata a
    `@everyone`, concessa al fondatore e al bot) PRIMA di scrivere il
    record (se la categoria fallisce non resta un clan senza spazio
    reale), poi `create_clan` con deficit di creazione e finestra di
    grazia di 24h
    → **Stato 04/10:** nessun `defer` (LIM-25); nome senza limite (LIM-18).
  - `[~]` Eliminazione automatica se il deficit non è colmato in
    tempo — `core/guild_clan_expiry_worker.py` (nuovo, tick orario):
    elimina canali + categoria Discord (se esistono ancora) e poi il
    record, per i clan non ufficializzati la cui finestra è scaduta
    → **Stato 04/10:** cancella anche i clan finanziati con un trasferimento (BUG-15).
  - `[~]` Ruoli Capo Clan / Admin Clan — **pari tra gilde diverse**
    (`core/guild_clan_role_service.py`, nuovo): un ruolo Discord
    condiviso "Capo Clan" e uno "Admin Clan" per TUTTO il server,
    riusati da ogni clan (Discord non permette due ruoli alla stessa
    posizione) — l'isolamento reale passa dagli OVERWRITE PER-UTENTE
    sulla categoria del proprio clan (`sync_member_clan_role`/
    `clear_member_clan_presence`), mai dal ruolo condiviso in sé, che
    non dà nessun permesso su nessun canale. Applicato a `/clan crea`
    (Capo Clan al fondatore), `/clan invita` (accesso base),
    `/clan promuovi` (Admin Clan + overwrite estesi o declassamento),
    `/clan espelli` e `/clan sciogli` (rimozione completa)
    → **Stato 04/10:** il ruolo Co-Owner non si può assegnare (REVIEW §11). SEC-17 corretto il 04/10.
  - `[x]` Isolamento totale: nessun capo/admin può agire su altre
    gilde — ogni comando di gestione membri recupera SEMPRE la gilda
    del chiamante via `get_member_clan_in_guild` e opera solo sulla
    categoria/membri di quella gilda; un Admin Clan non può espellere
    un altro Admin Clan (serve il Capo), solo il Capo Clan può
    promuovere/retrocedere
  - `[~]` Comandi di gestione membri: `/clan invita` (Capo/Admin,
    rispetta il tetto `max_members`, rifiuta chi è già in un'altra
    gilda del server), `/clan espelli` (Capo/Admin, il Capo Clan non
    può essere espulso, un Admin non può espellere un altro Admin),
    `/clan promuovi` (solo Capo Clan, ruolo admin/mod/member, rispetta
    i tetti `MAX_ADMINS_PER_CLAN`/`MAX_MODS_PER_CLAN` in
    `guild_clan_logic.py`)
    → **Stato 04/10:** `/clan invita` aggiunge senza consenso; manca `/clan lascia` (REVIEW §4).
  - `[~]` Guadagno ×2 XP e coin — vocale: `guild_clan_voice_worker.py`
    applica il tick per la presenza vocale (agganciato a
    `clan_voice_activity_repo`), ×2 LETTERALE rispetto al vocale
    normale (`TICK_XP=10`/`TICK_COINS=4` in `core/guild_clan_logic.py`
    contro `VOICE_XP_PER_MINUTE=5`/`VOICE_COINS_PER_MINUTE=2` in
    `core/leveling_logic.py` — corregge una discrepanza reale trovata
    in una sessione precedente: la prima versione usava 30 XP/2 coin,
    un target mensile assoluto (500-750k XP/mese) invece del ×2
    dichiarato qui, mai un rapporto ×6 XP/×1 coin come si era finito
    per implementare). Testuale: `GuildClanRepository.apply_text_tick`
    agganciato a `on_message` in `cogs/leveling/leveling.py`, ×2
    letterale sull'XP (30 contro i 15 del testo normale), stesso
    cooldown 60s, NESSUNA coin (come nel testo normale) e NESSUN
    boost applicato (individuale/di gilda restano scoped al solo tick
    vocale, confermato in Fase 54)
    → **Stato 04/10:** l'XP vocale di clan non ha anti-farm (REVIEW §4).
  - `[~]` Tesoreria: **a SENSO UNICO per design** — solo membro ->
    gilda (`/clan tesoreria dona`, scala il saldo personale e
    accredita la tesoreria, ufficializzando il clan in automatico se
    il deficit viene colmato), MAI gilda -> membro (nessun prelievo
    individuale, confermato esplicitamente dall'utente quando il
    repository fu scritto — non è una voce mancante, è la regola).
    Log movimenti consultabile via `/clan info`. Il bisogno di
    "premio evento" che questa voce indicava erroneamente come
    lacuna è già servito da un percorso diverso e corretto: la cassa
    DI SERVER (§15.15, non la tesoreria di un singolo clan) via
    `/assegna-lobby`/`/assegna-winner` — chiarito esplicitamente
    dall'utente in questa sessione, correggendo un fraintendimento di
    una sessione precedente
    → **Stato 04/10:** lo storico dei movimenti non si legge da nessun comando (REVIEW §12).
  - `[~]` Trasferimento tesoreria→tesoreria tra due gilde dello
    STESSO owner, **ANCHE cross-server** — `core.repositories.
    guild_clan_repo.transfer_between_treasuries` esisteva già da una
    sessione precedente (clan con ID GLOBALE non per server proprio
    per questo) ma non era mai stato collegato a nessun comando
    Discord né tracciato in questo schema: **debito di
    documentazione trovato e chiuso in questa sessione**, non un
    pezzo nuovo. `/clan tesoreria trasferisci <tag_destinazione>
    <importo>`: solo il Capo Clan, cerca il tag tra TUTTE le gilde
    (di QUALUNQUE server) di cui il chiamante è owner
    (`list_clans_owned_by`, nuovo) — l'UNICA condizione è lo stesso
    owner, mai lo stesso server (confermato esplicitamente
    dall'utente quando il repository fu scritto): senza questo
    comando le coin di una seconda gilda su un altro server
    resterebbero bloccate per sempre lì
    → **Stato 04/10:** BUG-15; possibile stallo tra due trasferimenti opposti (REVIEW §5).
  - `[~]` Decadimento mensile 10% sulla tesoreria NON spesa —
    `guild_clan_treasury_decay_worker.py`, idempotente per periodo
    (`clans.last_decay_period`), calcolo atomico sotto `FOR UPDATE`,
    deposita il delta nella cassa di server (SPEC.md §15.15). **Bug di
    race condition trovato e corretto in questa sessione**:
    `apply_monthly_decay` restituiva solo il nuovo saldo, costringendo
    il worker a calcolare il delta verso la cassa usando il saldo
    "stale" letto da `list_officialized_clans()` (NON sotto lock) —
    se una donazione arrivava tra quella lettura e il lock, il delta
    depositato in cassa era sbagliato. Corretto seguendo lo stesso
    pattern già usato da `LevelingRepository.apply_weekly_decay`:
    `apply_monthly_decay` ora restituisce `(saldo_prima, saldo_dopo)`,
    entrambi letti sotto lo stesso `FOR UPDATE`, e il worker calcola
    il delta da questa coppia
    → **Stato 04/10:** scatta entro un'ora dalla creazione (REVIEW §4).
  - `[~]` Acquisto canali: testuale / vocale / forum — `/clan
    compra-canale <tipo> [nome]`, Capo/Admin Clan, crea il canale
    Discord VERO dentro la categoria del clan PRIMA di scalare la
    tesoreria (stesso ordine di `/clan crea` con la categoria — se la
    creazione fallisce non resta una spesa senza contropartita), poi
    `increment_channels_unlocked`
    → **Stato 04/10:** può dare il canale gratis (BUG-14).
  - `[x]` Costo coin raddoppiato/quadruplo per canale successivo
    (25.000 → 50.000 → 200.000 → 800.000) — applicato da `/clan
    compra-canale` via `next_channel_unlock_cost`
  - `[x]` Requisito **ore vocali accumulate in gilda** come sblocco
    canale — separato dal guadagno XP/coin: nuova colonna
    `clans.total_voice_ticks` (persona-tick, non per singolo membro),
    incrementata ad OGNI tick vocale di gilda indipendentemente dal
    decadimento/tetto giornaliero (la presenza conta comunque, a
    differenza della ricompensa), soglie 12h/24h/96h/384h
    (`VOICE_HOURS_REQUIRED` — la stessa scala persona-ora da cui
    erano già stati derivati i costi in coin, ora resa un requisito
    verificato) verificate da `/clan compra-canale` insieme al costo
  - `[x]` Boost individuale acquistabile (D23, #146) — `/clan boost
    individuale tipo:<exp|coin|super>`, QUALUNQUE membro (paga dal
    proprio saldo per il proprio guadagno), ×2 per 24h, coin personali:
    **exp 6.000**, **coin 6.000**, **super 10.000** (exp + coin). Si
    applica SOLO al proprio tick vocale di gilda (mai al leveling
    generale del server); exp raddoppia solo gli XP, coin solo le coin.
  - `[x]` Boost di gilda acquistabile (D23, #146) — `/clan boost gilda
    tipo:<exp|coin|super>`, Capo/Admin Clan, ×2 per 24h dalla
    tesoreria: **exp 60.000**, **coin 60.000**, **super 100.000**; si
    applica al tick di TUTTI i membri. Individuale e di gilda si
    moltiplicano tra loro sullo stesso beneficio (×4 totale).
  - `[x]` Regola d'acquisto (D23): per ambito, un boost si compra solo se
    NESSUNO dei suoi benefici è già attivo (coin attivo: solo exp; exp
    attivo: solo coin; super o exp+coin attivi: niente; il super non si
    compra con exp o coin attivi). Controllo sotto la riga bloccata:
    due acquisti insieme dello stesso beneficio, ne passa uno solo; se
    rifiutato nessun addebito. Nessuna somma delle durate: la scadenza
    è sempre adesso + 24h. Colonne: `boost_exp_expires_at`,
    `boost_coin_expires_at` (membro), `guild_boost_exp_expires_at`,
    `guild_boost_coin_expires_at` (gilda); la migrazione 0020 copia la
    scadenza di prima in entrambe (il boost di oggi diventa un super);
    le colonne vecchie restano ma non si usano più. La scheda del clan
    mostra i boost di gilda attivi per tipo.
  - `[~]` Comandi: `/clan crea|info|membri|classifica|sciogli|
    tesoreria dona|tesoreria trasferisci|invita|espelli|promuovi|
    compra-canale|boost individuale|boost gilda` — tutti i comandi
    previsti per §15.14 sono scritti, nessuna voce mancante (la
    tesoreria resta a senso unico per design, vedi sopra)
    → **Stato 04/10:** manca `/clan lascia`; lo scioglimento lascia i ruoli agli altri admin (REVIEW §12).
- `[~]` **15.15 Decadimento economico + cassa di server** (scope
  emerso in conversazione con l'utente dopo la stesura iniziale
  dello schema, non presente nell'elenco originale)
  → **Stato 04/10:** vedi le voci sotto.
  - `[~]` Decadimento settimanale 10% sui coin PERSONALI di
    QUALUNQUE membro del server (in un clan o no) — logica pura
    (`apply_weekly_personal_decay`, `week_key` in
    `core/leveling_logic.py`: mai negativo, mai sotto 1, sempre
    intero — 10% di 105 → 10 o 11, mai 10,5), persistenza atomica
    (`LevelingRepository.apply_weekly_decay`, colonna
    `last_weekly_decay_period` per riga) e worker (
    `core/weekly_personal_decay_worker.py`, stesso pattern tick
    orario/idempotente per periodo del worker di tesoreria di clan)
    tutti fatti e testati
    → **Stato 04/10:** scatta entro un'ora dalla creazione (REVIEW §4).
  - `[x]` Cassa di server: `core/repositories/guild_chest_repo.py`
    (tabelle `guild_chest` + `guild_chest_ledger`), alimentata da
    ENTRAMBI i decadimenti — quello settimanale personale
    (`weekly_personal_decay_worker`) e quello mensile della
    tesoreria di clan (`guild_clan_treasury_decay_worker`, aggiornato
    per depositare il delta nella cassa del server del clan). Saldo
    e ultimi movimenti consultabili con `/cassa saldo`
  - `[~]` Uso della cassa: premi per eventi organizzati nel server
    e/o acquisto di mesi di bot premium — lo sblocco premium è
    fatto (`/cassa sblocca-premium`); i premi evento sono fatti con
    due comandi distinti: `/assegna-lobby <importo>` (premio
    partecipazione — accredita `importo` coin a CIASCUN membro
    presente in un canale vocale nell'istante in cui il comando
    viene eseguito, bot esclusi; se nessuno è in vocale o la cassa
    non basta per l'intero gruppo non viene assegnato nulla) e
    `/assegna-winner <membro> <importo>` (premio vincitore —
    accredita `importo` coin a un singolo membro scelto), entrambi
    riservati a chi ha `manage_guild` e a spesa dalla cassa di
    server (non dalla tesoreria di un clan)
    → **Stato 04/10:** `/assegna-lobby` può addebitare due volte (LC-1).
  - `[~]` Sblocco premium a doppio cancello: **tempo** dal join del
    bot nel server (1° mese dopo 6 mesi, 2° dopo 1 anno, 3° dopo 2
    anni, confermato da `core.premium_pricing_logic.TIER_MONTHS_
    REQUIRED`) **E** costo in coin dalla cassa (500.000/5.000.000/
    50.000.000 sotto i 1.000 membri, ×10 per fascia successiva —
    numeri confermati dall'utente), arrotondato in eccesso a
    multipli di 25.000. `core.premium_purchase_service.
    purchase_premium_tier` orchestra i controlli (tempo, tier già
    comprato, saldo) prima di toccare la cassa; `guild_has_premium_
    access` in `core/premium.py` ora controlla anche questo stato
    oltre alla whitelist manuale — comando: `/cassa sblocca-premium`
    → **Stato 04/10:** doppio clic: doppio addebito (BUG-14).

## §16 FUN & IMMAGINI — SFW presente; NSFW da fare (fase F11)

- `[x]` 16.1 Mini-giochi — `/fun coinflip`, `/fun dice [facce]`,
  `/fun rps` (carta/forbici/sasso contro il bot), `/fun 8ball
  <domanda>`. A differenza di Ship/Rate (deterministici via hash,
  §16.5/§16.7), qui il risultato è genuinamente casuale ad ogni
  chiamata — è il punto di un mini-gioco (`core/minigames_logic.py`,
  ogni funzione riceve un `random.Random` dal chiamante, mai
  `random` globale usato direttamente, per restare testabile con un
  seed). **Sotto-comandi di un gruppo `/fun`, non comandi top-level
  separati** — vedi la nota tecnica sotto 16.8
- `[x]` 16.2 Image manipulation — `/fun grayscale`, `/fun invert`,
  `/fun blur [raggio]`, `/fun pixelate [dimensione-blocco]`, tutti
  con priorità allegato > utente menzionato > avatar dell'autore
  (`core/image_manipulation.py`, funzioni pure Pillow che restituiscono
  `bytes | None`, mai un'eccezione — `None` se l'input non è
  un'immagine apribile, stesso pattern di `core/image_thumbnail.py`).
  Validazione su tipo MIME e dimensione massima (15 MB) dell'allegato
  prima di elaborare. Il calcolo Pillow (CPU-bound) gira in
  `asyncio.to_thread(...)` nel cog, mai nel modulo `core/` puro.
  Sotto-comandi del gruppo `/fun` esistente — vedi nota tecnica sotto
  16.8, nessun nuovo slot top-level consumato
  → **Stato 04/10:** SEC-20 corretto il 04/10 (`b2303a5`). (da verificare live)
- `[x]` 16.3 Comandi meme — `/fun meme [top-text] [bottom-text]`,
  stile classico Impact (testo bianco, contorno nero) su qualunque
  immagine (allegato > utente menzionato > avatar autore), testo
  automaticamente a capo se troppo lungo (`core/meme_logic.py`,
  `ImageFont.load_default(size=...)` di Pillow, nessun file `.ttf`
  incorporato nel repository). Richiede almeno uno tra top/bottom
  text, altrimenti messaggio d'errore effimero. Stesso gruppo `/fun`,
  nessun nuovo slot top-level
- `[~]` 16.4 Comandi animal — `/fun animal <specie>` (cane/gatto/
  volpe), immagine casuale da tre API pubbliche GRATUITE, nessuna
  chiave richiesta: dog.ceo, thecatapi.com, randomfox.ca
  (`core/animal_fetcher.py` interpreta le risposte con `core/animal_
  api_logic.py`, logica pura testata senza rete con un server
  aiohttp finto — stesso principio già seguito per Twitch/YouTube).
  Restituisce un messaggio d'errore effimero (non un'eccezione) se
  la richiesta fallisce. Sotto-comando del gruppo `/fun` esistente,
  nessun nuovo slot top-level
  → **Stato 04/10:** nessun `defer` (LIM-24).
- `[x]` 16.5 Ship — percentuale deterministica via hash, non casuale
  ad ogni chiamata
- `[ ]` 16.6 Howgay — deliberatamente non fatto: troppo vicino a un
  attributo protetto (l'orientamento sessuale) per un giochino
  casuale, anche se comune in altri bot Discord
  → **Stato 04/10:** resta non fatto per il motivo scritto. Alternativa pianificata: misuratore casuale a tema libero, senza attributi protetti (NF-40).
- `[x]` 16.7 Rate — punteggio 0-10 deterministico via hash
- `[x]` 16.8 Altri comandi di intrattenimento classici — `/fun joke`,
  `/fun quote`, `/fun fact`, contenuto testuale curato a mano
  (`core/classic_entertainment_logic.py`), nessuna dipendenza esterna
  o chiave API richiesta (a differenza di §16.4/§16.9, che hanno
  bisogno di immagini vere da un servizio esterno). **Nota tecnica
  importante, vale anche per 16.1**: il bot era già a 96 comandi
  slash TOP-LEVEL su un limite GLOBALE di Discord di 100 (verificato
  con una prova reale, non solo letto sulla documentazione — caricare
  tutti i cog insieme e contare `bot.tree.get_commands()`). 7 nuovi
  comandi separati avrebbero sfondato il limite, con lo stesso
  identico effetto silenzioso di un nome duplicato: il cog caricato
  DOPO quello che sfonda il limite fallisce la registrazione senza
  errore visibile (`load_all_cogs` lo cattura e lo logga, non lo fa
  risalire). Per questo tutti i comandi di 16.1/16.8 vivono sotto UN
  SOLO gruppo (`cogs/fun/entertainment.py`, `/fun ...`), che consuma
  un solo slot top-level indipendentemente da quanti sotto-comandi
  contiene. Aggiunta una guardia di regressione in
  `tests/test_cog_manager_load_all.py` che fa fallire la suite se il
  totale supera 100 e avvisa se supera 90 — qualunque comando FUTURO
  di §16 (16.2/16.3/16.4/16.9) andrà sotto questo stesso gruppo o un
  gruppo analogo, non come nuovo comando top-level
  → **Stato 04/10:** Correzione al testo: i comandi di primo livello erano 97, non 96.
- `[~]` 16.9 Ricerca immagini SFW — `/fun search-image <query>`, via
  Pixabay (`PIXABAY_API_KEY`, opzionale come Twitch/YouTube ma —
  a differenza di quelle — il comando non può funzionare affatto
  senza: risponde spiegando come attivare la chiave gratuita invece
  di restare silenziosamente inutilizzabile). `safesearch=true`
  impostato SEMPRE nella richiesta: è Pixabay stesso, lato server, a
  garantire risultati SFW (`core/image_search_fetcher.py`/`core/
  image_search_logic.py`, logica pura testata senza rete). Sotto-
  comando del gruppo `/fun` esistente, nessun nuovo slot top-level
  → **Stato 04/10:** nessun `defer` (LIM-24); condizioni d'uso di Pixabay non rispettate (LIM-48).
- `[x]` 16.11 Voci piccole SFW (#131, r5) — `cogs/fun/fun_extra.py`:
  `/fun scegli`, `numero`, `testo` (largo, corsivo, grassetto corsivo,
  gotico, gotico grassetto, doppio tratto, maiuscoletto, emoji, applauso,
  separato, owo), `casuale` (preferiresti, argomento, consiglio, oggetto
  magico), `scherzo` (lancia, presa in giro, Google), `effetto`
  (arcobaleno, R.I.P., ricercato, triggered). In più `/fun dice formula`
  (3d6+2), `/fun joke tema`, `/fun fact animale`; `8ball` e `meme` con
  massimo di lunghezza e senza menzioni. Logica in
  `core/fun_extra_logic.py` e `core/image_effects_logic.py`. Restano
  fuori (servono API/chiavi o spazio nel gruppo): FUN-049..057, 066..073,
  GIF di reazione/azione (FUN-081..139), giochi di gruppo (FUN-007..021),
  telefono (FUN-079).
- `[~]` 16.10 NSFW / Rule 34 → **applicazione separata iYokai NSFW**
  → **Stato 21/10 (r9):** fatto, da provare live (`NSFW_TOKEN`; senza token non parte). Alternativa (D18):
  niente Rule 34 né altri siti «booru» (non dichiarano età e consenso, e hanno disegni di personaggi minorenni):
  la fonte è RedGifs, solo elementi di creatori **verificati**; disegni, AI e cosplay bloccati.
  - `[x]` Solo canali con flag NSFW, verificato a runtime a ogni post; comandi con il segno `nsfw` di Discord
  - `[x]` Comando ricerca: `/nsfw cerca tag` → contenuto a caso (tag della lista permessa)
  - `[x]` Auto-post configurabile: `/nsfw-admin autopost` ogni 30–1440 minuti, tag scelto o a caso
  - `[x]` **Filtro a due strati obbligatori**: `/nsfw-admin tag-aggiungi|tag-togli` + lista vietata fissa
    (`core/nsfw_filter_logic.py`), su ricerca manuale E auto-post
  - `[x]` Log con hash (SHA-256 dell'anteprima) di ogni immagine pubblicata; bottone «Segnala» che blocca in
    tutti i server
  - `[ ]` Invito solo dopo la verifica dell'identità sul pannello (NF-20): da fare con il pannello

## §17 OWNER / GLOBAL ADMIN

- `[x]` 17.1 Gestione Premium List (add / remove)
- `[x]` 17.2 Toggle flag premium per modulo
- `[x]` 17.3 Eval / Exec / Shell (con secondo fattore di conferma) —
  `/owner eval`/`/owner shell`, il codice/comando va mostrato per
  intero prima dell'esecuzione (bottoni Esegui/Annulla), ogni
  invocazione loggata in modo persistente
  → **Stato 04/10:** spenti di default in produzione (D7); BUG-23 corretto. (da verificare live)
- `[x]` 17.4 Blacklist globale utenti — cache come per i moduli,
  blocca ogni interazione tramite `BlacklistAwareCommandTree`
  → **Stato 04/10:** ora ferma anche bottoni, moduli e listener (SEC-10, SEC-21). (da verificare live)
- `[x]` 17.5 Blacklist globale server — uscita automatica su
  `on_guild_join` se già in blacklist, uscita immediata se aggiunto
  mentre il bot è già dentro
  → **Stato 11/10:** corretto (M 13.2): escono il bot principale e i cinque worker musicali
  (`core/blacklist_exit.py`), sia al comando sia all'ingresso. (da verificare live)
- `[x]` 17.6 Forced cog load / unload / reload — `/owner cog-load|
  cog-unload|cog-reload`. Due bug sistemici trovati e corretti
  facendolo: i nomi dei metodi Python collidevano con hook di ciclo
  di vita riservati di `discord.py` (`cog_load`/`cog_unload`,
  rompeva ogni cog del bot), e sia `registry.register()` che
  `scheduler.register_handler()` sollevavano su un reload legittimo
  (ogni cog con un modulo premium/handler scheduler era rotto)
- `[x]` 17.7 Annuncio globale a tutti i server — `/owner announce`,
  riusa la stessa catena di fallback del messaggio di benvenuto
  (system_channel → primo canale scrivibile → DM proprietario),
  estratta in un metodo generico su `iYokaiBot`
- `[~]` 17.8 Statistiche globali (guild count, shard health, RAM,
  latenza, comandi/minuto, errori) — `/owner stats`, contatori a
  finestra scorrevole di 60s (`core/bot_stats.py`)
  → **Stato 04/10:** `bot_stats` cresce senza fine (REVIEW §4).
- `[x]` 17.9 Leave guild forzato
- `[~]` 17.10 Pannello premium interattivo con conferma a due step e
  log persistente di ogni modifica — `/owner premium-panel`, Select
  + conferma, `premium_toggle_history` (append-only, distinta dallo
  stato più recente)
  → **Stato 04/10:** nessun controllo a 25 moduli (LIM-22).
- `[x]` 17.11 **Aggiornamento a caldo** — l'owner aggiorna il bot da
  Discord senza entrare nel server: il bot prende il codice rivisto da
  GitHub (oppure un file allegato dall'owner), controlla che sia
  valido, tiene una copia del vecchio, ricarica il cog e torna indietro
  da solo se il caricamento fallisce (D21, issue #141, fase F9)
  → **Stato 14/10:** `/owner cog reload` con le opzioni `commit` (solo `main`), `file` (.py o .zip) e `registro`; `core/hot_patch.py`, registro `hot_patch_log` (0134). Spento senza `ENABLE_HOT_PATCH=1`; i file di `core/` chiedono il riavvio. Da provare live.

## §18 ROUTER DEI CANALI E LOG SU FORUM — fatto per i log (fase F6)

- `[~]` 18.1 Un canale per **tipo** di uscita (NF-01, `core/channel_router.py`,
  migrazione 0028). Fatti i tipi di log: eventi, messaggi, voce, server
  (`/log canale tipo:…`, `/log stato`). Mod-log (casi), log dell'AutoMod,
  phishing e allarmi passano dal router con il loro canale di sempre come
  predefinito (forum e un solo avviso al proprietario). Resta fuori il benvenuto
- `[x]` 18.2 Canale di testo oppure forum; nel forum un post per tipo
  di log (D3). Il post nasce al primo log e, se cancellato, si ricrea
- `[x]` 18.3 `/log crea-canali` (categoria privata + un canale per tipo)
  e `/log crea-forum`, visibili solo al bot e a chi ha permessi di
  amministratore; tetto di 500 canali controllato
- `[x]` 18.4 Canale sparito o senza permessi: un solo DM al proprietario
  del server, poi niente finché un invio non riesce di nuovo (LC-6, M 5.5)
- `[x]` 18.5 Le impostazioni esistenti restano valide: senza una scelta per
  il tipo vale il canale generale `log_channel_id` (nessun dato da migrare)
- `[~]` 18.6 Ignora canali, utenti e prefissi: `/log ignora` (migrazione
  0029) vale per il log dei messaggi; gli altri log non lo usano
- `[ ]` 18.7 Log delle azioni oggi mai registrate: `/lock`, `/unlock`,
  `/slowmode`, `/clear`, `/untimeout`, `/unmute-role`, scadenza dei
  tempban, azioni dell'escalation

## §19 DATI, PRIVACY E GDPR — fatto per i dati personali (fase F5); restano policy e intent

- `[x]` 19.1 Registro dei dati personali: ogni tabella con `user_id` o
  `guild_id` è dichiarata, con il modo di cancellarla (NF-04) —
  `core/data_registry.py`, 87 tabelle (compresi `command_usage`,
  `rank_card_prefs`, `event_log`, `log_ignora`, `output_channels`); un test legge lo
  schema vero e fallisce se una tabella o una colonna con una persona non è dichiarata
- `[x]` 19.2 Uscita da un server: dati cancellati dopo 90 giorni,
  tranne ban e kick di sicurezza (D6, GDPR-1) — `on_guild_remove` segna `guild_presence.left_at`
  (migrazione 0034); un rientro prima dei 90 giorni azzera il conto; la colonna calcolata
  `moderation_cases.retain_for_security` (0035, rifatta in 0050) tiene ban, tempban, softban, kick, escalation dell'automod e mute con ruolo (#46)
  → **Scelta (da confermare):** la cancellazione richiesta dall'utente toglie tutto ciò che non è
  di sicurezza e dice cosa resta; non rifiuta l'intera richiesta.
- `[x]` 19.3 Cancellazione dei dati di un utente su richiesta (GDPR-2) —
  `core/forget_user_service.py`, una transazione; richieste in `data_deletion_requests` (0036),
  una in attesa per utente, esito senza dati personali, conservato 24 mesi
- `[x]` 19.4 Esportazione dei dati di un utente in un file (art. 15) — JSON sotto 8 MiB,
  senza token, solo righe DELL'utente (non quelle dove ha solo agito su altri), in ordine di chiave
  primaria, tabelle grandi accorciate e tagli dichiarati
- `[x]` 19.5 Pulizia giornaliera delle tabelle che crescono (GDPR-3,
  PERF-3) — `core/retention_worker.py` (scadenze nel registro: 30 giorni azioni concluse,
  90 verifiche, 180 automod e trascrizioni, 365 sicurezza/storico/casse); `event_log.id` BIGINT (0037)
- `[x]` 19.6 Comandi: richiesta dell'utente, approvazione dell'owner —
  `/utility privacy esporta|cancella`, `/owner privacy richieste|approva|rifiuta`. (da verificare live)
- `[ ]` 19.7 Privacy policy e termini pubblicati (serve anche per la
  verifica dell'app a 100 server)
- `[ ]` 19.8 Elenco delle funzioni che usano ogni intent privilegiato
  (serve per la domanda a Discord da 10.000 utenti, D11)
- `[ ]` 19.9 Token dei webhook salvati come hash; chiave dei token
  OAuth ruotabile (SEC-16, LIM-52)

## §20 NUOVA STRUTTURA DEI COMANDI — fatto (fase F7, D24/D25)

- `[x]` 20.1 13 gruppi: `/owner /admin /mod /modban /security /log
  /ticket /voice /music /level /clan /fun /utility` (NF-05, D2)
- `[x]` 20.2 Ogni gruppo dello staff ha i suoi permessi predefiniti:
  chi non può usare un comando non lo vede (SEC-1)
- `[x]` 20.3 Ogni gruppo funziona solo dentro un server (LC-2)
- `[x]` 20.4 `/owner` registrato solo nel server dell'owner
- `[x]` 20.5 Nessuna compatibilità con i vecchi nomi (D4)
- `[x]` 20.6 Al massimo 25 figli per gruppo e un livello di
  sotto-gruppi, controllati da un test (LIM-57)
- `[x]` 20.7 `COMMAND_LIST.md` rigenerato dall'albero vero
- `[x]` 20.8 Gruppi nascosti dalla lista a chi non li può usare, per ruolo scelto dall'admin (#148, OAuth2)
  → **Stato 12/10:** `core/command_permissions.py`: state firmato di **5 minuti** e **monouso**
  (`consuma_state`/`rilascia_state`), link con scope `applications.commands.permissions.update identify`,
  fusione con le regole già impostate dall'admin (una regola «nega» sul ruolo scelto diventa «consenti»),
  tetto di 100 regole, client HTTP, rinnovo del token (solo `invalid_grant` cancella; 429/5xx/rete lo
  tengono; un rinnovo alla volta per server), `command_permission_tokens` (0039, token cifrato, cancellato
  all'uscita del bot), aggancio a `imposta_ruolo`. **Fatto il 12/10:** l'indirizzo di ritorno (stessa
  `/oauth/callback` del restore, `gestisci_callback`) e il bottone-link «Nascondi i comandi…» sotto
  `/admin setup attiva` senza categoria (solo con OAuth2 configurato), nessun comando nuovo.
  **Stato 16/10 (r8):** il pannello web sceglie i ruoli con `imposta_ruolo` (i permessi si scrivono) e ha
  la sezione «Comandi nascosti»: stato (chi ha autorizzato e fino a quando, mai il token), link
  «Autorizza con Discord», «Riscrivi adesso» (una volta al minuto per server) e revoca.
  **Resta (`[~]`):** prova live. Senza autorizzazione resta la base (permessi di Discord + controllo nel codice).

## §21 LINGUE E RICERCA DEI COMANDI — da fare (fase F8)

- `[~]` 21.1 Tutti i testi in un file per lingua, italiano e inglese
  (NF-06) — `locales/it.json` e `locales/en.json` (stesse chiavi e segnaposto, `tests/test_i18n_completo.py`);
  `core/i18n.py` (`t`, `lingua_risposta`, `lingua_interazione`)
  → **Stato 14/10:** nel catalogo ci sono i messaggi del gestore errori, del controllo accessi e dei comandi di lingua.
  Gli altri cog scrivono ancora in italiano: si portano nel catalogo file per file, quando li si tocca (21.6).
- `[x]` 21.2 La lingua del server decide la lingua delle risposte pubbliche — `/admin lingua set`
  (solo `it`/`en`); le risposte che vede solo l'utente seguono la sua lingua personale, se l'ha scelta
  (`/utility lingua`, tabella `user_language`, migrazione 0130, nel registro dei dati). Senza database: italiano.
- `[x]` 21.3 Nomi e descrizioni dei comandi tradotti da Discord secondo la lingua dell'utente (D1) —
  `core/command_translator.py` + `locales/comandi.en.json` (nomi, descrizioni di tutti i 447 comandi e gruppi,
  owner compreso); `TraduttoreYokai` risponde per en-US/en-GB; l'impronta della sync include le traduzioni;
  test sull'albero vero (fratelli unici, nome 32, descrizione 100, totale 8000 contando la traduzione più lunga per campo).
  **Scarto da D1:** la base nel codice resta l'italiano (cambiarla vorrebbe dire rinominare ~300 comandi); l'inglese
  è la traduzione. Le descrizioni delle OPZIONI (562) non sono ancora tradotte (cricchetto `MINIMO_PARAMETRI_TRADOTTI`).
- `[x]` 21.4 `COMMAND_LIST_ITA.md` e `COMMAND_LIST_ENG.md` generati da `scripts/generate_command_list.py`
  (anche `/owner`, che prima mancava)
- `[x]` 21.5 `-cerca-comando`: sinonimi nelle due lingue, solo i comandi che l'utente può usare e con il
  modulo attivo — punteggio sul testo italiano E inglese, parole vuote e gruppi di sinonimi inglesi, risultati,
  completamento e pannello nella lingua di chi cerca (`cerca_*` nel catalogo); `filtra_per_moduli` toglie i
  comandi i cui moduli (`MODULE_*` del file) sono tutti spenti nel server. Restano in italiano le etichette dei
  bottoni del pannello. (da verificare live)
- `[ ]` 21.6 Risposte oggi in inglese (role menu, verify, spam-trap,
  benvenuti) portate nel file dei testi
  → **Stato 14/10:** non fatto qui: i cog sono di altre aree (utility/role menu, security, welcome). La
  struttura c'è (`t`, `lingua_interazione`, `testo_per`); ogni area porta i suoi testi quando tocca il file.

## §22 FUNZIONI NUOVE, PRIMO GRUPPO — da fare (fase F9)

- `[x]` 22.1 Ruolo automatico all'ingresso (NF-07)
  → **Stato 13/10:** `/gestione ruoli auto-aggiungi|auto-rimuovi|auto-elenco` (0080); salta i bot, aspetta schermata di verifica e ruolo Verify, in pausa durante un raid. Da provare live.
- `[x]` 22.2 Ruoli ridati a chi rientra entro 30 giorni (NF-07)
  → **Stato 13/10:** `/gestione ruoli auto-ricorda`: ruoli ricordati al massimo 30 giorni (0080).
- `[x]` 22.3 Ruoli dati dopo un ritardo (NF-07)
  → **Stato 13/10:** ritardo configurabile per regola, via scheduler (0080).
  → **Stato 21/10 (catalogo #123, giro r8):** condizioni «solo con» e «non con» altri ruoli (ricontrollate allo
  scatto dei ritardati), ruoli ridati se tolti a mano, sincronizzazione dei membri già presenti (RUO-034, 035, 036, 038;
  migrazione 0230). I ruoli a tempo dati da `/ruoli` non si ricordano all'uscita.
- `[x]` 22.4 Starboard (NF-08)
  → **Stato 13/10:** `/moduli starboard imposta|soglia|disattiva` (0081): un post per messaggio, canali vietati ai minori esclusi. Da provare live.
- `[x]` 22.5 Comandi personalizzati creati dal server: testo o embed,
  ruolo, pausa; prefisso facoltativo solo per questi (NF-09)
  → **Stato 13/10:** `/moduli comandi crea|modifica|elimina|elenco|prefisso`, `/utility tag` (0082); massimo 50 per server, menzioni neutralizzate. Resta lo scripting avanzato (condizioni, variabili, cron).
- `[x]` 22.6 Costruttore di embed con anteprima e modifica (NF-17)
  → **Stato 13/10:** `/moduli embed crea|modifica|pubblica|elenco|elimina` (0086), limiti Discord controllati al salvataggio.
- `[x]` 22.7 Immagine di benvenuto con avatar, nome e sfondo (NF-11)
  → **Stato 13/10:** `/gestione benvenuto immagine` (0084): 4 modelli e sfondo proprio. L'editor completo resta al pannello web (NF-20).
- `[x]` 22.8 Rank card come immagine (NF-12)
  → **Stato 11/10:** `/level rank` disegna la card (avatar, livello, barra, posizione, coin);
  colore e tema (scuro, chiaro, notte) salvati per utente (migrazione 0031).
  → **Stato 15/10:** sfondo con immagine propria (`/level rank sfondo:<immagine>`, 0202): ritagliata e ricompressa
  (JPEG 800x360, al massimo 256 KiB) con `safe_open_image` in un thread; vale anche per il profilo; `reimposta` la toglie.
  Per tutti (scelta: MEE6 la fa pagare, qui niente premium per un'immagine); lo staff la spegne nel suo server con
  `/level impostazioni card sfondi:No` (alternativa a LIV-057). `rank_card_prefs` e `rank_card_sfondi` sono nel registro dei dati.
- `[x]` 22.9 Ticket: modulo con domande prima dell'apertura (NF-13)
  → **Stato 13/10:** fino a 5 domande per pannello (`/admin ticket modulo-aggiungi|modulo-rimuovi|modulo-mostra`), finestra
  Discord, risposte nell'embed del ticket (migrazione 0100). Pannello con 0 domande: il ticket si apre subito.
- `[x]` 22.10 Ticket: più pannelli in un messaggio (NF-13)
  → **Stato 13/10:** fino a 25 pannelli per server (`pannello-crea|rimuovi|lista|pubblica`); un messaggio porta fino a 25 bottoni
  persistenti (`DynamicItem`, custom_id `tkt:pan:<id>`). Il pannello storico (`/gestione ticket panel`) resta com'è.
- `[x]` 22.11 Ticket: chiusura automatica per inattività o utente
  uscito (NF-13)
  → **Stato 13/10:** per inattività (`/admin ticket chiusura-auto`, scheduler, azione `ticket_autoclose`, 5 min - 30 giorni,
  vale per i ticket nati da un pannello) e quando l'utente lascia il server.
- `[x]` 22.12 Ticket: voto a fine ticket e limite per utente (NF-13)
  → **Stato 13/10:** voto a 5 stelle in DM alla chiusura (`/admin ticket voto`), una volta sola, media in `/gestione ticket stats`.
  Limite di ticket aperti per utente configurabile da 1 a 5, predefinito 1 (`/gestione ticket limite`, impostazione
  `ticket_max_per_utente`, migrazione 0106 che sostituisce l'indice unico con un controllo sotto blocco in `ticket_repo.create_ticket`).
- `[x]` 22.13 Modalità dei reaction roles: unique, verify, drop,
  reversed, binding, temp, lock; ruoli ammessi ed esclusi (NF-14)
  → **Stato 13/10:** `/gestione ruoli menu-crea|menu-modifica|menu-accesso|menu-elenco` (0085). Da provare live.
- `[x]` 22.14 Livelli: canali e ruoli senza XP, moltiplicatori, canale
  del level-up, premi "accumula" o "togli i precedenti", valori
  configurabili (NF-15)
  → **Stato 15/10 (catalogo #124/#125):** `/level premi` elenco pubblico di ruoli-premio e moltiplicatori (LIV-048, LIV-027);
  `/level attese` con le pause di daily e work (ECO-020); `/level livelli-recenti` con gli ultimi 25 level-up (LIV-039, 0203, anche ad annuncio spento).
  → **Stato 11/10:** `/level impostazioni` (mostra, annuncio, premi, xp,
  escludi, moltiplicatore); migrazione 0030; `core/repositories/leveling_settings_repo.py`.
  Annuncio: spento, canale corrente, DM, canale scelto, livello minimo, ogni N,
  solo con premio. Moltiplicatori: somma o massimo. Restano fuori `/daily` e `/work`
  (importi fissi) e il tetto di livello.
  → **Stato 13/10:** fatti anche gli importi di `/level daily` e `/work` e il livello
  massimo (LIV-005): `/level impostazioni xp daily|lavoro_min|lavoro_max|livello_massimo`
  (migrazione 0090). Al tetto gli XP salgono ma il livello no, e non c'è annuncio.
  → **Stato 14/10 (giro correzioni):** `/economia xp livello` ha un tetto assoluto di 1000
  (`LIVELLO_MASSIMO`) e `level_for_xp` usa la formula chiusa (nessun ciclo); l'XP a mano passa
  `esecutore` a `_grant_level_rewards`, che non dà né toglie ruoli sopra il ruolo più alto di chi
  ha lanciato il comando (il proprietario del server è escluso dal limite); il minimo del lavoro
  non supera il massimo per vincolo del database (migrazione 0099).
- `[x]` 22.15 Captcha a immagine nella verifica (NF-18)
- `[ ]` 22.16 Wizard di primo avvio per categoria, con creazione dei
  canali
- `[ ]` 22.17 Soglie sui warn dati a mano

## §23 FUNZIONI NUOVE, SECONDO GRUPPO — da fare (fasi F9, F13, F14)

- `[x]` 23.1 Canale richieste musicali con player e bottoni; playlist
  salvate (NF-19, fase F9)
  → **Stato 14/10:** `/admin musica canale-richieste` (0170): chi scrive un titolo, un link o allega un file nel canale lo mette in coda; messaggio player con 5 bottoni persistenti, aggiornato al massimo ogni 5 secondi. `/music playlist salva|carica|elenco|elimina|esporta|importa` (0171): 25 playlist per utente, 200 brani, file JSON (MUS-082). Da verificare live.
- `[x]` 23.2 Canali contatore (NF-16)
  → **Stato 13/10:** `/moduli contatori crea|elimina|elenco` (0087), aggiornamento ogni 10 minuti, massimo 5 per server.
- `[x]` 23.3 Statistiche di attività per canale e per membro, ruoli per
  attività (NF-25)
  → **Stato 14/10 (r5):** messaggi e minuti in vocale come somme per giorno
  (canale, membro, ora), scritte a lotti ogni minuto in 3 tabelle (0120),
  90 giorni di conservazione, dati personali nel registro dati. `/utility
  serverstats` ha le viste crescita, ingressi, uscite, canali, membri (anche
  per ruolo), ore, giorni della settimana, membro, con bottoni 7/30/90 giorni
  e Aggiorna. `/moduli statistiche impostazioni|ruolo-aggiungi|ruolo-elimina|
  elenco|diagnosi`: esclusioni di canali e ruoli, fino a 10 regole "ruolo a
  chi è attivo" (controllo ogni 30 minuti, al massimo 25 cambi per regola e
  giro). `activity_stats_repo.member_total` è il punto da usare per il
  requisito messaggi dei giveaway (oggi `giveaway_message_counts`, in
  `cogs/leveling`, non toccato qui).
- `[x]` 23.4 Compleanni (NF-26)
  → **Stato 13/10:** `/level compleanno imposta|rimuovi|mostra`, `/moduli compleanni canale|ruolo` (0088): solo giorno e mese.
- `[x]` 23.5 Inviti: comando personale e classifica (NF-27)
  → **Stato 13/10:** `/level inviti utente|classifica` (0089), con avviso sull'attribuzione (LC-6). Da provare live.
- `[x]` 23.6 Giveaway avanzati: modelli, più ingressi, requisito sui
  messaggi, programmati (NF-28)
  → **Nota:** il requisito sui messaggi conta dall'inizio del giveaway, non dallo storico (che arriva con NF-25): da far accettare all'owner.
  → **Stato 13/10:** `/economia giveaway` (min_messaggi, ruolo_bypass, ruolo_extra +
  ingressi_extra, inizia_tra) e `/economia giveaway-modello` (salva, elenco, elimina, avvia;
  25 modelli per server); migrazione 0091. I messaggi si contano **dall'inizio del giveaway** (non lo storico):
  il conteggio storico per canale e membro arriva con NF-25. Il worker fa partire i programmati.
  Avviso ai vincitori in thread e forum: già fatto (M 9.15).
  → **Stato 14/10 (revisione):** senza conferma l'acquisto nello shop vale per il prezzo letto (se cambia, nessun addebito); `/economia xp` avvisa se i ruoli-premio non si aggiornano; `/fun conteggio` e i giveaway programmati controllano i permessi del bot nel canale; l'annuncio dei vincitori avvisa solo i vincitori.
  → **Stato 14/10 (giro correzioni):** i comandi staff stanno nel gruppo `/economia` (D25), non più in `/gestione`.
  Il worker conclude un giveaway con una scrittura condizionata (`mark_ended` vero a uno solo: un annuncio solo);
  un programmato che non parte (canale sparito, bot senza permessi, invio rifiutato) non si chiude: resta con il
  motivo (migrazione 0098) e `/economia giveaway-programmati` lo elenca o lo annulla; «Partecipa» è rifiutato dopo
  `ends_at`; i messaggi si contano con l'attesa dell'XP e non nei canali esclusi; l'elenco dei modelli sta in 2000
  caratteri; il blocco dei salvataggi usa una chiave propria (non quella di `security_repo`).
- `[x]` 23.7 Blocco totale del server e "panic mode" (NF-29)
- `[ ]` 23.8 Anti-nuke con due soglie (al minuto e all'ora) e
  quarantena come punizione di default
- `[x]` 23.9 Appello anche per i ban dati a mano (NF-30) — `/modban appelli canale|elenco`; bottone «Fai appello» nel DM di ban e tempban, un appello ogni 24 ore, Accetta/Rifiuta solo a chi può bannare (da provare live); chi scrive al bot in privato con un ban manuale attivo riceve il bottone (stesso ingresso dei DM dello spam-trap, un bottone per server, al massimo 25)
- `[x]` 23.10 Blocco dei link di phishing (NF-31); accorciatori di link e inviti a server per adulti con interruttore proprio (SIC-042, r6)
- `[ ]` 23.11 Alert Kick e ruolo "in diretta" (NF-32)
- `[x]` 23.12 Ticket via messaggio privato (NF-33)
  → **Stato 13/10:** `cogs/tickets/modmail.py`: un DM apre un canale dello staff (`/admin ticket dm`), risposta anche anonima
  (`/ticket rispondi`), chiusura con transcript solo al log (`/ticket dm-chiudi`), blocco utenti (`/admin ticket dm-blocca`),
  menu se l'utente è in più server (migrazione 0101). Il testo dei messaggi non è salvato nel database.
  Con un solo server il primo DM chiede conferma con un bottone prima di creare il canale; il menu e la conferma scadono
  e liberano l'utente. Il blocco (`modmail_blocks`) è conservato come l'elenco della verifica.
- `[x]` 23.13 Moduli e candidature (NF-34)
  → **Stato 13/10:** `/moduli candidature crea|elimina|elenco`, `/utility modulo` (0096): fino a 5 domande, Accetta/Rifiuta persistenti, ruolo all'accettazione. Da provare live.
- `[x]` 23.14 Effetti sonori in vocale (NF-35)
  → **Stato 14/10:** `/music suono` (il gruppo `/fun` ha 25 figli): suono della soundboard del server o di Discord, mandato dal bot musicale del canale (la musica continua) o dal primo libero, che poi esce; pausa di 10 secondi per utente. Da verificare live.
- `[~]` 23.15 Bot con marchio proprio per i server premium (NF-38)
  → **Stato 14/10:** `/admin premium marchio` (token da finestra, cifrato; tabella `whitelabel_bots`, 0133): il bot del marchio sta online nel suo server con nome, avatar e testo di stato. **Stato 16/10 (r8):** anche dal pannello, pagina «Bot con marchio» del server (stato senza token, collega, testo di stato, accendi/spegni, scollega), dalle stesse funzioni di `core/whitelabel_bot.py`. **Manca:** far rispondere ai comandi il bot del marchio (oggi rispondono solo con iYokai). Da provare live.
- `[~]` 23.16 Profili, collezioni e giochi con le monete, senza soldi
  veri; gioco del conteggio (NF-40)
  → **Stato 15/10:** `/level profilo` è un'immagine (avatar, nome, presentazione, livello, XP, posizione, coin, collezione),
  con il colore dello sfondo comprato, il tema della rank card e lo sfondo con immagine propria; i badge (emoji) nel testo; se il disegno fallisce, l'embed di prima.
  → **Stato 13/10:** `/fun gioca` (monetina, dadi, slot; puntata 1-10000, una sola scrittura sul saldo, pausa di 5 s),
  `/fun misura` (tema libero, stabile per il giorno, rifiuta temi su caratteristiche protette),
  `/fun conteggio` (canale, spegni, stato; a turno, record) con `core/repositories/counting_game_repo.py` (migrazione 0092);
  `/level profilo` (presentazione di 140 caratteri, badge, sfondo come colore) e `/level collezione negozio|compra|equipaggia`
  (14 oggetti nel codice, migrazione 0093, acquisto atomico). Resta fuori: sfondo con immagine (serve il disegno della card
  e un controllo delle immagini) e profilo come immagine; le vincite dei giochi non contano nella classifica del mese.
  → **Stato 14/10 (giro correzioni):** l'attesa tra due partite la decide il database nella stessa scrittura
  della puntata (`leveling_totals.ultima_partita_at`, migrazione 0097): dieci richieste insieme giocano una partita
  sola; `/fun gioca` richiede anche il modulo Livelli; il filtro di `/fun misura` guarda le parole intere
  (non le sottostringhe) e normalizza lettere cirilliche/greche simili, caratteri invisibili, punteggiatura e
  lettere staccate.
- `[ ]` 23.17 Idee rimandate di `BACKLOG.md`: missioni, traguardi,
  serie, battle pass, profilo globale positivo, punteggio di rischio,
  carico dello staff (NF-41, fase F14)

## §24 PANNELLO WEB: CONFIGURAZIONE DEI SERVER — da fare (fase F10)

Completa la parte C più sotto (pagine di verifica e dell'owner).

- `[~]` 24.1 Accesso con Discord e scelta del server (NF-20)
  → **Stato 14/10:** `core/web_panel_server.py` (aiohttp, nello stesso processo del bot, porta `WEB_PANEL_PORT`): OAuth2 `identify` con `state` legato al browser, sessioni nel database (0150, solo l'impronta), cookie HttpOnly/SameSite=Lax (`Secure` e `__Host-` su https), CSRF, controllo dell'origine, limite di frequenza, CSP. Permessi come `/admin` controllati a **ogni** richiesta (`core/panel_bridge.py`, membri chiesti a Discord tenuti 30 s); il ruolo admin del bot si sceglie solo con «Amministratore» (D28); `X-Forwarded-For` letto solo dai proxy di `WEB_PANEL_TRUSTED_PROXY`. Spento senza le variabili del `.env`. Da provare live.
- `[~]` 24.2 Una pagina per modulo, con interruttore e impostazioni
  → **Stato 14/10:** una pagina per server: interruttore di ogni modulo (per categoria), ruoli del bot, lingua, storico, premium. Mancano le impostazioni interne di ogni modulo (canali, testi, soglie).
- `[~]` 24.3 Il pannello scrive le **stesse** impostazioni dei comandi,
  con gli stessi controlli (`core/config_schema.py`)
  → **Stato 14/10:** moduli e lingua da `core/config_schema.py` (usato anche da `/admin setup attiva`, configurazione guidata, `/admin lingua set`), ruoli da `core.command_access.imposta_ruolo`. Ogni nuova impostazione del pannello va prima portata in un punto unico.
- `[~]` 24.4 Il bot vede un cambio fatto dal pannello senza riavvio
  → **Stato 14/10:** il pannello gira nel processo del bot e scrive dagli stessi metodi del database, che svuotano le cache; parte anche `modules_updated`.
- `[ ]` 24.5 Editor visuali: embed, immagine di benvenuto, rank card,
  moduli dei ticket
- `[ ]` 24.6 Pagine legali: privacy policy e termini
- `[~]` 24.7 Pagamento del premium: abbonamento dentro Discord e
  pagamento esterno registrato dall'owner (NF-22)
  → **Stato 14/10:** fatti abbonamento Discord (`premium_entitlements`, 0131), `/admin premium stato` e codici (`/admin premium riscatta`, 0132); pagamento esterno = `/owner premium grant`. Pagina del pannello `/server/<id>/premium` fatta (stesse righe di `/admin premium stato` e link al negozio). Da provare live (serve l'app verificata).

## §25 MOTORE AI — in corso (fase F12, issue #95, #50, #132)

Stato 14/10 (r6): motore in `core/ai_*.py` (porta unica `core/ai_servizio.py`), fornitori dal `.env`
(D26), comandi `/ai`, `/utility ai`, `-chiedi`, `/ticket assistente`; migrazione 0140.

Prerequisiti: privacy policy pubblicata con l'elenco dei fornitori;
consenso dell'admin per server; tetto di spesa (D13). Vietato usare i
messaggi per addestrare modelli.

L'elenco completo delle funzioni AI discusse, con la fonte, chi l'ha
chiesta e come farla, è in `revisione/01-analisi/FUNZIONI_AI.md`. Ogni
voce qui sotto porta il suo codice `AI-R`. Le voci 25.1–25.9 sono
quelle di prima. Da 25.10 in poi ci sono le funzioni discusse che non
erano in questa lista: una voce per funzione, nell'ordine dei gruppi
di quel file.

- `[x]` 25.1 Router con più fornitori in cascata e risposta locale di
  riserva (NF-24; AI-R-001, AI-R-002, AI-R-007)
- `[x]` 25.2 Cache delle risposte a domande uguali o molto simili
  (AI-R-004)
- `[x]` 25.3 Filtri di sicurezza in ingresso e in uscita; dati personali
  tolti prima dell'invio (AI-R-013)
- `[x]` 25.4 Conteggio dell'uso e tetto di spesa per server (AI-R-009,
  AI-R-010)
- `[x]` 25.5 Helpdesk: risposte sui comandi e sul server (AI-R-024,
  AI-R-033)
- `[x]` 25.6 Riassunti di canali e ticket (AI-R-043, AI-R-075)
- `[x]` 25.7 Lore: tono e ambientazione scelti dal server (tabella e
  comando possono nascere prima del motore, vedi `BACKLOG.md` §8;
  AI-R-049, AI-R-051)
- `[x]` 25.8 Generazione di immagini (AI-R-065)
- `[x]` 25.9 Interruttore per server e per canale (AI-R-017, AI-R-019)

**Motore e infrastruttura**

- `[x]` 25.10 Pausa automatica del fornitore che dà errori (AI-R-003)
- `[x]` 25.11 Libreria dei contenuti generati, che cresce da sola
  (AI-R-005)
- `[~]` 25.12 Smistamento delle domande: prima regole e database, AI
  solo se serve (AI-R-006)
  → **Stato 14/10 (r6):** cache e libreria comune prima dell'AI; `-chiedi` torna alla ricerca per parole. Manca uno smistamento a regole per tutte le funzioni.
- `[x]` 25.13 Passaggio alle chiavi a pagamento con un interruttore
  (AI-R-008)
- `[x]` 25.14 Quota per utente (AI-R-011; catalogo AI-002)
- `[x]` 25.15 Quota per funzione (AI-R-012)
- `[x]` 25.16 Lista delle richieste vietate e limite di richieste per
  utente (AI-R-014)
- `[x]` 25.17 Regola "l'AI propone, una persona conferma" (AI-R-015)
- `[x]` 25.18 Livelli di privacy dell'AI per server (AI-R-016)
- `[x]` 25.19 Tempo di conservazione del contesto dell'AI (AI-R-018)
- `[~]` 25.20 Modulo AI in manutenzione o a mezzo servizio, senza
  fermare il resto (AI-R-020)
  → **Stato 14/10 (r6):** interruttore per server e per canale; se i fornitori sono fermi ogni funzione dà la sua risposta senza AI. Manca un interruttore "manutenzione" globale per l'owner.
- `[ ]` 25.21 AI in un processo separato (AI-R-021)
- `[~]` 25.22 Coda e limite per molte richieste insieme (AI-R-022)
  → **Stato 14/10 (r6):** limite al minuto per persona e per la moderazione (20 controlli al minuto per server). Manca una coda vera.
- `[~]` 25.23 AI come diritto premium a parte, con periodo di prova
  (AI-R-023)
  → **Stato 14/10 (r6):** modulo `ai` registrato: l'owner lo rende premium. Manca il periodo di prova.

**Assistente e helpdesk**

- `[x]` 25.24 Base di conoscenza caricata dall'admin (AI-R-025)
- `[~]` 25.25 Cerca comando a parole, in qualsiasi lingua (AI-R-026)
  → **Stato 14/10 (r6):** `-chiedi` risponde con l'AI nella lingua della domanda; `-cerca-comando` resta per parole.
- `[x]` 25.26 Registro unico dei comandi letto dall'AI (AI-R-027)
- `[~]` 25.27 Risposta con al massimo 3 comandi e bottoni che aprono la
  configurazione (AI-R-028)
  → **Stato 14/10 (r6):** al massimo 3 comandi, cliccabili. Mancano i bottoni che aprono la configurazione.
- `[ ]` 25.28 Stato del comando nella risposta (AI-R-029)
- `[ ]` 25.29 Ricerca che guarda il server e propone di attivare ciò che
  manca (AI-R-030)
- `[ ]` 25.30 Richiesta composta: più comandi in fila e "Configura
  tutto" (AI-R-031)
- `[~]` 25.31 Scoperta delle funzioni: "cosa posso fare qui?" (AI-R-032)
  → **Stato 14/10 (r6):** `-chiedi` risponde anche a "cosa posso fare qui?" con l'elenco dei comandi che la persona può usare.
- `[x]` 25.32 Il bot risponde in chat quando viene menzionato (AI-R-034;
  catalogo AI-009)
- `[x]` 25.33 Memoria corta della conversazione (AI-R-035; catalogo
  AI-011)
- `[~]` 25.34 Chiedere a parole di eseguire un comando (AI-R-036;
  catalogo AI-013)
  → **Stato 14/10 (r6):** un bot non può lanciare un comando slash per l'utente né precompilarlo: l'AI indica il comando cliccabile e i valori da mettere; la persona lo lancia.
- `[x]` 25.35 Costruzione del server con l'AI (AI-R-037; catalogo
  AI-025)
- `[~]` 25.36 Messaggi "nello stile" di un utente (AI-R-038; catalogo
  AI-024)
  → **Stato 14/10 (r6):** `/utility ai stile` usa solo i messaggi di chi lo chiede: imitare un'altra persona senza consenso non si fa (privacy).

**Moderazione e sicurezza con AI**

- `[x]` 25.37 Aiuto alla moderazione: l'AI segnala, lo staff decide
  (AI-R-039; catalogo AI-018)
- `[ ]` 25.38 Classificazione delle segnalazioni degli utenti (AI-R-040)
- `[ ]` 25.39 Riassunto di un incidente (AI-R-041)
- `[ ]` 25.40 Assistente per le regole di AutoMod (AI-R-042)

**Riassunti e ricerca**

- `[ ]` 25.41 Riepilogo del server, ogni giorno o ogni settimana
  (AI-R-044)
- `[ ]` 25.42 Contenuto del riepilogo fatto di numeri (AI-R-045)
- `[ ]` 25.43 Avviso su parole chiave quando una discussione si accende
  (AI-R-046)
- `[ ]` 25.44 Ricerca nei log con una domanda (AI-R-047)
- `[ ]` 25.45 Ricerca assistita sul web o su una base di conoscenza
  (AI-R-048)

**Lore, giochi e narrazione**

- `[x]` 25.46 Temi pronti (AI-R-050)
- `[ ]` 25.47 La lore viene chiesta durante il setup (AI-R-052)
- `[x]` 25.48 La lore entra in ogni testo dell'AI del server (AI-R-053)
- `[ ]` 25.49 World Boss: evento di gruppo contro un mostro (AI-R-054)
- `[ ]` 25.50 World Boss: comparsa a orario e avvio a mano (AI-R-055)
- `[ ]` 25.51 World Boss: mostro creato dall'AI secondo la lore
  (AI-R-056)
- `[ ]` 25.52 World Boss: danno secondo il livello, vita secondo i
  membri attivi (AI-R-057)
- `[ ]` 25.53 Dungeon di gruppo con scelte votate (AI-R-058)
- `[ ]` 25.54 Dungeon: la storia continua scritta dall'AI (AI-R-059)
- `[ ]` 25.55 Dungeon: esito secondo classi e livelli di chi vota
  (AI-R-060)
- `[ ]` 25.56 Misteri: frammenti di storia nascosti dall'admin
  (AI-R-061)
- `[x]` 25.57 Personaggi AI creati dagli utenti (AI-R-062; catalogo
  AI-014)
- `[x]` 25.58 Installare e togliere personaggi dal server (AI-R-063;
  catalogo AI-015)
- `[ ]` 25.59 Boss ed eventi di gioco uguali in più server (AI-R-064)

**Immagini, voce e media**

- `[x]` 25.60 Variazioni di un'immagine appena generata (AI-R-066;
  catalogo AI-005)
- `[x]` 25.61 Ingrandimento dell'immagine generata (AI-R-067; catalogo
  AI-006)
- `[x]` 25.62 Ingrandire e ripulire un'immagine caricata (AI-R-068;
  catalogo AI-007)
- `[x]` 25.63 Quota di immagini e pacchetti in più (AI-R-069; catalogo
  AI-008)
- `[ ]` 25.64 Immagine del boss nell'annuncio (AI-R-070)

**Ticket e staff**

- `[~]` 25.65 Bottone "Chiedi all'assistente" dentro il ticket
  (AI-R-071)
  → **Stato 14/10 (r6):** `/ticket assistente` al posto del bottone (il messaggio di apertura è dei file dei ticket).
- `[ ]` 25.66 Prima risposta automatica nei ticket (AI-R-072)
- `[x]` 25.67 Bozza di risposta per lo staff (AI-R-073)
- `[x]` 25.68 Smistamento dei ticket (AI-R-074)

**Livelli, economia e community**

- `[ ]` 25.69 Nomi a tema per moneta, punti e titoli (AI-R-076)
- `[ ]` 25.70 Premi del World Boss (AI-R-077)
- `[ ]` 25.71 Frammenti di lore da collezionare (AI-R-078)
- `[ ]` 25.72 Spirito Yokai: affinità che cresce con l'attività
  (AI-R-079)
- `[ ]` 25.73 Traguardo "primo comando scoperto con l'AI" (AI-R-080)

**Traduzione e lingue**

- `[x]` 25.74 Traduci un messaggio o un testo (AI-R-081; vedi B.2)
- `[x]` 25.75 Traduzione automatica dei messaggi di un canale (AI-R-082;
  catalogo AI-020)
- `[x]` 25.76 Traduzione reagendo con una bandiera (AI-R-083; catalogo
  AI-021)
- `[ ]` 25.77 Traduzione che raccoglie i messaggi successivi dello
  stesso autore (AI-R-084; catalogo AI-022; NF-36)
- `[x]` 25.78 Elenco delle lingue per la traduzione (AI-R-085; catalogo
  AI-023; NF-36)
- `[x]` 25.79 Riconoscere la lingua della domanda (AI-R-086)
- `[x]` 25.80 Cache delle traduzioni (AI-R-087)
- `[x]` 25.81 L'AI risponde nella lingua giusta (AI-R-088; catalogo
  AI-016)

**Owner e analisi**

- `[~]` 25.82 Scelta del modello e della lunghezza delle risposte
  (AI-R-089; catalogo AI-012)
  → **Stato 14/10 (r6):** lunghezza delle risposte per server (`/ai privacy`); i modelli si scelgono nel `.env` per fornitore.
- `[x]` 25.83 Spesa e uso visti dall'owner (AI-R-090)
- `[ ]` 25.84 Richieste di cancellazione dei dati lette prima dall'AI
  (AI-R-091)

**App utente e Desktop**

- `[ ]` 25.85 Cerca comando e scoperta delle funzioni dentro l'app
  utente (AI-R-092)
- `[ ]` 25.86 Assistente AI personale (AI-R-093)
- `[ ]` 25.87 Preferenza personale: assistente acceso o spento
  (AI-R-094)
- `[~]` 25.88 Spiega o riassumi un messaggio (AI-R-095; vedi B.2)
  → **Stato 14/10 (r6):** `/utility ai spiega` con il link del messaggio; il menu sul messaggio arriva con l'app utente (B.2).
- `[x]` 25.89 "Spiega questo Yokai": scheda di lore a richiesta
  (AI-R-096)
- `[ ]` 25.90 Desktop: traduzione rapida (AI-R-097; vedi D.8)

**Pannello web**

- `[ ]` 25.91 Pagina AI del pannello (AI-R-098; vedi 24.2)
- `[ ]` 25.92 Riepilogo del server visibile sul pannello (AI-R-099)
- `[ ]` 25.93 Pagina "Uso dell'AI" nel centro privacy (AI-R-100)

**Richieste dell'owner del 05/10/2026** (D19)

- `[~]` 25.94 Scelta del servizio per tipo di lavoro e per fascia:
  chat semplice, testo, giudizio, codice, traduzione, confronto,
  immagini, audio, musica, video (AI-R-101)
  → **Stato 14/10 (r6):** tipi chat, testo, giudizio, codice, traduzione, confronto, immagine; audio, musica e video sono accettati nella configurazione ma non hanno ancora un trasporto.
- `[x]` 25.95 Quote di ogni servizio contate in anticipo, con cambio
  di servizio prima di finirle (AI-R-102)
- `[x]` 25.96 Controllo delle chiavi ogni ora e avviso all'owner
  (AI-R-103)
- `[~]` 25.97 Risposte standard imparate dalle risposte dello staff
  nei ticket, con i loro allegati (AI-R-104; vedi §13)
  → **Stato 13/10 (parte senza AI):** alla chiusura il bot propone nel canale dei log la prima risposta dello staff (allegati
  ricaricati nel log); bottoni Approva/Modifica/Scarta (persistenti); ricerca per parole (`core/ticket_standard_logic.py`);
  accese per pannello (`/admin ticket standard`), migrazione 0102. Resta con l'AI: scelta della risposta migliore e delle
  parole chiave, riconoscimento del tema oltre le parole, archivio durevole dei file (oggi: link nel canale dei log).
  **Dati personali (giro 14/10, migrazione 0105):** la riga ricorda `user_id` di chi aveva scritto (esportazione e cancellazione
  dati nel registro); titolo, parole e corpo non tengono menzioni, e-mail, link, numeri lunghi né il nome dell'utente
  (`{utente}` nel corpo, sostituito al momento dell'uso); se dopo la risposta pronta l'utente scrive ancora, lo staff è chiamato.
  → **Stato 21/10 (parte con l'AI):** se le parole non bastano e l'AI è accesa nel server, l'AI sceglie tra le sole risposte
  approvate (`core/ticket_ai_logic.py`, porta `core/ai_servizio.py`); non scrive testo libero. Restano: parole chiave proposte
  dall'AI e archivio durevole dei file.
- `[x]` 25.98 Ticket senza risposta dopo N minuti: il bot chiede
  nella lingua dell'utente, risponde se sa, altrimenti chiama il ruolo
  giusto (AI-R-105; vedi §13)
  → **Stato 13/10 (parte senza AI):** timer nello scheduler (`ticket_sollecito`, `/admin ticket sollecito`), domanda in
  italiano, risposta standard se c'è, altrimenti chiama il ruolo scelto per il pannello (o i ruoli di supporto). Resta con
  l'AI: lingua dell'utente e scelta tra moderatore e amministratore secondo il caso.
  → **Stato 21/10 (parte con l'AI):** sollecito tradotto nella lingua dell'utente (senza AI: italiano o italiano e inglese);
  se il pannello non ha un ruolo scelto, l'AI dice se chiamare il ruolo moderatore o amministratore del bot (senza AI:
  i ruoli di supporto). (da verificare live)
- `[ ]` 25.99 Storie di dungeon intere, con tutte le strade e i
  finali, salvate e riusate in ogni server con lo stesso tema
  (AI-R-106)
- `[ ]` 25.100 Funzione richiesta che non esiste: bozza del codice in
  una pull request per l'owner (AI-R-107)
- `[ ]` 25.101 Cerca comando: mostra anche le alternative, spiegate
  (AI-R-108; vedi §21)
- `[ ]` 25.102 Sintesi vocale sul server, con cache dell'audio e toni
  della voce scelti dall'admin (AI-R-109; vedi 14.19)
- `[ ]` 25.103 Trascrizione e traduzione del vocale nella lingua di chi
  preme il bottone (AI-R-110)
- `[ ]` 25.104 Trascrivi e traduci i vocali registrati dalle persone,
  anche dall'app utente (AI-R-111)
- `[ ]` 25.105 Saluti a voce: risposta al "buongiorno" con il nome, una
  sola risposta per più persone (AI-R-112)

---

# B. iYOKAI APPLICATION (user-installable) — in corso (NF-36, fase F13)

**Stato 21/10 (r9):** applicazione separata (`YOKAI_APP_TOKEN`, `core/user_app_bot.py`, albero suo):
`/promemoria crea|elenco|annulla` (DM), `/profilo`, menu «Profilo» e «Testo pulito». Sul bot principale
`-cerca-comando` e `-chiedi` sono installabili dall'utente (dove il bot non c'è valgono come in DM). I comandi
installati sull'utente contano negli stessi 100 dell'app (`LIMITI.md` §1.3).

Comandi che l'utente installa **su di sé** e usa ovunque: in qualsiasi
server (anche dove il bot non c'è), nei DM e nei gruppi. L'elenco
completo, con limiti e motivi, è in
`revisione/01-analisi/APP_UTENTE_E_DESKTOP.md`.

- `[x]` B.1 Applicazione separata con installazione sull'utente
  (`USER_INSTALL`) e i tre contesti (server, DM con il bot, DM e gruppi)
- `[ ]` B.2 Menu sul messaggio: Traduci, Salva nei segnalibri,
  Ricordamelo, Citazione come immagine, Meme da questa immagine,
  Controlla i link, Segnala alla rete iYokai, Spiega/riassumi (AI)
- `[~]` B.3 Menu sull'utente: Profilo iYokai (fatto: scheda Discord; mancano livello e clan), Stato nella rete di
  sicurezza (solo per chi lo chiede, risposta privata)
- `[~]` B.4 Utility personali: promemoria (fatto), note, liste, fusi orari,
  conversioni, calcolatrice, QR, colori
- `[ ]` B.5 Risposte salvate personali ("comandi custom" dell'utente):
  testi ed embed richiamabili ovunque
- `[ ]` B.6 Profilo globale: livello, clan, medaglie, rank card
- `[ ]` B.7 Divertimento e immagini ovunque (stessi comandi di `/fun`)
- `[ ]` B.8 Musica senza bot nel canale: Attività "radio iYokai"
  (ascolto condiviso dentro un'Attività di Discord), testi, playlist
  personali
- `[ ]` B.9 Assistenza: apri un ticket con il supporto iYokai da ovunque
- `[ ]` B.10 Storico dei propri comandi e impostazioni personali
  (lingua, risposte private o pubbliche)

---

# C. WEB PANEL (iYokai Panel) — da fare (NF-20, NF-21, fase F10)

- `[ ]` C.1 Pagina di verify avanzato (IP, ISP, geo, fingerprint)
  → **Stato 04/10:** in piano: NF-21, fase F10.
- `[ ]` C.2 Flusso OAuth2 `identify` (verify)
- `[ ]` C.3 Flusso OAuth2 `guilds.join` separato (restore utenti)
- `[ ]` C.4 Dashboard owner: premium list, toggle moduli premium
  → **Stato 04/10:** in piano: NF-20, fase F10. Le pagine di configurazione dei server sono in §24.
- `[ ]` C.5 Privacy policy pubblicata + informativa GDPR (prerequisito
  legale per C.1, non opzionale)
  → **Stato 04/10:** anticipata alla fase F5 (NF-04): serve anche per la verifica dell'app.

---

# D. iYOKAI DESKTOP — da fare (NF-37, fase F13)

Programma per PC collegato al proprio account iYokai (accesso con
Discord). Offre in modo regolare ciò che programmi come Nighty fanno
automatizzando l'account dell'utente. L'elenco completo, funzione per
funzione, è in `revisione/01-analisi/APP_UTENTE_E_DESKTOP.md`.

- `[✗]` D.0 Modulo selfbot con user token — **scartato**: viola i ToS
  Discord e fa bannare l'utente finale. Ogni funzione di quel tipo è
  sostituita qui sotto dall'alternativa regolare più vicina.
- `[ ]` D.1 App locale collegata al client Discord (IPC) e al servizio
  iYokai (accesso OAuth2, canale in tempo reale)
- `[ ]` D.2 Stato personalizzato (rich presence): attività, immagini,
  testi, bottoni, tempo
- `[ ]` D.3 Rotazione automatica di più stati
- `[ ]` D.4 Profili salvati
- `[ ]` D.5 Notifiche a schermo: menzioni, parole chiave, risposte ai
  ticket, promemoria, giveaway vinti, dirette, avvisi per lo staff
- `[ ]` D.6 Storico delle menzioni con salto al messaggio (nei server
  dove c'è iYokai)
- `[ ]` D.7 Storico dei propri comandi e delle azioni fatte dal bot per
  conto dell'utente
- `[ ]` D.8 Traduzione rapida (appunti e tasto rapido) e risposte
  salvate da incollare
- `[ ]` D.9 Pannello rapido per lo staff: azioni eseguite dal bot nei
  server dove l'utente ha i permessi (blocca canale, timeout, giveaway)
- `[ ]` D.10 I miei server: elenco, dove c'è iYokai, dove sono staff
  (scope OAuth2 `guilds` e `guilds.members.read`)
- `[ ]` D.11 Funzioni che richiedono l'approvazione di Discord (scope
  `rpc`): notifiche del client, controllo di microfono e cuffie
- `[✗]` D.12 Stato testuale con emoji, bio animate, avatar e banner a
  rotazione, temi del client — **impossibile senza user token**.
  Alternativa: D.2, il profilo globale B.6 e i "Game Stats Widget" del
  profilo Discord, se l'app viene ammessa.

---

# E. APPLICAZIONI DEL PROGETTO

Bot che girano nello stesso processo: principale, Mod, Creator, 5
musicali, più NSFW quando verrà fatto.

- `[~]` iYokai (principale) — comandi e interfaccia
- `[~]` iYokai Mod (log e moderazione) — D15. Facoltativo (`YOKAI_MOD_TOKEN`), nessun comando e
  nessun listener: gli eventi li ascolta il principale, `core/bot_roles.py` sceglie per server chi
  scrive i log (router, mod-log, AutoMod, allarmi) ed esegue AutoMod, escalation, anti-raid,
  anti-nuke, spam-trap e fine dei tempban. Mod assente, scollegato, senza permesso, sotto il
  bersaglio o in rate limit lungo (oltre 30 s) → fa il principale, una volta sola. Invito in
  `/utility info`. Non fatto: canali di log via webhook (Mod ha già limiti suoi)
- `[~]` iYokai Creator (backup) — resta; non crea più server, porta e
  tiene aggiornato il server di backup (D8, §11)
- `[~]` iYokai Music #1-5 — vedi §9
  → **Stato 04/10:** il codice c'è; l'audio dei worker va corretto (LIM-40, D10).
- `[~]` iYokai NSFW — vedi §16.10 (fatto r9, da provare live)
- `[~]` iYokai App (installabile dall'utente) — vedi B (prima parte r9)
- `[ ]` iYokai Desktop — vedi D
- `[ ]` iYokai Panel (sito) — vedi C e §24

---

# Note storiche (fino al 28/09/2026)

**Il conteggio aggiornato è nel riquadro "Legenda e stato" in cima al
file.** Il testo qui sotto è la cronaca delle sessioni precedenti,
tenuta come storico. I numeri e i "COMPLETO al 100%" che contiene **non
valgono più**: la revisione del 28/09 (`revisione/01-analisi/REVIEW.md`
§12) ha mostrato che molte voci segnate fatte non lo erano.

Su 273 voci totali: **167 fatte, 1 parziale, 105 mancanti** — circa
il 61% dello schema (contando i parziali a metà peso). **§15 Levels/
Gilde è ora COMPLETO al 100%** (34/34): chiusa l'ultima voce parziale
rimasta in tutto §15, la variante MENSILE di 15.10 Classifica Gilde,
più l'annuncio automatico della top 3 in "bacheca clan" richiesto
esplicitamente dall'utente. **§10 Alerts
& Social: la parte "webhook" di §10.8 è ora fatta** (endpoint
proprio in ricezione, `/alerts webhook-create`, token segreto
mostrato una sola volta) — §10 resta parziale solo per §10.4
(YouTube live, rimandato per limiti di API, non un debito di questa
sessione). **§11 Backup
System è ora COMPLETO al 100%** (13/13): orchestrazione
automatizzabile, mirror in tempo reale, auto-propagazione e restore
utenti via OAuth2 con la progettazione di sicurezza concordata
esplicitamente con l'utente (cifratura AES-256-GCM, tre modalità di
consenso, retention differenziata per uscita/kick/ban). §15
Levels: il Sistema Gilde/Clan (§15.14) ha ora il motore economico,
tutti i comandi Discord previsti (`/clan crea|info|membri|classifica|
sciogli|tesoreria dona|tesoreria trasferisci|invita|espelli|
promuovi|compra-canale|boost individuale|boost gilda`), il worker di
eliminazione automatica, i ruoli Discord condivisi Capo Clan/Admin
Clan, l'acquisto di canali extra con doppio requisito (coin + ore
vocali accumulate dalla gilda), i boost XP/coin ×2 per 24h
(individuale e di gilda, si moltiplicano tra loro), e ORA anche il
trasferimento tesoreria→tesoreria tra due gilde dello STESSO owner
ANCHE cross-server (`/clan tesoreria trasferisci`) — un debito di
documentazione trovato durante un controllo dell'utente e chiuso in
questa sessione: `transfer_between_treasuries` esisteva già dal
secondo pezzo del repository (l'ID globale dei clan, non per server,
era stato scelto proprio per questo) ma non era mai stato collegato
a nessun comando Discord né tracciato in questo schema. ORA anche il
lato TESTUALE del guadagno ×2 è fatto (`GuildClanRepository.
apply_text_tick`, agganciato a `on_message`) — e nello stesso
controllo si è corretta una discrepanza reale trovata nel lato
vocale: la prima calibrazione usava 30 XP/2 coin al tick (un target
mensile assoluto), non il ×2 letterale dichiarato qui; ora è 10 XP/4
coin, ×2 esatto del vocale normale. **§15.14 è ORA COMPLETO**: la
voce che sembrava ancora aperta (un comando di PRELIEVO dalla
tesoreria verso un membro) era un fraintendimento di una sessione
precedente, chiarito esplicitamente dall'utente in questa sessione —
la tesoreria di clan resta a SENSO UNICO per design (membro -> gilda
sempre, gilda -> membro MAI), e il bisogno reale di "premio evento"
è già servito da un percorso diverso e corretto: la cassa DI SERVER
(§15.15), non la tesoreria di un singolo clan. Il decadimento
mensile 10% sulla tesoreria (l'altra voce `[~]` di §15.14) è ORA
COMPLETO: bug di race condition trovato e corretto — il delta
depositato nella cassa di server era calcolato sul saldo "stale"
letto da `list_officialized_clans()` (non sotto lock) invece che
sulla coppia `(saldo_prima, saldo_dopo)` letta sotto lo stesso `FOR
UPDATE` di `apply_monthly_decay`, stesso pattern già corretto di
`LevelingRepository.apply_weekly_decay`. Unica voce genuinamente
ancora aperta in tutto §15: la variante MENSILE di 15.10 Classifica
Gilde (oggi solo il totale cumulativo). §15.15
(non nello schema
originale, emersa in conversazione) è ORA COMPLETO: decadimento
settimanale personale, cassa di server alimentata da entrambi i
decadimenti, sblocco premium a doppio cancello (tempo dal join +
costo dalla cassa) — comandi `/cassa saldo` e `/cassa
sblocca-premium` — e ORA anche i due comandi di spesa dedicati ai
premi evento: `/assegna-lobby <importo>` (premio partecipazione, a
tutti i presenti in vocale nell'istante dell'esecuzione) e
`/assegna-winner <membro> <importo>` (premio vincitore, a un membro
scelto), entrambi a spesa dalla cassa di server.

Correzione del 21/09: il marcatore parziale (`` `[~]` ``) era definito nella
legenda ma non era mai stato usato — §9.4/9.5 e §10.8 erano marcati
come completamente fatti quando in realtà erano solo iniziati.
Audit a campione sul resto del documento (§5, §6, §12, §13, §15) non
ha trovato altri casi: i comandi/funzionalità elencati nelle voci
controllate esistono davvero nel codice.

**§12 Temporary Voice Channels è ORA COMPLETO al 100%** (8/8):
notifica personale alla creazione del canale (automatica E manuale,
prima solo quest'ultima rispondeva), selezione piattaforma PC/
Console/Mobile puramente informativa (`/voicetemp-platform-setup`),
cap configurabile per categoria (`/voicetemp-cap`, sempre troncato al
limite hard di Discord di 50).

**§13 Ticket System è ORA COMPLETO al 100%** (13/13): select menu
categorie (`/ticket-category`), force close riservato allo staff
(`/ticket forceclose`), transcript automatico alla chiusura inviato
nel canale log + in DM all'utente (`/ticket close`/`forceclose`, via
`channel.history()` PRIMA di cancellare il canale — **non richiede
il Message Content Intent**, verificato: quell'intent riguarda solo
gli eventi gateway in tempo reale, non la history REST governata dal
normale permesso Read Message History, stessa assunzione già
verificata per lo Spam Trap), statistiche (`/ticket-stats`, tempo
medio di prima risposta per operatore o per server), ruoli di
supporto multipli (`/ticket-support-role`, combinati col ruolo
legacy singolo per retrocompatibilità).

**§14 Utility: chiusi 14.11 Reactionsnipe e 14.12 Ghost ping
detection**, entrambi VERIFICATI punto per punto contro il Message
Content Intent invece di essere liquidati in blocco come "famiglia
snipe bloccata" (l'errore già fatto e corretto su §8.13/§8.8, vedi
Fase 70b): nessuno dei due ha bisogno del contenuto del messaggio
(`on_raw_reaction_remove` non lo richiede affatto; `Message.mentions`
arriva da un campo gateway separato dal contenuto, non azzerato
dall'intent). 14.9 Snipe, 14.10 Editsnipe e 14.7 Autoresponder restano
`[ ]` — genuinamente bloccati, stesso motivo di §8.16: servono il
contenuto del messaggio nel momento stesso dell'evento gateway
(`on_message`/`on_message_delete`/`on_message_edit`), che è
esattamente il campo azzerato senza il Message Content Intent, e a
differenza del transcript ticket non c'è modo di recuperarlo dopo
via REST (per Snipe/Editsnipe il messaggio non esiste più; per
l'Autoresponder la decisione va presa SUBITO, non in un secondo
momento).

**§2 Setup & Dashboard: chiusi 2.1 Reset configurazione, 2.2 Wizard
guidato, 2.5 Esporta configurazione, 2.6 Importa configurazione**
(`/config reset`, `/setup-wizard`, `/config export`, `/config
import`). Reset e import sovrascrivono la configurazione IN BLOCCO
(mai un merge) con una singola voce di storico ciascuno, annullabile
con `/config rollback` come qualunque altra voce. Il wizard
(`/setup-wizard`) è un'esperienza deliberatamente diversa da
`/setup`: un modulo curato alla volta (Moderazione, AutoMod, Logging,
Greetings, Vocali temporanei, Ticket) con Attiva/Disattiva + Avanti/
Indietro, invece del select menu con tutti i moduli insieme.
**2.3 Lingua per server è marcata `[~]`, non `[x]`**: il comando
(`/config language show|set`) e la colonna `language` sono ora
davvero collegati, con un piccolo registro di traduzioni
(`core/i18n.py`) per un insieme limitato di stringhe generiche
condivise — ma NON è un sistema i18n applicato a tutto il bot, che
resta in italiano nella stragrande maggioranza dei suoi messaggi;
tradurre l'intero bot è un lavoro enormemente più grande di questa
singola voce e non è stato tentato. 2.4 Prefisso personalizzato resta
`[✗]` scartato (slash-command-only, decisione già presa in una
sessione precedente).

**§3 Premium System è ORA COMPLETO al 100%** (11/11): mancavano solo
due comandi di sola LETTURA, mai scritti prima perché add/remove/
toggle bastavano per il lavoro quotidiano ma non davano una vista
d'insieme. `/owner whitelist-list` elenca i server whitelistati
(id, chi li ha aggiunti, quando, motivo) — nessuna sorpresa nella
query, solo un `ORDER BY added_at`. `/owner premium-status-all`
itera su TUTTI i server in cui il bot è presente e mostra, per
ciascuno, OGNI meccanismo di sblocco davvero attivo (whitelist/
nitro boost sul server principale/premium via cassa/abbonamenti per
modulo) invece di un singolo True/False — nuova funzione pubblica
`core.premium.get_guild_premium_breakdown()`, che riusa la stessa
logica già verificata di `guild_has_premium_access` (stessi
repository, stesse condizioni) ma restituisce il dettaglio completo
invece di fermarsi al primo sblocco trovato. Formattazione delle
righe estratta in `core/premium_status_logic.py`, logica pura
testabile senza database né bot vero — stesso principio già seguito
per ticket/snipe.

**§10 Alerts & Social è ORA COMPLETO al 100%** per tutto ciò che non
è stato esplicitamente scartato: 10.4 YouTube live era l'ultima voce
rimandata (vedi la nota più sopra in questo stesso documento,
risalente a una sessione precedente — "§10 resta parziale solo per
§10.4"), ora chiusa con lo stesso principio già usato per Twitch
(§10.1/§10.2): un metodo di sblocco opzionale via variabile
d'ambiente (`YOUTUBE_API_KEY`), watcher (`core/youtube_watcher.py`)
inattivo finché non è configurata, nessun impatto sull'avvio del bot
per chi non la usa. `core/youtube_api_logic.py` interpreta la
risposta di `videos.list` (logica pura, testata senza rete);
`core/repositories/youtube_subscription_repo.py` persiste le
sottoscrizioni (stesso schema di twitch_subscription_repo.py);
`/alerts add-youtube-live` le crea (prefisso `YT-`, integrato in
`/alerts list`/`/alerts remove` esistenti). 10.5 TikTok, 10.6
Instagram e 10.13 X/Twitter restano `[✗]` scartati, decisioni già
prese e confermate dall'utente in sessioni precedenti — non
rivisitate qui.

**§16 Fun & Immagini: chiusi 16.1 Mini-giochi e 16.8 Altri comandi
di intrattenimento classici** (2/0/13 → 4/0/11), primo dei tre lotti
in cui è stato diviso questo settore (16.2/16.3 Pillow-based e
16.4/16.9 basati su API esterne seguiranno in commit separati — la
sezione è troppo ampia per un solo giro, ma resta un unico punto
della direttiva "fai tutto a parte bcde"). Entrambe le voci sono
testuali/casuali, senza bisogno di rete o chiavi API: `/coinflip`,
`/dice`, `/rps`, `/8ball` (`cogs/fun/minigames.py`, `core/minigames_
logic.py`) e `/joke`, `/quote`, `/fact` (`cogs/fun/classic_
entertainment.py`, `core/classic_entertainment_logic.py`, liste
curate a mano). Entrambi i cog condividono il modulo "fun" già
registrato da `cogs/fun/ship_rate.py` (Ship/Rate, §16.5/§16.7) —
stesso raggruppamento logico per l'utente finale, non un modulo
separato per ogni singolo comando.

**§16 Fun & Immagini, secondo lotto: chiusi 16.2 Image manipulation
e 16.3 Comandi meme** (4/0/11 → 6/0/9), tutto basato su Pillow, senza
alcuna dipendenza esterna o chiave API (a differenza del terzo lotto
previsto, 16.4/16.9, che avrà bisogno di un servizio esterno per le
immagini di animali/ricerca SFW). Cinque nuovi sotto-comandi —
`/fun grayscale`, `/fun invert`, `/fun blur [raggio]`, `/fun pixelate
[dimensione-blocco]`, `/fun meme [top-text] [bottom-text]` — tutti
aggiunti come sotto-comandi del gruppo `/fun` già esistente in
`cogs/fun/entertainment.py` (nessun nuovo slot top-level: il conteggio
resta a 97/100, verificato dalla guardia di regressione in
`tests/test_cog_manager_load_all.py`). Logica pura in due nuovi
moduli, entrambi con lo stesso pattern già seguito da
`core/image_thumbnail.py` (`Image.open(io.BytesIO(...))` in un
try/except che restituisce `None`, mai un'eccezione, se l'input non è
un'immagine apribile): `core/image_manipulation.py` (grayscale,
invert, blur con raggio limitato 1-50, pixelate con dimensione
blocco limitata 2-100) e `core/meme_logic.py` (testo bianco con
contorno nero in stile Impact, `ImageFont.load_default(size=...)` di
Pillow — nessun file `.ttf` incorporato nel repository, stesso
principio di `core/server_stats_image.py`). Tutti i cinque comandi
condividono la stessa priorità di sorgente immagine, pensata per non
richiedere sempre un allegato esplicito: allegato > utente menzionato
> avatar dell'autore del comando (helper `_resolve_image_bytes` nel
cog), con validazione di tipo MIME e dimensione massima (15 MB)
sull'allegato prima di elaborarlo. Il calcolo Pillow (CPU-bound) gira
sempre in `asyncio.to_thread(...)` nel cog, mai nel modulo `core/`
puro, per non bloccare il loop asyncio del bot. `/fun meme` richiede
almeno uno tra top-text e bottom-text, altrimenti risponde con un
messaggio d'errore effimero invece di generare un meme vuoto.
Terzo e ultimo lotto di questo settore (16.4 Comandi animal + 16.9
Ricerca immagini SFW, basati su API esterne) e §16.10 NSFW/Rule34
restano da fare in commit separati.

**§16 Fun & Immagini, terzo e ultimo lotto: chiusi 16.4 Comandi
animal e 16.9 Ricerca immagini SFW** (6/0/9 → 8/0/7). Due nuovi
sotto-comandi del gruppo `/fun` esistente — nessun nuovo slot
top-level, il totale resta a 97/100. `/fun animal <specie>`
(cane/gatto/volpe) usa tre API pubbliche GRATUITE senza chiave
(dog.ceo, thecatapi.com, randomfox.ca — `core/animal_fetcher.py`,
`core/animal_api_logic.py`), a differenza di `/fun search-image
<query>` (§16.9) che usa Pixabay e QUINDI richiede una chiave
gratuita (`PIXABAY_API_KEY` in `core/config.py`, stesso principio di
sblocco opzionale già usato per Twitch/YouTube) — con una differenza
importante rispetto a quelle due integrazioni: senza `PIXABAY_
API_KEY` il comando NON PUÒ funzionare affatto (non è un extra
opzionale come "sapere quando un canale va live"), quindi risponde
con un messaggio che spiega come attivare la chiave gratuita invece
di restare silenziosamente inutilizzabile. `safesearch=true` è
impostato SEMPRE nella richiesta a Pixabay — è Pixabay stesso, lato
server, a garantire risultati SFW, non questo codice a dover
rifiltrare (`core/image_search_fetcher.py`, `core/image_search_
logic.py`).

Entrambi i fetcher (`core/animal_fetcher.py`, `core/image_search_
fetcher.py`) seguono lo stesso schema di gestione errori già usato
da `core/twitch_watcher.py`/`core/youtube_watcher.py`: sessione
aiohttp riusata, timeout esplicito, log + `None` (mai un'eccezione)
se la richiesta fallisce (rete, timeout, status non-200) o la
risposta non ha la forma aspettata. Testati con un server aiohttp
VERO in locale (`aiohttp.test_utils.TestServer`) che imita la forma
delle risposte reali — non un mock della sessione HTTP — stesso
principio già seguito da `tests/test_twitch_watcher.py`/`tests/
test_youtube_watcher.py`.

**Tutto il settore §16 Fun & Immagini SFW è ORA COMPLETO** per tutto
ciò che non è stato esplicitamente scartato o rimandato a
un'applicazione separata: 16.1/16.2/16.3/16.4/16.5/16.7/16.8/16.9
fatti; 16.6 scartato deliberatamente (attributo protetto); 16.10
NSFW/Rule34 resta l'ultima voce, rimandata all'applicazione separata
iYokai NSFW (Task #24, non ancora iniziato).

SPEC.md: §16 6/0/9 → **8/0/7**. Ricalcolo meccanico di TUTTA la
tabella dei totali: **238/3/35**.

