# CONFRONTO_BOT.md — iYokai a confronto con i grandi bot Discord

Dati raccolti il **4 ottobre 2026**. È il documento dell'issue #52
("confronto con altri bot").

**Aggiornato la sera del 04/10**, dopo la fase R1-bis e i tre controlli
sui limiti. Da oggi le proposte di questo confronto **sono nel piano**:
- cosa aggiungere: [`../02-piano/NUOVE_FUNZIONI.md`](../02-piano/NUOVE_FUNZIONI.md);
- cosa migliorare: [`../02-piano/MODIFICHE_ESISTENTE.md`](../02-piano/MODIFICHE_ESISTENTE.md);
- in che ordine: [`../02-piano/PRIORITA.md`](../02-piano/PRIORITA.md).

I file citati qui sotto si trovano ora in: `revisione/01-analisi/`
(`REVIEW.md`, `LIMITI.md`), `revisione/02-piano/` (`PIANO_FIX.md`,
storico) e nella cartella principale (`SPEC.md`, `BACKLOG.md`).

Come leggerlo:
- **Fonte ufficiale** = sito, documentazione o pagina aiuto del bot.
- **(terzi)** = l'informazione viene da un sito esterno, non dal bot.
- **Non verificato** = non ho trovato una fonte ufficiale leggibile.
- I codici tra parentesi quadre, es. `[CARL]`, rimandano al §9 Fonti.

---

## 1. In sintesi

1. **Il backup di iYokai oggi non può funzionare.** Discord ha tolto ai
   bot la possibilità di creare server. Nella documentazione ufficiale
   l'endpoint "Create Guild" non c'è più `[DISCORD]`. Il design
   "il Creator crea un server nuovo" va rifatto sul modello di Xenon:
   il backup è un **salvataggio di dati**, e si ricarica su un server
   che l'admin ha creato a mano `[XENON]`. **Confermato** anche dalla
   libreria: discord.py 2.6 segna deprecati `create_guild` e
   `Guild.delete`. La scelta è presa: decisione **D8**, fase F3. I bug
   BUG-26, 28 e 29 sul vecchio flusso sono superati da D8.
2. **Manca il pannello web, e tutti i grandi ce l'hanno.** MEE6, Dyno,
   Carl-bot, ProBot, Arcane, Maki, Sapphire, Wick e Ticket Tool si
   configurano da sito. iYokai ha 252 comandi slash. È il divario più
   grande, e anche il più costoso da chiudere.
3. **iYokai ha tante funzioni, ma poche "finite".** `REVIEW.md` dice che
   circa 28 voci segnate fatte non lo sono e circa 25 sono rotte. Il
   bot è in zero server e niente è stato provato su Discord vero. Il
   confronto va letto così: i concorrenti funzionano oggi, iYokai no.
   Il 04/10 è stata chiusa la fase R1-bis (2614 test verdi) e `SPEC.md`
   è stata riallineata allo stato reale.
4. **MEE6 ha messo quasi tutto a pagamento.** Secondo la sua tabella
   ufficiale (aggiornata il 16/06/2026) nel piano gratuito restano solo
   ricerca, achievement, starboard e 1 promemoria. Moderazione,
   benvenuto, livelli, reaction roles e alert sono Premium `[MEE6]`.
   **È l'occasione migliore per iYokai**: un piano gratuito generoso.
