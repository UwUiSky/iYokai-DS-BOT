# PRIORITA.md — Cosa fare, in che ordine

Questa è **l'unica lista di lavoro**. Sostituisce `PIANO_FIX.md`, che
resta in questa cartella come storico.

Come si usa:
- Le fasi si fanno **nell'ordine scritto**: F1, F2, F3…
- Dentro una fase, dall'alto verso il basso.
- Ogni voce ha un codice. Il dettaglio è in:
  - [`../01-analisi/REVIEW.md`](../01-analisi/REVIEW.md) per SEC-, BUG-,
    LC-, GDPR-, DB-, PERF- e per i paragrafi "§";
  - [`PIANO_FIX.md`](PIANO_FIX.md) (storico) per RT-1…RT-5;
  - [`../01-analisi/LIMITI.md`](../01-analisi/LIMITI.md) per LIM-;
  - [`NUOVE_FUNZIONI.md`](NUOVE_FUNZIONI.md) per NF-;
  - [`MODIFICHE_ESISTENTE.md`](MODIFICHE_ESISTENTE.md) per il "come"
    (indicato con → M e il numero della riga, es. → M 1.2);
  - [`DECISIONI.md`](DECISIONI.md) per D1…D14.
- `[x]` = fatto e provato con i test, con lo SHA del commit.
  `[ ]` = da fare. ⚡ = poche righe.
- Un `[x]` **non** è una prova su Discord vero. Quelle prove sono in
  [`../03-verifica/VERIFICA_LIVE.md`](../03-verifica/VERIFICA_LIVE.md).

Regola dell'owner: **nessuna funzione richiesta viene tolta dal piano.**
Non ci sono voci "in attesa di decisione": le scelte sono in
`DECISIONI.md`.

## Soglia di lancio

Il bot **non va invitato in server veri** prima di aver finito F1, F5 e
F7. Motivi: fino a F7 chiunque può usare i comandi di moderazione
(SEC-1); fino a F5 i dati non vengono mai cancellati (GDPR).

## Perché quest'ordine

| Fase | Viene qui perché |
|---|---|
| F1 | Le funzioni esistenti devono smettere di rompersi prima di costruirci sopra. |
| F2 | La musica è una promessa centrale e oggi quasi certamente è muta. |
| F3 | Il backup è una promessa centrale e oggi è impossibile. Toglie anche un bot intero. |
| F4 | Già fatta con questo lavoro: `SPEC.md` dice la verità. |
| F5 | Obbligo di legge, e condizione per la verifica dell'app. Va dopo F3 perché il backup nuovo crea tabelle con dati personali. |
| F6 | I log nuovi devono nascere già nel router dei canali. |
| F7 | È il cambio più grande ai comandi: si fa una volta sola, dopo che la logica è stabile. |
| F8 | I nomi dei comandi cambiano in F7: si traduce dopo. |
| F9 | Le funzioni nuove nascono già con gruppi, lingue e router giusti. |
| F10 | Il pannello ha senso quando le impostazioni sono stabili. |
| F11–F14 | Dipendono da pannello, lingue o privacy policy. |

**Una differenza dall'ordine proposto:** ho aggiunto F13 e F14. Servono
a non lasciare fuori nulla: F13 raccoglie le funzioni nuove di priorità
media e bassa, l'applicazione utente e iYokai Desktop (in `SPEC.md` ma
senza una fase); F14 raccoglie le idee "rimandate" di `BACKLOG.md`.

---

## F0 — Già fatto (stato portato da `PIANO_FIX.md`)

**R-T, rete di test**
- [x] RT-1, RT-2, RT-3, RT-4 — `b8848f1`
- [x] RT-5 test deboli rinforzati — `307941e`, `96011cf`, `e04eca5`,
  `9e8cc1e`, `c2a9582`, `965ab35`, `fba882e`, `44ede43`

