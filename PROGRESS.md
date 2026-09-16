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

## 🚧 Non ancora iniziato

Nell'ordine di sviluppo concordato:

1. **Vocali temporanei** — modalità automatica + manuale, sempre
   entrambe visibili (vedi decisione in `PROGRESS.md` § Decisioni)
2. **Livelli / Economy / Classifiche**, poi **Gilde** sopra
3. **Spam Trap** — la specifica è già completa e dettagliata (vedi
   § Decisioni prese, punto Spam Trap), va solo implementata
4. Richiesta di **verifica Discord** a ~90 server, con il set
   "pulito" (moduli 1-3)
5. **Music** (5 istanze + Lavalink)
6. **Alert social** (Twitch EventSub, YouTube PubSubHubbub)
7. **Security Suite completa** (Anti-Raid avanzato, Anti-Nuke)
8. **Backup** (iYokai Creator + snapshot + mirror in tempo reale)
9. **NSFW** (iYokai NSFW, applicazione separata)
10. **iYokai Desktop** (presence via RPC locale)
11. **iYokai Panel** (web, verify avanzato, OAuth2)

---

## 📐 Decisioni prese (da rispettare in ogni sviluppo futuro)

Queste non sono suggerimenti: sono vincoli verificati sulle API
Discord reali. Se in una sessione futura sembra di poter "semplificare"
uno di questi punti, **rileggere prima il motivo** — quasi sempre è già
stato scartato per un limite tecnico specifico.

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

## 🗂️ Le 8 applicazioni Discord del progetto

| # | Nome | Repository | Note |
|---|---|---|---|
| 1 | iYokai Main | **questa repo** | Core, deve passare la verifica a 100 server |
| 2 | iYokai Creator | da creare | Sempre sotto i 10 server |
| 3-7 | iYokai Music #1-5 | da creare | Una connessione vocale ciascuno |
| 8 | iYokai NSFW | da creare | Isolata per non appesantire la review del core |
| — | iYokai Desktop | da creare | App locale, RPC, no user token |
| — | iYokai Panel | da creare | Web, verify avanzato + OAuth2 |

---

## 🔜 Prossimo passo concreto

**Vocali temporanei** (punto 1 di "Non ancora iniziato"): modalità
automatica (canale generatore -> crea e sposta) + modalità manuale
(pannello con bottone, nessuno spostamento forzato), entrambe SEMPRE
visibili a tutti indipendentemente dalla piattaforma (decisione già
presa, vedi § Decisioni prese più sopra — i problemi di disconnessione
su spostamento forzato riguardano sia PlayStation sia mobile).

Il bottone "Crea canale vocale" della modalità manuale è un altro
caso di pannello a vita lunga: **richiede una view persistente**,
esattamente come `TicketPanelView` in `cogs/tickets/tickets.py` — non
riscoprire il problema da capo, riusare lo stesso pattern
(`timeout=None`, `custom_id` esplicito, `bot.add_view()` in `setup()`).

La modalità automatica invece userà un listener `on_voice_state_update`
per rilevare l'ingresso nel canale generatore — ricordarsi il
controllo `bot.extra_events` nello smoke test, come per
`cogs/logging/basic_logs.py`.
