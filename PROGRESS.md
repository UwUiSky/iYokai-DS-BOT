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

**Music multi-istanza (SPEC.md §9) ha un'architettura reale e
funzionante** — main + 5 worker instradati, verificabile dal vivo
solo con credenziali vere (impossibile in questo sandbox: servono 6
token Discord veri e una connessione Lavalink reale). Due punti
aperti, da chiarire con l'utente prima di costruirli:
1. Auto-leave su canale vuoto (§9.9) — l'evento esiste già in
   wavelink di default, manca solo il listener che agisce
2. "Singolo decoder condiviso" per /nonstop-main (§9.11) — costruito
   per un server alla volta, dubbio se l'utente intendeva trasmettere
   la stessa playlist a più server insieme

**Due grandi pezzi ancora da discutere con l'utente prima di
costruire**, entrambi con vincoli tecnici reali:
1. **Alert & Social multi-piattaforma**: Twitch pronto non appena
   arrivano le credenziali dell'utente (Client ID/Secret da
   dev.twitch.tv). TikTok (nessuna API ufficiale, solo scraping
   fragile), Instagram (già scartato ✗, nessuna API per account di
   terzi), X/Twitter (lettura a pagamento nel tier utile) — chiedere
   esplicitamente prima di costruire qualcosa di fragile o a
   pagamento senza consenso
2. Nient'altro di grande bloccato al momento

**§11 Backup System resta l'unica sezione ancora completamente a
zero.** §15 Levels/Gilde/Classifiche parzialmente fatta (6/25).

⚠️ **REGOLE PERMANENTI**:
1. Dopo ogni commit che tocca i comandi slash, rilanciare
   `scripts/generate_command_list.py` e pushare `COMMAND_LIST.md`
   nello stesso giro.
2. Marcare `SPEC.md` SUBITO dopo il commit del codice, nello stesso
   giro. Usare il marcatore parziale (`~`) quando è vero — l'utente
   ha dovuto correggere che non veniva mai usato nonostante esistesse
   da sempre nella legenda. Un rifiuto esplicito dell'utente (non un
   limite tecnico) va marcato SCARTATO (✗), non lasciato vuoto — si
   esclude dal conteggio totale, come Instagram, Howgay, filtri audio/
   DJ role/voteskip. Ricalcolare SEMPRE con lo script meccanico, mai a
   mente, e MAI scrivere il pattern letterale di un marcatore dentro
   un testo di prosa esplicativa (falso positivo nel conteggio —
   successo tre volte in questa sessione).

Promemoria tecnici aggiuntivi:
- Verificare collisioni con hook riservati di discord.py prima di
  nominare un metodo di cog
- Verificare idempotenza di qualunque `register()`/simile chiamato
  da `setup()`, per non rompere `/owner cog-reload`
- Prima di usare `await` su una libreria esterna dentro `setup()`,
  verificare con un test diretto se può bloccare indefinitamente
  invece di fallire rapidamente
- Prima di aggiungere un listener duplicato su più bot/cog per lo
  stesso evento, verificare nel sorgente della libreria se esiste
  già un meccanismo interno che lo gestisce indipendentemente dal
  client Discord (come `player._auto_play_event()` in wavelink)

Metodologia acquisita: `scripts/load_simulation.py` per misurare per
davvero invece di stimare a tavolino — vedi il suo stesso docstring.
