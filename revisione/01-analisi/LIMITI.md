# LIMITI.md — I limiti che iYokai deve rispettare

Questo file serve a una cosa: **non ripetere l'errore di `/setup`**
(un menu con 32 voci quando Discord ne accetta 25).

Contiene:
1. la tabella dei limiti che contano;
2. i cambiamenti recenti di Discord che ci toccano;
3. tutti i punti del codice che oggi superano o ignorano un limite
   (codici `LIM-n`);
4. una lista di controllo da usare **prima** di scrivere una funzione.

Fonti dei numeri: documentazione ufficiale di Discord (letta il
04/10/2026), sorgente delle librerie installate (discord.py 2.7.1,
wavelink 3.5.2), tre controlli sul codice del 04/10/2026. I numeri di
riga sono quelli del codice al commit `783329e`.

Parole usate:
- **embed** = il riquadro colorato dei messaggi del bot;
- **interazione** = un comando slash, un clic su un bottone o un menu;
- **defer** = dire subito a Discord "sto lavorando", per avere più tempo;
- **REST** = le chiamate che il bot fa a Discord per agire (bannare,
  creare un canale…);
- **nodo Lavalink** = il programma esterno che produce l'audio.

---

## Parte 1 — I limiti

### 1.1 Componenti e moduli (bottoni, menu, finestre)

