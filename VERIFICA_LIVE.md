# VERIFICA_LIVE.md — Test da fare con il bot vero

Qui finiscono i fix che i test automatici non possono certificare
(servono Discord, il database reale o Lavalink). Li esegue l'owner sul
suo PC con il `.env` locale, seguendo `CLAUDE_MANDATORY_TEST_RULES.md`.

**Mai** scrivere qui token, password, `DATABASE_URL` o log che li
contengono.

## Preparazione (una volta)

- Server Discord di test con il bot invitato e con ruoli sopra e sotto
  quello del bot.
- Un secondo account Discord **senza** permessi, per le prove negative.
- `.env` locale compilato da `.env.example`, con `DATABASE_URL` di Aiven
  (`sslmode=require`).
- Per la musica: Lavalink in locale (`deploy/lavalink/`, quando esiste).

## Voci da verificare

Formato: `- [ ] CODICE (#issue) — commit SHA — passi — risultato atteso`.
Quando l'owner ha provato: `[x]` con data ed esito, poi l'issue si può
chiudere.

- [ ] SEC-4/SEC-17 (#10, #14, #29, #32) — commit 599a2d4 — passi:
  1. Crea un ruolo con permesso `Amministratore` e prova a impostarlo
     con `/level-roles add`, `/shop add-item`, `/rolemenu add-option`,
     `/verify setup`, `/voicetemp-platform-setup`: ognuno deve
     rifiutare con un messaggio che nomina il permesso pericoloso.
  2. Configura un ruolo-premio "innocuo" (nessun permesso pericoloso,
     sotto il ruolo del bot) con `/level-roles add`, poi sali di
     livello nel server di test: il ruolo deve arrivare da solo.
  3. Dopo il punto 2, aggiungi `Amministratore` al ruolo-premio già
     configurato (dal pannello ruoli di Discord) e sali di un altro
     livello: stavolta il ruolo NON deve essere assegnato (ricontrollo
     al momento dell'assegnazione, non solo alla configurazione).
  4. Stesso schema del punto 3 per `/verify` (verifica un secondo
     account dopo aver reso pericoloso il ruolo verificato) e per un
     role menu in modalità bottone/select/reazione (clicca dopo aver
     reso pericoloso il ruolo dell'opzione).
  Risultato atteso: nei punti 1 e 3-4 nessun ruolo pericoloso viene
  mai assegnato; nel punto 2 il ruolo innocuo arriva normalmente.
- [ ] SEC-3 (#8) — commit 4d5e4a4 — passi: con
  OAUTH2_CLIENT_ID/SECRET/REDIRECT_URI e OAUTH_ENCRYPTION_KEY veri
  configurati, un server "main" e uno "backup" collegati
  (/define-main, /define-backup), e almeno uno snapshot con un
  utente senza token salvato:
  1. `/restore-users` nel server di backup, verso l'ID del main:
     l'utente riceve un DM con il link di autorizzazione.
  2. Cliccando il link e autorizzando su Discord, l'utente viene
     aggiunto al server di backup (e riceve il ruolo di verifica se
     configurato).
  3. Ricliccando LO STESSO link una seconda volta: la pagina deve
     mostrare l'errore "link non valido, scaduto o già usato",
     nessuna azione ripetuta.
  4. Aspettando più di 10 minuti prima di cliccare il link: stesso
     errore di link scaduto.
  Risultato atteso: il restore funziona una volta sola per link, con
  scadenza reale a 10 minuti — nessuna delle due condizioni è
  verificabile con i soli test automatici (serve il tempo reale che
  passa e la vera autorizzazione OAuth2 di Discord).
- [ ] SEC-5 (#7) — commit bde6f00 — passi:
  1. Con un account admin (ma non owner del bot) su un server
     qualsiasi, prova `/nonstop-main add-track`, `add-local`,
     `remove-track`, `list-tracks`, `start`, `stop`: ognuno deve
     rifiutare con "riservato al proprietario del bot" senza
     eseguire nulla.
  2. Con l'account owner, verifica che tutti e 6 i sottocomandi
     funzionino normalmente (nessuna regressione).
  3. Con l'account owner, prova `/nonstop-main add-local` con un nome
     file tipo `../../.env` o `..\..\.env`: deve rifiutare con "Nome
     file non valido" e non deve leggere/aggiungere nulla fuori dalla
     cartella configurata.
  Risultato atteso: la playlist condivisa resta modificabile solo dal
  proprietario del bot, su qualunque server; il path traversal in
  add-local è bloccato anche con un vero filesystem (non solo con
  `pathlib` simulato nei test).
- [ ] SEC-8b (#11) — commit e24059f — passi:
  1. Con un secondo account che ha "Gestisci messaggi" (o un ruolo
     sopra quello del bot), scrivi nel canale trappola: non deve
     scattare nessun ban, nessun DM, nessuna riga in #spam-log.
  2. Configura un ruolo con `/spamtrap-setup staff_role_add:@ruolo`,
     assegnalo a un account senza altri permessi speciali, fallo
     scrivere nella trappola: stesso risultato del punto 1.
  3. Con un account senza permessi/ruoli esentati, scrivi nella
     trappola: il ban scatta come prima (nessuna regressione).
  4. Apri un thread di appello (o riusa uno esistente) e prova a
     cliccare Unban/Reject/Reply con un account SENZA "Bannare i
     membri": deve arrivare il rifiuto effimero, nessuna azione
     eseguita. Con un account che ha il permesso, i bottoni
     funzionano come prima.
  Risultato atteso: lo staff non viene mai bannato dalla propria
  trappola, e solo chi può bannare può decidere l'esito di un appeal.
- [ ] SEC-10 (#20) — commit 9d52a82 — passi:
  1. Metti un account di prova in blacklist globale con
     `/owner blacklist-user add`. Con quell'account, prova ad
     aprire un ticket, cliccare "Verificati", cliccare un bottone di
     un role menu, e cliccare "Partecipa" a un giveaway: ognuno deve
     rifiutare (per i bottoni, con un messaggio effimero "Sei stato
     bloccato dall'uso di questo bot."; per i menu/modali la stessa
     risposta), nessuna azione eseguita.
  2. Con lo stesso account in blacklist, reagisci con l'emoji giusta
     a un pannello di verifica in modalità reaction e a un role menu
     in modalità reaction: nessun ruolo assegnato, nessuna verifica
     completata (nessuna risposta visibile, è un secondo livello di
     difesa silenzioso).
  3. Con lo stesso account, scrivi qualche messaggio in un canale con
     la leveling attiva e resta in vocale per un paio di minuti:
     `/rank` deve mostrare XP e coin invariati.
  4. Rimuovi l'account dalla blacklist e ripeti i punti 1-3: tutto
     deve tornare a funzionare normalmente (nessuna regressione).
  Risultato atteso: un utente in blacklist globale non ottiene più
  nulla dal bot — né tramite interazioni (bottoni/menu/modali) né
  tramite i listener che assegnano XP, ruoli o verifica fuori da
  un'interazione.
- [ ] SEC-11 — commit ac11f7a — passi:
  1. Genera un PNG con dimensioni enormi ma tinta unita (es. con
     Pillow: `Image.new("RGB", (10000, 10000), (10, 20, 30)).save
     ("bomba.png")` — pochi KB su disco) e allegalo a `/fun grayscale`
     (o invert/blur/pixelate/meme): deve rispondere che non è stato
     possibile elaborare l'immagine, senza errori e senza un picco di
     RAM del processo visibile (`htop`/`docker stats` durante la
     prova).
  2. Stesso file allegato a un messaggio nel canale trappola
     anti-spam (o come avatar di un account di prova che ci scrive):
     il transcript generato deve saltare la thumbnail di quell'
     allegato senza fallire l'intero report.
  3. Con un'immagine normale (una foto qualsiasi), verifica che tutti
     i comandi `/fun` di manipolazione immagine e il transcript della
     trappola continuino a funzionare come prima (nessuna
     regressione).
  Risultato atteso: un'immagine "bomba" non fa mai allocare al
  processo la RAM per i suoi pixel decompressi — solo i test
  automatici possono simulare le dimensioni dichiarate, non l'effetto
  reale su un processo Discord con limiti di memoria veri (Oracle
  Free Tier).
