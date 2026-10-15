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
- [ ] Vocali temporanei (#144) — passi:
  1. Da proprietario non staff di un vocale temporaneo, `/voice kick` su un admin e su un moderatore: rifiutato con messaggio chiaro; su un membro normale: espulso.
  2. Imposta a mano `Connetti = consentito` per @everyone su un vocale temporaneo, `/voice lock` poi `/voice unlock`: torna `consentito`, gli altri permessi non cambiano.
  Risultato atteso: nessun permesso perso.
- [ ] Ordine dei comandi (D24) — passi:
  1. Scrivi `/` nel server di prova e guarda l'ordine dei comandi di iYokai (anche aprendo solo l'icona dell'app).
  2. Segna dove stanno `/cerca-comando` e `/chiedi` rispetto agli altri.
  Risultato atteso: i due sono i primi. Se no, annota come Discord ordina (nome? uso?) e si cambiano i nomi in `core/command_groups.py`.
- [ ] Ordine per nome e posto dell'app (D24, prove del 06/10) — passi:
  1. `python3 scripts/prova_ordine_comandi.py registra` (server di prova, con `YOKAI_BOT_TOKEN` e `PROVA_GUILD_ID` nel tuo `.env`).
  2. Scrivi `/` e clicca l'icona di iYokai: annota l'ordine dei comandi `_prova`, `-prova`, `ʼprova`, `0prova`, `1prova`, `aprova`, `mprova`, `zprova` (da telefono e da PC).
  3. `python3 scripts/prova_ordine_comandi.py rimuovi`.
  4. Dal Developer Portal rinomina per un minuto l'app (es. `AAA iYokai` o `1 iYokai`), poi guarda se cambia il posto di iYokai tra le app nel selettore (accanto al bot che comincia per M), e rimetti il nome.
  Risultato atteso: si capisce se simboli e numeri vengono prima delle lettere e se il nome dell'app decide il posto. Scrivi i risultati nella issue.
- [ ] Avvisi feed, Twitch e YouTube (#67, voci 11.1-11.9, migrazione 0023) — passi:
  1. YouTube live (serve `YOUTUBE_API_KEY`): `/moduli alert youtube-live` su un canale che sta facendo una diretta; entro 5 minuti arriva l'avviso. Poi la diretta finisce: arriva l'avviso di fine. Sulla Google Cloud Console la quota usata sale di 1 unità per giro, non di 100 per canale.
  2. 304 reale con ETag: `/moduli alert feed` su un feed vero che manda `ETag` (es. un RSS di Reddit o di un blog); nel log di debug del server o con un proxy si vede il secondo giro rispondere 304. Quando esce un contenuto nuovo, arriva un solo messaggio.
  3. Twitch oltre 20 stream: segui più di 20 streamer che sono live insieme; tutti ricevono l'avviso (prima ne arrivavano solo 20).
  4. 26º feed rifiutato: con 25 feed attivi, il 26º dà "ha già 25 feed"; `/moduli alert elenco` resta leggibile e mostra sempre gli ID.
  5. Modulo spento: `/admin setup` disattiva `feed_alerts`; nessun messaggio da feed, Twitch o YouTube, e nessuna quota YouTube consumata. Riattivalo: riprendono.
  Risultato atteso: nessun errore nel log, nessun avviso doppio.

## Sicurezza — passaggio `feat/sicurezza-audit` (#59, #117)

Prima: server di test con il bot (premium acceso per anti-nuke, anti-raid, heatmap, ban globale), tre account: **P** (proprietario), **A** (amministratore, non fidato), **U** (utente semplice). Il ruolo del bot deve stare sotto quello di P e sopra a quelli di A e U. Dettaglio dei file in `AUDIT_SICUREZZA.md`. Commit: anti-nuke `8895c79`, anti-raid `e684371`, score/heatmap/ban globale `ccdc53b`, spam-trap/verify/inviti `012e083`.

- [ ] SIC-001, SIC-002, SIC-017 (#117) — commit 8895c79 — passi:
  1. Come P: `/security antinuke enable true`; `/security antinuke limits category:Canali max_actions:50 seconds:60 max_per_hour:3`.
  2. Come A (con Gestisci canali): crea e cancella 2 canali di prova nell'arco di qualche minuto (meno di 50 al minuto). Ogni creazione e ogni cancellazione contano: sono 4 azioni, più di 3 in un'ora.
  3. Come P: `/security antinuke status` e `/security antinuke casi`.
  4. Come P: `/security antinuke rilascia caso:1`.
  Risultato atteso: al **secondo** canale (alla quarta azione) A perde i ruoli e riceve "Quarantined" (resta nel server, non scrive); il proprietario riceve il DM "Anti-Nuke — channel (caso #1)"; `casi` elenca il caso, `casi numero:1` mostra i ruoli tolti; `rilascia` rimette i ruoli e toglie la quarantena; un secondo `rilascia caso:1` dice "già rilasciato".
- [ ] SIC-018 (#117) — commit 8895c79 — passi: come A: `/security antinuke trusted-add user_id:<id di A>`; poi `/security antinuke enable false`; poi come P: `/security antinuke trusted-add user_id:<id di A> livello:Extra owner`; poi come A: `/security antinuke trusted-add user_id:<id di U>`, e `... livello:Extra owner` per U. Risultato atteso: A viene rifiutato ai primi due ("Solo il proprietario…"); P nomina A extra owner; A aggiunge U come fidato ma non come extra owner; `trusted-list` mostra tutto.
- [ ] SIC-019, SIC-020 (#117) — commit 8895c79 — passi: 1) Come P: crea la categoria "Ticket"; `/security antinuke trusted-add user_id:<id di un bot di prova> azione:Canali categoria_canali:Ticket`. Il bot di prova (o A, con la stessa voce) crea e cancella 6 canali **dentro** Ticket: nessuna punizione. Poi 6 canali fuori da Ticket: punizione. 2) Crea un webhook in un canale, copia il suo ID e fai `trusted-add user_id:<id webhook> tipo:Webhook`; con `limits category:Webhook max_actions:0` crea e cancella quel webhook come A: nessuna punizione; con un altro webhook sì. Risultato atteso: come descritto; `trusted-list` mostra categoria e webhook.
- [ ] SIC-005, SIC-006, SIC-008 (#117) — commit 8895c79 — passi: come P: `/security antinuke guardie permessi_ruoli:Ogni ruolo ruoli_ai_membri:Sì`. Come A: dai `Amministratore` a un ruolo di prova; poi dai a U un ruolo che ha già `Gestisci ruoli`. Poi come P: `trusted-add` per A e ripeti. Risultato atteso: prima volta il permesso torna com'era (log in `casi`, avviso al proprietario) e il ruolo viene tolto a U; dopo `trusted-add` A non viene fermato. Con modalità "Solo @everyone e ruoli di quasi tutti" un ruolo piccolo non viene toccato, `@everyone` sì.
- [ ] SIC-007 (#117) — commit 8895c79 — passi: `limits category:Permessi dei canali max_actions:2 seconds:60`; come A modifica i permessi di 3 canali di fila. Risultato atteso: al terzo A viene punito e i permessi dei 3 canali tornano come prima (se il recupero è attivo).
- [ ] SIC-009 (#117) — commit 8895c79 — passi: serve un server con link personalizzato (livello boost 3). `guardie link_personalizzato:Sì`; come A cambia il link in Impostazioni → Panoramica. Risultato atteso: il caso dice se il link è stato ripristinato; **se la chiamata `PATCH /guilds/{id}/vanity-url` è rifiutata ai bot**, il caso dice "ripristino fallito… rimettilo a mano" (annota l'esito vero qui: è l'unica parte non verificabile senza Discord).
- [ ] SIC-010 (#117) — commit 8895c79 — passi: server con almeno 5 membri inattivi da 7 giorni; `limits category:Ban/Kick max_actions:3 seconds:60`; come A: Impostazioni → Pulizia membri (prune). Risultato atteso: A punito, caso "pulizia (prune) di N membri"; senza prune, le uscite volontarie non contano.
- [ ] SIC-025 (#117) — commit 8895c79 — passi: `guardie aggiunta_bot:Sì`; come A invita un bot qualsiasi; poi come P (o un fidato) lo stesso. Risultato atteso: il bot di A viene espulso e c'è il caso; quello di P resta.
- [ ] SIC-003, SIC-004, SIC-022 (#117) — commit e684371 — passi: 1) `/antiraid enable true` (deve segnalare se il ruolo del bot è troppo in basso: prova prima con il bot sotto un ruolo Amministratore); `join-rate max_joins:2 seconds:60`; 3 account nuovi entrano → "Quarantined". 2) `/antiraid quarantine-hold true`; come A togli "Quarantined" a uno di loro da Discord: deve tornare e arrivare l'avviso; dai a uno di loro un altro ruolo: deve sparire. 3) Come A dai `Amministratore` al ruolo "Quarantined": torna senza permessi. 4) `/antiraid rilascia member:<uno di loro>`: esce dalla quarantena. 5) `/antiraid status` mostra canale allarmi, ruolo e blocco. Risultato atteso: come descritto; dopo `rilascia` il blocco non lo rimette.
- [ ] Punteggio e heatmap (#59, #117) — commit ccdc53b — passi: 1) In un server **senza** 2FA richiesta per lo staff: `/security score` deve dire "Attiva l'autenticazione a due fattori…" (prima non lo diceva mai); attivala da Discord e riprova. 2) Metti un ruolo del bot troppo in basso o togli "Gestisci ruoli": il punteggio cala di 10 e il consiglio lo spiega. 3) Dai `Amministratore` a `@everyone`: `/security heatmap` lo mostra per primo con ⚠️. 4) Dai a 8 utenti di fila un ruolo con `Gestisci ruoli`: il proprietario riceve 5 DM e poi uno solo "troppi ruoli…". Risultato atteso: come descritto.
- [ ] SIC-044, SIC-046 e revoca (#117) — commit ccdc53b, `012e083` — passi: tre server di test S1, S2, S3, tutti con il bot e `/security globalban enable`. 1) S3: `enable invia:No ricevi:Sì`. 2) In S1 un account di prova scrive nel canale trappola: viene bannato in S1 e in S2, **non** in S3 se S3 ha `ricevi:No`, e viene bannato in S3 con `ricevi:Sì`. 3) In S2: `/security globalban controlla utente:<account>` → "bannato … da 1 server" senza nomi. 4) In S1 l'account scrive in DM al bot, lo staff preme **Unban** nel thread dell'appello: l'account viene sbannato in S1 **e** negli altri server, tranne dove il ban è stato messo a mano. Risultato atteso: come descritto; `status` mostra le due direzioni.
- [ ] Spam-trap (#59) — commit `012e083` — passi: 1) `/security spamtrap trap_channel:#a log_channel:#a` → rifiutato ("due canali diversi"). 2) Senza canali: `/security spamtrap` crea trappola e log; il log è visibile al bot anche se il suo ruolo non ha permessi di canale; se manca Bannare membri/Crea thread privati la risposta lo dice. 3) Un account di prova incolla 5 messaggi in 1 secondo nella trappola: **un solo** DM, un solo caso, un solo messaggio nel log. 4) Un account con 100+ messaggi nei canali: il ban parte entro pochi secondi e il transcript dice "N older messages are not included". Risultato atteso: come descritto.
- [ ] Verify e inviti (#59, #60) — commit `012e083` — passi: 1) `/security verify blacklist-add member:<id di un utente uscito dal server>` (prima non si poteva: serviva un membro). 2) Clic sul pannello dopo aver già il ruolo: risposta "You are already verified", nessuna nuova riga nel log. 3) Modalità reaction con il bot senza "Aggiungi reazioni": il pannello esce e un messaggio spiega di aggiungere la reazione a mano. 4) Spegni il modulo Verify (`/admin setup`) e prova `/security verify panel`: rifiutato. 5) Crea e cancella un invito con spam-trap attivo: nessun errore nei log del bot. Risultato atteso: come descritto.

### Dopo la revisione (cacciatore e revisore) — stesso ramo

- [ ] Solo chi gestisce (#117) — passi: come A (amministratore, non fidato, non extra owner): `/security antinuke limits category:Canali max_actions:1000 seconds:3600`, `/security antinuke punish-action`, `/security antinuke recovery enabled:No`, `/antiraid quarantine-hold enabled:Sì`. Poi come P gli stessi. Risultato atteso: A rifiutato quattro volte ("Solo il proprietario e gli extra owner…") e le impostazioni non cambiano; P le cambia. Con il blocco acceso anche `/antiraid rilascia member:<qualcuno>` è rifiutato ad A. Come P nomina A extra owner: ora A può farle; con un secondo extra owner B, A non può `trusted-add user_id:<B>` (né declassarlo né sostituirlo).
- [ ] Una punizione per attacco (#117) — passi: `punish-action Quarantena`, `limits category:Canali max_actions:2 seconds:60`; come A cancella 10 canali di fila. Risultato atteso: **un solo** caso, **un solo** DM al proprietario e **un solo** avviso nel canale degli allarmi, anche se A continua; `casi` elenca un caso. Se mentre l'attacco dura qualcuno ridà un ruolo ad A, l'evento dopo lo ferma di nuovo **senza** aprire un secondo caso (il caso elenca anche i ruoli ritolti).
- [ ] Rilascio per caso (#117) — passi: A subisce due attacchi distinti (caso 1 sui canali, caso 2 sui ruoli, a distanza di più di un'ora e senza rilasciare); `/security antinuke rilascia caso:1`. Risultato atteso: A riprende **solo** i ruoli del caso 1 e **resta in quarantena** ("ha altri casi attivi (#2)"); `rilascia caso:2` lo libera del tutto. `/antiraid rilascia member:<A con un caso attivo>` risponde "resta in quarantena: ha casi anti-nuke attivi". Dopo il rilascio una sola azione sotto soglia non punisce (i contatori ripartono da zero).
- [ ] Quarantena che non toglie i poteri (#117) — passi: sposta il ruolo del bot **sotto** il ruolo Amministratore di A; `punish-action Quarantena`; come A cancella 4 canali. Risultato atteso: avviso e `casi numero:N` dicono "ha il ruolo di quarantena ma i suoi ruoli NON sono stati tolti: l'autore è ancora potente", non "messo in quarantena".
- [ ] Ruolo di quarantena all'attivazione (#117) — passi: server senza ruolo "Quarantined"; `/antiraid enable true` e `/security antinuke enable true`. Risultato atteso: subito dopo c'è **un solo** ruolo "Quarantined", senza permessi, con scrittura, reazioni e voce negate su tutti i canali. Se ne crei uno a mano con `Amministratore` e rifai `enable`, il bot gli toglie i permessi.
- [ ] Recupero di un attacco lento (#117) — passi: `limits category:Canali max_actions:100 seconds:60 max_per_hour:3`; come A cancella 1 canale ogni 10 minuti. Risultato atteso: alla quarta cancellazione A è punito e **tutti e 4** i canali vengono ricreati (prima solo quelli dell'ultimo minuto).
- [ ] Ban globale: revoca e staff (#117) — passi: S1, S2, S3 in rete. 1) Un account di prova **amministratore in S3** scrive nella trappola di S1: bannato in S1 e S2, **non** in S3. 2) Togli al bot in S2 il permesso Bannare membri e premi **Unban** nell'appello: S1 sbannato, S2 resta bannato; ridai il permesso e rifai la revoca (rimetti il ban e premi di nuovo): S2 viene sbannato. 3) Fai bannare lo stesso account anche dalla trappola di S2: l'appello in S1 **non** lo toglie da dove S2 lo ha bannato. 4) `/modban unban` in S1: oltre al messaggio normale arriva "Il ban era arrivato anche ad altri server della rete: tolto da N". Risultato atteso: come descritto.
- [ ] Verify con captcha (#59) — passi: `/security verify setup` con captcha attivo; da verificato premi di nuovo il pannello. Risultato atteso: "You are already verified" **subito**, senza la finestra del captcha.

- [ ] Utilità: sticky, benvenuto, programmati, promemoria (#66, voci 10.2-10.6, migrazione 0027) — passi:
  1. Sticky: `/admin messaggi sticky-set` in un canale (con un ruolo che nomina `<@&ruolo>` nel testo); fai scrivere 10 messaggi veloci a due account: resta un solo sticky in fondo. Poi togli al bot "Invia messaggi" nel canale: nessun errore a ogni messaggio (solo un avviso nel log).
  2. Ping D12: da un account SENZA "Menziona tutti" imposta sticky/benvenuto/messaggio programmato con `<@&ruolo> @everyone`: il ruolo e @everyone non suonano. Rifai da un account CON il permesso: il ruolo suona, `@everyone` mai.
  3. Benvenuto: `/gestione benvenuto benvenuto message:` con `{server}` e un testo lungo 1990 caratteri su un server dal nome lungo: rifiutato con il numero di caratteri. `/gestione benvenuto benvenuto` senza `dm`: il DM già attivo resta attivo. `/gestione benvenuto anteprima` non va in errore.
  4. Un bot che entra o esce: nessun benvenuto né addio.
  5. `/admin messaggi programma` con canale che poi cancelli (o permesso tolto): all'ora fissata chi l'ha programmato riceve un DM che dice che non è partito. Elenco dei programmati con molti messaggi lunghi: non va in errore.
  6. Promemoria con DM chiusi e `@everyone` nel testo: nel canale di ripiego suona solo chi l'ha impostato.
  7. Un moderatore con solo "Gestisci server" cambia canale o stato del benvenuto senza riscrivere il testo: il ping di ruolo scelto da un admin non si spegne.
  8. Togli lo sticky mentre il canale è attivo: nessun messaggio dello sticky resta nel canale.
  Risultato atteso: nessun messaggio perso in silenzio, nessun ping non voluto.
- [ ] Menu dei ruoli (#66, voce 10.7) — passi:
  1. `/gestione ruoli menu-aggiungi` con emoji `ciao`: rifiutata. Con un'emoji personalizzata di un altro server dove il bot non c'è: rifiutata.
  2. Menu a bottoni con 25 ruoli e etichette di 80 caratteri: il messaggio si pubblica (l'elenco va su più campi).
  3. Cancella a mano il messaggio del menu e aggiungi un'opzione: il menu viene ripubblicato.
  4. Togli all'ultimo ruolo: il menu e il messaggio spariscono e il bot lo dice.
  5. Menu a reazioni: aggiungi un'opzione con un'emoji che Discord rifiuta: l'embed del menu non cambia. Due `/gestione ruoli menu-aggiungi` lanciati insieme: entrambe le opzioni nel menu, un solo messaggio.
  6. Menu a bottoni creato con `toggle: no`: cliccare di nuovo non toglie il ruolo.
  Risultato atteso: mai "Opzione aggiunta" se il messaggio non è cambiato.
- [ ] Suggerimenti e richieste (#66, voce 10.9) — passi:
  1. Due account dello staff cliccano insieme Approva e Rifiuta su un suggerimento: una sola decisione, l'altro legge "già deciso".
  2. `/utility suggest` con un testo da 2000 caratteri: pubblicato; con il canale senza permessi: "il suggerimento non è stato inviato" e nessuna riga resta in sospeso.
  3. Stessa prova a due clic su una richiesta di `/utility richiedi-comando`.
  Risultato atteso: un solo esito, un solo DM al richiedente.
- [ ] Pannello e liste dell'owner (#66, voce 10.12) — passi (serve `/owner`, server owner):
  1. `/owner premium list`, `/owner premium whitelist-list`, `/owner premium subscriptions`, `/owner premium status-all`, `/owner blacklist utente-list`, `/owner blacklist server-list` con tanti elementi: risposta a pagine con Indietro/Avanti.
  2. `/owner premium panel` con più di 25 moduli premium-capable: tendina da 25 e pagine.
  3. `/owner system eval` con un testo da 4001 caratteri: Discord lo rifiuta.
  Risultato atteso: mai un errore generico "L'applicazione non ha risposto".
- [ ] `modules_updated` (#66, voce 10.13) — passi:
  1. Con il log a livello debug, attiva un modulo dal wizard (`/admin setup wizard`), da `/admin config import`, dopo un `/admin config reset` e dopo un `/admin config rollback`.
  Risultato atteso: per ogni modulo cambiato un evento `modules_updated` (un ascoltatore di prova, o `bot.dispatch` loggato); nessun evento per quelli invariati.
- [ ] Router dei canali e log su forum (#72, NF-01, M 5.5) — passi:
  1. `/log crea-canali`: categoria `📜 Log` privata con 4 canali; `/log stato` li elenca. Un utente normale non li vede.
  2. `/log crea-forum` su un server Community: forum `log` privato. Fai un evento di ogni tipo (entra un membro, cancella un messaggio, entra in un vocale, crea un canale): compare un post per tipo, con più messaggi nello stesso post. Cancella un post a mano e rifai l'evento: ne nasce uno nuovo.
  3. `/log canale tipo:messaggi` su un canale dove il bot non può scrivere: rifiutato con i permessi che mancano. Togli il permesso al bot dopo averlo impostato e fai 3 eventi: il proprietario del server riceve un solo DM; ridai il permesso, poi toglilo di nuovo: nuovo DM.
  4. Cancella il canale dei log a mano: un solo DM al proprietario, nessun errore a ogni evento.
  Risultato atteso: mai più di un avviso per problema, nessuna riga persa nel database.
- [ ] Log dei messaggi (#73, NF-02) — passi (serve `message_content` acceso nel Portal e il Logging Avanzato sbloccato):
  1. Scrivi, modifica e cancella un messaggio: due embed (prima/dopo e cancellato) con autore e canale. Un messaggio da 3000 caratteri: embed valido.
  2. `/clear` 20 messaggi: un solo riepilogo con il file `messaggi_cancellati.txt`.
  3. `/log ignora azione:Aggiungi canale:…`, poi cancella lì: nessun log. Stessa prova con un utente e con il prefisso `!`.
  4. Cancella un messaggio vecchio (prima di un riavvio del bot): il log dice che il contenuto non c'è più.
  Risultato atteso: nessun messaggio di bot nel log, nessun testo nella tabella `event_log`.
- [ ] Log avanzati (#61, M 5.6, 5.7, 5.8) — passi:
  1. Trascina un canale sopra altri 5: un solo messaggio «Canali spostati» dopo circa 5 secondi.
  2. Entra in un vocale e muta il microfono tu: «Si è mutato da solo». Fatti mutare da un moderatore (muta server): «Mutato dal server».
  3. Aggiungi, rinomina ed elimina un suono soundboard: una riga per evento, subito (senza aspettare 5 minuti), anche il primo.
  4. Dal 16/11/2026: dai/togli al bot l'accesso a un canale: nessun log con `___hidden___`.
  Risultato atteso: nessun doppione, nessun evento saltato.
- [ ] Snipe, editsnipe e ghost ping (#74, NF-03; #61, M 5.9) — passi (serve `message_content` e il modulo `snipe` acceso):
  1. Scrivi e cancella un messaggio con un allegato: `/utility snipe` lo mostra (testo e nome del file). Dopo 5 minuti: «Nessun messaggio da mostrare».
  2. Modifica un messaggio: `/utility editsnipe` mostra prima e dopo. Un messaggio da 3000 caratteri: embed valido.
  3. Spegni il modulo: i comandi dicono che non è attivo e il bot non ricorda niente.
  4. Ghost ping: menziona un utente e cancella tu il messaggio: avviso nel canale dei log. Ripeti facendo cancellare il messaggio a un moderatore: nessun avviso. Cancella tu un secondo messaggio con menzione subito dopo che un moderatore ne ha cancellato un altro tuo: l'avviso deve comparire (il registro di Discord può unire le cancellazioni dello stesso moderatore: annota cosa succede).
  Risultato atteso: nessun testo salvato su disco, nessun avviso per le cancellazioni dei moderatori.


## Livelli ed economia — passaggio `feat/giro-eco` (#65, #86)

- [ ] `M 9.18` (#65) — passi:
  1. Entra in un canale vocale con un secondo account (due persone, nessuno assordato, non AFK) e resta 3 minuti.
  2. Controlla `/level rank` di entrambi.
  Risultato atteso: entrambi hanno XP e coin (5 XP e 2 coin al minuto di base); l'account assordato o nel canale AFK no.
- [ ] `NF-15` (#86) — passi:
  1. `/level impostazioni annuncio modo:Messaggio privato`, poi scrivi finché sali di livello.
  2. `/level impostazioni escludi canale:#test`, scrivi in #test e in un altro canale.
  3. `/level impostazioni moltiplicatore fattore:2 ruolo:@vip` e scrivi con un account con quel ruolo.
  4. `/level impostazioni premi modo:Sostituisci`, con due ruoli-premio a livelli diversi, e supera il secondo.
  Risultato atteso: il level-up arriva in DM; in #test nessun XP; con @vip gli XP del messaggio sono doppi; al secondo ruolo il primo viene tolto. `/level impostazioni mostra` riassume tutto.
- [ ] `NF-12` (#83) — passi:
  1. `/level rank` per te e per un altro membro (con avatar normale e con avatar animato).
  2. `/level rank colore:#FF8800 tema:Notte`, poi di nuovo `/level rank`; poi `/level rank reimposta:True`.
  3. `/level rank member:@altro colore:#00FF00`.
  Risultato atteso: un'immagine PNG con avatar tondo, nome (tagliato se lungo), livello, barra XP, posizione e coin; colore e tema restano salvati; il passo 3 avvisa che si cambia solo la propria card e non salva nulla. Nessun "L'applicazione non ha risposto".
- [ ] `NF-15` bis (#86) — passi:
  1. `/level impostazioni escludi canale:<una categoria>`, poi scrivi in un canale dentro la categoria e in uno fuori.
  2. Con `premi modo:Sostituisci`, metti il ruolo-premio del livello alto sopra il ruolo del bot e fai salire un membro.
  Risultato atteso: nella categoria nessun XP (né per la gilda); il membro tiene il ruolo-premio vecchio perché il nuovo non è assegnabile.
- [ ] `NF-12` bis (#83) — `/level rank` con un nome pieno di emoji: la card mostra il nome senza quadrati vuoti.


## Moderazione — passaggio `feat/giro-mod` (#138)

- [ ] `5.11` (#138) — passi:
  1. Con un secondo account: `/modban tempban member:@prova duration:2m reason:prova modo:Fuori, con invito e ruoli al rientro`.
  2. Controlla il DM ricevuto (data di fine e invito) prima che l'account sparisca dal server.
  3. Aspetta 2 minuti, entra con l'invito.
  Risultato atteso: l'invito funziona anche dopo la scadenza; l'account rientra con i ruoli di prima (non quelli sopra il bot); riga nel log di moderazione «Tempban scaduto».
- [ ] `5.12` (#138) — passi:
  1. `/modban tempban ... duration:3m modo:Isolamento` su un account con due ruoli.
  2. Controlla che veda solo #isolamento (con la data di fine), crea un canale nuovo e controlla che non lo veda.
  3. Fallo uscire e rientrare prima della fine: deve tornare isolato. Poi prova `/modban unban` con l'ID.
  Risultato atteso: ruoli tolti durante l'isolamento e ridati alla fine (o all'unban); nessun ban vero.
- [ ] `NF-30` (#101) — passi:
  1. `/modban appelli canale channel:#appelli`.
  2. Banna un secondo account con `/modban ban`: nel DM deve esserci il bottone «Fai appello».
  3. Clicca il bottone dal DM (l'account è fuori dal server), scrivi il testo, invia. Riprova subito: deve dire di attendere 24 ore.
  4. Nel canale staff usa «Rifiuta» (nessun ban tolto) su un secondo appello, poi «Accetta» su un terzo; prova anche con un account senza «Bannare membri».
  Risultato atteso: il modulo si apre anche da un account bannato (se Discord lo impedisce, annotarlo); Accetta toglie il ban e scrive all'utente; il bottone dopo un riavvio del bot funziona ancora. `/modban appelli elenco` mostra gli stati.
- [ ] `VER-014/015/016` (#118) — passi:
  1. `/security verify opzioni non_verificato:@Nuovo extra_1:@Membro`, poi fai entrare un account di prova.
  2. L'account riceve @Nuovo; clicca il pannello di verifica.
  3. Con un altro account: `/security verify manuale member:@prova`; poi `/security verify tentativi` e `statistiche`.
  Risultato atteso: alla verifica l'account perde @Nuovo e prende il ruolo di verifica più @Membro; la verifica a mano appare nei tentativi come «Verificato a mano».
- [ ] `5.12` bis (#138, giro bug) — passi:
  1. Isola un account con due ruoli (`modo:Isolamento`, 5m), poi rilancia `/modban tempban ... modo:Isolamento` sullo stesso account (3m).
  2. Aspetta la fine dei 3 minuti; poi prova lo stesso con `/modban unban` durante il secondo isolamento e con un tempban con rientro sopra l'isolamento.
  Risultato atteso: alla fine l'account riprende i DUE ruoli veri e NON resta col ruolo «Isolamento»; la scadenza dei 5 minuti non libera il secondo isolamento; dopo `unban` nessuna scadenza scatta più. Con i DM chiusi nel tempban con rientro, il moderatore riceve l'invito in un messaggio solo suo.
- [ ] `NF-30` bis (#101, giro bug) — passi:
  1. Fai appello con un account bannato e accetta dal canale staff togliendo al bot il permesso «Bannare membri» (poi riprova con il permesso).
  2. Premi «Accetta» due volte di fila, e prova a fare appello 3 volte in pochi secondi.
  Risultato atteso: senza permesso il ban resta, l'appello resta aperto e lo staff vede il motivo; col permesso il ban cade e l'appello passa ad «accettato»; un solo appello ogni 24 ore anche con clic ripetuti.
- [ ] `clear` canale (#57, giro bug) — `/mod clear amount:5 channel:#staff` da un account che non vede #staff o non ha «Gestire i messaggi» là. Risultato atteso: rifiutato, nessun messaggio cancellato.
- [ ] `VER-014` bis (#118, giro bug) — con il ruolo di verifica sopra il bot: il pannello dice di contattare lo staff e l'utente tiene @Nuovo. Con @Nuovo uguale al ruolo di verifica: l'utente resta verificato.
- [ ] `AMD-021` bis (#116, giro bug) — regola con sola azione «warn»: modifica più volte lo stesso messaggio che viola. Risultato atteso: un solo warn.
- [ ] Isolamento su server grande (#138) — su un server con molti canali, `modo:Isolamento` finisce senza «L'applicazione non ha risposto» e nasconde tutti i canali.
- [ ] Dati (NF-04, F5) — `rank_card_prefs` compare in esportazione e sparisce con la cancellazione: vedi «Core e privacy».


## Core e privacy — passaggio `feat/giro-core` (#70, #69, #145, #75, #19, #37, #46)

- [ ] `NF-04` esportazione (#75) — passi:
  1. Con un account di prova che ha XP, una rank card colorata e un `/level rank`, lancia `/utility privacy esporta`.
  2. Rilancialo subito: deve rispondere che c'è un'attesa di 60 secondi.
  Risultato atteso: un file JSON visibile solo a te, con `leveling_totals`, `rank_card_prefs`, `command_usage`; nessun token OAuth; il secondo lancio è rifiutato dal tempo di attesa.
- [ ] `NF-04` cancellazione (#37, #46) — passi:
  1. Con l'account di prova (che ha anche un avviso e un kick ricevuti): `/utility privacy cancella motivo:prova`. Ripeti: deve dire che c'è già una richiesta.
  2. Come owner: `/owner privacy richieste` (nel server dell'owner), poi `/owner privacy approva richiesta:<numero>`.
  3. Con l'account di prova: `/level rank` e `/utility privacy esporta`.
  Risultato atteso: l'owner vede la richiesta; dopo l'approvazione l'utente riceve un messaggio privato con righe cancellate, rese anonime e conservate; XP e rank card sono spariti; l'avviso è sparito; il kick resta (e il messaggio lo dice). Con i messaggi privati chiusi l'approvazione riesce lo stesso e lo dice. `/owner privacy rifiuta` con un motivo: l'utente lo legge e nulla si cancella.
- [ ] `NF-04` uscita dal server (#19, D6) — passi:
  1. Fai uscire il bot da un server di prova (o toglilo): controlla `guild_presence.left_at` valorizzato.
  2. Rientra entro pochi minuti: `left_at` torna vuoto e la configurazione del server è intatta.
  3. Per la cancellazione dopo 90 giorni: imposta a mano `left_at` a 91 giorni fa e riavvia il bot (o aspetta il giro giornaliero).
  Risultato atteso: i dati del server spariscono, restano solo ban e kick di sicurezza. Il bot non cancella mai un server in cui si trova.
- [ ] `M 13.2` blacklist (#69) — `/owner blacklist server-add` per un server dove sono presenti bot principale e almeno un worker musicale: escono tutti; il messaggio dice quanti. Reinvitare un worker in quel server: uscita all'ingresso del principale (il worker da solo non controlla ancora la blacklist: apri una issue se serve).
- [ ] `M 14.2` / `M 14.3` (#70) — passi:
  1. Con un account senza permesso lancia un comando di moderazione: messaggio chiaro, nessun «errore imprevisto» nel log del bot (solo una riga INFO).
  2. Prova un comando che fa `defer()` pubblico e poi fallisce (es. forzando un errore in sviluppo): il messaggio d'errore lo vede solo chi ha lanciato il comando e il «sta pensando» pubblico sparisce.
- [ ] `M 14.4` scheduler (#70) — pianifica un promemoria da 1 minuto e un tempban breve: eseguiti entro 30-60 secondi; con la tabella `scheduled_actions` controlla che `claimed_at` torni vuoto dopo l'esecuzione.
- [ ] `#145` premium (#145) — con il modulo Logging avanzato premium: aggiungi un server alla whitelist (`/owner premium whitelist-add`) e subito dopo genera un evento di log: il log arriva senza aspettare 60 secondi; rimuovilo dalla whitelist: smette subito.
- [ ] `#148` permessi dei gruppi per ruolo (OAuth2) — **provabile a metà**: l'indirizzo di ritorno c'è (stessa `/oauth/callback` del restore, `OAUTH2_REDIRECT_URI`) e il bottone-link sta sotto `/admin setup attiva` senza categoria; manca ancora la scelta dei ruoli (nessuno chiama `imposta_ruolo`), quindi i passi 2-4 non sono ancora provabili. (1) autorizza il bot con il bottone di `/admin setup attiva` con un admin vero e controlla la pagina «Autorizzazione salvata»; riaprire lo stesso link deve dare «già usato», e aprirlo con un altro account Discord «link per un altro account»; (2) scegli il ruolo admin: in Impostazioni → Integrazioni → iYokai → `/admin`, `/gestione`, `/moduli`, `/security`, `/automod`, `/log` compare quel ruolo; il ruolo mod su `/mod`, il ruolo ban su `/modban`; (3) un membro senza permessi né ruolo non vede i gruppi; (4) cambia ruolo: il vecchio sparisce e le regole messe a mano dall'admin restano (una regola «nega» sul ruolo scelto diventa «consenti»); (5) revoca l'app dal profilo Discord: la scelta di un ruolo continua a funzionare e il bot dimentica il token (solo con la revoca vera, non con un errore temporaneo di Discord).
- [ ] `NF-04` bis esportazione (#75) — con un account di staff che ha scritto note, casi e preso in carico ticket di altri: `/utility privacy esporta` non contiene quelle righe né gli id dello staff; `event_log` senza `details`. Su un account con più di 5000 righe in una tabella il messaggio dice quale tabella è tagliata.
- [ ] `NF-04` bis DM di esportazione e cancellazione (#37) — l'approvazione manda un messaggio privato con il rapporto: prova con DM aperti e chiusi; titolare di un clan con altri membri (il clan passa al co-titolare o al più anziano e il messaggio lo dice) e titolare da solo (il clan sparisce; il canale/categoria Discord del clan resta da togliere a mano); due utenti con un ticket aperto nello stesso server chiedono la cancellazione: entrambe riescono.
- [ ] `NF-04` bis uscita e rientro (#19, #46) — (1) fai uscire il bot da un server con almeno un ban e un `/warn`; (2) a bot spento riaggiungilo (nessun `on_guild_join`) e riavvia: `guild_presence.left_at` e `purged_at` vuoti; (3) con `left_at` a 91 giorni fa e dati nel server, fai partire il giro e riaggiungi il bot nello stesso momento: i dati restano e `left_at` è vuoto; (4) dopo una cancellazione vera, rientra e lancia `/warn`: il numero del caso continua dopo il ban trattenuto, nessun errore; (5) un tempban in corso al momento della cancellazione conserva lo sban programmato.
- [ ] `M 14.10` impostazioni in memoria (#70) — cambia con un comando una impostazione letta spesso (es. il canale di un log con `/log canale`) e subito dopo genera l'evento: arriva nel canale nuovo, non nel vecchio; due admin che cambiano la stessa impostazione insieme: l'ultimo vince e `/admin config history` mostra due voci coerenti.
- [ ] `M 14.12` chiavi esterne dei clan (#70) — sciogli un clan con membri, tesoreria e XP del mese: nessuna riga resta in `clan_members`, `clan_treasury_ledger`, `clan_monthly_xp` (controllo con una query a mano).
- [ ] Sincronizzazione comandi con i nuovi `/owner privacy` e `/utility privacy` (#75) — riavvia il bot e controlla nei log che la sync del server dell'owner riesca (nessun «max_value» rifiutato da Discord): `/owner privacy richieste|approva|rifiuta` compaiono, e `/utility privacy esporta|cancella` si vedono in un altro server. Rilancia `/utility privacy esporta` entro 60 secondi: risposta «Attendi N secondi…».
- [ ] `NF-04` ter cancellazione (#37) — l'utente ha un promemoria in coda e un tempban in corso: dopo l'approvazione il promemoria è sparito, lo sban programmato resta e il rapporto parla di «sban programmati».

**Note di rilascio (core):** la migrazione `0037` riscrive `event_log` (id a BIGINT): su una tabella con milioni di righe blocca la tabella all'avvio. Applicarla fuori orario o con il bot spento. La `0050` rifà la colonna calcolata `retain_for_security` di `moderation_cases` e l'indice dei ticket.

- [ ] `5.11` OAuth (#138) — con un account che ha autorizzato il ripristino utenti (`/admin backup restore-utenti`, token valido): `/modban tempban ... duration:2m modo:Fuori, con invito e ruoli al rientro`. Risultato atteso: alla scadenza l'account rientra da solo (nessun invito usato) con i ruoli di prima; riga di log «Rientro: Automatico». Senza autorizzazione e senza «Creare invito» il comando si ferma prima del ban.
- [ ] `5.12` ter (#138) — `/modban ban` su un account isolato, poi `/modban unban`: l'account risulta sbannato davvero. Se Discord rifiuta di nascondere qualche canale, il moderatore legge quanti.
- [ ] Dati (NF-04, F5) — quando il registro esisterà: `rank_card_prefs` deve comparire in esportazione e cancellazione.
- [ ] `M 15.1` + `M 15.2` (#71) — passi (serve `PIXABAY_API_KEY` nel `.env`):
  1. `/fun animal specie:Cane` e `/fun search-image query:gatto`.
  2. Rifai `/fun search-image query:gatto` subito: poi dopo 10 secondi, con le stesse parole.
  3. `/fun search-image` con 101 caratteri nel testo.
  Risultato atteso: nessun "L'applicazione non ha risposto"; la ricerca arriva come immagine allegata (non collegata) con la riga "Immagine da Pixabay" che apre la pagina giusta; il passo 2 subito dopo dice di aspettare; la stessa ricerca ripetuta usa la cache (nel log una sola chiamata a Pixabay); Discord rifiuta il testo oltre 100 caratteri.

### Musica F2 (#64, D10) — ramo `feat/r3-mus`

Prima: Lavalink 4.2.0 o successivo raggiungibile (`deploy/lavalink/README.md`), `LAVALINK_NODES` nel `.env` con almeno un nodo pubblico (facoltativo), i 5 token musicali, un server con tutti e 5 i bot musicali invitati. Per ogni prova guarda anche i log (righe `iyokai.music`).

- [ ] `M 8.1` audio dai worker (#64) — in un canale vocale: `/music play` con un titolo. Poi, dallo stesso server ma da un SECONDO canale vocale, un altro utente fa `/music play`. Risultato atteso: si sente la musica da ENTRAMBI i bot musicali (due bot diversi, nomi diversi nel canale), non solo dal primo. Nei log, ogni nodo ha l'identificatore `…@w1`, `…@w2`, `…@main`. Se non si sente nulla dai worker, la D10 non è risolta: riapri #64.
- [ ] `M 8.6` / `M 8.7` due canali nello stesso server (#64) — mentre suonano i due canali: `/music queue` da ciascun canale mostra la sua coda; `/music skip` dal canale A salta solo il brano di A. Un utente in un terzo canale vocale (o che sta in A ma comanda dal canale B) riceve «devi essere nel suo stesso canale» per skip, stop, pause, resume, disconnect.
- [ ] `M 8.2` nodo morto (#64) — metti in `LAVALINK_NODES` come PRIMO un indirizzo che non risponde e riavvia: il bot parte, gli altri nodi si collegano (log «non raggiungibile: scartato» solo per quello), `/music play` funziona. Spegnendo il bot, nei log non restano sessioni aperte.
- [ ] `M 8.11` versione (#64) — collega un Lavalink 4.1 (o un nodo pubblico vecchio): nei log «scartato: versione 4.1.x sotto la 4.2.0»; il bot usa gli altri nodi. `python3 scripts/check_lavalink_nodes.py` segnala lo stesso nodo.
- [ ] `M 8.4` brani locali (#64, #47) — con `deploy/lavalink/` avviato e un `.mp3` in `MAIN_RADIO_LOCAL_FOLDER`: `/owner radio add-local filename:<file>`. Risultato atteso: la traccia viene aggiunta con titolo e durata giusti (non una ricerca su YouTube). `add-local filename:../x.mp3` e `add-local filename:sub/x.mp3` → «Nome file non valido». Con Lavalink spento: messaggio chiaro, nessuna riga salvata.
- [ ] `M 8.5` radio in canale vuoto (#64) — `/owner radio start` in un canale, poi esci dal canale e aspetta oltre 5 minuti e oltre 3 brani: il bot principale resta e continua a suonare (nessun «scollegato per inattività»).
- [ ] `M 8.8` radio all'ingresso (#45) — con la playlist della radio non vuota, sposta/porta il bot principale in un canale vocale senza usare `/owner radio start` (es. dopo un riavvio con il bot ancora nel canale): la radio parte da sola, nel punto in cui si trova l'orologio condiviso (stesso punto di un altro server che ascolta). Se il canale non è raggiungibile non succede nulla e nel log c'è l'errore.
- [ ] `M 8.14` canali particolari (#64) — `/music play` da un canale palco → messaggio «canale palco»; da un canale con limite utenti pieno (bot senza «Sposta membri») → messaggio «canale pieno»; con Discord lento/bloccato → messaggio sul tempo scaduto. In tutti i casi il worker torna libero (subito un altro `/music play` altrove funziona).
- [ ] `M 8.12` / `M 8.13` worker (#64) — nei log di avvio gli intent dei 5 worker sono solo `guilds` e `voice_states`. (Il passaggio a più shard si vede solo oltre 2.500 server: nessuna prova possibile ora.)
- [ ] `M 8.15` titoli lunghi (#64) — `/music play` con un video dal titolo molto lungo, poi `/music nowplaying` e `/music queue`: nessun errore, titolo troncato con «…». `/owner radio list-tracks` con più di 80 brani: l'elenco ha i bottoni Precedente/Successiva e ogni pagina si legge.
- [ ] Catalogo MUS (#126) — `/music join` (entra senza suonare), `/music play query:… in-cima:True` (il brano è il primo in coda), `/music skipto numero:3`, `/music previous`, `/music history`, `/music queue` e il campo «Chi ha messo cosa», `/music shuffle solo-miei:True`. Risultato atteso: ognuno fa quel che dice e la coda resta coerente.
- [ ] Impostazioni musicali (#126) — `/admin musica impostazioni volume-massimo:80`, poi `/music volume set level:150` → 80. `durata-massima:5` e `/music play` di un megamix → rifiutato. `canale-vocale:#x` e `/music play` da un altro canale → rifiutato; `tutti-i-canali:True` toglie la restrizione. `resta-a-coda-finita:True`: a coda finita il bot resta oltre i 5 minuti. `/admin musica riepilogo` mostra tutto.
- [ ] Sicurezza delle ricerche (#64) — `/music play query:/etc/passwd`, `query:local:x`, `query://audio/local/x.mp3`, `query:file:x` → «ricerca non valida», nessun worker assegnato (riprova subito `/music play` con un titolo: funziona). `query:http://127.0.0.1:2333/v4/info` e `query:http://169.254.169.254/` → «Nessun risultato», nei log «URL musicale rifiutato». Un link `https://` pubblico a un `.mp3` suona.
- [ ] Worker scollegato o spostato (#64) — mentre suona un worker: un admin lo trascina in un altro canale vocale. Risultato atteso: la sessione lo segue (`/music queue` dal nuovo canale funziona). Poi lo disconnette a mano dal canale: lo slot si libera (un altro `/music play` può riusare lo stesso worker).
- [ ] Resta-a-coda-finita (#126) — `/admin musica impostazioni resta-a-coda-finita:True`; fai finire la coda e lascia il canale VUOTO: il bot esce comunque dopo qualche minuto; con almeno una persona nel canale resta oltre i 5 minuti.
- [ ] Playlist oltre la durata massima (#126) — `durata-massima:5`, poi `/music play` con una playlist che ha anche brani lunghi: entrano solo quelli corti e il messaggio dice quanti sono stati scartati; con una playlist tutta di brani lunghi: nessuna entrata del bot, messaggio sulla durata.
- [ ] `/music join` fuori dal canale permesso (#126) — `canale-vocale:#x`, poi `/music join` da un altro canale: rifiutato, nessun bot entra; da `#x` entra.

**Domanda per l'owner:** vuoi `/music remove` (e la ricerca dentro `/music queue`)? Oggi sono TOLTI perché SPEC §9.4 li dichiara permanentemente scoperti per tua richiesta esplicita. Se li vuoi, va cambiata la SPEC e il codice (rimessi in un solo commit: la logica era già scritta e provata).

**Note di rilascio (musica):** la migrazione `0060` cambia la chiave di `music_sessions` in (server, canale). Le righe vecchie si svuotano comunque all'avvio. Nodi pubblici: nel codice non ce ne sono più, vanno messi in `LAVALINK_NODES`. Variabile nuova: `LAVALINK_LOCAL_ROOT`.

### Musica — giro r6 (#90, #106, #64, #126) — ramo `feat/r6mus`

Prima: come sopra (Lavalink 4.2.0+, 5 bot musicali invitati **con il link nuovo**, che aggiunge «Usare la soundboard»), modulo musica attivo, `sources.http: true` nel Lavalink proprio. Migrazioni `0170` e `0171`.

- [ ] `M 8.16` defer (#64) — con un nodo lento (o un nodo pubblico lontano): `/music skip`, `stop`, `pause`, `resume`, `volume set|up|down`, `disconnect`. Risultato atteso: compare «sta pensando…» e poi la risposta; mai «L'applicazione non ha risposto».
- [ ] `MUS-056` bot sordo (#126) — dopo `/music play` il bot musicale nel canale ha l'icona delle cuffie barrate. La musica si sente normalmente.
- [ ] `MUS-009` allegato (#126) — `/music play allegato:<un .mp3>` → il file suona. Con un `.png` → «deve essere un file audio o video». Senza titolo né allegato → messaggio che lo chiede.
- [ ] `NF-19` canale richieste (#90) — `/admin musica canale-richieste canale:#richieste`: nel canale compare il player con 5 bottoni. Da un canale vocale scrivi un titolo in `#richieste`: il tuo messaggio sparisce, compare «➕ Aggiunta…» che sparisce dopo 15 secondi, il player mostra il brano e la coda. Allega un `.mp3`: entra in coda. Fuori dal vocale: «Entra in un canale vocale». Prova i bottoni Pausa (due volte), Salta, Mescola, Ripeti (tre volte: brano, coda, spenta), Stop: ognuno risponde solo a te e il player si aggiorna entro 5 secondi. Da un altro canale vocale i bottoni dicono «devi essere nel suo stesso canale». Riavvia il bot: i bottoni del vecchio messaggio funzionano ancora. Cancella a mano il player: al prossimo brano ne compare uno nuovo. Senza il permesso «Gestisci messaggi» il comando avvisa che i messaggi non saranno cancellati. `disattiva:True` toglie canale e player.
- [ ] `NF-19` playlist (#90) — con 3 brani in coda: `/music playlist salva nome:Prova` → «3 brani». `/music playlist elenco` la mostra con durata. In un ALTRO server: `/music playlist carica nome:Prova` (autocompletamento) → i 3 brani in coda e suonano. `esporta` → arriva un `.json`; un secondo account fa `importa file:<json> nome:Copia` e poi `carica` → suona. `elimina` la toglie. Con 25 playlist la ventiseiesima è rifiutata.
- [ ] `NF-35` effetti sonori (#106) — mentre suona la musica: `/music suono nome:` (autocompletamento con i suoni del server e di Discord). Risultato atteso: si sente il suono sopra la musica, la musica non si ferma, il bot torna «sordo» dopo qualche secondo. In un canale senza bot musicale: entra un bot libero, suona ed esce dopo circa 8 secondi (e lo slot si libera: subito dopo `/music play` funziona). Due suoni di fila → «Aspetta ancora…». Bot musicale senza «Usare la soundboard» nel canale → messaggio sul permesso.

**Note di rilascio (musica r6):** re-invitare i 5 bot musicali con il link di `/music play` (istanze esaurite) per dare «Usare la soundboard», oppure aggiungere il permesso a mano al loro ruolo. Il canale delle richieste usa l'intent «Message Content» del bot principale (già acceso).
## Backup e restore — passaggio `feat/r3-bak` (#68)

Servono: il server principale di prova, **iYokai**, **iYokai Creator** (con `YOKAI_CREATOR_TOKEN`), un secondo account admin e un account senza permessi. Un bot non può creare server: lo crea l'admin.

- [ ] `12.1` / `12.2` / `12.9` (#68) — collegamento e copia vera. Passi:
  1. Nel server principale: `/admin backup main`, poi `/admin backup crea modello:True`.
  2. Crea a mano un server nuovo (anche dal link modello). Invita iYokai e iYokai Creator con i due link. Controlla nel selettore dei permessi che compaia «Creare espressioni».
  3. Nel server nuovo: `/admin backup collega codice:<codice>`. Prima prova un codice sbagliato, poi uno già usato, poi (dopo 24 ore o con la data cambiata nel database) uno scaduto.
  4. Aspetta il DM «Backup pronto» al proprietario del server principale.
  Risultato atteso: struttura, ruoli e permessi uguali; nessun doppione se si è partiti dal modello; il Creator **resta** nel server di backup; codice sbagliato/usato/scaduto rifiutati con un messaggio; un account senza «Amministratore» rifiutato; il Creator assente nel server nuovo dà il messaggio che spiega come invitarlo.
- [ ] `12.4` (#68) — gerarchia dei ruoli. Passi: confronta l'ordine dei ruoli nei due server (il ruolo del Creator deve stare **in alto**). Risultato atteso: ordine identico; se il Creator è in basso, il riepilogo dice «Ordine dei ruoli non impostato».
- [ ] `12.5` (#68) — server principale con boost e canale vocale a 384 kbps, backup senza boost. Risultato atteso: copia riuscita, bitrate ridotto al massimo del server di backup, nessun errore.
- [ ] `12.6` (#68) — un canale con 15 webhook. Risultato atteso: nel backup 14 webhook copiati + «iYokai Mirror»; il riepilogo cita 1 webhook oltre il limite; il mirror funziona in quel canale. Rilancia la copia: nessun secondo «iYokai Mirror».
- [ ] `12.7` (#68) — un account con nome «Discord Fan» scrive nel principale. Risultato atteso: il messaggio compare nel backup con il nome «disc0rd Fan».
- [ ] `12.8` (#68) — un canale chiamato `___hidden___` (o che il bot non vede). Risultato atteso: saltato; il riepilogo dice quanti e di dare al bot il permesso di vedere tutti i canali.
- [ ] `12.13` (#68, BUG-34) — nel server di backup collegato: `/admin backup promuovi`, poi `/admin backup restore-utenti server_di_origine:<id del vecchio main>`. Risultato atteso: il restore parte (prima rifiutava); un terzo server resta rifiutato.
- [ ] `12.10` (#68) — token OAuth salvato con scadenza nel passato (database di prova, solo la data) e refresh token vero. `/admin backup restore-utenti`. Risultato atteso: l'utente viene aggiunto con il token rinnovato; con refresh token revocato riceve il DM di consenso.
- [ ] `12.11` (#68) — restore con molti utenti (30+ in snapshot, DM aperti). Risultato atteso: pausa visibile tra un DM e l'altro, nessun errore 429 non gestito, conteggi che contano solo gli esiti riusciti, un solo riepilogo finale (anche oltre i 15 minuti: finisce nel canale).
- [ ] `12.15` (#68) — metti in `OAUTH_ENCRYPTION_KEY` due chiavi separate da virgola (nuova, vecchia). Risultato atteso: i token vecchi si leggono ancora, i nuovi si scrivono con la prima; una riga rovinata a mano nel database non ferma il restore (avviso nel log, richiesta di nuovo consenso).
- [ ] `#46 D / #15` (#46) — da un terzo server: `/admin backup restore-utenti` con l'ID di un main che non ti ha come backup. Risultato atteso: rifiutato.

### Correzioni del cacciatore-bug — stesso ramo (#68)

- [ ] Permessi del Creator (#68) — nel server principale un ruolo «Mod» con «Espellere membri» e un ruolo sopra il Creator. Invita il Creator col link di `/admin backup crea` (senza Amministratore) e collega. Risultato atteso: copia finita; il riepilogo dice «Ruoli con permessi che il Creator non ha» e «Ruoli sopra quello del Creator, non aggiornati»; con Amministratore al Creator, nessuna delle due righe e permessi identici. (Non provabile senza Discord: se Discord rifiuta ancora, annotare quale permesso.)
- [ ] Collegamento (#68) — un secondo admin prova a usare il codice di un altro: rifiutato. Un server già backup di un altro main, o un main che ha già un backup: rifiutato. Due codici insieme: il secondo rifiuta finché la copia è in corso.
- [ ] Restore (#68) — lancia `/admin backup restore-utenti` due volte insieme: il secondo dice «ripristino in corso». Rilancialo dopo la fine: chi ha già ricevuto il DM (ultimi 7 giorni) è contato in «Già contattati di recente», nessun DM doppio. Un utente bannato con riga rovinata a mano non riceve nulla.
- [ ] Ingresso (#68) — fai rientrare iYokai in un server di backup in blacklist: esce. Rientro in un backup normale: nessun benvenuto, ma `left_at` azzerato.

## Utilità — passaggio `feat/r4-uti` (#66, #78–#82, #85, #87, #88, #97, #98, #105)

Servono: un server di prova con iYokai, un account admin, due account senza permessi, un secondo account per entrare e uscire.

- [ ] NF-07 (#78) — ruoli automatici. Passi: `/admin setup attiva` per «Ruoli automatici»; `/gestione ruoli auto-aggiungi ruolo:@A`, poi `... ruolo:@B ritardo_minuti:2`. Fai entrare un account nuovo. Risultato atteso: @A subito, @B dopo 2 minuti; `auto-elenco` mostra le due righe. Con un ruolo gestito da integrazione o sopra quello del bot: rifiutato con il motivo. Un bot aggiunto al server non riceve nulla.
- [ ] NF-07 (#78) — rientro. `/gestione ruoli auto-ricorda attivo:True giorni:7`. Dai due ruoli a un account, fallo uscire e rientrare. Risultato atteso: riprende i ruoli (una volta sola; un secondo rientro non li ridà). Un ruolo tolto dal server nel frattempo o salito sopra il bot viene saltato senza errore.
- [ ] NF-07 (#78) — attesa. Con le regole di Discord (Membership Screening) attive: il ruolo arriva solo dopo l'accettazione. Con `Verify` attivo: arriva solo dopo il ruolo di verificato. Durante un raid (anti-raid in allarme) i ruoli slittano di 15 minuti.
- [ ] NF-08 (#79) — starboard. Passi: attiva «Starboard» in `/admin setup attiva`; `/moduli starboard imposta canale:#bacheca soglia:2`. Con due account metti ⭐ a un messaggio di un terzo. Risultato atteso: copia in #bacheca (testo, autore, link, prima immagine); un terzo ⭐ aggiorna il numero senza duplicare; il voto dell'autore e dei bot non conta. In un canale vietato ai minori nulla, finché non si cambia. Se tolgo al bot «Incorporare link» in #bacheca, `imposta` lo dice. Il post cancellato a mano non riappare.
- [ ] NF-09 (#80) / M 10.15 — comandi personalizzati. Passi: attiva «Comandi personalizzati»; `/moduli comandi crea nome:regole testo:"Ciao {user}, {args}"`, `... crea nome:gioco testo:ok ruolo:@Giocatore azione:alterna pausa_secondi:30`; `/moduli comandi prefisso simbolo:!`. Prova `/utility tag regole argomenti:"@everyone"`, `/utility tag gioco` due volte, e scrivere `!regole ciao` nel canale. Risultato atteso: risposta con la menzione dell'autore e senza ping a @everyone; il ruolo si dà e si toglie alternando; il secondo uso entro 30 secondi dice di aspettare (col prefisso tace); l'autocompletamento di `nome` mostra al massimo 25 voci. Con un ruolo sopra quello del bot `crea` rifiuta. `prefisso` senza simbolo lo spegne. Con `message_content` spento nel portale il prefisso non parte, lo slash sì.
- [ ] NF-10 (#81) — risposte automatiche. Passi: attiva «Risposte automatiche»; `/moduli comandi risposta-crea parola:ciao risposta:"Ciao {user}!"`, poi `... parola:regole risposta:x modalita:esatta canale:#generale`. Un secondo account scrive «ciao a tutti», «ciaone», «regole» in #generale e altrove. Risultato atteso: risponde (come risposta al messaggio, senza ping) solo a «ciao» come parola intera; «regole» solo se il messaggio è esattamente quello e nel canale scelto; una seconda frase entro 10 secondi nello stesso canale non fa rispondere; un bot non fa scattare nulla. `/moduli comandi risposte` elenca i numeri, `risposta-elimina` li toglie (entro 30 secondi la cache si aggiorna; subito dopo il comando sì).
- [ ] NF-11 (#82) + RUO-018..021 (#123) — immagine di benvenuto. Passi: `/gestione benvenuto benvenuto` con testo `Ciao {user}, sei il {ordinal} (id {userid}, {displayname}, server {serverid})`; `/gestione benvenuto immagine attiva:True modello:viola titolo:"Benvenuto!"`; `anteprima welcome`; poi un secondo account entra. Prova anche `sfondo:` con un PNG da 2 MB, uno da 5 MB (rifiutato), un PDF (rifiutato), `forma_avatar:quadrato`, `colore_testo:#FF8800`, `togli_sfondo:True`. Risultato atteso: nel canale il testo con i segnaposto sostituiti e `benvenuto.png` (avatar, nome, «Membro n. …»), leggibile su ogni modello e sullo sfondo; nome con emoji senza quadrati vuoti; durante un raid (anti-raid in allarme) solo testo; con DM di benvenuto attivo il DM resta solo testo.
- [ ] NF-14 / M 10.8 (#85, #66) + RUO-050/051 (#123) — modalità dei menu di ruoli. Passi: `/gestione ruoli menu-crea` una volta per comportamento (`unique`, `verify`, `drop`, `binding`, `temp` con `durata_minuti:2`, `lock`; `reversed` solo con la modalità reazione) e `menu-aggiungi` tre ruoli; `/gestione ruoli menu-elenco` mostra gli ID. Con un account: unique = prendere un secondo ruolo toglie il primo; verify = cliccare di nuovo non toglie; drop = il bottone toglie e non dà; binding = dopo la prima scelta le altre sono rifiutate; temp = dopo 2 minuti il ruolo sparisce (controlla anche dopo un riavvio del bot); lock = tutto rifiutato; reversed = mettere la reazione toglie il ruolo, toglierla lo dà. `menu-accesso` con un ruolo ammesso e uno escluso: chi non ha l'ammesso, o ha l'escluso, riceve il rifiuto. `menu-modifica` cambia titolo/descrizione/comportamento del messaggio già pubblicato senza ripubblicarlo; se tolgo al bot il permesso di scrivere nel canale il menu resta com'era. Nota: con unique in reazione la reazione precedente resta sul messaggio (il ruolo si toglie, la reazione no).
- [ ] NF-17 (#88) — costruttore di embed. Passi: attiva «Costruttore di embed»; `/moduli embed crea nome:annuncio titolo:"Novità" descrizione:"Testo" colore:#FF8800 immagine:<https a un'immagine vera>`; `/moduli embed modifica nome:annuncio campo_nome:Quando campo_valore:Sabato campo_inline:True`; `/moduli embed pubblica nome:annuncio canale:#annunci`; poi `/moduli embed modifica nome:annuncio titolo:"Novità 2"`. Prova anche un titolo da 300 caratteri, un colore «rosso», un indirizzo `http://127.0.0.1/a.png` e `ftp://…`, 26 campi, `titolo:-` per toglierlo. Risultato atteso: anteprima privata uguale al messaggio pubblicato (immagine compresa); la modifica aggiorna il messaggio già pubblicato; i casi sbagliati sono rifiutati con il numero del limite senza salvare nulla; se cancello a mano il messaggio pubblicato, `/moduli embed modifica` lo dice e propone `/moduli embed pubblica`; nessun ping anche con @everyone nel testo.
- [ ] NF-16 (#87) — canali contatore. Passi: attiva «Contatori»; `/moduli contatori crea tipo:membri` (senza canale: il bot ne crea uno vocale chiuso a tutti), poi `tipo:boost`, `tipo:online` e `tipo:obiettivo obiettivo:100 etichetta:"🎯 {n}/{target}"`; fai entrare/uscire un account. Risultato atteso: i nomi si aggiornano entro 10 minuti dal cambio e non più spesso (nessun errore 429 nel log; due rinomine a mano in 10 minuti rendono il giro seguente «in attesa» senza bloccare il bot); `online` usa una sola richiesta per server; con «Gestire i canali» tolto al bot su un canale scelto `crea` lo dice; cancellando il canale a mano il contatore sparisce dall'elenco al giro dopo; `elimina` lascia il canale. Con più di 5 contatori `crea` rifiuta.
- [ ] NF-26 (#97) — compleanni. Passi: attiva «Compleanni»; `/moduli compleanni canale canale:#auguri` e `/moduli compleanni ruolo ruolo:@Compleanno`; due account registrano la data di oggi (UTC) con `/level compleanno imposta`; prova anche `30 2` (rifiutato) e `29 2`. Risultato atteso: entro 30 minuti un solo messaggio con entrambi i festeggiati, il ruolo a entrambi, tolto dopo 24 ore (anche dopo un riavvio del bot); nessun secondo messaggio all'avvio successivo dello stesso giorno; chi ha lasciato il server non compare; `rimuovi` cancella il dato (e `/utility privacy esporta` lo mostra prima). Il 29 febbraio in un anno non bisestile arriva il 28. Con il canale senza permessi `canale` rifiuta; se il canale diventa muto durante la giornata gli auguri si riprovano al giro dopo.
- [ ] NF-27 Inviti (#98): con il modulo `invites` attivo, entrare con un invito creato da A e controllare `/level inviti utente` di A (+1 presenti); uscire e rientrare con l'invito di B sposta il conteggio su B; `/level inviti classifica` mostra al massimo 10 righe e l'avviso sull'attribuzione. Provare 2 ingressi insieme da due inviti diversi: nessuno dei due deve essere attribuito (giusto o sconosciuto). Il bot ha bisogno di "Gestisci server".
- [ ] NF-34 (#105) — moduli e candidature. Passi: attiva «Moduli e candidature»; `/moduli candidature crea nome:staff titolo:"Candidatura staff" canale:#candidature domande:"Nome|+Perché vuoi entrare?" ruolo:@Staff`; con un secondo account `/utility modulo nome:staff` (l'autocompletamento propone `staff`), compila, invia; riprova subito. Con un account staff clicca Accetta; riavvia il bot e ripeti con una seconda candidatura cliccando Rifiuta. Risultato atteso: la finestra ha 2 campi (il secondo lungo); in #candidature arriva un embed con le risposte e i bottoni, senza ping; la seconda candidatura in attesa è rifiutata; Accetta dà @Staff, scrive in privato al candidato (se ha i DM chiusi nessun errore) e toglie i bottoni; un secondo clic dice «già decisa»; i bottoni funzionano anche dopo il riavvio; chi non ha «Gestire il server» riceve il rifiuto. Con 6 domande, o una da 46 caratteri, `crea` rifiuta; dopo 10 moduli rifiuta. Togliendo al bot il permesso di scrivere in #candidature l'utente vede l'errore e può riprovare. `elimina` toglie anche le risposte.
- [ ] Utilità, correzioni del giro bug (`feat/r4-uti`): (1) starboard: un messaggio in un canale che @everyone non vede (staff, ticket) non va in bacheca; (2) menu di ruoli `unique`/`binding`: due clic rapidissimi su due bottoni danno un solo ruolo; ruolo `temp` ripreso prima della scadenza dura per tutta la nuova durata; (3) `/utility tag` con ruolo: la risposta compare anche se Discord è lento (defer); (4) `/moduli contatori crea` su un canale che l'admin non può gestire è rifiutato; (5) un ruolo a tempo (menu o compleanno) non torna permanente dopo uscita e rientro con «ricorda ruoli»; un rientro con schermata di verifica ancora da accettare, o durante un raid, riceve i ruoli solo dopo; (6) chi esce e rientra con un altro invito è contato sul nuovo invito in `/level inviti`.
- [ ] Utilità, correzioni della revisione capo (`feat/r4-uti`): (1) starboard: un messaggio in un thread privato non va in bacheca; `/moduli starboard imposta` ha ora `nsfw` e `voto_autore`; (2) immagine di benvenuto: senza «Allega file» il testo esce lo stesso; (3) clic su un menu di ruoli con Discord lento risponde (defer); (4) `/utility tag` e risposte automatiche rifiutano parola o risposta fatte di soli spazi; (5) chi lascia il server perde il compleanno registrato.
## Livelli, economia e giochi — passaggio `feat/r4-liv` (#65, #86, #99, #111, #124, #125)

- [ ] `NF-15` ter (#86, LIV-005) — passi:
  1. `/level impostazioni xp daily:300 lavoro_min:10 lavoro_max:20 livello_massimo:3`.
  2. `/level daily` e `/level work`; poi fai salire un membro oltre il livello 3.
  3. `/level rank` di quel membro.
  Risultato atteso: daily dà 300 coin, work da 10 a 20; il membro si ferma al livello 3 senza altri annunci e la card dice «Livello massimo».
- [ ] `LIV-064..067 / LIV-041` (#124) — con due ruoli-premio (livello 5 e livello 10) e un membro al livello 10 con entrambi i ruoli:
  1. `/economia xp azione:Imposta il livello membro:@x valore:6`.
  2. `/economia xp azione:Azzera XP e livello membro:@x`.
  Risultato atteso: al passo 1 perde il ruolo del livello 10 e tiene quello del 5; al passo 2 li perde tutti. La risposta dice livello e XP prima e dopo, senza menzioni che notificano.
- [ ] `ECO-009 / ECO-011` (#125) — `/economia monete azione:Togli coin membro:@x importo:99999` su un membro con pochi coin, poi `azione:Azzera il saldo`. Risultato atteso: il saldo arriva a 0, mai negativo; `/level balance` di @x lo conferma.
- [ ] `NF-28` (#99) — passi:
  1. `/economia giveaway prize:Test duration_minutes:3 min_messaggi:3 ruolo_extra:@vip ingressi_extra:2 ruolo_bypass:@staff`.
  2. Con un account senza ruoli premi «Partecipa» subito: rifiutato (mancano i messaggi). Scrivi 3 messaggi in qualunque canale e riprova: entra.
  3. Con un account @vip: entra e il bot dice «Hai 3 ingressi». Con un account @staff: entra senza messaggi.
  4. `/economia giveaway-modello azione:Salva nome:prova premio:Test durata_minuti:2`, poi `azione:Avvia nome:prova inizia_tra:1`.
  Risultato atteso: l'annuncio elenca requisiti, ruolo che salta e ingressi extra; il programmato appare da solo dopo circa 1 minuto (al massimo 30 secondi di ritardo) con il bottone che funziona; alla fine i vincitori sono avvisati nello stesso canale (anche se è un thread o un post di forum).
- [ ] `NF-40` giochi (#111) — passi:
  1. `/fun gioca gioco:Monetina puntata:50 scelta:Testa` più volte (aspetta 5 secondi tra una e l'altra), poi `gioco:Slot puntata:10` e `gioco:Dadi`.
  2. Con meno coin della puntata; poi due volte di fila senza aspettare.
  3. `/fun misura tema:coraggio`, ripetilo (stesso numero); `/fun misura tema:<un tema sulla religione>`.
  Risultato atteso: il saldo mostrato dopo ogni partita coincide con `/level balance`; con coin insufficienti rifiuta senza togliere nulla; la seconda partita immediata dice di aspettare; la misura è stabile nel giorno; il tema vietato è rifiutato in privato.
- [ ] `NF-40` conteggio (#111) — passi:
  1. `/fun conteggio azione:Scegli il canale canale:#conta`.
  2. Con due account scrivete a turno 1, 2, 3; poi lo stesso account scrive due numeri di fila; poi un numero sbagliato; poi una frase qualsiasi.
  Risultato atteso: ✅ sui numeri giusti; ❌ e messaggio «ha rovinato tutto» sul doppio turno e sul numero sbagliato, con ripartenza da 1; le frasi non fanno nulla. `/fun conteggio azione:Stato` mostra ultimo numero e record. Dopo `Spegni` i numeri non contano più (fino a 60 secondi).
- [ ] `NF-40` profilo (#111) — passi:
  1. `/level collezione negozio`, poi `/level collezione compra oggetto:Stella` con coin sufficienti e con coin insufficienti.
  2. `/level collezione equipaggia tipo:Badge oggetto:Stella`, poi uno sfondo comprato.
  3. `/level profilo presentazione:Ciao a tutti`, poi `/level profilo membro:@altro`.
  Risultato atteso: le coin scendono del prezzo una sola volta (doppio clic rapido sul comando non paga due volte); il profilo mostra badge nel titolo, colore dello sfondo, presentazione, livello, posizione, coin e collezione; la presentazione di un altro non si può cambiare.
- [ ] `ECO-062 / ECO-064 / ECO-061 / ECO-069` (#125) — passi:
  1. `/economia shop-add name:Raro price:50 scorte:2 ruolo_richiesto:@vip`, poi `/level shop list`.
  2. Con un account senza @vip: `/level shop buy`. Con due account @vip: compra il primo, il secondo; un terzo account @vip prova dopo.
  3. `/economia shop-edit item_id:<id> price:80 scorte_illimitate:True`, poi un nuovo acquisto.
  4. `/level impostazioni negozio conferma:True`, poi `/level shop buy`: premi «Annulla», ripeti e premi «Conferma» (anche due volte di fila).
  Risultato atteso: la lista mostra «rimasti 2» e il ruolo richiesto; senza @vip rifiuta senza togliere coin; dopo due acquisti dice «esaurito» senza addebito; dopo l'edit il prezzo nuovo vale solo per gli acquisti successivi; con la conferma attiva non si paga finché non premi «Conferma», e il secondo clic dice «Già fatto». Se il ruolo-premio non si può dare, scorte e coin tornano indietro.
- [ ] `LIV-063 / LIV-074 / ECO-016` (#124, #125) — passi:
  1. `/level leaderboard metric:XP period:Di sempre posizioni:50` in un server con più di 10 membri con XP.
  2. `/level calcola livello:10`, poi `/level calcola livello:10 member:@altro`.
  3. `/level balance`.
  Risultato atteso: la classifica ha le pagine con ◀ ▶ (10 per pagina) e solo chi l'ha aperta le sfoglia; il calcolo dà XP, messaggi e minuti in vocale coerenti con `/level impostazioni mostra`; il saldo dice anche la posizione («#N in classifica»).
- [ ] `giro correzioni feat/r4-liv` (14/10) — passi:
  1. `/economia xp azione:Imposta il livello membro:@x valore:5000`: deve rifiutare (massimo 1000). Con `valore:1000` il bot risponde subito.
  2. Con un account staff che ha Gestisci server ma un ruolo basso: `/economia xp azione:Imposta il livello membro:@x valore:10` con un ruolo-premio più alto del suo: il ruolo NON arriva a @x.
  3. `/economia giveaway prize:Test duration_minutes:3 inizia_tra:1` in un canale dove il bot non può scrivere (o che poi elimini): dopo circa 1 minuto `/economia giveaway-programmati azione:Elenca` lo mostra con ⚠️ e il motivo; `azione:Annulla numero:<n>` lo toglie.
  4. `/economia giveaway-modello azione:Elenca` con molti modelli salvati: una sola risposta, mai un errore.
  5. `/fun gioca` premuto due volte in fretta: una sola partita, l'altra dice di aspettare. Con il modulo Livelli spento: rifiuta.
  6. `/level impostazioni negozio conferma:True`, `/level shop buy`, poi (altro account staff) `/economia shop-edit item_id:<id> price:<altro>`, poi «Conferma»: «Il prezzo è cambiato», nessun addebito.
  Risultato atteso: come descritto in ogni passo; nessun errore imprevisto nei log.
## Ticket, ModMail, log e vocali — passaggio `feat/r4-tkt` (#84, #104)

Servono: un server di prova con il modulo `tickets` acceso, un account staff (Manage Server), un account normale con i DM aperti e uno con i DM chiusi.

- [ ] `NF-13` (#84) — pannelli e modulo. Passi: `/admin ticket pannello-crea nome:Supporto categoria:<cat>`, `modulo-aggiungi` due volte (una lunga, una facoltativa), `pannello-crea nome:Candidature`, `pannello-pubblica pannelli:Supporto, Candidature`. Con l'account normale premi «Supporto». Risultato atteso: si apre la finestra con le domande; lasciando vuota l'obbligatoria Discord/il bot rifiuta; inviando, nasce `ticket-NNNN` con le risposte nell'embed. «Candidature» (senza domande) apre subito il ticket (ma solo uno alla volta per utente).
- [ ] `NF-13` (#84) — bottoni dopo un riavvio. Passi: riavvia il bot e premi di nuovo un bottone del messaggio già pubblicato. Risultato atteso: risponde come prima (DynamicItem).
- [ ] `NF-13` (#84) — chiusura automatica. Passi: `/admin ticket chiusura-auto pannello:Supporto minuti:5`, apri un ticket da quel pannello, scrivi un messaggio dopo 3 minuti, poi non scrivere più. Risultato atteso: dopo circa 5 minuti dal messaggio (non dall'apertura) il ticket si chiude da solo, arriva il transcript nel canale log e il canale sparisce. Il bot non tiene vivo il ticket con i propri messaggi. Riavvia il bot durante l'attesa: la chiusura avviene comunque.
- [ ] `NF-13` (#84) — voto. Passi: `/admin ticket voto pannello:Supporto attivo:True`, chiudi un ticket con `/ticket close`. Risultato atteso: DM con 5 bottoni; premendo se ne usa uno solo (un secondo clic dice «già votato»); `/gestione ticket stats` mostra il voto medio. Con i DM chiusi il ticket si chiude lo stesso, senza errori.
- [ ] `NF-13` (#84) — utente che esce. Passi: l'account normale apre un ticket da un pannello ed esce dal server. Risultato atteso: il ticket si chiude e il canale viene eliminato.
- [ ] `NF-33` (#104) — ModMail. Passi: `/admin ticket dm attivo:True categoria:<cat>`; con l'account normale (membro del server) scrivi in privato al bot. Risultato atteso: reazione ✅ al DM, risposta «Messaggio ricevuto», nuovo canale `modmail-<nome>` visibile solo allo staff con il tuo messaggio. Scrivi altri DM: vanno nello stesso canale. Un testo con `@everyone` non menziona nessuno.
- [ ] `NF-33` (#104) — risposta e chiusura. Passi: nel canale `/ticket rispondi testo:... anonimo:True`, poi `anonimo:False`; poi un messaggio normale scritto nel canale; poi `/ticket dm-chiudi motivo:risolto`. Risultato atteso: l'utente riceve «Staff di <server>» nel primo caso e il nome dello staff nel secondo; il messaggio normale NON arriva all'utente; alla chiusura l'utente riceve il motivo, il canale log riceve il transcript (con le note interne), l'utente non riceve nessun file; il canale viene eliminato dopo pochi secondi.
- [ ] `NF-33` (#104) — più server e blocco. Passi: con il bot in due server col ModMail acceso e l'account normale in entrambi, scrivi in privato. Risultato atteso: menu «In quale server vuoi scrivere?»; dopo la scelta si apre il canale in quello. `/admin ticket dm-blocca utente:<lui>`: la conversazione aperta si chiude e nuovi DM non aprono nulla. Cancella a mano un canale ModMail: l'utente può riscrivere e ne nasce uno nuovo.
- [ ] `NF-33` (#104) — convivenza con l'appello dello spam-trap. Passi: un account bannato dallo spam-trap in un server A ed ancora membro di un server B col ModMail acceso scrive in DM. Risultato atteso: non si rompe nulla; segnala se arrivano due risposte (appello e ModMail) allo stesso DM.
- [ ] `#139` (parte senza AI) — risposte standard. Passi: `/admin ticket standard pannello:Supporto attive:True`; apri un ticket da quel pannello, scrivi una richiesta lunga (es. requisiti per l'affiliazione Twitch), da staff rispondi con testo e un file allegato, poi `/ticket close`. Risultato atteso: nel canale dei log arriva «Risposta standard #N (proposta)» con testo, parole chiave, allegato ricaricato e i bottoni Approva / Modifica / Scarta. Premi Modifica, cambia le parole chiave, poi Approva. Con un altro account apri un nuovo ticket dallo stesso pannello e scrivi la stessa richiesta con parole diverse ma lo stesso tema: il bot risponde subito con la risposta e l'allegato. Prima dell'approvazione la risposta non deve mai uscire. Riavvia il bot e premi i bottoni di una proposta vecchia: funzionano.
- [ ] `#139` (parte senza AI) — sollecito. Passi: `/admin ticket sollecito pannello:Supporto minuti:2 ruolo:<ruolo>`; apri un ticket e non scrivere: dopo 2 minuti il bot chiede «Di cosa hai bisogno?». Rispondi con qualcosa che non ha risposta pronta: il bot chiama il ruolo (una volta sola). Prova anche scrivendo PRIMA del timer: allo scadere chiama subito il ruolo. Se lo staff risponde prima dei 2 minuti non deve scrivere nulla. Il timer deve funzionare dopo un riavvio.
- [ ] `LOG-009` / `LOG-007` / `LOG-008` / `LOG-013` (#119) — log di base e avanzati. Passi: con il modulo log acceso e un canale log scelto: (1) dal menu di Discord dai un timeout a un membro e poi toglilo; (2) con un account di prova cambia avatar, poi nome visualizzato, poi nome utente (Discord limita i cambi: usa un account di prova); (3) con il Logging Avanzato (premium) acceso apri un palco in un canale Stage, cambia l'argomento, chiudilo. Risultato atteso: righe «Timeout dato/tolto», «Avatar/Nome utente/Nome visualizzato cambiato» (una per server in comune col bot) e «Palco aperto/modificato/chiuso» nel canale dei log (tipo voce). Annota se `on_user_update` arriva davvero (serve l'intent dei membri) e se il cambio di avatar arriva con ritardo.
- [ ] `LOG-022` / `LOG-024` (#119) — `/log ignora ruolo:@Bot-amici` poi scrivi con un utente con quel ruolo: il messaggio cancellato non compare nel log. `/log ignora espressione:^!\w+` poi scrivi e cancella `!ping`: non compare; con `(a+)+$` il comando rifiuta e spiega perché.
- [ ] `TKT-047/048/049/056/058/069` (#120) — catalogo ticket. Passi: in un ticket `/ticket add ruolo:<ruolo>` (il ruolo vede il canale), `/ticket remove ruolo:<ruolo>`, `/ticket claim` poi `/ticket rilascia` e `/ticket passa collega:<staff>`, `/ticket transcript` (il file arriva solo a te, il ticket resta aperto), `/ticket close motivo:Risolto`. Risultato atteso: il motivo compare nel messaggio di chiusura e nel transcript; `/admin ticket chiudi-tutti` con più di 25 ticket aperti ne chiude 25 e dice quanti restano.
- [ ] `VOC-001/002/003/004/005` (#127) — vocali temporanei. Passi: A crea il vocale, B entra, A esce: B esegue `/voice claim` (diventa proprietario); `/voice lock` poi `/voice permit` a un terzo (entra comunque); `/voice deny` su chi è dentro (viene espulso e non rientra); `/voice nascondi nascosto:True` (un non presente non vede il canale); `/voice bitrate kbps:384` su un server di livello basso (rifiuto col massimo consentito).
- [ ] `ModMail` (#104) — un solo gestore per DM. Passi: un account bandito dallo Spam Trap in un server A (con bot in B col ModMail acceso, account membro di B) scrive in privato al bot. Risultato atteso: risponde solo l'appello dello Spam Trap; in B non nasce nessun canale `modmail-*`. Poi un account senza ban scrive due messaggi di fila: arrivano tutti e due, in ordine, nello stesso canale. Con un account in blacklist del bot: nessun canale.
- [ ] `ModMail` (#104) — menu e chiusura. Passi: con due server col ModMail, due DM prima di scegliere dal menu (il secondo riceve un avviso, nessuna seconda tendina); blocca l'utente nel server scelto prima del clic (nessun canale); chiudi con `/ticket dm-chiudi` su un canale con molta storia: il transcript arriva intero (nomi veri di utente e staff) e il canale sparisce dopo. Senza canale log, il comando avvisa che il transcript non è stato salvato.
- [ ] `#139` (parte senza AI) — dati personali. Passi: chiudi un ticket dove l'utente ha scritto nome, e-mail e menzioni e lo staff ha risposto con `@utente`; nella proposta nel canale dei log non devono comparire; approva e apri un altro ticket con lo stesso tema: la risposta menziona il nuovo utente. Un secondo messaggio dopo la risposta pronta (staff assente) chiama lo staff. `/privacy` (esportazione e cancellazione) tocca la riga.
- [ ] `VOC-004` (#127) — `/voice nascondi nascosto:True`: il proprietario e chi è già dentro restano nel canale e lo vedono; un altro utente non lo vede; il bot può ancora eliminarlo quando si svuota. `/voice claim` fatto da due persone insieme: una sola diventa proprietaria.
- [ ] `LOG-024` (#119) — un filtro costoso (`a?a?a?a?a?aaaaa`) viene rifiutato; una modifica da `password: x` a `ok` con `/log ignora espressione:password` non finisce nel log.
- [ ] `TKT` (#120) — due `/ticket close` insieme (due staff): un solo transcript, un solo voto in DM; un ticket classico (senza pannello) si chiude quando l'utente esce dal server; `/admin ticket chiudi-tutti` manda un avviso ogni 5 ticket e nessuna menzione.
- [ ] `NF-13` (#84) — limite per utente. Passi: `/gestione ticket limite massimo:2`; con l'account normale apri due ticket, poi tenta il terzo; poi `limite massimo:1`. Risultato atteso: il terzo è rifiutato con «Hai già 2 ticket aperti»; con 1 il messaggio è quello del singolo ticket.
- [ ] `NF-33` (#104) — conferma del primo DM e scadenza. Passi: con il ModMail acceso in un solo server scrivi al bot in privato. Risultato atteso: nessun canale finché non premi «Invia»; «Annulla» scarta il messaggio. Con due server lascia scadere il menu (10 minuti) e riscrivi: compare un menu nuovo.
- [ ] `#139` — sicurezza. Nel DM/ticket scrivi un telefono con spazi o trattini e un IBAN: non compaiono nella proposta di risposta standard. Un sollecito con ruolo `@everyone` è rifiutato e nel ticket nessuno riceve un `@everyone`.
- [ ] `NF-29` (#100) — blocco totale. Passi: in un server di prova con canali testo, voce e una categoria esclusa (`/security panico configura escludi_categoria:...`), `/mod blocco attiva`; con un account normale prova a scrivere e a entrare in voce; poi `/mod blocco togli`. Risultato atteso: scrivere e parlare bloccati, la categoria esclusa libera, livello di verifica al massimo e inviti chiusi; dopo `togli` tutto com'era (anche un canale che prima negava già Invia messaggi).
- [ ] `NF-29` (#100) — panico. Passi: `/security panico configura aggiungi_ruolo:@Staff sblocco_minuti:5 automatico:True`; `/security panico attiva`; un moderatore non fidato prova `/mod warn`; poi aspetta 5 minuti. Risultato atteso: ping a @Staff, `/mod` rifiutato al non fidato, riapertura da sola dopo 5 minuti. Poi forza un allarme anti-nuke (cancella canali sopra soglia con un account di prova): il panico parte da solo.
- [ ] `NF-29` (#100) — riavvio a metà. Passi: `/mod blocco attiva` e riavvia il bot subito; poi `/mod blocco togli`. Risultato atteso: i canali già toccati vengono riaperti.
- [ ] `NF-31` (#102) — phishing. Passi: `/automod filtri phishing enabled:True`; con un account normale scrivi `https://discord-nitro.xyz/ritira` e poi `https://discord.com/channels/1/2`. Risultato atteso: il primo è cancellato e l'autore va in timeout; il secondo resta. Con `PHISHING_LIST_URL` impostato (https) controlla nel log che il download non dia errori.
- [ ] `NF-18` (#89) — captcha a immagine. Passi: `/security verify setup method:Button verified_role:@Verificato captcha_tipo:Immagine`, pubblica il pannello, premi «Verify» con un account di prova. Risultato atteso: messaggio privato al clic con l'immagine e il bottone «Scrivi il codice»; modulo con il campo; codice giusto = ruolo; tre errori o 3 minuti = nessun ruolo e nuovo clic per un codice nuovo. Controlla che le lettere si leggano su telefono.
- [ ] `AMD-002/003/005` (#116) — `/automod filtri forma-testo max_a_capo:3 max_lunghezza:200 max_spoiler:1`: un messaggio con 6 righe, uno da 300 caratteri e uno con due `||spoiler||` vengono cancellati; `0` spegne il limite.
- [ ] `VER-029` (#118) — `/security verify opzioni log_compatto:True`: nel canale log ogni tentativo è una riga sola.

- [ ] `SIC-043` (#102) — log del phishing. Passi: `/automod filtri phishing enabled:True canale_log:#phishing`, scrivi `https://discord-nitro.xyz/ritira` con un account di prova. Risultato atteso: il messaggio sparisce e nel canale scelto compare la scheda con il link dentro il codice (non cliccabile); con un forum come canale nasce un post.
- [ ] `NF-29` (#100) — sblocco automatico a metà. Passi: `/security panico configura sblocco_minuti:1`, `/security panico attiva`; togli al bot il permesso «Gestire i canali» su un canale prima dello scadere. Risultato atteso: un solo avviso di fallimento negli allarmi; dopo aver ridato il permesso, entro un minuto il blocco si chiude da solo con un avviso di riuscita.
## Alert Kick, ruolo «in diretta» e opzioni — passaggio `feat/r5-fun` (#103, #129)

Servono: modulo avvisi acceso, `KICK_CLIENT_ID` e `KICK_CLIENT_SECRET` (e per Twitch le chiavi Twitch), un canale Kick o Twitch di prova che si può mettere in diretta, un canale di annunci, un ruolo di prova sotto il ruolo del bot.

- [ ] `NF-32` (#103) — Kick. Passi: `/moduli alert kick kick:<canale> channel:#avvisi label:Prova`; vai in diretta e poi termina. Risultato atteso: entro circa 2 minuti arriva l'avviso con il bottone «Guarda» (link a kick.com), a fine diretta arriva il messaggio di chiusura. Senza le due variabili sul bot il comando avvisa che l'avviso resta inattivo. `/moduli alert elenco` mostra `KK-N` (con «in diretta» mentre è attivo) e `/moduli alert rimuovi id:KK-N` lo toglie.
- [ ] `NF-32` (#103) — ruolo «in diretta». Passi: `/moduli alert ruolo-live ruolo:<ruolo>` (un ruolo sopra quello del bot deve essere rifiutato), poi `/moduli alert opzioni id_avviso:KK-N membro:<tu>`. Vai in diretta. Risultato atteso: ricevi il ruolo; a fine diretta lo perdi. Senza «Gestire i ruoli» il bot non fa nulla e l'avviso parte lo stesso.
- [ ] `ALR-021/025/026/027/028` (#129) — opzioni. Passi: `/moduli alert opzioni id_avviso:TW-N ruolo:<ruolo menzionabile> elimina:True fine:True annunci:True` con l'avviso in un canale di annunci. Risultato atteso: l'avviso menziona il ruolo (mai @everyone), ha il bottone «Guarda», è pubblicato nei server che seguono il canale; a fine diretta l'avviso sparisce e arriva il messaggio di chiusura senza menzione. Con un ruolo non menzionabile e un account senza «Menzionare @everyone» il riepilogo dice «non avvisato» e nessuno riceve la notifica. `azzera:True` riporta tutto ai valori di base.
- [ ] `NF-32` (#103) — `/moduli alert guida-social` mostra la guida per TikTok, Instagram e X (nessun errore, solo chi lo usa la vede).

## Core — giro r5 (#122, #77, #93, #109, #141, #69)

- [ ] `CFG-004/005` storico (#122) — passi: cambia due impostazioni con due admin diversi (es. `/log canale`), poi `/admin config history chi:@admin1`, `tipo:setting`, `dal:2026-10-01 al:2026-10-31`, `voce:<id>`, `come_csv:Sì`. Risultato atteso: l'elenco si restringe; `voce` mostra due blocchi «Prima» e «Dopo» solo a te; il CSV si apre in Excel (accenti giusti) e una voce che inizia con `=` esce con un apice davanti. Una data scritta male (`ieri`) dà un messaggio, non un errore.
- [ ] `CFG-008/009/010/018` politica dei comandi (#122) — passi (con un account senza «Gestisci server»): (1) `/utility politica comando comando:fun meme` poi prova `/fun meme`: risposta privata «spento»; rilancia con `acceso:Sì`: torna. (2) `/utility politica canali regola:solo in questo canale:#bot`: fuori da #bot i comandi sono rifiutati, dentro funzionano; un admin del server non è bloccato. (3) `/utility politica ignora utente:@prova`: il bot non risponde a @prova. (4) Prova a spegnere `admin setup`: rifiutato. (5) `/utility politica diagnosi comando:fun meme` con il modulo spento: dice il modulo da accendere. (6) `/utility politica elenco azzera:…` svuota. Controlla anche che le regole compaiano in `/admin config export` e tornino con `import`.
- [ ] `CFG-019` pulizia (#122) — cancella un canale usato come canale dei log, poi `/admin config pulizia` (solo anteprima: lista la chiave), poi `applica:Sì`; `/admin config history` mostra la modifica e `rollback` la annulla.
- [ ] `CFG-020` sincronizza (#122) — su un server che ha autorizzato i permessi dei comandi (link di `/admin setup attiva`): togli a mano un permesso di un gruppo dalle impostazioni di Discord, `/admin config sincronizza`: torna com'era. Subito dopo un secondo lancio: attesa di 5 minuti. Senza autorizzazione: il messaggio dice di usare il link.
- [ ] `CFG-021` nickname (#122) — `/admin config nickname-bot nome:Prova`: il bot cambia nome nel server; senza argomento torna normale; senza il permesso «Cambia nickname» il messaggio lo dice.
- [ ] `CFG-046` info (#122) — `/utility info`: versione (commit), latenza, numero di server, link di invito che apre la pagina giusta; con `SUPPORT_SERVER_URL` nel `.env` compare anche il link al supporto.
- [ ] `NF-22` abbonamento Discord (#93) — **serve l'app verificata e uno SKU di prova**: crea l'abbonamento di server nel Developer Portal e acquistalo (modalità test) su un server di prova; metti lo SKU in `PREMIUM_SKU_ID`. Passi: (1) con `PREMIUM_ALPHA_UNLOCK_ALL=0` e un modulo premium, il comando è bloccato; (2) dopo l'acquisto `/admin premium stato` dice «Abbonamento Discord attivo» e il comando funziona subito (evento `entitlement_create`); (3) elimina l'abbonamento: il comando si blocca di nuovo; (4) acquista mentre il bot è spento: all'avvio il log dice «Abbonamenti Discord allineati».
- [ ] `CFG-038` codici (#122) — `/owner premium grant module_name:tutti duration:Permanente` senza server: risponde con un codice `YOKAI-XXXX-XXXX-XXXX`; su un altro server `/admin premium riscatta codice:…` sblocca i moduli; il secondo uso dello stesso codice è rifiutato; 5 codici sbagliati di fila bloccano per 10 minuti. Con `module_name:<un modulo>` e `guild_id` il comando concede direttamente.
- [ ] `NF-38` marchio (#109) — **serve un'applicazione Discord di prova**: crea l'app, copia il token del bot, imposta `OAUTH_ENCRYPTION_KEY`. Passi: `/admin premium marchio azione:collega bot` → incolla il token nella finestra: il messaggio dà il link d'invito (mai il token); invita il bot; `azione:stato` dice «online»; `azione:testo di stato` cambia lo stato del bot; invitalo in un secondo server: esce da solo; `azione:spegni` lo porta offline, `accendi` lo riaccende; riavvia il bot principale: il bot del marchio torna online; con premium finito (togli la whitelist) dopo al massimo 30 minuti si ferma. **Limite noto:** i comandi rispondono ancora solo con iYokai.
- [ ] `#141` aggiornamento a caldo — con `ENABLE_HOT_PATCH=1`: (1) `/owner cog reload extension:cogs.utility.ping file:<ping.py con una riga cambiata>` → «Aggiornati 1 file», il comando cambia senza riavvio; (2) un file con errore di sintassi → «non compila», nulla cambia; (3) un cog che solleva errore all'avvio → «i file di prima sono stati rimessi» e il cog di prima funziona; (4) `commit:main` dopo aver unito un commit su `main`: aggiorna solo i file `.py` cambiati; un file di `core/` → «Serve il riavvio»; un commit non di `main` → rifiutato; (5) senza la variabile: «spento»; con un altro utente: rifiutato; (6) `registro:Sì` mostra chi, quando, file e commit. Le copie sono in `data/hot_patch/`.
- [ ] `NF-06` lingue (#77) — con Discord impostato in inglese i nomi dei comandi sono in inglese (`/admin config history`, `/utility policy`); `/utility lingua` e `/admin lingua set` cambiano la lingua delle risposte; i messaggi nuovi di questo giro (politica, premium, marchio, info) escono nella lingua scelta.

## Motore AI — giro r6 (#95, #50, #132)

Prima di tutto: nel `.env` almeno un fornitore compatibile OpenAI (`AI_FORNITORI`, `AI_URL_<NOME>`, `AI_KEY_<NOME>`, `AI_MODELLO_<NOME>`, `AI_TIPI_<NOME>`, `AI_ADDESTRA_<NOME>=no`). Per le immagini un fornitore con il tipo `immagine` e `AI_MODELLO_IMMAGINI_<NOME>`.

- [ ] Senza fornitori — togli `AI_FORNITORI`, riavvia: il bot parte; `/utility ai traduci` risponde che l'AI non è configurata; `-chiedi come si banna` dà la ricerca per parole; `/ai stato` dice «Nessuno».
- [ ] Fornitore che addestra — metti `AI_ADDESTRA_<NOME>=si`: all'avvio il log dice «Fornitore AI scartato … D19» (mai la chiave).
- [ ] Consenso — `/ai attiva acceso:Sì`: compare il testo del consenso; un altro admin non può premere il bottone; dopo «Acconsento» `/ai stato` dice «accesa». `/ai attiva acceso:No` spegne.
- [ ] `-chiedi metti in timeout Mario per 10 minuti` — risposta «Assistente» con al massimo 3 comandi cliccabili (`/mod timeout`) e i valori da mettere. Con l'AI spenta torna la ricerca per parole.
- [ ] Menzione — `/ai funzioni funzione:menzione acceso:Sì`, poi scrivi `@iYokai mi chiamo Luca`, poi `@iYokai come mi chiamo?`: risponde Luca (memoria corta); con `/ai privacy memoria_minuti:0` non lo ricorda più. Nessun @everyone nella risposta anche se lo chiedi.
- [ ] Riassunto, spiegazione, stile — `/utility ai riassumi messaggi:50` (privato); `/utility ai spiega link:<link>`; `/utility ai stile argomento:la pizza`. Con `/ai privacy livello:senza_messaggi` riassumi risponde che il server non manda messaggi all'AI e mostra i numeri del canale.
- [ ] Traduzioni — `/utility ai traduci testo:ciao lingua:en`; `/ai traduzione canale:#int lingua:en`: un messaggio in italiano riceve la risposta 🌐, uno già in inglese no; `/ai funzioni bandiere Sì` e reazione 🇫🇷 a un messaggio: traduzione che sparisce dopo 2 minuti; una seconda 🇫🇷 sullo stesso messaggio non la ripete.
- [ ] Immagini — `/utility ai immagina descrizione:un gatto samurai`: immagine con i bottoni; «Variazione» ne fa un'altra; «Ingrandisci» manda il doppio della risoluzione; un altro utente non può premere i bottoni. `/ai limiti immagini_settimana:1`: la seconda immagine è rifiutata; `/ai limiti prezzo_pacchetto:100` e `/utility ai pacchetto` scala le monete e permette altre immagini. `/utility ai ingrandisci immagine:<png>` funziona anche con l'AI spenta; un PDF è rifiutato.
- [ ] Lore e personaggi — `/ai lore tema:yokai testo:Il santuario di Kitsune`; `/utility ai lore argomento:Kitsune` usa l'ambientazione. `/utility ai crea-personaggio`, poi `/ai personaggio azione:installa nome:…`, poi `/utility ai personaggio nome:… messaggio:ciao`: risponde nel personaggio. Prima dell'installazione il personaggio non è disponibile.
- [ ] Base di conoscenza — `/ai conoscenza aggiungi` (finestra), `elenco`, `togli numero:…`; `-chiedi` usa le voci del server.
- [ ] Ticket — in un ticket aperto: l'utente usa `/ticket assistente` → risposta pubblica segnata come automatica; lo staff → bozza e smistamento visibili solo a lui. Fuori da un ticket: messaggio d'errore.
- [ ] Moderazione — `/ai moderazione canale:#generale acceso:Sì avvisi:#staff`: un insulto pesante produce una segnalazione in #staff (gravità, motivo, link); nessuna azione automatica.
- [ ] Costruisci — `/ai costruisci descrizione:community di un gioco con tornei`: anteprima di ruoli e canali; «Annulla» non crea niente; «Crea tutto» crea (togli al bot «Gestisci canali» e verifica il conteggio dei non riusciti).
- [ ] Limiti e conti — `/ai limiti utente_giorno:1`: la seconda richiesta del giorno è rifiutata; `/ai stato` mostra richieste e token del mese; l'owner vede anche tutti i server e le quote di oggi. Con `tetto_euro_cent:0` un fornitore con `AI_COSTO_<NOME>` > 0 non viene usato.
- [ ] Chiavi — metti una chiave sbagliata: entro un'ora arriva un messaggio privato all'owner con il nome del fornitore (mai la chiave); non si ripete finché non cambia qualcosa.
## Pannello web — giro r6 (#91, #93)

Servono: dominio con https e reverse proxy verso `WEB_BIND_HOST:WEB_PANEL_PORT`; nel `.env` `OAUTH2_CLIENT_ID`, `OAUTH2_CLIENT_SECRET`, `WEB_PANEL_SECRET_KEY` (32+ caratteri), `WEB_PANEL_PUBLIC_URL`; nel Developer Portal il redirect `WEB_PANEL_PUBLIC_URL/callback`. Un secondo account senza «Gestisci server».

- [ ] `24.1` accesso — senza le variabili il log dice «Pannello web spento». Con le variabili apri il sito, «Accedi con Discord»: Discord chiede solo «sapere chi sei». Tornato al sito vedi i server dove hai «Gestisci server» (o il ruolo admin del bot). Nel browser il cookie `__Host-iyokai_sessione` è HttpOnly, Secure, SameSite=Lax. Il secondo account non vede il server e `…/server/<id>` dà «Accesso negato».
- [ ] `24.1` permessi a ogni richiesta — con la pagina del server aperta togli all'account «Gestisci server»: al primo clic su «Accendi» la risposta è «Accesso negato» e niente cambia. Ridai il permesso: torna a funzionare.
- [ ] `24.3/24.4` stesse impostazioni — accendi un modulo dal pannello e usa subito un suo comando su Discord (funziona senza riavvio); `/admin config history` mostra la modifica con il tuo nome; cambia la lingua dal pannello: le risposte pubbliche cambiano lingua; scegli il ruolo admin del bot dal pannello e controlla `/admin setup attiva` (stesso ruolo).
- [ ] `D28` ruolo admin del bot — con un account che ha «Gestisci server» ma non «Amministratore»: dal pannello scegli il ruolo admin → «serve il permesso Amministratore», niente cambia; lo stesso con `/admin config import` di un file con un `admin_role_id` diverso e con `/admin config rollback` di una voce che lo rimette. Ruolo mod e ban si scelgono lo stesso. Con «Amministratore» (o da proprietario) tutto passa.
- [ ] limite per IP dietro proxy — con `WEB_PANEL_TRUSTED_PROXY=127.0.0.1` (nginx sulla stessa macchina) 11 «Accedi» in un minuto da un telefono danno «Troppi tentativi», ma un altro dispositivo entra ancora; senza la variabile il limite è uno solo per tutti (lo dice `.env.example`).
- [ ] `24.7` premium (#93) — la pagina «Premium» del server mostra le stesse righe di `/admin premium stato` e il link al negozio.
- [ ] wiki — `…/wiki` elenca i comandi, `?q=banna` trova i comandi di ban (`/modban …`); con `WIKI_BASE_URL=<WEB_PANEL_PUBLIC_URL>/wiki` il bottone «Apri nella wiki» della ricerca comandi apre la pagina del comando.
- [ ] sicurezza — `curl -I` sulla home: ci sono `Content-Security-Policy`, `Strict-Transport-Security`, `X-Frame-Options: DENY`; nei log del bot non compaiono `code` né `state` del callback; 11 «Accedi» in un minuto danno «Troppi tentativi».

## Moderazione e sicurezza — giro r6 (#115, #116, #117, #118)

- [ ] `SIC-042` phishing — `/automod filtri phishing enabled:Sì accorciatori:Sì inviti_adulti:Sì`. Un messaggio con `https://bit.ly/…` viene cancellato; con `bit.ly` nella whitelist (`anti-link-domain`) passa. Un invito a un server con livello NSFW «esplicito» o nome con «NSFW» viene cancellato; l'invito del proprio server e un invito scaduto passano. Il log va nel canale del phishing con il link non cliccabile.
- [ ] `SIC-023…028` filtri all'ingresso — `/antiraid filtro-ingresso filtro:Account troppo giovane azione:Kick messaggio_dm:"Servono 3 giorni"` con `account-age` alto: un account nuovo riceve il DM PRIMA del kick. `nomi-vietati operazione:Aggiungi schema:*free*nitro*` + filtro «Nome vietato» → timeout; un nome con `discord.gg/x` e il filtro pubblicitario → azione scelta. Invita un bot non verificato con il filtro dei bot a «Ban»: viene bannato. Nel canale degli allarmi compare «filtro all'ingresso».
- [ ] `SIC-029…035` raid — `/antiraid join-rate max_joins:2 seconds:60 conta:Solo gli account sospetti`: tre ingressi normali non fanno scattare, tre senza avatar sì. `segnali account_vicini:3 margine_minuti:10` con tre alt creati insieme (o `nomi_simili:3` con «spam1/2/3»): raid. `lockdown-action:Ban degli account del raid` + `segnali retroattivo:Sì`: bannati anche i due entrati prima. `ping-ruoli ruolo_1:@Staff`: il primo allarme pinga, gli aggiornamenti no. `/antiraid elenco ore:1` manda il file con tutti gli account.
- [ ] `SIC-037/038` — lo stesso account che entra in 4 server con iYokai in 10 minuti fa comparire «ingresso in molti server» nel canale degli allarmi (solo avviso). `/antiraid segnala nota:prova` manda un DM all'owner del bot con il file degli ultimi ingressi.
- [ ] `MOD-001…006` massa — `/modban massa ban utenti:"<@a> 123… 456…" reason:prova`: banna anche l'ID di chi non è nel server, salta chi è sopra di te con il motivo; un solo riepilogo nel mod-log, un caso per utente. `massa unban` dice «non è bannato» per chi non lo è. `/modban massa kick`, `/mod massa timeout duration:10m`, `/mod massa warn`: DM a ciascuno, caso per ciascuno.
- [ ] `VER-008…013` — `/security verify tempi promemoria_minuti:1 scadenza_minuti:3 azione_scadenza:Kick azione_fallita:Kick solo_sospetti:Sì`. Un alt nuovo entra e non si verifica: dopo 1 minuto DM di promemoria (con DM chiusi: avviso nel canale del pannello che sparisce in 15 s); dopo 3 minuti kick. Tre captcha sbagliati di fila: kick. Un account vecchio con avatar riceve subito i ruoli.
- [ ] `VER-010` — da membro non verificato `/utility verifica`: stesso percorso del bottone (modulo del captcha o ruoli subito); funziona anche con il panico attivo.
- [ ] `AMD-001…041` — `/automod filtri messaggi max_ripetuti:2 min_caratteri:3 max_link:3 finestra_link:30 max_menzioni:5 finestra_menzioni:30`: il terzo messaggio uguale, un «ok», il quarto link in 30 s e la sesta menzione su più messaggi vengono cancellati. `contenuto embed:Sì inoltrati:Sì estensioni_vietate:"exe bat"`: un inoltro con un link di phishing e un allegato `.exe` cancellati. `canale-media canale:#foto modo:Solo media`: un messaggio di solo testo sparisce. `actions-set violation:Messaggio troppo corto kick:Sì`: DM e kick.


### Dopo la revisione (cacciatore e revisore) — stesso ramo (r6)

- [ ] Tetto delle azioni in massa — **limite noto**: `/modban massa ban` e `massa kick` si possono usare 2 volte all'ora per server (l'owner del server è esente). Il conteggio vive **in memoria**: un riavvio del bot lo azzera. Passi: come moderatore (non owner) tre `massa ban` di fila: il terzo è rifiutato; come owner passa.
- [ ] `AMD-019` anteprima — `contenuto embed:Sì` e `anti-link-domain` in lista nera con un sito che ha l'anteprima: scrivi solo il link coperto (`<https://…>` no, va lasciato visibile) di un sito permesso la cui anteprima contiene il dominio vietato; l'anteprima arriva un attimo dopo e il messaggio viene cancellato. Con anti-caps e `max_lunghezza:20` attivi, un link a una pagina con titolo lungo e in maiuscolo **resta**.
- [ ] `AMD-023` solo media — in un canale `canale-media modo:Solo media` uno sticker e l'inoltro di un messaggio con un'immagine restano; un testo semplice viene cancellato.
- [ ] `VER-012` finestra — `azione_fallita:Kick`: due captcha sbagliati, poi aspetta 24 ore (o sposta l'orologio del DB di prova) e sbagliane uno: **nessun** kick. Tre errori nella stessa giornata: kick.
- [ ] Massa e gerarchia — riavvia il bot senza scaricare i membri (o usa un membro mai visto dal bot): `/modban massa ban` su un membro con un ruolo sopra il tuo viene **saltato** («sopra di te»), non bannato.
