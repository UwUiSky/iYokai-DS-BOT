# VERIFICA_LIVE.md — Test da fare con il bot vero

> **Nota del 04/10/2026.** Questo file ora si trova in
> `revisione/03-verifica/`. In fondo ci sono le prove dei fix della
> fase R1-bis. Le prove che riguardano il vecchio backup con il bot
> Creator sono segnate "non eseguibile": si rifanno alla fine della
> fase F3 (vedi `../archivio/PRIORITA.md`).

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
- [ ] SEC-3, BUG-21, SEC-19 (#8) — commit 4d5e4a4, poi 8590e89 — passi:
  con OAUTH2_CLIENT_ID/SECRET/REDIRECT_URI e OAUTH_ENCRYPTION_KEY veri,
  un server "main" e uno "backup" collegati, e uno snapshot con almeno
  due utenti senza token salvato (A e B):
  1. `/restore-users` nel server di backup, verso l'ID del main: A e B
     ricevono un DM con il link. Il testo dice che il link è personale
     e vale **7 giorni**.
  2. A clicca il suo link e autorizza: entra nel server di backup e
     riceve il ruolo verificato, se configurato.
  3. A riclicca lo stesso link: errore "link non valido, scaduto o già
     usato", nessuna azione ripetuta.
  4. B apre il link **di A** (copiato a mano): deve essere rifiutato,
     perché il link è legato al destinatario.
  5. Clicca un link dopo più di 10 minuti (ma entro 7 giorni): deve
     funzionare ancora.
  6. Con un utente segnato "bannato, in blacklist" nel restore: anche
     con un link valido non entra e resta in blacklist.
  Risultato atteso: un link vale una volta, solo per il suo
  destinatario, per 7 giorni. Un errore temporaneo di Discord non
  brucia il link (si può riprovare).
  **Nota:** finché non c'è il backup nuovo (D8, fase F3) non esiste una
  coppia di server su cui lanciare `/restore-users`: questa prova si fa
  alla fine di F3.
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
- [ ] SEC-12 — commit 647b680 — passi:
  1. Con un account bannato dallo spam-trap in un server di prova,
     manda un DM al bot: deve aprire il thread di appello nel canale
     di log come prima (nessuna regressione).
  2. Subito dopo, manda un secondo DM entro 30 secondi: non deve
     succedere nulla (né un nuovo thread né una risposta) — il
     limite di elaborazione lo ignora silenziosamente.
  3. Aspetta più di 30 secondi e manda un altro DM: deve tornare a
     funzionare (rifiutato dal cooldown di 24h sull'appello vero e
     proprio, che è un limite diverso e resta invariato).
  4. Con un account bannato con un `/ban` normale (non dallo
     spam-trap) in un server di prova, manda un DM al bot: non deve
     succedere nulla (non è un ban dello spam-trap, non deve aprire
     un appello).
  Risultato atteso: il flusso di appello funziona come prima per chi
  è davvero bannato dalla trappola, ma un DM ripetuto o un ban non
  legato alla trappola non fanno più lavoro — solo la prova su
  Discord vero conferma i tempi reali del cooldown.
- [ ] SEC-13 — commit 8a96320 — passi:
  1. Con `.env` senza `ENABLE_EVAL` (vuoto) e `ENVIRONMENT=production`,
     avvia il bot ed esegui `/owner eval 1+1` (o `/owner shell`,
     `/owner cog-load`) da owner: deve rispondere subito con "Questo
     comando è disattivato su questa istanza (ENABLE_EVAL=false)...",
     effimero, senza eseguire nulla.
  2. Con `.env` con `ENABLE_EVAL=true` (o `ENVIRONMENT` diverso da
     production e `ENABLE_EVAL` vuoto), stesso comando: deve mostrare
     la view di conferma come prima.
  3. Conferma un `/owner eval` che richiede più di 3 secondi (es.
     `import time; time.sleep(4)`): non deve comparire l'errore
     "This interaction failed" — la risposta finale deve arrivare
     comunque, modificando il messaggio di conferma.
  4. Esegui `/owner shell` con un comando che non termina mai (es.
     `sleep 999`) e aspetta il timeout: verifica con `ps`/`htop` sulla
     macchina che il processo `sleep` non resti vivo dopo che il bot
     ha risposto col messaggio di timeout.
  5. Controlla nel database (tabella `eval_shell_log`) che per il
     comando del punto 4 esista comunque una riga (con `success` a
     `NULL` se non hai ancora aspettato `mark_result`, altrimenti
     `false`) — prova che il tentativo è stato registrato subito,
     prima dell'esecuzione.
  Risultato atteso: `ENABLE_EVAL` blocca davvero i tre comandi quando
  spento; la conferma non scade più su esecuzioni lunghe; un comando
  shell appeso non lascia processi orfani — solo la prova su Discord
  vero e sulla macchina reale conferma questi tre punti.
- [ ] SEC-14 — commit 0e9eb3b — passi:
  1. Avvia il bot con `.env` di default (`WEB_BIND_HOST=127.0.0.1`,
     nessun webhook custom ancora creato): con `netstat -tlnp` (o
     `ss -tlnp`) sulla macchina, verifica che NON ci sia nulla in
     ascolto sulla porta `ALERTS_WEBHOOK_PORT` (8421) — il server
     webhook non deve partire senza webhook configurati.
  2. Con le credenziali OAuth2 configurate (`OAUTH2_CLIENT_ID/SECRET/
     REDIRECT_URI`, `OAUTH_ENCRYPTION_KEY`), verifica invece che la
     porta `RESTORE_WEB_PORT` (8420) sia in ascolto solo su
     `127.0.0.1` (`curl http://127.0.0.1:8420/oauth/callback` risponde,
     `curl http://<ip-esterno-della-macchina>:8420/oauth/callback` no).
  3. Con `OAUTH_ENCRYPTION_KEY` vuota, riavvia il bot e controlla i
     log all'avvio: deve comparire un WARNING (non un INFO) che dice
     che il server callback restore è disattivato.
  4. Su un server di prova, esegui `/alerts webhook-create`: la
     risposta deve avvisare che il server webhook non è ancora attivo
     e serve un riavvio (è il primo webhook dell'istanza). Riavvia il
     bot e verifica con `netstat`/`curl` che la porta 8421 sia ora in
     ascolto e che una POST a `/webhook/<token>` pubblichi nel canale
     come previsto.
  5. Manda più di 10 richieste POST allo stesso `/webhook/<token>` in
     meno di un minuto (es. con un piccolo script o `for i in
     {1..12}; do curl -s -o /dev/null -w "%{http_code}\n" -X POST
     -H "Content-Type: application/json" -d '{"message":"test"}'
     http://127.0.0.1:8421/webhook/<token>; done`): le prime 10
     devono rispondere 200, le successive 429, senza pubblicare altri
     messaggi nel canale.
  Risultato atteso: nessuna delle due porte resta esposta su tutte le
  interfacce di rete per default; il server webhook non occupa una
  porta finché nessuno lo usa; un token non può inondare il canale di
  destinazione oltre il limite — solo la prova su una macchina reale
  (con `netstat`/`curl` veri) conferma che i server ascoltano dove e
  quando devono.
- [ ] SEC-15 — commit bf2a772 — passi:
  1. Sulla macchina reale (non nel sandbox di sviluppo), in un
     ambiente virtuale pulito: `pip install -r requirements.lock` e
     verifica che finisca senza errori di conflitto tra pacchetti.
  2. Avvia il bot (`python main.py`) e verifica che parta come prima
     (nessuna regressione da `structlog` rimosso o da `aiohttp`
     aggiornato — i due server web di SEC-14, il feed watcher e i
     comandi che usano aiohttp sotto banco devono continuare a
     funzionare).
  Risultato atteso: l'installazione da `requirements.lock` è
  riproducibile sulla macchina reale (non solo nel sandbox dove è
  stato generato) e il bot si avvia e funziona come prima.
- [ ] #41 — commit 576f155 — passi:
  1. Con `.env` con `ENVIRONMENT=production` e
     `PREMIUM_ALPHA_UNLOCK_ALL` vuoto, avvia il bot: nei log non deve
     comparire il WARNING di PREMIUM_ALPHA_UNLOCK_ALL (è spento di
     default). Verifica anche a comando (es. `/premium status` su un
     server senza whitelist/boost) che le feature premium NON siano
     sbloccate.
  2. Con `.env` con `ENVIRONMENT=production` e
     `PREMIUM_ALPHA_UNLOCK_ALL=true` (forzato esplicitamente), avvia
     il bot: nei log deve comparire il WARNING che lo segnala.
  Risultato atteso: in produzione le feature premium non sono più
  sbloccate per tutti "per dimenticanza" — solo la prova su Discord
  vero con un server senza whitelist/boost conferma che il
  comportamento a comando corrisponde al valore di configurazione.
- [ ] DB-1/#25 — commit 659d9fa — passi:
  1. Su un database che rappresenta la produzione (dump reale o
     un'istanza avviata almeno una volta con lo schema vecchio, PRIMA
     di questo commit): avvia il bot con il codice di questo commit e
     controlla i log all'avvio — deve applicare `schema_migrations`
     (nuova tabella) e poi `core/migrations/0001_db2_indici.sql` senza
     errori. Verifica con `psql`: `SELECT * FROM schema_migrations;`
     deve contenere la riga `version = 1`.
  2. Con `psql` sullo stesso database, verifica che gli indici vecchi
     siano spariti e i nuovi presenti:
     `SELECT indexname FROM pg_indexes WHERE tablename IN ('event_log',
     'clans', 'leveling_totals');` — non deve comparire
     `idx_event_log_guild_role` né `idx_event_log_guild_case`; devono
     comparire `idx_clans_unofficialized_deadline` e
     `idx_leveling_totals_weekly_decay_due`.
  3. Riavvia il bot una seconda volta sullo stesso database (migrazione
     già applicata): nei log NON deve comparire nessun errore "relation
     already exists" o simile — la migrazione deve risultare già fatta
     e essere saltata in silenzio.
  4. Con `EXPLAIN ANALYZE` sulla query reale usata da
     `core/guild_clan_expiry_worker.py` (`SELECT ... FROM clans WHERE
     officialized = false AND officialize_deadline <= now()`) e da
     `core/weekly_personal_decay_worker.py` (`SELECT ... FROM
     leveling_totals WHERE coins_total > 1 AND
     last_weekly_decay_period IS DISTINCT FROM $1`) sul database di
     produzione (con dati veri, non vuoto): verifica che il piano usi i
     due nuovi indici parziali (`Index Scan` su
     `idx_clans_unofficialized_deadline`/
     `idx_leveling_totals_weekly_decay_due`) invece di un `Seq Scan`
     sull'intera tabella.
  5. Se possibile, avvia il bot su due processi/macchine
     contemporaneamente puntati allo stesso database (simulando un
     doppio avvio accidentale): nei log di uno dei due deve comparire
     un'attesa sul lock (o comunque nessun errore di doppia
     applicazione), e `schema_migrations` deve avere una sola riga per
     `version = 1` alla fine, non due tentativi falliti a metà.
  Risultato atteso: la migrazione numerata si applica una volta sola
  su un database vero, è sicura da rieseguire ad ogni riavvio, non
  lascia schema a metà in caso di errore, e i due nuovi indici sono
  davvero usati dalle query orarie che dovevano velocizzare — solo la
  prova su un database con dati reali (via `EXPLAIN ANALYZE`) conferma
  che l'indice viene scelto dal query planner, non solo che esiste.
- [ ] BUG-1/#2/#42 — commit 6c724d3 — passi:
  1. Su un server Discord di prova, apri un ticket e usa `/ticket
     close`: deve rispondere subito "Ticket chiuso. Questo canale
     verrà eliminato tra 10 secondi." senza errori (prima: crash
     immediato con TypeError, visibile nei log come interazione
     fallita).
  2. Aspetta i 10 secondi reali e controlla che il canale sparisca
     davvero da Discord (prima restava lì per sempre, anche col
     ticket già "closed" nel database).
  3. Ripeti con `/ticket forceclose` (che non ha mai avuto questo bug,
     nessun ritardo): verifica che il canale sparisca subito, senza
     regressioni.
  4. (Sostituito dalla voce BUG-30 più sotto: l'eliminazione ora
     passa dallo scheduler e sopravvive a un riavvio.)
  Risultato atteso: `/ticket close` non va più in crash e il canale
  viene davvero eliminato dopo 10 secondi — solo la prova su Discord
  vero conferma che l'eliminazione arriva a buon fine (i test usano un
  `fake_text_channel()`, non un canale Discord reale).
