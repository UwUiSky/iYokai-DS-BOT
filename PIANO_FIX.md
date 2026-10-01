# PIANO_FIX.md — Ordini di lavoro per la correzione di iYokai

Questo file dice **cosa** sistemare, **in che ordine** e **come**. Il
*perché* e i dettagli di ogni problema stanno in `REVIEW.md` (i codici
SEC-/BUG-/LC-/GDPR-/DB-/PERF- rimandano lì). Le issue GitHub sono
indicate con `#N`.

Regole di processo: `CLAUDE.md`. Regole sui test live e sui segreti:
`CLAUDE_MANDATORY_TEST_RULES.md` (vincolante, prevale su tutto).

Stato delle voci:
- `[ ]` da fare
- `[x]` fatto e testato offline (scrivi accanto lo SHA del commit)
- `[B]` bloccato da una decisione dell'owner (vedi §D)

Una voce `[x]` **non** è verificata live: quella verifica si traccia
in `VERIFICA_LIVE.md` (§V).

---

## 0. Analisi incrociata: REVIEW.md contro le 53 issue

Le issue #1–#35 sono lo stesso elenco di REVIEW.md, trovato in modo
indipendente. Le #36–#53 aggiungono decisioni e tre problemi nuovi.
Controllato di nuovo sul codice il 28/09:

| Punto | Esito |
|---|---|
| Moduli registrati | **32**, non ~37 come dicono #38/#43: le issue contano le righe `registry.register(`, alcune registrano lo stesso nome. REVIEW.md è corretto. |
| `/owner` | 25 sotto-comandi su 25 (L2). Non aggiungere niente a `/owner` prima di R5. |
| `automod` | 22 sotto-comandi su 25. |
| Top-level | 97 su 100. Non aggiungere comandi top-level prima di R5: usa sotto-comandi di gruppi esistenti. |
| BUG-17 / #33 (drop cliccato due volte) | **Probabile falso positivo.** In `cogs/leveling/leveling.py` tra `if self.claimed_by is not None` e `self.claimed_by = …` non c'è nessun `await`, quindi in asyncio il blocco è atomico. Si conferma con un test (fase R1), non con un fix. |
| #36 "log cancellati/modificati correttamente disattivati" | Superato dalla decisione dell'owner: `message_content` si accende e quei log vanno costruiti (R4). |
| #42 fix proposto "`asyncio.sleep(10)` poi `delete()`" | Va bene, ma dentro un task separato con log degli errori, non bloccando la risposta (vedi R1). |
| #47 `application.yml` | Le versioni dei plugin nell'issue vanno ricontrollate sulle pagine ufficiali al momento di scriverlo. Il percorso dei file locali è quello **dentro il container Lavalink** (`/audio/local`), non quello della macchina del bot (vedi BUG-10). |
| #50 (AI), #52 (confronto con altri bot) | Fuori scope di questo piano. Non aprire lavori su questi. |
| Bot senza utenti (regole live §2.4) | Nessun server reale usa il bot: **non serve retrocompatibilità** dei nomi comandi (decisione D4 raccomandata "nessuna") e la sicurezza sulla superficie dei comandi (SEC-1) si risolve una volta sola in R5 invece di decorare 97 comandi due volte. |

**Cambio d'ordine rispetto a REVIEW.md §17:** le migrazioni versionate
(DB-1) passano **prima** di R1, perché diversi fix di R1 aggiungono
vincoli `UNIQUE` o colonne a tabelle esistenti, e oggi lo schema sa
solo "crea se non esiste" / "aggiungi colonna se non esiste".

Ordine finale:

```
R-T  rete di test (resto)
R0   sicurezza lato logica
DB   migrazioni versionate
R1   bug che rompono funzioni
R1b  SPEC onesta
R2   dati e GDPR
R3   router dei canali
R4   message_content e log dei messaggi
R5   nuova struttura comandi (+ permessi e visibilità)
R6   lingue e /cerca-comando
R7   NSFW
Continuo: docstring, codice morto, prestazioni
```

---

## R-T — Rete di test (completare prima di qualsiasi fix)

Già fatto (commit con questo file):
- `tests/support/full_tree.py`: carica tutti i cog come il bot vero.
- `tests/support/command_policy.py` + `tests/test_command_policy.py`:
  chi deve vedere ogni comando; cricchetti `KNOWN_MISSING_DEFAULT_PERMISSIONS`
  e `KNOWN_NOT_GUILD_ONLY`.
- `tests/test_repository_callers.py`: ogni metodo pubblico dei
  repository ha un chiamante in produzione; cricchetto `KNOWN_UNCALLED`.

Come funziona un **cricchetto**: un insieme `KNOWN_*` contiene i
problemi aperti oggi. Il test fallisce se ne compare uno nuovo **e**
se uno dell'elenco è stato sistemato ma non tolto. Quando sistemi un
problema, togli il nome dall'insieme nello stesso commit. Non
aggiungere mai nomi a un cricchetto per far passare un test.

Da fare:

- [x] **RT-1 Oggetti finti fedeli** (b8848f1) — `tests/support/discord_fakes.py`.
  - Funzioni `fake_text_channel()`, `fake_voice_channel()`,
    `fake_forum_channel()`, `fake_member()`, `fake_guild()`,
    `fake_role()`, `fake_message()`, `fake_interaction()` costruite con
    `unittest.mock.create_autospec(discord.X, instance=True)`, con i
    metodi async (`send`, `delete`, `edit`, `add_roles`, `ban`, …) già
    impostati come `AsyncMock` con autospec.
  - Motivo: un finto con autospec rifiuta le firme sbagliate.
    Verificato: `channel.delete(delay=10)` solleva `TypeError`, cioè
    avrebbe trovato BUG-1.
  - `fake_interaction()` deve avere `response.is_done()`,
    `response.send_message`, `response.defer`, `followup.send`, e
    `guild`/`user`/`channel`/`permissions` impostabili.
  - Test `tests/test_discord_fakes.py`: un test per finto che dimostra
    che una chiamata con un argomento inesistente fallisce.
  - I test vecchi con finti scritti a mano **non** si riscrivono tutti
    adesso: si passano ai finti fedeli quando si tocca quel file.