| Limite | Valore | Fonte |
|---|---|---|
| Opzioni in un menu a tendina | 25 | [Components](https://docs.discord.com/developers/components/reference) |
| Etichetta, valore e descrizione di un'opzione | 100 caratteri ciascuno | Components |
| Segnaposto di un menu | 150 caratteri | Components |
| Scelte minime e massime di un menu | da 0 a 25 | Components |
| Bottoni in una riga | 5 | Components |
| Righe di componenti in un messaggio classico | 5 | discord.py `ui/view.py` |
| Componenti totali in un messaggio (Components V2) | 40 | Components |
| Etichetta di un bottone | 80 caratteri | Components |
| `custom_id` | da 1 a 100 caratteri | Components |
| Campo di testo di un modulo: lunghezza | fino a 4000 caratteri | Components |
| Campo di testo: segnaposto | 100 caratteri | Components |
| Titolo di un modulo e etichetta di un campo | 45 caratteri | discord.py `ui/modal.py`, `ui/text_input.py` |
| Campi in un modulo | 5 | discord.py `ui/modal.py` |
| Durata di una View non persistente | 180 secondi di default | discord.py `ui/view.py` |

### 1.2 Embed e messaggi

| Limite | Valore | Fonte |
|---|---|---|
| Testo di un messaggio | 2000 caratteri | [Message](https://docs.discord.com/developers/resources/message) |
| Embed per messaggio | 10 | Message |
| Titolo di un embed | 256 caratteri | Message |
| Descrizione di un embed | 4096 caratteri | Message |
| Campi di un embed | 25 | Message |
| Nome di un campo | 256 caratteri | Message |
| Valore di un campo | 1024 caratteri | Message |
| Testo a piè di embed | 2048 caratteri | Message |
| Nome autore | 256 caratteri | Message |
| Somma di tutti i testi degli embed di un messaggio | 6000 caratteri | Message |
| Dimensione di un file caricato | 20 MiB dal 03/09/2026 (prima 10) | [Change log](https://docs.discord.com/developers/change-log) |
| Dimensione che discord.py crede valida | 10 MiB (valore fisso nella libreria) | discord.py `Guild.filesize_limit` |
| Sondaggio: domanda | 300 caratteri | [Poll](https://docs.discord.com/developers/resources/poll) |
| Sondaggio: risposta | 55 caratteri | Poll |
| Sondaggio: risposte | 10 | Poll |
| Sondaggio: durata | fino a 32 giorni | Poll |
| Nome di un webhook | non può contenere "discord" o "clyde" | **non riverificato** (audit REST) |

### 1.3 Comandi slash

| Limite | Valore | Fonte |
|---|---|---|
| Comandi slash di primo livello | 100 globali | [Application Commands](https://docs.discord.com/developers/interactions/application-commands) |
| Comandi del menu contestuale | 15 per tipo (dal 03/03/2026, prima 5) | Change log |
| Sotto-comandi o sotto-gruppi per gruppo | 25 | Application Commands; discord.py `app_commands/commands.py` |
| Livelli di sotto-gruppo | 1 (`/gruppo sottogruppo comando`) | Application Commands |
| Opzioni per comando | 25 | Application Commands |
| Scelte fisse per opzione | 25 | Application Commands |
| Nome di comando o opzione | da 1 a 32 caratteri | Application Commands |
| Descrizione | da 1 a 100 caratteri | Application Commands |
| Somma di nomi, descrizioni e valori di un comando | 8000 caratteri | Application Commands |
| Testo libero di un'opzione, senza `max_length` | fino a 6000 caratteri | Application Commands |
| Creazioni di comandi al giorno per server | 200 | Application Commands |
| `default_permissions` | vale solo sul comando o gruppo di primo livello | discord.py `app_commands/commands.py` (REVIEW L9) |

Stato di iYokai (misurato): 97 comandi di primo livello su 100;
`/owner` 25 su 25; `/automod` 22 su 25; peso massimo 2943 caratteri su
8000 (`/automod`).

### 1.4 Interazioni e tempi

| Limite | Valore | Fonte |
|---|---|---|
| Prima risposta a un'interazione | entro 3 secondi | [Receiving and Responding](https://docs.discord.com/developers/interactions/receiving-and-responding) |
| Validità del token dopo la prima risposta | 15 minuti | Receiving and Responding |
| Dopo un `defer` | la risposta si manda con `followup` | discord.py |
| Blacklist su `CommandTree` | ferma solo i comandi slash, non bottoni e moduli | REVIEW L10 |

### 1.5 Azioni REST e moderazione

| Limite | Valore | Fonte |
|---|---|---|
| Richieste al secondo per bot | 50 | [Rate Limits](https://docs.discord.com/developers/topics/rate-limits) |
| Richieste "non valide" (401, 403, 429) | 10.000 in 10 minuti, poi blocco dell'indirizzo IP | Rate Limits |
| Cosa fare su un 429 | aspettare il tempo di `Retry-After` | Rate Limits |
| Motivo nel registro di controllo (audit log) | 512 caratteri | [Audit Log](https://docs.discord.com/developers/resources/audit-log) |
| Timeout di un membro | massimo 28 giorni | Auto Moderation (2.419.200 s) |
| Messaggi cancellati con il ban | fino a 7 giorni (604.800 s) | [Guild](https://docs.discord.com/developers/resources/guild) |
| Cancellazione in blocco | da 2 a 100 messaggi, non più vecchi di 14 giorni | discord.py `TextChannel.purge` |
| Slowmode | da 0 a 21.600 secondi | discord.py `TextChannel.edit` |
| Nome di un canale | da 1 a 100 caratteri | discord.py |
| Rinomina di un canale | 2 ogni 10 minuti per canale | **non ufficiale**, nota alla community |
| Attesa di discord.py su un limite | senza `max_ratelimit_timeout` dorme anche 10 minuti | discord.py `http.py` |
| Autore di un evento | non è nell'evento: va letto dal registro di controllo, che arriva in ritardo | [Gateway Events](https://docs.discord.com/developers/events/gateway-events) |
| Un bot non può entrare da solo in un server | serve un clic umano sull'invito | Discord OAuth2 |
| `guilds.join` | il bot deve già essere nel server; il token utente scade e va rinnovato | [OAuth2](https://docs.discord.com/developers/topics/oauth2) |

### 1.6 Risorse del server

| Limite | Valore | Fonte |
|---|---|---|
| Canali per server | 500 | audit REST |
| Canali per categoria | 50 | audit REST |
| Ruoli per server | 250 | audit REST |
| Emoji senza boost | 50 fisse + 50 animate | audit avvio (`core/backup_clone_logic.py`) |
| Sticker senza boost | 5 | audit avvio |
| Suoni soundboard senza boost | 8 | audit avvio |
| Webhook per canale | 15 | audit REST (errore 30007) |
| Inviti per server | 1000 | audit REST |
| Qualità audio di un canale vocale senza boost | 96 kbps | audit REST |
| Server creati da un bot | **0**: non è più possibile | vedi Parte 2 |

### 1.7 AutoMod nativo di Discord

| Limite | Valore | Fonte |
|---|---|---|
| Regole "parole chiave" per server | 6 | [Auto Moderation](https://docs.discord.com/developers/resources/auto-moderation) |
| Regole spam, preset, menzioni, profilo | 1 ciascuna | Auto Moderation |
| Parole per regola | 1000, ognuna fino a 60 caratteri | Auto Moderation |
| Espressioni regolari per regola | 10, ognuna fino a 260 caratteri | Auto Moderation |
| Lista delle eccezioni | 100 voci (1000 per i preset) | Auto Moderation |
| Menzioni massime impostabili | 50 | Auto Moderation |
| Ruoli esenti / canali esenti | 20 / 50 | Auto Moderation |
| Messaggio personalizzato del blocco | 150 caratteri | Auto Moderation |

### 1.8 Permessi nuovi dal 23/02/2026

| Permesso | A cosa serve | Fonte |
|---|---|---|
| `PIN_MESSAGES` | fissare i messaggi (prima bastava "Gestisci messaggi") | Change log |
| `BYPASS_SLOWMODE` | scrivere ignorando lo slowmode | Change log |
| `CREATE_GUILD_EXPRESSIONS` | creare emoji e sticker ("Gestisci" non basta più) | Change log |
| `CREATE_EVENTS` | creare eventi programmati | Change log |

### 1.9 Intent e crescita

| Limite | Valore | Fonte |
|---|---|---|
| Intent privilegiati | membri, presenze, contenuto dei messaggi | [Privileged Intents](https://support-dev.discord.com/hc/en-us/articles/6207308062871-What-are-Privileged-Intents) |
| Quando serve l'approvazione degli intent | da 10.000 utenti in su, con nuova domanda ogni anno (dal 10/06/2026) | Change log |
| Verifica dell'app | serve per superare i 100 server | [App Verification](https://support-dev.discord.com/hc/en-us/articles/23926564536471-How-Do-I-Get-My-App-Verified) |
| Server per connessione senza "shard" | 2.500 | audit REST (`commands.Bot` oltre non si collega) |
| Messaggi tenuti in memoria da ogni bot | 1000 di default | discord.py `max_messages` |

### 1.10 Voce e Lavalink

| Limite | Valore | Fonte |
|---|---|---|
| Cifratura vocale DAVE | obbligatoria dal 01/03/2026 | Change log (voce del 02/09/2025) |
| Lavalink | versione 4.2.0 o successiva | [Lavalink changelog](https://lavalink.dev/changelog/v4) |
| wavelink | 3.5.1 o successiva (noi: 3.5.2) | [Wavelink releases](https://github.com/PythonistaGuild/Wavelink/releases) |
| Identità di una sessione Lavalink | **un solo** bot (`User-Id`) per nodo | wavelink `node.py`; [Lavalink websocket](https://lavalink.dev/api/websocket.html) |
| Player su un nodo | uno per server (chiave = ID del server) | wavelink `player.py` |
| Connessioni vocali | una per bot per server | Discord |
| YouTube in Lavalink | serve il plugin youtube-source | [youtube-source](https://github.com/lavalink-devs/youtube-source) |

### 1.11 Librerie e servizi esterni

| Servizio | Limite | Valore | Fonte |
|---|---|---|---|
| wavelink | `Pool.connect` | collega i nodi **uno dopo l'altro**; con `retries=None` un nodo morto blocca tutti i successivi | wavelink `node.py`, `websocket.py` |
| wavelink | scelta del nodo | prende quello con meno player: il nodo locale vince sempre | wavelink `node.py` |
| wavelink | `Playable.search` | aggiunge `ytmsearch:` a tutto ciò che non ha un host | wavelink `tracks.py` |
| wavelink | canale vuoto | dopo 3 brani a canale vuoto scatta l'evento "inattivo" | wavelink `node.py`, `player.py` |
| Twitch | `Get Streams` | 100 nomi per richiesta; `first` vale 20 se non indicato | **a memoria**, da ricontrollare |
| YouTube | `search.list` | 100 chiamate al giorno | [Quota](https://developers.google.com/youtube/v3/determine_quota_cost) |
| YouTube | altri metodi | 10.000 unità al giorno; `videos.list` costa 1 e accetta 50 ID | Quota |
| Pixabay | cache | ogni ricerca va tenuta in cache 24 ore | [Pixabay API](https://pixabay.com/api/docs/) |
| Pixabay | immagini | vietato il collegamento diretto permanente; l'indirizzo vale 24 ore | Pixabay API |
| Pixabay | ricerca | testo fino a 100 caratteri; 100 richieste ogni 60 secondi | Pixabay API |
| RSS | cortesia | nessun limite scritto: usare `User-Agent` e `ETag` | buona pratica |
| RSS (nostro) | dimensione e tempo | 2 MB, 15 secondi, 3 redirect | `core/safe_http.py` |
| asyncpg | pool | 5–10 connessioni; tempo massimo 30 s per comando | `core/config.py:325-326`, `core/database.py:81-82` |
| Aiven gratuito | connessioni | 20 in tutto, nessun pooler, si spegne se inattivo | [Aiven free](https://aiven.io/docs/products/postgresql/concepts/pg-free-tier) |
| PostgreSQL | colonna `SERIAL` | finisce a circa 2,1 miliardi | REVIEW PERF-3 |
| aiohttp (server) | corpo della richiesta | 1 MiB di default | aiohttp |
| aiohttp (client) | sessioni | ogni `ClientSession` va chiusa | aiohttp |
| Pillow (nostro) | immagini | 16 megapixel (4 per WebP e JPEG progressivo), ridotte a 2048 px, allegato fino a 8 MB | `core/safe_image.py` |
| Token OAuth Discord | durata | circa 7 giorni, poi va rinnovato con il `refresh_token` | OAuth2 (`expires_in`) |

---

## Parte 2 — Cambiamenti della piattaforma che ci toccano

| Quando | Cosa è cambiato | Cosa rompe in iYokai | Dove si risolve |
|---|---|---|---|
| Luglio 2025 | I bot non possono più creare server. discord.py 2.6 segna deprecati `create_guild` e `Guild.delete`. | **Tutto il backup**: `/define-backup` fallisce, quindi niente coppia, niente mirror, niente snapshot, niente `/restore-users`, niente `/promuovi-backup`. Il token del Creator è ancora obbligatorio all'avvio. | D8, fase F3 (`LIM-39`) |
| 23/02/2026 | Permessi divisi: `PIN_MESSAGES`, `BYPASS_SLOWMODE`, `CREATE_GUILD_EXPRESSIONS`, `CREATE_EVENTS`. | Oggi niente: il bot chiede Amministratore e non fissa messaggi. **Con il backup nuovo** il bot clona emoji e sticker non da proprietario: gli serve `CREATE_GUILD_EXPRESSIONS`. | F3 |
| 01/03/2026 | Voce solo cifrata (DAVE). | Un nodo Lavalink più vecchio della 4.2.0 non entra in vocale (codice di chiusura 4017). `requirements.txt` accetta wavelink 3.4.0, che non basta. I nodi pubblici hanno versione sconosciuta. | D10, F2 (`LIM-54`) |
| 03/03/2026 | Comandi del menu contestuale: 15 per tipo. | Niente. È spazio in più per funzioni nuove (es. "Segnala messaggio"). | F9 |
| 10/06/2026 | Intent privilegiati: conta il numero di **utenti** (10.000), con domanda da rifare ogni anno. | I documenti dicevano "100 server". La verifica dell'app a 100 server resta: sono due regole diverse. | D11 (`LIM-56`) |
| 03/09/2026 | File fino a 20 MiB. | discord.py 2.7.1 crede ancora 10 MiB. Nessun danno: restiamo sotto i 10. | `LIM-55` |
| 16/11/2026 | Canali nascosti "offuscati": il bot li vede come `___hidden___`, con un solo permesso finto. | Backup: copierebbe il nome finto. Anti-nuke: ricreerebbe `___hidden___`. Log avanzati: finte rinomine quando il bot perde o prende accesso. | `LIM-38`, F3 e F6 |

---

## Parte 3 — Dove il codice supera o ignora un limite

Stato: 🔴 da sistemare · 🟢 già protetto.
Ogni `LIM-n` è assegnato a una fase in
[`../02-piano/PRIORITA.md`](../02-piano/PRIORITA.md).

### 3.1 Testi troppo lunghi e liste che crescono

| Codice | Dove | Limite | Come succede | Stato |
|---|---|---|---|---|
| LIM-1 | Tutte le opzioni di testo libero dei comandi (97) | 6000 caratteri accettati da Discord | Nessuna ha `max_length`. È la causa di quasi tutti i casi qui sotto. | 🔴 |
| LIM-2 | `cogs/utility/poll.py:70-75` (`/poll`) | risposta 55, domanda 300 | Una risposta di 56 caratteri: errore generico. | 🔴 |
| LIM-3 | `cogs/voice_temp/voice_temp.py:461` (`/voice rename`), `cogs/tickets/tickets.py:574` (`/ticket rename`) | nome 100; 2 rinomine in 10 minuti | La 3ª rinomina (la 2ª per un ticket, che ne spende una alla creazione, righe 163 e 184) fa dormire il bot fino a 10 minuti. | 🔴 |
| LIM-4 | `cogs/moderation/report.py:94` (`/report`) | campo 1024 | Motivo più lungo: errore non gestito (riga 99 cattura solo `Forbidden`), segnalazione persa. | 🔴 |
| LIM-5 | `cogs/automod/automod.py:474` (`/automod badword-list`) | messaggio 2000 | Si rompe verso le 160 parole; ne può tenere 1000. | 🔴 |
| LIM-6 | `cogs/tickets/tickets.py:219-220` (menu categorie), `:385-401` (`/ticket-category add`), `:432` | 25 opzioni, etichetta 100, emoji valida | La 26ª categoria, un'etichetta lunga o un testo non-emoji bloccano l'apertura dei ticket **per tutti**. È lo stesso errore di `/setup`. | 🔴 |
| LIM-7 | `cogs/utility/restore.py:180-247` (`/restore-users`), `core/restore_orchestrator.py` | token 15 minuti; 429; 10.000 richieste non valide | Con qualche centinaio di utenti il riepilogo finale non arriva. Le chiamate saltano il limitatore di discord.py: un 429 conta come "utente fallito" e avvicina al blocco IP di **tutti e 7 i bot**. I contatori salgono prima di sapere l'esito. Nessuna pausa tra i DM. | 🔴 |
| LIM-8 | `cogs/moderation/actions.py:153,201,268,356`, `softban_mute.py:64,184`, `case_system.py:82,105` | motivo 512 (audit log), campo 1024, descrizione 4096 | Motivo di 513 caratteri: il caso e il DM "sei stato bannato" partono, il ban no. Oltre 1024: `/modcase view` si rompe per quel caso. | 🔴 |
| LIM-9 | `cogs/security/verify.py:79-130,180` | 3 secondi | Quattro letture, ruolo e log prima della risposta. In un'ondata di ingressi l'utente vede "interazione fallita" anche se il ruolo arriva. | 🔴 |
| LIM-10 | `cogs/utility/greetings.py:59,68,87,118`, anteprima `:280` | messaggio 2000 | Testo accettato alla configurazione, rifiutato all'invio in silenzio. L'anteprima va in errore. | 🔴 |
| LIM-11 | `cogs/utility/sticky_messages.py:62` | messaggio 2000 | Cattura solo `Forbidden`: ogni messaggio nel canale genera un errore. | 🔴 |
| LIM-12 | `cogs/utility/scheduled_messages.py:55` | messaggio 2000 | Il messaggio programmato non parte, senza avviso. | 🔴 |
| LIM-13 | `cogs/utility/reminders.py:57,68,148` | messaggio 2000, descrizione 4096 | Promemoria perso in silenzio; la lista di 25 promemoria può superare 4096. | 🔴 |
| LIM-14 | `cogs/security/permission_heatmap.py:89` | descrizione 4096 | Circa 40 ruoli con permessi critici (contano anche i ruoli dei bot). | 🔴 |
| LIM-15 | `cogs/logging/logs_query.py:74,108`, esportazione | descrizione 4096; file | 25 voci con dettagli lunghi. L'esportazione manda tutto lo storico in un file senza controllo di dimensione. | 🔴 |
| LIM-16 | `cogs/utility/feed_alerts.py:328` (`/alerts list`) | descrizione 4096 | Circa 30 feed. Nessun tetto per server. | 🔴 |
| LIM-17 | `cogs/utility/role_menus.py:58,68,71,86,101,160,496` | campo 1024; etichetta; emoji; menu con 0 opzioni | 25 opzioni con etichette lunghe superano 1024: la modifica fallisce ma l'admin legge "Opzione aggiunta". Titolo, descrizione ed etichetta senza limite. Togliere l'ultima opzione di un menu a tendina lo lascia rotto. | 🔴 |
| LIM-18 | `cogs/leveling/leveling.py:573` (lista ruoli premio), `:650` (negozio), `:732`, `:1087`, `:1142`, comando `/giveaway` | 4096; 256; 512 | Lista ruoli oltre 80 righe; negozio senza tetto; nome clan oltre 256 rompe `/clan info` per sempre; nome oggetto lungo: monete spese, ruolo non dato; premio del giveaway oltre 243 caratteri. | 🔴 |
| LIM-19 | `cogs/logging/basic_logs.py:290-300` | campo 1024 | 42 ruoli cambiati insieme (es. punizione anti-nuke): errore non gestito. | 🔴 |
| LIM-20 | `cogs/security/spam_trap.py:815`, `:929-935` | campo 1024; file | Una riga per canale ripulito: oltre 1024 il log del ban non esce. Il transcript HTML parte senza controllo di dimensione, **dopo** che il blocco di 24 ore è già scattato. | 🔴 |
| LIM-21 | `cogs/music/player.py:608`, `:920` (`/nonstop-main list-tracks`) | titolo 256; 4096 | Titolo del brano come titolo dell'embed; playlist radio oltre 80 brani. | 🔴 |
| LIM-22 | `cogs/utility/owner_premium.py:109-116,163` (pannello), `:293` (`premium-list`), `:760` (eval), `:900`, `:991` (liste blacklist) | 2000; 4096; 25 | `premium-list` è a 1759 caratteri su 2000 con 32 moduli: altri 4 moduli lo rompono. Liste blacklist oltre 52 righe. Codice eval oltre 4086 caratteri. Pannello premium senza controllo a 25. | 🔴 |
| LIM-23 | `cogs/utility/command_search.py:75` (`/search`) | descrizione 4096 | Il testo cercato viene ricopiato nella risposta. | 🔴 |
| LIM-24 | `cogs/fun/entertainment.py:374,392,413` (`/fun animal`, `/fun search-image`) | 3 secondi; titolo 256 | Aspettano un sito esterno (fino a 10 s) senza `defer`. Il testo cercato va nel titolo. | 🔴 |

### 3.2 Lavoro lento prima della prima risposta e bottoni che muoiono

| Codice | Dove | Limite | Come succede | Stato |
|---|---|---|---|---|
| LIM-25 | `cogs/leveling/leveling.py:993` (`clan crea`), `:1254` (`clan sciogli`), `:1304,1349,1403,1474` (invita, espelli, promuovi, compra-canale), `:891` (`/assegna-lobby`); `cogs/security/spam_trap.py:197` (bottone Unban); `cogs/utility/suggestions.py:189-202`; comandi musicali di `cogs/music/player.py` che parlano con Lavalink; `kick`, `ban`, `tempban`, `softban` | 3 secondi | Più chiamate a Discord prima di rispondere. `clan sciogli` cancella ogni canale e poi risponde. È LC-3 di REVIEW. | 🔴 |
| LIM-26 | `cogs/voice_temp/voice_temp.py:83` (bottoni piattaforma, `timeout=300`), `cogs/security/spam_trap.py:161` (appello, in memoria), `cogs/leveling/leveling.py:181` | View non persistenti | I bottoni piattaforma muoiono dopo 5 minuti in un canale che vive ore. I bottoni di appello muoiono a ogni riavvio (LC-5). | 🔴 |

### 3.3 Azioni su Discord

| Codice | Dove | Limite | Come succede | Stato |
|---|---|---|---|---|
| LIM-27 | `core/backup_mirror_dispatch.py:95` | nome webhook | Un utente con "discord" o "clyde" nel nome: il messaggio non viene copiato. Regola non riverificata. | 🔴 |
| LIM-28 | `core/backup_clone_logic.py:165,294,323` | 96 kbps; 15 webhook per canale | Copia la qualità audio di un server con boost in uno senza: errore, clonazione interrotta. 15 webhook copiati + 1 del mirror = 16. Il webhook "iYokai Mirror" non viene riusato. | 🔴 |
| LIM-29 | `cogs/automod/automod.py:281-337`, `core/automod_sync.py` | parola 60 caratteri; 6 regole; lista eccezioni | Una parola di 61 caratteri viene salvata e poi rompe **ogni** sincronizzazione. Il tetto di 6 regole non è gestito. `edit()` cancella le eccezioni messe a mano dall'admin. | 🔴 |
| LIM-30 | `cogs/moderation/softban_mute.py:84-101`, `cogs/security/anti_raid.py:53-66` | 250 ruoli; tipi di canale | I ruoli Muted e Quarantined non coprono thread, forum, chat dei vocali, canali palco e canali creati dopo. `create_role` cattura solo `Forbidden`. | 🔴 |
| LIM-31 | `cogs/security/anti_nuke.py:84`, `core/soundboard_log_service.py:80` | ritardo del registro di controllo; 403 | L'anti-nuke legge il registro subito e una volta sola: se la voce non c'è ancora, l'azione non viene contata. Il servizio soundboard fa 3 letture per server ogni 5 minuti, ma discord.py 2.7.1 ha gli eventi soundboard. | 🔴 |
| LIM-32 | `cogs/automod/escalation.py:48` | un evento per azione | Una regola con "blocca" + "avvisa" conta due infrazioni. | 🔴 |
| LIM-33 | `core/music_worker_bot.py:20` | 2.500 server senza shard | I worker musicali sono `commands.Bot`: oltre 2.500 server non si collegano. Conta per l'obiettivo dei 10.000. | 🔴 |
| LIM-34 | `cogs/music/player.py:318` e avvio della radio | canale palco, canale pieno, tempo scaduto | Nessuno dei tre casi è gestito. | 🔴 |
| LIM-35 | `cogs/utility/greetings.py:66-70` | DM di massa | Un DM di benvenuto per ogni ingresso, senza pausa, anche durante un raid. | 🔴 |
| LIM-36 | `cogs/security/spam_trap.py:375,385`, `cogs/utility/restore.py:289-291` | 500 canali; 1000 inviti | Creazione di canali e inviti senza gestire il tetto. | 🔴 |
| LIM-37 | `core/restore_orchestrator.py:80` | il token dura circa 7 giorni | Esiste solo lo scambio iniziale; il `refresh_token` salvato non viene mai usato. Dopo una settimana ogni consenso raccolto è inutile. | 🔴 |
| LIM-38 | `core/backup_clone_logic.py:138-182`, `cogs/security/anti_nuke.py:297-310`, `cogs/logging/advanced_logs.py:139-147,258-276` | canali offuscati dal 16/11/2026 | Vedi Parte 2. | 🔴 |
| LIM-39 | `core/backup_orchestrator.py:62,106,128,167-170`, `core/backup_creator_bot.py`, `core/config.py:138` | i bot non creano server | Vedi Parte 2. `YOKAI_CREATOR_TOKEN` è obbligatorio: senza, il bot non parte. | 🔴 |

### 3.4 Musica

| Codice | Dove | Limite | Come succede | Stato |
|---|---|---|---|---|
| LIM-40 | `cogs/music/player.py:1099`, `:318` | un bot per sessione Lavalink | Tutti i nodi sono collegati con il bot **principale**. I 5 worker usano quella sessione: Lavalink si presenta a Discord con l'identità sbagliata. Quasi certamente **nessun audio** dai worker (da provare live). La radio e un worker nello stesso server si sovrascrivono. | 🔴 |
| LIM-41 | `cogs/music/player.py:84-110,1094-1099`, `main.py` (spegnimento) | `Pool.connect` in sequenza | Se il primo nodo pubblico è morto, nessun altro nodo si collega, nemmeno quello locale. `Pool.close()` non viene mai chiamato: sessioni lasciate aperte. | 🔴 |
| LIM-42 | `cogs/music/player.py:280` | scelta del nodo | "Prima i pubblici, poi il locale" è al contrario. La ricerca sceglie un nodo per conto suo. | 🔴 |
| LIM-43 | `cogs/music/player.py:794,867`, `core/music_logic.py` | `ytmsearch:` | `local:` e `spotify:` diventano ricerche su YouTube Music. È BUG-10. | 🔴 |
| LIM-44 | `core/memory_guard.py:90-97`, `core/music_fleet.py:135` | canale vuoto | La radio 24/7 viene scollegata: dal controllo memoria ogni 60 secondi e dall'evento "inattivo" dopo 3 brani. | 🔴 |
| LIM-54 | `requirements.txt:15`, `core/music_logic.py:39-45` | wavelink ≥ 3.5.1, Lavalink ≥ 4.2.0 | `wavelink>=3.4.0`. Nessun controllo della versione del nodo. Cinque nodi pubblici scritti nel codice, di versione ignota. | 🔴 |

### 3.5 Servizi esterni, database, processi

| Codice | Dove | Limite | Come succede | Stato |
|---|---|---|---|---|
| LIM-45 | `core/youtube_watcher.py:41-106` | 100 `search.list` al giorno | 288 chiamate al giorno **per canale**. Un canale finisce la quota in 8 ore e 20 minuti; tre canali in meno di 3 ore. È BUG-16. | 🔴 |
| LIM-46 | `core/twitch_watcher.py:118-129` | 100 nomi; `first` 20 | Oltre 100 iscrizioni: errore 400, alert fermi per tutti. Con più di 20 streamer in diretta gli altri risultano "offline". Un 401 non svuota il token. | 🔴 |
| LIM-47 | `core/scheduler.py:275-292` | una connessione e un blocco di riga tenuti durante chiamate a Discord | Dopo BUG-27 è una transazione per azione, ma la chiamata a Discord avviene ancora **dentro** la transazione. | 🔴 |
| LIM-48 | `core/image_search_fetcher.py:56-62`, `cogs/fun/entertainment.py:392-413` | condizioni d'uso Pixabay | Nessuna cache, immagine collegata direttamente (sparisce dopo 24 ore), nessun credito, ricerca oltre 100 caratteri data come "nessun risultato". | 🔴 |
| LIM-49 | `core/music_worker_bot.py:22`, `core/backup_creator_bot.py:27` | memoria e CPU | Sei bot secondari con `Intents.default()`: leggono ogni messaggio e tengono 1000 messaggi in memoria ciascuno, senza motivo. | 🔴 |
| LIM-50 | `core/config.py:325-326` | 20 connessioni su Aiven gratuito | Bot sul server + bot di prova sul PC = 10 + 10 = 20: tutte. | 🔴 |
| LIM-51 | `core/safe_http.py:204` | cortesia verso i siti | Una sessione nuova per ogni feed, nessun `User-Agent`, nessun `ETag`. Reddit può rallentarci. | 🔴 |
| LIM-52 | `core/oauth_crypto.py:63-87` | rotazione della chiave | Il dato cifrato non dice con quale chiave: la chiave non si può cambiare. | 🔴 |
| LIM-53 | `cogs/music/player.py:1094`, `cogs/utility/backup_mirror.py:24` | task non conservati | Python può eliminarli prima che finiscano. | 🔴 |
| LIM-55 | `Guild.filesize_limit` di discord.py; transcript e esportazioni | 10 MiB per la libreria | Tutti i file generati vanno tenuti sotto 10 MiB (o divisi). | 🔴 |
| LIM-56 | `cogs/moderation/clear.py` (docstring), `core/backup_reminder_logic.py:23` | testi superati | Parlano di "intent spento" e di "10 server per i bot". | 🔴 |
| LIM-57 | albero comandi | 100 comandi; 25 per gruppo | 97 su 100 e `/owner` 25 su 25: il 4° comando nuovo fa sparire in silenzio i comandi dell'ultimo cog caricato. | 🔴 |

### 3.6 Segnalati dai controlli e già sistemati

| Dove | Problema | Stato |
|---|---|---|
| `cogs/utility/setup.py` | Menu oltre 25 opzioni (BUG-2) | 🟢 `c9534fb` |
| `cogs/fun/entertainment.py` (comandi immagine) | Nessun `defer`, file troppo grande (SEC-20) | 🟢 `b2303a5` |
| `cogs/utility/config_history.py` | Conferma oltre 2000, storico oltre 4096 (BUG-32) | 🟢 `c2a9582` |
| `main.py`, worker di `core/` | Avviati prima del login (BUG-19) | 🟢 `fba882e`, `b0d5302` |
| `core/music_fleet.py` | Worker non partito (`user=None`) | 🟢 `b1452be` |
| `core/safe_http.py` | URL malformato ferma i feed (BUG-20) | 🟢 `c5ebd0f` |

### 3.7 Controllati e a posto

- Timeout fino a 28 giorni; slowmode 0–21.600; ban con cancellazione
  fino a 7 giorni.
- `/clear` fermo a 200; cancellazione in blocchi da 100 e a mano oltre
  i 14 giorni.
- 50 canali per categoria (vocali temporanei, ticket, clan).
- Emoji, sticker e suoni: contati e saltati se non c'è posto.
- Role menu: massimo 20 reazioni, 25 bottoni, 25 opzioni.
- Moduli: titoli ed etichette entro 45 caratteri, al massimo 3 campi.
- Testi di feed e webhook tagliati a 2000; contenuto del mirror a 2000.
- Classifiche con 10 righe; membri di un clan fino a 50.
- View persistenti di ticket, verify, vocali, giveaway, role menu,
  suggerimenti: registrate all'avvio.
- Il bot principale è `AutoShardedBot`.

---

## Parte 4 — Lista di controllo prima di scrivere una funzione nuova

Rispondi sì o no. Se una risposta è "no", sistema prima di scrivere il
resto.

1. **Menu a tendina:** ogni menu costruito con dati del server ha al
   massimo 25 opzioni, oppure è diviso in pagine?
2. **Etichette:** ogni etichetta, valore e descrizione di un'opzione è
   tagliata a 100 caratteri? Le emoji sono controllate prima di usarle?
3. **Testo libero:** ogni opzione di testo di un comando ha `max_length`
   (nome di canale 100, motivo 512, risposta di sondaggio 55…)?
4. **Embed:** titolo entro 256, descrizione entro 4096, campo entro
   1024, al massimo 25 campi, e il totale entro 6000?
5. **Liste:** ogni lista che cresce con i dati (ruoli, feed, oggetti,
   casi, brani) ha un tetto o le pagine?
6. **Messaggi salvati:** un testo scritto dall'admin viene controllato
   **quando lo salva** (2000 caratteri dopo aver sostituito i
   segnaposto), non quando parte?
7. **Tre secondi:** se il comando fa più di una chiamata a Discord, a un
   sito o a Lavalink, chiama `defer()` per prima cosa?
8. **Quindici minuti:** se il lavoro può durare più di 15 minuti, il
   riepilogo va in un messaggio nel canale e non in `followup`?
9. **Motivo:** ogni `reason=` mandato a Discord è tagliato a 512?
10. **Ordine:** prima l'azione su Discord, poi il caso, il log e il DM?
    (Mai un caso o un addebito per un'azione che poi fallisce.)
11. **Errori:** si cattura `discord.HTTPException`, non solo `Forbidden`?
12. **Rinomine:** una rinomina di canale è protetta dal limite di 2 ogni
    10 minuti?
13. **File:** ogni file mandato resta sotto 10 MiB, o viene diviso?
14. **Bottoni:** se il messaggio deve vivere oltre un riavvio, la View è
    persistente (`timeout=None`, `custom_id` fisso, `add_view` all'avvio)?
15. **Comandi:** la funzione entra in un gruppo esistente senza superare
    25 sotto-comandi? Nessun comando di primo livello nuovo?
16. **Risorse del server:** si controllano i tetti (250 ruoli, 500
    canali, 50 per categoria, 15 webhook per canale, 6 regole AutoMod)?
17. **Cicli lunghi:** un ciclo su molti utenti o server ha una pausa,
    rispetta i 429 e isola l'errore di un singolo elemento?
18. **Servizi esterni:** conosco quota, cache richiesta e condizioni
    d'uso del servizio? Ho scritto il numero in questo file?
19. **Database:** nessuna chiamata a Discord dentro una transazione
    aperta? La tabella nuova ha una regola di pulizia?
20. **Canali nascosti:** il codice ignora i canali chiamati
    `___hidden___`?
