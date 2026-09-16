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

## 🚧 Non ancora iniziato

Nell'ordine di sviluppo concordato:

1. **AutoMod ibrido** — lettura/creazione/aggiornamento delle regole
   AutoMod native di Discord via API, invece di duplicare i filtri
   lato bot
2. **Logging semplificato** — join/leave/ban/kick/ruoli
3. **Setup interattivo** (`/setup`) — pannello reale con Select Menu +
   bottoni, oggi `on_guild_join` crea solo la riga di config vuota
   (nessun modulo risulta ancora attivabile dai server reali finché
   questo non esiste — anche Moderation, pur scritta, resta invisibile
   finché un server non ha `modules.moderation_actions = true`)
4. **Ticket system**
5. **Vocali temporanei** — modalità automatica + manuale, sempre
   entrambe visibili (vedi decisione in `PROGRESS.md` § Decisioni)
6. **Livelli / Economy / Classifiche**, poi **Gilde** sopra
7. **Spam Trap** — la specifica è già completa e dettagliata (vedi
   § Decisioni prese, punto Spam Trap), va solo implementata
8. Richiesta di **verifica Discord** a ~90 server, con il set
   "pulito" (moduli 1-7)
9. **Music** (5 istanze + Lavalink)
10. **Alert social** (Twitch EventSub, YouTube PubSubHubbub)
11. **Security Suite completa** (Anti-Raid avanzato, Anti-Nuke)
12. **Backup** (iYokai Creator + snapshot + mirror in tempo reale)
13. **NSFW** (iYokai NSFW, applicazione separata)
14. **iYokai Desktop** (presence via RPC locale)
15. **iYokai Panel** (web, verify avanzato, OAuth2)

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

**AutoMod ibrido** (punto 1 di "Non ancora iniziato"): il bot legge le
regole AutoMod native esistenti su un server, crea quelle mancanti dal
proprio preset, aggiorna quelle presenti unendo le proprie voci senza
sovrascrivere quanto configurato dall'owner. Limiti Discord da
rispettare: ~6 regole keyword per server, una per spam, una per
mention-spam, ~1000 voci per lista, ~10 pattern regex — le regole
vanno consolidate, non create una per categoria.

Subito dopo, punto 3 (**Setup interattivo**) diventa urgente: oggi
Moderation è scritta e testata ma **invisibile a qualunque server
reale**, perché `/setup` non esiste ancora e nessun server ha
`modules.moderation_actions = true` nel proprio `guild_config`. Senza
`/setup`, ogni nuovo modulo continuerà ad accumularsi "pronto ma
spento" — vale la pena anticiparlo rispetto all'ordine originale se le
prossime sessioni iniziano a sentirne la mancanza per testare quanto
già scritto.