- [ ] BUG-2/#4/#38/#43/#49 — commit c9534fb — passi:
  1. Su un server di prova esegui `/setup` senza categoria: deve mostrare l'elenco di sola lettura con lo stato di tutti i moduli.
  2. Esegui `/setup categoria:Utility`, cambia la selezione e premi Salva: lo stato deve cambiare davvero (controlla con `/setup` senza categoria).
  3. Ripeti per ogni categoria: nessun errore e nessuna categoria troncata.
  Risultato atteso: nessun "interazione fallita" e nessun rifiuto; solo Discord vero lo conferma.
- [ ] BUG-6 — commit 071504a — passi:
  1. Su un server di prova: `/setup` attiva un modulo, poi `/config reset`, poi `/config history` e `/config rollback` sulla voce del reset: moduli, impostazioni e lingua devono tornare come prima.
  2. Cambia la lingua con `/config language`, poi rollback di quella voce: `/config language` deve mostrare di nuovo la lingua precedente.
  3. Imposta per la prima volta `/ticket-support-role add`, poi rollback: `/ticket-support-role list` deve funzionare senza errori (niente null).
  Risultato atteso: ogni "✅ Rollback eseguito" corrisponde a un ripristino reale.
- [ ] /config import (validazione) — commit 80322ff — passi:
  1. Esporta con `/config export`, importa lo stesso file: deve riuscire.
  2. Modifica il file a mano (es. `"tickets": "si"` o `"language": "xx"`) e importalo: deve rispondere con un ❌ chiaro e non cambiare nulla (controlla con `/config export`).
  Risultato atteso: nessun dato sbagliato viene scritto.
