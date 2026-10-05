# NUOVE_FUNZIONI.md — Le funzioni da aggiungere

Qui c'è ogni funzione che iYokai **non ha ancora** e che va costruita.
Vengono da tre posti: `SPEC.md` (voci mai fatte), il confronto con gli
altri bot ([`../01-analisi/CONFRONTO_BOT.md`](../01-analisi/CONFRONTO_BOT.md),
issue #52) e il motore AI (issue #50).

**Regola dell'owner:** nessuna funzione richiesta viene abbandonata. Se
Discord la rende impossibile così com'era pensata, qui c'è
l'alternativa più vicina che funziona.

Quando farle: vedi [`PRIORITA.md`](../archivio/PRIORITA.md). Cosa cambiare in ciò
che esiste già: vedi [`MODIFICHE_ESISTENTE.md`](MODIFICHE_ESISTENTE.md).

## Regole per ogni funzione nuova

1. Prima di progettarla, passa la lista di controllo di
   [`../01-analisi/LIMITI.md`](../01-analisi/LIMITI.md) (Parte 4).
2. Dove va il codice:
   - comandi e ascolto degli eventi: `cogs/<area>/<nome>.py`;
   - logica senza Discord, facile da provare: `core/<nome>_logic.py`;
   - database: `core/repositories/<nome>_repo.py`;
   - cambi allo schema: `core/migrations/NNNN_<nome>.sql`, dove `NNNN`
     è il primo numero libero **nel momento in cui la scrivi** (oggi
     l'ultimo è `0004`);
   - test: `tests/test_<nome>.py`, con gli oggetti finti di
     `tests/support/discord_fakes.py`.
3. Nessun comando nuovo di primo livello. Ogni comando entra in uno dei
   13 gruppi. Prima della fase F7 i gruppi nuovi non esistono: si usa un
   gruppo esistente e si sposta in F7.
4. Ogni modulo nuovo si registra con una categoria valida (vedi
   `core/premium.py`) e si accende da `/setup`.
5. Ogni tabella nuova con `user_id` o `guild_id` va scritta nel registro
   dei dati personali (`core/data_registry.py`, NF-04).

## Albero dei comandi dopo la fase F7

Limiti: 25 figli per gruppo, un solo livello di sotto-gruppi.

| Gruppo | Chi lo vede | Figli previsti (sotto-comandi e sotto-gruppi) | Quanti |
|---|---|---|---|
| `/owner` | Solo nel server dell'owner | `premium`, `blacklist`, `cog`, `system`, `radio`, `privacy`, `ai` | 7 |
| `/admin` | Amministratori e ruoli delegati | `setup`, `wizard`, `config`, `lingua`, `backup`, `restore`, `benvenuto`, `economia`, `ticket`, `voice`, `alert`, `ruoli`, `starboard`, `comandi`, `embed`, `contatori`, `compleanni`, `moduli`, `musica`, `ai`, `statistiche`, `premium` | 22 |
| `/mod` | Chi può moderare i membri | `warn`, `timeout`, `untimeout`, `mute`, `unmute`, `clear`, `lock`, `unlock`, `slowmode`, `caso`, `nota`, `blocco` | 12 |
| `/modban` | Chi può bannare | `ban`, `tempban`, `softban`, `kick`, `unban` | 5 |
| `/security` | Amministratori e ruoli delegati | `automod`, `escalation`, `antinuke`, `antiraid`, `globalban`, `verify`, `spamtrap`, `alt`, `panico`, `score`, `heatmap` | 11 |
| `/log` | Chi gestisce il server | `canale`, `crea-canali`, `crea-forum`, `stato`, `cerca`, `esporta`, `ignora` | 7 |
| `/ticket` | Tutti | `close`, `claim`, `add`, `remove`, `rename`, `priority`, `forceclose` | 7 |
| `/voice` | Tutti | `rename`, `limit`, `lock`, `unlock`, `kick`, `transfer` | 6 |
| `/music` | Tutti | `play`, `skip`, `stop`, `pause`, `resume`, `queue`, `clear-queue`, `shuffle`, `loop`, `nowplaying`, `volume`, `disconnect`, `nonstop`, `playlist` | 14 |
| `/level` | Tutti | `rank`, `leaderboard`, `daily`, `work`, `pay`, `balance`, `shop`, `cassa`, `inviti`, `compleanno`, `profilo` | 11 |
| `/clan` | Tutti | quelli di oggi, più `lascia` e `accetta` | 14 |
| `/fun` | Tutti | i 14 di oggi, più `ship`, `rate`, `suono`, `immagina`, `gioca`, `misura` | 20 |
| `/utility` | Tutti | `ping`, `poll`, `reminder`, `suggest`, `report`, `serverstats`, `cerca-comando`, `reactionsnipe`, `snipe`, `editsnipe`, `privacy`, `tag`, `modulo`, `chiedi`, `riassumi` | 15 |

`/admin` è il gruppo più pieno (22 su 25). Prima di aggiungergli un
figlio, controlla il conto. Se serve altro spazio, una funzione nuova
va **dentro** un sotto-gruppo esistente (per esempio dentro `config`).

---

## Le funzioni

### NF-01 — Router dei canali e log su forum

- **Fase:** F6 · **SPEC:** §18
- **Cosa fa:** Un solo punto che decide **dove** scrive il bot. Per ogni tipo di uscita (log membri, log messaggi, moderazione, voce, server, automod, allarmi, benvenuto…) si sceglie un canale di testo o un forum. Nel forum il bot usa un post per tipo di log (D3). Se il canale sparisce, avvisa gli admin una volta sola.
- **Da chi prendere spunto:** Carl-bot (`log aio` crea categoria e 5 canali), Wick (crea `#logs` e `#modlogs`).
- **Comandi:** `/log canale`, `/log crea-canali`, `/log crea-forum`, `/log stato`, `/log ignora …`. Fino a F7 vivono nel gruppo esistente `/logs`.
- **File nuovi:** `core/channel_router.py`, `core/repositories/output_channel_repo.py`, `cogs/logging/log_config.py`, `tests/test_channel_router.py`.
- **Migrazione:** `core/migrations/NNNN_output_channels.sql`.
- **Limiti da rispettare:** 50 canali per categoria; 500 per server; nome 100; `HTTPException` sempre catturata; canali `___hidden___` ignorati (`LIM-38`).
- **Dipende da:** Migrazioni versionate (fatte). `REVIEW.md` §8.

### NF-02 — Log dei messaggi cancellati, modificati e cancellati in blocco

- **Fase:** F6 · **SPEC:** §8.16
- **Cosa fa:** Quando un messaggio viene cancellato o modificato, il bot lo scrive nel log con autore, canale e testo di prima e dopo. Una cancellazione in blocco produce un solo riepilogo con un file.
- **Da chi prendere spunto:** Carl-bot e Dyno. Carl-bot permette di ignorare canali, utenti e prefissi.
- **Comandi:** Nessun comando nuovo: si configura con `/log canale tipo:messaggi` e `/log ignora`.
- **File nuovi:** `cogs/logging/message_logs.py`, `core/message_log_logic.py`, `tests/test_message_logs.py`.
- **Limiti da rispettare:** Campo 1024 e descrizione 4096: testo tagliato; file sotto 10 MiB (`LIM-55`); cache dei messaggi limitata (`BoundedCache`).
- **Dipende da:** `message_content` attivo nel Portal (D9). NF-01.

### NF-03 — Snipe ed editsnipe

- **Fase:** F6 · **SPEC:** §14.9, §14.10
- **Cosa fa:** `snipe` mostra l'ultimo messaggio cancellato nel canale. `editsnipe` mostra l'ultima modifica. Memoria breve, mai salvata su disco.
- **Da chi prendere spunto:** Funzione classica di molti bot.
- **Comandi:** `/utility snipe`, `/utility editsnipe` (accanto a `reactionsnipe`). Fino a F7: sotto-comandi di un gruppo esistente, mai comandi nuovi di primo livello.
- **File nuovi:** `tests/test_snipe_messaggi.py`.
- **File esistenti da toccare:** `cogs/utility/snipe.py`, `core/snipe_logic.py`.
- **Limiti da rispettare:** Descrizione 4096: testo tagliato. Scadenza breve (es. 5 minuti). Un interruttore per server (privacy).
- **Dipende da:** `message_content` (D9).

### NF-04 — Privacy: cancellazione, esportazione, conservazione

- **Fase:** F5 · **SPEC:** §19
- **Cosa fa:** Ogni utente può chiedere una copia dei suoi dati o la loro cancellazione. I dati di un server vengono cancellati 90 giorni dopo l'uscita del bot (D6). Un solo lavoro giornaliero pulisce le tabelle che crescono.
- **Da chi prendere spunto:** Double Counter (`/privacy`, conservazione dichiarata di 24 mesi).
- **Comandi:** `/utility privacy esporta`, `/utility privacy cancella`; `/owner privacy richieste`, `/owner privacy approva`. Fino a F7: sotto il gruppo esistente `/config`.
- **File nuovi:** `cogs/utility/privacy.py`, `core/data_registry.py`, `core/forget_user_service.py`, `core/retention_worker.py`, `core/repositories/guild_presence_repo.py`, `core/repositories/data_deletion_request_repo.py`, `tests/test_data_registry.py`, `tests/test_forget_user.py`, `tests/test_retention_worker.py`.
- **Migrazione:** `core/migrations/NNNN_guild_presence.sql`, `core/migrations/NNNN_retain_for_security.sql`, `core/migrations/NNNN_data_deletion_requests.sql`.
- **Limiti da rispettare:** Esportazione come file sotto 10 MiB; DM con `HTTPException` catturata.
- **Dipende da:** GDPR-1/2/3 di `REVIEW.md`. D6.

### NF-05 — Nuova struttura dei comandi

- **Fase:** F7 · **SPEC:** §20
- **Cosa fa:** Da 97 comandi di primo livello a 13 gruppi: `/owner /admin /mod /modban /security /log /ticket /voice /music /level /clan /fun /utility`. Chi non può usare un comando non lo vede. `/owner` esiste solo nel server dell'owner.
- **Da chi prendere spunto:** Standard di Discord (permessi predefiniti e delega in *Integrazioni*).
- **Comandi:** Tutti. Vedi la tabella "Albero dei comandi" più sotto.
- **File nuovi:** `core/command_groups.py`, `tests/test_command_groups.py`.
- **Limiti da rispettare:** 100 comandi; 25 figli per gruppo; un solo livello di sotto-gruppi; `default_permissions` solo sul primo livello (`LIM-57`).
- **Dipende da:** D2, D4. `REVIEW.md` §6.

### NF-06 — Lingue italiano e inglese, e `/utility cerca-comando`

- **Fase:** F8 · **SPEC:** §21
- **Cosa fa:** Tutti i testi del bot in un unico file per lingua. La lingua del server decide le risposte. I nomi dei comandi sono tradotti da Discord secondo la lingua dell'utente (D1). La ricerca dei comandi capisce sinonimi in entrambe le lingue e mostra solo i comandi che l'utente può usare.
- **Da chi prendere spunto:** Maki (32 lingue), ProBot (10).
- **Comandi:** `/admin lingua`, `/utility cerca-comando`.
- **File nuovi:** `locales/it.json`, `locales/en.json`, `core/command_translator.py`, `tests/test_i18n_completo.py`.
- **File esistenti da toccare:** `core/i18n.py`, `core/command_search_logic.py`, `cogs/utility/command_search.py`, `scripts/generate_command_list.py` (da estendere: scrive `COMMAND_LIST_ITA.md` e `COMMAND_LIST_ENG.md`).
- **Limiti da rispettare:** Nome comando 32, descrizione 100, totale 8000 per comando anche con le traduzioni.
- **Dipende da:** NF-05 (i nomi cambiano lì). D1.

### NF-07 — Ruolo automatico all'ingresso, ruoli ridati a chi rientra, ruoli a tempo

- **Fase:** F9 · **SPEC:** §22
- **Cosa fa:** Chi entra riceve uno o più ruoli. Chi esce e rientra entro 30 giorni riprende i ruoli che aveva. Un ruolo può essere dato dopo un ritardo.
- **Da chi prendere spunto:** Carl-bot (autorole, ruoli ridati entro 30 giorni, ruoli a tempo), Arcane.
- **Comandi:** `/admin ruoli auto aggiungi|rimuovi|elenco`, `/admin ruoli ricorda`.
- **File nuovi:** `cogs/utility/autoroles.py`, `core/autorole_logic.py`, `core/repositories/autorole_repo.py`, `tests/test_autoroles.py`.
- **Migrazione:** `core/migrations/NNNN_autoroles.sql`.
- **Limiti da rispettare:** 250 ruoli; `check_role_assignable` alla configurazione e all'assegnazione; niente ruoli ai bot; pausa durante un raid.
- **Dipende da:** Nessuna. Va d'accordo con Verify: se la verifica è attiva, il ruolo arriva dopo.

### NF-08 — Starboard

- **Fase:** F9 · **SPEC:** §22
- **Cosa fa:** Un messaggio che riceve abbastanza ⭐ viene copiato in un canale "bacheca".
- **Da chi prendere spunto:** MEE6 (gratis), Carl-bot, Dyno, Zeppelin, Circle.
- **Comandi:** `/admin starboard imposta|soglia|disattiva`.
- **File nuovi:** `cogs/utility/starboard.py`, `core/starboard_logic.py`, `core/repositories/starboard_repo.py`, `tests/test_starboard.py`.
- **Migrazione:** `core/migrations/NNNN_starboard.sql`.
- **Limiti da rispettare:** Embed entro i limiti; un solo messaggio in bacheca per originale; canali NSFW esclusi di default.
- **Dipende da:** NF-01 per il canale.

### NF-09 — Comandi personalizzati (tag)

- **Fase:** F9 · **SPEC:** §22
- **Cosa fa:** Ogni server crea i suoi comandi: un nome, un testo o un embed, un ruolo da dare o togliere, una pausa tra un uso e l'altro. Si usano con `/utility tag <nome>` e, se l'admin vuole, anche con un prefisso scelto dal server (solo per i tag: è l'alternativa al "prefisso personalizzato" di SPEC §2.4).
- **Da chi prendere spunto:** YAGPDB (100 gratis), Carl-bot (tag), MEE6.
- **Comandi:** `/admin comandi crea|modifica|elimina|elenco`, `/utility tag`.
- **File nuovi:** `cogs/utility/custom_commands.py`, `core/custom_command_logic.py`, `core/repositories/custom_command_repo.py`, `tests/test_custom_commands.py`.
- **File esistenti da toccare:** `cogs/utility/custom_command_requests.py` resta (richieste all'owner).
- **Migrazione:** `core/migrations/NNNN_custom_commands.sql`.
- **Limiti da rispettare:** Testo 2000; nome 32; tetto per server (es. 50 gratis); nessun `str.format` (si usa `core/template_renderer.py`); ruoli con `check_role_assignable`.
- **Dipende da:** `message_content` solo per l'uso con prefisso.

### NF-10 — Risposte automatiche

- **Fase:** F9 · **SPEC:** §14.7
- **Cosa fa:** Quando un messaggio contiene una parola o frase scelta, il bot risponde da solo. Con condizioni: canale, ruolo, corrispondenza esatta o parziale.
- **Da chi prendere spunto:** Carl-bot ("trigger": 50 gratis), YAGPDB.
- **Comandi:** `/admin comandi risposta-crea|risposta-elimina|risposte`.
- **File nuovi:** `cogs/utility/autoresponder.py`, `core/autoresponder_logic.py`, `core/repositories/autoresponder_repo.py`, `tests/test_autoresponder.py`.
- **Migrazione:** `core/migrations/NNNN_autoresponder.sql`.
- **Limiti da rispettare:** Tetto per server; pausa per canale; mai rispondere ai bot; testo 2000.
- **Dipende da:** `message_content` (D9). NF-09 (stessa tabella di base).

### NF-11 — Immagine di benvenuto

- **Fase:** F9 · **SPEC:** §22
- **Cosa fa:** Il benvenuto può avere un'immagine con avatar, nome e numero del membro. Si parte con 3–4 modelli pronti e uno sfondo caricabile.
- **Da chi prendere spunto:** ProBot (sfondo sotto 3 MB, avatar tondo o quadrato, testo con posizione e colore).
- **Comandi:** `/admin benvenuto immagine`.
- **File nuovi:** `core/welcome_image.py`, `tests/test_welcome_image.py`.
- **File esistenti da toccare:** `cogs/utility/greetings.py`, `core/repositories/greetings_repo.py`.
- **Migrazione:** `core/migrations/NNNN_greetings_immagine.sql`.
- **Limiti da rispettare:** Regole di `core/safe_image.py` (16 megapixel, 2048 px); file sotto 10 MiB; lavoro Pillow fuori dal ciclo principale.
- **Dipende da:** Nessuna. L'editor completo arriva con il pannello web (NF-20).

### NF-12 — Rank card

- **Fase:** F9 · **SPEC:** §22
- **Cosa fa:** `rank` mostra un'immagine con avatar, livello, barra dell'XP e posizione in classifica. Colore e sfondo a scelta.
- **Da chi prendere spunto:** MEE6 (colori gratis, sfondo premium), Arcane, Carl-bot.
- **Comandi:** `/level rank`.
- **File nuovi:** `core/rank_card_image.py`, `tests/test_rank_card_image.py`.
- **File esistenti da toccare:** `cogs/leveling/leveling.py`.
- **Limiti da rispettare:** `defer()` prima di disegnare; regole di `core/safe_image.py`.
- **Dipende da:** Nessuna.

### NF-13 — Ticket: modulo, più pannelli, chiusura automatica, voto

- **Fase:** F9 · **SPEC:** §22
- **Cosa fa:** Prima di aprire un ticket l'utente compila un modulo (fino a 5 domande). Un messaggio può avere più pannelli. Un ticket fermo si chiude da solo. Alla chiusura l'utente dà un voto. Limite di ticket aperti per utente.
- **Da chi prendere spunto:** Ticket Tool (25 pannelli, 5 domande, transcript), Tickets (chiusura automatica, voto a stelle).
- **Comandi:** `/admin ticket modulo`, `/admin ticket pannello`, `/admin ticket chiusura-auto`.
- **File nuovi:** `core/ticket_form_logic.py`, `core/repositories/ticket_form_repo.py`, `core/ticket_autoclose_worker.py`, `tests/test_ticket_form.py`, `tests/test_ticket_autoclose.py`.
- **File esistenti da toccare:** `cogs/tickets/tickets.py`, `core/ticket_logic.py`, `core/repositories/ticket_repo.py`.
- **Migrazione:** `core/migrations/NNNN_ticket_form.sql`.
- **Limiti da rispettare:** 5 campi per modulo, etichetta 45; 25 opzioni per menu (`LIM-6`); 5 bottoni per riga; chiusura tramite scheduler.
- **Dipende da:** BUG-30 (fatto).

### NF-14 — Modalità dei reaction roles

- **Fase:** F9 · **SPEC:** §22
- **Cosa fa:** Per ogni menu si sceglie il comportamento: *unique* (un ruolo alla volta), *verify* (si dà e non si toglie), *drop* (si toglie soltanto), *reversed*, *binding* (una scelta per sempre), *temp* (a tempo), *lock*. In più lista di ruoli ammessi o esclusi.
- **Da chi prendere spunto:** Carl-bot.
- **Comandi:** `/admin ruoli menu …` (oggi `/rolemenu`).
- **File nuovi:** `tests/test_role_menu_modalita.py`.
- **File esistenti da toccare:** `cogs/utility/role_menus.py`, `core/role_menu_logic.py`, `core/repositories/role_menu_repo.py`.
- **Migrazione:** `core/migrations/NNNN_role_menu_modalita.sql`.
- **Limiti da rispettare:** 20 reazioni, 25 bottoni, 25 opzioni; campo 1024 (`LIM-17`).
- **Dipende da:** `LIM-17` sistemato prima.

### NF-15 — Impostazioni dei livelli

- **Fase:** F9 · **SPEC:** §22
- **Cosa fa:** Canali e ruoli senza XP. Moltiplicatori per canale e per ruolo. Scelta di dove annunciare il level-up (spento, canale corrente, DM, canale scelto). Premi "accumula" o "togli i precedenti". XP e monete configurabili per server.
- **Da chi prendere spunto:** MEE6, ProBot, Maki.
- **Comandi:** `/admin economia livelli …`.
- **File nuovi:** `core/repositories/leveling_settings_repo.py`, `tests/test_leveling_settings.py`.
- **File esistenti da toccare:** `cogs/leveling/leveling.py`, `core/leveling_logic.py`.
- **Migrazione:** `core/migrations/NNNN_leveling_settings.sql`.
- **Limiti da rispettare:** 25 scelte per opzione; valori con minimo e massimo.
- **Dipende da:** Nessuna.

### NF-16 — Canali contatore

- **Fase:** F13 · **SPEC:** §23
- **Cosa fa:** Canali il cui nome mostra un numero: membri, membri online, boost, obiettivo.
- **Da chi prendere spunto:** ServerStats, Arcane (3 gratis), Statbot.
- **Comandi:** `/admin contatori crea|elimina|elenco`.
- **File nuovi:** `cogs/utility/counters.py`, `core/counter_logic.py`, `core/counter_worker.py`, `core/repositories/counter_repo.py`, `tests/test_counters.py`.
- **Migrazione:** `core/migrations/NNNN_counters.sql`.
- **Limiti da rispettare:** Rinomina 2 ogni 10 minuti per canale: aggiornamento al massimo ogni 10 minuti (`LIM-3`); tetto per server.
- **Dipende da:** Nessuna.

### NF-17 — Costruttore di embed

- **Fase:** F9 · **SPEC:** §22
- **Cosa fa:** Un admin compone un messaggio con titolo, testo, colore, immagine e campi, lo vede in anteprima e lo pubblica o lo modifica dopo.
- **Da chi prendere spunto:** ProBot, Atlas, Hydra ("message builder"), Carl-bot.
- **Comandi:** `/admin embed crea|modifica|pubblica|elenco`.
- **File nuovi:** `cogs/utility/embed_builder.py`, `core/embed_builder_logic.py`, `core/repositories/saved_embed_repo.py`, `tests/test_embed_builder.py`.
- **Migrazione:** `core/migrations/NNNN_saved_embeds.sql`.
- **Limiti da rispettare:** Tutti i limiti degli embed (256, 4096, 1024, 25, 6000) controllati **al salvataggio**.
- **Dipende da:** Nessuna. L'editor visuale arriva con il pannello web.

### NF-18 — Captcha a immagine

- **Fase:** F9 · **SPEC:** §22
- **Cosa fa:** La verifica mostra un'immagine con lettere storte da ricopiare, al posto della somma scritta.
- **Da chi prendere spunto:** Wick, Captcha.bot.
- **Comandi:** `/security verify setup` (opzione `captcha: immagine`).
- **File nuovi:** `core/captcha_image.py`, `tests/test_captcha_image.py`.
- **File esistenti da toccare:** `cogs/security/verify.py`, `core/verify_logic.py`.
- **Limiti da rispettare:** Campo del modulo 45 caratteri di etichetta; immagine piccola; tempo massimo e numero di tentativi.
- **Dipende da:** Nessuna.

### NF-19 — Canale richieste musicali con player, playlist salvate

- **Fase:** F9 · **SPEC:** §23
- **Cosa fa:** Un canale dedicato con un messaggio "player" sempre aggiornato e bottoni (pausa, salta, stop, mescola, ripeti). Chi scrive un titolo nel canale lo mette in coda. Ogni utente può salvare playlist. Nessun ruolo DJ e nessun voto (scelta dell'owner).
- **Da chi prendere spunto:** Hydra (storico), Jockie (raccolte).
- **Comandi:** `/admin musica canale-richieste`, `/music playlist salva|carica|elenco|elimina`.
- **File nuovi:** `cogs/music/request_channel.py`, `core/music_request_logic.py`, `core/repositories/music_request_repo.py`, `core/repositories/music_playlist_repo.py`, `tests/test_music_request_channel.py`, `tests/test_music_playlist.py`.
- **File esistenti da toccare:** `cogs/music/player.py`.
- **Migrazione:** `core/migrations/NNNN_music_request.sql`, `core/migrations/NNNN_music_playlist.sql`.
- **Limiti da rispettare:** View persistente; 5 bottoni per riga; titolo 256 (`LIM-21`); aggiornamento del messaggio non più di una volta ogni pochi secondi.
- **Dipende da:** F2 finita (D10) e provata live. `message_content`.

### NF-20 — Pannello web (iYokai Panel)

- **Fase:** F10 · **SPEC:** §24
- **Cosa fa:** Un sito dove l'admin entra con Discord, sceglie il server e configura ogni modulo. Scrive **le stesse impostazioni** dei comandi. Ha anche le pagine dell'owner (premium, blacklist) e le pagine legali.
- **Da chi prendere spunto:** MEE6, Dyno, Carl-bot, ProBot, Wick.
- **Comandi:** Nessun comando. Vive in un repository separato e privato (scelta dell'owner).
- **File nuovi:** `core/panel_bridge.py`, `core/config_schema.py`, `tests/test_panel_bridge.py`, `tests/test_config_schema.py`.
- **Limiti da rispettare:** Stessi controlli dei comandi: il pannello chiama le stesse funzioni di validazione, mai il database a mano.
- **Dipende da:** NF-01, NF-05, NF-06. Dominio con HTTPS. Privacy policy (NF-04).

### NF-21 — Verifica su web e riconoscimento degli account doppi

- **Fase:** F10 · **SPEC:** §4.2, §4.3
- **Cosa fa:** La verifica passa da una pagina web. Il bot calcola un'impronta (mai l'IP in chiaro) e la confronta con quelle già viste. Se trova un doppione **avvisa lo staff**: nessun ban automatico tra server (scelta già presa).
- **Da chi prendere spunto:** Double Counter, Wick (modalità Web).
- **Comandi:** `/security verify setup` (opzione `modo: web`), `/security alt elenco`.
- **File nuovi:** `cogs/security/alt_detection.py`, `core/alt_detection_logic.py`, `core/repositories/fingerprint_repo.py`, `tests/test_alt_detection.py`.
- **File esistenti da toccare:** `cogs/security/verify.py`.
- **Migrazione:** `core/migrations/NNNN_fingerprints.sql`.
- **Limiti da rispettare:** Dati personali: conservazione dichiarata, comando privacy, cifratura a riposo.
- **Dipende da:** NF-20. Privacy policy pubblicata. Scope OAuth `identify` separato da `guilds.join`.

### NF-22 — Pagamento vero del premium

- **Fase:** F10 · **SPEC:** §3
- **Cosa fa:** Il premium si compra davvero: abbonamento dentro Discord (app premium) e, in alternativa, pagamento esterno registrato dall'owner. Resta lo sblocco con le monete (1.000.000 per modulo, SPEC §3.1) e con la cassa del server.
- **Da chi prendere spunto:** Tutti i grandi bot. Double Counter vende tramite Discord.
- **Comandi:** `/admin premium stato`, `/owner premium …` (già esistenti).
- **File nuovi:** `core/premium_entitlement_service.py`, `core/repositories/entitlement_repo.py`, `tests/test_premium_entitlement.py`.
- **File esistenti da toccare:** `core/premium.py`, `cogs/utility/owner_premium.py`.
- **Migrazione:** `core/migrations/NNNN_entitlements.sql`.
- **Limiti da rispettare:** Per vendere dentro Discord l'app deve essere verificata.
- **Dipende da:** Verifica dell'app. I 6 moduli premium devono controllare davvero il premium (F1).

### NF-23 — Istanza NSFW

- **Fase:** F11 · **SPEC:** §16.10
- **Cosa fa:** Un bot a parte (stesso codice, token `NSFW_TOKEN`). Funziona solo nei canali segnati NSFW. Ricerca e pubblicazione automatica, con due filtri obbligatori: lista permessa scelta dal server e lista vietata fissa nel codice.
- **Da chi prendere spunto:** Lawliet.
- **Comandi:** Comandi propri dell'istanza NSFW (non contano nei 100 del bot principale).
- **File nuovi:** `core/nsfw_bot.py`, `cogs/nsfw/__init__.py`, `cogs/nsfw/ricerca.py`, `core/nsfw_filter_logic.py`, `core/nsfw_autopost_worker.py`, `core/repositories/nsfw_repo.py`, `tests/test_nsfw_filter_logic.py`, `tests/test_nsfw_canale.py`.
- **Migrazione:** `core/migrations/NNNN_nsfw.sql`.
- **Limiti da rispettare:** Controllo del canale NSFW a **ogni** invio; registro con hash di ogni immagine; contenuti vietati dalla legge bloccati sempre.
- **Dipende da:** NF-05, NF-06. Verifica dell'identità sul pannello (NF-20) per l'invito.

### NF-24 — Motore AI

- **Fase:** F12 · **SPEC:** §25
- **Cosa fa:** Tutte le funzioni AI di cui si è parlato sono in [`../01-analisi/FUNZIONI_AI.md`](../01-analisi/FUNZIONI_AI.md): 100 righe con codice `AI-R`, ognuna con la fonte, chi l'ha chiesta, come farla e i limiti. Questa scheda dice solo come sono divise e quali file servono. In breve: un motore unico con più fornitori in cascata e una risposta locale di riserva; sopra ci stanno i 12 gruppi della tabella. Tutto parte spento. L'AI propone, una persona conferma.
- **Da chi prendere spunto:** MEE6 (AI venduta a parte), Maki (AI nei piani a pagamento), NadekoBot (comandi a parole).
- **Comandi:** `/admin ai …` (un solo sotto-gruppo: `stato`, `interruttori`, `tetto`, `privacy`, `filtri`, `lore`, `faq`, `riepilogo`, `boss`, `misteri`, `personaggi`, `traduzione`; 12 su 25), `/owner ai …` (`fornitori`, `modello`, `spesa`, `libreria`), `/utility chiedi`, `/utility riassumi`, `/utility cerca-comando`, `/fun immagina`, `/fun gioca boss`, `/fun gioca dungeon`. In più opzioni dentro comandi che ci sono già: `/log cerca`, `/security automod`, `/security panico`, `/admin ticket`, `/owner privacy`. Un figlio da aggiungere all'albero: `/utility parole-chiave` (`/utility` passa da 15 a 16).
- **Gruppi e file:**

  | Gruppo | Codici | File nuovi | File esistenti da toccare |
  |---|---|---|---|
  | Motore e infrastruttura | AI-R-001…AI-R-023 (23) | `core/ai_router.py`, `core/ai_cache_logic.py`, `core/ai_guardrail_logic.py`, `core/ai_cost_logic.py`, `core/repositories/ai_repo.py`, `cogs/ai/__init__.py`, `tests/test_ai_router.py`, `tests/test_ai_guardrail_logic.py`, `tests/test_ai_cost_logic.py`, `cogs/ai/admin.py`, `core/ai_queue_logic.py`, `core/ai_privacy_logic.py`, `core/repositories/ai_library_repo.py`, `tests/test_ai_queue_logic.py`, `tests/test_ai_privacy_logic.py`, `tests/test_ai_library.py` | — |
  | Assistente e helpdesk | AI-R-024…AI-R-038 (15) | `cogs/ai/helpdesk.py`, `core/ai_helpdesk_logic.py`, `core/repositories/ai_faq_repo.py`, `tests/test_ai_helpdesk_logic.py` | `core/command_search_logic.py`, `cogs/utility/command_search.py` |
  | Moderazione e sicurezza con AI | AI-R-039…AI-R-042 (4) | `cogs/ai/moderation_assist.py`, `core/ai_moderation_logic.py`, `tests/test_ai_moderation_logic.py` | `cogs/moderation/report.py`, `cogs/automod/automod.py`, `cogs/security/lockdown.py` |
  | Riassunti e ricerca | AI-R-043…AI-R-048 (6) | `cogs/ai/summaries.py`, `core/ai_digest_logic.py`, `core/ai_digest_worker.py`, `core/repositories/ai_digest_repo.py`, `cogs/utility/keyword_alerts.py`, `core/keyword_alert_logic.py`, `core/repositories/keyword_alert_repo.py`, `tests/test_ai_digest_logic.py`, `tests/test_keyword_alerts.py` | `cogs/logging/logs_query.py` |
  | Lore, giochi e narrazione | AI-R-049…AI-R-064 (16) | `cogs/ai/lore.py`, `core/lore_logic.py`, `core/repositories/lore_repo.py`, `cogs/fun/boss.py`, `core/boss_logic.py`, `core/boss_worker.py`, `core/repositories/boss_repo.py`, `cogs/fun/dungeon.py`, `core/dungeon_logic.py`, `core/repositories/dungeon_repo.py`, `cogs/ai/characters.py`, `tests/test_lore_logic.py`, `tests/test_boss_logic.py`, `tests/test_dungeon_logic.py` | `core/setup_wizard_logic.py`, `cogs/utility/setup.py` |
  | Immagini, voce e media | AI-R-065…AI-R-070 (6) | `cogs/ai/images.py`, `core/ai_image_logic.py`, `core/boss_image.py`, `tests/test_ai_image_logic.py`, `tests/test_boss_image.py` | — |
  | Ticket e staff | AI-R-071…AI-R-075 (5) | `cogs/ai/ticket_assist.py`, `core/ai_ticket_logic.py`, `tests/test_ai_ticket_logic.py` | `cogs/tickets/tickets.py`, `core/ticket_logic.py` |
  | Livelli, economia e community | AI-R-076…AI-R-080 (5) | `core/lore_collection_logic.py`, `tests/test_lore_collection_logic.py` | `cogs/leveling/leveling.py`, `cogs/leveling/profiles.py`, `core/repositories/profile_repo.py` |
  | Traduzione e lingue | AI-R-081…AI-R-088 (8) | `cogs/ai/translate.py`, `core/translate_logic.py`, `tests/test_translate_logic.py` | `cogs/user_app/personal.py`, `core/command_search_logic.py` |
  | Owner e analisi | AI-R-089…AI-R-091 (3) | nessuno in questo repository | `cogs/ai/admin.py` (gruppo 1), `cogs/utility/privacy.py`, `core/ai_cost_logic.py` |
  | App utente e Desktop | AI-R-092…AI-R-097 (6) | `tests/test_user_app_ai.py` | `cogs/user_app/personal.py` |
  | Pannello web | AI-R-098…AI-R-100 (3) | nessuno in questo repository | `core/config_schema.py`, `core/panel_bridge.py` |

- **Migrazione:** `core/migrations/NNNN_ai.sql` (motore: uso, cache, consenso, libreria), `core/migrations/NNNN_ai_lore.sql` (può nascere prima del motore), `core/migrations/NNNN_ai_faq.sql`, `core/migrations/NNNN_ai_digest.sql`, `core/migrations/NNNN_keyword_alerts.sql`, `core/migrations/NNNN_boss_dungeon.sql`.
- **Limiti da rispettare:** Vietato usare i messaggi per addestrare modelli; risposta entro 3 secondi con `defer()`; testo 2000/4096; tetto di spesa (D13); 25 comandi per sotto-gruppo; 5 messaggi dopo la prima risposta dove l'app non è nel server; un riepilogo o un boss a orario lo esegue un solo bot.
- **Ordine dei lavori:** quello di `FUNZIONI_AI.md` ("Ordine consigliato dentro la fase F12"). Il passo 0 (lore, tetto, interruttori, consenso, livelli di privacy, registro dei comandi, parte del riepilogo fatta di numeri) non manda niente a nessun fornitore e si può fare prima della policy.
- **Dipende da:** Privacy policy pubblicata con l'elenco dei fornitori. Consenso dell'admin per server. `message_content`. D13. NF-06 (registro dei comandi), NF-25 (attività, per riepilogo e boss), NF-40 (oggetti e profilo, per i premi).

### NF-25 — Statistiche di attività e ruoli per attività

- **Fase:** F13 · **SPEC:** §23
- **Cosa fa:** Messaggi e minuti in vocale per canale e per membro, con grafici. Ruoli dati a chi è attivo in un periodo e tolti a chi smette.
- **Da chi prendere spunto:** Statbot (Statroles).
- **Comandi:** `/admin statistiche …`, `/utility serverstats`.
- **File nuovi:** `cogs/utility/activity_stats.py`, `core/activity_stats_logic.py`, `core/repositories/activity_stats_repo.py`, `tests/test_activity_stats.py`.
- **File esistenti da toccare:** `cogs/utility/server_stats.py`.
- **Migrazione:** `core/migrations/NNNN_activity_stats.sql`.
- **Limiti da rispettare:** Tabelle che crescono: dati aggregati per giorno e regola di pulizia (NF-04).
- **Dipende da:** NF-04.

### NF-26 — Compleanni

- **Fase:** F13 · **SPEC:** §23
- **Cosa fa:** Ogni utente registra il suo compleanno. Il giorno giusto il bot fa gli auguri in un canale e può dare un ruolo per 24 ore.
- **Da chi prendere spunto:** MEE6, Maki, Lawliet.
- **Comandi:** `/level compleanno imposta|rimuovi`, `/admin compleanni canale|ruolo`.
- **File nuovi:** `cogs/utility/birthdays.py`, `core/birthday_logic.py`, `core/birthday_worker.py`, `core/repositories/birthday_repo.py`, `tests/test_birthdays.py`.
- **Migrazione:** `core/migrations/NNNN_birthdays.sql`.
- **Limiti da rispettare:** Solo giorno e mese (niente anno: meno dati personali); dato cancellabile dall'utente.
- **Dipende da:** NF-04 (dato personale).

### NF-27 — Inviti: comando e classifica

- **Fase:** F13 · **SPEC:** §23
- **Cosa fa:** Ogni membro vede quante persone ha invitato. Classifica degli inviti del server.
- **Da chi prendere spunto:** MEE6, Maki, Lawliet.
- **Comandi:** `/level inviti`, `/level leaderboard tipo:inviti`.
- **File nuovi:** `cogs/utility/invites.py`, `core/repositories/invite_stats_repo.py`, `tests/test_invites.py`.
- **File esistenti da toccare:** `core/invite_tracker.py`.
- **Migrazione:** `core/migrations/NNNN_invite_stats.sql`.
- **Limiti da rispettare:** Classifica di 10 righe; l'attribuzione sbaglia con ingressi simultanei (LC-6): va detto all'utente.
- **Dipende da:** LC-6 sistemato.

### NF-28 — Giveaway avanzati

- **Fase:** F13 · **SPEC:** §23
- **Cosa fa:** Modelli riusabili, più ingressi per certi ruoli, requisito "numero di messaggi", ruoli che saltano i requisiti, giveaway programmati.
- **Da chi prendere spunto:** Giveaway Boat.
- **Comandi:** `/admin economia giveaway …`.
- **File nuovi:** `tests/test_giveaway_avanzati.py`.
- **File esistenti da toccare:** `cogs/leveling/leveling.py`, `core/giveaway_logic.py`, `core/repositories/giveaway_repo.py`.
- **Migrazione:** `core/migrations/NNNN_giveaway_avanzati.sql`.
- **Limiti da rispettare:** Premio nel titolo: 256 (`LIM-18`); avviso ai vincitori anche in thread e forum.
- **Dipende da:** NF-25 per il requisito sui messaggi.

### NF-29 — Blocco totale del server e "panic mode"

- **Fase:** F13 · **SPEC:** §23
- **Cosa fa:** Un comando blocca tutti i canali, gli inviti e gli ingressi, e un altro riapre tutto com'era. Durante un attacco riconosciuto può scattare da solo.
- **Da chi prendere spunto:** Wick (lockdown e panic mode).
- **Comandi:** `/mod blocco attiva|togli`, `/security panico …`.
- **File nuovi:** `cogs/security/lockdown.py`, `core/lockdown_logic.py`, `core/repositories/lockdown_repo.py`, `tests/test_lockdown.py`.
- **Migrazione:** `core/migrations/NNNN_lockdown.sql`.
- **Limiti da rispettare:** 500 canali: lavoro lungo, `defer()` e riepilogo nel canale; stato salvato per poter riaprire.
- **Dipende da:** BUG-11 e BUG-12 sistemati.

### NF-30 — Appello per i ban normali

- **Fase:** F13 · **SPEC:** §23
- **Cosa fa:** Chi viene bannato a mano può chiedere una revisione in DM, come già succede per lo spam-trap.
- **Da chi prendere spunto:** Circle ("Ban Appeals").
- **Comandi:** `/admin config appelli`.
- **File nuovi:** `cogs/moderation/ban_appeal.py`, `core/ban_appeal_logic.py`, `tests/test_ban_appeal.py`.
- **File esistenti da toccare:** `cogs/security/spam_trap.py`.
- **Limiti da rispettare:** Un appello ogni 24 ore; View persistente; solo chi ha "Bannare membri" decide.
- **Dipende da:** LC-5 sistemato (bottoni di appello persistenti).

### NF-31 — Blocco dei link di phishing

- **Fase:** F13 · **SPEC:** §23
- **Cosa fa:** Il bot riconosce i link truffa più comuni (finti regali Nitro, finti login) e li cancella.
- **Da chi prendere spunto:** Captcha.bot, Wick.
- **Comandi:** `/security automod phishing`.
- **File nuovi:** `core/phishing_logic.py`, `core/phishing_list_fetcher.py`, `tests/test_phishing_logic.py`.
- **File esistenti da toccare:** `cogs/automod/automod.py`.
- **Limiti da rispettare:** Lista aggiornata da una fonte esterna: cache e condizioni d'uso scritte in `LIMITI.md`.
- **Dipende da:** `message_content`.

### NF-32 — Alert: Kick, ruolo "in diretta", TikTok, Instagram e X

- **Fase:** F13 · **SPEC:** §10.5, §10.6, §10.13
- **Cosa fa:** Alert per Kick. Un ruolo dato a chi è in diretta. Per TikTok, Instagram e X, che non hanno API gratuite: feed "ponte" RSS e webhook in ingresso (già esistenti), con una guida, più una chiave API a pagamento facoltativa (D14).
- **Da chi prendere spunto:** Streamcord (ruolo in diretta, Kick), Pingcord.
- **Comandi:** `/admin alert aggiungi-kick`, `/admin alert ruolo-live`, `/admin alert guida-social`.
- **File nuovi:** `core/kick_watcher.py`, `core/kick_api_logic.py`, `core/repositories/kick_subscription_repo.py`, `core/live_role_logic.py`, `tests/test_kick_watcher.py`, `tests/test_live_role_logic.py`.
- **File esistenti da toccare:** `cogs/utility/feed_alerts.py`.
- **Migrazione:** `core/migrations/NNNN_kick_subscriptions.sql`.
- **Limiti da rispettare:** Quote di ogni servizio scritte in `LIMITI.md`; tetto di alert per server.
- **Dipende da:** LC-7 e `LIM-46` sistemati.

### NF-33 — Ticket via messaggio privato

- **Fase:** F13 · **SPEC:** §23
- **Cosa fa:** L'utente scrive in DM al bot e nasce un canale per lo staff. Lo staff risponde da lì, anche in forma anonima.
- **Da chi prendere spunto:** ModMail.
- **Comandi:** `/admin ticket dm attiva|disattiva`.
- **File nuovi:** `cogs/tickets/modmail.py`, `core/modmail_logic.py`, `core/repositories/modmail_repo.py`, `tests/test_modmail.py`.
- **Migrazione:** `core/migrations/NNNN_modmail.sql`.
- **Limiti da rispettare:** Un solo ciclo sui DM (oggi lo usa lo spam-trap): un punto di ingresso comune.
- **Dipende da:** `message_content`. NF-30 (stesso ingresso dei DM).

### NF-34 — Moduli e candidature

- **Fase:** F13 · **SPEC:** §23
- **Cosa fa:** L'admin crea un modulo (candidatura staff, ingresso in un clan). Le risposte arrivano in un canale con bottoni accetta e rifiuta.
- **Da chi prendere spunto:** Dyno (form builder), Circle.
- **Comandi:** `/admin moduli crea|elimina|elenco`, `/utility modulo`.
- **File nuovi:** `cogs/utility/forms.py`, `core/form_logic.py`, `core/repositories/form_repo.py`, `tests/test_forms.py`.
- **Migrazione:** `core/migrations/NNNN_forms.sql`.
- **Limiti da rispettare:** 5 campi per modulo; etichetta 45; risposte in campi da 1024.
- **Dipende da:** NF-13 (stessa logica dei moduli).

### NF-35 — Effetti sonori in vocale

- **Fase:** F13 · **SPEC:** §23
- **Cosa fa:** Brevi suoni da far partire in un canale vocale.
- **Da chi prendere spunto:** Yggdrasil (19 suoni), YAGPDB.
- **Comandi:** `/fun suono`.
- **File nuovi:** `cogs/fun/soundboard.py`, `tests/test_soundboard_play.py`.
- **Limiti da rispettare:** Usa un bot musicale libero; pausa per utente.
- **Dipende da:** F2 finita.

### NF-36 — Applicazione installabile dall'utente

- **Fase:** F13 · **SPEC:** §B
- **Cosa fa:** Comandi personali che l'utente porta con sé in qualsiasi server e in DM: promemoria, profilo, utilità.
- **Da chi prendere spunto:** Nighty (solo l'idea lecita: comandi ovunque).
- **Comandi:** Comandi dell'applicazione utente (albero separato).
- **File nuovi:** `cogs/user_app/__init__.py`, `cogs/user_app/personal.py`, `tests/test_user_app.py`.
- **Limiti da rispettare:** 5 risposte successive per interazione dove l'app non è installata nel server.
- **Dipende da:** NF-05.

### NF-37 — iYokai Desktop (presenza personalizzata)

- **Fase:** F13 · **SPEC:** §D
- **Cosa fa:** Un programma sul PC dell'utente che imposta la "rich presence" tramite il collegamento locale di Discord. È l'alternativa lecita allo stato animato dei self-bot (SPEC §D.5): stato testuale, bio e avatar a rotazione **non** si possono fare senza violare le regole.
- **Da chi prendere spunto:** Nighty (solo l'idea lecita).
- **Comandi:** Nessun comando: progetto separato.
- **File nuovi:** nessuno in questo repository.
- **Limiti da rispettare:** Nessun token utente, mai.
- **Dipende da:** Nessuna.

### NF-38 — Bot con marchio proprio

- **Fase:** F13 · **SPEC:** §23
- **Cosa fa:** Un server premium usa il bot con nome e avatar suoi.
- **Da chi prendere spunto:** MEE6 (Bot Personalizer), Tickets (6,99 $/mese), Sapphire.
- **Comandi:** `/admin premium marchio`.
- **File nuovi:** `core/whitelabel_bot.py`, `core/repositories/whitelabel_repo.py`, `tests/test_whitelabel_bot.py`.
- **Migrazione:** `core/migrations/NNNN_whitelabel.sql`.
- **Limiti da rispettare:** Ogni bot in più è un'applicazione Discord con token proprio, cifrato a riposo.
- **Dipende da:** NF-22.

### NF-39 — Modelli di server e sincronia tra server

- **Fase:** F13 · **SPEC:** §23
- **Cosa fa:** Una raccolta di strutture pronte da caricare. Ban e ruoli tenuti uguali tra due server dello stesso proprietario.
- **Da chi prendere spunto:** Xenon (5.731 modelli, sync).
- **Comandi:** `/admin backup modello …`, `/admin backup sincronia …`.
- **File nuovi:** `core/server_sync_logic.py`, `tests/test_server_sync_logic.py`.
- **File esistenti da toccare:** `cogs/utility/backup.py`.
- **Limiti da rispettare:** Stessi limiti del backup (`LIM-28`, `LIM-38`).
- **Dipende da:** F3 finita (D8).

### NF-40 — Profili, collezioni e giochi con le monete

- **Fase:** F13 · **SPEC:** §23
- **Cosa fa:** Profilo personale con sfondo e badge. Oggetti da collezionare. Giochi semplici con le monete (senza soldi veri). Include un misuratore casuale a tema libero, alternativa neutra a SPEC §16.6, e il gioco del conteggio in un canale.
- **Da chi prendere spunto:** Tatsu, Dank Memer, UnbelievaBoat.
- **Comandi:** `/level profilo`, `/fun gioca …`, `/fun misura`.
- **File nuovi:** `cogs/fun/coin_games.py`, `core/coin_games_logic.py`, `cogs/leveling/profiles.py`, `core/repositories/profile_repo.py`, `tests/test_coin_games_logic.py`, `tests/test_profiles.py`.
- **Migrazione:** `core/migrations/NNNN_profiles.sql`.
- **Limiti da rispettare:** Discord vieta di monetizzare il gioco d'azzardo: le monete di questi giochi non si comprano mai con soldi veri.
- **Dipende da:** BUG-14 sistemato (monete senza doppi accrediti).

### NF-41 — Idee rimandate di `BACKLOG.md`

- **Fase:** F14 · **SPEC:** BACKLOG §6, §7, §9, §11
- **Cosa fa:** Missioni, traguardi, serie di giorni consecutivi, "battle pass"; profilo globale con soli dati positivi; punteggio di rischio che unisce i segnali di sicurezza; misura del carico dello staff (senza premi automatici). **Attenzione:** questa scheda non conteneva tutto ciò che `BACKLOG.md` §7–§9 aveva rimandato. World Boss, Dungeon, frammenti di lore e Spirito Yokai ora sono in NF-24 (`FUNZIONI_AI.md`). Le idee non AI che mancavano (guerra tra clan OM-040, albero delle abilità OM-041, percorso di ingresso OM-048, mentori OM-050, ricordi OM-051, anniversari OM-052, eventi di stagione OM-053, gradi OM-060, profili pronti OM-061, identità del server OM-062 e altre) sono in [`../01-analisi/VOCI_OMESSE.md`](../01-analisi/VOCI_OMESSE.md), con i dettagli da non perdere per missioni, serie e battle pass.
- **Da chi prendere spunto:** Tatsu, Dank Memer.
- **Comandi:** Da decidere quando si arriva alla fase.
- **File nuovi:** nessuno in questo repository.
- **Limiti da rispettare:** Vedi i rischi scritti in `BACKLOG.md` per ogni voce.
- **Dipende da:** Bot in produzione con utenti veri. NF-40.

---

## File da creare

Tabella per chi prepara gli scheletri dei file. I percorsi sono gli
stessi scritti nei blocchi sopra. Le migrazioni non sono in tabella:
il loro numero si sceglie quando si scrivono.

| Percorso | Scopo | Funzione | Fase |
|---|---|---|---|
| `core/channel_router.py` | Trova il canale giusto per ogni tipo di uscita e ci scrive | NF-01 | F6 |
| `core/repositories/output_channel_repo.py` | Tabella `output_channels` (server, tipo, canale, post) | NF-01 | F6 |
| `cogs/logging/log_config.py` | Comandi per scegliere o creare i canali dei log | NF-01 | F6 |
| `tests/test_channel_router.py` | Test del router (testo, forum, canale sparito) | NF-01 | F6 |
| `cogs/logging/message_logs.py` | Ascolta cancellazioni e modifiche e le manda al router | NF-02 | F6 |
| `core/message_log_logic.py` | Prepara il testo dei log dei messaggi (tagli, differenze) | NF-02 | F6 |
| `tests/test_message_logs.py` | Test dei tre eventi con messaggi finti con contenuto | NF-02 | F6 |
| `tests/test_snipe_messaggi.py` | Test di snipe ed editsnipe | NF-03 | F6 |
| `cogs/utility/privacy.py` | Comandi di richiesta dati e cancellazione | NF-04 | F5 |
| `core/data_registry.py` | Elenco di tutte le tabelle con dati personali e come cancellarle | NF-04 | F5 |
| `core/forget_user_service.py` | Cancella o rende anonimi i dati di un utente | NF-04 | F5 |
| `core/retention_worker.py` | Pulizia giornaliera: server usciti da 90 giorni e tabelle con scadenza | NF-04 | F5 |
| `core/repositories/guild_presence_repo.py` | Quando il bot è entrato e uscito da ogni server | NF-04 | F5 |
| `core/repositories/data_deletion_request_repo.py` | Richieste di cancellazione e loro esito | NF-04 | F5 |
| `tests/test_data_registry.py` | Ogni tabella con `user_id` o `guild_id` è nel registro | NF-04 | F5 |
| `tests/test_forget_user.py` | Cancellazione di un utente, rifiuto se ha righe di sicurezza | NF-04 | F5 |
| `tests/test_retention_worker.py` | Pulizia dopo 90 giorni, righe di sicurezza conservate | NF-04 | F5 |
| `core/command_groups.py` | I 13 gruppi di primo livello, definiti una volta sola e usati da tutti i cog | NF-05 | F7 |
| `tests/test_command_groups.py` | Ogni gruppo: `guild_only`, permessi predefiniti, al massimo 25 figli | NF-05 | F7 |
| `locales/it.json` | Tutti i testi in italiano | NF-06 | F8 |
| `locales/en.json` | Tutti i testi in inglese | NF-06 | F8 |
| `core/command_translator.py` | Dà a Discord nomi e descrizioni tradotti dei comandi | NF-06 | F8 |
| `tests/test_i18n_completo.py` | Ogni chiave esiste in entrambe le lingue; nessun testo fisso nei cog | NF-06 | F8 |
| `cogs/utility/autoroles.py` | Comandi e ascolto degli ingressi | NF-07 | F9 |
| `core/autorole_logic.py` | Decide quali ruoli dare e quando | NF-07 | F9 |
| `core/repositories/autorole_repo.py` | Ruoli automatici e ruoli ricordati di chi esce | NF-07 | F9 |
| `tests/test_autoroles.py` | Ingresso, rientro, ruolo pericoloso rifiutato | NF-07 | F9 |
| `cogs/utility/starboard.py` | Comandi e ascolto delle reazioni | NF-08 | F9 |
| `core/starboard_logic.py` | Soglia, autovoto, costruzione del messaggio | NF-08 | F9 |
| `core/repositories/starboard_repo.py` | Configurazione e messaggi già in bacheca | NF-08 | F9 |
| `tests/test_starboard.py` | Soglia, niente doppioni, rimozione delle stelle | NF-08 | F9 |
| `cogs/utility/custom_commands.py` | Comandi di gestione e uso dei tag | NF-09 | F9 |
| `core/custom_command_logic.py` | Validazione, segnaposto, pausa | NF-09 | F9 |
| `core/repositories/custom_command_repo.py` | Tag salvati per server | NF-09 | F9 |
| `tests/test_custom_commands.py` | Creazione, limiti, uso, ruolo pericoloso rifiutato | NF-09 | F9 |
| `cogs/utility/autoresponder.py` | Ascolta i messaggi e risponde | NF-10 | F9 |
| `core/autoresponder_logic.py` | Confronto del testo e condizioni | NF-10 | F9 |
| `core/repositories/autoresponder_repo.py` | Risposte automatiche salvate | NF-10 | F9 |
| `tests/test_autoresponder.py` | Corrispondenze, pausa, bot ignorati | NF-10 | F9 |
| `core/welcome_image.py` | Disegna l'immagine di benvenuto | NF-11 | F9 |
| `tests/test_welcome_image.py` | Dimensioni, nome lungo, avatar mancante | NF-11 | F9 |
| `core/rank_card_image.py` | Disegna la rank card | NF-12 | F9 |
| `tests/test_rank_card_image.py` | Dimensioni, nome lungo, livello massimo | NF-12 | F9 |
| `core/ticket_form_logic.py` | Domande del modulo e controllo delle risposte | NF-13 | F9 |
| `core/repositories/ticket_form_repo.py` | Moduli per categoria e voti | NF-13 | F9 |
| `core/ticket_autoclose_worker.py` | Chiude i ticket fermi | NF-13 | F9 |
| `tests/test_ticket_form.py` | Modulo, limite per utente, voto | NF-13 | F9 |
| `tests/test_ticket_autoclose.py` | Chiusura per inattività e per utente uscito | NF-13 | F9 |
| `tests/test_role_menu_modalita.py` | Un test per modalità | NF-14 | F9 |
| `core/repositories/leveling_settings_repo.py` | Impostazioni dei livelli per server | NF-15 | F9 |
| `tests/test_leveling_settings.py` | Canale escluso, moltiplicatore, modalità dei premi | NF-15 | F9 |
| `cogs/utility/counters.py` | Comandi dei contatori | NF-16 | F13 |
| `core/counter_logic.py` | Calcola il testo di ogni contatore | NF-16 | F13 |
| `core/counter_worker.py` | Aggiorna i nomi rispettando il limite delle rinomine | NF-16 | F13 |
| `core/repositories/counter_repo.py` | Contatori configurati | NF-16 | F13 |
| `tests/test_counters.py` | Testo, limite di rinomina, canale sparito | NF-16 | F13 |
| `cogs/utility/embed_builder.py` | Comandi e modulo di composizione | NF-17 | F9 |
| `core/embed_builder_logic.py` | Controllo dei limiti e costruzione dell'embed | NF-17 | F9 |
| `core/repositories/saved_embed_repo.py` | Embed salvati per server | NF-17 | F9 |
| `tests/test_embed_builder.py` | Ogni limite rifiutato al salvataggio | NF-17 | F9 |
| `core/captcha_image.py` | Genera l'immagine e il testo atteso | NF-18 | F9 |
| `tests/test_captcha_image.py` | Testo casuale, immagine leggibile, tentativi | NF-18 | F9 |
| `cogs/music/request_channel.py` | Canale richieste e messaggio player | NF-19 | F9 |
| `core/music_request_logic.py` | Stato del player e testo del messaggio | NF-19 | F9 |
| `core/repositories/music_request_repo.py` | Canale richieste per server | NF-19 | F9 |
| `core/repositories/music_playlist_repo.py` | Playlist salvate degli utenti | NF-19 | F9 |
| `tests/test_music_request_channel.py` | Messaggio player, bottoni, riavvio | NF-19 | F9 |
| `tests/test_music_playlist.py` | Salva, carica, tetto di brani | NF-19 | F9 |
| `core/panel_bridge.py` | Riceve dal pannello l'avviso "configurazione cambiata" e aggiorna la memoria del bot | NF-20 | F10 |
| `core/config_schema.py` | Schema unico di ogni impostazione (tipo, minimo, massimo), usato da comandi, import e pannello | NF-20 | F10 |
| `tests/test_panel_bridge.py` | Un cambio dal pannello arriva al bot | NF-20 | F10 |
| `tests/test_config_schema.py` | Ogni impostazione ha uno schema | NF-20 | F10 |
| `cogs/security/alt_detection.py` | Avvisi allo staff e comandi di consultazione | NF-21 | F10 |
| `core/alt_detection_logic.py` | Confronto delle impronte e punteggio | NF-21 | F10 |
| `core/repositories/fingerprint_repo.py` | Impronte in forma di hash | NF-21 | F10 |
| `tests/test_alt_detection.py` | Doppione segnalato, nessun ban automatico | NF-21 | F10 |
| `core/premium_entitlement_service.py` | Legge gli abbonamenti Discord e li trasforma in accesso premium | NF-22 | F10 |
| `core/repositories/entitlement_repo.py` | Abbonamenti attivi per server | NF-22 | F10 |
| `tests/test_premium_entitlement.py` | Abbonamento attivo, scaduto, revocato | NF-22 | F10 |
| `core/nsfw_bot.py` | Avvio dell'istanza NSFW | NF-23 | F11 |
| `cogs/nsfw/__init__.py` | Pacchetto dei cog NSFW | NF-23 | F11 |
| `cogs/nsfw/ricerca.py` | Comando di ricerca e pubblicazione automatica | NF-23 | F11 |
| `core/nsfw_filter_logic.py` | I due filtri: lista permessa e lista vietata | NF-23 | F11 |
| `core/nsfw_autopost_worker.py` | Pubblicazione a intervalli | NF-23 | F11 |
| `core/repositories/nsfw_repo.py` | Configurazione e registro degli hash | NF-23 | F11 |
| `tests/test_nsfw_filter_logic.py` | La lista vietata vince sempre | NF-23 | F11 |
| `tests/test_nsfw_canale.py` | Niente invio fuori dai canali NSFW | NF-23 | F11 |
| `core/ai_router.py` | Sceglie il fornitore, passa al successivo se uno fallisce | NF-24 | F12 |
| `core/ai_cache_logic.py` | Riusa le risposte a domande uguali o molto simili | NF-24 | F12 |
| `core/ai_guardrail_logic.py` | Filtri in ingresso e in uscita, rimozione dei dati personali | NF-24 | F12 |
| `core/ai_cost_logic.py` | Conta l'uso e applica il tetto per server | NF-24 | F12 |
| `core/repositories/ai_repo.py` | Configurazione, uso, cache e lore per server | NF-24 | F12 |
| `cogs/ai/__init__.py` | Pacchetto dei cog AI | NF-24 | F12 |
| `cogs/ai/helpdesk.py` | Risponde alle domande sui comandi e sul server | NF-24 | F12 |
| `cogs/ai/summaries.py` | Riassunti di canali e ticket | NF-24 | F12 |
| `cogs/ai/lore.py` | Tono e ambientazione del server | NF-24 | F12 |
| `cogs/ai/images.py` | Generazione di immagini | NF-24 | F12 |
| `tests/test_ai_router.py` | Cascata dei fornitori e risposta locale | NF-24 | F12 |
| `tests/test_ai_guardrail_logic.py` | Filtri e dati personali rimossi | NF-24 | F12 |
| `tests/test_ai_cost_logic.py` | Tetto di spesa rispettato | NF-24 | F12 |
| `cogs/ai/admin.py` | Comandi `/admin ai` e `/owner ai`: stato, interruttori, tetto, privacy, filtri, fornitori, modello, spesa, libreria | NF-24 | F12 |
| `core/ai_queue_logic.py` | Coda delle richieste e limite per server e globale | NF-24 | F12 |
| `core/ai_privacy_logic.py` | Consenso, livelli di privacy e tempo di conservazione del contesto | NF-24 | F12 |
| `core/repositories/ai_library_repo.py` | Libreria dei contenuti generati e testi di riserva per tema | NF-24 | F12 |
| `tests/test_ai_queue_logic.py` | Molte richieste insieme: fila, limite, risposta locale oltre l'attesa | NF-24 | F12 |
| `tests/test_ai_privacy_logic.py` | Senza consenso niente AI; ogni livello passa solo ciò che può | NF-24 | F12 |
| `tests/test_ai_library.py` | Contenuto salvato e riusato; niente dati di utenti nella libreria | NF-24 | F12 |
| `core/ai_helpdesk_logic.py` | Sceglie le fonti (FAQ, regole, registro dei comandi) e prepara la risposta con al massimo 3 comandi e il loro stato | NF-24 | F12 |
| `core/repositories/ai_faq_repo.py` | Base di conoscenza del server: domande, risposte, regole | NF-24 | F12 |
| `tests/test_ai_helpdesk_logic.py` | Solo comandi che esistono; stato giusto; funziona anche senza AI | NF-24 | F12 |
| `cogs/ai/moderation_assist.py` | Avvisi allo staff, etichetta delle segnalazioni, riassunto di un incidente, proposta di regole | NF-24 | F12 |
| `core/ai_moderation_logic.py` | Prepara la proposta e i bottoni di conferma; nessuna azione diretta | NF-24 | F12 |
| `tests/test_ai_moderation_logic.py` | Nessuna punizione senza conferma; permessi di chi conferma | NF-24 | F12 |
| `core/ai_digest_logic.py` | Contenuto del riepilogo: i numeri (senza AI) e il testo (con AI) | NF-24 | F12 |
| `core/ai_digest_worker.py` | Pubblica il riepilogo all'ora scelta, da un solo bot | NF-24 | F12 |
| `core/repositories/ai_digest_repo.py` | Configurazione del riepilogo e ultimi riepiloghi salvati | NF-24 | F12 |
| `cogs/utility/keyword_alerts.py` | Parole chiave personali e avviso quando una discussione si accende | NF-24 | F12 |
| `core/keyword_alert_logic.py` | Conteggio per canale e parola, soglia, pausa tra gli avvisi | NF-24 | F12 |
| `core/repositories/keyword_alert_repo.py` | Parole registrate per utente | NF-24 | F12 |
| `tests/test_ai_digest_logic.py` | Solo i canali scelti; embed entro i limiti; riepilogo senza AI | NF-24 | F12 |
| `tests/test_keyword_alerts.py` | Soglia dei 10 messaggi; nessun avviso per canali che l'utente non vede | NF-24 | F12 |
| `core/lore_logic.py` | Temi pronti, tema libero, nomi a tema, testo da aggiungere a ogni richiesta | NF-24 | F12 |
| `core/repositories/lore_repo.py` | Tabella `guild_lore_config` | NF-24 | F12 |
| `cogs/fun/boss.py` | World Boss: annuncio, bottoni di combattimento, chiusura | NF-24 | F12 |
| `core/boss_logic.py` | Danno, vita del boss, premi | NF-24 | F12 |
| `core/boss_worker.py` | Comparsa a orario | NF-24 | F12 |
| `core/repositories/boss_repo.py` | Eventi, partecipanti, danni | NF-24 | F12 |
| `cogs/fun/dungeon.py` | Dungeon di gruppo: stanze, voto, misteri | NF-24 | F12 |
| `core/dungeon_logic.py` | Esito delle scelte secondo classi e livelli; stanze di riserva | NF-24 | F12 |
| `core/repositories/dungeon_repo.py` | Partite, classi scelte, misteri e premi a tempo | NF-24 | F12 |
| `cogs/ai/characters.py` | Personaggi AI del server | NF-24 | F12 |
| `tests/test_lore_logic.py` | Tema di partenza, tema libero filtrato, nomi a tema | NF-24 | F12 |
| `tests/test_boss_logic.py` | Danno, vita, premi una volta sola, evento senza AI | NF-24 | F12 |
| `tests/test_dungeon_logic.py` | Voto, esito, partita senza AI | NF-24 | F12 |
| `core/ai_image_logic.py` | Filtro prima e dopo, quota di immagini, variazioni e ingrandimento | NF-24 | F12 |
| `core/boss_image.py` | Disegna l'immagine dell'annuncio del boss (Pillow, senza AI) | NF-24 | F12 |
| `tests/test_ai_image_logic.py` | Richiesta vietata rifiutata; quota rispettata; file sotto 10 MiB | NF-24 | F12 |
| `tests/test_boss_image.py` | Dimensioni e nome lungo | NF-24 | F12 |
| `cogs/ai/ticket_assist.py` | Bottone "Chiedi all'assistente", prima risposta, bozza per lo staff, smistamento, riassunto nel transcript | NF-24 | F12 |
| `core/ai_ticket_logic.py` | Cosa può leggere l'AI in un ticket e come prepara bozza e riassunto | NF-24 | F12 |
| `tests/test_ai_ticket_logic.py` | Bozza mai inviata da sola; ticket che funziona con l'AI ferma | NF-24 | F12 |
| `core/lore_collection_logic.py` | Frammenti di lore e Spirito Yokai: come si ottengono, cosa sbloccano | NF-24 | F12 |
| `tests/test_lore_collection_logic.py` | Frammento dato una volta; spirito cambiabile; nessun effetto sui permessi | NF-24 | F12 |
| `cogs/ai/translate.py` | Traduzione di un canale, con la bandiera, di più messaggi di fila | NF-24 | F12 |
| `core/translate_logic.py` | Riconosce la lingua, sceglie il servizio, usa la cache delle traduzioni | NF-24 | F12 |
| `tests/test_translate_logic.py` | Lingua riconosciuta; testo già tradotto preso dalla cache | NF-24 | F12 |
| `tests/test_user_app_ai.py` | Cerca comando, assistente personale e scheda di lore fuori dal server: al massimo 5 messaggi dopo la prima risposta | NF-24 | F12 |
| `cogs/utility/activity_stats.py` | Comandi delle statistiche | NF-25 | F13 |
| `core/activity_stats_logic.py` | Aggregazione per giorno e calcolo dei ruoli per attività | NF-25 | F13 |
| `core/repositories/activity_stats_repo.py` | Conteggi giornalieri | NF-25 | F13 |
| `tests/test_activity_stats.py` | Aggregazione, ruolo dato e tolto | NF-25 | F13 |
| `cogs/utility/birthdays.py` | Comandi dei compleanni | NF-26 | F13 |
| `core/birthday_logic.py` | Chi compie gli anni oggi, per fuso orario del server | NF-26 | F13 |
| `core/birthday_worker.py` | Auguri giornalieri e ruolo a tempo | NF-26 | F13 |
| `core/repositories/birthday_repo.py` | Compleanni e configurazione | NF-26 | F13 |
| `tests/test_birthdays.py` | 29 febbraio, fuso orario, ruolo tolto dopo 24 ore | NF-26 | F13 |
| `cogs/utility/invites.py` | Comandi degli inviti | NF-27 | F13 |
| `core/repositories/invite_stats_repo.py` | Chi ha invitato chi | NF-27 | F13 |
| `tests/test_invites.py` | Conteggio, uscita dell'invitato, classifica | NF-27 | F13 |
| `tests/test_giveaway_avanzati.py` | Più ingressi, requisiti, modello | NF-28 | F13 |
| `cogs/security/lockdown.py` | Comandi di blocco e sblocco | NF-29 | F13 |
| `core/lockdown_logic.py` | Cosa bloccare e come ripristinare | NF-29 | F13 |
| `core/repositories/lockdown_repo.py` | Permessi di prima del blocco | NF-29 | F13 |
| `tests/test_lockdown.py` | Blocco, sblocco identico a prima, interruzione a metà | NF-29 | F13 |
| `cogs/moderation/ban_appeal.py` | Appello per i ban manuali | NF-30 | F13 |
| `core/ban_appeal_logic.py` | Regole comuni agli appelli (spam-trap e ban manuali) | NF-30 | F13 |
| `tests/test_ban_appeal.py` | Appello, pausa di 24 ore, bottoni dopo un riavvio | NF-30 | F13 |
| `core/phishing_logic.py` | Confronto dei domini con la lista | NF-31 | F13 |
| `core/phishing_list_fetcher.py` | Scarica e tiene in memoria la lista | NF-31 | F13 |
| `tests/test_phishing_logic.py` | Dominio truffa, sottodominio, falso positivo | NF-31 | F13 |
| `core/kick_watcher.py` | Controlla le dirette su Kick | NF-32 | F13 |
| `core/kick_api_logic.py` | Legge le risposte di Kick | NF-32 | F13 |
| `core/repositories/kick_subscription_repo.py` | Iscrizioni Kick | NF-32 | F13 |
| `core/live_role_logic.py` | Dà e toglie il ruolo "in diretta" | NF-32 | F13 |
| `tests/test_kick_watcher.py` | Diretta iniziata e finita | NF-32 | F13 |
| `tests/test_live_role_logic.py` | Ruolo dato e tolto | NF-32 | F13 |
| `cogs/tickets/modmail.py` | Ticket aperti in DM | NF-33 | F13 |
| `core/modmail_logic.py` | A quale server e ticket appartiene un DM | NF-33 | F13 |
| `core/repositories/modmail_repo.py` | Conversazioni aperte | NF-33 | F13 |
| `tests/test_modmail.py` | Apertura, risposta anonima, chiusura | NF-33 | F13 |
| `cogs/utility/forms.py` | Comandi e raccolta delle risposte | NF-34 | F13 |
| `core/form_logic.py` | Domande, controllo e riepilogo | NF-34 | F13 |
| `core/repositories/form_repo.py` | Moduli e risposte | NF-34 | F13 |
| `tests/test_forms.py` | Compilazione, accetta, rifiuta | NF-34 | F13 |
| `cogs/fun/soundboard.py` | Comando dei suoni | NF-35 | F13 |
| `tests/test_soundboard_play.py` | Bot libero, pausa | NF-35 | F13 |
| `cogs/user_app/__init__.py` | Pacchetto dei comandi personali | NF-36 | F13 |
| `cogs/user_app/personal.py` | Comandi personali | NF-36 | F13 |
| `tests/test_user_app.py` | I comandi funzionano in DM e fuori dal server | NF-36 | F13 |
| `core/whitelabel_bot.py` | Avvio dei bot con marchio proprio | NF-38 | F13 |
| `core/repositories/whitelabel_repo.py` | Token cifrati e stato | NF-38 | F13 |
| `tests/test_whitelabel_bot.py` | Avvio, token sbagliato isolato | NF-38 | F13 |
| `core/server_sync_logic.py` | Cosa copiare tra due server collegati | NF-39 | F13 |
| `tests/test_server_sync_logic.py` | Ban e ruoli tenuti uguali | NF-39 | F13 |
| `cogs/fun/coin_games.py` | Giochi con le monete e misuratore | NF-40 | F13 |
| `core/coin_games_logic.py` | Regole dei giochi | NF-40 | F13 |
| `cogs/leveling/profiles.py` | Profilo e collezioni | NF-40 | F13 |
| `core/repositories/profile_repo.py` | Profili e oggetti | NF-40 | F13 |
| `tests/test_coin_games_logic.py` | Regole e saldo mai negativo | NF-40 | F13 |
| `tests/test_profiles.py` | Profilo e collezione | NF-40 | F13 |

Totale: 200 file.