- [x] **RT-2 Invarianti dell'albero comandi** (b8848f1) — `tests/test_command_tree_invariants.py`
  usando `full_tree`:
  - ogni gruppo ha al massimo 25 sotto-comandi e al massimo 1 livello
    di sotto-gruppi;
  - al massimo 100 top-level (esiste già in
    `tests/test_cog_manager_load_all.py`: non duplicarlo, spostalo qui
    solo se semplifica);
  - ogni `Select` costruito con dati reali ha al massimo 25 opzioni:
    per ora il pannello `/setup` con i 32 moduli reali (oggi fallisce:
    mettilo in un cricchetto `KNOWN_OVERSIZED_SELECTS = {"setup"}`).
- [x] **RT-3 Igiene della suite** (b8848f1): fixture `_rt3_igiene_risorse`
  (autouse) in modalità solo avviso, `pytest_terminal_summary` elenca
  le `aiohttp.ClientSession` non chiuse e le eccezioni di task per
  nodeid. Oggi 6 test caricano l'albero completo e lasciano 6 sessioni
  aperte ciascuno (worker musicali/Lavalink) — verrà chiuso quando lo
  shutdown pulito dei worker sarà sistemato (voce collegata più avanti
  nel piano). `reset_premium_registry`: fixture riusabile, non autouse.
- [x] **RT-4 Regola per ogni fix successivo** (b8848f1, applicata da qui
  in avanti — non è codice, è metodo): ogni fix di R0/R1 aggiunge un
  test che **esegue davvero il comando o il callback** con i finti
  fedeli, e che fallisce prima del fix. Controlla che fallisca **per
  il motivo giusto**, non per un import o una fixture sbagliata.

Criterio di fine R-T: suite completa verde due volte, i tre cricchetti
esistenti invariati, i nuovi test committati.

---

## R0 — Sicurezza lato logica

