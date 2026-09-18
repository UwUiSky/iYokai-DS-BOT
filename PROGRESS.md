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

**Welcome/Goodbye/Boost (SPEC.md §14.4-14.6) completato.** Zero voci
parziali, invariato.

**`BACKLOG.md` scritto e valutato.** La mia priorità #1 lì dentro,
`ACCETTATA-PRESTO`: cache della configurazione moduli per server
(`BoundedCache` già costruita, §1.5), perché risolve un problema di
performance già presente ora — ogni cog che condivide `on_message`/
`on_raw_reaction_add` (leveling, spam_trap, verify, role_menus,
greetings — 5 moduli e in crescita) fa una query DB separata per
controllare se il proprio modulo è attivo, ad ogni singolo evento.

Le altre priorità del backlog accettato, in ordine (vedi `BACKLOG.md`
§ Riepilogo numerico): softban + mute via ruolo + reason obbligatorio
+ mod-log channel (chiudono gap già noti in `SPEC.md` §5), poi Config
Diff & Rollback / Permission Heatmap / Escalation Ladder (estendono
moduli già previsti), poi logging multi-indice su DB.

Nessuna priorità imposta in modo vincolante — la decisione resta
dell'utente. Ricordarsi SEMPRE, prima di scrivere codice: leggere
`SPEC.md`, non un riassunto. E qualunque proposta esterna futura
passa da `BACKLOG.md` prima di toccare `SPEC.md`.