**R0, sicurezza**
- [x] SEC-4, SEC-17 — `599a2d4`, `67e5771`, `42f227d`
- [x] SEC-2 — `15ddf7d`
- [x] SEC-3 — `4d5e4a4`, poi rifatto in BUG-21
- [x] SEC-5 — `bde6f00`
- [x] SEC-6 — `25c3cdc`
- [x] SEC-7 — `cb05eff`
- [x] SEC-8 — `a28f817`
- [x] SEC-8b — `e24059f`
- [x] SEC-9 — `a31dbba`
- [x] SEC-10, LC-4 — `9d52a82`
- [x] SEC-11 — `ac11f7a`
- [x] SEC-12 — `647b680`
- [x] SEC-13 (D7) — `8a96320`, `2596734`
- [x] SEC-14 — `0e9eb3b`
- [x] SEC-15 — `bf2a772`
- [x] SEC-16 (parte `repr`) — `2df2265`
- [x] #41 `PREMIUM_ALPHA_UNLOCK_ALL` — `576f155`
- [x] #36 log degli intent all'avvio — `3666a66`

**DB, migrazioni**
- [x] DB-1 — `659d9fa`, `5fa15fb`
- [x] DB-2 (indici) — `659d9fa`, `d17f071`

**R1, prima metà**
- [x] BUG-1 — `6c724d3`
- [x] BUG-2 — `c9534fb`
- [x] BUG-6 — `071504a`
- [x] `/config import` valida lo schema — `80322ff`
- [x] BUG-7 — `8a218d1`, `44ede43`
- [x] BUG-8 — `9683b36`
- [x] BUG-9 — `376ff6b`
- [x] LC-8 — `45d2a78`
- [x] BUG-3 — `3547e4c` (il flusso cambia con D8)
- [x] BUG-4 — `b6eeb81` (pulizia dei server orfani poi **disattivata apposta** in `fba882e`)
- [x] `/define-backup` un job alla volta — `93f7049`
- [x] Snapshot settimanale dopo il login — `1098bb2`
- [x] Limiti di emoji, sticker e suoni nel backup — `e502c1f`

**R1-bis (04/10)**
- [x] BUG-19 — `fba882e`, `b0d5302`
- [x] BUG-20 — `c5ebd0f`
- [x] SEC-18 — `6509fec`
- [x] BUG-21, SEC-19 — `8590e89`
- [x] BUG-22 — `ea2e897`, `77e0fe1`
- [x] BUG-30 — `10d16f1`
- [x] BUG-27 — `cf6eea0`
- [x] BUG-23 — `9e8cc1e`
- [x] SEC-20 — `b2303a5`
- [x] SEC-21 — `7b96e8c`
- [x] SEC-22 — `690a5b6`
- [x] BUG-24 — `263fdf2`
- [x] BUG-25 — `3046fda`
- [x] BUG-31 — `965ab35`
- [x] BUG-32 — `c2a9582`
- [x] BUG-33 — `eceedc8`
- [x] Feed con la codifica dichiarata — `d6bda5e`
- [x] Worker musicale non partito saltato dalla flotta — `b1452be`
- [x] D9 intent `message_content` acceso nel codice — `783329e`

**Superati dalla decisione D8** (non si correggono: il codice che
riguardano viene tolto in F3)
- BUG-26, BUG-28, BUG-29.

---

## F1 — Resto di R1 e superamenti dei limiti

**Obiettivo:** ogni funzione che esiste fa quello che dice, senza
rompersi sui limiti di Discord.

**Serve dall'owner:**
- attivare "Message Content Intent" nel Developer Portal del bot
  principale (senza, il bot non si collega più);
- controllare che nel `.env` ci sia `ENVIRONMENT=development` oppure
  `production` (ora è obbligatoria).

**Dipende da:** niente.

### F1.a — Subito ⚡ (poche righe ciascuna, con test)
- [ ] **LIM-2** `/poll`: limiti su domanda e risposte → M 10.1
- [ ] **LIM-4** `/report`: limite sul motivo e errore gestito → M 1.5
- [ ] **LIM-5** `/automod badword-list` come file se lungo → M 2.4
- [ ] **LIM-11** sticky: catturare `HTTPException` → M 10.3
- [ ] **LIM-14** `/permission-heatmap` tagliata → M 3.15
- [ ] **LIM-19** log dei ruoli tagliato → M 5.3
- [ ] **LIM-23** `/search`: limite sul testo → M 10.10
- [ ] **LIM-53** task conservati → M 14.5
- [ ] **LIM-56** testi superati nel codice (D11) → M 14.8
- [ ] BUG-11 (prima metà): l'anti-nuke non conta il bot → M 3.1
- [ ] LC-6 (bot): anti-raid, benvenuto e XP ignorano bot e messaggi di sistema → M 3.6, M 9.17, M 10.16
- [ ] BUG-18 (prima metà): `/voice transfer` rifiuta bot e assenti → M 7.3
- [ ] LC-8 (residuo): `/security-score` effimero → M 3.16
- [ ] REVIEW §5: `duration_logic` con tetto → M 1.9
- [ ] REVIEW §5: `/alerts add` mostra il prefisso `RSS-` → M 11.7
- [ ] REVIEW §5: `OWNER_ID` non numerico, messaggio chiaro → M 13.3
- [ ] REVIEW §11: `NSFW_TOKEN` facoltativo fino a F11 → M 14.15

