# REVIEW.md — Revisione completa del codice iYokai

Revisione del 28/09/2026, fatta **prima** di qualsiasi riscrittura.
Nessun file di codice è stato modificato per scriverla. Ogni bug qui
sotto è stato verificato leggendo il codice e i suoi chiamanti; i più
gravi li ho ricontrollati una seconda volta a mano. Quelli che si
possono confermare solo con il bot collegato a Discord sono segnati
**DA VERIFICARE LIVE**.

Codici usati: **SEC** = sicurezza, **BUG** = funzionamento sbagliato o
silenzioso, **PERF** = prestazioni. Gravità: 🔴 alta, 🟠 media, 🟡 bassa.
Ogni voce ha un codice (es. SEC-3) per poterla citare quando decidiamo
cosa fare.

---

## 0. In sintesi

- **~36.000 righe** di codice (esclusi i test), 32 moduli, 97 comandi
  top-level su 100, 252 comandi totali.
- **9 problemi di sicurezza seri** (SEC), tra cui: chiunque può usare
  `/ban`, `/kick`, `/clear`; un admin di un server qualsiasi può
  "rubare" gli utenti di un altro server con `/restore-users`; un
  utente bannato può cancellarsi il ban da solo.
- **Molte funzioni che sembrano funzionare ma non lo fanno**: `/ticket
  close` non cancella mai il canale, `/setup` si rifiuta sempre di
  aprirsi, il backup non registra mai la coppia main→backup (quindi
  snapshot e restore non hanno mai dati), metà dei filtri AutoMod non
  scatta mai.
- **Nessun comando è nascosto a chi non può usarlo**: tutti vedono
  tutto nel menu `/`, compreso `/owner eval`.
- **Nessuna funzione di log/annunci supporta canali forum**, quasi
  nessuna sa creare il canale da sola, e i log vanno tutti in **un
  solo canale**.
- **La lingua del server non cambia niente**: esiste il comando
  `/config language set`, ma nessun messaggio del bot la legge.

---

## 1. Limiti reali di Discord che cambiano il piano (verificati)

Li ho controllati nel sorgente di discord.py installato e nella
documentazione Discord, non a memoria. Alcune delle tue richieste
vanno adattate per questi motivi.

| # | Limite | Conseguenza per la tua richiesta |
|---|---|---|
| L1 | **Massimo 100 comandi top-level** per bot | Il raggruppamento `/owner`, `/admin`, `/mod`… risolve il problema alla radice: si passa da 97 a circa 12. |
| L2 | **Massimo 25 sotto-comandi per gruppo** (discord.py solleva errore al 26°) | `/owner` ne ha **già 25**: non ci sta nemmeno un comando in più. Serve usare sotto-gruppi, es. `/owner premium grant`, `/owner cog reload`. |
| L3 | **Un solo livello di sotto-gruppo** (`/gruppo sottogruppo comando`, non oltre) | L'albero va progettato su 3 livelli massimo. |
| L4 | **Un bot non può rendere un comando visibile a un singolo utente** (Permissions v2: servono token utente, non del bot) | "Visibile solo a bot_owner_id" non si può fare su comandi globali. **Soluzione:** `/owner` registrato **solo nel tuo server privato** (MAIN_GUILD_ID) + `default_permissions(administrator)` + controllo `OWNER_ID` a runtime. Negli altri server non esiste proprio. |
| L5 | `default_permissions` accetta **solo permessi Discord** (es. Amministratore, Bannare membri), non "ruoli definiti dal bot" | Per `/admin` e `/mod`: il menu li nasconde a chi non ha il permesso Discord base. Chi è admin/mod **solo tramite ruolo assegnato dal bot** (`/admin ruolo-admin add`) passa il controllo a runtime, ma vede il comando solo se il proprietario del server lo abilita per quel ruolo in *Impostazioni server → Integrazioni → iYokai*. Il bot non può farlo da solo (vedi L4). Il comando può però **spiegare all'admin come farlo** subito dopo l'assegnazione. |
| L6 | **I nomi dei comandi si traducono in base alla lingua del client Discord di chi li usa**, non in base a un'impostazione del server (localizzazioni native `name_localizations`) | Con i comandi globali, `/banna` contro `/ban` dipende dalla lingua dell'app Discord dell'utente, non dalla lingua scelta per il server. L'impostazione del server si può comunque applicare a **tutti i messaggi di risposta del bot**. Vedi §7 per le due opzioni. |
| L7 | `message_content` è un **privileged intent**: va attivato nel Developer Portal e, sopra i 100 server, approvato da Discord con motivazione | Oggi è spento, e questo **rompe silenziosamente** diverse funzioni già scritte (vedi BUG-5). Lo attiviamo come hai chiesto, ma il toggle nel Portal devi farlo tu. |
| L8 | Senza `message_content`, **anche i messaggi letti via REST arrivano vuoti** (politica Discord su tutte le API) | Due docstring del progetto affermano il contrario (ticket, spam-trap) e sono sbagliate. |

