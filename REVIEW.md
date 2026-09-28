# REVIEW.md — Revisione completa del codice iYokai

Revisione del 28/09/2026, fatta **prima** di qualsiasi riscrittura, in
**due passate**. La prima (§2–§11) copre area per area tutti i cog e
tutto `core/`. La seconda (§12–§16) copre quello che la prima non
aveva guardato:
- corrispondenza SPEC.md ↔ codice;
- server web, segreti e dipendenze;
- qualità dei test, con coverage misurata;
- ciclo di vita di interazioni, listener e dati;
- GDPR.
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

**Aggiunte della seconda passata:**
- **SPEC.md sovrastima.** Delle 238 voci `[x]`, circa **28 non sono
  davvero fatte** e circa **25** sono rotte da bug di questo log.
  Circa **55 voci funzionanti non si possono accendere** da nessun
  comando: dipendono da `/setup`, che è rotto (BUG-2).
- **Dati mai cancellati.** Quando il bot esce da un server i dati
  restano per sempre, e non esiste un modo per cancellare i dati di
  un utente che lo chiede. È un problema **GDPR** (sei in UE).
- **Altri 8 problemi di sicurezza** (SEC-9…16), tra cui:
  - i token dei webhook e i codici OAuth finiscono nei log;
  - gli utenti in blacklist possono ancora usare tutti i bottoni;
  - un'immagine "bomba" da 15 MB può far crollare tutti i bot.
- **Test: 2054 test verdi ma coverage al 71%.** I comandi dove
  stanno i bug sono testati al 20–45%, e nessun test li esegue
  davvero. Per questo nessun test ha mai visto BUG-1, BUG-2, BUG-3,
  BUG-6 e SEC-1.
- **Schema del database senza versioni.** Ogni modifica a una tabella
  esistente oltre "aggiungi colonna" va fatta a mano. Serve prima
  delle fasi di refactor.

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
| L9 | `default_permissions` funziona **solo sul comando/gruppo di primo livello**: sui sotto-comandi viene ignorato (scritto nel sorgente di discord.py) | La delega che fai in *Integrazioni* vale per **l'intero gruppo** (es. tutto `/mod`), non per il singolo sotto-comando. Se vuoi dare a un ruolo "helper" il timeout ma non il ban, servono due gruppi separati, oppure un controllo più fine lato bot. Vedi §6. |
| L10 | La blacklist di un `CommandTree` blocca solo i comandi slash: **bottoni, menu e modali non passano da lì** | La blacklist va controllata anche sui componenti (vedi SEC-10). |

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

**Modello di accesso** (deciso con te il 28/09): chi non ha
ricevuto il permesso, in un modo o nell'altro, **non vede** i
comandi.
- **Visibilità.** Ogni gruppo ha un `default_permissions`: gli
  amministratori lo vedono già. Il proprietario o un admin può
  delegarlo a ruoli specifici in *Impostazioni server → Integrazioni
  → iYokai*, senza dare il permesso Amministratore. Discord allora
  lo **mostra e lo consente** solo a quei ruoli.
- **Controllo a runtime coerente con la delega.** Il bot **non deve**
  richiedere di nuovo "Amministratore" dentro il comando, altrimenti
  bloccherebbe proprio i ruoli delegati. Discord ha già deciso chi
  può usarlo. Il bot controlla solo quello che Discord non vede:
  gerarchia dei ruoli, e che il bot stesso abbia il permesso
  per l'azione.
- **Granularità** (L9). La delega nativa vale per gruppo intero. Se
  serve più fine (es. "helper" = timeout sì, ban no), le strade sono
  due:
  - gruppi separati, es. `/mod` per timeout/warn/clear e `/modban`
    per ban/kick/softban;
  - un sistema di ruoli del bot per sotto-comando, che però non può
    cambiare la visibilità.

**Proposta** (rispetta L2 e L3; i nomi sono indicativi, versione IT
tra parentesi):