Qui si sistema tutto quello che è sicurezza **dentro** i comandi e i
servizi. La visibilità dei comandi (SEC-1, LC-2, #3, #24, #31, #40) si
fa in R5 insieme alla nuova struttura: il bot non ha utenti, quindi
non c'è motivo di decorare due volte 97 comandi.

**Aiuto condiviso da creare per primo:** `core/role_safety.py`
```
check_role_assignable(guild, role, actor, *, self_service: bool) -> str | None
```
Restituisce `None` se va bene, altrimenti il motivo in italiano. Rifiuta
se il ruolo:
- è `@everyone` o gestito da un'integrazione (`role.managed`);
- è uguale o sopra il ruolo più alto del bot;
- è uguale o sopra il ruolo più alto di `actor` (salvo il
  proprietario del server);
- con `self_service=True` (ruoli che un utente ottiene da solo: shop,
  level-roles, role menu, verify, ruolo piattaforma dei vocali): ha
  uno di questi permessi: `administrator`, `manage_guild`,
  `manage_roles`, `manage_channels`, `ban_members`, `kick_members`,
  `moderate_members`, `manage_webhooks`, `mention_everyone`.

Va chiamato **due volte**: quando l'admin configura il ruolo e quando
il bot lo assegna (il ruolo può aver cambiato permessi nel frattempo).

- [x] **SEC-4 / SEC-17 (#10, #14, #29, #32)** (599a2d4) `check_role_assignable`
  collegato in `/shop add-item` + `/shop buy`, `/level-roles add` +
  assegnazione automatica di livello, `/rolemenu add-option` + click
  bottone/select + reazione, `/verify setup` + assegnazione a fine
  verifica, `/voicetemp-platform-setup` + click bottoni piattaforma.
  Test (tests/test_role_safety_wiring.py): per ognuno dei 5 comandi
  di configurazione, un ruolo con `administrator` viene rifiutato —
  eseguito davvero il callback con i finti fedeli, confermato che
  fallisce senza il collegamento (verificato con `git stash` sui
  file dei cog prima del commit). "(da verificare live)": serve una
  prova su un server Discord reale per i tre percorsi di assegnazione
  automatica (livello, verify, click su rolemenu/vocali) — vedi
  VERIFICA_LIVE.md.
- [x] **SEC-2 (#15)** (15ddf7d) `/restore-users`: accetta solo se
  esiste una coppia con `main_guild_id == origine` e
  `backup_guild_id == interaction.guild.id`. Senza coppia: rifiuta
  con messaggio chiaro. Controllo fatto con
  `core/repositories/backup_repo.py:get_pair`, prima ancora di
  leggere lo snapshot. Test in tests/test_restore_cog_behavior.py:
  nessuna coppia, coppia verso un terzo server, coppia corretta (i
  test già esistenti sono stati aggiornati per definire la coppia
  dove il restore deve riuscire — confermato che fallivano senza il
  fix, `AttributeError` sul modulo che non importava ancora
  `backup_repo`).
- [x] **SEC-3 (#8)** (4d5e4a4) OAuth del restore:
  - `state` firmato in `core/restore_oauth_logic.py`:
    `base64(payload) + "." + HMAC-SHA256`, con dentro origine,
    destinazione, scadenza (10 minuti) e un nonce monouso (dizionario
    in memoria con pulizia lazy, non serve altro: uno state vive al
    massimo 10 minuti e un riavvio del bot lo invalida comunque).
    Chiave: derivata con HKDF da `OAUTH_ENCRYPTION_KEY` già
    esistente (nessuna nuova variabile da configurare, mai la stessa
    chiave riusata per due scopi);
  - **niente `user_id` nello state**: `build_authorize_url` non lo
    accetta più. Dopo lo scambio del code, `RestoreOrchestrator.
    fetch_current_user` chiama `GET /users/@me` con l'access token e
    quell'ID (mai uno scritto nello state) è quello usato per
    salvare il token/aggiungere al server/assegnare il ruolo;
  - confronto della firma con `hmac.compare_digest`.
  Test: tests/test_restore_oauth_logic.py (state manomesso, firma
  sbagliata, chiave sbagliata, scaduto, riusato, senza chiave
  configurata), tests/test_restore_web_server.py (stessi casi a
  livello di endpoint + identità non verificabile da /users/@me),
  tests/test_restore_orchestrator.py (fetch_current_user con token
  valido/invalido contro un server aiohttp finto).
- [x] **SEC-5 (#7)** `/nonstop-main` diventa owner-only subito (controllo
  `OWNER_ID` a runtime; lo spostamento sotto `/owner` avviene in R5).
  Il nome file di `add-local` si valida come in BUG-10. — commit bde6f00
- [x] **SEC-6 (#17)** Sostituisci `str.format` in
  `core/feed_parsing_logic.py` e `core/custom_webhook_logic.py` con una
  funzione `render_template(testo, valori: dict[str, str]) -> str` in
  `core/`: sostituisce solo `{nome}` con una regex `\{([a-z_]+)\}`,
  ignora le chiavi sconosciute lasciandole com'erano, niente format
  spec, output troncato a 2000 caratteri. `{` spaiato non è un errore.
  Test: `{title:>999999999}` resta testo, `{` spaiato non solleva. — commit 25c3cdc
- [x] **SEC-7 (#5)** `allowed_mentions=discord.AllowedMentions(everyone=False,
  roles=False, users=True, replied_user=False)` nel costruttore di
  **ogni** bot (principale, Creator, worker musicali, e NSFW quando
  nascerà). Dove un ping di ruolo è voluto (ruolo supporto ticket,
  ruolo degli alert) passa `allowed_mentions` esplicito solo in quella
  `send`. Cerca tutti i punti con `grep -rn "role.mention\|<@&"`.
  Test: il bot costruito ha il valore giusto; i due o tre punti voluti
  passano il ruolo esplicitamente. — commit cb05eff (nessun punto del
  codice oggi pinga davvero un ruolo, quindi nessuna eccezione
  per-send è servita)
- [x] **SEC-8 (#9)** SSRF nei feed: modulo `core/safe_http.py` con
  `safe_get(url, max_bytes=2_000_000)`:
  - solo `http`/`https`, porte 80 e 443;
  - risolve il nome e rifiuta IP privati, loopback, link-local,
    multicast e riservati (`ipaddress`), sia IPv4 che IPv6;
  - redirect disattivati e seguiti a mano (massimo 3), ricontrollando
    ogni destinazione;
  - lettura a blocchi con limite di byte e timeout totale.
  Usalo in `feed_watcher` e in ogni fetch di URL scelto da un utente.
  Test: `http://127.0.0.1:8420`, `http://169.254.169.254`, un redirect
  verso IP privato e una risposta troppo grande vengono rifiutati
  (server di test locale con `aiohttp.test_utils`). — commit a28f817
  (`core/twitch_watcher.py`/`core/youtube_watcher.py` non toccati:
  URL fissi in codice, mai scelti da un utente, nessun rischio SSRF)
- [x] **SEC-8b (#11)** Spam-trap: esenta chi ha `manage_messages`,
  `administrator`, i ruoli staff configurati o un ruolo sopra quello del
  bot, e non propagare al global-ban in quei casi. I bottoni di appello
  controllano che chi clicca abbia `ban_members`. — commit e24059f
- [x] **SEC-9** Server web: `access_log` con un formato che non scrive
  il percorso né la query (oppure un logger che li sostituisce con
  `/webhook/***` e `?code=***`). Aggiungi `logs/*.log.*` a
  `.gitignore`. Cancella dal disco i log locali che già contengono URL
  interi (non sono in git: verifica con `git ls-files logs`). — commit
  a31dbba (nessuna issue GitHub collegata: non in tabella REVIEW.md
  §"Corrispondenza issue → codici")
- [x] **SEC-10 (#20)** Blacklist su bottoni, menu e modali:
  - crea `core/ui_base.py` con `class BaseView(discord.ui.View)` e
    `class BaseModal(discord.ui.Modal)`: `interaction_check` rifiuta gli
    utenti e i server in blacklist (cache in memoria, stessa fonte del
    `BlacklistAwareCommandTree`), `on_error` risponde in modo effimero
    e registra l'errore (è anche LC-4);
  - tutte le View e i Modal del progetto ereditano da queste;
  - i listener che danno qualcosa all'utente (XP testuale e vocale,
    ruolo da reazione nei role menu, verifica da reazione) ignorano
    gli utenti in blacklist.
  Test cricchetto: nessuna classe in `cogs/` eredita direttamente da
  `discord.ui.View` o `discord.ui.Modal` (elenco `KNOWN_RAW_VIEWS`
  che si svuota). — commit 9d52a82
- [x] **SEC-11** Immagini bomba:
  - `Image.MAX_IMAGE_PIXELS = 40_000_000` impostato in un solo punto
    all'avvio;
  - prima di `.load()` leggi `im.size` (l'apertura è pigra) e rifiuta
    oltre il limite;
  - elaborazione in `run_in_executor` con un `asyncio.Semaphore(2)`
    globale.
  Test: un PNG piccolo su disco ma con dimensioni dichiarate enormi
  viene rifiutato senza allocare la memoria. — commit ac11f7a
  (nessuna issue GitHub collegata: non in tabella REVIEW.md
  §"Corrispondenza issue → codici" — il commit cita erroneamente
  "Refs #20", che è in realtà l'issue di SEC-10; correzione qui)
- [x] **SEC-12** DM di appello dello spam-trap: una sola query per
  `user_id` sulla tabella degli incidenti (con indice), non un giro su
  tutti i server. Riconosce solo i ban dello spam-trap. Limite di un
  DM elaborato ogni 30 secondi per utente. — commit 647b680
  (nessuna issue GitHub collegata: non in tabella REVIEW.md
  §"Corrispondenza issue → codici" — il commit cita erroneamente
  "Refs #20", che è in realtà l'issue di SEC-10; correzione qui)
- [x] **SEC-13** `[B]` decisione D7 (già presa: "Sì, con
  `ENABLE_EVAL`"): variabile `ENABLE_EVAL` (default `False` se
  `ENVIRONMENT=production`, `True` altrove, sempre sovrascrivibile in
  `.env`), e quando spenta `/owner eval`, `shell` e `cog-load`
  rispondono "disattivato" senza eseguire nulla. Sistemati anche i
  bug minori di §5 su eval/shell: log scritto PRIMA dell'esecuzione
  (`log_started`/`mark_result`, non più `log()` dopo), `defer()`
  prima di eseguire (l'output non si perde più oltre i 3 secondi),
  processo shell ucciso (`kill()`+`wait()`) al timeout invece di
  restare orfano. — commit 8a96320 (nessuna issue GitHub
  collegata: non in tabella REVIEW.md §"Corrispondenza issue →
  codici")
- [x] **SEC-14** Server web:
  - indirizzo da `WEB_BIND_HOST`, default `127.0.0.1` (davanti ci va un
    reverse proxy con HTTPS);
  - il server webhook parte solo se esiste almeno un webhook
    configurato;
  - limite di richieste per token (finestra in memoria);
  - il server del restore non parte se manca la chiave di cifratura
    (log WARNING).
  — commit 0e9eb3b (nessuna issue GitHub collegata: non in tabella
  REVIEW.md §"Corrispondenza issue → codici")
- [x] **SEC-15** Dipendenze: aggiungi `aiohttp` in `requirements.txt`
  con un minimo senza vulnerabilità note (controlla la versione su
  PyPI e sugli advisory al momento del fix), togli `structlog`,
  genera un lockfile (`pip-compile` → `requirements.lock`) e usalo
  nell'installazione.
  — commit bf2a772 (nessuna issue GitHub collegata: non in tabella
  REVIEW.md §"Corrispondenza issue → codici")
- [x] **SEC-16** `field(repr=False)` su tutti i segreti in
  `core/config.py` e sulle dataclass dei token OAuth. Test: `repr(config)`
  non contiene nessun valore di token. La password Postgres nella storia
  di `.env.example` si segnala all'owner (non si riscrive la storia).
  — commit 2df2265 (nessuna issue GitHub collegata: non in tabella
  REVIEW.md §"Corrispondenza issue → codici").
  ⚠️ **[B] segnalazione per l'owner, non un'azione fatta qui**: nella
  storia git di `.env.example` ci sono 2 commit con una password
  Postgres locale nel valore di esempio di `DATABASE_URL`, poi
  sostituita con un segnaposto — vedi REVIEW.md SEC-16. Non riscritta
  la storia (nessuna richiesta esplicita in tal senso). Se quella
  password era una password REALE usata da qualche parte (non solo un
  valore di comodo per lo sviluppo locale), l'owner deve cambiarla
  ovunque sia ancora in uso. Le altre 3 voci minori di REVIEW.md
  SEC-16 (cifratura token non legata a guild/utente, riga corrotta
  che blocca l'intero elenco, token webhook in chiaro nel DB) restano
  fuori da questa voce del piano — non erano nell'elenco puntato di
  PIANO_FIX.md per SEC-16, da valutare se aggiungerle come voci nuove
  in un secondo momento.
- [x] **#41** `PREMIUM_ALPHA_UNLOCK_ALL`: default `False` quando
  `ENVIRONMENT=production`, `True` solo in sviluppo; log WARNING
  all'avvio se è `True`. Aggiorna `.env.example` e il commento.
  — commit 576f155 (Refs #41, vedi REVIEW.md §"Corrispondenza issue →
  codici")
- [x] **#36 (parte R0)** Log INFO all'avvio con gli intent effettivi di
  ogni bot.
  — commit 3666a66 (Refs #36)

---

## DB — Migrazioni versionate (DB-1, #25)

Obiettivo: poter cambiare lo schema in modo sicuro prima di R1–R5.
Approccio a **basso rischio**: non si riscrivono le ~41 funzioni
`run_migrations` esistenti.

- [x] Nuovo `core/migrations/__init__.py` (pacchetto, non un singolo
  file: le migrazioni numerate `NNNN_*.sql`/`.py` vivono nella STESSA
  cartella `core/migrations/`, "core/migrations.py" e "core/
  migrations/" come richiesto letteralmente dal piano non possono
  coesistere sullo stesso filesystem):
  - tabella `schema_migrations(version INT PRIMARY KEY, name TEXT,
    applied_at TIMESTAMPTZ)`;
  - le funzioni `run_migrations` esistenti restano la **base**
    (sono idempotenti) e girano per prime, come oggi — spostate da
    `core/database.py` a `core/migrations/__init__.py`
    (`run_core_config_tables` + `run_all_repo_migrations`), un solo
    punto invece di due copie;
  - dopo la base, le migrazioni numerate in `core/migrations/`
    (`0001_descrizione.sql` o `.py` con `async def up(conn)`),
    ciascuna in una transazione, sotto `pg_advisory_lock` (così due
    processi non migrano insieme), registrate in `schema_migrations`;
  - una migrazione applicata non si modifica mai: se serve, se ne
    aggiunge una nuova.
- [x] `tests/conftest.py` copiava a mano l'SQL di `core/database.py`
  (`db_singleton_run_migrations_with_pool`, "tenuto in sync
  manualmente") — ora `clean_db` chiama `core.migrations.
  run_all_migrations(db_pool)`, lo STESSO runner usato in produzione
  da `core.database.Database.run_migrations()`. L'elenco `TRUNCATE`
  fisso è sparito: ora legge le tabelle da `information_schema`
  (escludendo `schema_migrations`, che non va svuotata tra un test e
  l'altro — altrimenti le migrazioni numerate verrebbero riapplicate
  ad ogni test).
- [x] Test (`tests/test_migrations.py`): il runner applica una
  migrazione una volta sola, due runner concorrenti (pool separati,
  `asyncio.gather`) non la applicano due volte, una migrazione che
  fallisce non lascia metà schema (transazione per migrazione).
- [x] Prima migrazione utile (DB-2, `core/migrations/
  0001_db2_indici.sql`): due nuovi indici parziali sulle query che
  girano ogni ora (`clans.get_unofficialized_expired()`,
  `leveling_repo.list_users_needing_weekly_decay()` — nessuna delle
  due coperta da un indice esistente, verificato leggendo le query e
  gli indici di `guild_clan_repo.py`/`leveling_repo.py`) e la
  rimozione di `idx_event_log_guild_role`/`idx_event_log_guild_case`
  (verificato con `grep` in `event_log_repo.py` che `role_id`/
  `case_number` compaiono solo in un `INSERT`, mai in una `WHERE`).
  — commit 659d9fa (Refs #25)

---

## R1 — Bug che rompono funzioni

Ogni voce: test che esegue il comando e fallisce → fix → test verde.

**Ticket e setup**
- [x] **BUG-1 (#2, #42)** `cogs/tickets/tickets.py`: rispondi, poi
  `self._pianifica_eliminazione(channel, 10, motivo)`, che lancia
  `self.bot.loop.create_task(self._elimina_dopo(...))`. La coroutine
  fa `await asyncio.sleep(10)`, poi `channel.delete(reason=…)`, e
  registra `NotFound`/`Forbidden` senza sollevare. Riferimento al task
  tenuto in `self._eliminazioni_pianificate` (un `set` sul cog, rimosso
  con `add_done_callback`) così non viene raccolto dal garbage
  collector, e cancellato in `cog_unload`. Test in
  `tests/test_ticket_close_deletion.py` con `fake_text_channel()`
  (autospec — riproduce lo stesso `TypeError: unexpected keyword
  argument 'delay'` del bot vero).
  — commit 6c724d3 (Refs #2, #42)
- [x] **BUG-2 (#4, #38, #43, #49)** `/setup` per categoria (scelta
  dell'owner, #49):
  - campo obbligatorio `category: str` in `PremiumModule`, con valori
    ammessi in una costante (`moderation`, `security`, `automod`,
    `logging`, `utility`, `tickets`, `voice`, `music`, `leveling`,
    `fun`). `register()` rifiuta categorie sconosciute;
  - assegna la categoria ai 32 moduli (tabella in #49, da validare
    sul registry reale);
  - `/setup` prende un parametro `categoria` con `choices`, mostra una
    `Select` solo con i moduli di quella categoria; se una categoria
    superasse 25 moduli, paginazione come #43 opzione A;
  - aggiungi `/setup` senza categoria → embed di sola lettura con lo
    stato di tutti i moduli;
  - il salvataggio emette `modules_updated` come oggi;
  - `/setup-wizard` resta com'è (onboarding dei 6 moduli base).
  Test: ogni modulo registrato ha una categoria valida; per ogni
  categoria la `Select` si costruisce con i moduli reali; il cricchetto
  `KNOWN_OVERSIZED_SELECTS` si svuota. In R5 il comando diventa
  `/admin setup`.
  Fatto: categorie assegnate in base al tipo di modulo (tabella di #49
  non raggiungibile da qui), `/setup categoria:`, embed di sola lettura,
  cricchetto svuotato — commit c9534fb (Refs #4, #38, #43, #49)
- [x] **BUG-6** `/config rollback`: lo storico deve salvare il valore
  precedente **completo** (per `reset` e `import`: la riga intera). Il
  rollback di una chiave che prima non esisteva la **rimuove** (non la
  mette a `null`); il rollback della lingua cambia la colonna
  `language`. Se non si può ripristinare, risponde con un errore, mai
  "✅". Un test per ciascuno dei casi descritti in REVIEW.md.
  Fatto in `core/database.py` (`rollback_config_change`), 5 test in
  `tests/test_config_rollback_bug6.py` — commit 071504a
- [x] `/config import` (§4 Utility): valida lo schema prima di scrivere
  e rifiuta i dati sbagliati. Fatto: `errore_schema_import` + limite 256 KB,
  12 test in `tests/test_config_import_validation.py` — commit 80322ff

**Avvio, scheduler e processi**
- [x] **BUG-7 (#12, #28)** `main.py`:
  - ogni bot parte in un proprio task con una funzione "supervisore"
    che registra l'errore; se cade un worker musicale o il Creator, gli
    altri restano su (log ERROR e, per il principale, DM all'owner);
    se cade il bot principale il processo esce con codice ≠ 0;
  - spegnimento ordinato su SIGTERM/SIGINT: chiudi i bot, ferma i loop
    dei cog (`cog_unload`), chiudi le sessioni HTTP condivise e il pool
    del database, in quest'ordine.
  Test: con un finto bot che fallisce all'avvio, gli altri restano
  attivi; lo spegnimento chiude tutte le sessioni (fixture di RT-3).
  Fatto in `core/bot_supervisor.py` + `main.py`, 5 test in
  `tests/test_bot_supervisor.py` — commit 8a218d1 (Refs #12, #28)
- [ ] **BUG-8 (#13)** `core/scheduler.py`: `try/except` intorno a ogni
  giro e intorno a ogni azione; un'azione senza handler viene segnata
  `failed` con il motivo e non blocca la coda.
- [ ] **BUG-9** All'avvio svuota `music_sessions` (i worker ripartono da
  zero). Test: righe vecchie spariscono al setup.
- [ ] **LC-8** Worker periodici: `try/except` **per server** dentro il
  giro (retention log, soundboard, XP vocale clan, decay), così un
  server problematico non blocca gli altri. Stesso schema per tutti:
  estrai una funzione `for_each_guild_safely(...)` in `core/`.

**Backup e restore**
- [ ] **BUG-3 (#26)** Nel punto dove il backup è completato (worker
  della coda), chiama `backup_repo.define_backup(...)` con il vero
  `backup_guild_id`. Togli `define_backup` da `KNOWN_UNCALLED`. Correggi
  il test esistente del backup che inserisce **da solo** la coppia (è
  quello che nascondeva il bug): la coppia deve nascere dal codice di
  produzione.
- [ ] **BUG-4 (#21)** Se un job fallisce o scade, il Creator cancella il
  server che ha creato (è il proprietario, può farlo). All'avvio, una
  pulizia: server del Creator non legati a nessuna coppia attiva e più
  vecchi di un'ora vengono cancellati. Correggi il messaggio "gli slot
  si liberano da soli" finché non è vero.
- [ ] `/define-backup`: al massimo una coppia attiva per server (§4).
- [ ] Snapshot settimanale: aspetta `wait_until_ready()` (§4).
- [ ] §12 11.5–11.7: prima di clonare emoji, sticker e suoni, controlla
  i limiti del server di destinazione e salta quello che non ci sta,
  invece di far fallire tutto il backup.
- [ ] §12 11.3: imposta le posizioni dei ruoli clonati. **DA VERIFICARE
  LIVE** (aggiungi a `VERIFICA_LIVE.md`).

**Musica**
- [ ] **BUG-10 (#7, #45, #47)** File locali della radio:
  - all'avvio, se `MAIN_RADIO_LOCAL_FOLDER` è impostata e non esiste,
    `Path.mkdir(parents=True, exist_ok=True)` e log INFO;
  - `add-local nome_file`: `(root / nome_file).resolve()` deve essere
    dentro `root.resolve()` (`is_relative_to`), deve esistere ed
    essere un file audio; altrimenti rifiuta;
  - il percorso passato a Lavalink è quello **visto dal nodo**: nuova
    variabile `LAVALINK_LOCAL_ROOT` (default `/audio/local`, il mount
    del `docker-compose`), identificatore = `LAVALINK_LOCAL_ROOT/nome_file`,
    passato **senza** prefisso di ricerca (niente `ytmsearch:`);
  - questi brani si riproducono solo sul nodo locale: se il nodo
    locale non è connesso, messaggio chiaro.
- [ ] **#45** Radio automatica: listener `on_voice_state_update` sul bot
  principale; quando il bot stesso entra in un canale vocale e la
  playlist non è vuota, parte la stessa logica di `/nonstop-main start`;
  quando esce, si ferma senza azzerare l'orologio globale.
- [ ] **#47, #48** Cartella `deploy/lavalink/` con `docker-compose.yml`,
  `application.yml` (password come segnaposto, **mai** un valore vero)
  e `README.md` con i link ufficiali (lavalink.dev, youtube-source,
  LavaSrc) e come leggere `sourceManagers` da `/v4/info`. Ricontrolla
  le versioni dei plugin sulle pagine ufficiali. Nel codice, il commento
  sulla lista dei nodi pubblici dice che è un default da riverificare,
  non una fonte ufficiale.
- [ ] Cascata dei nodi (§4 Musica): pubblici prima, locale per ultimo
  (tranne i brani locali, vedi sopra). Serve scegliere il nodo in modo
  esplicito invece di lasciare decidere a wavelink. **DA VERIFICARE
  LIVE**.
- [ ] `/stop`, `/skip` & co.: chi li usa deve essere nello stesso canale
  del player.

**Sicurezza automatica**
- [ ] **BUG-11** Anti-nuke: escludi `bot.user.id` dai conteggi; se
  l'autore è un bot con ruolo gestito, la punizione è kick o ban, non
  `strip_roles`.
- [ ] **BUG-12, #27** Anti-raid: escludi `member.bot`; un solo ingresso
  non fa mai scattare il lockdown; il lockdown ha una scadenza e poi
  ripristina il livello di verifica precedente; un solo ruolo
  "Quarantined" (creazione protetta da `asyncio.Lock` per server); un
  solo DM al proprietario per episodio.
- [ ] **#30** Recovery anti-nuke: ricrea anche canali vocali, categorie
  e forum, con posizione e topic. **DA VERIFICARE LIVE**.
- [ ] Anti-nuke e `/restore`: controlla se il modulo è attivo **prima**
  di leggere l'audit log (è anche PERF-5).

**Errori e interazioni**
- [ ] **BUG-13** Gestore errori globale (`core/premium.py` ~431):
  `CheckFailure`, `MissingPermissions`, `NoPrivateMessage` → messaggio
  effimero chiaro in italiano, log INFO, niente "errore imprevisto".
- [ ] **LC-3** `defer()` prima delle operazioni lente: kick, ban,
  tempban, softban, `/suggest`, `clan invita|espelli|promuovi|compra-canale|crea|sciogli`,
  salvataggio di `/setup`, verify, comandi immagine di `/fun`,
  `animal`, `search-image`.
- [x] **LC-4 (#22)** Coperto da `BaseView.on_error`/`BaseModal.on_error`
  (SEC-10) — commit 9d52a82.
- [ ] **LC-5 (#16)** View di appello dello spam-trap persistente:
  `timeout=None`, `custom_id` fissi con l'ID dell'incidente,
  `bot.add_view(...)` all'avvio. Test: la view è tra quelle registrate
  al setup del cog.
- [ ] **BUG-18 (#34)** `/voice transfer`: il nuovo proprietario deve
  essere nel canale e non un bot; i permessi del canale passano al
  nuovo proprietario (§4).

**Economia e clan** — regola: nessuno schema "leggi, controlla, poi
scrivi" con un `await` in mezzo. Il controllo va dentro la scrittura.
- [ ] **BUG-14, #35** `/daily` e `/work`: un solo `UPDATE … SET
  ultimo = now() WHERE … AND (ultimo IS NULL OR ultimo < now() -
  interval …) RETURNING …`; se non torna righe, il cooldown non è
  scaduto.
- [ ] **BUG-14, #23** `/shop buy`: in una transazione, `INSERT` dell'acquisto
  con vincolo `UNIQUE` (migrazione in `core/migrations/`) e `ON CONFLICT
  DO NOTHING RETURNING`, addebito condizionato al saldo; poi si dà il
  ruolo; se il ruolo non si può dare, rimborso e cancellazione
  dell'acquisto.
- [ ] **BUG-14** `/cassa sblocca-premium` e `/clan compra-canale`: stesso
  schema (scrittura condizionata, poi azione Discord, poi compensazione
  se fallisce).
- [ ] **LC-1 (#18)** `/assegna-lobby`: `defer()`, poi addebito della cassa
  e tutti gli accrediti **in una sola transazione**.
- [ ] **BUG-17 (#33)** Scrivi un test che lancia due `raccogli` insieme
  con `asyncio.gather` e controlla che `add_coins` venga chiamato una
  volta sola. Se passa (atteso), aggiungi sopra il controllo un
  commento di una riga: "nessun await tra controllo e assegnazione: è
  atomico", e segnala nell'issue #33 che è un falso positivo con il
  test come prova. Non chiuderla tu.
- [ ] **BUG-15** I clan finanziati con trasferimento risultano
  "ufficiali" e non vengono cancellati dopo 24 ore.
- [ ] Economia e clan controllano se il modulo `leveling` è attivo (§4).
- [ ] Trasferimenti A→B e B→A: blocca le righe sempre nello stesso
  ordine (ID minore prima) per evitare il deadlock (§5).

**Moderazione e AutoMod (parte non legata a message_content)**
- [ ] `/automod anti-spam-* seconds=`: usa il valore salvato.
- [ ] Sincronizzazione AutoMod: prima di `edit()` leggi la regola e
  conserva le regex e le allow-list aggiunte a mano.
- [ ] Blacklist link: normalizza con `urllib.parse` (porta, userinfo,
  sottodomini) prima del confronto.
- [ ] Escalation: una violazione conta una volta; conteggio con
  `UPDATE … RETURNING`.
- [ ] Casi di moderazione: crea il caso **dopo** l'azione riuscita
  (§5).
- [ ] `duration_logic`: limite massimo (es. 5 anni) e test su
  `9999999999w`.

**Feed e watcher**
- [ ] **LC-7** Feed, Twitch e YouTube non pubblicano con il modulo
  spento.
- [ ] Twitch: richieste a blocchi di 100.
- [ ] RSS: se l'ultimo elemento visto sparisce, pubblica solo gli
  elementi più recenti di una data, non tutto il feed.
- [ ] **BUG-16** `[B]` decisione D5 (RSS + `videos.list`).

**Resto di §4 e §5 di REVIEW.md:** ogni voce non elencata sopra si
sistema in questa fase, una alla volta, con lo stesso metodo. Prima di
iniziare R1b, ogni voce di §4 e §5 deve essere `[x]`, `[B]` o spostata
esplicitamente in una fase successiva con il motivo.

---

## R1b — SPEC onesta

- [ ] Correggi in `SPEC.md` i marcatori della tabella di REVIEW.md §12:
  una voce resta `[x]` solo se il codice la fa davvero **e** ha un
  test. Se funziona offline ma serve una prova su Discord, scrivi
  accanto "(da verificare live)".
- [ ] Correggi i testi imprecisi elencati in §12.
- [ ] Aggiorna PROGRESS.md con un riepilogo di R-T…R1.

---

## R2 — Dati e GDPR (GDPR-1/2/3, #19, #37, #46)

Decisioni già prese: 90 giorni, conservazione per sicurezza, richiesta
di cancellazione manuale.

- [ ] Migrazione: tabella `guild_presence(guild_id PK, joined_at,
  left_at NULL)`; `on_guild_join` azzera `left_at`, `on_guild_remove`
  lo imposta. Conta solo il bot principale, non il Creator né i
  worker musicali.
- [ ] Migrazione: colonna `retain_for_security BOOLEAN NOT NULL DEFAULT
  FALSE` sui casi di moderazione e sui log di sicurezza/global-ban. La
  imposta a `TRUE` ogni ban o kick fatto da spam-trap, anti-raid,
  anti-nuke e global-ban, più i ban manuali con categoria "spam",
  "raid" o "nuke".
- [ ] **Registro dei dati personali** `core/data_registry.py`: ogni
  repository dichiara le sue tabelle con colonna utente e/o server e
  come cancellarle (delete o anonimizzazione). Test invariante: ogni
  tabella in `information_schema` con una colonna `user_id` o
  `guild_id` è dichiarata nel registro (cricchetto se serve).
- [ ] Worker giornaliero di retention: server con `left_at` più vecchio
  di 90 giorni → cancellazione di tutti i dati del server in una
  transazione, **tranne** le righe con `retain_for_security`. Più le
  durate per tabella di GDPR-3 (log AutoMod e sicurezza, tentativi di
  verify, incidenti spam-trap, storico config, movimenti cassa, azioni
  programmate eseguite): una costante per tabella in un solo punto.
- [ ] Schedula `prune_old_index` e `purge_expired_voluntary_leaves`
  (oggi mai chiamate) dentro questo worker; toglile da `KNOWN_UNCALLED`.
- [ ] `forget_user(user_id)` in `core/`: usa il registro; se l'utente ha
  righe `retain_for_security`, rifiuta con spiegazione.
- [ ] Comando utente per la richiesta (nome definitivo in R5, es.
  `/utility privacy`): apre un modal, salva in `data_deletion_requests`
  (stato, motivo, esito). Comando owner per approvare, che chiama
  `forget_user`. Anche esportazione dei dati (art. 15) in JSON inviato
  in DM.
- [ ] Documenta la politica in SPEC.md (e in un file privacy da
  pubblicare quando ci sarà il Web Panel).

---

## R3 — Router dei canali (REVIEW.md §8)

- [ ] `[B]` per la parte forum: decisione D3.
- [ ] Migrazione: `output_channels(guild_id, output_type, channel_id,
  thread_id NULL, PRIMARY KEY(guild_id, output_type))`.
- [ ] `core/channel_router.py`:
  - elenco dei tipi di uscita in una costante (log-membri,
    log-messaggi, log-moderazione, log-vocale, log-server, log-automod,
    alert-sicurezza, benvenuto, …: l'elenco completo è in §8);
  - `async def send(bot, guild, output_type, **kwargs)`: trova il
    canale configurato; se è testuale scrive lì; se è un forum usa o
    crea il post giusto; se non c'è niente torna al vecchio canale
    unico dei log (compatibilità durante la migrazione); se il canale
    è sparito o mancano i permessi avvisa gli admin **una volta** per
    tipo (cache con scadenza) e non solleva;
  - funzioni per creare categoria + canali o forum con i permessi
    giusti (visibili solo allo staff).
- [ ] Migrazione che copia le impostazioni esistenti nella nuova tabella.
- [ ] Sposta sul router, una funzione alla volta, tutte le uscite
  elencate in §8. Test cricchetto: elenco dei file che scrivono ancora
  in un canale preso dalle impostazioni senza router; si svuota.
- [ ] Log delle azioni oggi non registrate: `/untimeout`, `/unmute-role`,
  scadenza dei tempban, azioni dell'escalation, `/lock`, `/unlock`,
  `/slowmode`, `/clear` (§12 5.10).
- [ ] Il canale di alert anti-nuke si imposta anche senza il modulo
  anti-raid.
- [ ] I comandi di configurazione nascono direttamente sotto il nuovo
  `/log` in R5; fino ad allora usa sotto-comandi del gruppo `logs`
  esistente (non aggiungere top-level).

---

## R4 — message_content e log dei messaggi (#6, #36, #39, #44)

- [ ] **Prima di tutto, owner:** attivare "Message Content Intent" nel
  Developer Portal per il bot principale (e per il Creator se il mirror
  del backup lo richiede). Senza questo il bot non si connette con
  l'intent attivo: chiedi conferma all'owner prima del commit che lo
  accende.
- [ ] `intents.message_content = True` in `main.py` dove serve. Aggiorna
  il commento e le due docstring sbagliate su "contenuto via REST"
  (L8).
- [ ] Log messaggi cancellati, cancellati in massa e modificati (SPEC
  §8.16) tramite il router; `/snipe` e `/editsnipe` (§14.9/14.10) con
  una cache in memoria limitata (`BoundedCache`) e scadenza breve.
- [ ] Ricontrolla con test i filtri AutoMod avanzati, le trascrizioni
  dei ticket, lo spam-trap, il mirror del backup e il filtro allegati di
  `/clear` con messaggi finti **con** contenuto.
- [ ] Testo di motivazione per la verifica Discord (≥100 server) in
  `SPEC.md`: elenco delle funzioni che usano ogni intent privilegiato.

---

## R5 — Nuova struttura comandi (REVIEW.md §6)

- [ ] `[B]` decisioni D2 (granularità di `/mod`) e D4 (retrocompatibilità;
  raccomandato: nessuna, il bot non ha utenti).
- [ ] Albero come nella tabella di §6: `/owner /admin /mod /security
  /log /ticket /voice /music /level /clan /fun /utility`, con i limiti
  L2 (25 per gruppo) e L3 (un livello di sotto-gruppi).
- [ ] Ogni gruppo: `guild_only=True`; i gruppi staff hanno
  `default_permissions` (es. `/mod` → `moderate_members`, `/admin` →
  `administrator` o `manage_guild`, `/log` → `manage_guild`).
  `/owner` si registra **solo** in `MAIN_GUILD_ID` (`guild=`),
  `default_permissions(administrator=True)`, e controlla `OWNER_ID` a
  runtime.
- [ ] Nessun controllo "sei amministratore?" dentro i comandi: Discord
  ha già deciso chi può usarli (delega in Integrazioni). Dentro i
  comandi solo gerarchia dei ruoli (`check_can_moderate`,
  `check_role_assignable`) e permessi del bot.
- [ ] Sposta i comandi **senza cambiarne la logica**: prima un commit
  per gruppo con i test esistenti aggiornati ai nuovi nomi, poi le
  pulizie.
- [ ] Sync: comandi globali + sync separato per `MAIN_GUILD_ID`.
- [ ] Gruppi misti di oggi (`shop`, `cassa`, `config`): parte pubblica
  in `/level`, parte staff in `/admin`.
- [ ] Alla fine: `KNOWN_MISSING_DEFAULT_PERMISSIONS` e
  `KNOWN_NOT_GUILD_ONLY` vuoti. Aggiorna `AUDIENCE` in
  `tests/support/command_policy.py` con i nuovi gruppi e togli `MIXED`.
  Aggiungi un test che, per ogni comando staff, esegue il callback con
  un membro senza permessi e controlla il rifiuto (dove il callback fa
  controlli di gerarchia).
- [ ] Rigenera `COMMAND_LIST.md` dall'albero reale.
- [ ] Spiega all'owner, in un messaggio, come delegare un gruppo a un
  ruolo in *Impostazioni server → Integrazioni → iYokai*.

---

## R6 — Lingue e /cerca-comando (REVIEW.md §7)

- [ ] `[B]` decisione D1 (opzione A consigliata).
- [ ] File di testi unico (IT/EN) con nome, descrizione, parole chiave
  e messaggi di risposta con variabili; `core/i18n.py` lo legge in
  base a `guild_config.language`.
- [ ] Con l'opzione A: `name_localizations`/`description_localizations`
  tramite un `app_commands.Translator` che legge lo stesso file.
- [ ] Script `scripts/genera_command_list.py` che produce
  `COMMAND_LIST_ITA.md` e `COMMAND_LIST_ENG.md` dal file di testi e
  dall'albero reale. Test: i file committati coincidono con l'output
  dello script.
- [ ] `/utility cerca-comando`: cerca su nomi, descrizioni e parole
  chiave in entrambe le lingue; mostra solo i comandi che l'utente può
  usare (permessi dell'interazione contro `default_permissions`) e
  con il modulo attivo. Test: "bannare un utente" e "ban a user"
  restituiscono `/mod ban` al primo posto.
- [ ] Traduci le risposte oggi in inglese (role menu, verify,
  spam-trap, benvenuti di default).

---

## R7 — NSFW

- [ ] Istanza separata con `NSFW_TOKEN`, stesso codice, sullo schema
  dei worker musicali (SPEC §16.10), con la struttura e le lingue di
  R5/R6. Dettagli da concordare con l'owner prima di iniziare.

---

## Continuo (in ogni commit che tocca un file)

- **Docstring in testa al file**, formato fisso (REVIEW.md §9):
  ```
  percorso/del/file.py
  ====================
  A cosa serve (1–2 frasi).
  Funzioni coperte: SPEC §x.y, §x.z
  Dipende da: … (solo se non ovvio)
  ```
  Niente cronache di sessioni, niente "perché abbiamo scelto", niente
  nomi di altre AI. Le spiegazioni tecniche utili diventano commenti
  vicino al codice. Correggi le docstring false elencate in §9.
- **Codice morto** (§11): togli ciò che è morto quando tocchi quel
  file. I metodi di repository si tolgono anche da `KNOWN_UNCALLED`.
- **Duplicazioni** (§11): un solo aiuto per "solo dentro un server",
  `_alert_staff`, `_case_embed`, cooldown.
- **Prestazioni** (§10, PERF-1…7): cache delle impostazioni del server
  e dei cooldown XP, loop vocali raggruppati per server, decay con una
  sola `UPDATE`, feed scaricati in parallelo con limite e URL
  deduplicati. Ogni ottimizzazione con un test che dimostra lo stesso
  risultato di prima.

---

## D. Decisioni che servono dall'owner

Non indovinare: quando una voce è `[B]`, chiedi all'owner e passa ad
altro.

| # | Domanda | Blocca | Raccomandazione |
|---|---|---|---|
| D1 | Nomi dei comandi: opzione A (localizzazione nativa per client) o B (registrazione per server)? | R6 | A |
| D2 | `/mod` unico gruppo, oppure `/mod` + `/modban`? | R5 | Due gruppi, se l'owner vuole delegare timeout/warn senza ban |
| D3 | Forum dei log avanzati: un post per tipo o per utente/caso? | R3 (parte forum) | Un post per tipo |
| D4 | Tenere i vecchi nomi dei comandi per un periodo? | R5 | No, il bot non ha utenti |
| D5 | YouTube: passare a RSS + `videos.list`? | BUG-16 | Sì |
| D7 | `/owner eval` e `/owner shell` spenti di default in produzione? | SEC-13 | Sì, con `ENABLE_EVAL` |

(D6, retention, è già decisa: 90 giorni.)

---

## V. Verifica live

Da questa sessione cloud Discord, Aiven e Lavalink **non sono
raggiungibili** (bloccati dal proxy). Quindi:

- ogni fix che ha bisogno di Discord, del database reale o di Lavalink
  per essere certificato si aggiunge a `VERIFICA_LIVE.md` con: codice
  REVIEW, issue, commit, e i **passi esatti** del test (cosa fare in
  Discord, cosa ci si aspetta);
- l'owner esegue quei passi sul suo PC con il `.env` locale e riporta
  l'esito (senza segreti);
- solo dopo l'esito positivo l'issue si può chiudere, dall'owner o su
  sua richiesta esplicita.

Esempi di voci che sono sempre live: ticket close su un canale vero,
permessi e visibilità in un server di test con un secondo account senza
permessi, gerarchia dei ruoli, OAuth del restore, riproduzione musicale
e file locali, race condition con clic reali, avvio con i token veri,
migrazioni su Aiven.