### F1.b — Intent acceso: riprovare ciò che leggeva messaggi vuoti
- [ ] BUG-5: test con messaggi **con** contenuto per filtri AutoMod, transcript dei ticket, spam-trap, mirror, filtro allegati di `/clear` → M 2.1, M 6.8

### F1.c — Limiti di testo e di liste
- [ ] **LIM-1** cricchetto "ogni opzione di testo ha un massimo" → M 14.1
- [ ] **LIM-8** motivo entro 512 ⚡, azione prima del caso, liste dei casi tagliate → M 1.2, M 1.3, M 1.6
- [ ] **LIM-10** benvenuti controllati al salvataggio → M 10.2
- [ ] **LIM-12** messaggi programmati → M 10.5
- [ ] **LIM-13** promemoria → M 10.5
- [ ] **LIM-15** `/logs` e esportazione → M 5.4
- [ ] **LIM-16** tetto e lista dei feed → M 11.8
- [ ] **LIM-17** role menu (anche `toggle=False`, REVIEW §4) → M 10.7
- [ ] **LIM-18** livelli, negozio, clan, giveaway → M 9.2, M 9.12
- [ ] **LIM-20** log e transcript dello spam-trap → M 3.10
- [ ] **LIM-22** liste e pannello dell'owner → M 10.12
- [ ] **LIM-55** funzione comune per i file sotto 10 MiB → M 14.7

### F1.d — Tre secondi e bottoni
- [ ] **LIM-9** verify → M 4.1
- [ ] **LIM-24** `/fun animal` e `/fun search-image` ⚡ → M 15.1
- [ ] **LIM-25** LC-3: `defer()` in moderazione, clan, suggerimenti, bottone Unban, comandi musicali → M 1.4, M 3.11, M 8.16, M 9.11, M 10.9
- [ ] **LIM-26** View persistenti: LC-5 appello dello spam-trap, bottoni piattaforma → M 3.9, M 7.6
- [ ] BUG-13 gestore errori → M 14.2
- [ ] REVIEW §5: errore effimero dopo `defer` pubblico → M 14.3

### F1.e — Sicurezza automatica
- [ ] BUG-11 (seconda metà) → M 3.2
- [ ] **LIM-31** registro di controllo letto con nuovi tentativi; PERF-5 modulo controllato prima → M 3.3
- [ ] #30 recupero anti-nuke completo (REVIEW §12 7.2) → M 3.4
- [ ] BUG-12, #27 anti-raid → M 3.7
- [ ] **LIM-30** ruoli Muted e Quarantined → M 1.7, M 3.8
- [ ] REVIEW §12 (7.3) date nel log dello spam-trap → M 3.12
- [ ] **LIM-36** tetti di canali e inviti → M 3.13, M 12.16
- [ ] REVIEW §12 (3.3, 8.18) i 6 moduli premium controllano il premium → M 3.14
- [ ] LC-6 (inviti): scarico e attribuzione → M 3.17

### F1.f — AutoMod
- [ ] **LIM-29** parole oltre 60 ⚡, eccezioni conservate, tetto di 6 regole → M 2.2, M 2.3
- [ ] REVIEW §4: `seconds=` rispettato → M 2.5
- [ ] REVIEW §4: lista nera dei link → M 2.6
- [ ] **LIM-32** escalation → M 2.7

### F1.g — Ticket e vocali
- [ ] **LIM-6** categorie dei ticket → M 6.1
- [ ] **LIM-3** rinomine (ticket e vocali) → M 6.2, M 6.3, M 7.1, M 7.2
- [ ] REVIEW §4: ticket doppi, canale cancellato, controllo staff, ruolo storico → M 6.4, M 6.5, M 6.6, M 6.7
- [ ] BUG-18 (seconda metà) → M 7.4
- [ ] REVIEW §4: vocali orfani → M 7.5

