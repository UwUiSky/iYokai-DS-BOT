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

Stato reale a colpo d'occhio: **~46 voci fatte su ~265**, cioè circa
il 17-20% dello schema. La base (core, moderazione, automod, logging
base, ticket, vocali temporanei, livelli/economia) è solida e
testata, ma non è "quasi tutto tranne le Gilde".

---

## 📐 Decisioni prese (da rispettare in ogni sviluppo futuro)

Queste non sono suggerimenti: sono vincoli verificati sulle API
Discord reali. Se in una sessione futura sembra di poter "semplificare"
uno di questi punti, **rileggere prima il motivo** — quasi sempre è già
stato scartato per un limite tecnico specifico.

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

**Spam Trap (SPEC.md §7.3) completato — quasi al 100%.** Resta un
candidato ovvio come continuazione diretta, dato che condivide
infrastruttura appena costruita:

**§4 Verify + Fingerprint + Anti-Alt** — l'invite tracker
(`core/invite_tracker.py`) è già pronto e riusabile per il Verify
Base (mutual servers/invite tracker). Inoltre completerebbe il "ban
globale via fingerprint" rimasto `[ ]` in Spam Trap §7.3, collegando
i due moduli.

In alternativa, qualunque altra voce di `SPEC.md` resta ugualmente
legittima — la decisione è dell'utente, non un default.

**Promemoria operativo per la prossima sessione, dopo l'errore di
questa**: PRIMA di riportare qualunque lavoro come "pushato",
verificare esplicitamente che `git rev-parse HEAD` locale coincida
con lo SHA restituito da una chiamata API GitHub diretta
(`GET /repos/.../commits/main`), non fidarsi del solo output di
`git push`. In questa sessione 5 commit erano rimasti locali per un
intero turno di conversazione perché il remote URL non aveva il
token e il fetch falliva silenziosamente — scoperto solo perché
l'utente ha chiesto esplicitamente di verificare.