- [ ] BUG-7/#12/#28 — commit 8a218d1 — passi:
  1. Metti un token musicale sbagliato in `.env` (es. `MUSIC_TOKEN_3`) e avvia il bot: nei log deve comparire un ERROR per 'Music worker 3', il bot principale e gli altri devono restare online e l'owner deve ricevere un DM.
  2. Con tutti i token giusti, ferma il bot con Ctrl+C (o `kill -TERM`): nei log deve comparire "Arresto richiesto", poi "Database disconnesso. Arresto completato." senza warning di sessioni aiohttp non chiuse.
  3. Metti un token sbagliato per il bot principale: il processo deve uscire con errore (codice diverso da 0).
  Risultato atteso: un bot secondario non ne spegne altri; lo spegnimento è pulito. Solo l'avvio con i token veri lo conferma.
- [ ] BUG-8/#13 — commit 9683b36 — passi:
  1. Al primo avvio con il codice nuovo controlla nei log che la migrazione `0002_scheduled_actions_failed` si applichi senza errori (`SELECT * FROM schema_migrations;`).
  2. Sul database di produzione: `SELECT id, action_type, failed_reason FROM scheduled_actions WHERE failed_reason IS NOT NULL;` — eventuali righe sono azioni di tipo non più registrato, da esaminare.
  3. Crea un promemoria con `/remind` a 1 minuto e verifica che arrivi (lo scheduler gira ancora dopo il nuovo codice).
  Risultato atteso: lo scheduler continua a girare e non rilegge azioni orfane ad ogni giro.
