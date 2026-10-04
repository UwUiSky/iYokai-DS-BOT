# APP_UTENTE_E_DESKTOP.md — Cosa si può offrire fuori dai server dove c'è il bot

Due domande dell'owner (04/10/2026):

1. Cosa possono fare gli utenti **nei server dove iYokai non è
   presente**, usando il sistema delle app di Discord?
2. Cosa si può offrire con una **versione desktop**, sullo stile di
   Nighty (profilo, traduzioni, comandi custom, log dei comandi,
   notifiche a schermo, storico dei ping con salto al messaggio…)?

Voci SPEC collegate: **B** (iYokai App) e **D** (iYokai Desktop).
Issue: NF-36 e NF-37.

Legenda: ✅ si può fare in modo regolare · 🟡 si può fare con un limite
(scritto accanto) · 🔒 serve l'approvazione di Discord · ❌ possibile
solo automatizzando l'account dell'utente (vietato, vedi §3.1): accanto
c'è l'alternativa più vicina.

---

## 1. iYokai App: comandi installati sull'utente

### 1.1 Come funziona

Un'app Discord può essere installata **su un server** (il bot classico)
oppure **su un utente**. Nel secondo caso l'utente si porta dietro i
comandi ovunque: in ogni server, nei DM e nei gruppi.

| Cosa | Valore | Fonte |
|---|---|---|
| Tipi di installazione | `GUILD_INSTALL`, `USER_INSTALL` | [Application Commands](https://docs.discord.com/developers/interactions/application-commands) |
| Dove funziona un comando | server (`GUILD`), DM con il bot (`BOT_DM`), DM e gruppi (`PRIVATE_CHANNEL`) | stessa pagina |
| Comandi slash globali per app | 100 | stessa pagina |
| Voci del menu "tasto destro su un utente" | 15 | stessa pagina |
| Voci del menu "tasto destro su un messaggio" | 15 | stessa pagina |
| Messaggi dopo la prima risposta, dove l'app non è nel server | 5 per interazione | [Receiving and Responding](https://docs.discord.com/developers/interactions/receiving-and-responding) |
| Tempo per la prima risposta | 3 secondi | stessa pagina |
| Durata del "gettone" dell'interazione | 15 minuti | stessa pagina |

**Scelta consigliata: un'applicazione separata ("iYokai App")**, non il
bot principale. Motivo: i 100 comandi slash sono per applicazione, e il
bot principale è già a 97. Un'app separata ha i suoi 100 + 15 + 15.
Stesso codice, stesso database, token diverso.

### 1.2 Cosa l'app **non** può fare dove il bot non c'è

Dove iYokai non è stato invitato, l'app esiste solo **durante il
comando** di chi l'ha installata:

- non riceve eventi: non vede messaggi, ingressi, reazioni;
- non legge la cronologia del canale; vede **solo** il messaggio o
  l'utente su cui è stato fatto "tasto destro";
- non può moderare, dare ruoli, creare canali, entrare in vocale;
- non può scrivere più tardi: solo la risposta e fino a 5 messaggi
  nei 15 minuti successivi;
- la risposta è **visibile solo a chi ha usato il comando** se in quel
  server l'utente non ha il permesso "Usa app esterne" (da verificare
  live server per server).

Per tutto il resto (log, moderazione, musica in vocale) serve il bot nel
server.

### 1.3 Elenco delle funzioni possibili

**A. Sul messaggio (menu "App" con il tasto destro) — 15 posti**

