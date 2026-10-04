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
dei documenti.

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
| §3 PREMIUM SYSTEM | 9 | 2 | 0 | 0 |
| §4 VERIFY + FINGERPRINT + ANTI-ALT | 7 | 3 | 9 | 0 |
| §5 MODERATION | 0 | 12 | 0 | 0 |
| §6 AUTOMOD | 5 | 10 | 0 | 0 |
| §7 SECURITY SUITE | 6 | 27 | 1 | 0 |
| §8 LOGGING | 10 | 7 | 1 | 0 |
| §9 MUSIC | 1 | 8 | 5 | 3 |
| §10 ALERTS & SOCIAL | 0 | 7 | 3 | 0 |
| §11 BACKUP SYSTEM | 0 | 11 | 6 | 0 |
| §12 TEMPORARY VOICE CHANNELS | 5 | 3 | 0 | 0 |
| §13 TICKET SYSTEM | 5 | 8 | 0 | 0 |
| §14 UTILITY & SERVER MANAGEMENT | 2 | 13 | 3 | 0 |
| §15 LEVELS / ECONOMY / GILDE / CLASSIFICHE | 14 | 20 | 0 | 0 |
| §16 FUN & IMMAGINI | 6 | 2 | 7 | 0 |
| §17 OWNER / GLOBAL ADMIN | 7 | 3 | 0 | 0 |
| §18 ROUTER DEI CANALI E LOG SU FORUM | 0 | 0 | 7 | 0 |
| §19 DATI, PRIVACY E GDPR | 0 | 0 | 9 | 0 |
| §20 NUOVA STRUTTURA DEI COMANDI | 0 | 0 | 7 | 0 |
| §21 LINGUE E RICERCA DEI COMANDI | 0 | 0 | 6 | 0 |
| §22 FUNZIONI NUOVE, PRIMO GRUPPO | 0 | 0 | 17 | 0 |
| §23 FUNZIONI NUOVE, SECONDO GRUPPO | 0 | 0 | 17 | 0 |
| §24 PANNELLO WEB: CONFIGURAZIONE DEI SERVER | 0 | 0 | 7 | 0 |
| §25 MOTORE AI | 0 | 0 | 9 | 0 |
| B iYOKAI APPLICATION (installabile dall'utente) | 0 | 0 | 10 | 0 |
| C WEB PANEL (iYokai Panel) | 0 | 0 | 5 | 0 |
| D iYOKAI DESKTOP | 0 | 0 | 11 | 2 |
| E APPLICAZIONI DEL PROGETTO | 0 | 3 | 5 | 0 |
| **Totale** | **97** | **145** | **146** | **6** |

Totale voci: **394**.

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
  → **Stato 04/10:** tratta "non hai i permessi" come errore imprevisto (BUG-13).
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
    → **Stato 04/10:** lavoro lento prima della risposta (LIM-9).
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
- `[ ]` 4.2 Verify Avanzato (richiede Web Panel) — non tentato,
  dipendenza non costruita
  → **Stato 04/10:** in piano: NF-21, fase F10.
  - `[ ]` Raccolta IP / ISP / localizzazione
  - `[ ]` Browser fingerprint / device fingerprint
  - `[ ]` OAuth2 scope `identify`
  - `[ ]` Salvataggio fingerprint (hash, mai IP in chiaro)
- `[ ]` 4.3 Sistema Anti-Alt — dipende da §4.2, non costruito
  → **Stato 04/10:** in piano: NF-21, fase F10.
  - `[ ]` Database fingerprint
  - `[ ]` Match → segnalazione allo staff (NON ban automatico
    cross-server; vedi § Decisioni)
  - `[ ]` Rilevamento pattern sospetti
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
- `[~]` 5.1 **Softban** (ban+unban immediato per cancellare i messaggi)
  → **Stato 04/10:** SEC-1, LIM-8.
- `[~]` 5.1 **Mute via ruolo** — ruolo "Muted" auto-creato con
  overwrite su ogni canale esistente al momento della creazione
  (canali creati dopo non ereditano l'overwrite, limite noto)
  → **Stato 04/10:** SEC-1; il ruolo non copre thread, forum e canali nuovi (LIM-30).
- `[~]` 5.2 Case system — numerazione atomica per server, ricerca per
  numero, storico per utente
  → **Stato 04/10:** caso creato prima dell'azione; liste oltre 4096 caratteri (LIM-8).
- `[~]` 5.3 Note utente
  → **Stato 04/10:** SEC-1.
- `[~]` 5.4 Report system
  → **Stato 04/10:** motivo oltre 1024 caratteri: segnalazione persa (LIM-4).
- `[~]` 5.5 Lock / Unlock canale
  → **Stato 04/10:** SEC-1; nessun log (REVIEW §12).
- `[~]` 5.6 Slowmode
  → **Stato 04/10:** SEC-1; nessun log (REVIEW §12).
- `[~]` 5.7 Clear avanzato con filtri
  → **Stato 04/10:** SEC-1; filtro allegati da riprovare con l'intent acceso (BUG-5).
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
  → **Stato 04/10:** `/lock`, `/unlock`, `/slowmode`, `/clear` non creano né casi né log (REVIEW §12).

## §6 AUTOMOD

- `[~]` 6.1 Anti-badwords (via AutoMod nativo Discord, con merge a tre vie)
  → **Stato 04/10:** una parola oltre 60 caratteri rompe la sincronizzazione; `edit()` cancella le eccezioni messe a mano (LIM-29).
- `[~]` 6.2 Anti-invite (via AutoMod nativo, regex)
  → **Stato 04/10:** LIM-29.
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
- `[~]` 6.15 Smart AutoMod Escalation Ladder (BACKLOG.md §11) — scala
  di severità crescente **nel tempo** in base a quante volte un
  utente ha già triggerato l'AutoMod nativo, con reset dopo un
  periodo configurabile di buona condotta. Concettualmente diversa
  da 6.13 (che è più azioni insieme su UN trigger, non su trigger
  ripetuti nel tempo) — voce nuova, non una ridefinizione di 6.13
  → **Stato 04/10:** una violazione conta più volte (LIM-32).

## §7 SECURITY SUITE — presente, con bug aperti su anti-raid, anti-nuke e spam-trap (fase F1)

- `[~]` 7.1 Anti-Raid — `cogs/security/anti_raid.py`, modulo CANDIDATO
  PREMIUM (come Spam Trap). Logica di valutazione pura in
  `core/security_logic.py` (`evaluate_join`), finestra mobile in
  memoria per il join rate (`core/security_rate_tracker.py`, mai
  persistita — stesso principio di `core/automod_rate_tracker.py`).
  Comandi: `/anti-raid enable|join-rate|account-age|username-check|
  avatar-check|lockdown-action|alert-channel|status`
  → **Stato 04/10:** BUG-12.
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
  tra evento e voce di audit log. Comandi: `/anti-nuke enable|limits|
  trusted-add|trusted-remove|punish-action|recovery|status`
  → **Stato 04/10:** può punire il bot stesso (BUG-11).
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
- `[~]` 8.13 Soundboard create / delete / update — **non via evento
  gateway** (quella parte del limite trovato nell'Anti-Nuke, §7.2,
  resta vera: nessun `on_soundboard_sound_...` esiste nella
  libreria), ma via POLLING PERIODICO dell'audit log
  (`discord.AuditLogAction.soundboard_sound_create/update/delete`
  esistono ed è lì che Discord registra l'evento — verificato
  leggendo l'enum reale della libreria installata, non assunto).
  `core/soundboard_log_service.py`, stesso pattern architetturale di
  `core/event_log_retention.py` (un `tasks.loop`, non un listener),
  ogni 5 minuti, con un "watermark" persistito per server per non
  ri-loggare le stesse voci né riversare lo storico alla prima
  attivazione
  → **Stato 04/10:** Correzione al testo: gli eventi soundboard **esistono** in discord.py 2.7.1; il giro periodico va sostituito (LIM-31). Il primo evento viene saltato (REVIEW §5).
- `[x]` 8.14 Thread events — create/delete/update (nome, archiviato,
  bloccato)
- `[x]` 8.15 Server update (impostazioni guild) — nome, icona,
  livello di verifica, canale AFK, canale di sistema, filtro
  contenuti espliciti
- `[ ]` 8.16 Message delete / bulk delete / edit — **rimandato
  deliberatamente**: richiede il Message Content Intent, da chiedere
  solo quando un modulo lo giustifica (vedi § Decisioni)
  → **Stato 04/10:** l'intent è acceso dal 04/10 (D9). In piano: NF-02, fase F6.
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
- `[~]` 9.4 Comandi: play, skip, stop, pause, resume, queue,
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
  NON da rimettere in lista in futuro): search distinta da play,
  forceskip, remove, move, seek, lyrics
  → **Stato 04/10:** `/stop` e `/skip` da un altro canale (REVIEW §4); nessun `defer` (LIM-25); titolo oltre 256 (LIM-21).
- `[~]` 9.5 Sorgenti: YouTube, Spotify (solo risoluzione titolo),
  SoundCloud, URL, file locali — YouTube funziona via la ricerca di
  default di Lavalink; Spotify richiede un plugin (LavaSrc) sul nodo
  Lavalink usato, non verificabile se presente su un nodo pubblico di
  terzi senza controllarlo direttamente — **fallback ORA predisposto**
  (`MusicCog._search_with_spotify_fallback`, `core.music_logic.
  is_spotify_query`): se una query Spotify non produce risultati sui
  nodi pubblici, si ritenta UNA volta pinnata specificamente sul nodo
  locale/self-hostato (`LOCAL_NODE_IDENTIFIER`, lo stesso già usato
  per i file locali qui sotto) — funziona non appena l'utente
  configura lì un nodo con LavaSrc installato (`LAVALINK_HOST/PORT/
  PASSWORD` in `.env`), nessun altro codice da scrivere quando lo
  farà. Fino ad allora il comportamento resta identico a oggi (il
  fallback semplicemente non trova nulla, come un nodo pubblico senza
  Spotify farebbe comunque). **File locali ORA fatti** per la radio
  condivisa (`/nonstop-main add-local`), instradati specificamente
  verso il nodo Lavalink locale — i nodi pubblici non hanno accesso
  al filesystem della macchina
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

- `[ ]` 9.13 Un nodo wavelink per ogni bot per ogni server Lavalink,
  con scelta esplicita del nodo (D10, LIM-40, LIM-42)
- `[ ]` 9.14 Controllo della versione di Lavalink all'avvio (4.2.0 o
  successiva) e nodi pubblici solo da `.env` (LIM-54)
- `[ ]` 9.15 Cartella `deploy/lavalink/` con `docker-compose.yml`,
  `application.yml` e guida (#47, #48)
- `[ ]` 9.16 Radio che parte da sola quando il bot principale entra in
  un canale vocale (#45)
- `[ ]` 9.17 Canale richieste con messaggio "player" e bottoni, playlist
  salvate degli utenti (§23, NF-19)

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
- `[~]` 10.4 YouTube live — via la YouTube Data API v3 (`search.list`,
  `eventType=live`), non via RSS (che non indica lo stato live). Come
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

- `[ ]` 11.1 Snapshot del server salvato come dati nel database, con
  più copie datate per server (D8, LIM-39)
- `[ ]` 11.2 Collegamento di un server creato a mano: codice generato
  nel server principale e usato nel server nuovo; link "modello" con
  `Guild.create_template`; nessuna cessione di proprietà (D8)
- `[~]` 11.3 Clonazione ruoli + permessi — `clone_roles()` in
  `core/backup_clone_logic.py`: salta @everyone ma ne applica i
  permessi, salta i ruoli "managed". Le posizioni non vengono
  impostate (REVIEW §12, da verificare live). Con un modello i ruoli
  esistono già: serve una mappa per **nome**
- `[~]` 11.4 Clonazione categorie + canali — `clone_categories_and_
  channels()`: categorie prima dei canali, permessi rimappati. Copia
  la qualità audio tale e quale (LIM-28); copierebbe i canali
  offuscati `___hidden___` (LIM-38)
- `[~]` 11.5 Clonazione emoji — `clone_emoji()`, con controllo dei
  limiti del server di destinazione (`e502c1f`). Senza essere
  proprietario serve il permesso `CREATE_GUILD_EXPRESSIONS`.
  Raggiungibile solo dopo 11.2
- `[~]` 11.6 Clonazione sticker — `clone_stickers()`, come 11.5
- `[~]` 11.7 Clonazione soundboard — `clone_soundboard()`, come 11.5
- `[~]` 11.8 Clonazione webhook — `clone_webhooks()`: nome e canale
  rimappato (l'URL non è copiabile). 15 webhook copiati + 1 del mirror
  superano il tetto di 15 per canale (LIM-28)
- `[~]` 11.9 Mirror messaggi in tempo reale via webhook con identità
  utente (scarto sui picchi, 5 messaggi ogni 5 secondi per canale) —
  `core/backup_mirror_logic.py`, `core/backup_mirror_dispatch.py`,
  `cogs/utility/backup_mirror.py`. SEC-22 corretto (`690a5b6`). Da
  riprovare con l'intent acceso (BUG-5); nome del webhook (LIM-27);
  oggi non ha mai un webhook di destinazione (dipende da 11.2)
- `[~]` 11.10 User backup: snapshot periodico (settimanale) dei
  verificati non bannati/kickati — `core/backup_snapshot_logic.py`,
  `core/backup_snapshot_worker.py`. Il worker ora parte (BUG-19,
  `fba882e`), ma non trova coppie finché non c'è 11.2
- `[~]` 11.11 Restore massivo utenti via OAuth2 `guilds.join` — token
  cifrati AES-256-GCM (`core/oauth_crypto.py`), tre modalità per
  server (`/configura-restore`), conservazione diversa per uscita,
  kick e ban. Corretti il 04/10: link valido 7 giorni e legato al
  destinatario (BUG-21, SEC-19, `8590e89`); ruolo verificato
  controllato (`67e5771`). Aperti: token mai rinnovati (LIM-37); ciclo
  senza pause e senza gestione dei 429 (LIM-7); la modalità "OAuth alla
  verifica" non fa niente di diverso (REVIEW §12); invito in DM solo a
  chi ha dato il consenso; chiave non ruotabile (LIM-52)
- `[~]` 11.12 Comandi `/define-main`, `/define-backup`,
  `/promuovi-backup`, `/restore-users`, `/configura-restore` —
  esistono; `/define-backup` oggi fallisce perché prova a creare un
  server. In F3 diventano il flusso di 11.1 e 11.2, e in F7 passano
  sotto `/admin backup` e `/admin restore`
- `[~]` 11.13 Promozione del backup a nuovo main — `/promuovi-backup`.
  Dopo la promozione `/restore-users` rifiuta sempre (BUG-34, da
  confermare con un test): la coppia storica va conservata
- `[ ]` 11.14 Il Creator smette di creare, cedere e cancellare server:
  entra nel server creato dall'admin e lo porta allo stato corrente,
  messaggi in ordine cronologico compresi (D8)
- `[ ]` 11.17 Aggiornamento continuo del server di backup: controllo
  periodico delle differenze di ruoli, canali e permessi (D8)
- `[ ]` 11.15 Salvataggio degli ultimi N messaggi per canale nello
  snapshot (modello Xenon), oltre al mirror in tempo reale
- `[ ]` 11.16 Modelli di server e sincronia di ban e ruoli tra server
  dello stesso proprietario (§23, NF-39)

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
- `[~]` 12.6 Gestione canale: rename, limite utenti, lock, unlock, kick, transfer
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
- `[~]` 13.3 Creazione canale privato
  → **Stato 04/10:** doppio clic apre due ticket (REVIEW §4); la creazione spende una rinomina (LIM-3).
- `[~]` 13.4 Claim
  → **Stato 04/10:** nessun controllo staff (REVIEW §4).
- `[~]` 13.5 Add / Remove utente
  → **Stato 04/10:** nessun controllo staff (REVIEW §4).
- `[~]` 13.6 Rename
  → **Stato 04/10:** LIM-3.
- `[~]` 13.7 Priorità
  → **Stato 04/10:** nessun controllo staff (REVIEW §4).
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
- `[x]` 13.11 Invio transcript nel canale log configurato (riusa
  `SETTING_LOG_CHANNEL` di §8) + DM all'utente che ha aperto il
  ticket (silenzioso se i DM sono chiusi)
  → **Stato 04/10:** (da verificare live)
- `[x]` 13.12 Statistiche ticket (`/ticket-stats [operatore]`) — prese
  in carico, chiuse, tempo medio di prima risposta (per operatore o
  per l'intero server)
- `[~]` 13.13 Configurazione ruoli di supporto multipli
  (`/ticket-support-role add|remove|list`) — combinati con il ruolo
  legacy singolo per retrocompatibilità, nessuna migrazione richiesta
  → **Stato 04/10:** `remove` non toglie il ruolo storico (REVIEW §4).

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
- `[ ]` 14.9 Snipe — **rimandato deliberatamente, stesso motivo di
  §8.16**: mostrare il testo del messaggio cancellato richiede il
  contenuto, azzerato sia in `on_message` (dove andrebbe cache-ato
  in anticipo) sia in `on_message_delete` senza il Message Content
  Intent — verificato punto per punto (non liquidato in blocco come
  errore fatto su §8.13/§8.8, vedi PROGRESS.md Fase 70b), a
  differenza di 14.11/14.12 sotto, che infatti SONO stati costruiti
  → **Stato 04/10:** l'intent è acceso dal 04/10. In piano: NF-03, fase F6.
- `[ ]` 14.10 Editsnipe — stesso motivo di 14.9 (before/after content)
  → **Stato 04/10:** in piano: NF-03, fase F6.
- `[x]` 14.11 Reactionsnipe — `/reactionsnipe`, NON richiede il
  Message Content Intent: `on_raw_reaction_remove` restituisce
  emoji/autore/messaggio senza bisogno del contenuto del messaggio.
  Stato in memoria (non persistito, come tutti i bot "snipe")
- `[~]` 14.12 Ghost ping detection — traccia in memoria i messaggi
  con menzioni (`Message.mentions`, popolato da un campo gateway a
  parte dal contenuto — non azzerato dall'intent, verificato
  leggendo `Message._handle_mentions` nella libreria installata) e
  segnala nel canale log se vengono cancellati, senza mai leggere il
  testo del messaggio
  → **Stato 04/10:** segnala anche i messaggi cancellati dai moderatori (REVIEW §5).
- `[~]` 14.13 Sticky messages — `/sticky set|remove`, debounce minimo
  (5s) per non cancellare+reinviare ad ogni singolo messaggio in un
  canale attivo
  → **Stato 04/10:** messaggi persi o doppi (REVIEW §4); errore non gestito (LIM-11).
- `[~]` 14.14 Suggestion system (per i server clienti, distinto da
  14.8) — `/suggestion-setup`, `/suggest`, bottoni persistenti
  approva/rifiuta + reazioni native 👍👎 per il voto
  → **Stato 04/10:** nessun `defer` (LIM-25); due staff decidono insieme (REVIEW §5).
- `[~]` 14.15 Poll — Poll nativo di Discord (`discord.Poll`), fino a
  5 opzioni, nessuna logica propria: voto/conteggio/chiusura gestiti
  interamente da Discord
  → **Stato 04/10:** risposta oltre 55 caratteri: errore (LIM-2).
- `[~]` 14.16 Reminder — `/reminder set|list|cancel`, riusa lo
  scheduler generico esistente (nessuna tabella nuova). Consegna via
  DM, fallback nel canale se i DM sono chiusi
  → **Stato 04/10:** promemoria lunghi persi in silenzio (LIM-13).
- `[~]` 14.17 Scheduled messages — `/schedule-message set|list|cancel`,
  riusa lo stesso scheduler dei Reminder (nessuna tabella nuova).
  Diversamente dal Reminder (personale, via DM), pubblica in un
  CANALE del server
  → **Stato 04/10:** messaggi lunghi persi in silenzio (LIM-12); ping di ruolo muti (D12).
- `[x]` 14.18 Server stats (+ grafici) — `/serverstats`: numeri del
  server + grafico a barre della crescita giornaliera (disegnato con
  Pillow, non matplotlib — nessuna nuova dipendenza pesante)
  → **Stato 04/10:** Correzione al testo: il grafico dipende dal modulo logging (REVIEW §12).

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
  - `[x]` Boost individuale XP / Coin acquistabile — `/clan boost
    individuale`, QUALUNQUE membro (non solo Capo/Admin: paga dal
    proprio saldo per il proprio guadagno), ×2 per 24h, **10.000**
    coin personali, si applica SOLO al proprio tick vocale di gilda
    (mai al leveling generale del server — numeri e scope confermati
    dall'utente prima di scrivere la logica)
  - `[x]` Boost di gilda XP / Coin acquistabile — `/clan boost gilda`,
    Capo/Admin Clan, ×2 per 24h, **100.000** coin dalla tesoreria, si
    applica al tick di TUTTI i membri; i due boost si moltiplicano
    tra loro se entrambi attivi (×4 totale). Un acquisto mentre un
    boost è già attivo ESTENDE la scadenza da lì (mai da subito,
    stesso pattern già usato per l'estensione mensile del premium)
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
- `[ ]` 16.10 NSFW / Rule 34 → **applicazione separata iYokai NSFW**
  → **Stato 04/10:** in piano: NF-23, fase F11.
  - `[ ]` Solo canali con flag NSFW, verificato a runtime a ogni post
  - `[ ]` Comando ricerca: `r34 <termine>` → immagine casuale
  - `[ ]` Auto-post configurabile: intervallo (numero + minuti/ore),
    sottocategorie scelte o random
  - `[ ]` **Filtro a due strati obbligatori**: allowlist decisa dal
    server + blocklist hardcoded non modificabile, su ricerca manuale
    E auto-post
  - `[ ]` Log con hash di ogni immagine pubblicata

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
- `[~]` 17.5 Blacklist globale server — uscita automatica su
  `on_guild_join` se già in blacklist, uscita immediata se aggiunto
  mentre il bot è già dentro
  → **Stato 04/10:** esce solo il bot principale; gli altri bot restano (REVIEW §12).
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

## §18 ROUTER DEI CANALI E LOG SU FORUM — da fare (fase F6)

- `[ ]` 18.1 Un canale per **tipo** di uscita (log membri, messaggi,
  moderazione, voce, server, automod, allarmi, benvenuto…), al posto
  del canale unico (NF-01)
- `[ ]` 18.2 Canale di testo oppure forum; nel forum un post per tipo
  di log (D3)
- `[ ]` 18.3 Creazione automatica di categoria e canali, o del forum,
  con i permessi giusti (visibili solo allo staff)
- `[ ]` 18.4 Canale sparito o senza permessi: avviso agli admin una
  volta sola, mai un errore a ogni evento (LC-6)
- `[ ]` 18.5 Migrazione delle impostazioni esistenti nella nuova
  tabella `output_channels`
- `[ ]` 18.6 Ignora canali, utenti e prefissi nei log
- `[ ]` 18.7 Log delle azioni oggi mai registrate: `/lock`, `/unlock`,
  `/slowmode`, `/clear`, `/untimeout`, `/unmute-role`, scadenza dei
  tempban, azioni dell'escalation

## §19 DATI, PRIVACY E GDPR — da fare (fase F5)

- `[ ]` 19.1 Registro dei dati personali: ogni tabella con `user_id` o
  `guild_id` è dichiarata, con il modo di cancellarla (NF-04)
- `[ ]` 19.2 Uscita da un server: dati cancellati dopo 90 giorni,
  tranne ban e kick di sicurezza (D6, GDPR-1)
- `[ ]` 19.3 Cancellazione dei dati di un utente su richiesta (GDPR-2)
- `[ ]` 19.4 Esportazione dei dati di un utente in un file (art. 15)
- `[ ]` 19.5 Pulizia giornaliera delle tabelle che crescono (GDPR-3,
  PERF-3)
- `[ ]` 19.6 Comandi: richiesta dell'utente, approvazione dell'owner
- `[ ]` 19.7 Privacy policy e termini pubblicati (serve anche per la
  verifica dell'app a 100 server)
- `[ ]` 19.8 Elenco delle funzioni che usano ogni intent privilegiato
  (serve per la domanda a Discord da 10.000 utenti, D11)
- `[ ]` 19.9 Token dei webhook salvati come hash; chiave dei token
  OAuth ruotabile (SEC-16, LIM-52)

## §20 NUOVA STRUTTURA DEI COMANDI — da fare (fase F7)

- `[ ]` 20.1 13 gruppi: `/owner /admin /mod /modban /security /log
  /ticket /voice /music /level /clan /fun /utility` (NF-05, D2)
- `[ ]` 20.2 Ogni gruppo dello staff ha i suoi permessi predefiniti:
  chi non può usare un comando non lo vede (SEC-1)
- `[ ]` 20.3 Ogni gruppo funziona solo dentro un server (LC-2)
- `[ ]` 20.4 `/owner` registrato solo nel server dell'owner
- `[ ]` 20.5 Nessuna compatibilità con i vecchi nomi (D4)
- `[ ]` 20.6 Al massimo 25 figli per gruppo e un livello di
  sotto-gruppi, controllati da un test (LIM-57)
- `[ ]` 20.7 `COMMAND_LIST.md` rigenerato dall'albero vero

## §21 LINGUE E RICERCA DEI COMANDI — da fare (fase F8)

- `[ ]` 21.1 Tutti i testi in un file per lingua, italiano e inglese
  (NF-06)
- `[ ]` 21.2 La lingua del server decide la lingua delle risposte
- `[ ]` 21.3 Nomi e descrizioni dei comandi tradotti da Discord secondo
  la lingua dell'utente (D1)
- `[ ]` 21.4 `COMMAND_LIST_ITA.md` e `COMMAND_LIST_ENG.md` generati
- `[ ]` 21.5 `/utility cerca-comando`: sinonimi nelle due lingue, solo
  i comandi che l'utente può usare e con il modulo attivo
- `[ ]` 21.6 Risposte oggi in inglese (role menu, verify, spam-trap,
  benvenuti) portate nel file dei testi

## §22 FUNZIONI NUOVE, PRIMO GRUPPO — da fare (fase F9)

- `[ ]` 22.1 Ruolo automatico all'ingresso (NF-07)
- `[ ]` 22.2 Ruoli ridati a chi rientra entro 30 giorni (NF-07)
- `[ ]` 22.3 Ruoli dati dopo un ritardo (NF-07)
- `[ ]` 22.4 Starboard (NF-08)
- `[ ]` 22.5 Comandi personalizzati creati dal server: testo o embed,
  ruolo, pausa; prefisso facoltativo solo per questi (NF-09)
- `[ ]` 22.6 Costruttore di embed con anteprima e modifica (NF-17)
- `[ ]` 22.7 Immagine di benvenuto con avatar, nome e sfondo (NF-11)
- `[ ]` 22.8 Rank card come immagine (NF-12)
- `[ ]` 22.9 Ticket: modulo con domande prima dell'apertura (NF-13)
- `[ ]` 22.10 Ticket: più pannelli in un messaggio (NF-13)
- `[ ]` 22.11 Ticket: chiusura automatica per inattività o utente
  uscito (NF-13)
- `[ ]` 22.12 Ticket: voto a fine ticket e limite per utente (NF-13)
- `[ ]` 22.13 Modalità dei reaction roles: unique, verify, drop,
  reversed, binding, temp, lock; ruoli ammessi ed esclusi (NF-14)
- `[ ]` 22.14 Livelli: canali e ruoli senza XP, moltiplicatori, canale
  del level-up, premi "accumula" o "togli i precedenti", valori
  configurabili (NF-15)
- `[ ]` 22.15 Captcha a immagine nella verifica (NF-18)
- `[ ]` 22.16 Wizard di primo avvio per categoria, con creazione dei
  canali
- `[ ]` 22.17 Soglie sui warn dati a mano

## §23 FUNZIONI NUOVE, SECONDO GRUPPO — da fare (fasi F9, F13, F14)

- `[ ]` 23.1 Canale richieste musicali con player e bottoni; playlist
  salvate (NF-19, fase F9)
- `[ ]` 23.2 Canali contatore (NF-16)
- `[ ]` 23.3 Statistiche di attività per canale e per membro, ruoli per
  attività (NF-25)
- `[ ]` 23.4 Compleanni (NF-26)
- `[ ]` 23.5 Inviti: comando personale e classifica (NF-27)
- `[ ]` 23.6 Giveaway avanzati: modelli, più ingressi, requisito sui
  messaggi, programmati (NF-28)
- `[ ]` 23.7 Blocco totale del server e "panic mode" (NF-29)
- `[ ]` 23.8 Anti-nuke con due soglie (al minuto e all'ora) e
  quarantena come punizione di default
- `[ ]` 23.9 Appello anche per i ban dati a mano (NF-30)
- `[ ]` 23.10 Blocco dei link di phishing (NF-31)
- `[ ]` 23.11 Alert Kick e ruolo "in diretta" (NF-32)
- `[ ]` 23.12 Ticket via messaggio privato (NF-33)
- `[ ]` 23.13 Moduli e candidature (NF-34)
- `[ ]` 23.14 Effetti sonori in vocale (NF-35)
- `[ ]` 23.15 Bot con marchio proprio per i server premium (NF-38)
- `[ ]` 23.16 Profili, collezioni e giochi con le monete, senza soldi
  veri; gioco del conteggio (NF-40)
- `[ ]` 23.17 Idee rimandate di `BACKLOG.md`: missioni, traguardi,
  serie, battle pass, profilo globale positivo, punteggio di rischio,
  carico dello staff (NF-41, fase F14)

## §24 PANNELLO WEB: CONFIGURAZIONE DEI SERVER — da fare (fase F10)

Completa la parte C più sotto (pagine di verifica e dell'owner).

- `[ ]` 24.1 Accesso con Discord e scelta del server (NF-20)
- `[ ]` 24.2 Una pagina per modulo, con interruttore e impostazioni
- `[ ]` 24.3 Il pannello scrive le **stesse** impostazioni dei comandi,
  con gli stessi controlli (`core/config_schema.py`)
- `[ ]` 24.4 Il bot vede un cambio fatto dal pannello senza riavvio
- `[ ]` 24.5 Editor visuali: embed, immagine di benvenuto, rank card,
  moduli dei ticket
- `[ ]` 24.6 Pagine legali: privacy policy e termini
- `[ ]` 24.7 Pagamento del premium: abbonamento dentro Discord e
  pagamento esterno registrato dall'owner (NF-22)

## §25 MOTORE AI — da fare (fase F12, issue #50)

Prerequisiti: privacy policy pubblicata con l'elenco dei fornitori;
consenso dell'admin per server; tetto di spesa (D13). Vietato usare i
messaggi per addestrare modelli.

- `[ ]` 25.1 Router con più fornitori in cascata e risposta locale di
  riserva (NF-24)
- `[ ]` 25.2 Cache delle risposte a domande uguali o molto simili
- `[ ]` 25.3 Filtri di sicurezza in ingresso e in uscita; dati
  personali tolti prima dell'invio
- `[ ]` 25.4 Conteggio dell'uso e tetto di spesa per server
- `[ ]` 25.5 Helpdesk: risposte sui comandi e sul server
- `[ ]` 25.6 Riassunti di canali e ticket
- `[ ]` 25.7 Lore: tono e ambientazione scelti dal server (tabella e
  comando possono nascere prima del motore, vedi `BACKLOG.md` §8)
- `[ ]` 25.8 Generazione di immagini
- `[ ]` 25.9 Interruttore per server e per canale

---

# B. iYOKAI APPLICATION (user-installable) — da fare (NF-36, fase F13)

Comandi che l'utente installa **su di sé** e usa ovunque: in qualsiasi
server (anche dove il bot non c'è), nei DM e nei gruppi. L'elenco
completo, con limiti e motivi, è in
`revisione/01-analisi/APP_UTENTE_E_DESKTOP.md`.

- `[ ]` B.1 Applicazione separata con installazione sull'utente
  (`USER_INSTALL`) e i tre contesti (server, DM con il bot, DM e gruppi)
- `[ ]` B.2 Menu sul messaggio: Traduci, Salva nei segnalibri,
  Ricordamelo, Citazione come immagine, Meme da questa immagine,
  Controlla i link, Segnala alla rete iYokai, Spiega/riassumi (AI)
- `[ ]` B.3 Menu sull'utente: Profilo iYokai, Stato nella rete di
  sicurezza (solo per chi lo chiede, risposta privata)
- `[ ]` B.4 Utility personali: promemoria, note, liste, fusi orari,
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
- `[ ]` iYokai Mod (log e moderazione) — D15, fase F3
- `[~]` iYokai Creator (backup) — resta; non crea più server, porta e
  tiene aggiornato il server di backup (D8, §11)
- `[~]` iYokai Music #1-5 — vedi §9
  → **Stato 04/10:** il codice c'è; l'audio dei worker va corretto (LIM-40, D10).
- `[ ]` iYokai NSFW — vedi §16.10
- `[ ]` iYokai App (installabile dall'utente) — vedi B
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
risposta di `search.list` (logica pura, testata senza rete);
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

