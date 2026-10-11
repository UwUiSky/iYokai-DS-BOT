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
- [ ] SIC-003, SIC-004, SIC-022 (#117) — commit e684371 — passi: 1) `/security antiraid enable true` (deve segnalare se il ruolo del bot è troppo in basso: prova prima con il bot sotto un ruolo Amministratore); `join-rate max_joins:2 seconds:60`; 3 account nuovi entrano → "Quarantined". 2) `/security antiraid quarantine-hold true`; come A togli "Quarantined" a uno di loro da Discord: deve tornare e arrivare l'avviso; dai a uno di loro un altro ruolo: deve sparire. 3) Come A dai `Amministratore` al ruolo "Quarantined": torna senza permessi. 4) `/security antiraid rilascia member:<uno di loro>`: esce dalla quarantena. 5) `/security antiraid status` mostra canale allarmi, ruolo e blocco. Risultato atteso: come descritto; dopo `rilascia` il blocco non lo rimette.
- [ ] Punteggio e heatmap (#59, #117) — commit ccdc53b — passi: 1) In un server **senza** 2FA richiesta per lo staff: `/security score` deve dire "Attiva l'autenticazione a due fattori…" (prima non lo diceva mai); attivala da Discord e riprova. 2) Metti un ruolo del bot troppo in basso o togli "Gestisci ruoli": il punteggio cala di 10 e il consiglio lo spiega. 3) Dai `Amministratore` a `@everyone`: `/security heatmap` lo mostra per primo con ⚠️. 4) Dai a 8 utenti di fila un ruolo con `Gestisci ruoli`: il proprietario riceve 5 DM e poi uno solo "troppi ruoli…". Risultato atteso: come descritto.
- [ ] SIC-044, SIC-046 e revoca (#117) — commit ccdc53b, `012e083` — passi: tre server di test S1, S2, S3, tutti con il bot e `/security globalban enable`. 1) S3: `enable invia:No ricevi:Sì`. 2) In S1 un account di prova scrive nel canale trappola: viene bannato in S1 e in S2, **non** in S3 se S3 ha `ricevi:No`, e viene bannato in S3 con `ricevi:Sì`. 3) In S2: `/security globalban controlla utente:<account>` → "bannato … da 1 server" senza nomi. 4) In S1 l'account scrive in DM al bot, lo staff preme **Unban** nel thread dell'appello: l'account viene sbannato in S1 **e** negli altri server, tranne dove il ban è stato messo a mano. Risultato atteso: come descritto; `status` mostra le due direzioni.
- [ ] Spam-trap (#59) — commit `012e083` — passi: 1) `/security spamtrap trap_channel:#a log_channel:#a` → rifiutato ("due canali diversi"). 2) Senza canali: `/security spamtrap` crea trappola e log; il log è visibile al bot anche se il suo ruolo non ha permessi di canale; se manca Bannare membri/Crea thread privati la risposta lo dice. 3) Un account di prova incolla 5 messaggi in 1 secondo nella trappola: **un solo** DM, un solo caso, un solo messaggio nel log. 4) Un account con 100+ messaggi nei canali: il ban parte entro pochi secondi e il transcript dice "N older messages are not included". Risultato atteso: come descritto.
- [ ] Verify e inviti (#59, #60) — commit `012e083` — passi: 1) `/security verify blacklist-add member:<id di un utente uscito dal server>` (prima non si poteva: serviva un membro). 2) Clic sul pannello dopo aver già il ruolo: risposta "You are already verified", nessuna nuova riga nel log. 3) Modalità reaction con il bot senza "Aggiungi reazioni": il pannello esce e un messaggio spiega di aggiungere la reazione a mano. 4) Spegni il modulo Verify (`/admin setup`) e prova `/security verify panel`: rifiutato. 5) Crea e cancella un invito con spam-trap attivo: nessun errore nei log del bot. Risultato atteso: come descritto.

### Dopo la revisione (cacciatore e revisore) — stesso ramo

- [ ] Solo chi gestisce (#117) — passi: come A (amministratore, non fidato, non extra owner): `/security antinuke limits category:Canali max_actions:1000 seconds:3600`, `/security antinuke punish-action`, `/security antinuke recovery enabled:No`, `/security antiraid quarantine-hold enabled:Sì`. Poi come P gli stessi. Risultato atteso: A rifiutato quattro volte ("Solo il proprietario e gli extra owner…") e le impostazioni non cambiano; P le cambia. Con il blocco acceso anche `/security antiraid rilascia member:<qualcuno>` è rifiutato ad A. Come P nomina A extra owner: ora A può farle; con un secondo extra owner B, A non può `trusted-add user_id:<B>` (né declassarlo né sostituirlo).
- [ ] Una punizione per attacco (#117) — passi: `punish-action Quarantena`, `limits category:Canali max_actions:2 seconds:60`; come A cancella 10 canali di fila. Risultato atteso: **un solo** caso, **un solo** DM al proprietario e **un solo** avviso nel canale degli allarmi, anche se A continua; `casi` elenca un caso. Se mentre l'attacco dura qualcuno ridà un ruolo ad A, l'evento dopo lo ferma di nuovo **senza** aprire un secondo caso (il caso elenca anche i ruoli ritolti).
- [ ] Rilascio per caso (#117) — passi: A subisce due attacchi distinti (caso 1 sui canali, caso 2 sui ruoli, a distanza di più di un'ora e senza rilasciare); `/security antinuke rilascia caso:1`. Risultato atteso: A riprende **solo** i ruoli del caso 1 e **resta in quarantena** ("ha altri casi attivi (#2)"); `rilascia caso:2` lo libera del tutto. `/security antiraid rilascia member:<A con un caso attivo>` risponde "resta in quarantena: ha casi anti-nuke attivi". Dopo il rilascio una sola azione sotto soglia non punisce (i contatori ripartono da zero).
- [ ] Quarantena che non toglie i poteri (#117) — passi: sposta il ruolo del bot **sotto** il ruolo Amministratore di A; `punish-action Quarantena`; come A cancella 4 canali. Risultato atteso: avviso e `casi numero:N` dicono "ha il ruolo di quarantena ma i suoi ruoli NON sono stati tolti: l'autore è ancora potente", non "messo in quarantena".
- [ ] Ruolo di quarantena all'attivazione (#117) — passi: server senza ruolo "Quarantined"; `/security antiraid enable true` e `/security antinuke enable true`. Risultato atteso: subito dopo c'è **un solo** ruolo "Quarantined", senza permessi, con scrittura, reazioni e voce negate su tutti i canali. Se ne crei uno a mano con `Amministratore` e rifai `enable`, il bot gli toglie i permessi.
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
- [ ] Dati (NF-04, F5) — quando il registro esisterà: `rank_card_prefs` deve comparire in esportazione e cancellazione.


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