| # | Funzione | Cosa fa | Note |
|---|---|---|---|
| A1 | Traduci | Traduce il messaggio nella lingua dell'utente | ✅ Serve un servizio di traduzione (gratuito con tetto, o AI in F12) |
| A2 | Salva nei segnalibri | Salva testo, autore e link; li ritrovi con `/segnalibri` o sul Desktop | ✅ |
| A3 | Ricordamelo | "Ricordami questo messaggio tra 2 ore": DM con il link | 🟡 Il DM arriva solo se l'utente accetta DM dall'app |
| A4 | Citazione come immagine | Crea l'immagine "citazione" con avatar e testo | ✅ Usa i limiti immagini già fatti (SEC-20) |
| A5 | Meme da questa immagine | Applica testo o filtri all'immagine allegata | ✅ |
| A6 | Controlla i link | Dice se un link è nella lista di phishing (NF-31) | ✅ |
| A7 | Segnala alla rete iYokai | Segnala una truffa allo staff della rete di ban globale | ✅ Solo segnalazione: decide un umano |
| A8 | Spiega o riassumi | Riassunto o spiegazione del messaggio | 🟡 Fase F12 (AI), solo quel messaggio |
| A9 | Leggi il testo dell'immagine | Estrae il testo da uno screenshot | ✅ Libreria OCR sul server |
| A10 | Converti | Trova nel messaggio orari, valute, unità e li converte | ✅ |
| A11 | Copia come testo pulito | Toglie formattazione, link di tracciamento | ✅ |
| A12 | Salva come risposta pronta | Trasforma il messaggio in una risposta salvata (C1) | ✅ |

**B. Sull'utente (tasto destro su una persona) — 15 posti**

| # | Funzione | Cosa fa | Note |
|---|---|---|---|
| B1 | Profilo iYokai | Mostra la scheda globale: livello, clan, medaglie | ✅ Solo dati che l'altro utente ha reso pubblici |
| B2 | Stato nella rete di sicurezza | Dice se l'account è segnalato nella rete di ban globale | 🟡 Risposta sempre privata; solo "segnalato sì/no", mai il motivo (privacy) |
| B3 | Avatar e banner | Mostra avatar e banner in grande | ✅ |
| B4 | Nota personale | Appunto privato su quella persona, visibile solo a te | ✅ |
| B5 | Ship / voto / gioco | I comandi di `/fun` su quella persona | ✅ |
| B6 | Invita nel mio clan | Manda la richiesta di ingresso nel clan | 🟡 Vale nei server dove c'è il bot |

**C. Comandi slash personali**

| # | Funzione | Cosa fa | Note |
|---|---|---|---|
| C1 | Risposte salvate ("comandi custom" personali) | `/r nome`: l'app scrive il testo o l'embed salvato | ✅ Appare come risposta dell'app, non come messaggio dell'utente |
| C2 | Promemoria | `/promemoria` con invio in DM | ✅ |
| C3 | Note e liste | Appunti e liste di cose da fare | ✅ |
| C4 | Fusi orari | "Che ore sono da Marco?", orario in formato Discord | ✅ |
| C5 | Conversioni e calcoli | Valute, unità, calcolatrice | ✅ |
| C6 | Strumenti di testo | Maiuscole, spoiler, conteggio, codice QR, colore | ✅ |
| C7 | Costruttore di embed | Crea un embed e lo pubblica come risposta | ✅ Limiti embed di `LIMITI.md` |
| C8 | Sondaggio veloce | Sondaggio nativo di Discord | 🟡 Da verificare live se è ammesso dove il bot non c'è |
| C9 | Traduci testo | `/traduci testo lingua`: pubblica la traduzione | ✅ |
| C10 | Profilo e rank card | La propria scheda come immagine | ✅ |
| C11 | Portafoglio globale | Monete e premio giornaliero legati all'utente, non al server | ✅ Va deciso con NF-40 |
| C12 | Divertimento e immagini | Tutti i comandi di `/fun`, animali, ricerca immagini | ✅ |
| C13 | Cerca comando | Lo stesso `/utility cerca-comando` | ✅ |
| C14 | Apri un ticket con il supporto iYokai | Da qualsiasi server | ✅ |
| C15 | Impostazioni personali | Lingua, risposte private o pubbliche, DM sì/no | ✅ |
| C16 | Storico dei miei comandi | Ultimi comandi usati e dove | ✅ |
| C17 | AFK personale | Messaggio "sono via" | 🟡 Risponde da solo solo nei server dove c'è il bot |
| C18 | Testi di una canzone, "cosa ascolto" | Testi e scheda del brano | ✅ |
| C19 | Playlist personali | Salvate una volta, usabili con `/music` dove c'è il bot | ✅ |

**D. Attività (app che si apre dentro Discord)**