| Gruppo | Chi lo vede (menu) | Controllo a runtime | Contenuto |
|---|---|---|---|
| `/owner` | **Solo nel tuo server privato**, solo admin | `OWNER_ID` | sotto-gruppi `premium`, `blacklist`, `cog`, `system` (eval, shell, memory, stats, announce, leave-guild) |
| `/admin` | Amministratore (+ ruoli delegati in Integrazioni) | gerarchia ruoli + permessi del bot | `setup`, `wizard`, `config …`, `lingua`, `backup …`, `restore …`, `benvenuto …`, `economia …` (shop, level-roles, monthly-winners, giveaway, assegna-*) |
| `/mod` | Moderare membri (+ ruoli delegati) | gerarchia ruoli + permessi del bot | `ban`, `kick`, `warn`, `timeout`, `tempban`, `softban`, `mute`, `clear`, `lock`, `slowmode`, `caso …`, `nota …` |
| `/security` | Amministratore (+ delegati) | gerarchia + permessi del bot | sotto-gruppi `automod` (22, ci stanno), `escalation`, `antinuke`, `antiraid`, `globalban`, `verify`, `spamtrap` + `score`, `heatmap` |
| `/log` | Gestisci server (+ delegati) | — | `canale <tipo> <canale>`, `crea-canali`, `forum`, `stato`, `cerca utente/canale`, `esporta` |
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

## 12. Seconda passata — SPEC.md contro il codice reale

Ho controllato una per una tutte le voci `[x]` e `[~]` di §1–§17
(122 + 116). Circa **195 corrispondono al codice**, circa **28 non
sono davvero fatte** e circa **25** sono rotte da bug già in questo
log.

**Problema trasversale (BUG-2):** circa **55 voci `[x]` funzionanti
non si possono accendere** da nessun comando. Il wizard copre solo 6
moduli, e l'unica alternativa è un `/config import` modificato a
mano. Riguarda verify §4, gran parte di §5, anti-raid, anti-nuke,
spam-trap, heatmap, security score (§7) e i log avanzati §8.6–8.15.

**Voci segnate fatte che non lo sono** (verranno corrette in SPEC.md):

| § | Cosa dice SPEC | Com'è davvero |
|---|---|---|
| 1.2 | L'evento `modules_updated` viene emesso a ogni cambio di modulo | Lo emette solo `/setup`, che è irraggiungibile. |
| 3.3 / 8.18 | Controllo premium applicato a runtime | 6 moduli "premium" (log avanzati, spam-trap, anti-nuke, anti-raid, global-ban, heatmap) **non controllano mai il premium**. `/owner premium-toggle` su di loro non fa niente. |
| 5.7 | `/clear` con filtro "solo allegati" | Senza `message_content` gli allegati arrivano vuoti, quindi il filtro non trova quasi niente. |
| 5.10 | Ogni azione va nel mod-log | `/lock`, `/unlock`, `/slowmode` e `/clear` non creano né casi né log. |
| 7.2 | Recovery anti-nuke con nome, permessi e posizione | Ricrea solo canali **testuali** (niente vocali, categorie, forum), senza posizione né topic. Ruoli senza posizione né membri. Le prime 3 cancellazioni non vengono mai recuperate. |
| 7.3 | Log dello spam-trap con data di ingresso e di ban | Manca la data del ban. La data di ingresso è quasi sempre assente, perché viene letta dopo il ban. |
| 9.2 / 9.3 | Un bot musicale per canale vocale, code indipendenti | È **uno per server**: un secondo canale nello stesso server condivide lo stesso bot e la stessa coda. |
| 10.9 | Messaggi personalizzabili anche per Twitch e YouTube | Solo RSS e webhook accettano un template. |
| 11.1 / 11.2 | Il Creator esce sempre; coda serializzata, un job alla volta | I job scaduti o falliti lasciano il server creato (BUG-4). La coda avvia più job insieme. |
| 11.3 | Ruoli clonati nell'ordine giusto | Le posizioni non vengono mai impostate: probabilmente la gerarchia esce **invertita** (DA VERIFICARE LIVE). |
| 11.5–11.7 | Clonazione di emoji, sticker e soundboard | Nessun controllo sui limiti di un server senza boost: il primo errore fa fallire tutto il backup. |
| 11.10 / 11.11 / 11.13 | Snapshot, restore e promozione del backup | Senza dati per BUG-3. La modalità "OAuth alla verifica" non fa niente di diverso dalle altre. |
| 13.8 / 13.10 | Chiusura del ticket, trascrizione | Chiusura rotta (BUG-1), trascrizione vuota (BUG-5). |
| 15.14 | Clan: storico movimenti in `/clan info`; lo scioglimento rimuove i ruoli | Lo storico viene scritto ma non si legge da nessuna parte. I ruoli degli altri admin del clan restano. |
| 17.4 | La blacklist blocca ogni interazione | Blocca solo i comandi slash (SEC-10). |

