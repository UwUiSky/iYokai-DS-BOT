# PROGRESS — Stato del progetto iYokai

> Questo file esiste per un motivo preciso: se una sessione di lavoro
> finisce (token esauriti, chiusura chat, cambio giornata), la sessione
> successiva legge QUESTO file per sapere esattamente dove riprendere,
> senza dover rileggere tutta la conversazione da capo.
>
> **Regola:** ogni commit che chiude un pezzo di lavoro aggiorna anche
> questo file, nella stessa sessione. Non lasciarlo mai indietro
> rispetto al codice.

Ultimo aggiornamento: **17 settembre 2026**

---

## ✅ Fatto

### Fase 0 — Fondamenta
- [x] Struttura cartelle del progetto (`core/`, `cogs/` con sottocartelle per dominio)
- [x] `.gitignore` — esclude `.env`, cache Python, venv, log, dati locali
- [x] `.env.example` — template completo di tutte le variabili previste
  (token delle 8 applicazioni, DB, Lavalink, OAuth2/web panel)
- [x] `requirements.txt` + `requirements-dev.txt` (pytest/pytest-asyncio
  separati, non servono in produzione)
- [x] `core/config.py` — loader di configurazione che **valida
  all'avvio**: se manca una variabile obbligatoria, il processo si
  ferma con un errore chiaro invece di crashare più avanti
- [x] `core/database.py` — pool `asyncpg`, `run_migrations()`,
  tabelle base (`guild_config` con colonne `modules` e `settings`
  JSONB, `premium_whitelist`, `premium_module_flags`),
  `is_module_active_for_guild`/`set_module_active_for_guild`,
  `get_guild_setting`/`set_guild_setting`
- [x] `core/premium.py` — sistema premium completo: `PremiumRegistry`,
  `PremiumModule`, decorator `@requires_module(...)` (vedi nota
  tecnica importante più sotto — RISCRITTO durante lo sviluppo di
  Moderation per un bug reale). **Tutto parte spento**
  (`is_premium_active = False` ovunque), come richiesto
- [x] `core/cog_manager.py` — scoperta automatica dei cog tramite
  `pkgutil.walk_packages`, nessuna registrazione manuale necessaria
- [x] `core/permissions.py` — gerarchia di moderazione come logica
  PURA (solo int/bool, niente `discord.Member`): testabile senza
  bisogno di una connessione Discord. **9 test**, tutti verdi
- [x] `core/scheduler.py` — scheduler generico backed da database per
  azioni differite (tempban, futuro: unmute, boost temporanei...).
  Sopravvive a un riavvio del bot, a differenza di un timer in
  memoria. **5 test contro PostgreSQL reale**
- [x] `core/repositories/moderation_repo.py` — case system con
  numerazione atomica per-server (contatore con UPSERT in
  transazione), note dello staff. **15 test**, incluso un test di
  concorrenza reale (20 creazioni in parallelo, nessuna collisione)
- [x] `main.py` — entry point, `AutoShardedBot`, `setup_hook`,
  `on_guild_join`, scheduler collegato al ciclo di vita, error
  handler globale dell'albero comandi registrato,
  `message_content` intent disattivato di default
- [x] `cogs/utility/ping.py` — cog modello/riferimento, commentato per
  intero: mostra il pattern di controllo "modulo attivo per questo
  server?" che sostituisce il (non fattibile) carico/scarico di cog
  per singolo server
- [x] `cogs/utility/owner_premium.py` — comandi
  `/owner premium-list`, `/owner premium-toggle`,
  `/owner whitelist-add`, `/owner whitelist-remove`
- [x] README aggiornato con struttura, setup, architettura a
  applicazioni multiple, sezione test

### Fase 2 — Moderation (`cogs/moderation/`) — COMPLETA
- [x] `_shared.py` — helper condivisi (file privato, il cog manager
  lo salta): `ensure_module_enabled`, `check_can_moderate`, `try_dm`,
  `parse_duration`/`format_duration`. **21 test** sul parser di durate
- [x] `actions.py` — `/warn`, `/kick`, `/ban`, `/tempban` (con
  auto-unban via scheduler), `/unban`, `/timeout`, `/untimeout`.
  Modulo SEMPRE gratuito, come da schema. Smoke test: il cog si
  carica davvero in un `Bot`, si registra nel sistema premium,
  l'handler dello scheduler si aggancia
- [x] `case_system.py` — `/modcase history|view`, `/modnote add|list`.
  Modulo candidato premium. Smoke test verifica ESPLICITAMENTE che
  i parametri (`member`, `case_number`) restino leggibili da
  discord.py attraverso `@requires_module`
- [x] `channel_control.py` — `/lock`, `/unlock`, `/slowmode`. Sempre
  gratuito
- [x] `report.py` — `/report`, `/report-setup` (usa
  `guild_config.settings` per il canale configurato). Sempre gratuito
- [x] `clear.py` — `/clear` con filtri (utente, solo bot, solo
  allegati). Candidato premium. **È il file che ha fatto emergere il
  bug di `@requires_module` — vedi sotto**

**Suite di test completa: 63/63 passano**, eseguiti per davvero
(PostgreSQL locale nel container di sviluppo, non mock) — vedi
`README.md` § Test per come rilanciarli.

### Fase 3 — Setup interattivo — COMPLETA
- [x] `cogs/utility/setup.py` — `/setup`: pannello con menu a
  tendina multi-selezione (`discord.ui.Select` + `discord.ui.View`),
  opzioni costruite da `registry.all_modules()` con `default=True`
  per i moduli già attivi su quel server. Bottoni "Salva
  configurazione"/"Annulla", timeout 180s con disattivazione
  automatica dei componenti. **Sblocca l'uso reale di tutto ciò che
  è già stato scritto**: prima di questo cog, Moderation esisteva
  ma nessun server poteva accenderla
- [x] Limite dei 25 elementi per Select gestito con fallimento
  controllato (messaggio chiaro + log), non un crash — TODO
  paginazione quando i moduli registrati supereranno 25
- [x] Test di persistenza REALE (non solo smoke): simula il click su
  "Salva" con un'Interaction finta e verifica contro PostgreSQL che
  un modulo prima attivo e non riselezionato risulti disattivato
  dopo il salvataggio — il caso che, se sbagliato, avrebbe lasciato
  moduli accesi per dimenticanza

**Suite di test completa: 67/67 passano.**

### Fase 4 — AutoMod ibrido — COMPLETA
- [x] `core/automod_sync.py` — logica PURA di sincronizzazione,
  merge a TRE VIE (vedi bug documentato sotto): `compute_sync_plan()`
  decide create/update/delete/skip senza mai toccare Discord
  direttamente. **15 test**