- [ ] BUG-9 — commit 376ff6b — passi:
  1. Avvia il bot, fai partire `/play` in un canale vocale, poi riavvia il processo senza fermare la musica.
  2. Dopo il riavvio lancia di nuovo `/play` nello stesso server: deve partire e non rispondere che i bot musicali sono occupati.
  3. Controlla con `SELECT * FROM music_sessions;` che dopo l'avvio sia vuota.
  Risultato atteso: nessun worker resta bloccato dopo un riavvio.
- [ ] LC-8 — commit 45d2a78 — passi:
  1. Avvia il bot con almeno due server e lascialo girare un giro dei worker (retention, soundboard, XP vocale): nei log non devono comparire errori inattesi.
  2. Se compare un errore "…: errore su <id>, passo al successivo", verifica che gli altri server abbiano comunque completato il giro (es. XP vocale accreditata).
  Risultato atteso: nessun server blocca gli altri; la prova vera richiede server reali.
- [ ] BUG-3/#26 — commit 3547e4c — **non eseguibile oggi** (il flusso con il Creator non esiste più: si riprova a fine F3) — passi:
  1. Lancia un backup completo (`/backup`), autorizza iYokai Main nel server creato e attendi la fine del job.
  2. `SELECT * FROM backup_pairs;`: deve esserci la riga con `main_guild_id` = il tuo server e `backup_guild_id` = il nuovo server.
  3. Nel server backup, `/promuovi-backup` non deve più rispondere "non registrato"; dopo una settimana (o forzando il worker) lo snapshot utenti deve partire.
  Risultato atteso: la coppia viene registrata a fine backup. Solo un backup vero su Discord lo conferma.