### F1.h — Economia e clan
- [ ] BUG-14 (#35, #23) → M 9.1, M 9.2, M 9.3
- [ ] LC-1 `/assegna-lobby` → M 9.4
- [ ] BUG-15 → M 9.5
- [ ] BUG-17 (test) → M 9.6
- [ ] REVIEW §4: modulo attivo, `/clan lascia`, invito con consenso, anti-farm, decadimenti, giveaway nei thread → M 9.7, M 9.8, M 9.9, M 9.10, M 9.15
- [ ] REVIEW §12 (15.14) e §11: storico tesoreria, ruoli allo scioglimento, co-owner → M 9.13, M 9.14
- [ ] REVIEW §5: stallo nei trasferimenti, giorno in UTC → M 9.16

### F1.i — Utility e owner
- [ ] D12 ping di ruolo nei messaggi dell'admin → M 10.6
- [ ] REVIEW §4: sticky persi o doppi → M 10.4
- [ ] REVIEW §5: due staff decidono insieme (suggerimenti, richieste) → M 10.9
- [ ] REVIEW §12 (1.2) `modules_updated` → M 10.13
- [ ] **LIM-35** DM di benvenuto durante un raid → M 10.16
- [ ] REVIEW §12 (17.5) blacklist dei server per tutti i bot → M 13.2

### F1.l — Feed e alert
- [ ] **LIM-45** BUG-16 YouTube (D5) → M 11.1
- [ ] **LIM-46** Twitch ⚡ (`first`), blocchi di 100, 401 → M 11.2, M 11.3
- [ ] LC-7 → M 11.4
- [ ] REVIEW §4: feed che ripubblica tutto → M 11.5
- [ ] REVIEW §12 (10.9) modelli per Twitch e YouTube → M 11.6
- [ ] **LIM-51** sessione, `User-Agent`, `ETag` (con PERF-7) → M 11.9
- [ ] **LIM-48** Pixabay: cache di 24 ore, immagine ricaricata come allegato, credito → M 15.2
- [ ] REVIEW §20: invio del webhook protetto → M 11.10

### F1.m — Core
- [ ] **LIM-47** scheduler senza chiamate a Discord in transazione → M 14.4
- [ ] **LIM-50** connessioni al database → M 14.6
- [ ] REVIEW §4: cache dei moduli, `bot_stats` → M 14.9

**Fatto quando:** suite verde due volte; i cricchetti
`KNOWN_SENZA_MAX_LENGTH` e simili sono vuoti; ogni voce ha il suo test;
`VERIFICA_LIVE.md` ha i passi per ciò che va provato su Discord.

---

## F2 — Musica (D10) e radio

**Obiettivo:** i 5 bot musicali suonano davvero, uno per canale, e la
radio resta accesa.

**Serve dall'owner:**
- un Lavalink 4.2.0 o successivo raggiungibile (la guida arriva con
  questa fase);
- i 5 bot musicali invitati nel server di prova;
- i file della radio nella cartella indicata.

**Dipende da:** F1 non obbligatoria, ma consigliata.

- [ ] **LIM-54** `wavelink>=3.5.1` ⚡, controllo della versione dei nodi → M 8.10, M 8.11
- [ ] **LIM-40** un nodo per bot → M 8.1
- [ ] **LIM-41** collegamento dei nodi, chiusura del Pool → M 8.2
- [ ] **LIM-42** scelta esplicita del nodo → M 8.3
- [ ] **LIM-43** BUG-10 brani locali → M 8.4
- [ ] **LIM-44** radio nei canali vuoti → M 8.5
- [ ] REVIEW §12 (9.2/9.3) un bot per canale vocale → M 8.6
- [ ] REVIEW §4: `/stop` e `/skip` solo dal canale del player → M 8.7
- [ ] #45 radio automatica → M 8.8
- [ ] #47, #48 `deploy/lavalink/` → M 8.9
- [ ] **LIM-49** intent dei worker ⚡ → M 8.12
- [ ] **LIM-33** worker con shard → M 8.13
- [ ] **LIM-34** palco, canale pieno, tempo scaduto → M 8.14
- [ ] **LIM-21** titoli e playlist → M 8.15
- [ ] REVIEW §11: `next_track_index` → M 8.17
- [ ] RT-5 (residuo): test sul cablaggio di `music_sessions` → M 8.18

**Fatto quando:** in un server di prova due canali vocali suonano
insieme con due bot diversi, e la radio resta in un canale vuoto per
un'ora (prova live scritta in `VERIFICA_LIVE.md`).

---

## F3 — Backup (D8)

**Obiettivo:** salvare un server e ricaricarlo su un server creato a
mano, senza il bot Creator. Riportare i membri che hanno dato il
consenso.

**Serve dall'owner:**
- togliere `YOKAI_CREATOR_TOKEN` dal `.env` quando la fase è finita;
- un server vuoto di prova per il caricamento.

**Dipende da:** niente. Prima di F5.

- [ ] **LIM-39** flusso nuovo e Creator tolto → M 12.1, M 12.2
- [ ] Mappa per nome, ordine dei ruoli (REVIEW §12 11.3) → M 12.3, M 12.4
- [ ] **LIM-28** qualità audio ⚡, webhook → M 12.5, M 12.6
- [ ] **LIM-27** nome del webhook del mirror → M 12.7
- [ ] **LIM-38** canali offuscati (backup, anti-nuke, log) → M 12.8, M 5.8
- [ ] Permesso `CREATE_GUILD_EXPRESSIONS` nel link → M 12.9
- [ ] **LIM-37** rinnovo dei token → M 12.10
- [ ] **LIM-7** ciclo di `/restore-users` → M 12.11, M 12.12
- [ ] BUG-34 coppia dopo la promozione → M 12.13
- [ ] REVIEW §12 (11.10/11.11) modalità "OAuth alla verifica" → M 12.14
- [ ] **LIM-52** chiave ruotabile → M 12.15
- [ ] Più snapshot e messaggi salvati (modello Xenon) → M 12.17

`LIM-38` ha una scadenza: il 16/11/2026 Discord accende i canali
offuscati per tutti i bot.

**Fatto quando:** un backup di prova viene caricato su un server vuoto
(prova live); il bot parte senza il token del Creator; nessun file
cita più il Creator.

---

## F4 — SPEC onesta

**Obiettivo:** `SPEC.md` dice la verità su cosa c'è e cosa manca.

- [x] Marcatori corretti, testi imprecisi sistemati, §9 e §11 riscritti
  secondo D10 e D8, sezioni nuove §18–§25, riquadro con i conteggi —
  fatto con la riorganizzazione dei documenti del 04/10.

**Da qui in poi:** ogni commit che chiude una voce aggiorna il suo
marcatore in `SPEC.md` e il conteggio nel riquadro.

---

## F5 — Dati e GDPR

**Obiettivo:** i dati hanno una scadenza, un utente può farli
cancellare, e il bot ha le carte per essere verificato da Discord.

**Serve dall'owner:**
- pubblicare privacy policy e termini (il testo si prepara qui);
- attivare la 2FA sull'account;
- fare la verifica dell'app quando il bot si avvicina a 100 server.

**Dipende da:** F3 (le tabelle del backup nuovo entrano nel registro).

- [ ] **NF-04** GDPR-1, GDPR-2, GDPR-3, PERF-3: registro dei dati, uscita dai server (D6), pulizia, cancellazione ed esportazione → M 14.11
- [ ] REVIEW §4 e §11: `prune_old_index` e `purge_expired_voluntary_leaves` messi in programma
- [ ] SEC-16 (residui): token dei webhook come hash → M 11.11
- [ ] Testo della politica dei dati in `SPEC.md` §19 e bozza di privacy policy
- [ ] Motivazione per gli intent (serve a 10.000 utenti, D11): elenco delle funzioni che usano ogni intent

**Fatto quando:** il test "ogni tabella con dati personali è nel
registro" è verde; un utente di prova viene cancellato davvero; la
privacy policy è pubblicata.

---

## F6 — Router dei canali e log

**Obiettivo:** ogni cosa che il bot scrive va nel canale giusto, anche
in un forum. I messaggi cancellati e modificati vengono registrati.

**Serve dall'owner:** niente.

**Dipende da:** F1 (intent riprovato).

- [ ] **NF-01** router, migrazione delle impostazioni, creazione automatica (D3) → M 5.1, M 5.5, M 3.18
- [ ] **NF-02** log dei messaggi
- [ ] **NF-03** snipe ed editsnipe
- [ ] REVIEW §12 (5.10): azioni di moderazione mai registrate → M 1.8
- [ ] REVIEW §4: log avanzati (spostamenti, mute volontario) → M 5.6
- [ ] REVIEW §5: soundboard con gli eventi, ghost-ping → M 5.7, M 5.9

**Fatto quando:** nessun file scrive più in un canale senza passare dal
router (cricchetto vuoto).

---

## F7 — Nuova struttura dei comandi (D2, D4)

**Obiettivo:** 13 gruppi, comandi nascosti a chi non può usarli.

**Serve dall'owner:**
- controllare `MAIN_GUILD_ID` nel `.env`;
- dopo la fase, delegare i gruppi ai ruoli dello staff in
  *Impostazioni server → Integrazioni → iYokai*.

**Dipende da:** F1–F6 (si spostano comandi già stabili).

- [ ] **NF-05** albero nuovo con `/mod` e `/modban`
- [ ] SEC-1 permessi dei comandi di moderazione → M 1.1
- [ ] LC-2 `guild_only` su ogni gruppo
- [ ] **LIM-57** conto dei comandi → M 13.1
- [ ] REVIEW §11: `can_use_moderation_commands` usata o tolta
- [ ] `COMMAND_LIST.md` rigenerato

**Fatto quando:** `KNOWN_MISSING_DEFAULT_PERMISSIONS` e
`KNOWN_NOT_GUILD_ONLY` sono vuoti; per ogni comando dello staff un
test rifiuta un membro senza permessi.

---

## F8 — Lingue e `/utility cerca-comando` (D1)

**Obiettivo:** tutto il bot in italiano e in inglese.

**Serve dall'owner:** rileggere i testi inglesi più visibili.

**Dipende da:** F7.

- [ ] **NF-06** file dei testi, traduttore dei comandi, liste comandi nelle due lingue, ricerca → M 10.11, M 14.14
- [ ] REVIEW §7: risposte oggi in inglese (role menu, verify, spam-trap, benvenuti) portate nel file dei testi

**Fatto quando:** nessun testo per l'utente è scritto dentro un cog;
"bannare un utente" e "ban a user" trovano `/modban ban` al primo
posto.

---

## F9 — Funzioni nuove, primo gruppo

**Obiettivo:** le funzioni che un admin si aspetta da un bot
tutto-in-uno.

**Serve dall'owner:** niente.

**Dipende da:** F6, F7, F8.

- [ ] **NF-07** ruolo automatico, ruoli ridati, ruoli a tempo
- [ ] **NF-08** starboard
- [ ] **NF-09** comandi personalizzati → M 10.15
- [ ] **NF-10** risposte automatiche
- [ ] **NF-11** immagine di benvenuto
- [ ] **NF-12** rank card
- [ ] **NF-13** ticket: modulo, pannelli, chiusura automatica, voto
- [ ] **NF-14** modalità dei reaction roles
- [ ] **NF-15** impostazioni dei livelli
- [ ] **NF-17** costruttore di embed
- [ ] **NF-18** captcha a immagine
- [ ] **NF-19** canale richieste musicali e playlist
- [ ] Wizard per categoria → M 10.14
- [ ] Soglie sui warn manuali → M 1.10

**Fatto quando:** ogni funzione ha i suoi test, il suo modulo in
`/admin setup` e la sua voce `[x]` in `SPEC.md` §22–§23.

---

## F10 — Pannello web

**Obiettivo:** configurare il bot da un sito; verifica avanzata;
premium che si paga davvero.

**Serve dall'owner:**
- un dominio con HTTPS;
- il repository privato del pannello;
- gli indirizzi di ritorno OAuth nel Developer Portal;
- app verificata da Discord, per vendere dentro Discord.

**Dipende da:** F5, F7, F8, F9.

- [ ] **NF-20** pannello (SPEC §C e §24)
- [ ] **NF-21** verifica web e account doppi (SPEC §4.2, §4.3)
- [ ] **NF-22** pagamento del premium

**Fatto quando:** un admin di prova accende un modulo dal sito e il bot
lo vede senza riavvio.

---

## F11 — Istanza NSFW

**Serve dall'owner:** creare l'applicazione NSFW e mettere `NSFW_TOKEN`
nel `.env`.

**Dipende da:** F7, F8, F10 (verifica dell'identità sul pannello).

- [ ] **NF-23** istanza NSFW (SPEC §16.10)

**Fatto quando:** nessun contenuto esce fuori da un canale NSFW (test)
e la lista vietata non si può aggirare.

---

## F12 — Motore AI (issue #50)

**Serve dall'owner:** le chiavi dei fornitori AI nel `.env`; la privacy
policy aggiornata con l'elenco dei fornitori.

**Dipende da:** F5 (privacy policy), F8, D13.

- [ ] **NF-24** motore, cache, filtri, tetto di spesa, helpdesk, riassunti, lore, immagini (SPEC §25)

**Fatto quando:** con tutti i fornitori spenti il bot risponde con la
risposta locale; il tetto di spesa di un server non viene mai superato
(test).

---

## F13 — Funzioni nuove, secondo gruppo; app utente; Desktop

**Serve dall'owner:** chiavi API facoltative (Kick, eventuali servizi a
pagamento per TikTok, Instagram, X).

**Dipende da:** F9, F10 per alcune voci (scritto in ogni scheda NF).

- [ ] **NF-16** canali contatore
- [ ] **NF-25** statistiche di attività
- [ ] **NF-26** compleanni
- [ ] **NF-27** inviti
- [ ] **NF-28** giveaway avanzati
- [ ] **NF-29** blocco totale e panic mode; doppia soglia e quarantena dell'anti-nuke → M 3.5
- [ ] **NF-30** appello per i ban normali
- [ ] **NF-31** link di phishing → M 2.8
- [ ] **NF-32** Kick, ruolo "in diretta", TikTok, Instagram, X (D14) → M 11.12
- [ ] **NF-33** ticket via DM
- [ ] **NF-34** moduli e candidature
- [ ] **NF-35** effetti sonori
- [ ] **NF-36** applicazione installabile dall'utente (SPEC §B)
- [ ] **NF-37** iYokai Desktop (SPEC §D)
- [ ] **NF-38** bot con marchio proprio
- [ ] **NF-39** modelli di server e sincronia
- [ ] **NF-40** profili, collezioni, giochi con le monete

---

## F14 — Idee rimandate di `BACKLOG.md`

**Dipende da:** bot in produzione con utenti veri.

- [ ] **NF-41** missioni, traguardi, serie, battle pass, profilo globale positivo, punteggio di rischio, carico dello staff

---

## Continuo (in ogni commit che tocca un file)

- [ ] REVIEW §9: docstring in testa ai file, formato fisso → M 14.13
- [ ] REVIEW §11: codice morto e copie (`KNOWN_UNCALLED` che si svuota)
- [ ] PERF-1, PERF-2: cache delle impostazioni e dei tempi di attesa → M 14.10
- [ ] PERF-4, PERF-6: cicli vocali e decadimenti raggruppati → M 9.18
- [ ] DB-2 (chiavi esterne) → M 14.12
- [ ] REVIEW §16: copertura dei comandi dei cog

---

## Dove sono finite le voci di REVIEW senza codice

| Paragrafo di REVIEW | Fase |
|---|---|
| §4 Moderazione, AutoMod, sicurezza | F1.e, F1.f |
| §4 Ticket, vocali, log | F1.g, F6 |
| §4 Utility | F1.c, F1.i; già fatti: import (`80322ff`, `965ab35`), ping dei promemoria (`cb05eff`), snapshot (`1098bb2`), limite di `/define-backup` (`93f7049`); pulizia dei token: F5 |
| §4 Economia e clan | F1.h |
| §4 Musica | F2 |
| §4 Fun | comandi immagine fatti (`b2303a5`); il resto in F1.d |
| §4 Core | F1.l, F1.m |
| §5 minori | F1 (a, c, d, h, i), F6; eval e shell già fatti (`8a96320`, `9e8cc1e`) |
| §10 prestazioni | PERF-5 in F1.e, PERF-3 in F5, PERF-7 in F1.l, il resto in Continuo |
| §11 codice morto e valori fissi | F1, F2, F5, F7, F9, Continuo; `PREMIUM_ALPHA_UNLOCK_ALL` già fatto (`576f155`) |
| §12 voci segnate fatte che non lo erano | SPEC corretta in F4; il codice in F1, F2, F3, F6 |
| §20 minori | fatti (vedi F0), tranne D12 in F1.i |