- [x] `core/repositories/automod_repo.py` — configurazione per-server
  (parole vietate, blocco inviti) + `automod_last_synced` (cosa
  iYokai ha scritto l'ultima volta, per rule name). **14 test contro
  PostgreSQL reale**
- [x] `cogs/automod/automod.py` — `/automod badword-add|remove|list`,
  `/automod invites`, `/automod sync`. Ogni comando di modifica
  richiama subito la sincronizzazione (nessun comando "sync"
  separato da ricordarsi — esperienza plug-and-play). Regole gestite
  sempre con prefisso `iYokai — ` nel nome, mai tocca regole con
  nomi diversi (create a mano dall'admin). Modulo sempre gratuito
- [x] Verificati con `inspect.signature` i nomi reali dell'API
  AutoMod di discord.py 2.7 (`AutoModRuleTriggerType`,
  `AutoModTrigger`, `guild.fetch_automod_rules()`, ecc.) prima di
  scrivere il codice, non assunti da documentazione ricordata a memoria

**Suite di test completa: 97/97 passano.**

### Fase 5 — Logging semplificato — COMPLETA
- [x] `cogs/logging/basic_logs.py` — `/logs-setup`, `/logs-status`,
  listener su join/leave/ban/unban/creazione-eliminazione ruoli/
  cambio ruoli sui membri. Canale configurabile per server via
  `guild_config.settings` (stesso pattern di `report.py`). Modulo
  sempre gratuito
- [x] **Punto tecnico verificato empiricamente prima di scrivere il
  codice**: discord.py NON registra un listener di un Cog per la
  sola convenzione del nome `on_xxx` — serve il decorator esplicito
  `@commands.Cog.listener()` su ognuno. Verificato con un test
  minimale isolato prima di scrivere l'intero file, non assunto
- [x] `diff_roles()` — logica pura per il confronto prima/dopo dei
  ruoli di un membro. **6 test**
- [x] Smoke test che verifica ESPLICITAMENTE la presenza di ogni
  listener in `bot.extra_events` — è il test che avrebbe intercettato
  un `@commands.Cog.listener()` dimenticato per errore
- [x] `_get_log_channel()` — tre condizioni devono essere tutte vere
  (modulo attivo, canale configurato, canale ancora esistente ed è
  un TextChannel) perché un log parta. **4 test contro PostgreSQL
  reale**, incluso il caso "canale cancellato dopo la configurazione"
  e "canale del tipo sbagliato"

**Suite di test completa: 108/108 passano.**

### Fase 6 — Ticket system — COMPLETA
- [x] `core/repositories/ticket_repo.py` — numerazione atomica
  per-server (stesso pattern del case system di Moderation), stato
  aperto/chiuso, claim, priorità. **17 test contro PostgreSQL
  reale**, incluso un test di concorrenza (15 creazioni in
  parallelo, nessuna collisione)
- [x] `cogs/tickets/tickets.py` — `/ticket-setup`, `/ticket-panel`,
  gruppo `/ticket` (claim, add, remove, rename, priority, close).
  Modulo sempre gratuito
- [x] `TicketPanelView` — **view persistente** (`timeout=None` +
  `custom_id` esplicito), registrata ad ogni avvio con
  `bot.add_view()`: senza questo, i bottoni dei pannelli già
  pubblicati smetterebbero di rispondere dopo ogni riavvio del bot.
  Verificato prima di scrivere il codice che `bot.add_view()`
  solleva `ValueError` su una view non persistente — non assunto
  dalla documentazione
- [x] Guardrail: un utente non può avere più di un ticket aperto
  contemporaneamente sullo stesso server
- [x] Permessi: l'utente che apre il ticket e un ruolo di supporto
  opzionale vedono il canale; iYokai non gestisce i permessi di
  categoria (quelli restano una scelta manuale dell'admin in Discord)
- [x] Smoke test che verifica esplicitamente `view.is_persistent()
  is True`, non solo che il cog si carichi senza eccezioni

**Suite di test completa: 127/127 passano.**

### Fase 7 — Vocali temporanei — COMPLETA
- [x] `core/voice_temp_logic.py` — logica pura delle decisioni
  (ingresso nel generatore, canale vuoto da eliminare, chi può
  gestire un canale). **11 test**
- [x] `core/repositories/voice_temp_repo.py` — configurazione per
  server (canale generatore, categoria), canali tracciati con
  proprietario, trasferimento proprietà. **10 test contro
  PostgreSQL reale**
- [x] `cogs/voice_temp/voice_temp.py` — `/voicetemp-setup`,
  `/voicetemp-panel`, gruppo `/voice` (rename, limit, lock, unlock,
  kick, transfer). Modalità automatica (listener
  `on_voice_state_update` sul canale generatore) e modalità manuale
  (bottone persistente), **entrambe sempre visibili**, come da
  decisione già presa
- [x] `CreateVoiceView` — persistente, stesso pattern di
  `TicketPanelView`, verificato con `view.is_persistent()`
- [x] Eliminazione automatica quando il canale resta vuoto: il
  cleanup gira anche se il modulo viene disattivato nel frattempo,
  per non lasciare canali orfani
- [x] **Bug reale trovato e corretto rileggendo il proprio codice
  prima di testare**: il controllo iniziale dei comandi `/voice`
  verificava se `interaction.channel` (da dove il comando viene
  digitato, tipicamente testuale) fosse un `VoiceChannel` — controllo
  senza senso, dato che ciò che conta è il canale a cui l'UTENTE è
  connesso (`interaction.user.voice.channel`), non da dove lancia lo
  slash command. Corretto prima di scrivere i test, non dopo un
  fallimento

**Suite di test completa: 150/150 passano.**

### Fase 8 — Livelli / Economy / Classifiche — COMPLETA (Gilde ancora da fare)
- [x] `core/leveling_logic.py` — logica pura: XP testuale (cooldown
  anti-spam), XP vocale (idoneità anti-farm + conteggio con
  azzeramento a 2 ore e cap giornaliero, regole già decise), formula
  di livello, cooldown daily/work. **39 test**
- [x] **Design del reset mensile: nessun reset.** Ogni guadagno è
  registrato per periodo (`period_key()`, es. "2026-09") invece che
  in un contatore azzerato da un job schedulato — un nuovo mese è
  semplicemente un nuovo periodo senza righe, niente cron che può
  fallire silenziosamente e bloccare la classifica
- [x] `core/repositories/leveling_repo.py` — `leveling_totals`
  (stato vivo, XP/coin cumulativi, livello, cooldown) +
  `leveling_activity` (una riga per periodo, base della classifica
  mensile). Transazioni con `FOR UPDATE` per XP testuale/vocale,
  trasferimento coin atomico con controllo saldo (mai negativo).
  **19 test contro PostgreSQL reale**
- [x] **Bug reale trovato dal database vero, non da un mock**:
  `VALUES ($1, $2, -$3)` in `transfer_coins()` falliva con
  `AmbiguousFunctionError` — Postgres non riesce a dedurre il tipo
  della negazione di un parametro non tipizzato in quel contesto.
  Risolto passando il valore già negativo da Python
- [x] `cogs/leveling/leveling.py` — XP testuale via `on_message`
  (verificato: NON richiede il Message Content Intent, quel
  privilegio riguarda solo se il contenuto è popolato, non se
  l'evento scatta), XP vocale via task periodico ogni 60s (non un
  listener sull'evento — l'XP va accumulato minuto per minuto per
  tutta la permanenza, non solo a ingresso/uscita), `/rank`,
  `/balance`, `/daily`, `/work`, `/pay`, `/leaderboard`
  (xp/coin × mensile/all-time)
- [x] Un errore nel calcolo per un singolo server non interrompe il
  giro per gli altri (try/except per-guild dentro il loop periodico)

**Ancora da fare in questa fase**: il Sistema Gilde/Clan, che si
appoggia sopra questo sistema di economia — vedi lo schema di
progetto per la specifica completa (ruoli Capo Clan/Admin Clan pari
tra gilde diverse, tesoreria, acquisto canali con costo raddoppiato
e requisito ore vocali scalabile ×4). Non incluso in questa fase.

**Suite di test completa: 209/209 passano.**

### Fase 9 — Memory Guard (SPEC.md §1.3) — parziale, sbloccata su richiesta esplicita
- [x] `core/memory_guard_logic.py` — logica pura: soglia di
  attivazione, cooldown tra un alert DM e il successivo (30 minuti,
  per non spammare l'owner ad ogni tick se la RAM resta alta),
  idoneità alla disconnessione di un VoiceClient inattivo. **11 test**
- [x] `core/memory_guard.py` — servizio reale (stesso pattern
  architetturale di `core/scheduler.py`): legge la RSS vera del
  processo con `psutil`, forza `gc.collect()` su soglia, invia DM
  all'owner (con cooldown), disconnette i VoiceClient rimasti in
  canali senza membri umani. **7 test**, incluso uno che legge la
  RAM VERA del processo di test in corso (nessun mock)
- [x] `MEMORY_ALERT_THRESHOLD_MB` aggiunto a `core/config.py` (default
  512, sovrascrivibile via `.env`). **Bug di dataclass trovato e
  corretto durante lo sviluppo**: un campo con default
  (`field(default=...)`) era stato inserito PRIMA di campi
  obbligatori nella dataclass `Config` — Python rifiuta questo
  ordine. L'errore emerge solo importando davvero la classe, non
  compilandola: verificato con un test di import reale, non solo
  `py_compile`
- [x] `/owner memory-status` — mostra il consumo RAM corrente.
  Aggiunto a `cogs/utility/owner_premium.py` (non un file proprio):
  `app_commands.Group` non ammette due gruppi di primo livello con
  lo stesso nome `owner` registrati da cog diversi
- [x] Colmato un vuoto di test preesistente: **non esisteva nessuno
  smoke test per `owner_premium.py`**, aggiunto mentre si toccava il file
- [x] Collegato a `main.py`, avviato insieme allo scheduler

**Ancora mancante in questa fase**: "Limitazione dimensione cache"
(SPEC.md §1.3) resta legata a §1.5 Cache Layer, non ancora scritta —
`SPEC.md` aggiornato di conseguenza (`[~]` parziale, non `[x]`).

**Suite di test completa: 228/228 passano.**

### Fase 10 — Spam Trap (SPEC.md §7.3) — quasi completo
- [x] `core/spam_trap_logic.py` — cooldown appeal (24h), partizione
  messaggi bulk/individuale al confine dei 14 giorni, finestra di
  purge 7-30 giorni, diff inviti. **16 test**, con i confini esatti
  a 7/14/30 giorni coperti esplicitamente
- [x] `core/invite_tracker.py` + `cogs/security/invite_sync.py` —
  infrastruttura RIUSABILE (utile anche al futuro Verify, SPEC.md
  §4.1): cache inviti in memoria, diff al join. Separazione
  deliberata core/cog per lo stesso motivo di scheduler/memory_guard.
  **13 test**
- [x] `core/repositories/spam_trap_repo.py` — config, indice
  messaggi (solo id/canale/timestamp, **mai contenuto** — nessun
  bisogno del Message Content Intent), appeal, incidenti (con
  transcript HTML persistito), tracciamento invito al join.
  **26 test contro PostgreSQL reale**, incluso un test di
  concorrenza sulla numerazione dei case (riusa moderation_repo)
- [x] `core/spam_trap_transcript.py` — generatore HTML, testabile
  senza Discord. **11 test**, 5 dei quali dedicati esplicitamente
  all'escaping anti-XSS (nickname/contenuto/titolo/allegato con
  markup HTML dentro)
- [x] `cogs/security/spam_trap.py` — `/spamtrap-setup`, sequenza
  fissa completa (cattura → transcript → DM prima del ban → ban →
  case → purge 7-30gg → cleanup webhook/inviti via audit log →
  log), ban appeal con thread privato e tre bottoni. **3 test smoke**,
  inclusa la verifica esplicita che `AppealActionsView` e
  `StaffReplyModal` (pattern mai usati prima nel progetto) si
  istanzino senza eccezioni

**Decisione architetturale importante, non ovvia**: il contenuto dei
messaggi (necessario per il log e il transcript) **non richiede il
Message Content Intent**. Quel privilegio riguarda solo il gateway
(eventi in tempo reale); un fetch REST esplicito
(`channel.fetch_message`) restituisce il contenuto pieno a
prescindere, governato dal normale permesso `READ_MESSAGE_HISTORY`.
Per questo l'indice messaggi salva solo id/canale/timestamp, e il
contenuto viene recuperato via fetch solo quando serve davvero (al
momento del ban). **Assunzione sul comportamento reale dell'API,
segnalata esplicitamente per la verifica sul server di test** — non
data per scontata in silenzio.

**Scope ridotto, dichiarato non nascosto**: il transcript non
rigenera le immagini degli allegati come thumbnail incorporate
(richiederebbe Pillow come nuova dipendenza, decisione non ancora
presa) — elenca gli allegati per nome. Il "ban globale via
fingerprint" resta `[ ]`: dipende da §4 Anti-Alt, non costruito.

**Suite di test completa: 287/287 passano.**

### Fase 11 — Verify Base (SPEC.md §4.1, 4.4, 4.5, 4.6) — completo, §4.2/4.3 restano bloccati sul Web Panel
- [x] `core/verify_logic.py` — età account, mutual servers, priorità
  di decisione **blacklist > whitelist > controlli** (la blacklist
  vince sempre, anche su un utente erroneamente anche whitelistato —
  verificato esplicitamente, non assunto). **15 test**
- [x] `core/repositories/verify_repo.py` — config, whitelist,
  blacklist (tabelle indipendenti a livello dati: è la logica, non
  il DB, a decidere chi vince), log di ogni tentativo. **18 test
  contro PostgreSQL reale**
- [x] `cogs/security/verify.py` — `/verify setup|panel|whitelist-add|
  whitelist-remove|blacklist-add|blacklist-remove`. Due modalità:
  **button** (persistente, supporta captcha testuale — nessuna
  immagine, evita Pillow) e **reaction** (`on_raw_reaction_add`, MAI
  captcha: una reazione non è un'Interaction, non può aprire un
  Modal — combinazione rifiutata esplicitamente a `/verify setup`,
  non implementata a metà)
- [x] **Bug di API deprecata trovato e corretto, in DUE file**:
  `TextInput(label=...)` produce un `DeprecationWarning` reale con
  discord.py 2.7.1 — il pattern corrente è `discord.ui.Label` che
  avvolge il `TextInput`. Scoperto dal warning summary di pytest
  scrivendo `CaptchaModal`, corretto lì **e** in `StaffReplyModal`
  (`cogs/security/spam_trap.py`, scritto in una sessione precedente
  con lo stesso pattern deprecato). Verificato con un giro di test
  dedicato a cercare l'ASSENZA dell'avviso, non solo che i test
  passassero

**Suite di test completa: 323/323 passano.**

### Fase 12 — Chiusura delle voci "parziali" di SPEC.md — 6 su 7
- [x] `core/bounded_cache.py` (SPEC.md §1.5) — cache LRU vera
  (verificata la differenza da un FIFO: un GET conta come uso
  recente quanto un SET), collegata come consumatore reale a
  `core/invite_tracker.py`, che prima cresceva senza limiti con il
  numero di server. Chiude anche l'ultima foglia mancante di §1.3
  Memory Guard. **19 test**
- [x] `core/error_handler_logic.py` + `main.py` `on_error` (SPEC.md
  §1.6) — le eccezioni non catturate nei LISTENER di eventi (non
  solo negli slash command) ora passano dal logger del progetto e
  avvisano l'owner in DM, con cooldown per event_method. **Colmato
  un vuoto di test preesistente: `main.py` non aveva MAI avuto un
  solo test**, non solo per questa parte. **9 test**
- [x] `core/json_log_formatter.py` (SPEC.md §1.7) — JSON con
  rotazione (`RotatingFileHandler`, 10MB×5), nessuna nuova
  dipendenza. **Un test di integrazione reale** (chiama
  `setup_logging()` per davvero, legge il file scritto su disco) ha
  trovato un `NameError` vero — un `import logging` mancante nel
  file di test stesso. **10 test**
- [x] `core/welcome_logic.py` + `main.py` `_send_welcome_message`
  (SPEC.md §1.8) — messaggio di benvenuto con fallback a catena
  (system_channel → primo canale scrivibile → DM owner). **Bug
  reale trovato scrivendo il test**: se l'invio sul system_channel
  falliva, la ricerca del canale alternativo poteva ritrovare lo
  stesso identico canale (quasi sempre incluso anche in
  `guild.text_channels`) e ritentarlo invece di passare a uno
  davvero diverso — corretto escludendolo esplicitamente dalla
  ricerca. **10 test**
- [x] `nickname_changed()` in `cogs/logging/basic_logs.py` (SPEC.md
  §8.4) — `on_member_update` ora gestisce ruoli E nickname nello
  stesso evento, senza uscire in anticipo se solo uno dei due cambia.
  **5 test**
- [ ] **Immagini nel transcript dello Spam Trap — lasciata aperta
  deliberatamente**, non decisa unilateralmente: richiede Pillow come
  nuova dipendenza, con peso reale sul deploy (compilazione, RAM) su
  una VM Oracle Free Tier. Chiesto esplicitamente all'utente invece
  di aggiungerla in autonomia

**Suite di test completa: 377/377 passano.**

### Fase 13 — Pillow + rigenerazione immagini nel transcript — chiude SPEC.md §7.3 al 100%
- [x] Pillow aggiunta come dipendenza (prima nuova dipendenza del
  progetto), su richiesta esplicita dell'utente dopo che il peso sul
  deploy era stato segnalato e discusso
- [x] `core/image_thumbnail_logic.py` — decisioni pure (è
  un'immagine? è dentro il limite di 8MB? costruzione della data
  URI). **16 test**
- [x] `core/image_thumbnail.py` — elaborazione vera con Pillow:
  apre, ridimensiona (max 400px, proporzioni conservate), ri-codifica
  in WebP. L'immagine rigenerata non è mai il file originale
  ricaricato — decodificata e ricreata pixel per pixel, il che
  elimina i metadati EXIF (posizione GPS, dispositivo) senza doverli
  ripulire esplicitamente. **9 test con immagini VERE generate da
  Pillow stesso al volo**, incluso un bug nel mio stesso helper di
  test (colore RGBA passato a un'immagine in modalità palette,
  invalido — Pillow l'ha sollevato correttamente)
- [x] Thumbnail degli allegati collegate al transcript reale
  (`cogs/security/spam_trap.py`, `_build_thumbnails`) —
  `asyncio.to_thread` per non bloccare l'event loop del bot durante
  l'elaborazione (Pillow è sincrono/CPU-bound)
- [x] Avatar dell'utente bannato nel transcript
  (`_build_author_avatar`) — scaricato **una sola volta per report**,
  non per ogni messaggio, dato che il transcript riguarda sempre un
  solo utente
- [x] Le thumbnail sono incorporate come **data URI dentro l'HTML
  stesso**, non riospitate da nessuna parte — coerente con "mai
  riospitare il file originale"
- [x] **17 test end-to-end** con oggetti Discord finti ma byte
  immagine veri (`test_spam_trap_thumbnails.py`), che verificano
  l'intera pipeline insieme (filtro → limite → download → thread →
  Pillow → data URI), non solo i pezzi isolati

**Con questa fase, `SPEC.md` non ha più NESSUNA voce `[~]`** —
verificato meccanicamente con lo stesso script di conteggio usato per
la tabella finale, non solo dichiarato.

**Suite di test completa: 419/419 passano.**

### Fase 14 — Role Menus (SPEC.md §14.1-14.3) — chiude le prime tre foglie di §14
- [x] `core/role_menu_logic.py` — toggle, sincronizzazione select
  (non tocca mai ruoli fuori dal menu, verificato esplicitamente),
  limiti opzioni per modalità. **13 test**
- [x] `core/repositories/role_menu_repo.py` — menu + opzioni, FK
  `ON DELETE CASCADE`. **18 test contro PostgreSQL reale**
- [x] `cogs/utility/role_menus.py` — `/rolemenu create|add-option|
  remove-option|delete`, tre modalità (reaction/button/select).
  **Pattern nuovo per il progetto**: View dinamiche **persistenti
  per-messaggio** (`bot.add_view(view, message_id=...)`), diverso dal
  pattern "un bottone fisso" già usato per ticket/verify/vocali —
  qui il numero di bottoni/opzioni varia da menu a menu, quindi ogni
  menu esistente viene ricostruito e registrato singolarmente ad
  ogni avvio del bot
- [x] Validazione emoji **non tentata lato client** — verificato con
  `inspect` che `PartialEmoji.from_str()` non solleva mai (accetta
  anche una stringa qualunque come fosse un'emoji valida): è l'API
  reale di Discord, quando l'emoji viene davvero usata, a dire se
  non è valida
- [x] **9 test smoke**, inclusa la costruzione delle View dinamiche
  verificata esplicitamente (numero di elementi corrisponde,
  `custom_id` codifica menu+ruolo, `max_selectable` limitato al
  numero di opzioni realmente presenti anche se il valore salvato in
  DB è più alto)

**Problema di test emerso e risolto, non di produzione**: questo è
il primo cog il cui `setup()` interroga il database al caricamento
(per ricostruire le View esistenti) — nessun test del progetto aveva
mai connesso il singleton `core.database.db` (tutti usano pool
isolati per-test). Risolto connettendo davvero il singleton in un
`try/finally` per questo specifico test, replicando esattamente
l'ordine reale di produzione (`db.connect()` avviene sempre prima
del caricamento dei cog).

**Suite di test completa: 459/459 passano.**

### Fase 15 — Greetings: Welcome/Goodbye/Boost (SPEC.md §14.4-14.6)
- [x] `core/greetings_logic.py` — rendering template con segnaposto
  `{user}`/`{username}`/`{server}`/`{membercount}`. **7 test**
- [x] `core/repositories/greetings_repo.py` — una tabella per tutti
  e tre i tipi (stesso pannello concettuale). **8 test contro
  PostgreSQL reale**
- [x] `cogs/utility/greetings.py` — `on_member_join` (canale + DM
  opzionale), `on_member_remove`, `on_member_update` filtrato al
  solo **inizio** boost (`premium_since` None → valorizzato).
  **Corretto prima di salvare, non dopo**: mancava il controllo
  `is_module_active_for_guild` nei tre listener — ogni altro modulo
  del progetto lo fa, l'ho notato rileggendo il file prima del test

**Suite di test completa: 475/475 passano.**

### Fase 16 — Moderazione completa al 100% (BACKLOG.md §5, priorità #2)
- [x] Cache configurazione moduli per server (BACKLOG.md §1,
  priorità #1) — `core/database.py`, `BoundedCache` invece di una
  query separata ad ogni messaggio/reazione per i 5 moduli che
  condividono `on_message`/`on_raw_reaction_add`. **4 nuovi test**,
  incluso uno che dimostra la cache *davvero* usata (SQL grezzo che
  bypassa l'invalidazione, verifica che il valore stantio resti in
  memoria)
- [x] `core/moderation_validation_logic.py` — `is_valid_reason()`
  (minimo 3 caratteri). **7 test**
- [x] `cogs/moderation/_shared.py` — `validate_reason()` e
  `post_to_mod_log()` (canale dedicato, riusa `get_guild_setting`/
  `set_guild_setting` già esistenti). **5 test**, incluso un bug
  reale nel mio stesso test (isinstance su un duck-type qualsiasi
  non basta — corretto ereditando da `discord.TextChannel` senza
  chiamare il costruttore, `isinstance` passa per gerarchia vera)
- [x] `reason: str` (obbligatorio) su warn/kick/ban/tempban/unban/
  timeout + i due nuovi comandi, con validazione e mod-log dopo ogni
  azione. `/untimeout` e `/lock` restano con reason opzionale per
  scelta dichiarata (non nella lista esplicita dello schema)
- [x] `cogs/moderation/softban_mute.py` (nuovo file) — `/softban`
  (ban+unban immediato), `/mute-role`+`/unmute-role` (ruolo "Muted"
  auto-creato con overwrite su ogni canale esistente al momento
  della creazione — limite dichiarato: canali creati dopo non
  ereditano l'overwrite), `/mod-log-setup`
- [x] **Verifica esplicita, non solo assunta**: aggiunto un controllo
  in entrambi gli smoke test che legge `reason_param.required` per
  davvero sui comandi interessati — se in futuro qualcuno
  reintroduce `reason: str | None = None` per errore, il test lo
  blocca subito, non serve accorgersene mesi dopo

**§5 Moderation è ora completa al 100% (12/12)** — la seconda
sezione a chiudersi del tutto, dopo §7.3 Spam Trap.

**Suite di test completa: 492/492 passano.**

### Fase 17 — Permission Heatmap + Config Diff & Rollback (BACKLOG.md §11, 2 su 4)
- [x] `core/permission_risk_logic.py` — `CRITICAL_PERMISSIONS`
  (sottoinsieme deliberatamente ristretto), `newly_gained_critical_
  permissions()` guarda solo i ruoli **appena aggiunti** — un ruolo
  critico rimosso non è mai un alert. **13 test**
- [x] `cogs/security/permission_heatmap.py` — `/permission-heatmap`
  + DM diretto all'owner su nuova assegnazione critica (nessun setup
  richiesto, stesso principio di Memory Guard). Modulo candidato
  premium. **1 test smoke**
- [x] `core/database.py` — nuova tabella `guild_config_history`,
  registrata da `set_module_active_for_guild`/`set_guild_setting`
  (parametro opzionale `changed_by`, compatibile con i 5 chiamanti
  esistenti). `rollback_config_change()` — il rollback stesso si
  registra come nuova voce di storico, non sparisce dalla cronologia.
  **16 test contro PostgreSQL reale**
- [x] `cogs/utility/config_history.py` — `/config history` + `/config
  rollback` con conferma a due passaggi (View non persistente).
  **2 test smoke**
- [x] **Bug reale trovato e corretto in `cogs/utility/setup.py`, non
  ipotizzato a tavolino**: `/setup` scriveva (e avrebbe loggato)
  OGNI modulo ad ogni salvataggio, anche quelli invariati — avrebbe
  riempito lo storico di voci "cambiate" false fin dal primo
  utilizzo. Corretto con una copia congelata dello stato iniziale
  prima che la selezione venga mutata. **Verificato con un test
  dedicato**

**Resta da fare in BACKLOG.md §11**: Smart AutoMod Escalation Ladder
(estende §6 AutoMod).

**Suite di test completa: 518/518 passano.**

### Fase 18 — Smart AutoMod Escalation Ladder (BACKLOG.md §11, chiude la priorità #3)
- [x] `core/escalation_ladder_logic.py` — `get_ladder_action()`
  gestisce esplicitamente il caso più importante: oltre l'ultimo
  gradino definito, un utente recidivo resta sul gradino **più
  severo**, non esce dal sistema senza conseguenze. **13 test**
- [x] `core/repositories/escalation_repo.py` — `DEFAULT_LADDER` (warn
  → timeout 10min → timeout 1h) usata finché l'admin non configura
  la propria. **14 test contro PostgreSQL reale**
- [x] `cogs/automod/escalation.py` — ascolta `on_automod_action`
  (l'evento nativo di Discord quando una regola AutoMod scatta) e
  applica una severità crescente nel tempo, cosa che l'AutoMod nativo
  non sa fare da solo. Doppio gate: `MODULE_AUTOMOD` attivo E
  escalation esplicitamente abilitata. Riusa `MODULE_AUTOMOD` invece
  di registrare un secondo modulo premium — stesso interruttore, non
  uno in più da gestire per l'admin. Ogni azione crea anche un case
  nel sistema di moderazione esistente. **1 test smoke**
- [x] `SPEC.md` §6.15 aggiunta come voce **nuova** (non una
  ridefinizione di §6.13, concettualmente diversa: azioni combinate
  su un trigger vs scala nel tempo su trigger ripetuti)

**BACKLOG.md §11 completata al 100%** (3 voci su 4 — Staff Workload
Intelligence resta `RIMANDATA` per il rischio di incentivi perversi
già discusso). **Priorità #1, #2 e #3 del backlog accettato sono ora
tutte FATTE.**

**Suite di test completa: 546/546 passano.**

### Fase 19 — Log eventi unificato multi-indice (BACKLOG.md §3, chiude la priorità #4)
- [x] `core/event_log_retention_logic.py` — `retention_days_for()`
  (30gg Free, 180gg Premium). **3 test**
- [x] `core/repositories/event_log_repo.py` — tabella `event_log`,
  un evento salvato UNA VOLTA con indici su membro/canale/ruolo/
  tempo/case. `export_events()` per l'export GDPR-style,
  `prune_old_events_for_guild()` per la retention per-server.
  **14 test contro PostgreSQL reale**
- [x] `cogs/logging/basic_logs.py` — tutti e 7 i listener esistenti
  scrivono ora anche nel log unificato, **indipendentemente dal
  canale live configurato** (verificato con un test dedicato: un
  evento arriva nel DB anche senza nessun canale impostato). **Bug
  evitato prima del commit**: `added_ids`/`removed_ids` sono `set`,
  `json.dumps()` solleva `TypeError` su un set — verificato con una
  chiamata reale prima di scrivere il fix, non assunto
- [x] `cogs/logging/logs_query.py` — `/logs user|channel|export`
  (JSON completo via `discord.File`/`io.BytesIO`, nessun file
  temporaneo su disco)
- [x] `core/event_log_retention.py` — servizio bot-wide (stesso
  pattern di Memory Guard), retention **differenziata per server**
  in base allo stato Free/Premium, agganciato in `main.py`.
  Verificato con un test di integrazione reale (whitelist premium
  vera, non un mock): due server con lo stesso evento vecchio,
  soglie diverse, solo uno dei due lo perde

**Deliberatamente non costruito, come da analisi**: la proiezione su
Forum Discord per canali/case (bassa cardinalità) — resta
un'estensione futura separata, la decisione di scartarla per
membri/messaggi (alta cardinalità) resta invariata.

**BACKLOG.md §3 (parte DB) completata. Priorità #1-#4 del backlog
accettato sono ora tutte FATTE.** Resta solo #5 (Memory Guard a
soglie scalate).

**Suite di test completa: 567/567 passano.**

### Fase 20 — Metodologia di simulazione di carico + fix trovato con essa
L'utente ha chiesto, giustamente, di non dare per buone stime a
tavolino sul consumo di RAM/CPU per il piano Oracle Free reale (2
OCPU Ampere, 12GB RAM — **verificato lo stesso giorno sulla
documentazione Oracle**: allowance dimezzata da 4 OCPU/24GB in
silenzio il 15 giugno 2026, termine di adeguamento 18 agosto 2026 già
passato). Creato `scripts/load_simulation.py` (istruzioni d'uso nel
suo stesso docstring): istanzia i cog REALI (`LevelingCog`,
`SpamTrapCog`) e li fa girare contro PostgreSQL vero con centinaia di
migliaia di eventi `on_message` simulati, misurando con `psutil` (non
a stima) RSS, tempo CPU, throughput. Eseguibile dentro un cgroup v1
reale (memory.limit_in_bytes) per un tetto di RAM verificabile, non
finto.

**Limite dichiarato esplicitamente**: il sandbox di sviluppo ha 1 CPU
e ~3.9GB RAM — MENO del piano Oracle reale su entrambi i fronti. I
numeri assoluti misurati qui sono ordine di grandezza/andamento
(cresce senza fine? si stabilizza?), non una previsione esatta per la
macchina Ampere reale.

**Trovato con la prima simulazione (100 server x 1000 messaggi,
200.000 chiamate)**: `spam_trap_repo.get_config()` girava SENZA cache
su ogni messaggio quando lo Spam Trap è attivo — stesso identico
problema già risolto per `is_module_active_for_guild`, rimasto
scoperto qui. Corretto con lo stesso pattern (`BoundedCache`,
invalidazione esplicita). **Confronto prima/dopo con GLI STESSI
parametri**: tempo CPU -22% (81.02s → 63.30s), tempo reale -14%
(149.26s → 128.01s), throughput +17% (670 → 781 msg/s). RSS invariata
in entrambi i giri (nessuna fuga di memoria, né prima né dopo).

Nessun altro problema emerso da questa simulazione: pool DB mai sotto
pressione, RSS piatta su 100.000 messaggi.

**Suite di test completa: 569/569 passano.**

### Fase 21 — Memory Guard a quattro livelli (BACKLOG.md §4, ULTIMA priorità del backlog)
- [x] `core/memory_guard_logic.py` — `MemoryTier` (NORMAL/WARNING/
  CRITICAL/EMERGENCY), derivati dalla soglia esistente
  `MEMORY_ALERT_THRESHOLD_MB` con due rapporti fissi (WARNING=70%,
  EMERGENCY=130%) — nessun nuovo schema di configurazione, CRITICAL
  conserva esattamente il significato che l'admin già le dava.
  Risposta graduata: WARNING forza GC senza avvisare, CRITICAL si
  comporta come la vecchia soglia singola, EMERGENCY avvisa SEMPRE
  bypassando il cooldown. **24 test**
- [x] **Bug reale trovato dal mio stesso test**, non nella funzione
  di produzione: un confine ESATTO in virgola mobile (512×0.7) è
  fragile da testare per via dell'arrotondamento nel giro
  byte→MB→byte. Corretto usando valori appena sopra il confine
  invece che esattamente su di esso
- [x] 3 test esistenti aggiornati perché **passavano ma per il
  motivo sbagliato** dopo il cambio (un valore così alto da ricadere
  sempre in EMERGENCY, che bypassa il cooldown comunque — non
  testavano più davvero il confine a cui erano intitolati)
- [x] `core/memory_guard.py` — `tick()` usa `should_force_gc()` (da
  WARNING in su) e `should_send_alert()` tier-aware. Pool DB e
  conteggio task letti in modo tollerante e inclusi nell'alert
  (versione ridotta come da BACKLOG.md §4 — solo le metriche già
  misurabili senza nuove dipendenze). **9 test**, inclusi due nuovi
  che verificano i comportamenti nuovi per davvero (WARNING senza
  alert, EMERGENCY che bypassa il cooldown)

**BACKLOG.md aggiornato**: tutte e 5 le priorità concrete del
backlog accettato sono ora `FATTA`. Restano solo le voci
`RIMANDATA`/`RESPINTA`/`NON DECISO`, ciascuna con la propria
condizione di riapertura già scritta — nessuna richiede azione ora.

**SPEC.md §1.3**: la sotto-voce "Garbage collection forzata su
soglia" aggiornata per descrivere i quattro livelli (nessun
marcatore cambiato, era già `[x]` — solo la descrizione è più
precisa, tabella dei conteggi invariata).

**Suite di test completa: 584/584 passano.**

### Fase 22 — Reminder personali (SPEC.md §14.16), primo lavoro dopo l'esaurimento del backlog
- [x] `core/duration_logic.py` — refactor: `parse_duration`/
  `format_duration` estratte da `cogs/moderation/_shared.py` (dove
  vivevano solo per tempban/timeout) al primo secondo consumatore
  reale. `_shared.py` ora **riesporta** dalla nuova sede (stessa
  funzione, non una copia) — nessun chiamante esistente ha dovuto
  cambiare. Test rinominato con `git mv` (storia preservata) da
  `test_duration_parser.py` a `test_duration_logic.py`
- [x] `core/scheduler.py` — `list_pending_for_user()` e
  `get_pending_action()`, prerequisito per i reminder. Il docstring
  dello scheduler aveva già "in futuro anche promemoria" come caso
  d'uso previsto. **6 nuovi test contro PostgreSQL reale**
- [x] `cogs/utility/reminders.py` — `/reminder set|list|cancel`,
  **nessuna tabella nuova** (riusa `scheduled_actions` così com'è).
  Consegna: DM prima, fallback nel canale se i DM sono chiusi,
  loggato senza sollevare se anche il fallback fallisce
- [x] **Disciplina test già scritta per `actions.py` riapplicata
  correttamente**: `registry.register()`/`scheduler.register_handler()`
  sollevano su doppia registrazione — un solo test per file di
  smoke, non separato in più funzioni
- [x] `tests/test_reminders_handler.py` — **5 test del comportamento
  REALE di consegna** (non solo che il cog carica): DM riuscito non
  tenta il fallback, DM fallito usa il fallback, entrambi falliti
  non solleva, nessun `channel_id` non solleva, utente non trovato
  tenta comunque il fallback

**Snipe/Editsnipe/Reactionsnipe e Autoresponder scartati per questo
giro** (non costruiti, non solo rimandati in silenzio): richiedono
il Message Content Intent per leggere/conservare il testo dei
messaggi altrui — stessa cautela già scritta per §8.16, non
richiesto finché un modulo non lo giustifica esplicitamente.

**Suite di test completa: 596/596 passano.**

### Fase 23 — Sticky Messages, Server Stats, Suggestion System (SPEC.md §14.13/14.18/14.14)
Tre feature richieste insieme dall'utente, costruite una alla volta
con la stessa disciplina.

**Sticky Messages (§14.13)**
- [x] `core/sticky_message_logic.py` — debounce minimo (5s) contro
  cancella+reinvia ad ogni singolo messaggio in un canale attivo.
  **5 test**
- [x] `core/repositories/sticky_message_repo.py` — una riga per
  canale, `set_sticky()` azzera lo stato di repost quando il testo
  cambia. **7 test**
- [x] `cogs/utility/sticky_messages.py` — `/sticky set|remove`.
  **BUG DI TEST trovato e corretto**: `sticky_messages.py` fa `from
  core.database import db`, il nome è legato al modulo AL MOMENTO
  DELL'IMPORT — monkeypatchare `core.database.db` non lo tocca, va
  patchato l'attributo dentro il modulo consumatore stesso (stesso
  schema già risolto per `basic_logs.py`, riapplicato correttamente
  qui dopo un primo tentativo sbagliato notato subito dall'errore).
  **5 test di integrazione reali** (ripubblica e cancella il
  vecchio, rispetta il debounce, ignora modulo disattivato, ignora
  messaggi del bot)

**Server Stats (§14.18)**
- [x] `core/server_stats_logic.py` — variazione giornaliera da
  eventi join/leave, senza tentare di ricostruire la popolazione
  storica assoluta (richiederebbe un dato che non abbiamo). **11 test**
- [x] `core/repositories/event_log_repo.py` — `get_events_by_type_since()`,
  nuovo metodo senza limite di conteggio. **3 nuovi test**
- [x] `core/server_stats_image.py` — grafico a barre disegnato a
  mano con Pillow, **deliberatamente non matplotlib** (avrebbe
  trascinato numpy come nuova dipendenza pesante). **7 test con
  immagini vere**
- [x] `cogs/utility/server_stats.py` — `/serverstats [days]`. **Bug
  evitato, verificato prima di scrivere**: `discord.Embed.Empty` non
  esiste più in discord.py 2.7 (verificato con `hasattr`, non
  assunto) — usato `None`. Aggiunto `is_module_active_for_guild`
  dimenticato nella prima stesura, notato rileggendo prima di
  testare. **1 test smoke**

**Suggestion System (§14.14, distinto da §14.8 che va al server dello
sviluppatore)**
- [x] `core/suggestion_logic.py` — `can_decide()`, solo una
  suggestion "pending" può essere decisa. **3 test**
- [x] `core/repositories/suggestion_repo.py` — `list_pending()` per
  ricostruire le View persistenti all'avvio, stesso principio dei
  Role Menu. **8 test**
- [x] `cogs/utility/suggestions.py` — `/suggestion-setup`, `/suggest`,
  bottoni persistenti approva/rifiuta + reazioni native 👍👎.
  **Pulizia fatta prima di salvare**: un ciclo morto e un footer che
  non diceva nulla di utile, corretti entrambi prima del commit,
  non dopo. **1 test smoke**

**§14.13 era stata dimenticata in SPEC.md in una sessione precedente**
(costruita e pushata, ma mai marcata) — notato e corretto durante
l'aggiornamento di questa fase.

**Suite di test completa: 648/648 passano.**

### Fase 24 — Poll (SPEC.md §14.15), sessione con budget token ridotto
`cogs/utility/poll.py`. Nessuna logica propria estratta: come
indicato dallo schema stesso, usa `discord.Poll` nativo — voto,
conteggio, chiusura automatica e visualizzazione dei risultati sono
TUTTI gestiti da Discord. `/poll` con fino a 5 opzioni, durata
configurabile (1-768 ore), scelta multipla opzionale. 1 test smoke.

**Traguardo tondo: 100 voci fatte** su 268 — circa il 37%.

**Suite di test completa: 649/649 passano.**

### Fase 25 — Scheduled Messages (SPEC.md §14.17)
- [x] `core/scheduler.py` — `list_pending_for_guild()`, simmetrico a
  `list_pending_for_user()` ma filtrato per server invece che per
  utente (un admin deve vedere tutti i messaggi programmati del
  proprio server, non solo i propri). **2 nuovi test**
- [x] `cogs/utility/scheduled_messages.py` — `/schedule-message
  set|list|cancel`, riusa lo stesso scheduler dei Reminder (nessuna
  tabella nuova). A differenza del Reminder (personale, via DM),
  pubblica in un canale del server — strumento admin, non personale.
  **1 test smoke + 4 test del comportamento reale dell'handler**
  (canale corretto, canale/server non raggiungibile non solleva,
  invio fallito non solleva)

**Suite di test completa: 656/656 passano.**

### Fase 26 — Custom Commands request (SPEC.md §14.8) + inizio §17 Owner
**Custom Commands request system (§14.8)**: modal a 3 campi, sempre
verso il server principale dello sviluppatore (distinto dal
Suggestion System di §14.14, che va al server cliente), bottoni
persistenti approva/rifiuta, notifica DM di ritorno. Riusa `core/
suggestion_logic.py` per lo stato — stessa macchina pending/approved/
rejected, applicata a un tipo diverso di richiesta.

**Verifica tecnica importante prima di iniziare §17**: testato
empiricamente se un `app_commands.Group` potesse essere condiviso tra
file diversi (per non far crescere `owner_premium.py` all'infinito).
**Confermato che NON si può**: `self` si lega alla classe che
POSSIEDE il `Group`, non a quella dove il metodo è scritto — tutti i
comandi `/owner` restano quindi in un solo file, come già deciso in
precedenza nel codice stesso.

**Blacklist globale (§17.4/17.5) + Leave guild forzato (§17.9)**:
- `core/repositories/blacklist_repo.py` — cache su entrambi i
  controlli (stesso principio della config moduli: girano su OGNI
  interazione del bot). **13 test**
- `core/blacklist_tree.py` — `BlacklistAwareCommandTree`, sottoclasse
  di `CommandTree` che intercetta OGNI interazione prima del dispatch
  al comando specifico. **Bug reale trovato scrivendo il primo test**:
  non si può costruire una seconda `CommandTree` su un bot che ne ha
  già una (discord.py solleva `ClientException`) — va passata come
  `tree_cls=` al costruttore di `commands.Bot()`. **4 test**
- `main.py` — `on_guild_join` esce SUBITO da un server in blacklist,
  prima di configurarlo. **2 test**
- `cogs/utility/owner_premium.py` — `blacklist-user/guild
  add|remove|list`, `leave-guild` (esce immediatamente se il server
  bloccato è già presente, non aspetta il prossimo controllo).
  **Bug di test trovato**: `core.config.Config` è un dataclass
  FROZEN, non monkeypatchabile — corretto usando il vero `OWNER_ID`
  già impostato dall'ambiente di test. **5 test del comportamento
  reale**, non solo smoke

**Resta di §17**: 17.3 Eval/Exec/Shell, 17.6 Forced cog load/unload/
reload, 17.7 Annuncio globale, 17.8 Statistiche globali, 17.10
Pannello premium interattivo.

**Suite di test completa: 688/688 passano.**

### Fase 27 — Forced cog load/unload/reload (SPEC.md §17.6), due bug sistemici corretti
`cogs/utility/owner_premium.py`: `/owner cog-load|cog-unload|
cog-reload`. Due bug sistemici trovati mentre lo costruivo, entrambi
corretti PRIMA di committare, non scoperti dopo.

**Bug #1 (rompeva ogni cog del bot)**: i nomi dei metodi Python erano
`cog_load`/`cog_unload` — hook di ciclo di vita **riservati** dalla
classe base `discord.ext.commands.Cog`, chiamati automaticamente
all'iniezione/rimozione. Il mio comando li sovrascriveva
silenziosamente. Rinominati in `owner_cog_load`/`owner_cog_unload`/
`owner_cog_reload` (i nomi degli slash command restano invariati).

**Bug #2 (sistemico, trovato con un test reale su un cog vero, non
ipotizzato)**: `bot.reload_extension()` richiama sempre `setup()` una
seconda volta — QUALUNQUE cog che chiama `registry.register()` o
`scheduler.register_handler()` nel proprio `setup()` (praticamente
tutti quelli con un modulo premium o un handler scheduler) falliva
SEMPRE al reload, perché entrambe le funzioni sollevavano un errore
alla seconda registrazione dello stesso nome, senza distinguere un
reload legittimo da un vero conflitto.

- `core/premium.py`: `PremiumRegistry.register()` ora confronta la
  dichiarazione (display_name/description/premium_capable) — stessa
  dichiarazione = reload legittimo, non sovrascrive l'entry
  (preserva `is_premium_active`, un reload non deve resettare lo
  stato premium a `False`); dichiarazione diversa = conflitto vero,
  solleva ancora. **7 nuovi test** (file nuovo, mancava un test
  dedicato per questa classe)
- `core/scheduler.py`: `register_handler()` confronta `__qualname__`
  dell'handler — stesso metodo (nuova istanza dopo un reload) =
  sostituisce il riferimento vecchio, metodo di classe diversa =
  vero conflitto. **4 nuovi test**

**Suite di test completa: 703/703 passano.**

### Fase 28 — Annuncio globale (SPEC.md §17.7)
`main.py`: estratto `_send_embed_with_fallback(guild, embed,
contesto)` da `_send_welcome_message` (che ora è un sottile wrapper)
— stessa catena system_channel → primo canale scrivibile → DM
proprietario, incluso il fix già presente per l'esclusione del
system_channel dalla ricerca del canale scrivibile. Ora restituisce
`bool`, non serviva prima. `cogs/utility/owner_premium.py`: `/owner
announce` itera `bot.guilds` e riusa il metodo generico, riportando
quanti server ha raggiunto. 4 nuovi test (2 sul valore di ritorno di
`_send_embed_with_fallback`, mai testato prima; 2 su `/owner
announce`, incluso il conteggio reale). 13/13 test esistenti
confermano che il refactor non ha cambiato il comportamento del
messaggio di benvenuto.

**Suite di test completa: 707/707 passano.**

### Fase 29 — Statistiche globali (SPEC.md §17.8)
`core/bot_stats.py`: `RollingCounter`, finestra scorrevole di 60s
per comandi/errori — non un contatore cumulativo dall'avvio (dice
"quanto è attivo il bot ADESSO"). **Bug reale trovato scrivendo il
test**: `count_in_window()` potava solo dalla testa della coda,
presumendo inserimenti in ordine cronologico — un test con
inserimenti fuori ordine ha rivelato che si fermava al primo
timestamp ancora valido, lasciando scaduti più indietro non rimossi.
Corretto filtrando l'intera coda. **7 test**.

`core/blacklist_tree.py` conta ogni interazione che supera la
blacklist (nessun hook `on_completion` disponibile in questa
versione di discord.py); `core/premium.py` conta ogni errore in
`handle_app_command_error`. **6 nuovi test**, incluso la prova che
un'interazione bloccata NON incrementa il contatore.

`cogs/utility/owner_premium.py`: `/owner stats` — server, membri
stimati, RAM (riusa memory_guard), latenza, latenza per shard,
comandi/errori nell'ultimo minuto. **2 nuovi test**.

**Suite di test completa: 719/719 passano.**

### Fase 30 — Pannello premium interattivo (SPEC.md §17.10)
`core/database.py`: nuova tabella `premium_toggle_history`
(append-only, distinta da `premium_module_flags` che tiene solo
l'ULTIMO stato) — il log persistente richiesto dallo schema, ogni
cambio resta nello storico anche dopo un cambio successivo.

`cogs/utility/owner_premium.py`: estratto `_apply_premium_toggle()`
condiviso da `/owner premium-toggle` (comando esistente,
refactorizzato per usarlo) e dal nuovo pannello — un solo punto che
applica un cambio premium (registry + `premium_module_flags` +
`premium_toggle_history`), mai due copie della stessa logica.

`/owner premium-panel`: Select con tutti i moduli premium-capable →
selezionandone uno, conferma a due step (embed "Conferma richiesta"
con bottoni Conferma/Annulla) prima di applicare — esattamente
"conferma a due step" come richiesto dallo schema, perché un cambio
premium vale per TUTTI i server insieme.

3 nuovi test, incluso un **ciclo COMPLETO** selezione→conferma
verificato contro PostgreSQL reale, non solo che i pezzi si carichino:
il Select invocato con `_values` impostato manualmente (`values` è
una proprietà di sola lettura, verificato l'attributo interno corretto
prima di scrivere il test), la conferma applica il cambio e scrive
nello storico, il bottone Annulla non applica nulla.

**§17 Owner è ora a 9/10 — resta solo Eval/Exec/Shell**, lasciato per
ultimo di proposito fin dall'inizio di questa sezione.

**Suite di test completa: 722/722 passano.**

### Fase 31 — Eval/Exec/Shell (SPEC.md §17.3) — CHIUDE L'INTERA SEZIONE §17 OWNER
Ultima voce di §17, lasciata per ultima di proposito fin dall'inizio
della sezione perché genuinamente delicata: esecuzione di codice
arbitrario, riservata all'owner verificato del bot.

`core/eval_shell_logic.py`: `truncate_output()` — un output troncato
a metà senza avviso sembra un risultato completo quando non lo è.
**5 test.**

`core/repositories/eval_shell_log_repo.py`: `eval_shell_log`,
append-only come `premium_toggle_history` — chi ha eseguito codice
arbitrario, cosa, quando, resta tracciabile per sempre. **4 test**
contro PostgreSQL reale.

`cogs/utility/owner_premium.py`: `/owner eval` (pattern standard di
"eval cog", codice avvolto in una funzione async — supporta `await`
—, stdout catturato, eccezioni mostrate come traceback) e `/owner
shell` (via `asyncio.create_subprocess_shell`, timeout esplicito di
30s — un comando appeso non deve bloccare l'event loop per sempre).
**Secondo fattore di conferma esplicito**, come richiesto dallo
schema: `_EvalConfirmView`/`_ShellConfirmView` mostrano il
codice/comando per intero prima dell'esecuzione, bottoni
Esegui/Annulla — stesso principio del pannello premium (§17.10).
Shell non è una nuova capacità concessa dal bot: equivale all'accesso
terminale che l'owner ha già sulla propria macchina.

**12 nuovi test, tutti su comportamento REALE**: esecuzione vera di
codice Python (espressioni, `await`, `print`, eccezioni con
traceback), esecuzione vera di comandi shell (successo, exit code
diverso da zero), due cicli completi conferma→esegui→logga e
annulla→niente-eseguito-niente-loggato verificati contro PostgreSQL
reale.

**§17 Owner è COMPLETO: 10/10.**

**Suite di test completa: 740/740 passano.**

### Fase 32 — COMMAND_LIST.md + /search (richiesta diretta dell'utente, fuori dallo schema originale)
L'utente ha chiesto un documento con tutti i comandi esistenti,
indicizzato per categoria, e un comando `/search <descrizione>` che
ci rimandi al comando giusto o, se non trova nulla, proponga di
aprire una richiesta verso lo sviluppatore (riusando il modal già
esistente di Custom Commands request, non uno nuovo).

**`COMMAND_LIST.md` non è scritto a mano**: `scripts/generate_command_
list.py` carica ogni cog reale e interroga `bot.tree` DOPO il
caricamento — il documento non può disallinearsi dal codice perché
non lo copia, lo LEGGE dal bot vero. **Bug trovato e corretto**: lo
script inizialmente creava una `Database()` separata invece di usare
il singleton globale `db` — 3 cog (custom_command_requests,
role_menus, suggestions) interrogano il DB nel proprio `setup()` per
ricostruire le View persistenti e fallivano il caricamento.

`core/command_search_logic.py`: punteggio per sovrapposizione di
parole (nessuna infrastruttura NLP/embedding nel progetto). **Due
correzioni trovate scrivendo test con query realistiche**: forme
verbali italiane diverse della stessa radice ("bannare" vs "banna")
non condividevano token esatti — aggiunto un confronto per prefisso
condiviso; parole di riempimento italiane ("voglio", "qualcuno")
diluivano il punteggio dividendo per un totale gonfiato da rumore —
aggiunto un filtro di stopword.

`core/command_tree_utils.py`: `walk_commands()` estratta in un
modulo condiviso tra lo script di generazione e il nuovo cog
`/search` — un solo posto che sa espandere i `Group` annidati.

`cogs/utility/command_search.py`: `/search` interroga `bot.tree` DAL
VIVO (non il markdown, che potrebbe non essere ancora rigenerato).
Nessun risultato → bottoni Sì/No; Sì apre `CustomCommandRequestModal`
GIÀ ESISTENTE (nessun modal nuovo), No annulla.

**26 nuovi test totali** tra i quattro file, tutti su comportamento
reale — incluso il collegamento vero al modal esistente (non solo
che viene istanziato, ma che il flusso completo dal bottone al modal
funziona quando il cog delle richieste è caricato, e non solleva
quando non lo è).

**REGOLA OPERATIVA PERMANENTE, da qui in avanti**: dopo ogni commit
che aggiunge, rimuove o rinomina un comando slash, rilanciare
`scripts/generate_command_list.py` (vedi il suo stesso docstring per
le variabili d'ambiente necessarie) e committare/pushare il
`COMMAND_LIST.md` aggiornato nello stesso giro — mai lasciarlo
disallineato dal codice reale. L'utente lo userà anche come base per
un futuro sito.

**Suite di test completa: 762/762 passano.**

### Fase 33 — Ship e Rate (SPEC.md §16.5/16.7), primo pezzo di §16 Fun & Immagini
`core/fun_logic.py`: deterministico via hash SHA-256, non random ad
ogni chiamata — stessa coppia di utenti o stesso testo devono dare
sempre lo stesso risultato. `compute_ship_percentage()` simmetrico
(ordina gli ID prima dell'hash). Nuova cartella `cogs/fun/`, prima
voce mai fatta della sezione. **Deliberatamente esclusi**: NSFW/
Rule34 (app separata secondo lo schema), "Howgay" (troppo vicino a
un attributo protetto per un giochino casuale). 21 nuovi test totali
(15 logica pura + 6 comportamento reale, incluso un test di
simmetria vera del comando, non solo della funzione isolata).

**Suite di test completa: 783/783 passano.**

### Fase 34 — Alert & Social (SPEC.md §10), quattro voci su otto
**Decisione tecnica per l'intera sezione**: lo schema chiedeva
EventSub (Twitch) e PubSubHubbub (YouTube), entrambi webhook PUSH —
richiedono un endpoint HTTPS pubblico che questo bot non ha (nessun
server web, verificato prima di scrivere codice). Sostituito con
POLLING (stesso principio di Memory Guard/Event Log Retention) su
feed RSS/Atom NATIVI di YouTube e Reddit — zero chiavi API.

- `core/feed_parsing_logic.py`: `parse_feed()` analizza RSS 2.0 e
  Atom, `find_new_entries()` (primo controllo mai fatto → sempre
  lista vuota, altrimenti pubblicherebbe l'intero storico in un
  colpo solo), `render_alert_message()` per template personalizzabili
  (§10.9). **14 test**, fixture XML fedeli allo standard pubblicato
  (non recuperabili dal vivo — rete del sandbox limitata)
- `core/repositories/feed_subscription_repo.py`: una riga per feed
  sottoscritto, `remove_subscription()` scoperto per server. **7 test**
- `core/feed_watcher.py`: servizio di polling ogni 5 minuti, stesso
  pattern architetturale di `event_log_retention.py`. **4 test con
  un server aiohttp VERO in locale**, non un mock della sessione HTTP
- `cogs/utility/feed_alerts.py`: `/alerts add|remove|list`. **5 test**
  sul comportamento reale, incluso il ciclo completo add→list→remove
  contro PostgreSQL vero

**Chiuso**: §10.3 (YouTube), §10.7 (Reddit), §10.8 (RSS generico),
§10.9 (template). **Aperto in attesa di credenziali dell'utente**:
§10.1/§10.2 (Twitch — serve un Client ID/Secret gratuito da
dev.twitch.tv). **Resta non fatto per lo stesso motivo già nello
schema**: §10.5 TikTok (nessuna API ufficiale). §10.4 YouTube live
rimandato (RSS non indica lo stato live in modo affidabile).

**Bug di documentazione trovato e corretto in questa stessa
sessione**: sia §16.5/§16.7 (Ship/Rate, Fase 33) sia il codice di
questa fase erano stati costruiti e pushati ma MAI marcati in
`SPEC.md` — notato solo ricalcolando i totali con lo script
meccanico (mostrava x=0 per una sezione che sapevo avere codice
funzionante). Corretto per entrambe insieme in questo aggiornamento.

**Suite di test completa: 813/813 passano.**

### Fase 35 — Music (SPEC.md §9), player base funzionante
Decisione presa CON l'utente prima di scrivere codice (risposta a
una sua domanda diretta): `wavelink` (già in requirements.txt) resta
la scelta giusta nel 2026, nessuna alternativa architetturale
migliore. Novità: nodi Lavalink PUBBLICI gratuiti mantenuti dalla
community (es. lista di `lavalink.darrennathanael.com`) — usati con
fallback tra più nodi invece di self-hostare un processo Java sulla
stessa VM del bot (peserebbe centinaia di MB extra su una macchina
già misurata con cura in `scripts/load_simulation.py`).

`wavelink` non era installato nel sandbox nonostante fosse già in
requirements.txt — installato (3.5.2) per scrivere codice contro
l'API vera, non a memoria, verificando firme reali di `Node`,
`Pool.connect()`, `Player`, `Playable.search()`, `Queue`,
`TrackEndEventPayload` prima di scrivere una riga di cog.

- `core/music_logic.py`: `format_duration()`, `build_queue_display()`,
  `parse_lavalink_nodes()` (un nodo scritto male nel .env viene
  ignorato, non fa sparire gli altri). **18 test**
- `core/config.py`: `LAVALINK_NODES` opzionale multi-nodo, con
  precedenza sui tre campi singoli esistenti (comportamento
  originale a singolo nodo invariato se non impostato)
- `cogs/music/player.py`: `/play|skip|stop|pause|resume|queue|
  volume|disconnect`, avanzamento automatico della coda su
  `on_wavelink_track_end`

**BUG SERIO trovato con un test diretto, non ipotizzato**:
`wavelink.Pool.connect()` NON fallisce rapidamente se un nodo è
irraggiungibile — ritenta all'infinito al proprio interno e la
`await` non ritorna mai, né solleva. Un `try/except` attorno a un
`await` diretto in `setup()` sarebbe stato inutile e avrebbe
bloccato l'INTERO avvio del bot (`load_all_cogs` aspetta ogni
`setup()` in sequenza) se Lavalink fosse anche solo temporaneamente
irraggiungibile. Corretto lanciando la connessione come task in
background (`asyncio.create_task`) — `setup()` ritorna subito.

**Bug di test trovato**: `discord.Member.voice` è una property di
sola lettura che legge da `self.guild._voice_state_for(...)` —
assegnare `self.voice` direttamente in un fake fallisce ("property
has no setter"). Corretto sovrascrivendo la property nella
sottoclasse finta.

**Limite dichiarato esplicitamente nel codice**: non è possibile
testare in questo ambiente una connessione vera a Lavalink né al
gateway voce di Discord. Testato quello che è verificabile senza
(controlli di guardia, logica pura). **5 test** (1 smoke + 4 sui
controlli di guardia reali, contro PostgreSQL vero).

**Stato onesto in SPEC.md**: nessuna voce di §9 marcata come fatta —
lo schema originale descrive un'architettura multi-istanza (5
MUSIC_TOKENS, tabella `music_sessions`) molto più ampia di un player
singolo, e questo progetto non usa spunte parziali. **Bug di
conteggio trovato nella stessa scrittura**: la nota di stato
conteneva letteralmente la stringa `[x]` in un punto di prosa, contata
per errore dallo script meccanico (+1 fatto). Notato verificando il
totale invece di fidarmi, corretto.

`.env.example` documenta `LAVALINK_NODES` con link all'elenco nodi
pubblici e l'avviso di controllare che siano ancora attivi.

**Suite di test completa: 836/836 passano.**

### Fase 36 — Audit SPEC.md + correzioni richieste dall'utente
L'utente ha notato correttamente che il marcatore parziale (`~`,
definito nella legenda fin dall'inizio) non era MAI stato usato in
tutto il documento, e ha chiesto un audit per trovare altre voci
marcate come completamente fatte quando non lo erano.

**Trovato e corretto**: §9.4, §9.5 (Music: comandi e sorgenti) e
§10.8 (Custom RSS/webhook) erano marcate `[x]`/lasciate vuote con
nota prosa quando in realtà erano parziali — usato il marcatore `~`
per la prima volta, con il dettaglio esplicito di cosa manca in
ciascuna.

**Audit a campione** su §5 (7 azioni di moderazione), §6 (merge a
tre vie delle badwords — confermato genuinamente a tre vie, non due:
esistente in Discord, ultimo sync di iYokai, nuovo desiderato), §12
(6 azioni di gestione canale vocale), §13 (6 sottocomandi ticket), §15
(XP testuale+vocale, 4 comandi economy) — tutti confermati reali nel
codice, nessun altro caso trovato nel campione controllato.

**Bug di conteggio trovato DUE VOLTE nella stessa sessione, stesso
schema esatto**: la nota di correzione stessa conteneva il pattern
letterale del marcatore "tutto fatto" scritto in prosa esplicativa —
lo script meccanico di conteggio non distingue una spunta vera da
una menzione testuale dello stesso pattern. Notato entrambe le volte
verificando che il totale tornasse a 268 invece di fidarmi a mente.

Tabella ricalcolata: **115 fatte, 3 parziali (mai contate prima), 150
mancanti su 268** — circa il 43%, la colonna Parziale esisteva dalla
prima versione della tabella ma era sempre rimasta a zero.

### Fase 36 (continua) — Fix volume Music, chiarimenti sulla portata reale
**Volume**: corretto da 0-150 (numero inventato da me) a 0-200 (la
scala reale di Discord). Aggiunti comandi rapidi `/volume up`/`/volume
down` oltre a `/volume set <valore>` — l'utente ha specificato che
sono i comandi musicali più usati davvero dalla gente, insieme a
play/skip/stop. **Confermato esplicitamente: NESSUN filtro audio**
(bassboost, nightcore, ecc.) — il bot non deve appesantirsi per una
funzionalità usata raramente.

**Chiarimento importante sull'architettura multi-istanza (§9.1/9.2/
9.3), da tenere presente per quando ci si torna**: non è "5 bot per
capacità" come avevo assunto — sono due cose DISTINTE:
1. Il **bot principale** (`YOKAI_BOT_TOKEN`) deve trasmettere **24/7
   in streaming dalla playlist PERSONALE dell'utente** (canzoni
   proprie, create da lui) — una specie di modalità radio sempre
   accesa, indipendente dai comandi normali
2. Le **5 istanze separate** (`MUSIC_TOKENS`, già dichiarati in
   config.py, mai usati) sono i music bot "normali" che i membri dei
   server richiamano con i comandi standard (play/skip/ecc.) — 5
   processi separati per permettere sessioni musicali simultanee in
   canali diversi, dato che un singolo bot può stare in un solo
   canale vocale per server alla volta

**Chiarimento sulla portata reale di Alert & Social**: la richiesta
originale dell'utente copriva Twitch, YouTube, TikTok, Instagram,
Reddit, X/Twitter, PIÙ la possibilità di feed generici per notizie
da un sito qualsiasi — non solo YouTube/Reddit/RSS generico come
avevo interpretato. TikTok (già segnalato come "scraping fragile,
nessuna API ufficiale" nello schema) e Instagram (già scartato ✗,
nessuna API per account di terzi) restano vincoli tecnici REALI, non
pigrizia — X/Twitter ha un'API a pagamento per la lettura (il tier
gratuito non permette di leggere i post di terzi in modo utilizzabile
per il monitoraggio) — da discutere con l'utente come procedere per
queste tre piattaforme prima di costruire qualcosa di fragile o a
pagamento senza il suo consenso esplicito.

**Suite di test completa: 839/839 passano.**

### Fase 37 — Music multi-istanza, cablaggio completo (SPEC.md §9.1/9.2/9.3/9.10/9.11/9.12)
L'utente ha chiarito l'architettura richiesta, correggendo
un'assunzione sbagliata fatta in precedenza: NON "5 bot per
capacità" — il bot principale trasmette 24/7 SOLO dalla playlist
personale dell'utente (non entra mai in vocale per /play), le 5
istanze separate sono i music bot "normali" richiamati dagli utenti
con i comandi standard, instradati automaticamente verso quella
libera per prima. Un solo punto di ingresso comandi (il bot
principale), esecuzione distribuita su 5 processi Discord separati.

**Ricerca Lavalink** fatta come richiesto: 5 nodi pubblici gratuiti
attualmente documentati (HeavenCloud × 4 regioni con supporto
Spotify/Apple Music/Deezer, più Serenetia) inclusi ORA di default nel
codice (`DEFAULT_PUBLIC_LAVALINK_NODES` in `core/music_logic.py`) —
Music funziona senza configurazione. Ordine esatto richiesto: pubblici
in cascata per primi, nodo locale/self-hostato dell'utente sempre per
ultimo. 2 nuovi test, incluso un bug trovato: `wavelink.Node()`
richiede un event loop attivo anche solo per essere costruito.

**Fondazione dell'instradamento**: `core/music_fleet_logic.py`
(logica pura, `find_free_worker()`) + `core/repositories/music_
session_repo.py` (tabella `music_sessions` PERSISTENTE, esattamente
quella prevista dallo schema originale §9.2) + `core/music_fleet.py`
(`MusicFleet`, coordina i 6 bot — `get_worker_for_guild()` sola
lettura per i comandi che agiscono su una sessione esistente,
`get_or_assign_worker_for_guild()` usato SOLO da /play).

**DECISIONE ARCHITETTURALE**, in contrasto con un commento
precedente in main.py ("i bot music hanno il proprio entry point
separato"): 6 client Discord concorrenti nello STESSO processo
(`asyncio.gather()` in `main()`), non 6 processi separati — l'utente
ha chiarito che il routing deve essere istantaneo (chiamata Python
diretta), non tramite comunicazione tra processi. Coerente con
l'attenzione alle risorse di questo progetto fin dall'inizio (6
processi avrebbero moltiplicato per 6 l'overhead di interprete).

**Scoperta importante verificata nel sorgente di wavelink prima di
scrivere codice**: `player._auto_play_event()` viene chiamato
DIRETTAMENTE da `wavelink/websocket.py` come metodo Python sul
player, non tramite il sistema di listener di discord.py — basta
`player.autoplay = AutoPlayMode.partial` alla creazione, funziona
correttamente per ogni player su ognuno dei 6 bot senza bisogno di
un listener `on_wavelink_track_end` duplicato 6 volte (come avrei
dovuto fare altrimenti, e come era nella versione precedente a
singola istanza).

**`cogs/music/player.py` riscritto per intero**: tutti i comandi
tranne `/nonstop-main` instradano tramite `_get_worker_guild()`. Il
volume ha ora scala Discord 0-200 (era 0-150, sbagliato) con `/volume
up`/`/volume down` oltre a `set` — richiesta esplicita dell'utente,
sono i comandi usati davvero. **Nessun filtro audio** — confermato
esplicitamente non voluto ("non voglio appesantire il bot per
niente"). `/nonstop on|off` (loop continuo sul worker attivo),
`/nonstop-main start|stop` (radio 24/7 del bot principale — nome
scelto perché "24/7" letterale non è un nome valido per uno slash
command Discord: niente cifre iniziali, niente barre).

**19 nuovi test**: `MusicFleet` contro PostgreSQL reale (routing
vero), instradamento del cog con bot/flotta finti (nessuna sessione
fallisce pulito, tutti i worker occupati avvisa, worker non invitato
avvisa, disconnect rilascia davvero il worker), smoke test del
worker bot. Due bug di test trovati scrivendo questi stessi test:
`_FakeResponse` mancava `defer()`/`followup` (nuovi nel flusso di
`/play`), `followup` va su `interaction` non su `interaction.
response` (errore mio, corretto subito).

**SPEC.md**: §9.1/9.2/9.3/9.12 marcate fatte. §9.4/9.5/9.10/9.11
parziali con dettaglio esplicito. §9.6/9.7/9.8 (filtri, DJ role,
voteskip) marcate SCARTATE (non mancanti) — rifiutate esplicitamente
dall'utente, stesso trattamento di Instagram e Howgay: un limite di
scelta, non tecnico. Tabella ricalcolata con lo script meccanico:
119 fatte, 5 parziali, 141 mancanti su 265 (268 meno le 3 scartate)
— circa il 45%.

**Resta aperto per il futuro**:
- Auto-leave su canale vuoto (§9.9): l'evento `wavelink_inactive_
  player` esiste già di default in wavelink, manca solo un listener
  che disconnette e rilascia il worker nella flotta quando scatta
- "Singolo decoder condiviso" per `/nonstop-main` (§9.11): costruito
  per un server alla volta (il bot principale entra in un solo
  canale vocale) — dubbio da chiarire con l'utente se intendeva
  trasmettere la STESSA playlist a PIÙ server contemporaneamente

**Suite di test completa: 873/873 passano.**

### Fase 38 — Twitch live/offline con credenziali fittizie (SPEC.md §10.1/10.2), chiude Twitch/TikTok/X

L'utente ha chiesto esplicitamente di costruire Twitch ORA con
credenziali segnaposto, sue vere più avanti dopo la registrazione su
dev.twitch.tv — e ha confermato TikTok/Instagram/X come vincoli
tecnici accettati (nessuna API gratuita di lettura), non pigrizia.

- `core/config.py`: `TWITCH_CLIENT_ID`/`TWITCH_CLIENT_SECRET`
  opzionali (default vuoto — il watcher resta inattivo se non
  compilati, non blocca l'avvio del bot)
- `core/twitch_api_logic.py`: `parse_get_streams_response()` —
  l'API "Get Streams" di Twitch restituisce SOLO chi è live in
  questo momento, non un "offline" esplicito; il chiamante passa la
  lista completa dei login richiesti e ogni assente viene marcato
  offline qui. `parse_app_access_token_response()` per l'OAuth
  Client Credentials. **9 test**
- `core/repositories/twitch_subscription_repo.py`: una riga per
  streamer, `last_known_live` invece di `last_seen_entry_id` (Twitch
  non è sequenziale come un feed RSS). **6 test** contro PostgreSQL
  reale
- `core/twitch_watcher.py`: stesso pattern di `feed_watcher.py`.
  Gestisce da solo il token OAuth (lo richiede alla prima chiamata,
  lo rinnova prima che scada con un margine di sicurezza). Una
  chiamata batch per TUTTI i login sottoscritti (fino a 100 per
  richiesta secondo i limiti Twitch), non una per sottoscrizione.
  Tick ogni 90s (più frequente del feed watcher: "live ora" vale di
  più notificato in fretta). URL di base passabili al costruttore,
  per puntare i test a un server locale finto invece che a Twitch
  vero. **5 test con un server aiohttp VERO in locale** che imita la
  forma dell'API (OAuth + Get Streams), credenziali fittizie come
  richiesto — incluso un test che verifica il RIUSO del token tra
  due tick (non richiesto due volte)
- `cogs/utility/feed_alerts.py`: `/alerts add-twitch`.

**BUG REALE trovato e corretto prima che arrivasse in produzione**:
gli ID di `feed_subscriptions` e `twitch_subscriptions` sono due
sequenze SEPARATE nel database — potevano collidere (`#1` di uno e
`#1` dell'altro), rendendo `/alerts remove` ambiguo su quale
sottoscrizione toccare. Corretto con prefissi nell'ID visibile
(`RSS-3`, `TW-2`), `remove` ora instrada verso il repository giusto
in base al prefisso. **7 test** aggiornati/aggiunti nel cog.

**SPEC.md**: §10.1/10.2 marcate fatte. §10.5 TikTok passato da
mancante a **scartato** (confermato dall'utente come vincolo
accettato). §10.13 X/Twitter — **voce nuova**, non nello schema
originale, aggiunta su richiesta esplicita e subito marcata
scartata (lettura a pagamento nel tier utile). Tabella ricalcolata
con lo script meccanico: 121 fatte, 5 parziali, 138 mancanti su 264
— circa il 46%.

**Domanda dell'utente su token veri**: ha chiesto se sarebbe più
comodo dargli accesso diretto a token Discord/Twitch/Lavalink reali
per test in tempo reale. Risposta data: no — limite tecnico concreto
di questo ambiente, l'accesso di rete del sandbox è ristretto a un
elenco fisso di domini (PyPI, npm, GitHub) che NON include Discord/
Twitch/Lavalink, quindi non potrei comunque connettermi anche con
credenziali vere. Il workflow utile resta: lui distribuisce con
token veri, testa dal vivo sul suo server, riporta log/errori
specifici — quello è il riscontro che il sandbox non può dare da
solo.

**Suite di test completa: 896/896 passano.**

### Fase 39 — Radio condivisa /nonstop-main, chiude SPEC.md §9.11

L'utente ha chiarito in dettaglio cosa intendeva con "singolo
decoder condiviso": una radio VERAMENTE condivisa tra server — non
riproduzioni indipendenti per server, un solo stato di riproduzione
che ogni server legge. Sorgenti: le sue pubblicazioni su piattaforme
più una cartella locale per gli inediti (di cui detiene i diritti),
interlacciate nell'ordine dell'album. Una volta avviata resta attiva
finché non fermata, e un server che si aggancia entra esattamente
nel punto in cui sono già gli altri, non riparte da capo.

Prima di progettare: verificato con una ricerca che Lavalink supporta
file locali nativamente (`local:` come sorgente), MA solo se è il
nodo Lavalink stesso ad avere accesso al filesystem — i nodi
pubblici non possono mai leggere una cartella sulla VM dell'utente.
Questo ha determinato il design: i file locali vanno instradati
SPECIFICAMENTE verso il nodo locale/self-hostato.

- `core/main_radio_logic.py`: `compute_current_position()` — l'idea
  centrale è un "orologio" che avanza col tempo reale trascorso,
  indipendentemente da quanti server sono collegati in un dato
  momento, come una vera stazione radio che trasmette anche se
  nessuno ascolta. Attraversa in avanti le tracce (con loop sulla
  playlist) finché il tempo trascorso dal riferimento non è
  "consumato" dalla durata delle tracce percorse — un server che si
  aggancia dopo ore calcola subito la traccia e la posizione giuste,
  anche attraversando più tracce. Casi limite gestiti: orologio nel
  futuro, durata zero (limite di sicurezza sul numero di giri).
  **12 test**, incluso il caso di attraversamento multiplo con loop
- `core/repositories/main_radio_repo.py`: `main_radio_tracks`
  (playlist ordinata, curata dall'utente) + `main_radio_state` (riga
  SINGOLA — la radio è una sola, condivisa). **7 test** contro
  PostgreSQL reale
- `cogs/music/player.py` riscritto: `/nonstop-main add-track|
  add-local|remove-track|list-tracks|start|stop`. `start()` legge lo
  stato condiviso (o lo crea, se primo avvio in assoluto), calcola
  dove dovrebbe essere la riproduzione ORA, risolve quella traccia e
  joina seekando esattamente lì (`player.play(track, start=
  elapsed_ms)` — verificato che wavelink lo supporta prima di
  progettare tutto questo). Costruisce la coda col resto della
  playlist in rotazione con loop. `add-local` instrada
  specificamente verso `LOCAL_NODE_IDENTIFIER` (identificatore fisso
  assegnato al nodo locale in `_build_lavalink_nodes`). `stop()` NON
  tocca lo stato condiviso — la radio continua a "trasmettere"
  concettualmente anche se un server esce, come una vera radio non
  si ferma solo perché un ascoltatore la spegne
- `core/config.py`: `MAIN_RADIO_LOCAL_FOLDER` opzionale

**8 nuovi test** sul comportamento reale, contro PostgreSQL vero,
con player finti (connessione Lavalink/voce vera impossibile in
questo ambiente). Il più importante: un SECONDO server che si
aggancia 90 secondi dopo l'inizio riceve la posizione calcolata
correttamente (~90000ms dentro la prima traccia), non riparte da
zero — verifica end-to-end del comportamento centrale richiesto.

**Bug di test trovato**: `discord.Member.id` è una property di sola
lettura (stesso problema già visto con `.voice`) — risolto
sovrascrivendola nella sottoclasse finta invece di assegnarla
direttamente.

**SPEC.md**: §9.11 marcata fatta, con spiegazione di come "condiviso"
è stato ottenuto (orologio logico, non un decode fisicamente
multicast — impossibile con l'architettura Lavalink, ma stesso
risultato percepito dall'ascoltatore). §9.5 aggiornata: file locali
ora genuinamente fatti. Tabella ricalcolata: 122 fatte, 4 parziali,
138 mancanti su 264 — circa il 46%.

**Suite di test completa: 923/923 passano.**

### Fase 40 — Auto-leave chiude Music, inizio Backup System (SPEC.md §9.9, §11.3-11.8)

**Music §9.9**: `core/music_fleet.handle_inactive_player()` reagisce
all'evento `wavelink_inactive_player` (il timeout, 300s di default,
era già gestito internamente da wavelink) — disconnette e libera il
worker nella flotta. Agganciato IDENTICAMENTE su tutti e 6 i bot
(main + 5 worker) in `main.py`, dato che i worker non caricano cog e
il listener va registrato direttamente con `add_listener()`. 2 test.
**§9 Music non ha più nessuna voce davvero mancante.**

**Backup System, prima volta toccato**: cominciato dalla clonazione
vera e propria (§11.3-11.8, `core/backup_clone_logic.py`), la base
riusabile indipendentemente da come funzionerà l'orchestrazione
completa. Verificate tutte le firme reali dell'API discord.py prima
di scrivere codice (create_role, create_category, create_text_
channel, create_voice_channel, create_custom_emoji, create_sticker,
create_webhook, create_soundboard_sound).

`clone_roles()`: salta @everyone (Discord non permette di crearne un
secondo) e i ruoli "managed". **Correzione dell'utente**: @everyone
non va solo saltato — i suoi PERMESSI vanno comunque applicati al
default_role del server di destinazione, perché l'amministratore
originale potrebbe averli personalizzati rispetto al default di
Discord. Corretto: `target_guild.default_role.edit(permissions=...)`
esplicito, con la mappatura inclusa nel dizionario restituito.

`clone_categories_and_channels()`: categorie create prima dei
canali (un canale ha bisogno dell'oggetto categoria già esistente
lato destinazione), overwrite di permessi rimappati tramite la
mappa ruoli — solo quelli per RUOLO, quelli per singolo utente
vengono saltati (nessun membro esiste ancora in un server appena
clonato).

`clone_emoji()`/`clone_stickers()`/`clone_soundboard()`: scaricano
il contenuto dal server originale (`.read()`, via CDN Discord) e lo
ricaricano nel server di destinazione. **Bug reale trovato con un
test diretto PRIMA di scrivere il codice dei test**: `discord.File`
non accetta bytes grezzi nonostante il type hint lo suggerisca —
tratta bytes come un PERCORSO FILE (`open(fp, 'rb')`), non come
contenuto, sollevando `FileNotFoundError`. Corretto avvolgendo
sempre in `io.BytesIO` prima di passarlo a `discord.File`.

`clone_webhooks()`: solo nome e canale rimappato — l'URL di un
webhook è univoco per ogni webhook creato, non copiabile.

**Bug di test trovato scrivendo i test dei ruoli**: `remap_
permission_overwrites()` usa `isinstance(..., discord.Role)` — un
fake che non eredita davvero da `discord.Role` non lo supererebbe
mai. Verificato con uno spike quali attributi sono property di sola
lettura (`permissions`/`colour` sì, leggono da `_permissions`/
`_colour` interni; `id`/`name`/`position`/`hoist`/`mentionable`/
`managed` no, assegnabili direttamente) prima di scrivere il fake
completo. Stesso lavoro ripetuto per `category`/`overwrites` sui
canali (property in `discord.abc.GuildChannel`, sovrascritte nei
fake).

**29 nuovi test totali** tra i 4 file di test creati, tutti passati
al primo colpo dopo la verifica delle firme reali (segno che la
disciplina di verificare prima di scrivere ha ripagato).

**SPEC.md**: §11.3-11.8 marcate fatte. §11 non è più a zero.
Tabella ricalcolata: 129 fatte, 4 parziali, 131 mancanti su 264 —
circa il 49%.

**Suite di test completa: 946/946 passano.**

### Fase 41 — Orchestrazione completa del Backup System (SPEC.md §11.1, §11.2, §11.12)

L'utente ha lasciato la priorità a discrezione ("tanto si deve
fare") — completata l'intera orchestrazione automatizzabile,
lasciando deliberatamente rimandate solo le parti con vere
implicazioni architetturali/di sicurezza (mirror messaggi, OAuth2).

**Fondazione**: `core/repositories/backup_repo.py` — `backup_pairs`
(quale server è "main", quale il suo "backup" designato) +
`backup_jobs` (coda SERIALIZZATA con timeout 24h, come richiesto
esplicitamente — `expire_stale_jobs()` scade sia i job pending sia
running rimasti bloccati, verificato retrodatando manualmente una
riga nel test, dato che `enqueue_job()` usa sempre `now()`).
`set_backup_guild_id()` impostato SUBITO dopo la creazione del
server, non solo a completamento, così il listener di Main può già
trovare il job giusto quando arriva quel momento. **15+4 test**.

**Orchestratore** (`core/backup_orchestrator.py`) — **limite reale
della piattaforma Discord verificato con una ricerca PRIMA di
progettare**: un bot non può autoinvitarsi in un server, serve
sempre che una persona clicchi il link di autorizzazione OAuth. Non
aggirabile dal codice, quindi il flusso è diviso in due fasi:
- `start_backup_job()`: Creator crea il server, clona tutto quello
  che si può (riusando tutte le funzioni di clonazione della fase
  precedente), genera l'URL di invito con `discord.utils.oauth_url()`
  (verificato che discord.py lo offre già, non serve costruirlo a
  mano) — guild pre-selezionato, `disable_guild_select` così l'admin
  non può sbagliare server
- `finalize_backup_job()`: chiamata dal listener `on_guild_join` di
  Main quando entra in un server che risulta essere il backup atteso
  di un job in corso — trasferisce la proprietà da Creator a Main e
  fa uscire Creator, così resta sotto il limite di 10 server
**4 test**.

**Bot Creator** (`core/backup_creator_bot.py`) — minimale, nessun
comando proprio, usa `YOKAI_CREATOR_TOKEN` (già dichiarato in
config.py da prima di questa sessione, mai usato finora).

**Worker della coda** (`core/backup_queue_worker.py`) — stesso
pattern di `feed_watcher.py`/`twitch_watcher.py`. Tick ogni 60s: un
job alla volta (coda serializzata), notifica l'amministratore del
server principale via DM con l'URL da cliccare — un link che
crea/trasferisce un intero server merita un messaggio privato, non
un post in un canale qualsiasi. Un fallimento marca il job fallito
con il messaggio d'errore, non fa fallire il worker. **6 test**,
incluso la verifica che UN SOLO job venga elaborato per tick anche
con più in coda.

**Collegamento in main.py**: `on_guild_join` di iYokai Main consulta
`finalize_backup_job()` PRIMA del controllo blacklist e del
trattamento normale — un server atteso da un job non riceve nessuna
riga di configurazione né messaggio di benvenuto, non è un server
"nuovo" per un utente qualsiasi, è un artefatto interno
dell'orchestrazione. Creator avviato insieme a tutto il resto
(`asyncio.gather`), `bot.backup_creator_client` impostato PRIMA di
`bot.start()`. Permessi richiesti a Main in un backup: Administrator
(un server di backup esiste apposta per essere gestito completamente
dal bot). **1 test end-to-end** contro PostgreSQL reale.

**Comandi** (`cogs/utility/backup.py`): `/define-main` e
`/define-backup`, con i nomi ESATTI richiesti dallo schema, non
raggruppati. `/restore-users` NON costruito — dipende da OAuth2
(§11.11), rimandato con essa. **4 test**.

**SPEC.md**: §11.1/§11.2 marcate fatte, §11.12 parziale (i due
comandi fatti, `/restore-users` no). Tabella ricalcolata: 131 fatte,
5 parziali, 128 mancanti su 264 — **circa il 50% dello schema**,
traguardo raggiunto in questa fase.

**Resta deliberatamente rimandato**, da discutere con l'utente prima
di scrivere codice:
- §11.9 Mirror messaggi in tempo reale via webhook con identità
  utente (impersonare l'autore originale — impatto notevole, ogni
  messaggio del server sorgente rilanciato in tempo reale)
- §11.10/§11.11 Backup e restore utenti via OAuth2 `guilds.join` —
  tema di sicurezza reale: storage di token OAuth di terzi, per
  quanto tempo, quali garanzie dare agli utenti
- §11.13 Auto-propagazione (backup diventa main → crea nuovo backup)
  — piccola estensione naturale una volta chiarito il resto

**Suite di test completa: 980/980 passano.**

### Fase 42 — Promemoria di scadenza + controllo capacità Creator (richiesta esplicita dell'utente)

L'utente ha chiesto se automatizzare l'auto-join dei bot con un
account secondario/selfbot fosse possibile — risposto di no
(contro i Termini di Servizio di Discord, rischio di ban per un
guadagno piccolo: il click serve una volta sola per backup, non è
un attrito ricorrente). Ha accettato e chiesto invece un sistema di
promemoria: countdown prima che un job in attesa del click venga
annullato, avviso quando tutti gli slot di Creator (max 10 server)
sono occupati.

`core/backup_reminder_logic.py`: `should_send_timeout_reminder()`
(un solo promemoria per job, quando restano meno di 2 ore alla
scadenza — non uno ad ogni tick, altrimenti spammerebbe ogni 60
secondi per ore), `format_time_remaining()` (countdown leggibile,
"1h 45m"), `format_slot_wait_message()` — **non** una stima precisa
di quando si libererà uno slot (impossibile saperlo con certezza,
dipende da quando altri amministratori cliccano i loro link), ma un
limite massimo ONESTO: ogni slot si libera entro 24h al più tardi
(i job scadono da soli). **10 test**.

`core/repositories/backup_repo.py`: colonna `reminder_sent_at`
aggiunta con `ALTER TABLE ADD COLUMN IF NOT EXISTS` — **primo caso
in questo progetto di estendere una tabella già esistente** invece
di crearne una nuova, verificato che funzioni anche sulla tabella
già popolata dalle fasi precedenti. `get_running_jobs()`,
`mark_reminder_sent()`. Un solo promemoria per job in totale (slot
pieno O scadenza vicina, quale arriva prima) invece di due contatori
separati. **Bug di sintassi trovato**: un commento SQL scritto con
`#` invece di `--` (sintassi Python, non SQL). **11 test**.

`core/backup_queue_worker.py` riscritto: `_controlla_promemoria_
scadenza()` ad ogni tick controlla i job RUNNING e manda il DM con
countdown quando serve. `tick()` ora controlla `len(creator_client.
guilds)` PRIMA di provare a creare un nuovo server — se Creator è
già al limite, non tenta la creazione, aspetta che uno slot si
liberi, avvisa l'amministratore in attesa una sola volta.
`_manda_dm()` estratta come metodo condiviso da tutti e tre i tipi
di notifica. **4 nuovi test**, incluso il countdown verificato per
davvero retrodatando `created_at` (stesso trucco già usato per
`expire_stale_jobs`), e la verifica che l'avviso di slot pieni non
si ripeta ad ogni tick.

**Suite di test completa: 997/997 passano.**

### Fase 43 — §15.12/15.13, primo pezzo di Levels/Gilde (1000 test raggiunti)

**§15.12 Notifica level-up vocale**: il repository calcolava già
tutto (`VoiceMinuteGrant.leveled_up`/`new_level` esistevano già),
mancava solo usarlo nel cog — il commento esistente spiegava perché
era stato lasciato così ("un task periodico su più server non ha un
canale testuale ovvio a cui scrivere"). Verificato prima di
scrivere codice: `discord.VoiceChannel` eredita da `Messageable` (i
canali vocali moderni hanno la propria chat integrata) — la
notifica va quindi nel canale vocale stesso. **3 test**, incluso un
bug di test trovato: il costruttore del cog avvia subito il task
periodico, serve una fixture ASINCRONA (non sincrona) per avere un
event loop attivo. **Traguardo: 1000/1000 test raggiunto.**

**§15.13 Ruoli-premio per livello**: `core/repositories/level_
reward_repo.py`, CUMULATIVO (ogni ruolo fino al nuovo livello, non
solo il più alto — coerente con l'aspettativa comune, i badge più
vecchi restano). Collegato sia a XP testuale che vocale tramite un
metodo condiviso `_grant_level_rewards()`. Comandi `/level-roles
add|remove|list`. **21 test totali** tra repository, collegamento
nel cog, e comandi.

**SPEC.md**: §15.12/15.13 marcate fatte. Tabella ricalcolata: 133
fatte, 5 parziali, 126 mancanti su 264 — circa il 50%.

**Prossimo in §15**: 15.11 (annuncio automatico vincitori, usa
infrastruttura già esistente), 15.4 (shop), 15.6 (drop messages),
15.5 (giveaway) — tutti buildable senza discussione preventiva.
**15.14 Sistema Gilde/Clan** resta la sottosezione enorme con la
sua economia interna (tesoreria, acquisto canali, boost),
dimensione paragonabile a Backup System — da trattare con la stessa
cura quando ci si arriva.

**Suite di test completa: 1013/1013 passano.**

### Fase 44 — Annuncio automatico dei vincitori a fine mese (SPEC.md §15.11)

`core/monthly_winners_logic.py` (logica pura: mese precedente con
passaggio d'anno, idempotenza, podio con testo esplicito se nessuno
ha partecipato) + `core/repositories/monthly_winners_repo.py` (canale
per server + `last_announced_period`) + `core/monthly_winners_
announcer.py` (tick orario avviato in main.py) + `/monthly-winners
set|disable`. `MEDALS` estratta come costante condivisa, ora usata
anche da `/leaderboard` al posto della sua lista inline.

Scelte deliberate: alla prima configurazione il mese appena passato
viene segnato come già coperto (nessun annuncio retroattivo a
sorpresa); canale sparito → periodo segnato comunque (niente
tentativi ogni ora per un mese); errore di invio transitorio →
periodo NON segnato (riprova al tick successivo).

**29 nuovi test**, incluso il podio verificato contro righe
`leveling_activity` vere nel database (l'attività del mese sbagliato
resta esclusa). SPEC.md e COMMAND_LIST.md aggiornati nello stesso
commit del codice. **51% dello schema (134/264).**

**Suite di test completa: 1042/1042 passano.**

### Fase 45 — Shop, "un posto dove spendere i coin" (SPEC.md §15.4)

`LevelingRepository.spend_coins()` — stesso pattern atomico (FOR
UPDATE dentro una transazione) di `transfer_coins()` già esistente,
mai un saldo negativo. `core/repositories/shop_repo.py`: oggetti con
prezzo e un ruolo OPZIONALE da concedere — senza ruolo l'oggetto
resta decorativo, un "pozzo" legittimo per i coin. `has_purchased()`
evita di far ricomprare un ruolo già posseduto. `/shop list|buy|
add-item|remove-item`.

**21 nuovi test**, incluso il comportamento reale contro Postgres:
saldo insufficiente non sottrae nulla, un secondo acquisto dello
stesso ruolo viene rifiutato senza toccare il saldo. SPEC.md e
COMMAND_LIST.md aggiornati nello stesso commit. **51% (135/264).**

**Suite di test completa: 1063/1063 passano.**

### Fase 46 — Drop di coin nei messaggi (SPEC.md §15.6)

`core/drop_logic.py`: `should_trigger_drop()` puramente
deterministica (il chiamante estrae `random.random()` e lo passa già
pronto). Agganciato in `on_message` del cog leveling: 0.5% di
probabilità per messaggio idoneo, un `DropClaimView` con pulsante
"primo che clicca vince" — stato in memoria, non persistito.

**Bug di test trovato scrivendo i test**: il decoratore
`@discord.ui.button()` sostituisce l'attributo sull'ISTANZA della
view con l'oggetto `Button` vero (non più la funzione originale) —
il callback si invoca tramite `view.children[0].callback(interazione)`,
non chiamando il metodo decorato direttamente. Verificato con uno
spike prima di scrivere i test completi. Un secondo bug di test:
`on_message` controlla `db.is_module_active_for_guild` sul singleton
globale `db`, mai sostituito nella prima versione della fixture.

8 nuovi test totali. SPEC.md aggiornata nello stesso commit. **52%
dello schema (136/264).**

**Suite di test completa: 1071/1071 passano.**

### Fase 47 — Giveaway con requisiti (SPEC.md §15.5), ultimo pezzo prima delle Gilde

`core/giveaway_logic.py`: `pick_winners()` con `random.Random`
iniettato (deterministico e testabile), `is_eligible()` richiede
ENTRAMBI i requisiti insieme quando configurati (livello E ruolo).
`core/repositories/giveaway_repo.py`: partecipazioni PERSISTITE (un
giveaway dura ore o giorni, deve sopravvivere a un riavvio) —
diverso dai drop effimeri. `core/giveaway_worker.py`: stesso pattern
di feed_watcher/monthly_winners, tick ogni 30s.

`GiveawayEnterView` in leveling.py: PERSISTENTE (`timeout=None`,
custom_id fisso con l'ID del giveaway incorporato) — verificato con
uno spike PRIMA di scrivere il codice reale che impostare custom_id
dinamicamente in `__init__` funziona davvero (il decoratore
`@discord.ui.button()` sostituisce l'attributo sull'istanza con
l'oggetto Button vero). main.py ri-registra la view per ogni
giveaway ancora attivo ad ogni avvio (`get_active_giveaways()`,
scelto al posto di riusare `get_due_giveaways` con un
`datetime.max` come stavo per fare — più chiaro).

**Bug di test reale trovato eseguendo l'intera suite** (non nei
singoli file, che passavano isolati): le fixture di due file
puliscono solo alla FINE, non all'inizio — una riga residua lasciata
dall'ultimo test di un altro file (che usa `clean_db`, il quale
svuota solo all'inizio di OGNI SUO test, non alla fine dell'intero
file) restava visibile e falsava un conteggio. Corretto pulendo
anche all'inizio.

**24 nuovi test.** SPEC.md e COMMAND_LIST.md aggiornati nello stesso
commit. **52% dello schema (137/264).**

**Suite di test completa: 1101/1101 passano.**

---

### Fase 48 — Motore economico Gilde/Clan (SPEC.md §15.14, backend
completo) + prima pietra del decadimento personale (§15.15, nuovo)

**Nota di processo**: le 4 commit precedenti a questa Fase
(`fd1951f` repository clan/membri/tesoreria, `131e89c` repository
attività vocale, `0008877` XP di gilda e classifica, `c97dd52`
worker vocale) erano state fatte e pushate ma SPEC.md/PROGRESS.md
non erano stati aggiornati di conseguenza — debito di
documentazione, sanato qui in un colpo insieme al lavoro nuovo.

**Cosa esiste ora per §15.14** (tutto testato, nessun comando
Discord ancora): `core/guild_clan_logic.py` (tick 30 XP + 2 coin/min,
decadimento lineare dopo 3h filate nello stesso vocale, tetto
720 tick/giorno, deficit di creazione 15.000 coin/24h, costi canale
25k/50k/200k/800k, validazione tag CJK-aware senza emoji);
`core/repositories/guild_clan_repo.py` (clan, membri, tesoreria con
ledger, XP/classifica, decadimento mensile 10% — resa ATOMICA
calcolando il decadimento dentro il metodo stesso sotto `FOR UPDATE`
invece di accettare un saldo pre-calcolato dal chiamante, per non
perdere una donazione/spesa concorrente); `clan_voice_activity_repo.py`
+ `guild_clan_voice_worker.py` (tick al minuto per membri in vocale
di gilda, salta bot e clan non ufficializzati); `guild_clan_treasury_decay_worker.py`
(decadimento mensile, idempotente via `clans.last_decay_period`).
Calibrazione XP/coin verificata con un test che SIMULA l'intero tick
loop (720 tick/giorno × 30 giorni) invece di fidarsi del calcolo a
mente — confermato dentro il target 500-750k XP/mese, <50k coin/mese
per un utente massimamente attivo.

**Nuovo scope emerso in conversazione (§15.15, non nello schema
originale)**: l'utente ha specificato un SECONDO decadimento,
distinto da quello mensile di tesoreria — 10% **settimanale** sui
coin PERSONALI di QUALUNQUE membro del server, in un clan o no. Le
coin decadute (da entrambi i decadimenti) confluiscono in una nuova
CASSA di server, usabile per premi eventi e/o per comprare mesi di
bot premium. Premium sbloccato a doppio cancello: tempo dal join del
bot nel server (6 mesi / 1 anno / 2 anni) E costo in coin dalla
cassa, variabile per fascia membri, arrotondato in eccesso a
multipli di 25.000 (numeri esatti ancora da confermare).

Fatto in questa Fase solo il primo pezzo, la logica pura:
`week_key()` (chiave settimana ISO, stesso pattern UTC di
`period_key()`) e `apply_weekly_personal_decay()` in
`core/leveling_logic.py` — mai negativo, mai sotto 1, sempre intero
(10% di 105 → 10 o 11, mai 10,5), floor applicato PRIMA di calcolare
la sottrazione per chi ha già un saldo ≤ 1. **Ancora da fare**:
colonna di idempotenza settimanale, worker che applica il
decadimento a tutti i membri del server (non solo quelli in un
clan), tabella/repository della cassa di server, e la logica di
sblocco premium una volta confermati i numeri esatti con l'utente.

**11 nuovi test** (`TestWeekKey`, `TestApplyWeeklyPersonalDecay` in
`tests/test_leveling_logic.py`). SPEC.md aggiornato (§15.14 passa da
"tutto da fare" a parziale — motore fatto, comandi mancanti; nuovo
§15.15 aggiunto). Nessun comando slash toccato in questa Fase,
COMMAND_LIST.md non rigenerato.

**Suite di test completa: 1201/1201 passano.**

---

### Fase 49 — Worker del decadimento settimanale + cassa di server
(SPEC.md §15.15, chiude i due decadimenti)

Completato quanto lasciato aperto nella Fase 48. Tre pezzi nuovi:

**Persistenza del decadimento personale**: `leveling_totals` prende
una colonna `last_weekly_decay_period` (via `ALTER TABLE ... ADD
COLUMN IF NOT EXISTS`, idempotente su un database già esistente).
`LevelingRepository.apply_weekly_decay(guild_id, user_id, period)` —
stesso pattern di `GuildClanRepository.apply_monthly_decay`: il 10%
è calcolato DENTRO il metodo sul saldo letto sotto `FOR UPDATE`, non
passato dal chiamante, per non perdere una spesa/un guadagno
concorrente. `list_users_needing_weekly_decay(period)` seleziona
`(guild_id, user_id)` con `coins_total > 1` e periodo non ancora
coperto — chi ha già un saldo al minimo non viene nemmeno
restituito, decadere un 1 non cambia nulla.

**Cassa di server** (`core/repositories/guild_chest_repo.py`, nuovo):
tabelle `guild_chest` (saldo per guild) e `guild_chest_ledger`
(storico movimenti, stesso pattern di `clan_treasury_ledger`). Solo
`deposit()` per ora — nessun prelievo, la cassa appartiene al
server non a un singolo membro, la spesa (eventi/premium) arriverà
con i comandi Discord corrispondenti.

**Due worker collegati alla stessa cassa**: `core/weekly_personal_
decay_worker.py` (nuovo, tick orario, itera `leveling_totals`
direttamente — non serve toccare l'API Discord per i membri, il
saldo esiste già nella tabella indipendentemente da chi è online o
in un clan) deposita il delta nella cassa del server con motivo
`weekly_personal_decay`. `guild_clan_treasury_decay_worker.py`
aggiornato per fare lo stesso con motivo `monthly_clan_decay`,
usando `clan.guild_id` per sapere in quale cassa versare (un clan
ha un ID globale ma appartiene sempre a UN server). Migration di
`guild_chest_repo` agganciata sia in `core/database.py` che in
`tests/conftest.py`.

**23 nuovi test**: `TestApplyWeeklyDecay`/liste in
`test_leveling_repo.py`, `test_guild_chest_repo.py` (nuovo),
`test_weekly_personal_decay_worker.py` (nuovo, stesso pattern di
`test_guild_clan_voice_worker.py` — `Database()` dedicato +
monkeypatch dei singoli repository nel modulo del worker), più due
test aggiunti a `test_guild_clan_treasury_decay_worker.py` per la
nuova destinazione in cassa (il fixture esistente doveva comunque
essere aggiornato per monkeypatchare anche `guild_chest_repo`,
altrimenti avrebbe chiamato il pool non connesso del singleton
globale).

SPEC.md aggiornato: §15.15 passa da "solo logica pura" a completo
per decadimento + cassa (resta solo l'USO della cassa — comandi
eventi/premio e il premium a doppio cancello, in attesa dei numeri
esatti). **54% dello schema (139/270, parziali a metà peso).**

**Suite di test completa: 1224/1224 passano.**

---

### Fase 50 — Sblocco premium via cassa (SPEC.md §15.15, chiude la
sottosezione) + primo comando Discord (`/cassa`)

Numeri confermati dall'utente prima di scrivere il codice: server
sotto i 1.000 membri — 1° mese di premium (sbloccabile dopo 6 mesi
dal join del bot) 500.000 coin, 2° (dopo 1 anno) 5.000.000, 3° (dopo
2 anni) 50.000.000; ogni fascia successiva di membri (sotto i
10.000, sotto i 100.000, ...) moltiplica per 10 la fascia
precedente; ogni costo arrotondato in eccesso a multipli di 25.000.

**Logica pura** (`core/premium_pricing_logic.py`, nuovo):
`months_elapsed()` (mesi civili pieni, mai negativo), `member_count_
bracket()` (generalizza il ×10 per fascia oltre le tre confermate),
`round_up_to_step()`, `premium_tier_cost()`, `is_tier_time_unlocked()`.

**Persistenza** (due repository nuovi): `guild_chest_repo.spend()`
aggiunto (stesso pattern atomico di `LevelingRepository.spend_coins`
— mai un saldo negativo). `guild_premium_repo.py` (nuovo): quali
tier sono già stati comprati (`guild_premium_purchases`, un tier si
compra una volta sola) e la scadenza `premium_until`
(`guild_premium_status`) — ogni acquisto AGGIUNGE un mese a partire
dal massimo tra ora e la scadenza attuale, quindi mesi comprati in
momenti diversi si accumulano invece di accavallarsi.
`core.database.Database.get_guild_joined_at()` (nuovo) usa
`guild_config.created_at` come approssimazione della data di join
del bot (quella riga non viene più sovrascritta da `ensure_guild_
exists` dopo la prima volta).

**Orchestrazione** (`core/premium_purchase_service.py`, nuovo):
`purchase_premium_tier()` è l'UNICO punto che combina tempo, tier
già comprato e saldo, in quest'ordine, PRIMA di toccare la cassa —
se un controllo fallisce la cassa non viene mai scalata (verificato
esplicitamente nei test). `core/premium.py`, `guild_has_premium_
access()` ora controlla anche questo stato oltre alla whitelist
manuale dell'owner: comprare "un mese di bot premium" sblocca TUTTI
i moduli premium per la durata acquistata, non un modulo alla volta.

**Primo comando Discord per il Sistema Gilde/Clan/Economy** (finora
tutto era solo repository/worker): `/cassa saldo` (chiunque, mostra
saldo + ultimi 5 movimenti) e `/cassa sblocca-premium` ([Admin],
`manage_guild`) in `cogs/leveling/leveling.py` — stesso posto dello
`shop_group` esistente, stesso stile. COMMAND_LIST.md rigenerato
(153 comandi).

**32 nuovi test**: `test_premium_pricing_logic.py` (nuovo, 30 test
sulla logica pura), `test_guild_premium_repo.py` (nuovo),
`test_premium_purchase_service.py` (nuovo, verifica esplicitamente
che la cassa non venga toccata quando un controllo fallisce),
aggiunte a `test_guild_chest_repo.py` per `spend()`,
`test_guild_chest_cog_behavior.py` (nuovo, comandi Discord).

SPEC.md: §15.15 ORA COMPLETO (decadimento + cassa + sblocco
premium). Resta solo un comando dedicato a spendere la cassa su
premi evento (oggi si può depositare/sbloccare premium, non ancora
premiare i membri) — non urgente, la cassa esiste già e può
accumulare nel frattempo. **54% dello schema (140/270).**

Prossimo pezzo, per dimensione il più grande rimasto: i comandi
Discord del Sistema Gilde/Clan stesso (§15.14 — crea, invita,
espelli, promuovi, tesoreria, compra-canale, boost, info,
classifica, sciogli), oggi a zero comandi nonostante il motore
economico sottostante sia completo.

**Suite di test completa: 1281/1281 passano.**

---

### Fase 51 — Primi comandi Discord del Sistema Gilde/Clan (SPEC.md
§15.14): crea, info, membri, classifica, sciogli, tesoreria/dona

Fino a questa Fase il Sistema Gilde/Clan esisteva solo a livello di
repository/worker — zero comandi Discord. Primo pezzo di comandi in
`cogs/leveling/leveling.py` (stesso posto e stile di `shop_group`/
`chest_group`), gruppo `/clan`:

- **`/clan crea <tag> <name>`**: valida il tag (`validate_guild_tag`),
  rifiuta se l'utente è già in una gilda in questo server o se il
  tag è già preso, poi crea la CATEGORIA DISCORD PRIMA di scrivere
  il record nel database (stesso ordine del sistema ticket — se la
  categoria fallisce non resta un clan senza spazio reale): view
  negata a `@everyone`, concessa al fondatore e al bot. Se la
  categoria va a buon fine, `create_clan` con deficit -15.000 e
  finestra di 24h.
- **`/clan info [tag]`**, **`/clan membri [tag]`**, **`/clan
  classifica`**: consultazione, nessuna scrittura.
- **`/clan sciogli`**: solo il Capo Clan (`clan.owner_id`), elimina
  prima i canali della categoria poi la categoria stessa (best-effort,
  `discord.HTTPException` loggata ma non bloccante), poi il record.
- **`/clan tesoreria dona <importo>`**: scala il saldo PERSONALE
  (`leveling_repo.spend_coins`, fallisce senza scrivere nulla se non
  basta) e accredita la tesoreria del clan (`guild_clan_repo.donate`).
  Se il deficit di creazione risulta coperto dopo la donazione
  (`is_creation_deficit_covered`), ufficializza il clan nello stesso
  comando — nessun worker separato serve per questo, la donazione è
  già il momento giusto per controllare.

**Nuovo worker**: `core/guild_clan_expiry_worker.py` — tick orario,
elimina automaticamente i clan non ufficializzati la cui finestra di
24h (`officialize_deadline`) è scaduta: prima i canali/categoria
Discord (se esistono ancora), poi il record. Mancava dalla lista dei
pending task di sessioni precedenti — chiuso qui insieme ai comandi
perché senza di esso un clan abbandonato a metà creazione (mai
ufficializzato) sarebbe rimasto per sempre con una categoria vuota.

**Bug di test reale, non ipotizzato**: i fake `discord.Member` usati
nei test (sottoclassi vere di `discord.Member`, non mock generici,
per superare `isinstance()` nel codice del comando) rompevano
`guild.create_category(overwrites={...})` — quel dizionario usa gli
oggetti come chiavi, e `discord.Member.__hash__`/`__str__` accedono
a `self._user`, un attributo interno che una sottoclasse "finta" non
ha mai popolato. Risolto sovrascrivendo `__hash__`/`__eq__`/`__str__`
sul fake stesso — non è un problema del codice di produzione, sono
oggetti reali Discord che avrebbero quegli attributi popolati
normalmente.

**36 nuovi test**: `test_guild_clan_cog_behavior.py` (nuovo, 15 test,
categoria/canali Discord finti con `create_category`/`get_channel`/
`delete`), `test_guild_clan_expiry_worker.py` (nuovo, 5 test, stesso
pattern fake-bot/fake-guild di `test_guild_clan_voice_worker.py`).
COMMAND_LIST.md rigenerato (159 comandi).

SPEC.md: §15.14 passa da "zero comandi" a parziale con un primo
pezzo di comandi reali; resta inviti/espulsioni/promozioni (serve
prima il sistema di ruoli Discord Capo/Admin Clan), acquisto canali,
boost. **55% dello schema (142/271).**

**Suite di test completa: 1301/1301 passano.**

---

### Fase 52 — Ruoli Discord Capo Clan/Admin Clan + comandi
invita/espelli/promuovi (SPEC.md §15.14, chiude il pezzo dei ruoli
segnalato come prerequisito nella Fase 51)

Continuazione diretta della Fase 51: lì avevo segnalato che inviti/
espulsioni/promozioni erano bloccati sulla mancanza di un sistema di
ruoli Discord Capo Clan/Admin Clan — questa Fase lo costruisce e ci
appoggia sopra i tre comandi.

**`core/guild_clan_role_service.py` (nuovo)**: il pezzo centrale.
Due ruoli Discord CONDIVISI a livello di server — un solo ruolo
"Capo Clan" e un solo ruolo "Admin Clan" per TUTTA la gilda Discord,
riusati da ogni clan — perché Discord non permette a due ruoli di
stare alla stessa posizione nella hierarchy, quindi non si può creare
un ruolo "Capo Clan" per-clan. L'isolamento fra clan diversi (nessun
capo/admin di un clan può toccare un altro clan) non passa quindi dal
ruolo condiviso, che di per sé non dà nessun permesso su nessun
canale, ma dagli OVERWRITE PER-UTENTE sulla categoria del proprio
clan — lo stesso meccanismo che `clan_crea` già usava per il
fondatore, qui generalizzato:
- `grant_member_access`/`grant_officer_access`/`revoke_access`:
  impostano o rimuovono l'overwrite di un membro sulla categoria del
  SUO clan (base per un membro comune, estesa con `manage_channels`/
  `move_members` — mai `manage_permissions`/`manage_roles`, per non
  permettere a un Admin Clan di alterare gli overwrite altrui o
  auto-promuoversi — per Capo/Admin).
- `get_or_create_shared_role`/`sync_shared_role`: crea il ruolo
  condiviso alla prima necessità (per-guild, mai per-clan) e lo
  aggiunge/rimuove dal membro.
- `sync_member_clan_role(guild, categoria, membro, ruolo)` e
  `clear_member_clan_presence(guild, categoria, membro)`: i due punti
  d'ingresso usati da tutti i comandi — il primo applica ruolo
  condiviso + overwrite coerenti con "owner"/"admin"/altro, il
  secondo rimuove tutto (espulsione, scioglimento). Ogni funzione è
  "best effort" verso Discord (`discord.Forbidden`/`HTTPException`
  solo loggate): il database resta la fonte di verità su
  appartenenza/ruolo, questa sincronizzazione è un livello aggiuntivo
  che non deve mai bloccare un comando già confermato lato dati.

**`guild_clan_logic.py`**: aggiunti `MAX_ADMINS_PER_CLAN=3` e
`MAX_MODS_PER_CLAN=5` — tetti sui ruoli di comando confermati prima
di scrivere i comandi (il Capo Clan resta unico per definizione,
essendo `clans.owner_id`).

**Comandi nuovi in `cogs/leveling/leveling.py`** (gruppo `/clan`):
- **`/clan invita <membro>`**: Capo o Admin Clan, rifiuta chi è già
  in un'altra gilda del server o se si è raggiunto `max_members`,
  `add_member` con ruolo `member` + `sync_member_clan_role` (accesso
  base alla categoria — senza questo overwrite l'invitato non
  vedrebbe affatto i canali, la categoria nega la vista a
  `@everyone` fin dalla creazione).
- **`/clan espelli <membro>`**: Capo o Admin Clan; il Capo Clan non
  può essere espulso (serve `/clan sciogli`); un Admin Clan non può
  espellere un altro Admin Clan (serve il Capo) — `remove_member` +
  `clear_member_clan_presence`.
- **`/clan promuovi <membro> <ruolo:admin|mod|member>`**: SOLO il
  Capo Clan, non può cambiare il proprio ruolo, rispetta i tetti
  `MAX_ADMINS_PER_CLAN`/`MAX_MODS_PER_CLAN` prima di promuovere —
  `set_member_role` + `sync_member_clan_role` (che si occupa sia di
  promuovere che di declassare, incluso rimuovere il ruolo Discord e
  gli overwrite estesi quando si torna a `member`).

**`/clan crea`** ora applica anche il ruolo condiviso "Capo Clan" al
fondatore (`sync_member_clan_role(..., ROLE_OWNER)`), oltre
all'overwrite di categoria che già impostava. **`/clan sciogli`**
rimuove ruolo/overwrite del Capo Clan (`clear_member_clan_presence`)
prima di cancellare canali/categoria/record — per gli altri
eventuali Admin Clan non necessariamente in cache la pulizia del
ruolo condiviso resta un gap accettato (annotato nel codice), la
loro categoria comunque sparisce con lo scioglimento.

**17 nuovi test**: `test_guild_clan_role_service.py` (nuovo, 16 test,
oggetti Discord finti senza database — ruoli/categoria/membro finti
con `set_permissions`/`add_roles`/`remove_roles`), più 14 nuovi test
in `test_guild_clan_cog_behavior.py` per invita/espelli/promuovi
(inclusi tetti massimi, isolamento admin-vs-admin, chi-può-fare-cosa).
I fake `_FakeMember`/`_FakeGuild`/`_FakeCategory` esistenti sono stati
estesi con `roles`/`add_roles`/`remove_roles`/`create_role`/
`set_permissions` — bug di test reale: `discord.Member.roles` è una
`@property` senza setter, il primo tentativo di `self.roles = []` nel
fake falliva con `AttributeError` per lo stesso motivo delle sessioni
precedenti (sottoclassi vere di `discord.Member` per superare
`isinstance()`, non mock generici) — risolto con un attributo privato
`_ruoli_finti` esposto via property, come già fatto per `id`.

SPEC.md: §15.14 comandi di gestione membri (invita/espelli/promuovi)
e ruoli Capo/Admin Clan passano da `[ ]` a `[x]`; restano `[ ]`
l'acquisto canali extra e i boost XP/coin individuali/di gilda.
**56% dello schema (145/272).** COMMAND_LIST.md rigenerato (162
comandi).

**Suite di test completa: 1331/1331 passano.**

---

### Fase 53 — Acquisto canali extra con doppio requisito coin + ore
vocali accumulate (SPEC.md §15.14, chiude il penultimo pezzo prima
dei boost)

Ultimo pezzo segnalato nella Fase 52 prima dei boost: `/clan
compra-canale`, più il requisito "ore vocali accumulate in gilda"
che nello schema era esplicitamente annotato come "non ancora
agganciato a nessuna soglia di acquisto".

**Da dove vengono i numeri**: il docstring dei costi in
`guild_clan_logic.py` diceva già da sessioni precedenti che i costi
25k/50k/200k/800k erano stati derivati "arrotondando" da una scala
"12h/24h/96h/384h persona-ora discussa" — quella scala non era mai
diventata un requisito VERO, solo la base di calcolo storica dei
prezzi. Questa Fase la rende un controllo reale: `VOICE_HOURS_
REQUIRED = (12, 24, 96, 384)` in `guild_clan_logic.py`, stessa
posizione della scala dei costi.

**Nuovo contatore**: colonna `clans.total_voice_ticks` (persona-tick,
non per singolo membro — la somma di tutti i tick di TUTTI i membri
della gilda), nuovo metodo `GuildClanRepository.add_voice_ticks`.
Incrementato in `guild_clan_voice_worker.py` ad OGNI tick di un
membro ufficializzato, **indipendentemente** dal decadimento per
permanenza o dal tetto giornaliero che azzerano solo la ricompensa
XP/coin — la presenza vocale in sé conta comunque per questo
requisito, sono due cose diverse per definizione (nuovo test
dedicato che lo dimostra: un membro con decadimento già esaurito,
zero XP guadagnato, continua ad accumulare ore). Due nuove funzioni
pure: `next_channel_voice_hours_requirement` (stessa forma di
`next_channel_unlock_cost`) e `voice_ticks_to_hours` (arrotondato per
difetto, mai a favore dell'utente).

**`/clan compra-canale <tipo:testuale|vocale|forum> [nome]`**:
Capo/Admin Clan, verifica in ordine — permesso, scala canali non
esaurita, ore vocali accumulate sufficienti, saldo tesoreria
sufficiente (pre-check di lettura, evita di creare un canale Discord
inutile quando si sa già che il saldo non basta) — POI crea il
canale Discord VERO dentro la categoria del clan (stesso ordine di
"risorsa Discord prima del record" già usato da `/clan crea` con la
categoria: se la creazione fallisce non deve restare una spesa senza
contropartita), e SOLO DOPO scala la tesoreria in modo atomico
(`spend_from_treasury`, che ri-verifica la sufficienza — un edge case
di saldo cambiato nel frattempo, es. dal decadimento mensile, viene
gestito senza bloccare lo sblocco: il canale esiste già ed è
comunque conteggiato, solo senza scalare un importo che non basta
più, loggato come warning). `/clan info` mostra ora anche le ore
vocali accumulate e il prossimo requisito (costo + ore) quando la
scala non è esaurita.

**22 nuovi test**: 6 in `test_guild_clan_logic.py` (le due nuove
funzioni pure), 2 in `test_guild_clan_repo.py` (`add_voice_ticks`), 2
in `test_guild_clan_voice_worker.py` (accumulo normale + accumulo
anche con decadimento a zero), 7 in `test_guild_clan_cog_behavior.py`
per `/clan compra-canale` (successo, permesso admin, permesso negato
a un membro semplice, tesoreria insufficiente, ore insufficienti,
scala esaurita, permessi Discord mancanti senza spesa). Fake
`_FakeGuild` esteso con `create_text_channel`/`create_voice_channel`/
`create_forum`.

SPEC.md: §15.14 acquisto canali e requisito ore vocali passano da
`[~]`/`[ ]` a `[x]`; resta `[ ]` solo il pezzo dei boost XP/coin
individuali/di gilda. **56% dello schema (148/272).** COMMAND_LIST.md
rigenerato (163 comandi).

**Suite di test completa: 1353/1353 passano.**

---

### Fase 54 — Boost XP/Coin individuali e di gilda (SPEC.md §15.14,
ultimo pezzo dei comandi previsti per il Sistema Gilde/Clan)

Ultimo pezzo segnalato nella Fase 53. A differenza delle Fasi
precedenti (dove i numeri economici erano già stati confermati in
sessioni passate o derivabili da costanti già scritte), qui non
esisteva ancora nessun numero: moltiplicatore, durata, costo. Prima
di scrivere qualunque logica ho chiesto esplicitamente all'utente
(non inventato, come già fatto per il prezzo del premium in una Fase
precedente) — confermati: moltiplicatore **×2** per **24h**, il
boost individuale si applica SOLO al proprio tick vocale di gilda
(mai al leveling generale del server, resta scoped al Sistema
Gilde/Clan), costi **10.000** coin personali (individuale) e
**100.000** coin dalla tesoreria (di gilda).

**`core/guild_clan_boost_logic.py` (nuovo, logica pura)**:
`is_boost_active(scadenza, now)`, `compute_boosted_reward(xp, coin,
individual_active, guild_active)` (i due boost si MOLTIPLICANO tra
loro se entrambi attivi — ×4 totale, non si escludono a vicenda:
fonti e portata diverse), `extend_boost_expiry(scadenza_attuale,
now)` (se un boost è già attivo, la nuova durata si estende da lì,
non da `now` — altrimenti si comprerebbe tempo già pagato; stesso
pattern già usato per l'estensione mensile del premium).

**Persistenza**: nuova colonna `clan_members.boost_expires_at`
(individuale, per membro) e `clans.guild_boost_expires_at` (di
gilda, per clan), due nuovi metodi scrittura-soltanto
(`set_member_boost_expiry`/`set_guild_boost_expiry` — la scadenza la
calcola sempre il chiamante con `extend_boost_expiry`, questi
metodi scrivono e basta).

**`guild_clan_voice_worker.py`**: dopo aver calcolato la ricompensa
base del tick (`compute_tick_reward`, già scontata di decadimento e
tetto giornaliero) e SOLO quando è positiva (evita una query
`get_member` in più ad ogni tick a vuoto), applica
`compute_boosted_reward` prima di accreditare XP/coin — i boost
moltiplicano la RICOMPENSA, mai le ore vocali accumulate (quelle
restano un conteggio di presenza indipendente, invariato da questa
Fase).

**`/clan boost individuale`**: QUALUNQUE membro della gilda (non
solo Capo/Admin — paga dal proprio saldo per il proprio guadagno),
scala `leveling_repo.spend_coins`, poi `extend_boost_expiry` +
`set_member_boost_expiry`. **`/clan boost gilda`**: Capo/Admin Clan,
scala dalla tesoreria (`spend_from_treasury`, stesso `REASON_GUILD_
BOOST` nuovo), poi `extend_boost_expiry` + `set_guild_boost_expiry`.
`/clan info` mostra ora anche lo stato del boost di gilda quando
attivo.

**26 nuovi test**: 13 in `test_guild_clan_boost_logic.py` (logica
pura), 2 in `test_guild_clan_repo.py` (i due setter), 4 in
`test_guild_clan_voice_worker.py` (boost individuale, di gilda,
entrambi che si moltiplicano, boost scaduto che non si applica), 7
in `test_guild_clan_cog_behavior.py` per i due comandi (successo,
chi può comprare cosa, saldo/tesoreria insufficiente, estensione di
un boost già attivo).

SPEC.md: §15.14 boost individuali/di gilda passano da `[ ]` a `[x]`
— **tutti i comandi previsti per il Sistema Gilde/Clan sono
scritti**; restano aperte solo due voci minori non bloccanti (lato
testuale del guadagno ×2, oggi solo vocale; un comando di prelievo
dalla tesoreria per Capo/Admin). **57% dello schema (151/272).**
COMMAND_LIST.md rigenerato (165 comandi).

**Suite di test completa: 1380/1380 passano.**

---

### Fase 55 — Debito di documentazione trovato dall'utente: trasferimento
tesoreria cross-server tra gilde dello stesso owner (SPEC.md §15.14)

L'utente ha chiesto esplicitamente di controllare la CHAT (non
GitHub, "che magari non avevi aggiornato la parte") per un discorso
già fatto in una sessione precedente: un Capo Clan con una seconda
gilda su un altro server con lo stesso bot deve poter spostare le
coin della tesoreria cross-server, altrimenti restano bloccate per
sempre nel server in cui sono state guadagnate.

**Verifica**: `core.repositories.guild_clan_repo.transfer_between_
treasuries` esisteva già — scritto nel secondo pezzo del repository
(commit `fd1951f`, prima ancora che esistesse un solo comando
Discord per il Sistema Gilde/Clan), con 3 test già passanti. Il
docstring della classe `Clan` diceva esplicitamente da allora: "Un
clan ha un ID GLOBALE (non per server): necessario perché i
trasferimenti di tesoreria tra clan dello STESSO owner possono
attraversare server diversi (confermato esplicitamente dall'utente)".
**Ma**: `grep` su SPEC.md non trovava NESSUNA voce per questa
funzionalità — non `[x]`, non `[~]`, non `[ ]`, semplicemente
assente dallo schema — e nessun comando Discord l'aveva mai
richiamata. Un debito di documentazione reale, non un pezzo nuovo da
progettare: i numeri e la regola ("solo lo stesso owner, mai lo
stesso server") erano già confermati, mancava solo collegare il
repository a un comando e a SPEC.md.

**Nuovo**: `GuildClanRepository.list_clans_owned_by(owner_id)` — TUTTI
i clan (su QUALUNQUE server) di cui `owner_id` è il Capo Clan, senza
scoping per guild_id (apposta). **`/clan tesoreria trasferisci
<tag_destinazione> <importo>`**: solo il Capo Clan, cerca il tag tra
le gilde restituite da `list_clans_owned_by` (escludendo la propria)
— se zero corrispondenze, avvisa che non è Capo Clan di nessun'altra
gilda con quel tag "su nessun server"; se più di una (stesso owner
con lo stesso tag su server diversi, raro ma possibile visto che i
tag sono univoci solo per server), chiede di rinominarne una prima di
procedere. Il messaggio di successo segnala esplicitamente quando il
trasferimento è avvenuto verso un altro server.

**7 nuovi test**: 2 in `test_guild_clan_repo.py` (`list_clans_owned_by`
attraversa i server, lista vuota), 5 in `test_guild_clan_cog_behavior.
py` per il comando (successo cross-server con messaggio che lo
segnala, permesso negato a un admin, gilda di un altro owner non
trovata, saldo insufficiente, nessuna gilda).

SPEC.md: nuova voce `[x]` sotto §15.14 per il trasferimento
cross-server (che prima non esisteva nello schema — non un
passaggio da `[ ]`/`[~]` a `[x]`, una voce mancante aggiunta e
chiusa nella stessa sessione). **58% dello schema (152/273).**
COMMAND_LIST.md rigenerato (166 comandi).

**Suite di test completa: 1387/1387 passano.**

---

### Fase 56 — Premi evento dalla cassa di server: `/assegna-lobby` e
`/assegna-winner` (SPEC.md §15.15, chiude l'ultima voce parziale
della sezione)

L'utente ha chiesto due comandi distinti per premiare i membri dalla
cassa di server (distinta dalla tesoreria di clan): un premio
partecipazione a tutti i presenti in vocale nel momento
dell'esecuzione, e un premio vincitore a un membro scelto.

**Nuovo**: due costanti di motivo nel ledger
(`REASON_EVENT_LOBBY_PRIZE`, `REASON_EVENT_WINNER_PRIZE` in
`core/repositories/guild_chest_repo.py` — nessun'altra modifica
necessaria al repository, `spend`/`get_balance` già atomici e
riusabili). **`/assegna-lobby <importo>`** \[Admin, `manage_guild`\]:
raccoglie tutti i membri (bot esclusi) presenti in QUALUNQUE canale
vocale del server nell'istante dell'esecuzione, calcola il costo
totale (`importo × presenti`), tenta la spesa dalla cassa in un colpo
solo — se la cassa non basta per l'INTERO gruppo non assegna nulla a
nessuno (niente assegnazioni parziali) — poi accredita `importo` a
ciascun presente via `leveling_repo.add_coins`. Se nessuno è in
vocale, avvisa senza toccare la cassa. **`/assegna-winner <membro>
<importo>`** \[Admin\]: stesso pattern spesa-poi-accredito per un
singolo membro.

**8 nuovi test** in `test_guild_chest_cog_behavior.py`: premio a
tutti i presenti, bot ignorati, nessuno in vocale, cassa
insufficiente (nessuna assegnazione parziale), vincitore premiato,
vincitore con cassa insufficiente, entrambi i comandi fuori da un
server.

SPEC.md: la voce `[~]` "Uso della cassa" sotto §15.15 passa a `[x]` —
la sezione §15.15 è ORA COMPLETA. Ricalcolo meccanico: §15
Levels/Gilde passa da 27/5/2 a **28/4/2** (fatte/parziali/mancanti).
**58% dello schema (153/273 pesato).** COMMAND_LIST.md rigenerato
(168 comandi).

**Suite di test completa: 1395/1395 passano.**

Nota: resta aperta la richiesta dell'utente di ricontrollare i
moltiplicatori XP/coin di vocale/testo normali contro quelli di
gilda — trattata separatamente (vedi sotto), perché ha rivelato una
discrepanza reale tra quanto dichiarato in SPEC.md ("×2") e le
costanti effettivamente implementate, da chiarire con l'utente prima
di toccare codice.

---

### Fase 57 — Chiusura della discrepanza ×2 XP/coin di gilda: vocale
corretto, lato testuale scritto da zero (SPEC.md §15.14)

**Cosa non tornava**: SPEC.md dichiarava esplicitamente "Guadagno ×2
XP e coin nei canali della propria gilda" ma le costanti vocali
implementate (`TICK_XP=30`, `TICK_COINS=2` in `core/guild_clan_
logic.py`) non erano il doppio del vocale normale (`VOICE_XP_PER_
MINUTE=5`, `VOICE_COINS_PER_MINUTE=2` in `core/leveling_logic.py`) —
erano ×6 sull'XP e ×1 (nessun moltiplicatore) sulle coin. Verificato
che entrambi i tick durano 60 secondi (`TICK_SECONDS` nel worker
vocale di gilda, cooldown testo normale), quindi i valori sono
confrontabili 1:1 al minuto — non un problema di unità diverse.
PROGRESS.md (Fase 48) confermava che quei numeri erano stati
calibrati indipendentemente contro un target mensile assoluto
(500-750k XP/mese, <50k coin/mese), non derivati da un ×2.

**Recupero della discussione originale**: l'utente ha detto che i
valori erano già stati confermati "abbondantemente" in questa stessa
conversazione. Verifica fatta cercando programmaticamente nella
trascrizione JSONL della sessione ogni occorrenza di "moltiplicat",
"×2", "TICK_XP" ecc.: la sessione aveva già superato un `compact_
boundary` che aveva scartato oltre 1 milione di token di storia
precedente — i valori originali non erano più recuperabili da
nessun file accessibile. Segnalato onestamente all'utente invece di
indovinare o insistere sulla ricerca; l'utente ha poi trascritto a
mano lo scambio (che risultava però relativo a §15.15 — cassa/
decadimento/premium, già implementato correttamente — non al ×2 di
§15.14), quindi chiesti di nuovo con `AskUserQuestion` i due numeri
specifici mancanti: confermato ×2 letterale sia per il vocale (10
XP/4 coin al minuto) sia per il testo (30 XP a messaggio, stesso
cooldown 60s, nessuna coin), nessun boost sul testo (già scoped al
solo vocale, Fase 54).

**Vocale corretto**: `TICK_XP` 30→10, `TICK_COINS` 2→4 in `core/
guild_clan_logic.py` — ora esattamente ×2 di `VOICE_XP_PER_MINUTE`/
`VOICE_COINS_PER_MINUTE`. Il test che verificava il vecchio target
mensile assoluto è stato sostituito con un test che verifica
direttamente il rapporto ×2 rispetto alle costanti del vocale
normale (non più un numero calibrato a parte). Aggiornati i valori
attesi hardcoded in `test_clan_voice_activity_repo.py` e
`test_guild_clan_voice_worker.py` (inclusi i test dei boost, che
moltiplicano il NUOVO tasso base).

**Testo scritto da zero** (non esisteva alcun hook): nuova colonna
`last_text_xp_at` su `clan_members` (stesso pattern cooldown di
`LevelingRepository.add_text_xp`, riusa `core.leveling_logic.
can_earn_text_xp` per il controllo — stesso cooldown 60s, niente
duplicato). Nuovo `GuildClanRepository.apply_text_tick(clan_id,
user_id)`: atomico con `FOR UPDATE` sulla riga membro, assegna
`TEXT_TICK_XP` (30, nuova costante in `core/guild_clan_logic.py`) se
il cooldown lo consente, nessuna coin, nessun boost. Agganciato in
`cogs/leveling/leveling.py` dentro `on_message`, PRIMA della
chiamata già esistente a `leveling_repo.add_text_xp` (le due sono
indipendenti: un membro di gilda guadagna sia l'XP personale che
l'XP di gilda dallo stesso messaggio).

**Bug trovato in un test preesistente durante la verifica**: la
suite completa segnalava 2 fallimenti in `test_drop_behavior.py`
(mai toccato in questa sessione) — la sua fixture usa un `Database()`
locale isolato ma non patchava `guild_clan_repo`, quindi il nuovo
hook in `on_message` risolveva il singleton globale (mai connesso in
quel test) e solleva. Corretto patchando anche `guild_clan_repo` con
un repository agganciato allo stesso pool locale del test — nessuna
altra suite preesistente chiamava `on_message` senza già avere quel
patch.

**11 nuovi test**: 3 in `test_guild_clan_logic.py` (rapporto ×2
verificato direttamente, sostituendo il vecchio test sul target
mensile), 3 in `test_guild_clan_repo.py` (`apply_text_tick`: assegna,
rispetta il cooldown, ignora chi non è membro), 4 in un nuovo
`test_guild_clan_text_xp_behavior.py` (messaggio di un membro di
clan accredita l'XP di gilda, secondo messaggio entro il cooldown non
raddoppia, chi non è in nessun clan viene ignorato, clan non
ufficializzato non accredita nulla) — più l'aggiornamento dei valori
hardcoded (non nuovi test) in `test_clan_voice_activity_repo.py` e
`test_guild_clan_voice_worker.py`.

SPEC.md: la voce `[~]` "Guadagno ×2 XP e coin" sotto §15.14 passa a
`[x]` (vocale corretto + testuale ora scritto) — resta aperta solo
la voce del prelievo dalla tesoreria verso un membro. Ricalcolo
meccanico: §15 Levels/Gilde passa da 28/4/2 a **29/3/2**
(fatte/parziali/mancanti). **58% dello schema (154/273 pesato).**
COMMAND_LIST.md rigenerato (nessun comando nuovo — solo il timestamp,
la feature non aggiunge comandi Discord).

**Suite di test completa: 1402/1402 passano.**

---

### Fase 58 — Audit richiesto dall'utente ("cosa resta da fare"):
chiude §15 al 100% correggendo due debiti di documentazione, nessun
codice toccato

L'utente ha chiesto lo stato generale del progetto. Controllando
§15.14/§15.15 a fondo (dato il lavoro appena fatto nelle Fasi 56-57)
sono emersi due problemi, entrambi di sola documentazione:

1. **15.10 "Classifica Gilde" segnata mancante per errore** —
   `/clan classifica` esiste già (ordina i clan per XP totale del
   server), testato in `test_guild_clan_cog_behavior.py`. Corretta a
   parziale: manca solo la variante MENSILE (nessun `period_key` per
   l'XP di clan, oggi solo il totale cumulativo mai resettato).
2. **"Manca un comando di prelievo dalla tesoreria verso un membro"
   era un fraintendimento**, non una lacuna — segnalato dall'utente:
   la tesoreria di clan è a SENSO UNICO per design (membro -> gilda
   sempre permesso, gilda -> membro MAI, confermato esplicitamente
   quando il repository fu scritto, in una sessione precedente a
   questa). Il bisogno reale di "premio evento" che questa voce
   indicava è già servito da un percorso diverso e corretto: la
   cassa DI SERVER (§15.15) via `/assegna-lobby`/`/assegna-winner`
   (Fase 56), non la tesoreria di un singolo clan.

Corretti anche due marcatori di livello superiore rimasti stale
(§15.14 e §15.15 erano ancora `[~]`/`[ ]` nonostante tutti i
sotto-punti fossero già `[x]`) e la cifra "30 XP + 2 coin a
tick/minuto" nell'introduzione di §15.14, non aggiornata dopo la
correzione della Fase 57 (ora 10 XP + 4 coin).

**Promemoria per il futuro**: durante la prima stesura della
correzione ho scritto io stesso, per errore, il pattern letterale di
un marcatore (`` `[ ]` ``) dentro una frase di prosa — esattamente
l'errore che la regola già in cima a questo file vieta esplicitamente
(punto 2 delle "Decisioni prese"), perché il conteggio meccanico lo
legge come una voce reale e sballa il totale (273→274). Trovato
SOLO perché il totale delle voci (274 invece di 273, un numero fisso
che non cambia mai) non corrispondeva più — controllo utile da
ripetere ogni volta che il ricalcolo meccanico dà un totale diverso
da quello della sessione precedente.

SPEC.md: §15.14 e §15.15 passano entrambi a `[x]` a livello di
sottosezione; 15.10 passa a `[~]`; **§15 Levels/Gilde ora 32/2/0
(fatte/parziali/mancanti) — ZERO voci genuinamente mancanti**.
Ricalcolo meccanico: **59% dello schema (157/273 pesato)**. Nessun
comando Discord aggiunto o rimosso — COMMAND_LIST.md non rigenerato
(nessuna variazione possibile).

**Suite di test completa: 1402/1402 passano** (nessun codice
toccato in questa fase, solo verifica di non regressione).

---

### Fase 59 — Chiude §9 Music: fallback Spotify predisposto verso un
nodo personale + gestione reale del cap istanze concorrenti (SPEC.md
§9.5/§9.10)

L'utente ha chiesto di finire Music, escludendo esplicitamente tutto
ciò già scartato/rimandato per sua richiesta (filtri, DJ role,
voteskip, comandi usati raramente — §9.4/9.6/9.7/9.8, invariati).
Restavano solo due voci genuinamente aperte, entrambe chiarite con
l'utente prima di scrivere codice (`AskUserQuestion`, due giri: la
prima ha isolato il vero bisogno, la seconda ha chiuso solo il
dettaglio del ticket).

**Spotify (§9.5)**: Spotify richiede il plugin LavaSrc sul nodo
Lavalink, non verificabile sui nodi pubblici di terzi senza
controllarli — l'utente vuole un fallback verso un suo nodo personale
con LavaSrc, da configurare più avanti, ma con il codice GIÀ
predisposto oggi. Scoperto che questo nodo personale altro non è che
`LAVALINK_HOST/PORT/PASSWORD` già esistente in config.py (il "nodo
locale/self-hostato", oggi usato solo per i file locali della radio
— `LOCAL_NODE_IDENTIFIER`) — nessuna nuova variabile d'ambiente
necessaria. Nuovo: `core.music_logic.is_spotify_query` (pura,
riconosce URL `open.spotify.com` e URI `spotify:`) e
`MusicCog._search_with_spotify_fallback`: cerca prima sui nodi
pubblici come sempre, e SOLO se una query Spotify torna vuota
ritenta UNA volta pinnata sul nodo locale. Comportamento identico ad
oggi finché l'utente non configura lì un nodo con LavaSrc davvero
installato — nessuna regressione, puro miglioramento silenzioso.

**Cap istanze concorrenti (§9.10)**: chiarito con l'utente cosa
"configurabile a parte" significasse davvero — non un numero
diverso da 5 impostabile a comando (il cap È il numero di token bot
worker configurati, non ha senso renderlo un altro numero), ma la
gestione di COSA succede quando `/play` non trova un worker
assegnabile, distinguendo due scenari reali con messaggi diversi e
un terzo pubblico (admin vs non-admin):
1. **Il server non ha ancora invitato tutte le 5 istanze** — un
   admin riceve i link d'invito delle istanze mancanti (generati al
   volo con `discord.utils.oauth_url`, permessi minimi — solo
   vocale, mai admin — SEMPRE per QUESTO server specifico via
   `guild=`/`disable_guild_select=True`); un non-admin viene
   invitato a chiedere all'admin, senza vedere alcun link.
2. **Il server ha già tutte le 5 istanze ma sono tutte occupate
   altrove in questo momento** — non c'è nulla da invitare qui,
   serve un'estensione del limite GLOBALE: il messaggio (sia per
   admin che no) indirizza ad aprire un ticket nel server ufficiale
   iYokai (il modulo Ticket, §13, è già attivo lì — nessun link
   fabbricato, quel server è già pubblicamente raggiungibile).

**Bug reale trovato e corretto nel percorso**: `MusicFleet.
get_or_assign_worker_for_guild` assegnava un worker SENZA controllare
se fosse davvero invitato nel server richiedente — solo DOPO
l'assegnazione (già scritta su `music_sessions`) `/play` scopriva che
il worker non c'era, falliva con un messaggio generico, e lasciava lo
slot occupato PER SEMPRE per quel server (nessun evento lo avrebbe
mai liberato, dato che nessun player si connette mai). Corretto
escludendo i worker non presenti PRIMA di assegnare (nuovo
`MusicFleet.get_missing_worker_indices`), e aggiunta una release
difensiva nel raro caso residuo (bot rimosso dal server DOPO
l'assegnazione).

**19 nuovi test**: 5 in `test_music_fleet.py` (esclusione worker non
presenti, nessuno assegnabile se tutti assenti, `get_missing_worker_
indices`, `build_invite_url`), 3 in `test_music_routing.py` (istanze
mancanti non-admin/admin con link, saturazione globale admin con
ticket), 5 in `test_music_logic.py` (`is_spotify_query`), 4 in un
nuovo `test_music_spotify_fallback.py` (fallback attivato/non
attivato, nodo locale assente) — più l'aggiornamento di un fake
preesistente (`_FakeWorkerBot` in `test_music_fleet.py`) e di
un'asserzione di testo cambiata deliberatamente in un test già
esistente.

SPEC.md: 9.5 resta `[~]` (il fallback è predisposto, ma Spotify non
funziona finché l'utente non configura davvero un nodo con LavaSrc)
con nota aggiornata; 9.10 passa a `[x]`. Ricalcolo meccanico: §9
Music passa da 6/3/0 a **7/2/0** (fatte/parziali/mancanti). **59%
dello schema (158/273 pesato).** Nessun comando Discord nuovo —
COMMAND_LIST.md rigenerato (solo il timestamp).

**Suite di test completa: 1419/1419 passano.**

---

### Fase 60 — Backup System: auto-propagazione (§11.13) e mirror
messaggi in tempo reale via webhook (§11.9)

L'utente ha chiesto "Facciamole tutte" per le 4 voci rimaste in §11
Backup (§11.9, §11.10, §11.11+§11.12, §11.13). Prima di scrivere
codice per §11.10/§11.11 (storage token OAuth altrui — tema di
sicurezza reale, mai affrontato) sono state fatte 3 domande esplicite
all'utente (`AskUserQuestion`) su: modalità di consenso, cifratura a
riposo, retention/revoca. Risposte ricevute (sintesi): consenso
ibrido a 3 vie a scelta del server owner (raccolta al primo verify
per server nuovi; raccolta on-demand al bisogno con verifica
aggiornata per server esistenti grandi; nessun token, solo invito
classico con auto-invito opzionale ai nuovi arrivati); cifratura
forte a riposo; retention differenziata (uscita spontanea → cancella
dopo 90gg, kick → preserva con flag/avviso admin al rejoin, ban →
preserva + blacklist). Questa fase completa le due voci SENZA
dipendenze OAuth (§11.9, §11.13); §11.10/§11.11/resto di §11.12
proseguono in una fase successiva.

**§11.13 Auto-propagazione**: nuovo comando `/promuovi-backup`
(lanciato DENTRO al server che finora era il backup, non nel main —
non serve altro ID, si risale al main tramite `BackupRepository.
get_pair_by_backup_guild_id`). `BackupRepository.promote_backup_to_
main(old_main_guild_id, new_main_guild_id)` (nuovo, transazione
singola): il vecchio main perde il backup (`backup_guild_id = NULL`,
riga non cancellata — potrebbe volerne un altro), il server promosso
diventa main senza backup. Il comando poi chiama IMMEDIATAMENTE
`enqueue_job` per il server appena promosso — questa è l'auto-
propagazione richiesta: non resta mai "main senza backup" più del
tempo tecnico di accodare un nuovo job.

**§11.9 Mirror messaggi in tempo reale**: nuovo `core.backup_mirror_
logic.MirrorRateLimiter` (pura, nessun I/O) — finestra scorrevole per
canale, MAX 5 messaggi/5s, chi supera viene SCARTATO (non accodato:
un mirror in ritardo non serve, e una coda rischierebbe di
accumulare backlog proprio durante un flood/raid, il momento in cui
il mirror serve di più). Nuovo `core.backup_clone_logic.create_
mirror_webhooks()`: crea un webhook dedicato "iYokai Mirror" in OGNI
canale testuale clonato durante la creazione del backup (diverso da
`clone_webhooks()`, che copia webhook già esistenti nel server
originale — questo ne crea di nuovi, di proprietà di iYokai),
restituendo canale_ORIGINALE→URL_webhook. Nuova tabella/repo `core.
repositories.backup_mirror_repo.BackupMirrorRepository` (`backup_
mirror_webhooks`, PK sul canale main) — `save_mapping` sostituisce
SEMPRE l'intera mappa per un main (stessa transazione: DELETE poi
INSERT), perché un nuovo backup rende invalida la mappa del
precedente. Nuovo `core.backup_mirror_dispatch.BackupMirrorDispatcher`:
isola in un solo metodo (`_send`, sovrascrivibile) l'unica vera
chiamata di rete, per restare testabile senza Discord — `handle_
message()` scarta messaggi di bot/webhook (evita loop, incluso il
proprio), messaggi in DM, canali senza mirror configurato, e quelli
sopra il rate limit; altrimenti inoltra impersonando l'autore
(username + avatar via `discord.Webhook.send`). Wired: `core.backup_
orchestrator.start_backup_job` ora restituisce anche la mappa
webhook (tupla di 3, non più 2 — aggiornati tutti i chiamanti/test);
`core.backup_queue_worker` salva la mappa in `backup_mirror_repo`
subito dopo aver impostato `backup_guild_id` sul job; nuovo `cogs.
utility.backup_mirror.BackupMirrorCog` collega `on_message` al
dispatcher (nessun comando, solo listener).

**Migrazioni**: `run_migrations()` in `core/database.py` E in
`tests/conftest.py` (elenco duplicato manualmente, come ogni altro
repository — vedi la nota già presente su questo pattern) aggiornate
con `backup_mirror_repo.run_migrations`; aggiunta `backup_mirror_
webhooks` alla lista TRUNCATE di `clean_db`.

**29 nuovi test**: `test_backup_repo.py` (+5: `get_pair_by_backup_
guild_id`, `promote_backup_to_main` in 3 varianti), `test_backup_cog_
behavior.py` (+3: `/promuovi-backup`), `test_backup_mirror_logic.py`
(nuovo, 5: finestra scorrevole), `test_backup_mirror_repo.py` (nuovo,
6), `test_backup_mirror_webhooks.py` (nuovo, 4: `create_mirror_
webhooks`), `test_backup_mirror_dispatch.py` (nuovo, 5), `test_backup_
mirror_cog_smoke.py` (nuovo, 1), più l'aggiornamento dei fake/tuple in
`test_backup_orchestrator.py` e `test_backup_queue_worker.py`
(`start_backup_job` ora restituisce 3 valori, non più 2).

SPEC.md: 11.9 e 11.13 passano a `[x]`; 11.12 aggiornato (`/promuovi-
backup` fatto, `/restore-users` ancora no). Ricalcolo meccanico
(script corretto in questa fase — vedi nota sotto): §11 Backup passa
da 8/1/4 a **10/1/2**. Totale schema: **160/6/107 su 273, ≈60%**.

**Lezione di processo trovata mentre si ricalcolava il totale**: lo
script di conteggio usato nelle fasi precedenti divideva il file solo
sugli header `## §N`, quindi tutto il testo DOPO l'ultimo header
(inclusa la sezione "Legenda stato" con `` `[x]`/`[~]`/`[ ]`/`[✗]` ``
come esempi letterali, la spiegazione del "Conteggio sintetico"
stesso, e le appendici B/C/D/E che usano header `# ` singolo, non
`## §`) finiva incollato dentro l'ultima sezione (§17), gonfiandola e
sporcando il totale con marcatori che sono prosa, non voci reali.
Corretto lo script per dividere su QUALSIASI header `#`/`##` e per
escludere esplicitamente "Legenda stato" e "Conteggio sintetico" dal
conteggio — il totale di 273 voci reali (verificato: 160+6+107)
torna a coincidere esattamente con quello già noto, confermando che
lo schema non è cambiato di dimensione, solo di stato.

**Suite di test completa: 1448/1448 passano.**

---

### Fase 61 — Backup System: chiude §11 al 100% con il restore
utenti via OAuth2 (§11.10/§11.11/§11.12)

Completa il "Facciamole tutte" iniziato in Fase 60. Prima di
scrivere codice per lo storage dei token OAuth altrui, tre domande
esplicite (`AskUserQuestion`) su consenso/cifratura/retention — vedi
Fase 60 per il dettaglio delle risposte. Un solo punto corretto
rispetto a quanto chiesto: l'utente ha suggerito "algoritmi custom
se possibile per evitare il reversing" — spiegato perché è
un'idea da NON seguire (crittografia fatta in casa, senza revisione
pubblica, è quasi sempre più debole di uno standard, non più
sicura: la protezione vera sta nella chiave segreta, non
nell'oscurità dell'algoritmo) e proceduto con AES-256-GCM standard,
comunicandolo esplicitamente prima di scrivere il codice.

**§11.10 Snapshot settimanale utenti**: `core.backup_snapshot_logic.
is_eligible_for_snapshot` (pura) — un bot non è mai incluso; se il
server ha Verify Base configurato serve il ruolo verificato, altri-
menti (nessun Verify configurato) chiunque non sia un bot conta,
piuttosto che escludere silenziosamente un intero server. Chi è
bannato/kickato non compare per costruzione: la funzione riceve solo
`guild.members` ATTUALI. Nuovo repo `core.repositories.backup_user_
snapshot_repo` (tabella `backup_user_snapshots`, sostituita
INTERAMENTE ad ogni scatto — stesso pattern DELETE+INSERT in
transazione già usato per i webhook mirror in Fase 60). Nuovo
`core.backup_snapshot_worker` (`tasks.loop` settimanale, un tick per
ogni main_guild_id con backup GIÀ attivo — nuovo `backup_repo.
get_all_main_guild_ids_with_backup()`).

**§11.11 Restore massivo via OAuth2**: nuovo `core.oauth_crypto`
(AES-256-GCM via `cryptography`, nonce casuale a 12 byte per ogni
cifratura — mai riusato con la stessa chiave, requisito di
sicurezza di GCM — anteposto al ciphertext e tutto in base64 in
un'unica colonna TEXT). Nuovo repo `core.repositories.restore_oauth_
repo` (`restore_oauth_tokens`, MAI in chiaro: cifra prima di
scrivere, decifra dopo aver letto, mai un valore intermedio in
chiaro nel repo stesso) con la retention concordata: `mark_left_
voluntarily` (imposta `left_at`, poi `purge_expired_voluntary_
leaves(90)` lo cancella se non riusato entro 90gg), `mark_kicked`/
`mark_banned` (preservano SENZA scadenza, cambiano solo `status`).
Nuovo `core.restore_oauth_logic` (pura: `build_authorize_url` con
scope `identify guilds.join`, `encode_state`/`decode_state` — lo
"state" OAuth2 standard, qui semplicemente
`source:target:user_id`, con `target_guild_id=0` che significa
"solo consenso, nessun join da fare ora", usato dalla modalità A).
Nuovo `core.restore_orchestrator.RestoreOrchestrator` — le uniche
due vere chiamate di rete: `exchange_code_for_token` (scambio
code→token) e `join_user_via_oauth` (il vero meccanismo
`guilds.join`: **il BOT** chiama `PUT /guilds/{id}/members/{id}`
con il proprio bot token e l'`access_token` OAuth2 dell'utente nel
corpo — non esiste un wrapper discord.py per questo endpoint, fatta
una chiamata REST diretta con aiohttp) più `assign_role`. Testato
con un server aiohttp VERO in locale che imita la FORMA delle due
API di Discord (stesso principio già usato per il Twitch Watcher —
mai un mock della sessione HTTP). Nuovo
`core.restore_web_server` (aiohttp, un solo endpoint `/oauth/
callback`, `build_app()` con ogni dipendenza iniettata per i test).
Nuovo `core.restore_batch_logic.plan_restore_action` (pura: bannato
→ sempre saltato anche in modalità classica; modalità classica →
sempre invito; token attivo/kickato non scaduto → riusato per
l'auto-join; altrimenti richiede un nuovo consenso). Nuovo `core.
restore_retention_logic.was_recently_kicked` (pura: Discord non dice
direttamente se un `on_member_remove` è un kick o un'uscita
spontanea — si controlla l'audit log per una voce "kick" recente
sullo stesso utente).

**Tre modalità per server** (`/configura-restore`, esattamente come
discusso): OAuth al momento della verifica (server NUOVI — il
consenso si raccoglie da subito, prima che serva); OAuth solo al
bisogno (DEFAULT, server ESISTENTI grandi — es. 50k utenti: non ha
senso rifare la verifica a tutti, si raccoglie il consenso solo se e
quando serve un restore, riusando i token già raccolti da restore
precedenti); solo invito classico (nessun token salvato affatto).
Nuovo comando `/restore-users <server_di_origine>` (in `cogs.
utility.restore.RestoreCog`) — legge lo snapshot §11.10 del server
indicato, per ognuno decide con `plan_restore_action` e agisce:
auto-join silenzioso se già autorizzato, DM con link di
autorizzazione se serve un nuovo consenso, DM con invito classico in
modalità C, salto silenzioso se in blacklist da un ban. Un DM
bloccato (privacy chiusa) viene contato, non fa fallire il resto del
restore. Riepilogo finale all'admin con tutti i contatori.

**Retention via listener** (stesso cog): `on_member_ban` marca
`banned_blacklisted`; `on_member_remove` controlla l'audit log
(azione kick, ultimi 10s, stesso utente) e marca `kicked_flagged` o
altrimenti `left_voluntarily`; `on_member_join` avvisa il canale di
log di moderazione (`mod_log_channel_id`, la STESSA chiave già usata
da `cogs/moderation/_shared.py` — riusata deliberatamente invece di
inventare un secondo canale da configurare) se chi rientra ha un
token flaggato come kickato.

**Config**: nuove `OAUTH_ENCRYPTION_KEY` (32 byte base64, AES-256),
`RESTORE_WEB_HOST`/`RESTORE_WEB_PORT` in `core/config.py` e
`.env.example`; `OAUTH2_CLIENT_ID/SECRET/REDIRECT_URI` (già esistenti
da prima, mai usati finora — stesso pattern di predisposizione
silenziosa già visto con `LAVALINK_HOST` in Fase 59) ora
effettivamente riusati. Nuova dipendenza `cryptography` aggiunta a
`requirements.txt` (era già presente come dipendenza transitiva di
`PyNaCl`/discord.py, ora è una dipendenza diretta dichiarata). Server
web e worker settimanale avviati da `main.py` — il server web parte
solo se le tre variabili OAuth2 sono configurate, altrimenti resta
disattivato senza bloccare l'avvio del bot.

**Migrazioni**: `backup_user_snapshot_repo` e `restore_oauth_repo`
registrate in `core/database.py` E in `tests/conftest.py` (elenco
duplicato manualmente, pattern già noto), tabelle aggiunte al
TRUNCATE di `clean_db`.

**80 nuovi test**: `test_oauth_crypto.py` (9), `test_backup_snapshot_
logic.py` (5), `test_backup_user_snapshot_repo.py` (7),
`test_restore_oauth_repo.py` (10), `test_backup_repo.py` (+2:
`get_all_main_guild_ids_with_backup`), `test_backup_snapshot_worker.
py` (4), `test_restore_oauth_logic.py` (4), `test_restore_
orchestrator.py` (7, con un server aiohttp finto reale),
`test_restore_web_server.py` (7), `test_restore_batch_logic.py` (6),
`test_restore_retention_logic.py` (4), `test_restore_cog_behavior.py`
(8), `test_restore_cog_smoke.py` (1), `test_restore_retention_
listeners.py` (6).

SPEC.md: 11.10 e 11.11 passano a `[x]`; 11.12 completo (`[x]`, tutti
e 5 i comandi fatti). **§11 Backup System è ora COMPLETO al 100%
(13/13)**. Ricalcolo meccanico: totale schema **163/5/105 su 273,
≈61%**.

**Suite di test completa: 1528/1528 passano.**

---

### Fase 62 — Chiude §15.14: bug di race condition nel decadimento
mensile della tesoreria clan

L'utente ha chiesto di finire il decadimento mensile della tesoreria
(§15.14, ultima voce `[~]` insieme alla classifica mensile di gilda
§15.10). Analizzando `guild_clan_treasury_decay_worker.py` per capire
perché fosse ancora marcato parziale, trovato un bug reale non
segnalato prima: `GuildClanRepository.apply_monthly_decay` restituiva
solo il NUOVO saldo (`int`), e il worker calcolava il delta da
versare nella cassa di server come `clan.treasury_balance -
nuovo_saldo` — ma `clan.treasury_balance` proveniva da `list_
officialized_clans()`, una lettura NON sotto lock, fatta PRIMA del
`FOR UPDATE` dentro `apply_monthly_decay`. Se tra quella lista e il
lock il saldo reale cambiava (es. una donazione arrivata nel
frattempo), il delta calcolato era sbagliato — poteva risultare
negativo o comunque diverso dal decadimento realmente applicato,
silenziosamente (nessuna eccezione, solo un deposito sbagliato o
saltato nella cassa).

Il pattern corretto esisteva già altrove nel codebase, identico nella
forma: `LevelingRepository.apply_weekly_decay` (decadimento
settimanale personale, §15.15) restituisce già `tuple[int, int]`
(`saldo_prima, saldo_dopo`), letti entrambi sotto lo stesso `FOR
UPDATE`, e `weekly_personal_decay_worker.py` calcola il delta da
QUELLA coppia, mai da un valore letto prima del lock. Applicata la
stessa correzione a `apply_monthly_decay` (ora restituisce
`(saldo_prima, saldo_dopo)`) e al worker corrispondente.

**Errore mio durante l'editing, autocorretto**: il primo `Edit` sul
repository ha lasciato per sbaglio un `return nuovo_saldo` morto
subito dopo il nuovo `return saldo_attuale, nuovo_saldo` (l'`old_str`
combaciava con il testo giusto prima della riga `return` originale,
ma quella riga restava sotto, ora irraggiungibile). Trovato
immediatamente con `git diff` (abitudine ormai fissa dopo la lezione
sui marcatori letterali in prosa) e rimosso con un secondo `Edit`
prima di eseguire qualunque test.

**3 nuovi test**: `test_apply_monthly_decay_applica_il_dieci_percento`
e `test_apply_monthly_decay_su_saldo_negativo_non_lo_tocca` aggiornati
per spacchettare la tupla; nuovo
`test_apply_monthly_decay_delta_corretto_con_saldo_cambiato_dopo_la_
lista` (simula una donazione arrivata dopo lo snapshot della lista ma
prima del lock, verifica che il delta usi il saldo REALE) in
`tests/test_guild_clan_repo.py`; nuovo `test_delta_in_cassa_usa_il_
saldo_reale_non_quello_stale_della_lista` in `tests/test_guild_clan_
treasury_decay_worker.py` — monkeypatch di `list_officialized_clans`
per restituire un `Clan` con `treasury_balance` volutamente "vecchio"
(1) mentre il saldo reale su database è 100.000, verifica che la
cassa di server riceva comunque il 10% del saldo REALE (10.000), non
un valore derivato dal saldo stale della lista.

SPEC.md: §15.14 "Decadimento mensile 10%" passa a `[x]`. §15 ora
33 fatte / 1 parziale (resta solo la variante mensile di §15.10
Classifica Gilde). Ricalcolo meccanico: totale schema **164/4/105 su
273, ≈61%**.

**2 nuovi test di regressione** (uno per file, come sopra), più i 2
test esistenti aggiornati per spacchettare la tupla.

**Suite di test completa: 1530/1530 passano.**

---

### Fase 63 — Music: clear-queue, shuffle, loop track/queue, nowplaying
con barra (§9.4), limite playlist e correzioni richieste dall'utente

L'utente ha corretto la mia comprensione su YouTube/Spotify sui nodi
Lavalink pubblici (Spotify funziona spesso già, è YouTube che è
spesso rotto sui nodi pubblici — annotato in SPEC.md §9.5, NESSUNA
modifica di codice fatta: non richiesta esplicitamente, solo la
correzione della documentazione) e ha chiesto di completare SOLO
clear (svuota coda), shuffle, i due loop (traccia/coda) e nowplaying
con barra di avanzamento — tutto il resto già segnato come mancante
in §9.4 (search distinta da play, forceskip, remove, move, seek,
lyrics) va invece **rimosso permanentemente** dalla lista, non solo
rimandato.

Nuova `core.music_logic.build_progress_bar(elapsed_ms, total_ms,
bar_length=20)` (pura, nessuna dipendenza da wavelink): un pallino
🔘 lungo una linea di trattini ▬, `total_ms <= 0` (stream live)
restituisce un indicatore fisso invece di dividere per zero,
`elapsed_ms` sempre ristretto a `[0, total_ms]` prima di calcolare la
posizione. Nuovi comandi in `cogs/music/player.py`: `/clear-queue`
(NON `/clear` — vedi il bug sotto), `/shuffle` (con guardia: coda con
meno di 2 tracce non fa nulla), `/loop track` e `/loop queue`
(gruppo `loop`, stesso campo sottostante `player.queue.mode` già
usato da `/nonstop` — attivare l'uno disattiva sempre l'altro, non
si sommano, sono varianti mutuamente esclusive), `/nowplaying`
(barra + tempo trascorso/totale + stato loop + conteggio tracce in
coda rimanenti).

**Due richieste aggiuntive dell'utente, arrivate a metà lavoro**:

1. **Limite tracce per playlist**: un link a una playlist enorme
   (Spotify e altre piattaforme ne permettono fino a migliaia) non
   deve poter riempire la coda di un server all'infinito in un
   colpo. Nuova `core.music_logic.MAX_PLAYLIST_TRACKS = 750` e
   `truncate_playlist_tracks(tracks, limit=750)` (pura, slicing puro
   — funziona su qualunque sequenza indicizzabile, incluso
   `wavelink.Playlist`). `/play` ora taglia alle prime 750 e lo dice
   esplicitamente nel messaggio di conferma se la playlist era più
   lunga.
2. **Shuffle genuinamente randomico**: preoccupazione esplicita
   dell'utente — molti bot musicali "mescolano" seguendo pattern
   nascosti, non un vero random. Verificato leggendo il sorgente di
   wavelink: `Queue.shuffle()` chiama `random.shuffle` della
   libreria standard (Fisher-Yates non polarizzato) — **nessuna
   modifica di codice necessaria**, `/shuffle` delega direttamente a
   quel metodo senza reimplementare nulla. Aggiunto un test di
   regressione che spia `random.shuffle` per bloccare esplicitamente
   questa garanzia (fallirebbe se una futura versione di wavelink
   cambiasse l'algoritmo internamente).

**Bug reale trovato e corretto in questa Fase, il più serio della
sessione per potenziale impatto silenzioso**: il primo tentativo di
`/clear-queue` era stato scritto come `/clear` — nome già usato dal
`/clear` di moderation (cancellazione messaggi). Un nome di comando
slash duplicato fa fallire la REGISTRAZIONE dell'intero cog che lo
dichiara (discord.py, non un limite di questo progetto), e
`core.cog_manager.load_all_cogs` cattura e LOGGA ogni eccezione di
`setup()` per singolo cog senza farla risalire — di proposito, un
cog rotto non deve bloccare l'avvio di tutto il resto — quindi
l'intero modulo Music si sarebbe disattivato in silenzio in
produzione, notato solo rilanciando `scripts/generate_command_list.
py` sull'albero comandi reale (il conteggio è sceso da 171 a 153
comandi, la categoria Music è sparita del tutto). **Mai scoperto dai
test unitari esistenti**: ognuno istanzia il proprio cog da solo,
senza mai unire il suo albero comandi a quello di TUTTI gli altri
cog insieme come fa il bot vero. Rinominato in `/clear-queue`.

**Chiusura del buco di test che ha permesso il bug**: nuovo
`tests/test_cog_manager_load_all.py` — chiama il `setup()` di OGNI
cog scoperto da `discover_cog_modules()` dentro lo stesso bot/albero
comandi, esattamente come fa il bot vero, e verifica che nessuno
fallisca né lasci nomi duplicati nell'albero. **Errore mio scrivendo
QUESTO test, trovato e corretto prima di committare**: la prima
versione usava `bot.load_extension(modulo_path)` per farlo — ma
`discord.ext.commands.Bot._load_from_module_spec` RICREA ED ESEGUE
DA CAPO il modulo con `importlib.util.module_from_spec` +
`exec_module`, sovrascrivendo `sys.modules[modulo_path]` con un
nuovo oggetto modulo OGNI VOLTA, anche se il modulo era già
importato altrove nella sessione pytest. Usarlo qui sostituiva
silenziosamente, per il resto dell'intera sessione di test, i moduli
di TUTTI i cog (classi, singleton come `eval_shell_log_repo`) con
copie fresche — rompendo `test_owner_blacklist_commands.py` (che
importa `OwnerPremiumCog` a livello di modulo) in un modo visibile
SOLO eseguendo i due file insieme, mai in isolamento — trovato
proprio perché ho rilanciato la suite completa dopo aver scritto
questo test, come da disciplina di sessione. Corretto usando
`importlib.import_module(modulo_path)` (riusa la cache se già
importato, non esegue nulla due volte) + `modulo.setup(bot)`
direttamente: stesso effetto reale sull'albero comandi, zero
effetti collaterali sugli altri test.

SPEC.md: §9.4 passa a `[x]` (era `[~]`); search distinta da play,
forceskip, remove, move, seek, lyrics rimossi PERMANENTEMENTE dalla
lista delle cose da fare (non più `[ ]`/`[~]`, tolti dal testo).
§9.5: annotata la correzione dell'utente su YouTube/Spotify, nessun
cambio di stato. Ricalcolo meccanico: totale schema **165/3/105 su
273, ≈61%**.

**8 nuovi test**: `TestBuildProgressBar` (7) e `TestTruncatePlaylist
Tracks` (5) in `tests/test_music_logic.py`; 12 nuovi test in
`tests/test_music_guard_clauses.py` (clear-queue/shuffle/loop/
nowplaying + il test-spia su random.shuffle); 3 nuovi in
`tests/test_music_playlist_limit.py`; 1 nuovo in
`tests/test_cog_manager_load_all.py`; 2 assert aggiornati/estesi in
`tests/test_music_cog_smoke.py`.

**Suite di test completa: 1557/1557 passano** (verificato due volte
di fila per escludere flakiness legata all'ordine, dato il bug di
inquinamento di sys.modules appena trovato e corretto).

---

### Fase 64 — Chiude §10.8: webhook custom in ricezione ("Vedi di
fare sto webhook? Tanto li devi fare per quanto li ignori..")

Richiesta esplicita dell'utente, riferita a un elemento dello schema
lasciato a metà (`[~]`): la parte RSS di §10.8 era già fatta
(`/alerts add`), ma la parte "webhook" (ricezione di push da servizi
terzi, non polling nostro) non esisteva. A differenza di Twitch
EventSub/YouTube PubSubHubbub (webhook push legati a un protocollo
specifico di quella piattaforma, scartati per il vincolo di
infrastruttura già documentato nella Nota tecnica di §10), qui non
serve integrarsi con nessun protocollo esterno: serve solo un
endpoint HTTP generico *nostro*, dove qualunque servizio terzo
(n8n, Zapier, IFTTT, un piccolo script proprio) può pubblicare un
messaggio in un canale Discord con una richiesta POST.

**Architettura**: riusato lo stesso pattern già stabilito per il
server di callback OAuth2 (`core/restore_web_server.py`, §11.11) —
`build_app(**dipendenze)` che ritorna una `aiohttp.web.Application`
con dependency injection (repository e callback passati come
parametri, mai importati come singleton globali dentro le closure
degli handler, per poterli sostituire nei test), e `start_server()`
che ritorna un `AppRunner` di cui `main.py` fa `.cleanup()` allo
shutdown. A differenza del server OAuth2 (che parte solo se le
variabili OAuth sono configurate), questo server parte SEMPRE,
incondizionatamente — non richiede configurazione per esistere,
solo per essere raggiungibile dall'esterno.

**Modello di sicurezza — "URL segreto come autenticazione"**: stesso
schema usato da Discord/Slack/GitHub per i loro webhook in
ricezione: un token opaco da 32 byte (`secrets.token_urlsafe(32)`,
non indovinabile per forza bruta) incorporato nel path dell'URL
(`/webhook/<token>`) È l'unica autenticazione — nessun sistema di
account/API-key separato. Il token viene mostrato all'admin UNA SOLA
VOLTA, al momento della creazione (`/alerts webhook-create`), e non
viene mai più ri-mostrato — né da `/alerts list` (che mostra solo
`WH-<id>`, label e canale, MAI il token, con un commento esplicito
nel codice a ricordarlo) né da nessun altro comando. Se il token si
perde, l'unica via è creare un nuovo webhook e rimuovere il vecchio
con `/alerts remove WH-<id>` — decisione di sicurezza deliberata, non
una svista.

**Nuovi file**:
- `core/custom_webhook_logic.py` — logica pura: generazione token,
  costruzione URL, estrazione campi dal payload JSON (con alias:
  `message`/`content`/`text` per il corpo, `url`/`link` per il
  link), troncamento a 256/1500/500 caratteri (titolo/messaggio/
  url), rendering del messaggio finale via template con placeholder
  `{label}` `{title}` `{message}` `{url}` (righe che restano vuote
  dopo la sostituzione vengono rimosse)
- `core/repositories/custom_webhook_repo.py` — tabella
  `custom_webhooks` (token `UNIQUE`, con retry fino a 5 tentativi in
  caso di collisione, statisticamente irrilevante con 32 byte
  casuali ma comunque gestita), CRUD scoped per `guild_id`
- `core/custom_webhook_server.py` — l'endpoint aiohttp vero e
  proprio: `POST /webhook/<token>` → 404 se il token non esiste, 400
  se il corpo non è JSON valido, 502 se il canale Discord configurato
  non è più raggiungibile (con `logger.warning`, per capire da log
  quando un webhook è "morto" perché il canale è stato cancellato),
  200 se pubblicato

**Modifiche**: `core/config.py` (nuovi campi
`ALERTS_WEBHOOK_HOST/PORT/PUBLIC_BASE_URL`, porta di default 8421,
deliberatamente diversa da `RESTORE_WEB_PORT=8420` per permettere ai
due server aiohttp di girare insieme sulla stessa macchina senza
collisione); `cogs/utility/feed_alerts.py` (nuovo comando `/alerts
webhook-create`, `/alerts remove` estende il prefisso a `WH-<id>`,
`/alerts list` mostra anche i webhook); `core/database.py` e
`tests/conftest.py` (migrazione della nuova tabella agganciata nei
due punti previsti dal pattern del progetto); `main.py` (avvio
incondizionato del nuovo server, con un log informativo se
`ALERTS_WEBHOOK_PUBLIC_BASE_URL` non è configurata — il comando
funziona comunque, mostra solo il token nudo invece dell'URL
completo); `.env.example` (nuova sezione documentata).

**41 nuovi test**: 21 in `tests/test_custom_webhook_logic.py`, 10 in
`tests/test_custom_webhook_repo.py` (contro Postgres reale via
`clean_db`), 5 in `tests/test_custom_webhook_server.py` (richieste
HTTP vere via `aiohttp.test_utils.TestClient`/`TestServer`, senza
socket reale), 6 nuovi in `tests/test_feed_alerts_behavior.py` (più
il retrofit di 2 test preesistenti che non avevano ancora il mock
del nuovo `custom_webhook_repo`, rotti dall'estensione di
`list_alerts`), 1 assert estesa in
`tests/test_feed_alerts_cog_smoke.py`.

**Bug di test evitato**: `core.config.Config` è un
`@dataclass(frozen=True)` — `monkeypatch.setattr(config_istanza,
"CAMPO", valore)` alza `FrozenInstanceError`. Seguito il pattern già
stabilito nel progetto (visto in `tests/test_twitch_watcher.py`): si
sostituisce l'intero riferimento al modulo `config` con una classe
finta minimale che espone solo il campo serve
(`monkeypatch.setattr(modulo, "config", classe_finta())`), non il
singolo campo.

SPEC.md: §10.8 passa a `[x]` (era `[~]`), testo riscritto per
descrivere cosa è stato costruito e la distinzione tecnica rispetto
a EventSub/PubSubHubbub (nuova nota tecnica separata, non confusa
con quella su Twitch/YouTube/Reddit polling). Ricalcolo meccanico:
totale schema **166/2/105 su 273, ≈61%**.

**Verificato con la regressione anti-collisione comandi**
(`tests/test_cog_manager_load_all.py`, introdotta nella Fase 63):
`webhook-create` non collide con nessun altro comando esistente, e
tutti i cog continuano a caricarsi insieme senza errori.

**Suite di test completa: 1598/1598 passano** (verificato due volte
di fila).

---

## BACKLOG.md — analisi delle proposte di Gemini/ChatGPT/Grok

L'utente ha esposto `SPEC.md` a tre AI in sequenza, ricevendo
proposte che portavano lo scope da 266 a oltre 400 voci. Lette le tre
trascrizioni per intero (non solo la sintesi di Grok), classificate
in `BACKLOG.md` per 13 cluster tematici con verdetto esplicito.

Punti salienti trovati durante l'analisi, non presi per buoni dalle
tre AI:
- **Contraddizione interna in `SPEC_v2`**: vieta il Message Content
  Intent "finché non necessario" ma le proprie proposte AI Digest/
  Smart Ping lo richiedono comunque — e comportano l'invio dei
  messaggi utente a Groq/Google, un problema GDPR mai menzionato
- **Regressione**: il Passport/Trust Score proposto reintroduce la
  reputazione cross-server da sanzioni che `SPEC.md` §4.3 aveva già
  scartato esplicitamente — **RESPINTA**, non rimandata
- **Compromesso Forum-per-logging corretto**: membri è l'unica
  dimensione ad alta cardinalità (un raid crea centinaia di thread
  proprio quando servono di meno)
- **Event Bus a 4 livelli RESPINTO**: discord.py fornisce già un
  event bus nativo, il problema concreto (query duplicate ad ogni
  messaggio) risolto da una cache a costo molto minore — quella
  cache è ora la priorità #1 del backlog accettato

Regola aggiunta permanentemente in Decisioni prese: qualunque
proposta esterna passa da `BACKLOG.md` prima, mai direttamente in
`SPEC.md`.

---

## 🐛 Bug reale trovato e risolto durante Moderation — da conoscere

`core/premium.py`, decorator `@requires_module`: la prima versione
avvolgeva la funzione del comando in un `wrapper` con
`functools.wraps`. Funzionava per `case_system.py` ma **falliva in
modo silenzioso** al caricamento di `clear.py`, con:

```
NameError: name 'MAX_CLEAR_AMOUNT' is not defined
```

Causa: `functools.wraps` copia nome, docstring, annotazioni — ma
**non può copiare `__globals__`**, che appartiene al modulo dove la
funzione è stata *definita*. Il wrapper viveva in `core/premium.py`,
quindi quando discord.py doveva risolvere
`app_commands.Range[int, 1, MAX_CLEAR_AMOUNT]`, cercava
`MAX_CLEAR_AMOUNT` nei globals di `core/premium.py`, non di
`clear.py`, e non lo trovava. `case_system.py` era passato per caso:
usava solo tipi (`discord.Member`, `int`, `str`) già visibili perché
`core/premium.py` importa `discord`.

**Soluzione**: `@requires_module` ora usa `app_commands.check()`
(il meccanismo nativo di discord.py per i controlli sui comandi),
che aggiunge un predicato SENZA MAI sostituire la funzione originale
— il callback che discord.py ispeziona resta sempre quello vero, con
i suoi `__globals__` corretti. Il predicato solleva
`ModuleNotUnlockedError`/`PremiumCheckOutsideGuildError`, gestite da
un error handler globale (`handle_app_command_error`, registrato in
`main.py` con `self.tree.error(...)`).

**Perché resta scritto qui**: qualunque futuro comando premium che
usi una costante locale in un'annotazione (`Range`, o altro) andrebbe
incontro allo stesso problema se `@requires_module` tornasse a un
wrapper con `functools.wraps`. Non "semplificarlo" in futuro senza
rileggere questa nota.

---

## 🐛 Secondo bug reale — merge AutoMod a due vie non permetteva la rimozione

Durante la scrittura di `cogs/automod/automod.py`: la prima versione
di `core/automod_sync.py` faceva un merge "esistenti ∪ nuove" — corretto
per non cancellare mai parole aggiunte a mano dall'admin, ma con una
conseguenza non voluta: **`/automod badword-remove` non aveva alcun
effetto reale sulla regola Discord**, perché una parola rimossa dalla
configurazione salvata restava comunque nell'unione con "esistenti"
(che la includeva ancora, dal sync precedente).

**Soluzione**: merge a TRE vie. Si traccia (`automod_last_synced`,
per nome regola) cosa iYokai stesso ha scritto nell'ultimo sync
riuscito. Al sync successivo:

```
finale = (esistenti − ciò che avevamo scritto noi l'ultima volta)
         ∪ (ciò che vogliamo ORA)
```

La prima parte isola ciò che è presumibilmente dell'admin (resta per
sempre); la seconda riflette la configurazione attuale (una parola
rimossa da lì sparisce davvero, a meno che l'admin non l'abbia anche
aggiunta di suo). Se non risulta mai stato tracciato nulla per una
regola (bot appena aggiornato), tutto il contenuto esistente viene
trattato come "dell'admin" — la scelta prudente di default.

Aggiunto anche un quarto tipo di azione, `DELETE`: se dopo il merge
non resta più nulla da tenere (né admin né iYokai), la regola va
eliminata, non aggiornata a vuoto — Discord rifiuta una regola
keyword senza contenuto.

**Perché resta scritto qui**: qualunque futuro modulo che sincronizzi
uno stato "posseduto in parte da noi, in parte dall'utente" (non solo
AutoMod) rischia lo stesso problema con un merge a due vie. Il pattern
corretto è sempre: traccia cosa hai scritto tu l'ultima volta, sottrai
quello dall'attuale per isolare l'altrui, poi unisci con il nuovo tuo.

---

## 🚧 Cosa manca → vedi SPEC.md

**La lista di cosa resta da fare NON vive più in questo file.**

È in **[`SPEC.md`](SPEC.md)**, che contiene lo schema originale
trascritto foglia per foglia con lo stato reale verificato contro il
codice, non contro un riassunto.

### Perché è stato spostato

Questo file conteneva una roadmap che io (Claude) avevo *derivato*
dallo schema originale, riassumendolo. Quella compressione ha fatto
sparire senza segnalarle:

- **§4 Verify + Fingerprint + Anti-Alt** — intera sezione
- **§7 Security Suite** (Anti-Raid, Anti-Nuke, Spam Trap, Permission
  Auditor, Security Score) — intera sezione
- **§14 Utility & Server Management** (reaction roles, welcome,
  autoresponder, custom command request, snipe, sticky, suggestion,
  poll, reminder…) — intera sezione
- **§16 Fun & Immagini** — intera sezione
- **§1.3 Memory Guard** — requisito centrale del progetto (Oracle
  Free Tier), mai scritto
- **B. iYokai Application** (user-installable) — mai tracciata
- e decine di foglie dentro sezioni che avevo segnato "COMPLETA"

Peggio: quando l'utente me l'ha fatto notare, per tre volte di fila
ho "verificato" ricostruendo a memoria invece di rileggere lo schema,
trovando ogni volta un insieme diverso di buchi. La causa non era la
singola dimenticanza, era **aver usato un riassunto come fonte di
verità**.

### Regola da qui in avanti

Ogni sessione parte da `SPEC.md`. Le fasi marcate "COMPLETA" qui
sotto restano valide **solo per le voci che SPEC.md segna `[x]`** —
diverse di esse hanno foglie ancora mancanti, elencate lì.

Stato reale aggiornato: la tabella conteggiata meccanicamente vive
**solo** in fondo a `SPEC.md`, non qui — per non dover tenere lo
stesso numero sincronizzato in due file ad ogni fase completata (è
esattamente il tipo di duplicazione che aveva causato il problema
originale). La base (core, verify base, moderazione, automod,
logging, ticket, vocali temporanei, livelli/economia, memory guard,
spam trap) è solida e testata, ma resta una minoranza dello schema
completo — la percentuale esatta è in `SPEC.md`, sempre aggiornata
lì e lì soltanto.

---

## 📐 Decisioni prese (da rispettare in ogni sviluppo futuro)

Queste non sono suggerimenti: sono vincoli verificati sulle API
Discord reali. Se in una sessione futura sembra di poter "semplificare"
uno di questi punti, **rileggere prima il motivo** — quasi sempre è già
stato scartato per un limite tecnico specifico.

- **Qualunque proposta esterna (altre AI, idee future) passa prima
  da `BACKLOG.md`, mai direttamente in `SPEC.md`.** Nato dopo che
  l'utente ha esposto `SPEC.md` a Gemini, ChatGPT e Grok in
  sequenza: le tre proposte insieme portavano lo scope da 266 a oltre
  400 voci. Chiedere a un LLM "cosa miglioreresti" produce quasi
  sempre aggiunte, mai "va bene così" — è il tipo di domanda che lo
  garantisce. `BACKLOG.md` classifica ogni proposta (ACCETTATA /
  RESPINTA + motivo / RIMANDATA + condizione) prima che tocchi lo
  scope reale. Una singola proposta interessante non è mai un motivo
  sufficiente per saltare questo passaggio.
- **Ogni push va verificato con una chiamata API GitHub diretta,
  non con il solo output di `git push`.** In una sessione, il remote
  URL era rimasto senza token (rimosso a fine sessione precedente per
  sicurezza, mai re-impostato prima del `git fetch` successivo): il
  fetch falliva silenziosamente con un errore facile da non notare
  in mezzo all'output, la comparazione `git log HEAD..origin/main`
  restava su un `origin/main` STANTIO, e 5 commit reali sono rimasti
  solo locali per un intero turno di conversazione — riportati
  erroneamente come "pushati". Scoperto solo perché l'utente ha
  chiesto esplicitamente una verifica. Procedura corretta, da
  ripetere ad ogni push: `git rev-parse --short=12 HEAD` in locale,
  poi `GET https://api.github.com/repos/.../commits/main` con il
  token, e confrontare i due SHA esplicitamente prima di dire
  "pushato" all'utente.
  **Aggiornamento**: `python3 -c "... json.load(sys.stdin) ..."` su
  quella risposta può fallire con `JSONDecodeError` se il messaggio
  di commit contiene caratteri che il parser JSON tratta come
  "control character" (successo con messaggi di commit multi-riga
  contenenti determinati caratteri) — un fallimento di PARSING, non
  un vero disallineamento, ma che SEMBRA un disallineamento se non
  investigato (l'eccezione fa sembrare la verifica fallita). Estrarre
  lo sha con `grep -o '"sha": "[a-f0-9]*"'` sulla risposta grezza
  invece di affidarsi a un parsing JSON completo — più robusto e
  sufficiente per questo scopo (serve solo lo sha, non l'intero
  oggetto). Se il confronto sha sembra fallire, riprovare con questo
  metodo prima di assumere un vero disallineamento.
- **Niente caricamento/scaricamento di cog per singolo server.** Un
  bot ha un solo processo condiviso da tutti i server. Il modo
  corretto per attivare/disattivare un modulo per server è un check a
  runtime a inizio comando (vedi `cogs/utility/ping.py`).
- **Ogni listener di un Cog richiede il decorator esplicito
  `@commands.Cog.listener()`.** Un metodo chiamato `on_member_join`
  senza quel decorator NON viene registrato da discord.py — resta un
  metodo Python normale che Discord non chiamerà mai, senza alcun
  errore o avviso. Verificato empiricamente prima di scrivere
  `cogs/logging/basic_logs.py` (vedi quel file e il suo smoke test,
  che controlla esplicitamente `bot.extra_events`). Ogni futuro cog
  con listener di eventi deve includere questo controllo nel proprio
  smoke test, non solo "il cog si carica".
- **Un pannello con bottoni che deve restare cliccabile a lungo
  termine richiede una View persistente**, non una normale
  `discord.ui.View` con timeout. Serve `timeout=None` + `custom_id`
  esplicito su ogni componente, e `bot.add_view(...)` va richiamato
  ad OGNI avvio del bot (non solo alla prima pubblicazione del
  pannello), altrimenti i bottoni dei pannelli già esistenti nei
  server smettono di rispondere dopo ogni riavvio. `bot.add_view()`
  solleva `ValueError` se la view non è persistente — verificato
  prima di scrivere `cogs/tickets/tickets.py`. Ogni futuro pannello
  con bottoni "a vita lunga" (non un menu temporaneo come `/setup`)
  deve seguire lo stesso pattern.
- **`discord.ui.TextInput(label=...)` è un'API deprecata in
  discord.py 2.7.1** — produce un `DeprecationWarning` reale a runtime
  (verificato, non solo scritto nella changelog). Il pattern corretto
  è `discord.ui.Label(text=..., component=TextInput(...))`, che
  avvolge il `TextInput` invece di dargli un'etichetta diretta. Il
  riferimento al `TextInput` per leggerne `.value` in `on_submit`
  resta valido tenendolo come attributo proprio (istanza o dentro il
  `Label.component`), a seconda di come viene costruito. Trovato
  scrivendo `CaptchaModal` (`cogs/security/verify.py`) e corretto
  ANCHE in `StaffReplyModal` (`cogs/security/spam_trap.py`, scritto
  prima con lo stesso pattern vecchio) — ogni futuro `Modal` con
  `TextInput` deve usare `Label`, non `label=`.
- **`POST /guilds` funziona solo per bot sotto i 10 server.** iYokai
  Main (il bot principale) non creerà mai server. La creazione dei
  server di backup è delegata a **iYokai Creator**, un'applicazione
  separata che crea, trasferisce subito la ownership al cliente, e
  esce — non resta mai owner. Timeout di 24h: se l'owner non entra
  nel server di backup entro 24h, la funzione si spegne per quel
  server e lo slot si libera.
- **Niente pool di più account "Creator" per aggirare il limite dei
  10 server.** Rischio concreto di essere letto come comportamento
  di abuso coordinato. Un solo Creator con coda seriale; se il volume
  lo giustificherà, si chiederà un innalzamento del limite a Discord
  Developer Support.
- **Una sola connessione vocale per server per ogni account bot.**
  Music multi-canale nello stesso server richiede 5 applicazioni bot
  separate (Music #1..#5), non una sola istanza "furba".
- **Message Content Intent**: va richiesto solo quando un modulo lo
  richiede davvero (log messaggi cancellati, automod comportamentale),
  motivazione dichiarata onestamente in fase di review — mai come
  giustificazione per l'archiviazione massiva di messaggi.
- **Scope OAuth2 separati**: `identify` per il verify avanzato,
  `guilds.join` SOLO per il modulo restore utenti, richiesti in
  flussi distinti — mai insieme.
- **Fingerprint anti-alt**: IP mai in chiaro nel DB (solo hash del
  fingerprint composito), un match produce segnalazione allo staff
  (non ban automatico), ban automatico consentito solo su match
  multipli e solo entro lo stesso server (mai cross-server).
- **Anti-farm XP vocale**: nessun XP se `self_deaf`, nessun XP se soli
  nel canale, nessun XP in canale AFK, azzeramento dopo 2 ore
  consecutive nello stesso canale, cap giornaliero di ore conteggiabili.
- **Ruoli Capo Clan / Admin Clan**: un solo ruolo condiviso per
  "Capo Clan" e uno per "Admin Clan" (Discord non permette due ruoli
  alla stessa posizione gerarchica), permessi reali dati come
  overwrite per-utente sulla categoria della propria gilda — così
  restano isolati tra loro pur condividendo il ruolo Discord.
- **Niente modulo selfbot.** Sostituito da **iYokai Desktop**, app
  locale che usa il socket RPC del client Discord — nessun user
  token, nessun rischio ban per l'utente finale.
- **NSFW su applicazione separata** (`iYokai NSFW`), filtro a due
  strati sempre attivi: allowlist decisa dal server + blocklist
  hardcoded non modificabile, applicati sia alla ricerca manuale sia
  all'auto-post.
- **Spam Trap — sequenza fissa, non modificabile nell'ordine:**
  1. Cattura il contenuto del messaggio trappola
  2. **DM di preavviso all'utente PRIMA del ban** (dopo il ban il bot
     non può più aprire un DM: non c'è più un server in comune)
  3. Ban con `delete_message_seconds` (max 7 giorni, limite Discord)
  4. Purge supplementare via indicizzazione DB per andare oltre i 7
     giorni (bulk_delete nativo copre solo 14 giorni comunque)
  5. Cleanup webhook/inviti creati dall'utente
  6. Embed di log completo in `#spam-log`
  - Ban appeal: il DM aperto al punto 2 resta utilizzabile anche a
    ban avvenuto → apre un thread privato in `#spam-log`, mai DM
    diretto agli admin
  - Transcript HTML: allegati Discord hanno URL firmati che scadono
    (~24h) — se servono immagini visibili nel transcript, vanno
    rigenerate come thumbnail (decodifica → resize → ricodifica),
    mai riospitato il file originale as-is
- **Database**: un solo cluster PostgreSQL, `guild_id` come colonna
  indicizzata su ogni tabella condivisa. **Niente database/schema
  separato per server** — a 10.000 server il catalogo di sistema e il
  connection pooling ne risentirebbero pesantemente. Partizionamento
  nativo (`PARTITION BY HASH(guild_id)`) riservato alle sole tabelle
  che davvero esplodono in dimensione (attività XP, log spam trap),
  da attivare quando il volume lo richiede — lo schema logico non
  cambia tra prima e dopo.

---

## 🗂️ Le applicazioni Discord del progetto

| Nome | Stato | Note |
|---|---|---|
| iYokai Main | **in sviluppo (questa repo)** | Core. Deve passare la review Discord per superare i 100 server |
| iYokai Creator | da creare | Backup: crea server, cede ownership, esce. Sempre sotto i 10 server |
| iYokai Music #1-5 | da creare | Una connessione vocale ciascuna |
| iYokai NSFW | da creare | Isolata per non appesantire la review del core |
| **iYokai Application** | **da creare** | User-installable (`USER_INSTALL`): comandi in qualsiasi server/DM. **Era stata omessa da questa tabella** |
| iYokai Desktop | da creare | App locale, presence via RPC IPC, nessun user token |
| iYokai Panel | da creare | Web: verify avanzato, OAuth2, dashboard owner |

---

## 🔜 Prossimo passo concreto

**§15 Levels/Economy/Gilde/Classifiche a 9/25** — notifica level-up
vocale, ruoli-premio e annuncio vincitori mensile fatti. Prossimi pezzi ben delimitati, senza
bisogno di discussione preventiva:
- **15.6** Drop messages — comparsa casuale di coin da reclamare nei
  messaggi, primo che clicca/reagisce vince
- **15.5** Giveaway (con requisiti di ruolo/livello) — creazione,
  partecipazione, estrazione vincitore

**15.14 Sistema Gilde/Clan — aggiornamento Fase 48: il motore
economico di backend è ora completo e testato** (tesoreria con
ledger, XP/classifica di gilda, tracciamento vocale con
anti-farm/decadimento/tetto giornaliero, decadimento mensile 10%
sulla tesoreria non spesa, costi/progressione di acquisto canale).
**Resta tutto il lato Discord**: creazione reale di categoria/canali,
ruoli Capo/Admin Clan pari tra gilde diverse (overwrite per-utente),
isolamento applicato nei comandi, boost XP/coin, requisito ore
vocali dedicato per lo sblocco canale, e ogni comando slash (zero
scritti finora). Nuovo §15.15 aperto nello stesso giro: decadimento
settimanale sui coin personali di chiunque + cassa di server + un
premium a doppio sblocco (tempo dal join del bot + costo variabile
dalla cassa) — solo la logica pura del decadimento personale è
pronta, il resto ancora da costruire e in parte da confermare con
l'utente (numeri esatti del premium).

**Backup System (§11) resta con solo le 3 voci delicate aperte**
(mirror messaggi, OAuth2, auto-propagazione), da discutere con
l'utente prima di scrivere codice.

⚠️ **REGOLE PERMANENTI**:
1. Dopo ogni commit che tocca i comandi slash, rilanciare
   `scripts/generate_command_list.py` e pushare `COMMAND_LIST.md`
   nello stesso giro.
2. Marcare `SPEC.md` SUBITO dopo il commit del codice, nello stesso
   giro. Usare il marcatore parziale (`~`) quando è vero. Un rifiuto
   esplicito dell'utente va marcato SCARTATO (✗), non lasciato vuoto.
   Ricalcolare SEMPRE con lo script meccanico, mai a mente, e MAI
   scrivere il pattern letterale di un marcatore dentro un testo di
   prosa esplicativa.
3. Quando due tabelle diverse usano ID SERIAL indipendenti ma
   vengono mostrate/gestite insieme all'utente, usare prefissi
   distinti nell'ID visibile.
4. Prima di progettare una feature che tocca file locali o risorse
   di sistema specifiche di UNA macchina, verificare con una ricerca
   se l'infrastruttura usata ha effettivamente accesso a quella
   risorsa.
5. Prima di una feature con implicazioni architetturali importanti,
   fare le domande giuste all'utente PRIMA di scrivere codice.
6. Prima di assumere che un'azione sia automatizzabile via API,
   verificare con una ricerca i limiti REALI della piattaforma
   Discord.
7. Per estendere una tabella già esistente, usare `ALTER TABLE ...
   ADD COLUMN IF NOT EXISTS` — idempotente, sicuro da rilanciare.
8. Quando una richiesta implica automazione che assomiglia a
   selfbotting/account secondari automatizzati, verificare i Termini
   di Servizio della piattaforma prima di costruire.

Promemoria tecnici aggiuntivi:
- Verificare collisioni con hook riservati di discord.py prima di
  nominare un metodo di cog
- Verificare idempotenza di qualunque `register()`/simile chiamato
  da `setup()`, per non rompere `/owner cog-reload`
- Prima di usare `await` su una libreria esterna dentro `setup()`,
  verificare con un test diretto se può bloccare indefinitamente
- Prima di aggiungere un listener duplicato su più bot/cog per lo
  stesso evento, verificare nel sorgente della libreria se esiste
  già un meccanismo interno che lo gestisce indipendentemente
- Su una property di sola lettura di una classe discord.py, un fake
  che eredita dalla classe vera deve SOVRASCRIVERE la property
- Prima di passare `bytes` grezzi a `discord.File`, avvolgerli
  sempre in `io.BytesIO`
- In SQL dentro una stringa Python, i commenti usano `--`, non `#`
- Se un cog avvia un task periodico nel proprio `__init__` (non in
  `setup()`), una fixture di test che lo istanzia deve essere
  ASINCRONA (non sincrona) per avere un event loop attivo, e va
  fermata subito con `cog_unload()`/`.cancel()` — trovato nella
  Fase 43

**Limite d'ambiente da ricordare**: la rete del sandbox di sviluppo è
ristretta a un elenco fisso di domini (PyPI, npm, GitHub) — non
raggiunge Discord/Twitch/Lavalink nemmeno con credenziali vere. Ogni
test di integrazione con questi servizi resta simulato; la verifica
dal vivo tocca all'utente.

**Nota per una futura sessione**: PROGRESS.md ha superato le 2000
righe — potrebbe valere la pena consolidare le fasi più vecchie
quando si ha tempo, per restare più navigabile. Non urgente.

Metodologia acquisita: `scripts/load_simulation.py` per misurare per
davvero invece di stimare a tavolino — vedi il suo stesso docstring.