| # | Funzione | Cosa fa | Note |
|---|---|---|---|
| D1 | Radio iYokai come Attività | Ascolto condiviso della radio dell'owner dentro un'Attività, anche dove il bot non c'è | 🟡 Va sviluppata come pagina web (Embedded App SDK); un solo comando "di ingresso" per app |
| D2 | Mini-giochi e quiz | Giochi a più utenti in vocale o in chat | 🟡 Stesso strumento di D1 |
| D3 | Lavagna, sondaggi dal vivo | Strumenti per riunioni | 🟡 |

**E. Collegamento con i server dove il bot c'è**

| # | Funzione | Cosa fa |
|---|---|---|
| E1 | Azioni a distanza per lo staff | Da qualsiasi posto: `/staff` con i propri server; il **bot** esegue l'azione nel server dove è presente, dopo aver controllato i permessi |
| E2 | Avvisi personali | Scegliere quali eventi dei propri server ricevere in DM |
| E3 | Ruoli collegati | Requisiti di ruolo basati sui dati iYokai (livello, verifica) con i "Linked Roles" di Discord — 🟡 il server deve aver aggiunto l'app |

---

## 2. iYokai Desktop

### 2.1 Come funziona, in modo regolare

Tre canali, tutti ufficiali:

1. **Accesso con Discord (OAuth2)** al servizio iYokai. Con il consenso
   dell'utente si leggono: identità (`identify`), elenco dei suoi server
   (`guilds`), il suo profilo in un server (`guilds.members.read`),
   account collegati (`connections`).
2. **Canale in tempo reale con il servizio iYokai.** Tutto ciò che il
   **bot** vede nei server dove è presente può arrivare al programma:
   menzioni, parole chiave, ticket, avvisi.
3. **Collegamento locale con il client Discord (RPC/IPC).** Lo stato
   "sta giocando a…" (rich presence) funziona per tutti. Le altre
   funzioni RPC (leggere le notifiche del client, comandare microfono e
   cuffie, leggere i canali) richiedono scope `rpc` che **Discord
   concede solo su approvazione**; senza approvazione funzionano per
   l'owner e per pochi tester dell'app.