**Testi SPEC imprecisi, correggibili senza cambiare il codice:**
- 7.2 / 8.13: "soundboard senza evento gateway" è falso, discord.py
  2.7.1 lo ha.
- 2.1 / 2.5 / 2.6: reset ed export toccano solo `guild_config`, non
  le tabelle dei singoli moduli.
- 5.9: `/untimeout` non ha il parametro motivo.
- 8.17: "cercabile per ruolo e tempo" non esiste.
- 9.9 / 9.10: la disconnessione avviene dopo 300 secondi, non subito.
- 13.2: più di 25 categorie di ticket rompono il menu.
- 14.18: il grafico dipende dal modulo logging.
- 16.8: 97 comandi, non 96.
- 17.5: solo il bot principale esce da un server in blacklist, gli
  altri 6 bot restano.

---

## 13. Seconda passata — sicurezza aggiuntiva

- **SEC-9 🔴 Token dei webhook e codici OAuth nei log.**
  - **Dove:** `core/restore_web_server.py:134`,
    `core/custom_webhook_server.py:74`.
  - **Il problema:** i due server web usano l'access log di default,
    che scrive ogni URL per intero: `/webhook/<token>` e
    `/oauth/callback?code=…`.
  - **Esempio:** chi legge i log può scrivere in qualsiasi canale
    webhook. Nel log locale ci sono già 342 righe così (per ora
    generate dai test).
  - I file di log ruotati (`.log.1`…`.5`) **non sono in
    `.gitignore`**.
- **SEC-10 🔴 La blacklist non blocca bottoni, menu e modali (L10).**
  - **Effetto:** un utente bloccato può ancora aprire ticket,
    verificarsi, usare i role menu, partecipare ai giveaway,
    raccogliere drop e inviare richieste. Nemmeno i listener lo
    ignorano (continua a guadagnare XP).
- **SEC-11 🔴 Immagini "bomba".**
  - **Il problema:** Pillow decomprime l'immagine prima di controllarne
    la dimensione.
  - **Esempio:** un PNG da 15 MB che si espande a circa 700 MB di RAM.
    Ci arriva `/fun` oppure chiunque posti un'immagine nel canale
    trappola. Poche in parallelo e crolla **tutto il processo**,
    compresi tutti i bot.
- **SEC-12 🔴 I DM al bot si possono usare per sovraccaricarlo.**
  - **Il problema:** ogni DM, di chiunque, fa **una query per ogni
    server** in cui c'è il bot, per cercare un appello dello
    spam-trap (`spam_trap.py:713`).
  - **Esempio:** con 2.000 server sono 2.000 query per ogni DM.
    Inoltre riconosce come appello anche i ban normali, non solo
    quelli dello spam-trap.
- **SEC-13 🟠 `/owner eval`, `/owner shell` e `/owner cog load` danno
  accesso completo alla macchina.**
  - **Il problema:** vedono tutti i token dei bot, il database e la
    chiave che decifra i token OAuth degli utenti.
  - **Esempio:** se qualcuno compromette il tuo account Discord,
    compromette anche il server.
  - **Proposta:** interruttore `ENABLE_EVAL`, spento di default in
    produzione, più 2FA obbligatoria sul tuo account.
- **SEC-14 🟠 Server web sempre esposti.**
  - Ascoltano su `0.0.0.0` in HTTP semplice.
  - Quello dei webhook parte **anche se la funzione non è usata**.
  - Nessun limite di frequenza per token.
  - Quello del restore parte anche senza chiave di cifratura: l'utente
    autorizza e poi riceve un errore.