- [ ] BUG-4/#21 — commit b6eeb81 — **non eseguibile oggi** (il flusso con il Creator non esiste più: si riprova a fine F3) — passi:
  1. Fai fallire un backup (es. rimuovi iYokai Main prima della clonazione) oppure lascia scadere un job.
  2. Controlla in Discord che il server creato da iYokai Creator sia sparito e che gli slot (max 10) siano tornati liberi.
  3. Riavvia il bot: eventuali server del Creator più vecchi di un'ora e non legati a una coppia devono essere cancellati.
  Risultato atteso: nessun server orfano resta nel Creator. Solo Discord reale lo conferma.

- [ ] Snapshot settimanale — commit 1098bb2 — **non eseguibile oggi** (il flusso con il Creator non esiste più: si riprova a fine F3) — passi:
  1. Con un backup attivo, riavvia il bot e controlla nel log "Snapshot settimanale completato" con un numero di utenti > 0.
  2. `SELECT count(*) FROM backup_user_snapshots;` per il tuo server.
  Risultato atteso: lo snapshot del primo giro contiene i membri reali.

- [ ] §12 11.5–11.7 limiti emoji/sticker/suoni — commit e502c1f — **non eseguibile oggi** (il flusso con il Creator non esiste più: si riprova a fine F3) — passi:
  1. Fai un backup di un server con più di 50 emoji (o più di 5 sticker / 8 suoni).
  2. Il backup deve completarsi; nel log compare "saltati N emoji, N sticker, N suoni".
  Risultato atteso: il backup non fallisce per i limiti. Solo Discord reale lo conferma.

## Fase R1-bis (fix del 04/10/2026)