5. **Le idee "uniche" di iYokai sono vere, ma meno uniche di quanto
   sembri.** Il canale trappola esiste già in Carl-bot (honeypot
   nell'automod) `[CARL]`. Il blocco raid globale lo fa Beemo, gratis
   `[BEEMO]`. Le flotte musicali le fa Jockie (4 bot gratis, 27 con
   premium) `[JOCKIE]`. La differenza reale di iYokai è **averle tutte
   insieme**, più appello dopo il ban, clan e radio propria.
6. **Le tre cose davvero diverse:** economia dei **clan** con canali
   veri comprati dalla tesoreria (non l'ho trovata in nessun
   concorrente), **backup + ritorno dei membri nello stesso bot**
   (Xenon non riporta i membri, RestoreCord sì ma fa creare all'utente
   un bot proprio `[XENON]`), **italiano come prima lingua** (ProBot e
   Lawliet non hanno l'italiano tra le lingue dichiarate).
7. **Musica: YouTube è un rischio concreto.** YouTube ha fatto chiudere
   Groovy e Rythm nel 2021 `[MUSICA]`. Jockie non elenca YouTube tra le
   sue sorgenti `[JOCKIE]`. Hydra ha smesso di vendere funzioni musicali
   il 7/02/2023 `[HYDRA]`. iYokai oggi cerca su YouTube di default. La
   radio con brani tuoi è la parte più sicura e più originale.
   **Confermato leggendo il codice:** i 5 bot musicali usano la
   sessione Lavalink del bot principale, quindi quasi certamente non
   producono audio (`LIM-40`). Si corregge con D10, fase F2.
8. **Mancano pezzi che gli utenti danno per scontati:** ruolo automatico
   all'ingresso, starboard, comandi personalizzati, risposte
   automatiche, immagine di benvenuto, rank card, log dei messaggi
   cancellati, moduli nei ticket, contatori, compleanni.
9. **Prima dei 100 server servono le carte in regola.** Discord chiede
   la verifica dell'app per superare i 100 server, con privacy policy,
   identità verificata e 2FA `[DISCORD]`. Chiede anche un modo facile
   per far cancellare i dati agli utenti. iYokai oggi non ha nessuna
   delle due cose (GDPR-1/2 in `REVIEW.md`). Gli **intent privilegiati**
   seguono un'altra regola: approvazione da 10.000 utenti, da rifare
   ogni anno (changelog del 10/06/2026, decisione D11).
10. **Nighty non è un concorrente da imitare.** È un self-bot: gira su
    un account utente, e Discord lo vieta `[NIGHTY]` `[DISCORD]`. Solo
    poche sue idee si possono rifare in modo lecito (vedi §7).

---

## 2. Come ho confrontato

### 2.1 Bot guardati

| Area | Bot |
|---|---|
| Tutto-in-uno | MEE6, Dyno, Carl-bot, ProBot, YAGPDB, Arcane, Maki, Sapphire, Atlas, Lawliet, Circle, Yggdrasil |
| Sicurezza | Wick, Beemo, Double Counter, Captcha.bot |
| Ticket | Ticket Tool, Tickets (tickets.bot), ModMail |
| Backup e restore | Xenon, RestoreCord |
| Musica | Jockie Music, Hydra, Maki, Rythm |
| Economia | Tatsu, UnbelievaBoat, Dank Memer |
| Statistiche | Statbot, ServerStats |
| Giveaway | Giveaway Boat, GiveawayBot |
| Alert social | Streamcord, Pingcord |
| Moderazione avanzata | Zeppelin |
| Non-bot | Nighty (self-bot) |

"Yggdrasil" e "YAGPDB" sono **due bot diversi**. Yggdrasil è un bot di
giochi e scherzi, oggi "in riscrittura" secondo il suo sito `[YGG]`.
YAGPDB è un bot serio, open source, famoso per i comandi personalizzati
`[YAGPDB]`. Li ho coperti tutti e due.

### 2.2 Cosa vuol dire "iYokai oggi"

Non ho usato `SPEC.md` da solo, perché sovrastima. Ho usato:
- `REVIEW.md` §0, §3, §4, §12, §19, §20 (cosa funziona davvero);
- `PIANO_FIX.md` (cosa è già stato corretto e cosa no);
- `COMMAND_LIST.md` e la cartella `cogs/` (cosa esiste).

Stato del piano la sera del 4/10: fatte R-T, R0, DB, metà di R1 e
tutta R1-bis (tranne BUG-26/28/29, superati da D8, e BUG-34, da
confermare). `message_content` è acceso nel codice (commit `783329e`):
l'owner deve solo attivarlo nel Developer Portal. Il resto è ordinato
in `PRIORITA.md` (fasi F1–F14).

Legenda della colonna "iYokai oggi":
- ✅ il codice c'è e non ha bug aperti noti;
- 🟡 c'è, ma è incompleto o ha bug aperti;
- ❌ manca.

**Attenzione:** nessun ✅ è stato provato su Discord. Il bot è in zero
server. ✅ vuol dire "funziona nei test offline".

### 2.3 Avvertenze

- **Nighty** è un self-bot, cioè automatizza un account utente. Discord
  scrive che è vietato e può portare alla chiusura dell'account
  `[DISCORD]`. Non propongo nessuna tecnica da self-bot.
- **RestoreCord**: il suo sito ha rifiutato la lettura (errore 403).
  Quello che scrivo viene dalla pagina di confronto di Xenon, che è un
  **concorrente**, e da Trustpilot. È tutto **(terzi)**.
- **Restore dei membri**: usa il permesso OAuth `guilds.join`. Funziona
  solo per chi ha dato il consenso *prima* del problema. Dettagli e
  vincoli al §5 e al §7.
- **Musica**: vedi §3.9 per la situazione YouTube.
- **Prezzi**: molti siti mostrano i prezzi solo con JavaScript e non
  sono leggibili da qui. Quando il prezzo viene da un sito esterno lo
  segno **(terzi)**. Diverse fonti esterne sono blog di PeakBot, che è
  un concorrente: vanno prese con cautela.
- **Numero di server**: preso dal sito del bot o dalla sua scheda su
  top.gg. Sono numeri dichiarati, non controllati da me.

### 2.4 Regole di Discord che contano per questo confronto

| Regola | Cosa dice | Fonte |
|---|---|---|
| Creare server | L'endpoint "Create Guild" e "Create Guild from Template" non sono più nella documentazione. discord.js e discord.py (dalla 2.6) li segnano deprecati. La data "luglio 2025" viene da un sito esterno e dal coordinatore del lavoro: il changelog ufficiale oggi mostra solo voci da agosto 2025 in poi. | `[DISCORD]` |
| Self-bot | "Automatizzare account utente normali... è vietato". | `[DISCORD]` |
| Verifica app | Serve per superare i 100 server. Chiede privacy policy, identità (via Stripe), 2FA. | `[DISCORD]` |
| Intent privilegiati | `message_content`, membri e presenze. Dal 10/06/2026: sotto i 10.000 utenti si accendono da soli; da 10.000 in su serve la domanda, da rifare ogni anno. `REVIEW.md` (L7) dice "sopra i 100 server": è superato (D11). | `[DISCORD]` |
| Dati utente | Privacy policy obbligatoria. Modo facile per chiedere la cancellazione. Dati cifrati a riposo. | `[DISCORD]` |
| Permesso dell'utente | "Non avviare processi per conto di un utente senza il suo permesso". "Non contattare gli utenti senza permesso esplicito". | `[DISCORD]` |
| AI | Vietato usare il contenuto dei messaggi per addestrare modelli AI. | `[DISCORD]` |
| Vendita | Per vendere dentro Discord l'app deve essere verificata. Vietato monetizzare il gioco d'azzardo. | `[DISCORD]` |
| Emoji e sticker | Dal 23/02/2026 per crearli serve il permesso nuovo `CREATE_GUILD_EXPRESSIONS`. Riguarda il backup. | `[DISCORD]` |
| `guilds.join` | Il bot deve già essere nel server. I token scadono e vanno rinnovati. | `[DISCORD]` |

---

## 3. Tabella per area

### 3.1 Moderazione

| Funzione | Chi la fa meglio e come | iYokai oggi | Nota |
|---|---|---|---|
| Ban, kick, timeout, warn, tempban, softban | Dyno e Carl-bot: comandi più pannello web, registro dei casi `[DYNO]` `[CARL]` | 🟡 | I comandi ci sono tutti. Ma oggi **chiunque** può usarli (SEC-1). Si chiude in R5. |
| Casi numerati e note | Carl-bot: caso con ID, motivo, storico per utente, classifica dei moderatori `[CARL]`. Zeppelin: casi come cuore del bot `[ZEPPELIN]` | ✅ | `/modcase`, `/modnote`. Il caso nasce prima dell'azione: se fallisce resta orfano. |
| Soglie sui warn | Carl-bot: superato un numero di warn scatta una punizione automatica `[CARL]` | 🟡 | La scala (`/escalation`) vale solo per l'AutoMod, non per i warn manuali. |
| Lock, slowmode, clear | Zeppelin: slowmode adattivo `[ZEPPELIN]` | 🟡 | Funzionano ma non lasciano traccia nel log. |
| Segnalazioni utenti | — | ✅ | `/report`. |
| Blocco totale del server | Wick: lockdown di canali, ruoli, ingressi e inviti `[WICK]` | ❌ | Solo `/lock` su un canale. |
| Appello dopo un ban | Circle: "Ban Appeals" tra le funzioni principali `[CIRCLE]` | 🟡 | Solo per i ban dello spam-trap. |

### 3.2 AutoMod

| Funzione | Chi la fa meglio e come | iYokai oggi | Nota |
|---|---|---|---|
| Parole vietate, inviti | Arcane e iYokai usano l'AutoMod nativo di Discord `[ARCANE]` | ✅ | La sincronizzazione cancella le regole aggiunte a mano (aperto in R1). |
| Link, maiuscole, emoji, zalgo, allegati | Carl-bot: spam, allegati, menzioni, link, inviti, parole, maiuscole `[CARL]` | 🟡 | Scritti. L'intent `message_content` è acceso nel codice dal 04/10: va attivato nel Portal e i filtri vanno riprovati (BUG-5). |
| Punizioni | Carl-bot: cancella, warn, mute, timeout, kick, ban, messaggio in canale o in DM `[CARL]` | ✅ | delete, warn, mute, ban combinabili. |
| "Calore" che sale e scende | Wick: sistema "Heat", si adatta al comportamento e cala col tempo `[WICK]` | 🟡 | La scala di escalation fa una cosa simile ma più semplice. I conteggi oggi sono gonfiati. |
| Decisione lasciata ai mod | Carl-bot: "drama channel", i mod decidono con una reazione (Premium) `[CARL]` | ❌ | |
| Canali solo media | Carl-bot `[CARL]` | ❌ | |
| Pulizia automatica dei canali | Carl-bot: auto-purge fino a 15 canali (Premium) `[CARL]` | ❌ | |
| Link di phishing | Captcha.bot: anti-phishing `[CAPTCHA]` | ❌ | |
| Numero di regole | YAGPDB: 25 gratis, 150 premium `[YAGPDB]` | ✅ | Nessun limite scritto. |

### 3.3 Sicurezza: anti-raid e anti-nuke

| Funzione | Chi la fa meglio e come | iYokai oggi | Nota |
|---|---|---|---|
| Anti-nuke | Wick: due limiti, al minuto e all'ora. Chi li supera va in quarantena `[WICK]` | 🟡 | Può punire il bot stesso (BUG-11). La punizione di default non funziona sui bot. |
| Quarantena | Wick: ruolo sotto quello del bot, l'utente non vede niente fino al controllo `[WICK]` | 🟡 | Il ruolo c'è. Ingressi simultanei ne creano più di uno. |
| Recupero dopo un attacco | Wick Premium: copia del server ogni 3 ore, usata dal "panic mode" `[WICK]` | 🟡 | Ricrea solo canali testuali, senza posizione. |
| Anti-raid sugli ingressi | Wick Premium: scatta con 10 account in 10 minuti (default) `[WICK]`. Beemo: gratis, automatico, 100.000+ server `[BEEMO]` | 🟡 | Scatta anche per **un solo** ingresso senza avatar (BUG-12). |
| Filtri all'ingresso | Wick "Join Gate": 7 filtri (avatar, età, bot non autorizzati, nomi pubblicitari…) `[WICK]` | 🟡 | Età, nome, avatar. Niente filtro su chi aggiunge bot. |
| Canale trappola | Carl-bot: honeypot nell'automod `[CARL]` | 🟡 | Più ricco di Carl (appello, pulizia, transcript). Contenuto da riprovare con l'intent acceso. I bottoni di appello muoiono a ogni riavvio (LC-5). |
| Ban condiviso tra server | Beemo: riconosce i raid da solo su tutti i server `[BEEMO]`. Double Counter: confronto tra database `[DC]` | 🟡 | Solo per i ban della trappola. Oggi salta il controllo premium. |
| Controllo dei permessi | Wick: pagina che mostra i problemi di sicurezza del server `[WICK]` | ✅ | `/security-score`, `/permission-heatmap`. |
| Chiave di soccorso | Wick: "rescue key" se perdi l'account owner `[WICK]` | ❌ | |
| Livelli di fiducia | Wick: "extra owner" e "trusted admin" `[WICK]` | 🟡 | Una sola lista di fidati. |

### 3.4 Verifica

| Funzione | Chi la fa meglio e come | iYokai oggi | Nota |
|---|---|---|---|
| Bottone di verifica | Wick: modalità "None", un clic e basta `[WICK]` | ✅ | Manca il `defer`: può scadere sotto carico. |
| Captcha | Wick: captcha proprio; misura, colori e lunghezza regolabili con il premium `[WICK]`. Captcha.bot: 533.000 server `[CAPTCHA]` | 🟡 | Solo una somma scritta. Un bot la risolve facilmente. |
| Verifica su pagina web | Wick "Web". Double Counter: link, esito in circa 3 secondi `[DC]` | ❌ | Prevista con il Web Panel (§4.2 SPEC). |
| Account doppi (alt) | Double Counter: IP, cookie, impronta; 600.000+ server `[DC]` | ❌ | Previsto, mai iniziato. |
| Blocco VPN | Double Counter: VPN, proxy, Tor `[DC]` | ❌ | |
| Tempo massimo | Captcha.bot: kick o ban a chi non si verifica in tempo `[CAPTCHA]` | ❌ | |
| Privacy della verifica | Double Counter: dati tenuti 24 mesi, comando `/privacy` `[DC]` | ❌ | Nessuna privacy policy ancora. |

### 3.5 Log

| Funzione | Chi la fa meglio e come | iYokai oggi | Nota |
|---|---|---|---|
| Ingressi, uscite, ban, ruoli, canali | Tutti | ✅ | |
| Messaggi cancellati e modificati | Carl-bot e Dyno `[CARL]` `[DYNO]` | ❌ | In piano (R4). |
| Log divisi per tipo | Carl-bot: 5 categorie, un canale ciascuna. `log aio` crea categoria e 5 canali da solo `[CARL]` | ❌ | Un solo canale per tutto. In piano (R3). |
| Ignora canali, utenti, prefissi | Carl-bot `[CARL]` | ❌ | |
| Voce, webhook, emoji, thread | Carl-bot: eventi vocali `[CARL]` | ✅ | iYokai copre anche soundboard e inviti usati. |
| Ricerca nello storico | Nessuno trovato con ricerca via comando | ✅ | `/logs user`, `/logs channel`, `/logs export`. Punto forte. |
| Conservazione | Arcane e YAGPDB dichiarano 1 ora gratis e 12 ore premium (sembra la memoria dei messaggi per i log di cancellazione) `[ARCANE]` `[YAGPDB]` | ✅ | Storico eventi: 30 giorni gratis, 180 premium. Non è la stessa cosa: confronto solo indicativo. |

### 3.6 Ticket

| Funzione | Chi la fa meglio e come | iYokai oggi | Nota |
|---|---|---|---|
| Pannello con bottone | Ticket Tool: 5,8 milioni di server `[TT]` | ✅ | |
| Più pannelli in uno | Ticket Tool: fino a 25 in un solo messaggio `[TT]`. Tickets: bottoni o menu `[TICKETS]` | 🟡 | Menu a tendina. Si rompe oltre 25 categorie (`LIM-6`). |
| Modulo prima di aprire | Ticket Tool: fino a 5 domande in un modal `[TT]`. Tickets: moduli con campi dinamici `[TICKETS]` | ❌ | |
| Transcript | Ticket Tool: HTML, fino a 1.000 messaggi, anche su Google Drive `[TT]` | 🟡 | C'è. Usciva vuoto senza l'intent (BUG-5): da riprovare ora che è acceso. |
| Presa in carico | Ticket Tool: rinomina, sposta di categoria, cambia permessi (Premium) `[TT]` | 🟡 | `/ticket claim` semplice, senza controllo staff. |
| Chiusura automatica | Tickets: per inattività, per nessuna risposta, se l'utente esce (Premium) `[TICKETS]` | ❌ | |
| Voto a fine ticket | Tickets: stelle più questionario `[TICKETS]` | ❌ | |
| Ticket come thread | Tickets: "thread mode" `[TICKETS]` | ❌ | |
| Orari di apertura | Ticket Tool (Premium) `[TT]` | ❌ | |
| Ticket via DM | ModMail: scrivi al bot, nasce un canale per lo staff `[MODMAIL]` | ❌ | |
| Statistiche | Tickets (Premium) `[TICKETS]` | ✅ | `/ticket-stats`. |
| Chiusura | — | ✅ | BUG-1 e BUG-30 corretti (da provare live). |

### 3.7 Benvenuto e ruoli

| Funzione | Chi la fa meglio e come | iYokai oggi | Nota |
|---|---|---|---|
| Messaggio di benvenuto | Tutti | ✅ | Testo con segnaposto, DM facoltativo. |
| Immagine di benvenuto | ProBot: sfondo caricabile, avatar tondo o quadrato con coordinate, testo con posizione e colore `[PROBOT]` | ❌ | Pillow è già nel progetto. |
| Ruolo automatico all'ingresso | Carl-bot, Arcane (1 gratis, 10 premium) `[CARL]` `[ARCANE]` | ❌ | **Mancanza grossa**: è una funzione di base. |
| Ruoli ridati a chi rientra | Carl-bot: entro 30 giorni `[CARL]` | ❌ | |
| Ruoli a tempo | Carl-bot: ruolo dato dopo un ritardo `[CARL]` | ❌ | |
| Reaction, bottoni, menu | MEE6: emoji, bottoni, menu `[MEE6]` | 🟡 | Tutti e tre. L'opzione `toggle=False` è ignorata. |
| Modalità dei reaction roles | Carl-bot: unique, verify, drop, reversed, binding, temp, lock, più limiti e liste `[CARL]` | 🟡 | Solo "normale" e "max selezionabili". |
| Quanti ruoli | Carl-bot: 250 per messaggio, 1.000 premium `[CARL]`. Arcane: 10 gratis `[ARCANE]`. MEE6: 0 gratis, 40 premium `[MEE6]` | ✅ | Nessun limite scritto. |
| Messaggio per i boost | — | ✅ | |

### 3.8 Livelli ed economia

| Funzione | Chi la fa meglio e come | iYokai oggi | Nota |
|---|---|---|---|
| XP da testo | MEE6: 15–25 XP a messaggio, pausa di 1 minuto `[MEE6]` | ✅ | |
| XP da voce | ProBot: livelli testo e voce separati `[PROBOT]`. Arcane: solo premium `[ARCANE]` | ✅ | Gratis in iYokai. Anti-farm incluso. |
| Rank card (immagine) | MEE6: colori gratis, sfondo personalizzato premium `[MEE6]`. Carl-bot: sfondo, colori, opacità `[CARL]` | ❌ | `/rank` è un riquadro di testo. |
| Ruoli premio | MEE6: "accumula" o "togli i precedenti" `[MEE6]`. Arcane: 15 gratis `[ARCANE]`. Maki: 25 gratis `[MAKI]` | 🟡 | Solo accumulo. Nessun limite. |
| Dove annunciare il level-up | MEE6: spento, canale corrente, DM, canale scelto `[MEE6]` | 🟡 | Sempre nel canale corrente. |
| Canali e ruoli senza XP | MEE6, ProBot `[MEE6]` `[PROBOT]` | ❌ | |
| Moltiplicatori di XP | Maki: per canale e per ruolo `[MAKI]` | ❌ | |
| Classifica | MEE6: pagina web `[MEE6]` | ✅ | Mensile e totale. |
| Monete: daily, work, pay | UnbelievaBoat: 2,6 milioni di server, economia per server `[UNB]` | 🟡 | Riscuotibili due volte (BUG-14). |
| Negozio | UnbelievaBoat: 25 oggetti gratis, illimitati premium `[UNB]` | 🟡 | Può togliere monete senza dare il ruolo. |
| Giochi (blackjack, roulette) | UnbelievaBoat, Dank Memer `[UNB]` `[DANK]` | ❌ | Vedi §7. |
| Animali, case, profili | Tatsu: 100+ animali, 1.000+ mobili `[TATSU]` | ❌ | |
| Clan con tesoreria e canali | Nessuno trovato | 🟡 | Punto unico. Bug aperti (BUG-15). |
| Cassa del server | Nessuno trovato | 🟡 | `/assegna-lobby` può addebitare due volte (LC-1). |

### 3.9 Musica

| Funzione | Chi la fa meglio e come | iYokai oggi | Nota |
|---|---|---|---|
| Più bot nello stesso server | Jockie: 4 bot gratis che "agiscono come uno", 27 con premium `[JOCKIE]` | 🟡 | 5 worker. Ma oggi è **uno per server**, non per canale (REVIEW §12), e i worker quasi certamente non suonano (`LIM-40`). Si corregge con D10. |
| Sorgenti | Jockie: Spotify, Deezer, Tidal, Apple Music, radio, Bandcamp. **YouTube non è in elenco** `[JOCKIE]`. Maki: "YouTube e altro" `[MAKI]` | 🟡 | YouTube di default. Spotify solo se il nodo ha il plugin. |
| Canale richieste con player | Hydra (storico): `.setup` creava un canale dedicato con coda e controlli (terzi, 2023) `[HYDRA]` | ❌ | Vedi §6. |
| Radio 24/7 | Jockie: 37.000+ stazioni radio `[JOCKIE]` | 🟡 | Radio condivisa con brani dell'owner. I file locali non si trovano (BUG-10). |
| Playlist salvate | Jockie: raccolte con codice da condividere `[JOCKIE]` | ❌ | |
| Filtri audio, DJ, voto per saltare | Maki: filtri `[MAKI]` | ❌ | **Scartati dall'owner.** Non vanno proposti. |
| Comandi di base | Jockie: 150+ comandi `[JOCKIE]` | ✅ | 23 comandi. Scelta voluta. |

**Situazione YouTube.** Groovy ha chiuso il 30/08/2021 e Rythm il
15/09/2021, dopo una diffida di YouTube per violazione dei termini
`[MUSICA]`. Il sito di Hydra oggi parla solo di livelli, benvenuto e
ruoli, e dice che dal 7/02/2023 non vende più funzioni musicali
`[HYDRA]`. Rythm è tornato come bot, attività Discord e app; se la
musica sia in licenza non l'ho potuto verificare `[MUSICA]`.

### 3.10 Vocali temporanei

| Funzione | Chi la fa meglio e come | iYokai oggi | Nota |
|---|---|---|---|
| Canale generatore | MEE6: 100 canali, solo premium `[MEE6]` | ✅ | Gratis. |
| Pannello con bottoni | — | ✅ | |
| Rinomina, limite, blocca, espelli, cedi | Maki, Lawliet: canali automatici `[MAKI]` `[LAWLIET]` | 🟡 | `/voice transfer` accetta chiunque (BUG-18). Restano canali orfani dopo un riavvio. |
| Ruoli piattaforma (PC, console) | Nessuno trovato | ✅ | Idea adatta a una community di gioco. |

### 3.11 Utility

| Funzione | Chi la fa meglio e come | iYokai oggi | Nota |
|---|---|---|---|
| Sondaggi | MEE6 (premium) `[MEE6]` | ✅ | Usa i sondaggi nativi. Massimo 5 opzioni. |
| Promemoria | MEE6: 1 gratis, 100 premium `[MEE6]` | ✅ | |
| Giveaway | Giveaway Boat: modelli, programmazione, requisiti (livello, messaggi, ruolo), più ingressi, ruoli che saltano i requisiti `[GBOAT]` | 🟡 | Requisiti di ruolo e livello. In thread e forum non avvisa i vincitori. |
| Suggerimenti | Carl-bot `[CARL]` | ✅ | |
| Starboard | MEE6 (gratis), Carl-bot, Dyno, Zeppelin, Circle `[MEE6]` `[CARL]` | ❌ | |
| Comandi personalizzati | YAGPDB: 100 gratis, 500 premium, 14 tipi di innesco `[YAGPDB]`. Carl-bot: "tag" con TagScript `[CARL]` | ❌ | Solo una richiesta all'owner. |
| Risposte automatiche | Carl-bot: "trigger", 50 gratis, 75 premium `[CARL]` | ❌ | Serve `message_content`. |
| Costruttore di embed | ProBot, Atlas, Hydra ("message builder") `[PROBOT]` `[ATLAS]` `[HYDRA]` | ❌ | |
| Messaggi programmati | Maki: 3 gratis, 100 premium `[MAKI]` | ✅ | I ping di ruolo oggi sono muti. |
| Messaggi fissi (sticky) | Maki: 3 gratis `[MAKI]` | 🟡 | Messaggi persi o doppi. |
| Compleanni | MEE6, Maki, Lawliet `[MEE6]` `[LAWLIET]` | ❌ | |
| Inviti: chi ha invitato chi | MEE6, Maki, Lawliet ("invite tracker") `[MEE6]` `[MAKI]` `[LAWLIET]` | 🟡 | Tracciato nei log. Nessun comando né classifica per gli utenti. |
| Moduli e candidature | Dyno ("form builder"), Circle `[DYNO]` `[CIRCLE]` | ❌ | |
| Ricerca dei comandi | — | 🟡 | `/search` dà risultati sbagliati. Rifatto in R6. |
| Storico e annulla configurazione | Nessuno trovato | ✅ | `/config history`, `rollback`, `export`, `import`. |

### 3.12 Alert social

| Funzione | Chi la fa meglio e come | iYokai oggi | Nota |
|---|---|---|---|
| Twitch | Streamcord: 1,2 milioni di server, ruolo "in diretta", 5 streamer gratis `[STREAMCORD]` | 🟡 | Controllo ogni 90 secondi. Si rompe oltre 100 iscrizioni (`LIM-46`). |
| YouTube video | Arcane: 2 gratis, 51 premium `[ARCANE]`. YAGPDB: 10 gratis `[YAGPDB]` | ✅ | Via feed. |
| YouTube live | Arcane: video, short e live `[ARCANE]` | 🟡 | Finisce la quota in poche ore (BUG-16, `LIM-45`). Soluzione decisa: D5. |
| Reddit, RSS | YAGPDB: Reddit 20 gratis, RSS 2 gratis `[YAGPDB]` | ✅ | BUG-20 corretto il 04/10. Manca un tetto di feed per server (`LIM-16`). |
| TikTok, Instagram, X | Pingcord: ci sono; Instagram e X solo premium `[PINGCORD]`. MEE6: premium `[MEE6]` | ❌ | Nessuna API gratuita. Alternativa in piano: feed RSS "ponte" e webhook in ingresso, più chiave API a pagamento facoltativa (vedi `NUOVE_FUNZIONI.md`). |
| Kick | Streamcord, Pingcord, MEE6 `[STREAMCORD]` `[PINGCORD]` | ❌ | |
| Velocità | Pingcord: da istantaneo a 2 minuti `[PINGCORD]` | 🟡 | Feed ogni 5 minuti. |
| Ruolo a chi è in diretta | Streamcord `[STREAMCORD]` | ❌ | |
| Webhook in ingresso | — | ✅ | `/alerts webhook-create`. Poco comune. |

### 3.13 Backup e restore

| Funzione | Chi la fa meglio e come | iYokai oggi | Nota |
|---|---|---|---|
| Salvare ruoli, canali, permessi | Xenon: 15 backup gratis, tenuti senza scadenza `[XENON]` | ❌ | Il design crea un server nuovo: **non più possibile**. Nuovo design: D8. |
| Ricaricare un backup | Xenon: crei un server vuoto, inviti il bot, `/backup load` `[XENON]` | ❌ | |
| Backup automatici | Xenon: ogni 24 ore gratis, ogni 4 ore al piano più alto `[XENON]` | ❌ | I worker ora partono (BUG-19 corretto), ma non hanno un server su cui lavorare finché non c'è D8. |
| Messaggi | Xenon: 0 gratis, 50/100/250 per canale a pagamento `[XENON]` | 🟡 | "Mirror" in tempo reale via webhook: idea diversa. Oggi non ha mai un webhook di destinazione (dipende da D8). |
| Ban, nickname, ruoli dei membri | Xenon (premium) `[XENON]` | ❌ | |
| Modelli di server | Xenon: 5.731 modelli `[XENON]` | ❌ | |
| Sincronia tra server | Xenon: messaggi, ban, ruoli (premium) `[XENON]` | ❌ | |
| Ritorno dei membri | RestoreCord: via `guilds.join` (terzi) `[RESTORECORD]`. Xenon: "non può riportare i membri" `[XENON]` | 🟡 | Scritto. BUG-21 e SEC-19 corretti il 04/10. Restano: nessuna coppia di server (D8), token mai rinnovati (`LIM-37`), ciclo senza pause (`LIM-7`), BUG-34. |

### 3.14 Statistiche

| Funzione | Chi la fa meglio e come | iYokai oggi | Nota |
|---|---|---|---|
| Canali contatore | ServerStats: 3,5 milioni di server, basta rinominare un canale `[SSTATS]`. Arcane: 3 gratis `[ARCANE]` | ❌ | |
| Statistiche di messaggi e voce | Statbot: per canale e per membro, pannello web `[STATBOT]` | ❌ | |
| Ruoli in base all'attività | Statbot "Statroles": il ruolo si perde se smetti di essere attivo `[STATBOT]` | ❌ | Interessante per i clan. |
| Grafico di crescita | Statbot `[STATBOT]` | 🟡 | `/serverstats`. Dipende dal modulo log. |

### 3.15 Divertimento

| Funzione | Chi la fa meglio e come | iYokai oggi | Nota |
|---|---|---|---|
| Mini-giochi | Yggdrasil: gare d'auto, battaglie, spinner `[YGG]` | ✅ | Moneta, dado, sasso-carta-forbici, 8ball. |
| Immagini e meme | Yggdrasil: pokéfusion, meme `[YGG]` | 🟡 | SEC-20 corretto il 04/10 (limiti e `defer`). Restano `/fun animal` e `/fun search-image` (`LIM-24`, `LIM-48`). |
| Effetti sonori in vocale | Yggdrasil: 19 suoni `[YGG]`. YAGPDB: 50 gratis `[YAGPDB]` | ❌ | |
| Telefono tra server | Yggdrasil `[YGG]` | ❌ | |
| Gioco di economia globale | Dank Memer: 8,6 milioni di server, 300+ oggetti `[DANK]` | ❌ | Altro tipo di prodotto. |

### 3.16 AI

| Funzione | Chi la fa meglio e come | iYokai oggi | Nota |
|---|---|---|---|
| Chat e personaggi AI | MEE6: venduti a parte, fuori dal Premium `[MEE6]` | ❌ | Rimandata (`BACKLOG.md` §8). |
| Moderazione con AI | Maki: solo a pagamento `[MAKI]` | ❌ | |
| Risposte AI nei ticket | Maki `[MAKI]` | ❌ | |
| Costruzione del server con AI | PeakBot (terzi, blog del bot stesso) `[TERZI]` | ❌ | |

### 3.17 Dashboard e configurazione

| Funzione | Chi la fa meglio e come | iYokai oggi | Nota |
|---|---|---|---|
| Pannello web | MEE6, Dyno, Carl-bot, ProBot, Arcane, Maki, Sapphire, Wick, Ticket Tool, Tickets | ❌ | Previsto, in un repository a parte. |
| Configurazione via comandi | Zeppelin, YAGPDB: per utenti esperti `[ZEPPELIN]` `[YAGPDB]` | 🟡 | 252 comandi. Troppi da ricordare. |
| Guida al primo avvio | ServerStats: un solo `/setup` `[SSTATS]`. ModMail: `=setup` `[MODMAIL]` | 🟡 | `/setup-wizard` copre 6 moduli su 32. |
| Creazione automatica dei canali | Carl-bot: `log aio`. Wick: crea `#logs` e `#modlogs` `[CARL]` `[WICK]` | 🟡 | Solo lo spam-trap. In piano (R3). |
| Comandi nascosti a chi non può | Standard Discord | ❌ | Tutti vedono tutto. In piano (R5). |
| Solo comandi slash | Carl-bot: i comandi a prefisso si spengono il 5/10/2026 `[CARL]` | ✅ | iYokai è già solo slash. |

### 3.18 Lingue

| Funzione | Chi la fa meglio e come | iYokai oggi | Nota |
|---|---|---|---|
| Molte lingue | Maki: 32 lingue `[MAKI]`. ProBot: 10 `[PROBOT]`. Lawliet: 7 `[LAWLIET]` | ❌ | |
| Italiano | Non in elenco per ProBot e Lawliet. Per gli altri: non verificato | ✅ | Punto forte. Qualche risposta è ancora in inglese. |
| Inglese | Tutti | ❌ | 4 frasi tradotte. In piano (R6). |
| Lingua per server | Maki, ProBot `[MAKI]` `[PROBOT]` | 🟡 | Il comando esiste ma non cambia niente. |

### 3.19 Premium e prezzi

| Bot | Prezzo | Cosa resta gratis | Fonte |
|---|---|---|---|
| MEE6 | 11,95 $/mese (terzi). "A vita" tra 89,90 e 119,99 $: fonti discordi, non verificato | Quasi niente | `[MEE6]` `[TERZI]` |
| Dyno | Da 4,99–5,99 $/mese (terzi) | Non verificato | `[TERZI]` |
| Carl-bot | 7,99 $/mese per 1 server (terzi). Piani da 1, 3 e 8 server | Quasi tutto. Livelli solo premium | `[CARL]` `[TERZI]` |
| ProBot | 5–10 $/mese (terzi) | Base | `[TERZI]` |
| Arcane | 5–7 $/mese (terzi) | 15 ruoli premio, 10 reaction roles, 5 comandi | `[ARCANE]` `[TERZI]` |
| YAGPDB | 3,50 $/server/mese (terzi) | 100 comandi personalizzati | `[YAGPDB]` `[TERZI]` |
| Maki | Non leggibile | 10 comandi, 25 ruoli livello, 1 categoria ticket | `[MAKI]` |
| Wick | Non verificato | Anti-nuke base, join gate, verifica | `[WICK]` |
| Xenon | 5,99 / 10,99 / 15,99 $/mese | 15 backup, senza messaggi | `[XENON]` |
| Tickets | 2,99 $/server/mese; marchio proprio 6,99 $ | 3 pannelli | `[TICKETS]` |
| Hydra | 5,99 $/mese per 3 server | Base | `[HYDRA]` |
| Jockie | Non leggibile | 4 bot | `[JOCKIE]` |
| RestoreCord | 0 / 5 / 10 / 20 € (terzi) | 1 backup | `[RESTORECORD]` |
| Sapphire | Tutto gratis; marchio proprio da 100 $/mese (terzi) | Tutto | `[TERZI]` |
| Nighty | 10 $ una volta | — | `[NIGHTY]` |
| **iYokai** | Nessun pagamento reale. L'owner concede a mano | 🟡 Tutto sbloccato in alpha | 6 moduli "premium" non controllano il premium |

### 3.20 Affidabilità e scala

| Bot | Server dichiarati | Fonte |
|---|---|---|
| MEE6 | 19,5 milioni | `[MEE6]` |
| Carl-bot | 15,1 milioni | `[CARL]` |
| Dyno | 11,6 milioni | `[DYNO]` |
| ProBot | 10,2 milioni | `[PROBOT]` |
| Jockie Music | 9,96 milioni | `[JOCKIE]` |
| Dank Memer | 8,6 milioni | `[DANK]` |
| Ticket Tool | 5,8 milioni | `[TT]` |
| YAGPDB | 3,6 milioni | `[YAGPDB]` |
| ServerStats | 3,5 milioni | `[SSTATS]` |
| Arcane | 3,1 milioni | `[ARCANE]` |
| UnbelievaBoat | 2,6 milioni | `[UNB]` |
| Lawliet | 2,1 milioni | `[LAWLIET]` |
| Xenon | 2,0 milioni | `[XENON]` |
| Sapphire | 1,8 milioni | `[SAPPHIRE]` |
| Maki | 1,6 milioni | `[MAKI]` |
| Tatsu | 1,5 milioni | `[TATSU]` |
| Streamcord | 1,2 milioni | `[STREAMCORD]` |
| Wick | 1,0 milioni | `[WICK]` |
| Statbot | 864.000 | `[STATBOT]` |
| Double Counter | 620.000 | `[DC]` |
| Giveaway Boat | 592.000 | `[GBOAT]` |
| Captcha.bot | 533.000 | `[CAPTCHA]` |
| Pingcord | 470.000+ | `[PINGCORD]` |
| Circle | 250.000 | `[CIRCLE]` |
| ModMail | 165.000 | `[MODMAIL]` |
| Beemo | 100.000+ | `[BEEMO]` |
| **iYokai** | **0** | Obiettivo dichiarato: 10.000 |

iYokai oggi: 7 bot in un solo processo, su una macchina sola (con D8
diventano 6: il Creator sparisce). 2614 test verdi il 04/10. La
copertura misurata il 28/09 era al 71%, con i comandi al 20–45%
(`REVIEW.md` §16). Nessuna cancellazione dei dati quando il bot esce da
un server (fase F5).

---

## 4. Cosa manca a iYokai

Impegno: **S** = pochi giorni, **M** = una o due settimane, **L** = un
mese o più. Sono stime grossolane.

**Dal 04/10 tutte le voci di questa sezione sono nel piano**, nessuna
esclusa. "Alta, media, bassa" indica solo l'ordine. Il dettaglio di
ognuna (file, comandi, limiti) è in `NUOVE_FUNZIONI.md`.

### Priorità ALTA

| # | Cosa | Chi ce l'ha | Perché ti serve | Impegno | Dipende da |
|---|---|---|---|---|---|
| A1 | **Backup senza creare server** | Xenon | È una promessa centrale di iYokai e oggi è impossibile. | L | Decisione dell'owner. Permesso `CREATE_GUILD_EXPRESSIONS`. |
| A2 | **Pannello web** | Tutti i grandi | 252 comandi sono una barriera. Chi prova MEE6 o Carl-bot si aspetta un sito. | L | Dominio e HTTPS. Login OAuth. Privacy policy. |
| A3 | **Privacy policy, termini, cancellazione dati** | Double Counter (`/privacy`) | Obbligo di Discord per superare i 100 server, e obbligo GDPR. | M | R2 del piano. Un sito dove pubblicarle. |
| A4 | **Log dei messaggi e log divisi** | Carl-bot, Dyno | È la prima cosa che un moderatore cerca. | M | Già in piano: R3 e R4. `message_content`. |
| A5 | **Ruolo automatico all'ingresso** e ruoli ridati a chi rientra | Carl-bot, Arcane | Funzione di base. Senza, un admin tiene un secondo bot. | S | R5 (struttura comandi). |
| A6 | **Inglese completo** | Tutti | Obiettivo dichiarato IT + EN. | L | Già in piano: R6. |
| A7 | **Comandi personalizzati e risposte automatiche** | YAGPDB, Carl-bot, MEE6, Sapphire | Ogni community vuole i suoi `/regole`, `/ip`, `/orari`. | M | `message_content` per le risposte automatiche. |
| A8 | **Rank card e immagine di benvenuto** | MEE6, Arcane, ProBot | È la parte "visibile" del bot, quella che fa dire "bello". | M | Niente: Pillow c'è già. |
| A9 | **Ticket: modulo, chiusura automatica, voto** | Ticket Tool, Tickets | Senza modulo lo staff fa sempre le stesse domande. | M | Niente. |
| A10 | **Pagamento vero per il premium** | Tutti | Senza, il modello free/premium resta sulla carta. | M | App verificata da Discord per vendere dentro Discord. |

### Priorità MEDIA

| # | Cosa | Chi ce l'ha | Perché ti serve | Impegno | Dipende da |
|---|---|---|---|---|---|
| M1 | Verifica su web e account doppi | Double Counter, Wick | Sicurezza forte è un tuo obiettivo. | L | Pannello web. Privacy policy. |
| M2 | Captcha a immagine | Wick, Captcha.bot | La somma scritta non ferma un bot. | S | Niente. |
| M3 | Starboard | MEE6, Carl-bot, Dyno | Semplice e molto richiesto. | S | Niente. |
| M4 | Canali contatore | ServerStats, Arcane, Statbot | Molto visibili, facili. | S | Niente. |
| M5 | Impostazioni XP: canali senza XP, moltiplicatori, canale del level-up, "togli i ruoli precedenti" | MEE6, ProBot, Maki | Ogni server le chiede. | S | Niente. |
| M6 | Modalità dei reaction roles | Carl-bot | Vedi §6. | S | Niente. |
| M7 | Canale richieste musicali con player | Hydra (storico) | Più comodo dei comandi. | M | Musica verificata live. |
| M8 | Comando e classifica degli inviti | MEE6, Maki, Lawliet (tracciano gli inviti) | Il tracciamento esiste già. | S | Niente. |
| M9 | Compleanni | MEE6, Maki, Lawliet | Classico delle community. | S | Niente. |
| M10 | Giveaway avanzati (modelli, più ingressi, requisito messaggi) | Giveaway Boat | Le community di gioco ne fanno tanti. | S | Niente. |
| M11 | Costruttore di embed | ProBot, Atlas, Hydra | Regole e annunci belli. | M | Meglio con il pannello web. |
| M12 | Blocco totale e "panic mode" | Wick | Un comando solo durante un attacco. | M | Anti-raid e anti-nuke corretti. |
| M13 | Appello anche per i ban normali | Circle | Riusa il flusso dello spam-trap. | S | LC-5 corretto. |
| M14 | Link di phishing | Captcha.bot, Wick | Truffa comune. | S | `message_content`. |
| M15 | Alert Kick e ruolo "in diretta" | Streamcord, Pingcord | Utile a una community di gioco. | S | Niente. |
| M16 | Statistiche di attività | Statbot | Dati utili anche per i clan. | M | Tabelle che crescono: serve retention. |
| M17 | Ticket via DM | ModMail | Alternativa ai pannelli. | M | Niente. |
| M18 | Moduli e candidature | Dyno, Circle | Candidature staff e clan. | M | Niente. |
| M19 | Soglie sui warn manuali | Carl-bot | Estende la scala che c'è già. | S | Niente. |

### Priorità BASSA

| # | Cosa | Chi ce l'ha | Perché | Impegno | Dipende da |
|---|---|---|---|---|---|
| B1 | AI (chat, moderazione, ticket) | MEE6, Maki | Costi e privacy. Ora in piano: fase F12 (issue #50). | L | Privacy policy pubblicata. Tetto di spesa (D13). |
| B2 | Bot con marchio proprio | MEE6, Tickets, Sapphire | Ricavo extra, ma tanto lavoro. | L | Premium funzionante. |
| B3 | Galleria di modelli di server | Xenon (5.731) | Serve una community grande. | L | Backup nuovo. |
| B4 | Sincronia tra server | Xenon | Utile a chi ha più server. | M | Backup nuovo. |
| B5 | Animali, case, profili | Tatsu, Dank Memer | Altro prodotto. I clan sono la tua versione. | L | Economia stabile. |
| B6 | Effetti sonori in vocale | Yggdrasil, YAGPDB | Carino, non essenziale. | S | Musica verificata. |
| B7 | Linguaggio di script | Atlas, YAGPDB | Solo per utenti esperti. | L | A7. |
| B8 | App installabile dall'utente | — (SPEC §B) | Mai iniziata. | M | Niente. |

---

## 5. Cosa iYokai fa meglio o in modo diverso

Solo differenze vere. Per ognuna dico anche cosa non va oggi.

**1. Musica a più bot dentro un bot tutto-in-uno.**
Jockie ha la flotta ma fa solo musica. I tutto-in-uno letti hanno un
bot solo. iYokai mette moderazione e 5 bot musicali in un'installazione.
- ⚠️ Oggi è un bot **per server**, non per canale vocale. Quindi il
  vantaggio non c'è ancora.
- ⚠️ I worker quasi certamente non suonano: usano la sessione Lavalink
  del bot principale (`LIM-40`). Da correggere con D10 e provare live.
- ⚠️ Jockie ne dà 4 gratis e 27 a pagamento: 5 non è un record.

**2. Radio condivisa con musica tua.**
Tutti i server sentono lo stesso punto dello stesso brano. I brani sono
tuoi: nessun problema di diritti. Non l'ho trovata altrove.
- ⚠️ I file locali non vengono trovati (BUG-10). L'avvio automatico
  non è fatto (#45).

**3. Canale trappola con appello.**
Carl-bot ha il canale trappola. iYokai aggiunge: DM prima del ban,
pulizia dei messaggi fino a 30 giorni, pulizia di inviti e webhook,
transcript HTML, appello in un thread con bottoni per lo staff.
- ⚠️ Contenuto e transcript da riprovare: l'intent `message_content` è
  acceso nel codice dal 04/10.
- ⚠️ I bottoni di appello muoiono a ogni riavvio (LC-5).
- ✅ BUG-22, BUG-24 e BUG-25 corretti il 04/10.

**4. Rete di ban tra server, a scelta e reciproca.**
Chi aderisce dà e riceve. Vale solo per i ban automatici della
trappola, quindi un admin non può usarla per colpire qualcuno.
- ⚠️ È una condivisione di dati tra server: va scritta nella privacy
  policy.
- ⚠️ Beemo fa una cosa simile, gratis, senza configurazione.

**5. Clan con economia vera.**
Tesoreria a senso unico, canali Discord comprati con le monete e con
le ore in vocale, boost, classifica mensile, ruoli pari tra clan.
Tatsu, UnbelievaBoat e Dank Memer non hanno niente di simile.
- ⚠️ I clan finanziati con trasferimento vengono cancellati (BUG-15).
- ⚠️ Manca `/clan lascia`. L'invito aggiunge senza chiedere.
- ⚠️ L'XP vocale dei clan non ha anti-farm.

**6. Backup e ritorno dei membri nello stesso bot.**
Xenon dichiara di non poter riportare i membri. RestoreCord li riporta
ma, secondo Xenon, fa creare all'utente una propria applicazione
Discord (terzi). iYokai farebbe tutto da solo.
- ⚠️ **Oggi non funziona ancora**: i server non sono creabili (D8).
  Corretti il 04/10: worker fermi (BUG-19) e link che scadevano in 10
  minuti (BUG-21: ora 7 giorni, legati al destinatario).

**7. Restore più prudente di RestoreCord.**
Token cifrati con AES-256-GCM. Tre modalità di consenso per server.
Conservazione diversa per chi esce, chi è espulso e chi è bannato.
Nessun IP raccolto. Su RestoreCord, Xenon riporta una fuga di dati
segnalata a febbraio 2025 (tra 840.000 e 1 milione di record; contestata
da RestoreCord, che parla di meno di 5.000) (terzi) `[RESTORECORD]`.
- ⚠️ Confronto onesto: RestoreCord funziona ed è usato. iYokai no.
- ⚠️ Il restore funziona solo per chi ha dato il consenso prima.
- ⚠️ I token scadono dopo circa 7 giorni e oggi non vengono mai
  rinnovati (`LIM-37`).
- ⚠️ La modalità "invito via DM" manda messaggi a utenti che non
  l'hanno chiesto. Discord vieta di contattare utenti senza permesso
  `[DISCORD]`. Va limitata a chi ha accettato prima.

**8. Italiano come prima lingua.**
ProBot dichiara 10 lingue e Lawliet 7: l'italiano non c'è. È una
nicchia vera, e tu hai già una community italiana.
- ⚠️ Alcune risposte sono ancora in inglese. L'inglese vero manca.

**9. Storico della configurazione con annulla.**
`/config history`, `rollback`, `export`, `import`. Non l'ho trovato
nelle pagine lette degli altri bot. Corretto di recente (BUG-6).

**10. Premium che si sblocca anche senza soldi.**
Con la cassa del server (monete e anzianità) o con un boost sul tuo
server. È un modello diverso da tutti gli altri.
- ⚠️ Non c'è un pagamento vero. 6 moduli non controllano il premium.

**11. Storico degli eventi consultabile.**
30 giorni gratis, 180 premium, con ricerca per utente e per canale e
esportazione. Non ho trovato una ricerca simile via comando negli altri.

**12. XP vocale gratis con anti-farm.**
In Arcane l'XP vocale è solo premium.

---

## 6. Cosa iYokai ha ma va migliorato

Per ogni punto: chi lo fa meglio e **come**.

### 6.1 Primo avvio e configurazione
- **Modello:** Carl-bot (`log aio` crea categoria e 5 canali già
  divisi), Wick (crea da solo `#logs` e `#modlogs`), ServerStats (un
  solo `/setup`).
- **Oggi:** il wizard copre 6 moduli su 32. Quasi nessuna funzione crea
  i suoi canali.
- **Da fare:** un wizard che per ogni modulo chiede "creo io i canali o
  ne scegli uno?" e alla fine mostra cosa è acceso. Il router dei canali
  (R3) è la base giusta.

### 6.2 Reaction roles
- **Modello:** Carl-bot. Modalità per messaggio:
  - *unique*: un solo ruolo alla volta;
  - *verify*: il ruolo si dà e non si toglie;
  - *drop*: il ruolo si toglie soltanto;
  - *reversed*: reagire toglie, togliere la reazione dà;
  - *binding*: una scelta sola, per sempre;
  - *temp*: ruolo a tempo (premium);
  - *lock*: menu bloccato.
  In più: lista di ruoli ammessi o esclusi, limite per ruolo.
- **Oggi:** solo "normale" e un tetto di scelte. `toggle=False` non va.
- **Da fare:** aggiungere unique, verify, binding e la lista dei ruoli
  ammessi. Sono le più usate (scelta colore, accettazione regole).

### 6.3 Ticket
- **Modello:** Ticket Tool e Tickets.
  - Fino a 25 pannelli in un messaggio.
  - Modulo con fino a 5 domande prima di aprire.
  - Transcript HTML fino a 1.000 messaggi, anche in DM a chi ha aperto.
  - Presa in carico che rinomina il canale e toglie la scrittura agli
    altri dello staff.
  - Chiusura automatica per inattività o se l'utente esce.
  - Voto a stelle alla chiusura.
  - Limite di ticket aperti per utente.
  - Ticket come thread privato invece che canale.
- **Oggi:** pannello, categorie, claim semplice, priorità, statistiche.
- **Da fare, in ordine:** modulo per categoria, limite per utente (oggi
  il doppio clic ne apre due), chiusura automatica, voto.

### 6.4 Rank card e premi di livello
- **Modello:** MEE6 e Arcane.
  - Rank card come immagine, con colori e sfondo.
  - Premi di ruolo "accumula" oppure "togli i precedenti".
  - Annuncio del level-up in quattro modi: spento, canale corrente, DM,
    canale scelto.
  - Canali e ruoli senza XP.
- **Oggi:** `/rank` è testo. Premi solo ad accumulo. Annuncio fisso.
- **Vantaggio da tenere:** nessun limite ai ruoli premio (Arcane 15,
  Maki 25) e XP vocale gratis.

### 6.5 Immagine di benvenuto
- **Modello:** ProBot. Sfondo caricabile (sotto 3 MB), avatar tondo o
  quadrato con posizione e misura, testi con posizione, misura e colore.
- **Oggi:** solo testo.
- **Da fare:** partire con 3–4 modelli pronti e uno sfondo caricabile.
  L'editor completo ha senso solo nel pannello web.

### 6.6 Comandi personalizzati
- **Modello:** YAGPDB (inneschi: comando, "inizia con", "contiene",
  regex, reazione, intervallo, bottone, modal, comando slash, cambio di
  ruolo) e Carl-bot (tag con variabili, condizioni, ruoli, embed).
- **Oggi:** l'utente può solo *chiedere* un comando all'owner. Non
  regge oltre pochi server.
- **Da fare:** versione semplice. Nome, testo o embed, ruolo da dare o
  togliere, pausa tra un uso e l'altro. Niente linguaggio di script.

### 6.7 Anti-nuke
- **Modello:** Wick.
  - Due soglie per ogni azione: al minuto e all'ora. Coprono sia
    l'attacco veloce sia quello lento.
  - Chi supera la soglia va in **quarantena**, non bannato: resta nel
    server, senza poteri, in attesa di un controllo.
  - Filtro su chi può aggiungere bot.
  - "Strict mode": avviso se un ruolo riceve permessi pericolosi.
  - Rilevamento della "pulizia" di massa dei membri (prune).
  - Due livelli di fiducia: extra owner e trusted admin.
- **Oggi:** una soglia sola. Può punire se stesso. La punizione di
  default non funziona sui bot, che sono il caso più comune.
- **Da fare:** dopo BUG-11, aggiungere la doppia soglia e la quarantena
  come punizione di default (già "ACCETTATA" in `BACKLOG.md` §6).

### 6.8 Verifica
- **Modello:** Double Counter. Un link, una pagina web, esito in circa
  3 secondi. Lo staff decide cosa fare dei sospetti. C'è `/manverify`
  per verificare a mano. Dati tenuti 24 mesi, comando `/privacy`.
- **Attenzione:** su top.gg ha 2,64 su 5, con 110 voti da una stella su
  202 `[DC]`. La sua documentazione ammette falsi allarmi "VPN" con
  ad-blocker, Private Relay di iOS e browser come Brave. La sua privacy
  policy cita anche dati pubblicitari (Ezoic).
- **Oggi:** bottone, reazione, somma scritta, età dell'account.
- **Da fare:** tenere la scelta già presa ("segnalare allo staff, mai
  ban automatico"). Captcha a immagine subito, verifica web dopo.

### 6.9 Backup
- **Modello:** Xenon, dopo la fine della creazione di server.
  1. `/backup create` salva ruoli, canali, permessi e impostazioni come
     **dati** nel database.
  2. Se il server viene distrutto, l'admin crea un server vuoto e
     invita il bot.
  3. `/backup load` ricrea tutto. Si può scegliere cosa caricare.
  4. Backup automatici a intervalli, con più copie conservate.
- **Oggi:** un secondo bot crea un server nuovo e lo cede. Impossibile.
- **Deciso (D8):**
  - lo snapshot del server si salva come dati nel database;
  - l'admin crea un server vuoto (anche da un link "modello" che il
    bot genera con `Guild.create_template`), invita il bot e lancia il
    comando di collegamento o caricamento;
  - il bot Creator e `YOKAI_CREATOR_TOKEN` **spariscono**;
  - mirror, snapshot settimanale dei membri, `/restore-users` e
    promozione continuano a funzionare su quel server.
- **Vantaggio da tenere:** dopo il caricamento, il ritorno dei membri.

### 6.10 Musica
- **Modello:** Hydra storico (canale dedicato con coda e controlli;
  fonte di terzi del 2023) e Jockie (più bot con un solo prefisso).
- **Oggi:** 23 comandi slash. Nessun player con bottoni.
- **Da fare:** un messaggio "player" con bottoni pausa, salta, stop,
  mescola, ripeti. Si aggiorna da solo. Non servono DJ né voti.
- **Prima di tutto (D10):** un nodo wavelink per ogni bot, un bot per
  canale vocale, Lavalink 4.2.0 o successivo.

### 6.11 Log
- **Modello:** Carl-bot. Cinque gruppi (messaggi, membri, ingressi,
  server, voce), un canale ciascuno. Si possono ignorare canali, utenti
  e messaggi che iniziano con un prefisso.
- **Oggi:** un canale solo. Niente log dei messaggi. Niente forum.
- **Nota:** Carl-bot registra modifiche e cancellazioni solo entro 1
  ora dal messaggio `[CARL]`. Con il database iYokai può fare di più.

### 6.12 Pannello
- **Modello:** tutti. Login con Discord, scelta del server, una pagina
  per modulo con interruttore.
- **Da fare:** il pannello deve scrivere **le stesse impostazioni** dei
  comandi. Così comandi e sito restano allineati, come dice già
  `REVIEW.md` §8.

---

## 7. Idee da NON copiare

Regola dell'owner (04/10): **nessuna funzione richiesta viene
abbandonata**. In questa sezione restano solo:
- ciò che Discord o la legge vietano (per ognuno c'è l'alternativa
  lecita più vicina);
- ciò che l'owner stesso ha scartato.

### 7.1 Da Nighty (self-bot)
Nighty automatizza un account utente. Discord lo vieta e può chiudere
l'account `[DISCORD]`.

| Idea di Nighty | Si può fare con un bot vero? |
|---|---|
| Vincere Nitro in automatico ("sniper") | **No.** |
| Entrare nei giveaway in automatico, anche con più account | **No.** |
| Clonare un server con l'account utente | **No.** Solo backup con bot invitato. |
| Spiare un utente | **No.** |
| Stato, bio e pronomi animati | **No.** Serve il token utente. |
| Comandi "in ogni server" | **Sì**, con un'app installabile dall'utente (SPEC §B). |
| Rich presence personalizzata | **Sì**, con un'app sul PC via RPC locale (SPEC §D). |
| Avvisi su parole chiave | **Sì**, lato bot, solo nei server col bot e con `message_content`. |
| Backup e restore | **Sì**, lato bot (§6.9). |
| Comandi fun e immagini | **Sì**, ci sono già. |
| "Trolling" | **No.** È molestia. |

### 7.2 Dal modello RestoreCord
- **Far creare all'utente un bot proprio** per aggirare i controlli.
  Xenon riporta che la guida di RestoreCord spiega come renderlo "più
  difficile da rilevare per Discord" (terzi). Da non fare.
- **Raccogliere IP alla verifica** senza una privacy policy. Su
  Trustpilot c'è chi lamenta proprio questo (terzi).
- **Riportare membri senza un consenso chiaro.** Il consenso deve dire:
  "questo bot potrà farti entrare nel server di riserva".
- **Riportare membri in un server qualsiasi.** Era SEC-2, già corretto.

### 7.3 Musica
- **YouTube come sorgente di un servizio a pagamento.** È il motivo
  della chiusura di Groovy e Rythm. Consiglio: non vendere mai funzioni
  musicali legate a YouTube.
- **DJ role, voto per saltare, filtri audio**: scartati da te.
- **Ricerca separata, forceskip, remove, move, seek, lyrics**: scartati
  da te in modo definitivo. Non li ho messi tra le mancanze.

### 7.4 Privacy e dati
- **Punteggio di reputazione globale** degli utenti: già respinto in
  `BACKLOG.md` §9.
- **Ban automatico tra server per account doppi**: già deciso di no.
- **Dati pubblicitari legati alla verifica** (li cita la privacy
  policy di Double Counter `[DC]`).
- **Usare i messaggi per addestrare un'AI**: vietato da Discord.
- **Mandare i messaggi degli utenti a un'AI esterna** senza averlo
  scritto nella privacy policy.

### 7.5 Modello commerciale
- **Mettere a pagamento le basi**, come MEE6. È una lamentela
  ricorrente su MEE6 (terzi) `[TERZI]`.
- **Giochi d'azzardo legati a soldi veri.** Discord vieta di
  monetizzare il gioco d'azzardo `[DISCORD]`. Se un giorno si vendono
  monete, niente blackjack o roulette.
- **Comandi NSFW sbloccati votando il bot** (UnbelievaBoat `[UNB]`).
  Non adatto al tuo piano di verifica dell'identità per l'NSFW.

### 7.6 Altro
- **Comandi a prefisso.** Carl-bot li spegne il 5/10/2026. iYokai è già
  solo slash: va bene così.
- **Messaggi automatici per "tenere vivo" un server**: vietati `[DISCORD]`.
- **Annunci in DM a tutti gli utenti**: vietati senza permesso.
- **Giuria automatica, classifica pubblica dello staff, plugin di
  terzi**: già respinti in `BACKLOG.md` §12.

---

## 8. Proposta di priorità

> **Superata.** L'ordine di lavoro valido è in
> [`../02-piano/PRIORITA.md`](../02-piano/PRIORITA.md). I passi P1–P10
> qui sotto sono stati distribuiti nelle fasi F1–F14. La domanda su
> BUG-26/28/29 è chiusa dalla decisione D8.

Testo originale del 04/10 mattina, tenuto come storico:

Viene **dopo** `PIANO_FIX.md`. Il piano resta com'è: R1-bis, R1, R1b,
R2, R3, R4, R5, R6, R7.

### Una decisione da prendere subito (dentro il piano, non una fase nuova)
R1-bis contiene BUG-26, BUG-28, BUG-29 e la parte "coda dei backup" di
BUG-19. Riguardano il bot Creator che crea server. Quel flusso non può
più funzionare. (La parte "snapshot degli utenti" di BUG-19 resta
valida: serve al restore.)
**Chiedi all'owner** se correggerli o segnarli "superati dal nuovo
backup". Correggerli ora rischia di essere lavoro buttato.
Lo stesso vale per la voce "posizioni dei ruoli clonati" di R1.

### Dopo il piano

| Passo | Cosa | Perché in questo punto |
|---|---|---|
| **P1 — Carte in regola** | Privacy policy e termini pubblicati. Verifica dell'app Discord. Lavalink proprio. Tutta `VERIFICA_LIVE.md` eseguita. | Senza, il bot si ferma a 100 server. Va fatto prima di invitare gente. |
| **P2 — Backup nuovo** | Modello Xenon (§6.9). Restore dei membri solo per chi ha dato il consenso. | È una promessa centrale e oggi è a zero. Toglie anche un bot (Creator). |
| **P3 — Le basi che mancano** | Ruolo automatico (A5). Starboard (M3). Contatori (M4). Impostazioni XP (M5). Modalità reaction roles (M6). Classifica inviti (M8). Compleanni (M9). | Tutte piccole. Portano iYokai al livello che un admin si aspetta. |
| **P4 — Parte visibile** | Rank card e immagine di benvenuto (A8). Ticket con modulo, chiusura automatica e voto (A9). | È quello che si vede e si mostra agli amici. |
| **P5 — Comandi personalizzati** | Versione semplice (A7), poi risposte automatiche. | Molto richiesto. Serve `message_content` già attivo (R4). |
| **P6 — Pannello web, prima versione** | Login, scelta server, interruttori dei moduli, impostazioni principali. | Il lavoro più grande. Meglio farlo quando le funzioni sono stabili. |
| **P7 — Sicurezza avanzata** | Captcha a immagine (M2). Doppia soglia e quarantena (§6.7). Panic mode (M12). Verifica web e account doppi (M1). | La verifica web ha bisogno del pannello e della privacy policy. |
| **P8 — Musica comoda** | Un bot per canale. Player con bottoni (M7). | Dopo la prova live dell'audio. |
| **P9 — Premium vero** | Pagamento (A10). Decidere cosa è gratis e cosa no. | Solo con utenti veri e app verificata. |
| **P10 — Extra** | Statistiche, ticket via DM, moduli, alert Kick, AI. | Quando il resto regge. |

### Una regola per decidere il premium
Tieni gratis tutto ciò che MEE6 ha messo a pagamento: moderazione,
benvenuto, livelli, reaction roles. Fai pagare ciò che ti costa:
backup con messaggi, più bot musicali, log conservati a lungo, verifica
avanzata, marchio proprio. È quello che fanno Xenon e Jockie.

---

## 9. Fonti

Tutte lette il 4/10/2026. Dove indicato "(terzi)" la pagina non è del
bot di cui parla.

**`[DISCORD]` Discord (ufficiale)**
- https://docs.discord.com/developers/resources/guild
- https://docs.discord.com/developers/resources/guild-template
- https://docs.discord.com/developers/topics/oauth2
- https://docs.discord.com/developers/change-log
- https://support-dev.discord.com/hc/en-us/articles/8563934450327-Discord-Developer-Policy
- https://support-dev.discord.com/hc/en-us/articles/8562894815383-Discord-Developer-Terms-of-Service
- https://support-dev.discord.com/hc/en-us/articles/6207308062871-What-are-Privileged-Intents
- https://support-dev.discord.com/hc/en-us/articles/23926564536471-How-Do-I-Get-My-App-Verified
- https://support.discord.com/hc/en-us/articles/115002192352-Automated-User-Accounts-Self-Bots
- https://support.discord.com/hc/en-us/articles/10575066024983-Monetization-Policy
- https://github.com/discord/discord-api-docs/pull/7991/files
- https://discord.js.org/docs/packages/discord-api-types/main/v10/RESTPostAPIGuildsJSONBody:Interface (terzi: libreria)
- https://discord-media.com/en/news/development-2025-the-complete-year-in-review-api-migration-guide.html (terzi)

**`[MEE6]`**
- https://help.mee6.xyz/en/articles/710936-mee6-free-vs-premium-plans-comparison
- https://help.mee6.xyz
- https://wiki.mee6.xyz/en/plugins/reaction-roles
- https://wiki.mee6.xyz/plugins/custom-commands
- https://wiki.mee6.xyz/en/plugins/levels
- https://top.gg/bot/159985870458322944

**`[DYNO]`**
- https://dyno.gg
- https://docs.dyno.gg/en/modules/actionlog
- https://docs.dyno.gg/en/modules/automod
- https://top.gg/bot/155149108183695360

**`[CARL]` Carl-bot**
- https://carl.gg
- https://docs.carl.gg/_sidebar.md
- https://docs.carl.gg/roles.md
- https://docs.carl.gg/logging.md
- https://docs.carl.gg/automod.md
- https://docs.carl.gg/tagstriggers.md
- https://docs.carl.gg/levels.md
- https://docs.carl.gg/premium.md
- https://docs.carl.gg/faq.md
- https://docs.carl.gg/notice.md
- https://www.patreon.com/carlbot
- https://discordbotlist.com/bots/235148962103951360

**`[PROBOT]`**
- https://probot.io
- https://docs.probot.io
- https://docs.probot.io/docs/modules/welcome
- https://docs.probot.io/docs/modules/level_system
- https://top.gg/bot/282859044593598464

**`[YAGPDB]`**
- https://yagpdb.xyz
- https://yagpdb.xyz/premium-perks
- https://help.yagpdb.xyz/
- https://help.yagpdb.xyz/docs/custom-commands/commands/
- https://github.com/botlabs-gg/yagpdb
- https://top.gg/bot/204255221017214977

**`[YGG]` Yggdrasil**
- https://ygg.fun
- https://thelinuxcode.com/use-yggdrasil-discord-bot/ (terzi, 2023; il numero di server che riporta non è stato usato)

**`[ARCANE]`**
- https://docs.arcane.bot
- https://docs.arcane.bot/premium
- https://top.gg/bot/437808476106784770

**`[MAKI]`**
- https://maki.gg
- https://maki.gg/premium
- https://top.gg/bot/563434444321587202

**`[SAPPHIRE]`**
- https://top.gg/bot/678344927997853742

**`[ATLAS]`**
- https://atlas.bot

**`[LAWLIET]`**
- https://lawlietbot.xyz
- https://top.gg/bot/368521195940741122

**`[CIRCLE]`**
- https://top.gg/bot/497196352866877441

**`[ZEPPELIN]`**
- https://github.com/ZeppelinBot/Zeppelin
- https://zeppelin.gg

**`[WICK]`**
- https://wickbot.com
- https://wickbot.com/premium
- https://docs.wickbot.com/intro/what-is-wick/
- https://docs.wickbot.com/setup/
- https://docs.wickbot.com/faq/
- https://top.gg/bot/536991182035746816

**`[BEEMO]`**
- https://beemo.gg
- https://docs.beemo.gg

**`[DC]` Double Counter**
- https://doublecounter.gg
- https://docs.doublecounter.gg
- https://docs.doublecounter.gg/double-counter-en/pro-version.md
- https://docs.doublecounter.gg/double-counter-en/legal.md
- https://docs.doublecounter.gg/double-counter-en/alt-detections-and-vpn-intrusions.md
- https://top.gg/bot/703886990948565003

**`[CAPTCHA]` Captcha.bot**
- https://captcha.bot
- https://docs.captcha.bot/
- https://docs.captcha.bot/introduction/getting-started
- https://top.gg/bot/512333785338216465

**`[TT]` Ticket Tool**
- https://docs.tickettool.xyz
- https://docs.tickettool.xyz/dashboard/panel-configs/panel-options.md
- https://docs.tickettool.xyz/dashboard/panel-configs/form-options.md
- https://docs.tickettool.xyz/dashboard/panel-configs/transcript-options.md
- https://docs.tickettool.xyz/dashboard/panel-configs/claiming-options.md
- https://docs.tickettool.xyz/dashboard/panel-configs/limit-options.md
- https://docs.tickettool.xyz/dashboard/panel-configs/automation-options.md
- https://top.gg/bot/557628352828014614

**`[TICKETS]` Tickets (tickets.bot)**
- https://tickets.bot/premium
- https://docs.tickets.bot/
- https://docs.tickets.bot/features/introduction
- https://top.gg/bot/508391840525975553

**`[MODMAIL]`**
- https://modmail.xyz
- https://top.gg/bot/575252669443211264

**`[XENON]`**
- https://xenon.bot/backups
- https://xenon.bot/docs
- https://xenon.bot/docs/backups
- https://xenon.bot/premium
- https://xenon.bot/templates
- https://xenon.bot/compare/backups
- https://xenon.bot/blog/xenon-vs-restorecord
- https://top.gg/bot/416358583220043796

**`[RESTORECORD]`** (sito ufficiale non leggibile: errore 403)
- https://xenon.bot/blog/xenon-vs-restorecord (terzi: concorrente)
- https://xenon.bot/compare/backups (terzi: concorrente)
- https://www.trustpilot.com/review/restorecord.com (terzi: recensioni)

**`[NIGHTY]`**
- https://nighty.one

**`[JOCKIE]` Jockie Music**
- https://www.jockiemusic.com
- https://top.gg/bot/411916947773587456

**`[HYDRA]`**
- https://hydra.bot
- https://hydra.bot/premium
- https://top.gg/bot/547905866255433758
- https://maketecheasier.com/add-hydra-bot-discord-server/ (terzi, 2023)

**`[MUSICA]` Storia di YouTube e bot musicali**
- https://9to5google.com/2021/09/13/youtube-nukes-popular-groovy-bot-discord-music-service-for-breaking-platforms-tos/ (terzi)
- https://rythm.fm
- https://bestforandroid.com/hydra-music-bot-discord-commands.md (terzi; dice che Hydra ha chiuso nel 2021, ma il sito di Hydra è attivo: non l'ho usato per questo punto)

**`[TATSU]`**
- https://tatsu.gg
- https://top.gg/bot/172002275412279296

**`[UNB]` UnbelievaBoat**
- https://unbelievaboat.com
- https://unbelievaboat.com/premium
- https://top.gg/bot/292953664492929025

**`[DANK]` Dank Memer**
- https://dankmemer.lol
- https://top.gg/bot/270904126974590976

**`[STATBOT]`**
- https://docs.statbot.net
- https://top.gg/bot/491769129318088714

**`[SSTATS]` ServerStats**
- https://serverstats.bot/

**`[GBOAT]` Giveaway Boat e GiveawayBot**
- https://top.gg/bot/530082442967646230
- https://giveawaybot.party

**`[STREAMCORD]`**
- https://streamcord.io
- https://top.gg/bot/375805687529209857

**`[PINGCORD]`**
- https://pingcord.xyz
- https://pingcord.xyz/premium

**`[TERZI]` Confronti e prezzi da siti esterni**
- https://peakbot.pro/blog/discord-bot-pricing-comparison-2026 (blog di un concorrente)
- https://peakbot.pro/blog/which-discord-bot-features-are-free-vs-premium-2026 (blog di un concorrente)
- https://peakbot.pro/blog/best-all-in-one-discord-bots-2026 (blog di un concorrente)
- https://peakbot.pro/blog/how-to-back-up-discord-server-restore (blog di un concorrente)
- https://blog.communityone.io/best-discord-bots/
- https://www.stork.ai/en/mee6

### Cosa non ho potuto verificare su fonte ufficiale
- La **data esatta** in cui Discord ha tolto la creazione di server ai
  bot ("luglio 2025" viene da terzi). È verificato che l'endpoint oggi
  non è documentato e che discord.py lo segna deprecato dalla 2.6.
- I **prezzi** di MEE6, Dyno, Carl-bot, ProBot, Arcane, YAGPDB, Wick,
  Double Counter, Captcha.bot, Ticket Tool, Jockie, Maki, Statbot,
  Pingcord, UnbelievaBoat. Dove c'è un numero, viene da terzi.
- Tutto su **RestoreCord** (sito non leggibile).
- I limiti gratis e premium di **Dyno**.
- Il canale richieste di **Hydra** (oggi non compare sul sito).
- Se **Rythm** usa musica in licenza.
- Numero di server e premium di **Yggdrasil**.
- Funzioni e prezzo di **Sapphire** (sito non leggibile; solo top.gg).
- Quali bot offrono l'**italiano**, a parte gli elenchi di ProBot e
  Lawliet.
- La tabella di MEE6 "gratis contro premium" è ufficiale, ma indica
  come Premium anche la moderazione: è un dato sorprendente, da
  ricontrollare a mano sul sito prima di usarlo in pubblico.
