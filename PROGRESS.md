# PROGRESS — Stato del progetto Yokai Bot

> Questo file esiste per un motivo preciso: se una sessione di lavoro
> finisce (token esauriti, chiusura chat, cambio giornata), la sessione
> successiva legge QUESTO file per sapere esattamente dove riprendere,
> senza dover rileggere tutta la conversazione da capo.
>
> **Regola:** ogni commit che chiude un pezzo di lavoro aggiorna anche
> questo file, nella stessa sessione. Non lasciarlo mai indietro
> rispetto al codice.

Ultimo aggiornamento: **16 settembre 2026**

---

## ✅ Fatto

### Fase 0 — Fondamenta
- [x] Struttura cartelle del progetto (`core/`, `cogs/` con sottocartelle per dominio)
- [x] `.gitignore` — esclude `.env`, cache Python, venv, log, dati locali
- [x] `.env.example` — template completo di tutte le variabili previste
  (token delle 8 applicazioni, DB, Lavalink, OAuth2/web panel)
- [x] `requirements.txt` — dipendenze base (discord.py, asyncpg,
  python-dotenv, psutil, wavelink, structlog)
- [x] `core/config.py` — loader di configurazione che **valida
  all'avvio**: se manca una variabile obbligatoria, il processo si
  ferma con un errore chiaro invece di crashare più avanti
- [x] `core/database.py` — pool `asyncpg`, metodo `run_migrations()`
  con le tabelle base (`guild_config`, `premium_whitelist`,
  `premium_module_flags`), metodi CRUD minimi
- [x] `core/premium.py` — sistema premium completo: `PremiumRegistry`,
  `PremiumModule`, decorator `@requires_module(...)`. **Tutto parte
  spento** (`is_premium_active = False` ovunque), come richiesto
- [x] `core/cog_manager.py` — scoperta automatica dei cog tramite
  `pkgutil.walk_packages`, nessuna registrazione manuale necessaria
- [x] `main.py` — entry point, `AutoShardedBot` (predisposto per lo
  sharding fin da subito), `setup_hook`, `on_guild_join`,
  `message_content` intent disattivato di default
- [x] `cogs/utility/ping.py` — cog modello/riferimento, commentato per
  intero: mostra il pattern di controllo "modulo attivo per questo
  server?" che sostituisce il (non fattibile) carico/scarico di cog
  per singolo server
- [x] `cogs/utility/owner_premium.py` — comandi
  `/owner premium-list`, `/owner premium-toggle`,
  `/owner whitelist-add`, `/owner whitelist-remove`
- [x] README aggiornato con struttura, setup, architettura a
  applicazioni multiple

---

## 🚧 Non ancora iniziato

Nell'ordine di sviluppo concordato:

1. **Repository layer per dominio** (`core/repositories/`) — vedi nota
   in fondo a `core/database.py`: ogni modulo avrà il proprio
   repository invece di ammassare tutto in `Database`
2. **Moderation** (`cogs/moderation/`) — warn, kick, ban, case system,
   note, report, lock/unlock, slowmode, clear
3. **AutoMod ibrido** — lettura/creazione/aggiornamento delle regole
   AutoMod native di Discord via API, invece di duplicare i filtri
   lato bot
4. **Logging semplificato** — join/leave/ban/kick/ruoli
5. **Setup interattivo** (`/setup`) — pannello reale con Select Menu +
   bottoni, oggi `on_guild_join` crea solo la riga di config vuota
6. **Ticket system**
7. **Vocali temporanei** — modalità automatica + manuale, sempre
   entrambe visibili (vedi decisione in `PROGRESS.md` § Decisioni)
8. **Livelli / Economy / Classifiche**, poi **Gilde** sopra
9. **Spam Trap** — la specifica è già completa e dettagliata (vedi
   § Decisioni prese, punto Spam Trap), va solo implementata
10. Richiesta di **verifica Discord** a ~90 server, con il set
    "pulito" (moduli 1-9)
11. **Music** (5 istanze + Lavalink)
12. **Alert social** (Twitch EventSub, YouTube PubSubHubbub)
13. **Security Suite completa** (Anti-Raid avanzato, Anti-Nuke)
14. **Backup** (Yokai Creator + snapshot + mirror in tempo reale)
15. **NSFW** (Yokai NSFW, applicazione separata)
16. **Yokai Desktop** (presence via RPC locale)
17. **Yokai Panel** (web, verify avanzato, OAuth2)

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
- **`POST /guilds` funziona solo per bot sotto i 10 server.** Yokai
  Bot (il bot principale) non creerà mai server. La creazione dei
  server di backup è delegata a **Yokai Creator**, un'applicazione
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
- **Niente modulo selfbot.** Sostituito da **Yokai Desktop**, app
  locale che usa il socket RPC del client Discord — nessun user
  token, nessun rischio ban per l'utente finale.
- **NSFW su applicazione separata** (`Yokai NSFW`), filtro a due
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
| 1 | Yokai Bot | **questa repo** | Core, deve passare la verifica a 100 server |
| 2 | Yokai Creator | da creare | Sempre sotto i 10 server |
| 3-7 | Yokai Music #1-5 | da creare | Una connessione vocale ciascuno |
| 8 | Yokai NSFW | da creare | Isolata per non appesantire la review del core |
| — | Yokai Desktop | da creare | App locale, RPC, no user token |
| — | Yokai Panel | da creare | Web, verify avanzato + OAuth2 |

---

## 🔜 Prossimo passo concreto

**Repository layer per dominio** (punto 1 di "Non ancora iniziato"),
propedeutico a tutto il resto: senza quello, ogni cog futuro rischia di
scrivere query SQL sparse invece di passare da un punto unico.

Subito dopo: **Moderation**, perché è il primo modulo "vero" e il
banco di prova del pattern intero (premium registry + check runtime +
repository).