- [ ] D9 intent `message_content` (#6, #36, #39, #44) — commit 783329e — passi:
  1. Nel Developer Portal attiva "Message Content Intent" per il bot
     principale, poi avvia il bot: deve collegarsi. (Senza
     l'interruttore il bot non si collega.)
  2. Nel log di avvio la riga degli intent deve contenere
     `message_content`.
  3. Attiva `/automod anti-caps` e scrivi un messaggio tutto in
     maiuscolo: il filtro deve scattare.
  4. Apri un ticket, scrivi due messaggi, chiudilo: il transcript deve
     contenere il testo.
  Risultato atteso: il bot legge il contenuto dei messaggi.
- [ ] BUG-19 — commit fba882e, b0d5302 — passi:
  1. Avvia il bot e leggi il log: nessun `RuntimeError` dai worker.
  2. Con un token sbagliato per un bot secondario: il bot principale
     resta acceso e il log non mostra `RuntimeError`.
  3. Dopo 10 minuti controlla che i feed siano stati letti almeno una
     volta (un feed di prova pubblica un elemento nuovo).
  Risultato atteso: i lavori periodici partono tutti dopo il login.
  La parte "il job di `/define-backup` esce da `pending`" non è più
  eseguibile (D8).
- [ ] BUG-20 — commit c5ebd0f — passi:
  1. `/alerts add` con `http://x:99999/`: deve rifiutare subito.
  2. Con due feed validi attivi, aspetta un giro (5 minuti): entrambi
     vengono letti.
  Risultato atteso: un indirizzo sbagliato non ferma i feed degli altri
  server.
- [ ] SEC-18 e test SSRF — commit 6509fec, 307941e — passi:
  1. `/alerts add` con `http://127.0.0.1:8420/` e con
     `http://169.254.169.254/`: rifiutati.
  2. `/alerts add` con un feed vero (es. un feed Reddit): accettato e
     pubblicato al giro dopo.
  Risultato atteso: nessun indirizzo interno viene letto; i feed veri
  funzionano ancora.
- [ ] Feed con codifica dichiarata — commit d6bda5e — passi:
  1. Segui un feed in ISO-8859-1 con lettere accentate nel titolo.
  Risultato atteso: gli accenti escono giusti ("Città", non "Citt�").
- [ ] Ruolo verificato del restore — commit 67e5771 — passi:
  1. Dai al ruolo verificato il permesso Amministratore, poi fai
     rientrare un utente con il restore.
  Risultato atteso: l'utente entra ma il ruolo **non** viene dato, e il
  riepilogo lo dice. (Eseguibile a fine F3.)
- [ ] BUG-33 — commit eceedc8 — passi:
  1. Manda 12 richieste al minuto allo stesso `/webhook/<token>` per 5
     minuti.
  Risultato atteso: ogni minuto 10 accettate e 2 rifiutate con 429. Mai
  un blocco permanente.
- [ ] SEC-22 — commit 690a5b6 — passi:
  1. Con un mirror attivo, scrivi `@everyone` nel server principale.
  Risultato atteso: nel server di backup il testo compare ma nessuno
  viene pingato. (Eseguibile a fine F3.)
- [ ] BUG-22, BUG-24 — commit ea2e897, 77e0fe1, 263fdf2 — passi:
  1. Fatti bannare dalla trappola, poi `/unban`, rientra, fatti bannare
     di nuovo.
  2. Scrivi al bot in DM due volte entro 10 secondi, poi una volta dopo
     30 secondi: il terzo messaggio deve aprire **un solo** thread di
     appello.
  3. Dopo `/unban` scrivi ancora in DM: nessuna risposta.
  4. Con ban della trappola su due server: il bot chiede "quale
     server?"; la risposta viene accettata anche se arriva entro 30
     secondi.
  Risultato atteso: l'appello si apre sempre, una volta sola.
- [ ] BUG-25 — commit 3046fda — passi:
  1. Su un server già configurato: `/spamtrap-setup staff_role_add:@ruolo`.
  Risultato atteso: nessun canale nuovo; i canali di prima restano
  attivi.
- [ ] SEC-21 — commit 7b96e8c — passi:
  1. Metti un utente di prova in blacklist.
  2. Fallo entrare nel canale generatore dei vocali: nessun canale
     creato.
  3. Tienilo in un vocale di clan: l'XP di clan non sale.
  4. `/assegna-lobby` con lui in vocale: viene saltato e la cassa non
     paga la sua quota. `/assegna-winner` su di lui: rifiutato.
  Risultato atteso: la blacklist ferma anche questi tre punti.
- [ ] SEC-20 — commit b2303a5 — passi:
  1. `/fun blur` con una foto da 7 MB: compare "sta pensando", poi il
     risultato.
  2. Un file da 9 MB: rifiutato subito.
  3. Un PNG 5000×5000: "Non sono riuscito a elaborare".
  4. Durante una raffica di `/fun`, scrivi nella trappola con un altro
     account: il ban non deve ritardare.
  Risultato atteso: nessun picco di memoria, nessuna interazione
  scaduta.
- [ ] BUG-23 — commit 9e8cc1e — passi (Windows e Linux):
  1. Imposta per la prova `SHELL_TIMEOUT_SECONDS` a 5.
  2. `/owner shell` con `ping -n 60 127.0.0.1` (Windows) oppure
     `sleep 60 | cat` (Linux).
  Risultato atteso: risposta dopo circa 5 secondi; in Gestione attività
  o con `ps` non resta nessun processo. Il ramo Windows non è mai stato
  eseguito nei test: questa è la sua prima prova.
- [ ] Ruoli clan (SEC-17) — commit 42f227d — passi:
  1. Dai al ruolo "Admin Clan" il permesso Amministratore, poi promuovi
     un membro di un clan.
  Risultato atteso: il ruolo non viene dato e nel log c'è un avviso.
- [ ] BUG-30 — commit 10d16f1 — passi:
  1. `/ticket close`, poi riavvia il bot entro 5 secondi: il canale
     sparisce entro un minuto dal riavvio.
  2. Segna a mano un ticket come `closed` nel database, poi
     `/ticket forceclose` nel suo canale: il canale viene eliminato.
  Risultato atteso: nessun canale ticket resta per sempre.
- [ ] BUG-27 — commit cf6eea0 — passi:
  1. Al primo avvio controlla che la migrazione `0003` sia applicata
     (`SELECT * FROM schema_migrations;`).
  2. Inserisci in `scheduled_actions` una riga scaduta con un
     `action_type` sconosciuto.
  Risultato atteso: `attempts` e `next_attempt_at` crescono a ogni
  tentativo; dopo 8 tentativi la riga diventa `failed`.
- [ ] BUG-31, BUG-32 — commit 965ab35, c2a9582 — passi:
  1. Controlla che la migrazione `0004` sia applicata.
  2. `/config export`, poi `/config import` dello stesso file, poi
     `/config rollback <id>`: il bottone Conferma compare e funziona.
  3. `/config history limit:25`: l'elenco compare.
  4. Importa un file con `"ticket_support_role_ids": null`: rifiutato
     con un messaggio chiaro.
  Risultato atteso: nessun messaggio troppo lungo, nessun valore
  sbagliato salvato.
- [ ] Migrazioni (DB-1, DB-2) — commit 5fa15fb, d17f071 — passi:
  1. Avvia il bot sul database reale: nessun errore di migrazione.
  2. `EXPLAIN ANALYZE` sulla query del decadimento settimanale: il
     piano usa l'indice `idx_leveling_totals_weekly_decay_due`.
  Risultato atteso: migrazioni applicate una volta sola, indice usato.
- [ ] `ENVIRONMENT` obbligatoria (SEC-13) — commit 2596734 — passi:
  1. `ENVIRONMENT=prod` nel `.env`: il bot rifiuta di partire e dice
     quali valori accetta.
  2. `ENVIRONMENT=development`: parte, con un avviso nel log se eval è
     acceso.
  Risultato atteso: solo `development` o `production`.
- [ ] Flotta musicale (worker non partito) — commit b1452be — passi:
  1. Con un token musicale sbagliato, lancia `/play` da admin con gli
     altri worker occupati.
  Risultato atteso: messaggio chiaro, nessun errore nel log.
- [ ] Spegnimento (BUG-7) — commit 44ede43 — passi:
  1. `kill -TERM` due volte a un secondo di distanza.
  Risultato atteso: il log finisce con "Arresto completato".
- [ ] Sicurezza F1 (#133, unione `Unione di fix/f1-133`) — passi:
  1. Anti-nuke con soglia canali a 2: cancella 3 canali di fila → tornano tutti, nella stessa categoria. Cancella un ruolo con membri in posizione alta → torna con posizione e membri. Cancella un forum con tag → tornano anche i tag.
  2. Raid (più di 10 ingressi in 60 s) con canale allarmi: un solo messaggio, aggiornato. Nessun DM di benvenuto agli entrati durante il raid (il canale di benvenuto sì).
  3. Server con "Quarantined" fatto a mano: dopo un raid viene adottato e i canali negano scrittura, thread, reazioni, voce e connessione.
  4. `/automod anti-link-domain` oltre 100 domini per lista: messaggio chiaro.
  5. Riavvio: pannello di verifica e reazioni ancora funzionanti.
  Risultato atteso: nessun errore nel log.
- [ ] Clan e config F1 (#135, #136) — passi:
  1. `/clan boost gilda` e `individuale` con due clic quasi insieme: un solo pagamento, l'altro riceve "già attivo" (vedi la voce #146).
  2. `/clan tesoreria dona`: saldo tesoreria e registro coerenti.
  3. `/clan promuovi` ad Admin/Mod con la gilda già al tetto: rifiuto chiaro.
  4. `/config export` su server con impostazioni vuote, poi `/config import` del file: nessun errore.
  Risultato atteso: nessuna moneta persa o doppia.
- [ ] Vocali, ticket e log avanzati F1 (#134) — passi:
  1. Nel tuo vocale temporaneo imposta su @everyone un permesso extra (es. "Parla" negato), poi `/voice lock` e `/voice unlock`: "Parla" resta negato in entrambi i casi, cambia solo "Connetti".
  2. `/voice kick` di un utente che non è nel canale: messaggio "non è nel canale", nessuna espulsione. Con un utente nel canale: espulso.
  3. `/ticket support-role remove` su un ruolo impostato con `/ticket-setup`: ruolo tolto, la chiave sparisce (`/config history` la mostra rimossa).
  4. `/owner premium` rende premium "Logging Avanzato"; su un server non sbloccato con il modulo acceso, modifica un ruolo o entra in un vocale: nessun log (entro un minuto dal cambio). Con whitelist o boost: i log riprendono (entro un minuto).
  Risultato atteso: nessun errore nel log.
- [ ] Boost del clan per tipo (#146, D23, migrazione 0020) — passi:
  1. `/clan boost individuale` mostra l'opzione `tipo` con 3 scelte (exp, coin, super); stessa cosa per `/clan boost gilda`.
  2. Compra `coin` poi `exp`: entrambi riescono (2 addebiti). Con `coin` attivo prova `coin` e `super`: "Hai già il boost coin attivo fino a ...: puoi comprare solo il boost exp", nessun addebito.
  3. Con `super` attivo: ogni tipo rifiutato con "non puoi comprare altri boost finché non scade".
  4. Due clic quasi insieme sullo stesso tipo: un solo addebito.
  5. Boost che c'era prima dell'aggiornamento: ora vale come super fino alla stessa scadenza.
  6. In vocale con soli exp attivo: XP della gilda raddoppiati, coin della tesoreria no (e viceversa con coin). `/clan info` elenca i boost di gilda attivi per tipo.
  Risultato atteso: nessun errore nel log, nessuna coin persa o doppia.