- **SEC-15 🟠 Dipendenze.**
  - `aiohttp` (che fa girare due server pubblici) **non è dichiarato**
    in `requirements.txt`: arriva di rimbalzo da discord.py, con un
    limite di versione che consente versioni con vulnerabilità note.
  - Tutte le dipendenze sono `>=` senza lockfile.
  - `structlog` è dichiarato ma inutilizzato.
  - Le versioni installate oggi sono tutte aggiornate.
- **SEC-16 🟡 Segreti e dati sensibili.**
  - Nella storia git (2 commit su `.env.example`) c'è una password
    Postgres locale, poi sostituita: se era reale, va cambiata.
  - `config` e i token OAuth hanno un `repr` che stampa i segreti:
    oggi nessun log lo usa, ma basta un `logger.info(config)`.
  - La cifratura dei token non lega il dato alla riga
    (guild/utente).
  - Una sola riga corrotta blocca tutto l'elenco.
  - I token dei webhook sono salvati in chiaro.

**Verificato pulito:**
- nessuna SQL injection (389 query, tutte parametrizzate);
- nessun token Discord nella storia git;
- nessun segreto scritto nei log applicativi;
- nessun `custom_id` falsificabile;
- nessun autocomplete che mostri dati di altri server;
- `/owner` non è raggiungibile da chi non è l'owner.

---

## 14. Seconda passata — dati e GDPR

- **GDPR-1 🔴 Nessun dato viene mai cancellato quando il bot esce da un
  server.**
  - **Il problema:** non esiste un `on_guild_remove`, e nessuna
    cancellazione è legata al server.
  - **Cosa resta per sempre:** XP, monete, casi di moderazione e
    note, trascrizioni HTML dello spam-trap, ticket, snapshot degli
    utenti e token OAuth.
  - **Proposta:** alla rimozione si segna la data di uscita; dopo un
    periodo di grazia (es. 30 giorni) un job giornaliero cancella
    tutto in una sola transazione. Se il bot rientra prima, non si
    perde niente.