Fonti: [RPC](https://docs.discord.com/developers/topics/rpc),
[Rich Presence](https://docs.discord.com/developers/discord-social-sdk/development-guides/setting-rich-presence),
[Change log](https://docs.discord.com/developers/change-log).

### 2.2 Funzione per funzione, rispetto a Nighty

| Funzione stile Nighty | Esito | Come si fa in iYokai Desktop |
|---|---|---|
| Stato personalizzato ricco, con immagini, bottoni, timer | ✅ | Rich presence via IPC. Profili salvati e rotazione automatica |
| Stato che cambia da solo in base a cosa fai | ✅ | Regole: app in primo piano, orario, brano in ascolto sulla radio iYokai |
| Stato testuale con emoji a rotazione, bio animata, avatar e banner che cambiano, tema Nitro finto | ❌ | Solo con il token dell'utente. Alternativa: rich presence a rotazione, scheda profilo iYokai (immagine), "Game Stats Widget" sul profilo Discord 🔒 se Discord ammette l'app |
| Notifiche a schermo per i ping | ✅ nei server con iYokai | Il bot vede la menzione e la manda al programma. Finestrella con autore, canale, testo, tasto "Vai al messaggio" |
| Storico di quando e dove sei stato pingato, con salto al messaggio | ✅ nei server con iYokai | Tabella delle menzioni per utente; elenco con filtri e link diretto. Disponibile anche come `/utility menzioni` e in DM |
| Storico dei ping in **tutti** i server e nei DM | 🔒 / ❌ | Con lo scope `rpc.notifications.read` il client Discord passa le notifiche al programma: serve l'approvazione di Discord. Senza, non esiste via regolare |
| Avviso su parole chiave ("highlight") | ✅ nei server con iYokai | Elenco di parole per utente; avviso sul Desktop e in DM |
| Avviso di "ghost ping" (menzione cancellata) | ✅ | Il modulo esiste già: si aggiunge l'invio al Desktop |
| Registro dei messaggi cancellati e modificati | 🟡 | Per lo staff, nei log del server (fase F6). Personale: `/snipe` dove il server lo permette. Nei DM ❌ |
| Traduzione automatica dei messaggi in arrivo | 🟡 | Un clic: "Traduci" dal menu del messaggio (iYokai App). Sul Desktop: tasto rapido che traduce il testo copiato. Tutto automatico e dentro il client ❌ |
| Traduzione di ciò che scrivi | 🟡 | `/traduci`: pubblica la traduzione come risposta dell'app. Oppure tasto rapido: traduce il testo negli appunti e tu lo incolli. Invio automatico a nome tuo ❌ |
| Comandi custom personali | ✅ | Risposte salvate (C1) ovunque; sul Desktop anche come testi da incollare con un tasto rapido |
| Script e automazioni che scrivono a nome tuo | ❌ | Alternativa: automazioni fatte dal **bot** nei tuoi server (risposte automatiche NF-10, messaggi programmati) |
| Log dei comandi usati | ✅ | Storico dei propri comandi iYokai; per lo staff, log dei comandi del server |
| Risposta automatica quando sei via (AFK) | 🟡 | `/afk`: il bot risponde a chi ti menziona nei server dove è presente. Nei DM ❌ |
| Pannello dei propri server | ✅ | Elenco con icone, dove c'è iYokai, dove sei staff, con collegamento al pannello web |
| Azioni rapide da tastiera per lo staff | ✅ | Il programma chiede al servizio iYokai, che controlla i permessi e fa agire il **bot**: blocca canale, timeout, annuncio, giveaway |
| Controlli vocali: muto, cuffie, cambio canale da tasto | 🔒 | Scope `rpc.voice.*`: serve l'approvazione di Discord |
| Suoni e radio | ✅ | Comandi alla radio e alla musica dei propri server; lettore della radio iYokai dentro il programma |
| Notifiche per dirette, giveaway vinti, ticket, promemoria, livello raggiunto | ✅ | Eventi del servizio iYokai |
| Statistiche personali | ✅ | Messaggi, tempo in vocale, livelli nei server con iYokai |
| Copia di un server ("clone") | 🟡 | È il backup di iYokai (fase F3), per i server dove sei admin |
| Partecipare da solo ai giveaway, "nitro sniper", messaggi di massa, strumenti per i token | ❌ | Non si fanno: sono abusi e costano il ban dell'account. Nessuna alternativa prevista |
| Temi e plugin dentro il client Discord | ❌ | Modificare il client è vietato. Il programma ha i **suoi** temi |
| Sovrimpressione in gioco | 🟡 | Finestra sempre in primo piano del programma, con le notifiche iYokai |

### 2.3 Cosa serve costruire

| Pezzo | Dove | Fase |
|---|---|---|
| Tabella delle menzioni e comando `/utility menzioni` | bot | F6 (insieme ai log dei messaggi) |
| Parole chiave personali ("highlight") | bot | F9 |
| Servizio in tempo reale per gli eventi dell'utente | servizio web | F10 (stesso servizio del pannello) |
| Programma per PC (Windows prima, poi macOS e Linux) | progetto a parte | F13 |
| Domanda a Discord per gli scope `rpc` | Developer Portal | F13, dopo la verifica dell'app |

---

## 3. Limiti da tenere a mente

### 3.1 Perché niente account automatizzato

Nighty funziona entrando in Discord **con il token dell'utente** e
agendo al suo posto. Discord lo vieta e chiude gli account che lo
fanno; un'app verificata che lo proponesse perderebbe la verifica. Per
questo ogni funzione di quel tipo qui sopra ha la sua alternativa
regolare, e dove non esiste è scritto.

### 3.2 Privacy

- Lo storico delle menzioni e le parole chiave salvano testi di altre
  persone: valgono le regole di conservazione della fase F5 (90 giorni,
  cancellazione su richiesta) e vanno spiegati nella privacy policy.
- "Stato nella rete di sicurezza" (B2) non deve mai rivelare il motivo
  di una segnalazione a chi non è staff.
- Tutto ciò che il Desktop mostra passa dai permessi veri dell'utente
  nel server: non si mostra un canale che l'utente non può vedere.

### 3.3 Da verificare live

- Risposte pubbliche o private dove il bot non c'è (permesso "Usa app
  esterne").
- DM dall'app a chi l'ha installata.
- Sondaggi nativi nelle risposte dell'app.
- Quanti tester possono usare gli scope `rpc` prima dell'approvazione.