Fonti: [Discussion #4831 — Update to application command permissions](https://github.com/discord/discord-api-docs/discussions/4831), [Discussion #4862 — Allow bots to manage their own permissions](https://github.com/discord/discord-api-docs/discussions/4862), [Application Commands docs](https://discord.com/developers/docs/interactions/application-commands); sorgente `discord/app_commands/commands.py` righe 1520, 1670, 1923.

---

## 2. Sicurezza (da sistemare per prima, a prescindere dal resto)

- **SEC-1 🔴 Comandi di moderazione senza permessi.**
  - **Dove:** `cogs/moderation/actions.py`, `softban_mute.py`,
    `channel_control.py`, `clear.py`, `case_system.py`.
  - **Comandi coinvolti:** `/warn /kick /ban /tempban /unban /timeout
    /untimeout /softban /mute-role /unmute-role /lock /unlock /slowmode
    /clear /modcase /modnote`. Nessuno ha un controllo di permesso:
    viene confrontata solo la posizione dei ruoli.
  - **Esempio:** un membro con un ruolo cosmetico sopra @everyone
    può bannare un nuovo arrivato. Chiunque può fare `/clear 200`,
    `/lock` o `/unban` di qualsiasi ID. La funzione
    `can_use_moderation_commands` esiste già, ma non viene mai
    chiamata.
- **SEC-2 🔴 `/restore-users` accetta qualunque server di origine**
  (`cogs/utility/restore.py:117`).
  - **Il problema:** non controlla che il server attuale sia il
    backup di quello di origine.
  - **Esempio:** un admin del server X scrive l'ID del server di
    qualcun altro. Gli utenti con il token salvato vengono fatti
    entrare a forza nel server X, gli altri ricevono un DM di invito.
- **SEC-3 🔴 OAuth del restore non firmato.**
  - **Dove:** `core/restore_oauth_logic.py:35`,
    `core/restore_web_server.py:86`.
  - **Il problema:** lo `state` è in chiaro (`origine:dest:user_id`)
    e l'identità dell'utente non viene mai verificata con
    `/users/@me`.
  - **Esempio:** un utente bannato si costruisce il link con il
    proprio ID e il suo stato "bannato" si azzera. Oppure qualcuno
    scrive l'ID di un altro e sovrascrive il token della vittima con
    il proprio.
- **SEC-4 🔴 Assegnazione di ruoli sopra il proprio grado.**
  - **Dove:** `/shop add-item`, `/level-roles add`, `/rolemenu
    add-option`, `/verify setup` (ruolo verificato).
  - **Il problema:** nessun controllo sulla gerarchia dei ruoli.
  - **Esempio:** chi ha solo "Gestisci server" mette @Admin in
    vendita a 1 moneta e se lo compra, oppure lo imposta come ruolo
    "verificato".
- **SEC-5 🔴 `/nonstop-main` modifica una playlist globale** (condivisa
  da tutti i server) con il solo permesso "Gestisci server" di *un
  server qualsiasi*.
  - `add-local` costruisce il percorso del file senza controlli, quindi
    con `../` si esce dalla cartella (path traversal sulla macchina
    del nodo Lavalink).
  - `cogs/music/player.py:801-902`.
  - **Soluzione:** comandi owner-only e nome file validato.
- **SEC-6 🔴 Template personalizzati passati a `str.format`.**
  - **Dove:** `core/feed_parsing_logic.py:148`,
    `core/custom_webhook_logic.py:109`.
  - **Esempio:** un template come `{title:>999999999}` alloca GB di
    RAM e fa crollare **l'intero processo**, compresi i 5 bot musicali
    e il Creator. Un `{` spaiato manda in errore l'intero giro dei
    feed.
- **SEC-7 🟠 Nessun `allowed_mentions` in tutto il progetto.**
  - **Il problema:** testi di promemoria, titoli RSS e payload dei
    webhook esterni possono contenere `@everyone`, e il bot li
    pinga.
  - **Soluzione:** una riga globale nel costruttore del bot.
- **SEC-8 🟠 SSRF nei feed** (`core/feed_watcher.py:48`).
  - **Il problema:** qualunque URL viene scaricato: indirizzi
    interni, `127.0.0.1:8420` (il nostro stesso server web), metadati
    cloud. In più la risposta non ha limite di dimensione.
- **SEC-8b 🟠 Lo spam-trap banna anche lo staff.**
  - **Il problema:** nessuna esenzione per mod o admin
    (`cogs/security/spam_trap.py:333`). Il ban viene anche propagato
    a tutta la rete global-ban.
  - I bottoni di appello non controllano chi li preme: chiunque veda
    il thread può sbannare.

---

## 3. Bug gravi (funzioni rotte o che falliscono in silenzio)

- **BUG-1 🔴 `/ticket close` va in crash a ogni chiusura.**
  - **Dove:** `cogs/tickets/tickets.py:646`.
  - **Il problema:** chiama `channel.delete(..., delay=10)`, ma
    `delete` non accetta `delay` (verificato: firma
    `(self, *, reason=None)`).
  - **Effetto:** il ticket risulta chiuso nel database ma il canale
    resta lì per sempre.
- **BUG-2 🔴 `/setup` si rifiuta sempre** (`cogs/utility/setup.py:318`).
  - **Il problema:** i moduli registrati sono 32, oltre il limite di
    25 opzioni di un menu a tendina.
  - **Effetto:** circa 26 moduli (suggerimenti, sticky, poll,
    promemoria…) non si possono attivare da nessuna interfaccia.
- **BUG-3 🔴 Il backup non registra mai la coppia main→backup.**
  - **Il problema:** `backup_repo.define_backup()` non viene chiamata
    da nessuna parte del codice di produzione.
  - **Effetto:** `/promuovi-backup` dice sempre "non registrato", lo
    snapshot settimanale degli utenti non parte mai, e
    `/restore-users` non ha mai dati.
- **BUG-4 🔴 Gli slot del bot Creator si esauriscono per sempre**
  (`core/backup_queue_worker.py:169`).
  - **Il problema:** se un job di backup fallisce, il server creato
    non viene cancellato.
  - **Effetto:** dopo 10 fallimenti il Creator è pieno per sempre e
    tutti i backup si bloccano. Il messaggio all'utente dice che gli
    slot si liberano da soli, ed è falso.
- **BUG-5 🔴 Funzioni che non funzionano con `message_content` spento.**
  Oggi appaiono attive, ma lavorano su messaggi vuoti:
  - filtri AutoMod avanzati: anti-link, anti-caps, anti-zalgo,
    anti-emoji, anti-allegati (`cogs/automod/automod.py`);
  - trascrizioni dei ticket (sempre "nessun testo");
  - trascrizioni e contenuto dello spam-trap;
  - mirror del backup, che riempie il server di backup di messaggi
    vuoti.

  Si risolvono tutte attivando l'intent (L7).
- **BUG-6 🔴 `/config rollback` riporta un successo che non c'è.**
  - **Dove:** `core/database.py:646`, riprodotto con uno script.
  - **Effetto:**
    - Il rollback di un `reset` o di un `import` non ripristina
      niente e scrive un'impostazione spazzatura.
    - Il rollback della lingua non cambia la lingua.
    - Il rollback di un'impostazione appena creata la trasforma in
      `null`, e da quel momento `/ticket-support-role` va in crash
      a ogni uso.
  - In tutti questi casi risponde "✅ Rollback eseguito".
- **BUG-7 🔴 Se un solo bot non riesce a partire, si spengono tutti**
  (`main.py:580`).
  - **Il problema:** main, Creator e i 5 bot musicali partono in un
    unico `asyncio.gather`.
  - **Esempio:** basta un token musicale sbagliato perché il bot
    principale muoia con gli altri.
  - In più, allo spegnimento nessuna sessione HTTP e nessun loop
    viene chiuso.
- **BUG-8 🔴 Lo scheduler può fermarsi per sempre** (`core/scheduler.py:291`).
  - **Il problema:** il loop non ha try/except.
  - **Effetto:** un errore del database basta a fermare fino al
    riavvio tempban, promemoria e messaggi programmati.
  - Inoltre le righe senza handler restano "in attesa" per sempre:
    con 50 righe così la coda si blocca del tutto.
- **BUG-9 🔴 Dopo un riavvio la musica può restare bloccata**
  (`core/music_fleet.py`).
  - **Il problema:** la tabella `music_sessions` non viene svuotata
    all'avvio.
  - **Effetto:** i bot musicali risultano "occupati" per sempre e la
    musica diventa indisponibile.
- **BUG-10 🔴 `/nonstop-main add-local` non trova i file locali.**
  - **Il problema:** il prefisso `local:` viene trasformato in una
    ricerca su YouTube Music.
  - **Effetto:** la traccia salvata è un risultato YouTube a caso.
- **BUG-11 🔴 L'anti-nuke può punire il bot stesso.**
  - **Il problema:** il bot non è escluso dai conteggi.
  - **Esempio:** durante un recupero ricrea canali e ruoli, supera
    le soglie e punisce se stesso.
  - In più la punizione di default (`strip_roles`) fallisce su tutti
    i bot, che hanno ruoli gestiti. Eppure i bot compromessi sono il
    caso più comune di nuke.
- **BUG-12 🔴 L'anti-raid scatta per un singolo ingresso normale.**
  - **Esempio:** entra un utente senza avatar e parte il lockdown
    completo. Il livello di verifica del server resta al massimo per
    sempre, e ogni ingresso manda un DM al proprietario.
  - Inoltre ingressi simultanei creano più ruoli "Quarantined".
- **BUG-13 🔴 Il gestore errori globale tratta "non hai i permessi"
  come un crash** (`core/premium.py:431`).
  - **Effetto:** chi non ha il permesso legge "errore imprevisto", e
    l'evento finisce nei log come ERROR.
- **BUG-14 🔴 Monete e ricompense sfruttabili** (`cogs/leveling/leveling.py`).
  - `/daily` e `/work` si possono riscuotere due volte con due invii
    ravvicinati.
  - `/cassa sblocca-premium` con un doppio clic addebita due volte.
  - `/clan compra-canale` può dare il canale gratis.
  - `/shop buy` toglie le monete anche se il ruolo non viene dato.
- **BUG-15 🔴 I clan finanziati con un trasferimento vengono cancellati
  dopo 24 ore**, perché non risultano mai "ufficiali". Le monete
  trasferite si perdono.
- **BUG-16 🔴 Il limite di quota YouTube si esaurisce in circa 3 ore**
  (`core/youtube_watcher.py`).
  - **Perché:** anche con un solo canale si consumano 28.800 unità al
    giorno, contro le 10.000 gratuite.
  - **Soluzione:** feed RSS + `videos.list` (1 unità).

---

## 4. Bug medi (raggruppati per area)

**Moderazione, AutoMod e sicurezza**
- `/automod anti-spam-* seconds=`: il valore viene salvato ma ignorato
  (le finestre sono fisse a 10 e 30 secondi).
- Sincronizzazione AutoMod: `edit()` cancella le regex e le allow-list
  aggiunte a mano dall'admin.
- Blacklist dei link aggirabile con `evil.com:443`, `x@evil.com` o
  `sub.evil.com`.
- Escalation: i conteggi sono gonfiati (ogni azione della stessa
  violazione conta) e soggetti a race condition.
- Anti-nuke: una sola lettura dell'audit log, senza attesa, quindi
  molti eventi non vengono attribuiti.
- `/global-ban enable` aggira il controllo premium.
- Verify: nessun `defer`, quindi con il bot carico l'interazione
  scade dopo 3 secondi anche se il ruolo è stato dato.

**Ticket, vocali temporanei e log**
- Ticket duplicati con un doppio clic.
- Un canale ticket cancellato a mano blocca l'utente per sempre.
- `claim`, `priority` e `add` non hanno controllo staff.
- `/ticket-support-role remove` non rimuove davvero il ruolo storico.
- Vocali temporanei: i canali restano orfani (nessuna pulizia
  all'avvio).
- `/voice rename` scade (Discord permette 2 rinomine ogni 10 minuti).
- `/voice transfer` non sposta i permessi al nuovo proprietario.
- Log avanzati:
  - Spostare un canale genera N messaggi di log.
  - Il mute volontario viene registrato come "mutato dal server".
- `/logs user|channel` può superare i 4096 caratteri di un embed e
  fallire.

**Utility**
- `/config import` non valida i dati: un JSON sbagliato rompe tutti i
  comandi del server.
- Sticky: messaggi persi o duplicati.
- Role menu: l'opzione `toggle=False` viene ignorata.
- Promemoria: possono pingare @everyone.
- La pulizia dei token OAuth promessa dopo 90 giorni non gira mai
  (privacy).
- Lo snapshot settimanale parte prima del login e trova 0 server.
- `/define-backup` non ha limiti per server: un admin può occupare
  tutti gli slot del Creator.

**Economia e clan**
- XP vocale dei clan senza anti-farm: un alt da solo nel canale AFK
  guadagna 24 ore su 24.
- Il decay della tesoreria e quello personale scattano entro un'ora
  dalla creazione.
- `/clan invita` aggiunge senza consenso, e non esiste `/clan lascia`.
- `/clan crea` e `/clan sciogli` non fanno `defer`, quindi scadono.
- **Nessun comando economia/clan controlla se il modulo è attivo:**
  anche con il leveling spento `/daily`, `/shop` e `/clan` funzionano.
- Giveaway in thread o forum: i vincitori vengono estratti ma nessuno
  viene avvisato.

**Musica**
- La cascata dei nodi "pubblici prima, locale per ultimo" non esiste:
  wavelink sceglie il nodo con meno player, quindi di solito il
  locale.
- I bot musicali worker probabilmente non riproducono audio, perché
  la sessione Lavalink è registrata a nome del bot principale
  (**DA VERIFICARE LIVE**).
- Chiunque in un canale vocale può usare `/stop` o `/skip` su un
  player in un altro canale.

**Fun**
- I comandi immagine, `animal` e `search-image` non fanno `defer`:
  sopra i 3 secondi falliscono con "Unknown interaction".

**Core**
- Una race nella cache dei moduli può lasciare un modulo nello stato
  sbagliato fino al riavvio.
- Twitch si rompe oltre 100 iscrizioni: la richiesta API è unica, non
  divisa in blocchi.
- Feed RSS: se sparisce l'ultimo elemento visto, ripubblica tutto il
  feed.
- `bot_stats` accumula un elemento per ogni comando senza mai
  svuotarsi (memory leak lento).

---

## 5. Bug minori (in breve)

- Casi di moderazione creati prima dell'azione: se l'azione fallisce,
  resta un caso orfano.
- Un errore "ephemeral" dopo un `defer` pubblico diventa visibile a
  tutti.
- Il ruolo Muted/Quarantined non blocca i thread.
- Il giorno per l'XP vocale usa l'ora locale del server invece di
  UTC.
- Trasferimenti A→B e B→A contemporanei possono andare in deadlock.
- `duration_logic` accetta `9999999999w`, che va in overflow.
- `OWNER_ID` non numerico produce un crash con un messaggio poco
  chiaro.
- La prima volta, il watermark del soundboard salta l'evento, e il
  rollback della config può ripristinarlo vecchio.
- `/owner eval` e `/owner shell`:
  - il log viene scritto *dopo* l'esecuzione (un hang non lascia
    traccia);
  - l'output si perde oltre i 3 secondi;
  - il processo shell non viene ucciso al timeout.
- Suggerimenti e richieste: due staff che cliccano insieme decidono
  entrambi.
- Ghost-ping: segnala anche i messaggi cancellati dai moderatori.
- `/alerts add` mostra un ID senza il prefisso `RSS-`, che però
  `remove` richiede.

---

## 6. Permessi e visibilità: proposta di nuova struttura comandi

**Stato attuale (verificato caricando l'albero reale):**
- 0 comandi su 97 hanno `default_permissions`.
- 0 su 97 sono `guild_only`.
- Tutti vedono tutto, anche nei DM.

**Proposta** (rispetta L2 e L3; i nomi sono indicativi, versione IT
tra parentesi):

| Gruppo | Chi lo vede (menu) | Controllo a runtime | Contenuto |
|---|---|---|---|
| `/owner` | **Solo nel tuo server privato**, solo admin | `OWNER_ID` | sotto-gruppi `premium`, `blacklist`, `cog`, `system` (eval, shell, memory, stats, announce, leave-guild) |
| `/admin` | Gestisci server | Amministratore **o** ruolo bot-admin | `setup`, `wizard`, `config …`, `lingua`, `ruolo-admin add/remove/list`, `ruolo-mod add/remove/list`, `backup …`, `restore …`, `benvenuto …`, `economia …` (shop, level-roles, monthly-winners, giveaway, assegna-*) |
| `/mod` | Moderare membri | permesso Discord specifico per comando **o** ruolo bot-mod | `ban`, `kick`, `warn`, `timeout`, `tempban`, `softban`, `mute`, `clear`, `lock`, `slowmode`, `caso …`, `nota …` |
| `/security` | Gestisci server | Amministratore o bot-admin | sotto-gruppi `automod` (22, ci stanno), `escalation`, `antinuke`, `antiraid`, `globalban`, `verify`, `spamtrap` + `score`, `heatmap` |
| `/log` | Gestisci server | Amministratore o bot-admin | `canale <tipo> <canale>`, `crea-canali`, `forum`, `stato`, `cerca utente/canale`, `esporta` |
| `/ticket` | tutti | staff per i comandi staff | apri/chiudi/claim…; configurazione sotto `/admin ticket …` |
| `/voice` | tutti | proprietario del canale | come ora; configurazione sotto `/admin voice …` |
| `/music` | tutti | nello stesso canale del player | play, skip, stop… (`/nonstop-main` va sotto `/owner`) |
| `/level` (`/livello`) | tutti | — | rank, leaderboard, daily, work, pay, balance, shop list/buy |
| `/clan` | tutti | ruoli clan | come ora (+ `lascia`) |
| `/fun` | tutti | — | come ora + ship, rate |
| `/utility` | tutti | — | ping, poll, reminder, suggest, report, serverstats, cerca-comando, reactionsnipe |

- **Risultato:** da 97 comandi top-level a circa **12**, con ampio
  margine.
- **Attenzione, cambiamento non retrocompatibile:** gli utenti dei
  server esistenti troveranno i comandi con nomi nuovi. I vecchi
  spariscono al primo sync.

---

## 7. Lingue, command list ITA/ENG e `/cerca_comando`

**Stato attuale:**
- `core/i18n.py` ha 4 frasi e nessun file lo usa.
- I nomi dei comandi mescolano italiano e inglese (`/cassa`,
  `/assegna-lobby` accanto a `/shop` e `/daily`).
- Alcune risposte sono in inglese (role menu, verify, spam-trap,
  messaggi di benvenuto di default).
- `/search` oggi, misurato sui comandi reali:
  - "bannare un utente" restituisce pay, logs user, unban: `/ban` non
    è tra i primi 3;
  - "mute a user" restituisce automod mute-duration.
  - Il motivo è che conta solo le parole uguali, senza sinonimi né
    traduzioni, e suggerisce anche comandi che l'utente non può
    usare (compreso `/owner eval`).

**Proposta:**
1. **Un unico file di testi** (es. `locales/it.json` e
   `locales/en.json`, oppure un modulo Python) con, per ogni comando:
   - nome IT/EN
   - descrizione IT/EN
   - parole chiave e sinonimi IT/EN (es. "bannare, espellere per
     sempre, ban, bannare utente / ban, ban user, block")
   - per ogni messaggio di risposta: testo IT/EN con variabili
     (`{utente}`, `{motivo}`)
2. **Nomi dei comandi**, due opzioni (per il limite L6):
   - **A (consigliata):** nome base inglese + localizzazione italiana
     nativa. Chi usa Discord in italiano vede `/mod banna`, gli altri
     `/mod ban`. La lingua del server controlla le **risposte** del
     bot. Nessun costo tecnico.
   - **B:** registrare i comandi **server per server** nella lingua
     scelta. Si ottiene esattamente quello che chiedi, ma servono un
     sync per ogni server, i limiti di Discord sulle creazioni
     giornaliere per server, avvii più lenti con molti server, e in
     DM non ci sono comandi.
3. **`COMMAND_LIST_ITA.md` e `COMMAND_LIST_ENG.md`**, generati in
   automatico dallo stesso file di testi, così non vanno mai
   disallineati.
4. **`/utility cerca-comando` (`/utility command-search`):**
   - cerca su nomi, descrizioni e parole chiave in entrambe le
     lingue;
   - mostra solo i comandi che l'utente **può usare** e che hanno il
     modulo attivo.

---

## 8. Canali di output: audit e proposta

**Stato attuale:**
- Log: **un solo canale** per tutti i tipi di log (`/logs-setup`),
  con eventi base, avanzati, soundboard e trascrizioni ticket tutti
  insieme.
- **Forum:** nessuna funzione li supporta. Quasi tutte accettano solo
  `TextChannel`, e il repository degli eventi rifiuta esplicitamente
  i forum.
- **Creazione automatica:** la fa solo lo spam-trap.
- Canale di alert anti-nuke: si imposta solo da `/anti-raid
  alert-channel`, che richiede il modulo anti-raid. Chi usa solo
  l'anti-nuke non può impostarlo.
- **Canali fissi o impliciti:** level-up e drop vanno nel canale
  dove l'utente ha scritto (non configurabile). I promemoria vanno
  nel canale dove è stato creato il comando. Gli annunci owner vanno
  nel `system_channel` o nel primo canale scrivibile.
- **Non loggati da nessuna parte:** `/untimeout`, `/unmute-role`,
  scadenza dei tempban, azioni dell'escalation.

**Funzioni che scrivono in un canale e dovranno usare il nuovo
sistema:** log base, log avanzati, soundboard, trascrizioni ticket,
mod-log (casi), log AutoMod, report, alert anti-nuke/anti-raid, log
verify, spam-trap, ghost-ping, benvenuto/addio/boost, suggerimenti,
richieste comandi custom, giveaway, podio mensile, bacheca clan,
level-up (opzionale), drop (opzionale), feed/Twitch/YouTube, sticky,
messaggi programmati, promemoria (fallback).

**Proposta: un unico "router dei canali"** in `core/` che usano tutti:
- **Configurazione per tipo:** per ogni *tipo* di uscita (log-membri,
  log-messaggi, log-moderazione, log-vocale, log-server, log-automod,
  alert-sicurezza, benvenuto, …) si salva un canale.
- **Canale testuale o forum:** un canale testuale, **oppure** un
  forum. Nel forum il bot crea e riusa un post per tipo di log (log
  avanzati), oppure un post per utente o per caso, da decidere.
- **Tre modi di impostarlo:**
  1. `/log canale <tipo> <canale>`: usa un canale esistente (testo o
     forum);
  2. `/log crea-canali`: il bot crea una categoria "iYokai Log" con
     un canale per tipo, già con i permessi giusti (visibili solo
     allo staff);
  3. `/log crea-forum`: il bot crea un forum con un post per tipo.

  Lo stesso schema vale per gli altri moduli (`/admin benvenuto
  canale`, ecc.) e in futuro dal Web Panel, che scriverà sulle stesse
  impostazioni.
- **Canale sparito:** se il canale configurato non esiste più, il
  bot lo segnala una volta sola agli admin invece di fallire in
  silenzio.

---

## 9. Descrizioni in testa ai file (docstring)

Circa **80 file** hanno un'intestazione che non si limita a "a cosa
serve e cosa copre":
- racconti di sessioni precedenti ("Fase 70b", "corretto in una
  sessione successiva");
- saggi sul "perché questa scelta";
- citazioni di conversazioni con te;
- riferimenti a Gemini, ChatGPT o Grok.

Alcune sono **sbagliate o vecchie**:
- `main.py` dice che il Creator ha un proprio avvio (falso);
- `memory_guard.py` dice "Music non ancora scritto";
- `i18n.py` dice di avere un utilizzatore reale (non ce l'ha);
- `backup_repo.py` dice che la coda è serializzata (non lo è);
- `feed_parsing_logic.py` dice "nessun server web" (ce ne sono due);
- le docstring di ticket e spam-trap sul contenuto via REST (vedi
  L8);
- `cogs/fun/entertainment.py` ha un'intestazione di 48 righe con la
  cronaca della sessione di ieri.

**Proposta:** riscriverle tutte con lo stesso formato fisso, breve:
- *nome file*
- *a cosa serve* (1-2 frasi)
- *funzioni coperte* (SPEC §)
- *dipende da* (solo se non ovvio)

Le spiegazioni tecniche utili restano come commenti vicino al codice
a cui si riferiscono, non in testa al file. Le cronache delle
sessioni restano in PROGRESS.md.

---

## 10. Prestazioni (dove si può alleggerire davvero)

- **PERF-1: una query al database per ogni messaggio**, spesso più
  di una. Riguarda leveling (transazione con lock anche durante il
  cooldown), spam-trap (INSERT più SELECT), ticket (SELECT), mirror
  del backup, sticky e impostazioni AutoMod.
  - **Soluzione:** cache in memoria (esiste già `BoundedCache`) per
    le impostazioni del server e per i cooldown XP. La maggior parte
    dei messaggi non toccherebbe più il database.
- **PERF-2:** `get_guild_setting` non ha cache e viene chiamata per
  ogni evento di log. Basta estendere la cache dei moduli all'intera
  riga di configurazione del server.
- **PERF-3: tabelle che crescono senza limite.**
  - `spam_trap` ha una riga per ogni messaggio e la funzione di
    pulizia esiste ma non viene mai chiamata.
  - `clan_treasury_ledger` riceve una riga per ogni membro in voce
    ogni minuto.
  - `event_log` usa un ID `SERIAL`, che può finire i numeri su una
    tabella molto trafficata.
- **PERF-4: loop vocali costosi.** Ogni minuto fanno circa 4-6 query
  per ogni membro in voce di ogni server (leveling più clan). Con
  server grandi possono superare il minuto. Vanno raggruppati per
  server.
- **PERF-5: chiamate all'audit log che si possono evitare.**
  - L'anti-nuke fa una chiamata all'audit log **prima** di
    controllare se il modulo è attivo, su ogni evento, compresa ogni
    uscita di un membro, in tutti i server.
  - `/restore` fa lo stesso su ogni uscita.
- **PERF-6:** il decay settimanale e mensile lavora utente per
  utente; basterebbe una sola UPDATE.
- **PERF-7:** i feed vengono scaricati uno alla volta e gli URL
  duplicati tra server non vengono uniti.

---

## 11. Codice morto, duplicazioni, valori fissi

- **Morto:**
  - colonna `guild_config.prefix`;
  - `NSFW_TOKEN` (obbligatorio ma mai usato; verrà usato con §16.10);
  - `WEB_PANEL_SECRET_KEY`;
  - `core.i18n.t`;
  - `can_use_moderation_commands`;
  - `define_backup` (dovrebbe essere usata, vedi BUG-3);
  - `prune_old_index` e `purge_expired_voluntary_leaves` (vanno
    schedulate);
  - una decina di metodi di repository senza chiamanti;
  - `main_radio_logic.next_track_index`;
  - il ruolo clan `co_owner`, che non si può assegnare.
- **Duplicato:**
  - la frase "solo dentro un server" è scritta circa 45 volte;
  - `_alert_staff`, `_case_embed` e `_replace` sono copiati in più
    file;
  - suggerimenti e richieste di comandi custom sono quasi identici;
  - 6 worker e 3 watcher ripetono lo stesso schema di avvio;
  - ci sono 4 gestori di cooldown fatti a mano.
- **Valori fissi da rendere configurabili:**
  - XP, monete, drop e costi dei clan;
  - nomi dei ruoli "Muted", "Quarantined", "Capo Clan";
  - finestre dell'AutoMod;
  - nodi Lavalink pubblici;
  - durate di conservazione.
- **Pericoloso:** `PREMIUM_ALPHA_UNLOCK_ALL` vale `True` di default.
  Se in produzione dimentichi la variabile, tutto diventa gratis in
  silenzio.

---

## 12. Piano proposto, a fasi

Ogni fase si chiude come sempre: test prima, suite completa due
volte, commit, push e verifica dello SHA, aggiornamento di
SPEC/PROGRESS.

| Fase | Contenuto | Perché in quest'ordine |
|---|---|---|
| **R0 — Sicurezza** | SEC-1…8b | Sono falle aperte oggi, indipendenti dal refactor. |
| **R1 — Bug che rompono funzioni** | BUG-1…16 + gestore errori + `allowed_mentions` globale + avvio e spegnimento dei bot isolati | Il refactor non deve partire da funzioni rotte, altrimenti non si distingue un bug vecchio da uno nuovo. |
| **R2 — Message content** | Attivare l'intent, poi message delete/bulk/edit log (§8.16), snipe ed editsnipe (§14.9/14.10), verificare AutoMod, ticket e spam-trap | Si fa **dopo R3**: i nuovi log di messaggi devono nascere già nel router dei canali. |
| **R3 — Router dei canali** | Canali per tipo, forum, creazione automatica; migrazione delle impostazioni esistenti (il `log_channel_id` attuale diventa il valore di default per tutti i tipi) | Serve prima dei log nuovi, così nascono già con il sistema giusto. |
| **R4 — Struttura comandi** | Nuovi gruppi `/owner`/`/admin`/`/mod`/…, `default_permissions`, ruoli bot-admin e bot-mod, `/owner` solo nel server privato | È il cambiamento più grande, e va fatto una volta sola. |
| **R5 — Lingue** | File dei testi IT/EN, localizzazioni, risposte tradotte, COMMAND_LIST_ITA/ENG, `/cerca-comando` nuovo | Va fatto dopo R4, perché i nomi dei comandi cambiano lì. |
| **R6 — Pulizia** | Docstring, codice morto, duplicazioni, prestazioni (PERF-1…7) | Si può anche distribuire nelle fasi precedenti, file per file, man mano che li tocchiamo. |
| **R7 — NSFW** | §16.10 come istanza separata con `NSFW_TOKEN`, sullo stesso schema dei bot musicali | Dopo R4 e R5, così nasce già con i gruppi e le lingue nuovi. |

Ordine effettivo consigliato: **R0 → R1 → R3 → R2 → R4 → R5 → R7**,
con R6 distribuita lungo il percorso.

---

## 13. Decisioni che servono da te prima di partire

1. **Lingua dei nomi dei comandi:** opzione A (localizzazione nativa
   per client) o B (registrazione per server)? Vedi §7.
2. **Ruoli bot-admin e bot-mod:** va bene che chi è admin solo
   tramite ruolo del bot debba essere abilitato una volta dal
   proprietario in *Integrazioni* per vedere i comandi (L5)?
   L'alternativa è rendere `/admin` visibile a tutti, con il blocco
   solo a runtime.
3. **Forum dei log avanzati:** un post per tipo di log, o un post per
   utente o caso?
4. **Retrocompatibilità:** i vecchi nomi dei comandi spariscono
   subito con R4, oppure li teniamo per un periodo? Tenerli costa
   slot: siamo a 97 su 100, quindi possiamo tenerne pochissimi.
5. **Quota YouTube (BUG-16):** passo al metodo RSS + `videos.list`?