- **GDPR-2 🔴 Nessun modo di cancellare i dati di un utente** (diritto
  all'oblio, art. 17) né di esportarli (art. 15).
  - **Proposta:** un servizio `forget_user(user_id)` che cancella o
    anonimizza nelle circa 20 tabelle interessate, più un comando
    owner per usarlo su richiesta.
- **GDPR-3 🟠 Circa 15 tabelle crescono senza limite**, senza nessuna
  pulizia:
  - log delle azioni AutoMod e sicurezza, tentativi di verify;
  - incidenti dello spam-trap con trascrizione HTML;
  - storico della configurazione;
  - movimenti della cassa;
  - azioni programmate già eseguite, e altre.
  - **Proposta:** un unico worker di retention con una durata per
    tabella.
- **DB-1 🟠 Schema senza versioni.**
  - **Il problema:** circa 40 migrazioni girano a ogni avvio, senza
    transazione e senza lock. Sanno solo "crea se non esiste" e
    "aggiungi colonna se non esiste".
  - **Effetto:** per cambiare un tipo di colonna, togliere `prefix`,
    aggiungere foreign key o migrare i canali dei log serve SQL a
    mano.
  - **Proposta:** una tabella `schema_migrations` con migrazioni
    numerate, ciascuna in transazione sotto lock. **Va fatto prima del
    refactor**, perché R3–R5 cambiano lo schema.
- **DB-2 🟡 Foreign key e indici.**
  - C'è **una sola** foreign key in 74 tabelle, quindi sciogliere un
    clan lascia righe orfane.
  - Due indici su `event_log` non sono usati da nessuna query:
    costano solo in scrittura sulla tabella più trafficata.
  - Mancano alcuni indici su query che girano ogni minuto.

---

## 15. Seconda passata — interazioni, listener e loop

- **LC-1 🔴 `/assegna-lobby` può addebitare due volte.**
  - **Il problema:** prima scala tutte le monete dalla cassa, poi le
    accredita una persona alla volta, senza transazione e senza
    `defer`.
  - **Esempio:** con 40 persone la risposta scade, l'admin riprova e
    paga due volte. Un errore a metà lascia la cassa svuotata ma solo
    metà delle persone pagate.
- **LC-2 🟠 38 comandi in DM restano senza risposta** e mostrano "The
  application did not respond". Si risolve con `guild_only` su tutti i
  gruppi (§6).
- **LC-3 🟠 Operazioni lente senza `defer`.** Se Discord è lento,
  l'utente vede un errore anche quando l'azione è stata fatta, e
  spesso la ripete:
  - kick, ban, tempban e softban: DM + azione, e il mod-log si perde
    se si superano i 3 secondi;
  - `/suggest`;
  - `clan invita`, `espelli`, `promuovi` e `compra-canale`;
  - il salvataggio di `/setup`.
- **LC-4 🟠 Errori nei bottoni e nei menu mai mostrati all'utente.**
  Nessuna View ha `on_error`: l'utente vede "Interazione non riuscita"
  e basta.
- **LC-5 🟠 I bottoni di appello dello spam-trap smettono di funzionare
  a ogni riavvio**, perché la View non è persistente. Lo staff non può
  più agire sugli appelli aperti.
- **LC-6 🟠 Listener.**
  - I log base vanno in errore (e ti mandano un DM di allarme) a ogni
    evento se il bot perde il permesso sul canale.
  - Il tracciamento degli inviti sbaglia attribuzione con ingressi
    simultanei, cioè proprio durante un raid.
  - `on_ready` scarica gli inviti di **tutti** i server, anche dove
    la funzione è spenta.
  - Anti-raid e benvenuto contano anche i bot aggiunti dagli admin.
  - I messaggi di sistema (boost, pin, ingressi) danno XP.
- **LC-7 🟠 Feed, Twitch e YouTube continuano a pubblicare anche con il
  modulo spento**, e YouTube continua a consumare quota.
- **LC-8 🟡 Loop periodici.**
  - Diversi worker (retention log, soundboard, XP vocale dei clan,
    decay) non isolano gli errori server per server: **un server
    problematico blocca il giro per tutti gli altri**.
  - `/security-score` pubblica in chiaro nel canale la postura di
    sicurezza del server.

**Cose verificate e a posto:** 0 doppie risposte, 0 `followup` senza
risposta, gli errori sono effimeri. 7 View persistenti su 9 vengono
registrate correttamente all'avvio; le 2 che non lo sono sono
indicate sopra.

---

## 16. Seconda passata — qualità dei test

- **Risultato:** 2054 test, 0 falliti, 0 saltati. **Coverage 71%.**
  La logica pura e i repository stanno all'80–100%; **i comandi dei
  cog al 20–45%**.
  - Meno coperti:
    - moderazione: actions 22%, softban 25%, channel_control 31%;
    - role menu 27%, spam-trap 27%, suggerimenti 31%, benvenuti 32%;
    - verify 36%, ticket 36%.
- **Perché nessun test ha visto i bug principali:**
  - BUG-1: il test dei ticket controlla solo che il comando `close`
    *esista*, non lo esegue mai.
  - BUG-2: il test di `/setup` usa 2–3 moduli finti, mai i 32 reali.
  - BUG-3: il test del backup inserisce **lui stesso** la coppia
    main→backup, nascondendo il bug.
  - BUG-6: vengono testati solo tre casi fortunati del rollback.
  - SEC-1: i test di moderazione caricano i comandi ma non li
    chiamano mai, e non controllano i permessi.
- **Altri segnali di fiducia falsa:**
  - 23 test senza nessuna asserzione;
  - 47 file di test gestiscono il database a mano, alcuni svuotano
    tabelle intere;
  - singleton condivisi tra test;
  - 18 sessioni HTTP mai chiuse durante la suite.
- **Proposta, da fare prima dei fix così ogni fix ha un test che
  fallisce prima e passa dopo:**
  1. **Oggetti finti condivisi e controllati.** Un test verifica che
     le firme corrispondano a quelle vere di discord.py; avrebbe
     trovato BUG-1 subito.
  2. **Un test di politica dei permessi sull'intero albero comandi:**
     ogni comando admin, mod o owner deve avere `default_permissions`
     e un controllo, e deve rifiutare un utente senza permessi.
  3. **Un test di invarianti:**
     - al massimo 25 opzioni in ogni menu;
     - ogni metodo di scrittura dei repository ha almeno un chiamante
       reale;
     - al massimo 100 comandi top-level (questo esiste già).
  4. **Un test che esegue ogni comando almeno una volta** con oggetti
     finti fedeli.
  5. **Igiene della suite:**
     - database solo tramite la fixture di pulizia;
     - reset dei singleton;
     - la suite fallisce se restano sessioni aperte o task con
       eccezioni non raccolte.

---

## 17. Piano proposto, a fasi

Ogni fase si chiude come sempre: test prima, suite completa due
volte, commit, push e verifica dello SHA, aggiornamento di
SPEC/PROGRESS.

| Fase | Contenuto | Perché in quest'ordine |
|---|---|---|
| **R-T — Rete di test** | Punti 1–3 di §16: oggetti finti controllati, test sui permessi, test sulle invarianti | Senza, molti fix di R0/R1 non avrebbero un test capace di fallire. È la base di tutto il resto. |
| **R0 — Sicurezza** | SEC-1…16 + `allowed_mentions` globale | Sono falle aperte oggi, indipendenti dal refactor. |
| **R1 — Bug che rompono funzioni** | BUG-1…16, LC-1…8, gestore errori, avvio dei bot isolati e spegnimento pulito | Il refactor non deve partire da funzioni rotte, altrimenti non si distingue un bug vecchio da uno nuovo. |
| **R1b — SPEC onesta** | Correggere i marcatori di §12 | Così SPEC.md torna a dire la verità prima di costruirci sopra. |
| **R2 — Infrastruttura dati** | Migrazioni versionate (DB-1), retention (GDPR-3), pulizia all'uscita da un server (GDPR-1), `forget_user` (GDPR-2) | R3–R5 cambiano lo schema, quindi serve prima un sistema di migrazioni. Il GDPR è un obbligo legale. |
| **R3 — Router dei canali** | Canali per tipo, forum, creazione automatica; migrazione delle impostazioni esistenti | Serve prima dei log nuovi, così nascono già con il sistema giusto. |
| **R4 — Message content** | Attivare l'intent; log di messaggi cancellati, cancellati in massa e modificati (§8.16); snipe ed editsnipe (§14.9/14.10); ricontrollare AutoMod, ticket, spam-trap e `/clear` | I nuovi log devono nascere già nel router. |
| **R5 — Struttura comandi** | Gruppi nuovi, `default_permissions`, `guild_only`, `/owner` solo nel server privato | È il cambiamento più grande, e va fatto una volta sola. |
| **R6 — Lingue** | Testi IT/EN, localizzazioni, COMMAND_LIST_ITA/ENG, `/cerca-comando` nuovo | Va fatto dopo R5, perché i nomi dei comandi cambiano lì. |
| **R7 — NSFW** | §16.10 come istanza separata con `NSFW_TOKEN` | Dopo R5 e R6, così nasce già con i gruppi e le lingue nuovi. |
| **Continuo** | Docstring, codice morto, duplicazioni, prestazioni (PERF-1…7), coverage dei cog | File per file, man mano che li tocchiamo. |

---

## 18. Decisioni che servono da te prima di partire

1. **Lingua dei nomi dei comandi:** opzione A (localizzazione nativa
   per client) o B (registrazione per server)? Vedi §7.
2. ~~Ruoli bot-admin e visibilità~~ → **decisa** (28/09): nascosti a
   chi non ha il permesso; delega nativa in *Integrazioni*. Resta da
   decidere la **granularità** di `/mod` (L9): un solo gruppo, oppure
   `/mod` + `/modban` separati?
3. **Forum dei log avanzati:** un post per tipo di log, o un post per
   utente o caso?
4. **Retrocompatibilità:** i vecchi nomi dei comandi spariscono
   subito con R5, oppure li teniamo per un periodo? Tenerli costa
   slot: siamo a 97 su 100, quindi possiamo tenerne pochissimi.
5. **Quota YouTube (BUG-16):** passo al metodo RSS + `videos.list`?
6. ~~GDPR-1 giorni di grazia~~ → **decisa**: 90 giorni, conservando ban e kick di sicurezza (#46).
7. **`/owner eval` e `/owner shell`:** li teniamo attivi in produzione,
   oppure li spegniamo di default con un interruttore (SEC-13)?

---

## 19. Aggiornamento dopo le issue GitHub (28/09 pomeriggio)

**Regole di test:** vale `CLAUDE_MANDATORY_TEST_RULES.md`.
- Nessun fix è "verificato live" senza bot e database reali.
- Da questo ambiente cloud Discord, Aiven e Lavalink sono bloccati
  dal proxy (verificato: risposta 403).
- I test live si fanno solo con la sessione collegata al PC
  dell'owner, e i segreti restano nel `.env` locale.
- Le issue si chiudono solo dopo lo smoke test live. Fino ad allora
  i commit le citano con "Refs #N".

**Problemi nuovi dalle issue** (non erano in questo log):
- **SEC-17 🔴 (#29) Ruoli piattaforma dei vocali temporanei senza
  controllo di gerarchia.** Se un admin configura come ruolo
  "piattaforma" un ruolo con permessi alti, chiunque crei un vocale
  può assegnarselo.
- **BUG-17 🟠 (#33) Drop riscattabile più volte.** Il controllo "già
  preso" sta in memoria e non è atomico, quindi due clic simultanei
  pagano due volte.
- **BUG-18 🟠 (#34) `/voice transfer` accetta chiunque**, anche bot o
  utenti che non sono nel canale.

**Decisioni prese nelle issue:**
- **Retention (#46):** i dati si conservano per **90 giorni**
  dall'uscita dal server, poi vengono cancellati. Le righe di chi è
  stato bannato o kickato per spam, nuke o raid restano
  (`retain_for_security`), perché servono come storico di
  affidabilità se l'utente rientra.
  - La cancellazione anticipata avviene solo su richiesta, tramite
    comando o form. Se l'utente ha un ban o kick di sicurezza la
    richiesta viene rifiutata con una spiegazione.
- **`/setup` (#49):** diviso **per categoria**, con un campo
  `category` su ogni modulo. Diventa un sotto-gruppo di `/admin`
  quando si applica la struttura di R5.
- **`message_content` (#36):** si attiva, con motivazione per la
  verifica di Discord e un log all'avvio che mostra gli intent
  effettivi.
- **`PREMIUM_ALPHA_UNLOCK_ALL` (#41):** in produzione il default
  diventa falso, con un avviso nel log all'avvio.
- **Musica (#45, #47, #48):**
  - la radio parte da sola quando il bot principale entra in un
    canale vocale;
  - la cartella dei file locali viene creata se non esiste;
  - aggiungiamo in `deploy/lavalink/` il `docker-compose.yml` e
    l'`application.yml` per il self-host, più una guida con i link
    ufficiali (lavalink.dev, youtube-source, LavaSrc).
- **Fuori scope per ora:** l'AI (#50) e il confronto con gli altri bot
  (#52) sono debito di prodotto, non bug.

**Corrispondenza issue → codici di questo log:**

| Issue | Codice | Issue | Codice |
|---|---|---|---|
| 2, 42 | BUG-1 | 3, 40 | SEC-1 |
| 4, 38, 43, 49 | BUG-2 | 5 | SEC-7 |
| 6, 36, 39, 44 | BUG-5 / L7 | 7 | SEC-5, BUG-10 |
| 8 | SEC-3 | 9 | SEC-8 |
| 10, 14, 32 | SEC-4 | 11 | SEC-8b |
| 12, 28 | BUG-7 | 13 | BUG-8 |
| 15 | SEC-2 | 16 | LC-5 |
| 17 | SEC-6 | 18 | LC-1 |
| 19, 37, 46 | GDPR-1/2/3 | 20 | SEC-10 |
| 21 | BUG-4 | 22 | LC-4 |
| 23, 35 | BUG-14 | 24, 31 | LC-2 |
| 25 | DB-1 | 26 | BUG-3 |
| 27 | LC-6 | 29 | SEC-17 |
| 30 | §12 (7.2) | 33 | BUG-17 |
| 34 | BUG-18 | 41 | §11 (valori pericolosi) |
| 45, 47, 48 | BUG-9/10, §12 (9.x) | 50, 52 | fuori scope |
