# MODIFICHE_ESISTENTE.md — Cosa cambiare in ciò che esiste già

Qui c'è, area per area, quello che iYokai **ha già** ma che è rotto,
incompleto o migliorabile. Per le funzioni che mancano del tutto vedi
[`NUOVE_FUNZIONI.md`](NUOVE_FUNZIONI.md).

Come leggere ogni voce:
- **Codice**: rimanda a [`../01-analisi/REVIEW.md`](../01-analisi/REVIEW.md)
  (SEC-, BUG-, LC-, GDPR-, DB-, PERF-) o a
  [`../01-analisi/LIMITI.md`](../01-analisi/LIMITI.md) (LIM-).
- **Fase**: quando si fa, secondo [`PRIORITA.md`](PRIORITA.md).
- ⚡ = **poche righe di codice**. Si può fare subito, sempre con il suo
  test.
- "Modello" = il bot da cui copiare l'idea, spiegato in
  [`../01-analisi/CONFRONTO_BOT.md`](../01-analisi/CONFRONTO_BOT.md) §6.

Regola valida per tutte: prima il test che fallisce, poi la modifica
(vedi `CLAUDE.md`).

---

## 1. Moderazione

**File:** `cogs/moderation/actions.py`, `softban_mute.py`,
`channel_control.py`, `clear.py`, `case_system.py`, `report.py`,
`_shared.py`, `core/moderation_validation_logic.py`.

**Cosa c'è oggi:** warn, kick, ban, tempban, softban, timeout, mute con
ruolo, unban, lock, slowmode, clear, casi numerati, note, segnalazioni.

| # | Cosa non va | Modifica | Test | Fase |
|---|---|---|---|---|
| 1.1 | **SEC-1**: nessun comando controlla i permessi. Chiunque può bannare. | Gruppi `/mod` e `/modban` con `default_permissions` (D2). Dentro i comandi restano solo i controlli di gerarchia. | Per ogni comando: un membro senza permessi viene rifiutato. | F7 |
| 1.2 ⚡ | **LIM-8**: il motivo può superare 512 caratteri (registro di Discord). | `app_commands.Range[str, 3, 512]` sull'opzione `reason` dei 9 comandi. | Motivo di 513 caratteri rifiutato da Discord prima di arrivare al bot (test sui metadati dell'opzione). | F1 |
| 1.3 | **LIM-8**, REVIEW §5: il caso e il DM partono **prima** dell'azione. Se il ban fallisce resta un caso finto. | Ordine nuovo in `actions.py` e `softban_mute.py`: azione → caso → log → DM. Catturare `discord.HTTPException`, non solo `Forbidden`. | Ban che fallisce: nessun caso, nessun DM. | F1 |
| 1.4 | **LIM-25**, LC-3: kick, ban, tempban e softban rispondono dopo più chiamate. | `defer()` come prima riga, risposta con `followup`. | Il callback chiama `defer` prima di ogni altra cosa. | F1 |
| 1.5 ⚡ | **LIM-4**: `/report` con motivo oltre 1024 perde la segnalazione. | `Range[str, 3, 1000]` sul motivo; `except discord.HTTPException` in `report.py:99`. | Motivo lungo rifiutato; errore di invio gestito. | F1 |
| 1.6 | **LIM-8**: `/modcase history` e `/modnote list` possono superare 4096. | Tagliare ogni riga e fermarsi a 4000 caratteri con "…e altri N". | 20 note lunghe: un solo embed valido. | F1 |
| 1.7 | **LIM-30**: il ruolo Muted non copre thread, forum, chat dei vocali, palchi e canali nuovi. | In `softban_mute.py`: negare anche `send_messages_in_threads`, `create_public_threads`, `create_private_threads`, `add_reactions`, `connect`; ascoltare `on_guild_channel_create` per i canali nuovi; catturare `HTTPException` su `create_role`. | Canale creato dopo: ha il blocco. | F1 |
| 1.8 | REVIEW §12 (5.10): `/lock`, `/unlock`, `/slowmode`, `/clear`, `/untimeout`, `/unmute-role`, scadenza dei tempban non lasciano traccia. | Scrivere un evento di moderazione tramite il router dei canali (NF-01). | Ogni comando produce una riga di log. | F6 |
| 1.9 | REVIEW §5: `duration_logic` accetta `9999999999w`. ⚡ | Tetto massimo (5 anni) in `core/duration_logic.py`. | `9999999999w` rifiutato con messaggio chiaro. | F1 |
| 1.10 | Soglie sui warn manuali (modello: Carl-bot). | Estendere la scala di `cogs/automod/escalation.py` ai warn dati a mano. | 3 warn manuali fanno scattare l'azione configurata. | F9 |

---

## 2. AutoMod

**File:** `cogs/automod/automod.py`, `cogs/automod/escalation.py`,
`core/automod_sync.py`, `core/automod_advanced_logic.py`,
`core/automod_rate_tracker.py`.

**Cosa c'è oggi:** parole vietate e inviti con l'AutoMod nativo; link,
spam, emoji, sticker, maiuscole, zalgo, menzioni, allegati lato bot;
azioni combinabili; scala di escalation.

| # | Cosa non va | Modifica | Test | Fase |
|---|---|---|---|---|
| 2.1 | **BUG-5**: i filtri lato bot leggevano messaggi vuoti. L'intent ora è acceso nel codice. | Riprovare ogni filtro con messaggi finti **con** contenuto. | Un test per filtro. | F1 |
| 2.2 | **LIM-29**: una parola oltre 60 caratteri rompe ogni sincronizzazione. ⚡ | `Range[str, 1, 60]` in `/automod badword-add`. | Parola di 61 caratteri rifiutata. | F1 |
| 2.3 | **LIM-29**, REVIEW §4: `edit()` cancella espressioni regolari e lista delle eccezioni messe a mano. | In `core/automod_sync.py`: leggere la regola e ricostruire il trigger con **tutti** i campi. Gestire il tetto di 6 regole con un messaggio chiaro. | Sincronizzazione su una regola con eccezioni: le eccezioni restano. | F1 |
| 2.4 ⚡ | **LIM-5**: `/automod badword-list` si rompe verso le 160 parole. | Mandare l'elenco come file di testo se supera 1900 caratteri. | 1000 parole: risposta valida. | F1 |
| 2.5 | REVIEW §4: `seconds=` dei filtri anti-spam viene salvato e ignorato. | Passare il valore salvato a `core/automod_rate_tracker.py`. | Finestra di 5 secondi rispettata. | F1 |
| 2.6 | REVIEW §4: lista nera dei link aggirabile (`evil.com:443`, `x@evil.com`, `sub.evil.com`). | Normalizzare con `urllib.parse` in `core/automod_advanced_logic.py`. | I tre casi vengono bloccati. | F1 |
| 2.7 | **LIM-32**, REVIEW §4: una violazione conta due volte; conteggio non atomico. | In `escalation.py`: contare una volta per messaggio; `UPDATE … RETURNING`. | Regola con due azioni: +1, non +2. | F1 |
| 2.8 | Link di phishing (modello: Captcha.bot). | Vedi NF-31. | — | F13 |

---

## 3. Sicurezza (anti-raid, anti-nuke, spam-trap, ban globale)

**File:** `cogs/security/anti_raid.py`, `anti_nuke.py`, `spam_trap.py`,
`global_ban.py`, `permission_heatmap.py`, `security_score.py`,
`invite_sync.py`, `core/security_logic.py`.

| # | Cosa non va | Modifica | Test | Fase |
|---|---|---|---|---|
| 3.1 ⚡ | **BUG-11** (prima metà): l'anti-nuke conta anche le azioni del bot stesso. | Saltare `bot.user.id` nei conteggi di `anti_nuke.py`. | Il bot ricrea 10 canali: nessuna punizione. | F1 |
| 3.2 | **BUG-11** (seconda metà): `strip_roles` non funziona sui bot. | Se l'autore è un bot con ruolo gestito: kick o ban. | Bot che cancella canali: espulso. | F1 |
| 3.3 | **LIM-31**, REVIEW §4: una sola lettura del registro, subito. | Riprovare 2–3 volte con breve attesa; controllare **prima** se il modulo è attivo (PERF-5). | Voce del registro che arriva dopo 2 secondi: azione contata. | F1 |
| 3.4 | REVIEW §12 (7.2), #30: il recupero ricrea solo canali testuali. | Ricreare anche vocali, categorie e forum, con posizione e argomento. Ignorare `___hidden___` (**LIM-38**). | Un test per tipo di canale. | F1 |
| 3.5 | Modello Wick: una soglia sola, punizione dura. | Due soglie (al minuto e all'ora) e **quarantena** come punizione di default. Filtro "chi può aggiungere bot". | Soglia oraria superata lentamente: quarantena. | F13 |
| 3.6 ⚡ | **BUG-12**, LC-6: l'anti-raid conta anche i bot aggiunti dagli admin. | `if member.bot: return` in `anti_raid.py`. | Ingresso di un bot: nessun conteggio. | F1 |
| 3.7 | **BUG-12**, #27: un solo ingresso senza avatar fa scattare il blocco; il livello di verifica resta alto per sempre; più ruoli Quarantined; un DM per ingresso. | Il blocco scatta solo sulla soglia di ingressi. Scadenza del blocco con ripristino del livello di prima. `asyncio.Lock` per server sulla creazione del ruolo. Un solo DM per episodio. | I quattro casi. | F1 |
| 3.8 | **LIM-30**: il ruolo Quarantined ha gli stessi buchi del ruolo Muted. | Stessa modifica di 1.7, in `anti_raid.py`. | Canale nuovo: bloccato. | F1 |
| 3.9 | **LC-5**, **LIM-26**: i bottoni di appello muoiono a ogni riavvio. | View persistente in `spam_trap.py`: `timeout=None`, `custom_id` con l'ID del caso, `bot.add_view` all'avvio. | Dopo un "riavvio" simulato il bottone risponde. | F1 |
| 3.10 | **LIM-20**: log del ban e transcript senza controllo di dimensione. | Tagliare l'elenco dei canali a 1000 caratteri. Controllare il peso del transcript; mandarlo **prima** di segnare il blocco di 24 ore. | 60 canali ripuliti: log valido. | F1 |
| 3.11 | **LIM-25**: il bottone Unban lavora prima di rispondere. | `defer()` e poi `edit_original_response`. | `defer` chiamato per primo. | F1 |
| 3.12 | REVIEW §12 (7.3): nel log mancano data del ban e data di ingresso. | Leggere `joined_at` **prima** del ban; aggiungere la data del ban. | Embed con entrambe le date. | F1 |
| 3.13 | **LIM-36**: creazione dei canali trappola senza gestire i tetti. | Catturare `HTTPException` e spiegare. | Server a 500 canali: messaggio chiaro. | F1 |
| 3.14 | REVIEW §4 e §12 (3.3): `/global-ban enable` e altri 5 moduli "premium" non controllano il premium. | Aggiungere il controllo `requires_module` a log avanzati, spam-trap, anti-nuke, anti-raid, global-ban, heatmap. | Con premium spento il modulo rifiuta. | F1 |
| 3.15 | **LIM-14**: `/permission-heatmap` oltre 4096 con molti ruoli. ⚡ | Fermarsi a 4000 caratteri con "…e altri N ruoli". | 60 ruoli critici: embed valido. | F1 |
| 3.16 | LC-8: `/security-score` pubblica la situazione di sicurezza a tutti. ⚡ | Risposta effimera. | La risposta è `ephemeral`. | F1 |
| 3.17 | LC-6: `on_ready` scarica gli inviti di tutti i server; attribuzione sbagliata con ingressi simultanei. | Scaricare solo dove serve; un blocco per server in `core/invite_tracker.py`. | Due ingressi insieme: attribuzioni giuste o "sconosciuto". | F1 |
| 3.18 | Il canale degli allarmi anti-nuke si imposta solo dall'anti-raid. | Impostazione propria tramite il router (NF-01). | Allarme con solo l'anti-nuke attivo. | F6 |

---

## 4. Verify

**File:** `cogs/security/verify.py`, `core/verify_logic.py`.

| # | Cosa non va | Modifica | Test | Fase |
|---|---|---|---|---|
| 4.1 | **LIM-9**, LC-3: letture, ruolo e log prima della risposta. | `defer(ephemeral=True)` nel bottone; il modulo del captcha resta la prima risposta, il lavoro lento va dopo l'invio del modulo. | `defer` o modulo come prima chiamata. | F1 |
| 4.2 | Captcha debole (una somma). Modello: Wick. | Vedi NF-18 (immagine). | — | F9 |
| 4.3 | Verifica web e account doppi mai costruiti. | Vedi NF-21. | — | F10 |

---

## 5. Log

**File:** `cogs/logging/basic_logs.py`, `advanced_logs.py`,
`logs_query.py`, `core/soundboard_log_service.py`,
`core/event_log_retention.py`.

| # | Cosa non va | Modifica | Test | Fase |
|---|---|---|---|---|
| 5.1 | Un solo canale per tutti i log; niente forum. Modello: Carl-bot. | Router dei canali (NF-01), un post per tipo nel forum (D3). | Vedi NF-01. | F6 |
| 5.2 | Niente log dei messaggi. | NF-02. | — | F6 |
| 5.3 | **LIM-19**: 42 ruoli cambiati insieme rompono l'embed. ⚡ | Tagliare l'elenco dei ruoli a 1000 caratteri in `basic_logs.py`. | 60 ruoli: embed valido. | F1 |
| 5.4 | **LIM-15**: `/logs user` e `/logs channel` oltre 4096; esportazione senza limite di peso. | Tagliare ogni voce; esportazione divisa in più file sotto 10 MiB. | 25 voci lunghe: embed valido. | F1 |
| 5.5 | LC-6: se il bot perde il permesso sul canale, errore e DM di allarme a ogni evento. | Avviso una volta sola (lo fa il router). | Canale senza permesso: un solo avviso. | F6 |
| 5.6 | REVIEW §4: spostare un canale genera N messaggi; il mute volontario è scritto come "mutato dal server". | Raggruppare gli spostamenti; distinguere mute proprio e mute del server. | I due casi. | F6 |
| 5.7 | **LIM-31**, REVIEW §5 e §12: il log del soundboard legge il registro ogni 5 minuti; il primo evento viene saltato. | Usare gli eventi soundboard di discord.py 2.7.1 e togliere il giro periodico. | Evento ricevuto: una riga di log. | F6 |
| 5.8 | **LIM-38**: canali offuscati dal 16/11/2026. | Ignorare `___hidden___` in `advanced_logs.py`. | Canale offuscato: nessun log. | F3 |
| 5.9 | REVIEW §5: il ghost-ping segnala anche i messaggi cancellati dai moderatori. | Controllare chi ha cancellato (registro) prima di segnalare. | Cancellazione da moderatore: nessun avviso. | F6 |

---

## 6. Ticket

**File:** `cogs/tickets/tickets.py`, `core/ticket_logic.py`,
`core/repositories/ticket_repo.py`.

| # | Cosa non va | Modifica | Test | Fase |
|---|---|---|---|---|
| 6.1 | **LIM-6**: 26 categorie, un'etichetta lunga o un'emoji sbagliata bloccano l'apertura per tutti. | In `/ticket-category add`: tetto di 25, etichetta fino a 100, emoji controllata. Nel menu: tagliare e saltare le voci non valide. | 26ª categoria rifiutata; menu sempre costruibile. | F1 |
| 6.2 ⚡ | **LIM-3**: nome del ticket oltre 100 caratteri. | `Range[str, 1, 100]` su `/ticket rename`. | Nome di 101 caratteri rifiutato. | F1 |
| 6.3 | **LIM-3**: la creazione spende una rinomina; la seconda rinomina fa dormire il bot 10 minuti. | Creare il canale direttamente con il numero giusto (riservare il numero prima). Sul limite: risposta "riprova tra N minuti". | Creazione senza `edit(name=…)`. | F1 |
| 6.4 | REVIEW §4: doppio clic apre due ticket. | Vincolo unico in database su (server, utente, aperto). | Due clic insieme: un solo ticket. | F1 |
| 6.5 | REVIEW §4: un canale cancellato a mano blocca l'utente. | Ascoltare `on_guild_channel_delete` e chiudere il ticket. | Canale cancellato: l'utente può riaprire. | F1 |
| 6.6 | REVIEW §4: `claim`, `priority` e `add` senza controllo staff. | Stesso controllo di `forceclose`. | Utente normale rifiutato. | F1 |
| 6.7 | REVIEW §4: `/ticket-support-role remove` non toglie il ruolo storico. | Togliere anche l'impostazione singola vecchia. | Dopo la rimozione il ruolo non vede i ticket. | F1 |
| 6.8 | **BUG-5**: transcript vuoto senza intent. | Riprovare con messaggi con contenuto. Peso sotto 10 MiB (**LIM-55**). | Transcript con testo. | F1 |
| 6.9 | Modello Ticket Tool e Tickets: modulo, più pannelli, chiusura automatica, voto. | NF-13. | — | F9 |

---

## 7. Vocali temporanei

**File:** `cogs/voice_temp/voice_temp.py`, `core/voice_temp_logic.py`.

| # | Cosa non va | Modifica | Test | Fase |
|---|---|---|---|---|
| 7.1 ⚡ | **LIM-3**: `/voice rename` senza limite di lunghezza. | `Range[str, 1, 100]`. | Nome di 101 caratteri rifiutato. | F1 |
| 7.2 | **LIM-3**, REVIEW §4: la terza rinomina in 10 minuti fa scadere il comando. | Contare le rinomine per canale e rispondere "riprova tra N minuti". | Terza rinomina: messaggio, nessuna attesa. | F1 |
| 7.3 ⚡ | **BUG-18** (prima metà): `/voice transfer` accetta bot e utenti fuori dal canale. | Due controlli in testa al comando. | Bot e assente rifiutati. | F1 |
| 7.4 | **BUG-18** (seconda metà): i permessi non passano al nuovo proprietario. | Spostare i permessi del canale. | Il nuovo proprietario può rinominare. | F1 |
| 7.5 | REVIEW §4: canali orfani dopo un riavvio. | Pulizia all'avvio dei canali vuoti registrati. | Canale vuoto all'avvio: cancellato. | F1 |
| 7.6 | **LIM-26**: i bottoni piattaforma muoiono dopo 5 minuti. | View persistente, come il pannello di creazione. | Bottone dopo un "riavvio". | F1 |

---

## 8. Musica

**File:** `cogs/music/player.py`, `core/music_fleet.py`,
`core/music_logic.py`, `core/music_worker_bot.py`,
`core/main_radio_logic.py`, `core/memory_guard.py`. Tutto in fase F2,
decisione D10.

| # | Cosa non va | Modifica | Test |
|---|---|---|---|
| 8.1 | **LIM-40**: i worker usano la sessione Lavalink del bot principale. | Un `wavelink.Node(client=<bot>, identifier=…)` per bot e per server Lavalink. Ogni player nasce con `nodes=[nodo del suo bot]`. | Il player di un worker è sul nodo di quel worker. Prova live obbligatoria. |
| 8.2 | **LIM-41**: un nodo morto blocca gli altri; `Pool.close()` mai chiamato. | Ogni nodo si collega in un task conservato, con `retries` limitati. Chiusura del Pool allo spegnimento. | Primo nodo irraggiungibile: gli altri si collegano. |
| 8.3 | **LIM-42**, REVIEW §4: ordine dei nodi al contrario. | Scelta esplicita: pubblici prima, locale per ultimo; `Playable.search(…, node=…)`. | Ricerca sul nodo scelto. |
| 8.4 | **BUG-10**, **LIM-43**: i brani locali diventano ricerche YouTube. | `Pool.fetch_tracks(<percorso visto dal nodo>, node=locale)`; variabile `LAVALINK_LOCAL_ROOT`; cartella creata all'avvio; nome file controllato. | Brano locale trovato solo sul nodo locale. |
| 8.5 | **LIM-44**: la radio viene scollegata dai canali vuoti. | Esentare il player della radio in `core/memory_guard.py`; `inactive_channel_tokens=None` su quel player. | Radio in canale vuoto: resta. |
| 8.6 | REVIEW §12 (9.2/9.3): un bot per server, non per canale. | `core/music_fleet.py`: assegnazione per (server, canale vocale). | Due canali nello stesso server: due bot, due code. |
| 8.7 | REVIEW §4: `/stop` e `/skip` da un altro canale. | Un controllo comune "sei nel canale del player". | Utente in un altro canale rifiutato. |
| 8.8 | #45: radio automatica quando il bot principale entra in vocale. | Ascolto di `on_voice_state_update` del bot stesso. | Ingresso del bot: radio parte dal punto giusto. |
| 8.9 | #47, #48: nessun Lavalink proprio documentato. | Cartella `deploy/lavalink/` con `docker-compose.yml`, `application.yml` (solo segnaposto) e guida. | — (documentazione) |
| 8.10 ⚡ | **LIM-54**: `wavelink>=3.4.0`. | `wavelink>=3.5.1` in `requirements.txt`; rigenerare `requirements.lock`. | Installazione pulita. |
| 8.11 | **LIM-54**: versione di Lavalink non controllata; nodi pubblici nel codice. | All'avvio leggere `/v4/info` di ogni nodo e scartare quelli sotto 4.2.0. Nodi pubblici solo da `.env`. | Nodo 4.1: scartato con avviso. |
| 8.12 ⚡ | **LIM-49**: i worker leggono ogni messaggio. | `Intents(guilds=True, voice_states=True)` e `max_messages=None` in `core/music_worker_bot.py`. | Il worker ha solo quei due intent. |
| 8.13 | **LIM-33**: i worker non reggono oltre 2.500 server. | `AutoShardedBot` anche per i worker. | Il worker è `AutoShardedBot`. |
| 8.14 | **LIM-34**: canale palco, canale pieno, tempo scaduto. | Messaggi chiari per i tre casi. | Un test per caso. |
| 8.15 | **LIM-21**: titolo del brano oltre 256; playlist radio oltre 80 brani. ⚡ (solo il taglio del titolo) | Tagliare il titolo; pagine per la playlist. | Titolo di 300 caratteri: embed valido. |
| 8.16 | **LIM-25**: comandi che parlano con Lavalink senza `defer`. Questa riga si fa in **F1**, con il resto di LIM-25. | `defer()` in pause, resume, skip, stop, volume, disconnect. | `defer` per primo. |
| 8.17 | REVIEW §11: `main_radio_logic.next_track_index` senza chiamanti. | Usarlo nella radio o toglierlo. | Cricchetto `KNOWN_UNCALLED`. |
| 8.18 | RT-5: nessun test sul collegamento di `music_sessions.clear_all` in `main()`. | Test sul cablaggio. | Righe vecchie sparite all'avvio di `main()`. |
| 8.19 | Player con bottoni e canale richieste (modello: Hydra). | NF-19. | — |

---

## 9. Livelli, economia, clan

**File:** `cogs/leveling/leveling.py`, `core/leveling_logic.py`,
`core/guild_clan_*.py`, repository collegati.

| # | Cosa non va | Modifica | Test | Fase |
|---|---|---|---|---|
| 9.1 | **BUG-14**, #35: `/daily` e `/work` riscuotibili due volte. | Un solo `UPDATE … WHERE (ultimo scaduto) RETURNING`. | Due chiamate insieme: un solo premio. | F1 |
| 9.2 | **BUG-14**, #23: `/shop buy` toglie le monete senza dare il ruolo. | Transazione con vincolo unico; ruolo; rimborso se il ruolo fallisce. Motivo tagliato a 512 (**LIM-18**). | Ruolo non assegnabile: monete restituite. | F1 |
| 9.3 | **BUG-14**: `/cassa sblocca-premium` e `/clan compra-canale` con doppio clic. | Stesso schema di 9.2. | Doppio clic: un solo addebito. | F1 |
| 9.4 | **LC-1**, **LIM-25**: `/assegna-lobby` può addebitare due volte. | `defer()`; addebito e accrediti in **una** transazione, una sola lettura dei membri. | 40 persone: tutto o niente. | F1 |
| 9.5 | **BUG-15**: i clan finanziati con trasferimento vengono cancellati. | Il trasferimento rende "ufficiale" il clan quando copre il debito. | Clan finanziato così: resta. | F1 |
| 9.6 | **BUG-17**: possibile doppio riscatto di un drop. | Test con due clic insieme; se passa, una riga di commento. | `add_coins` chiamato una volta. | F1 |
| 9.7 | REVIEW §4: nessun comando di economia o clan controlla se il modulo è attivo. | Controllo comune in testa ai comandi. | Modulo spento: comando rifiutato. | F1 |
| 9.8 | REVIEW §4: `/clan invita` aggiunge senza consenso; manca `/clan lascia`. | Invito con bottone Accetta; nuovo `/clan lascia`. | Rifiuto dell'invito; uscita dal clan. | F1 |
| 9.9 | REVIEW §4: XP vocale dei clan senza anti-farm. | Stesse regole dell'XP vocale normale (solo nel canale, AFK, sordo). | Utente solo in AFK: zero XP. | F1 |
| 9.10 | REVIEW §4: i decadimenti scattano entro un'ora dalla creazione. | Primo decadimento solo dopo un periodo intero. | Clan nuovo: nessun decadimento. | F1 |
| 9.11 | **LIM-25**: `clan crea`, `sciogli`, `invita`, `espelli`, `promuovi`, `compra-canale` senza `defer`. | `defer()` per primo. | `defer` per primo in ognuno. | F1 |
| 9.12 | **LIM-18**: nome clan, oggetto e premio senza limite; liste senza tetto. ⚡ (solo i `Range`) | `Range` su nome clan (64), nome oggetto (80), premio (200). Pagine per negozio e ruoli premio. | Valori lunghi rifiutati. | F1 |
| 9.13 | REVIEW §12 (15.14): lo storico della tesoreria non si legge; lo scioglimento lascia i ruoli agli altri admin. | Mostrare gli ultimi movimenti in `/clan info`; togliere i ruoli a tutti. | I due casi. | F1 |
| 9.14 | REVIEW §11: il ruolo `co_owner` non si può assegnare. | Aggiungerlo a `/clan promuovi` (massimo 1). | Promozione a co-owner. | F1 |
| 9.15 | REVIEW §4: giveaway in thread o forum senza avviso ai vincitori. | Usare il canale giusto anche per thread e forum. | Vincitore avvisato in un thread. | F1 |
| 9.16 | REVIEW §5: trasferimenti incrociati in stallo; giorno dell'XP vocale in ora locale. | Bloccare le righe in ordine di ID; usare UTC. | Due trasferimenti opposti insieme. | F1 |
| 9.17 ⚡ | LC-6: i messaggi di sistema (boost, pin, ingressi) danno XP. | In `leveling.py`: contare solo i messaggi normali e le risposte. | Messaggio di boost: zero XP. | F1 |
| 9.18 | PERF-4, PERF-6: cicli vocali e decadimenti utente per utente. | Query raggruppate per server; una sola `UPDATE` per il decadimento. | Stesso risultato di prima. | Continuo |
| 9.19 | Rank card, impostazioni XP (modello: MEE6, Arcane). | NF-12, NF-15. | — | F9 |

---

## 10. Utility

**File:** `cogs/utility/*.py`.

| # | Cosa non va | Modifica | Test | Fase |
|---|---|---|---|---|
| 10.1 ⚡ | **LIM-2**: `/poll` con risposta oltre 55 o domanda oltre 300. | `Range[str, 1, 55]` sulle opzioni, `Range[str, 1, 300]` sulla domanda. Portare le opzioni a 10. | Risposta di 56 caratteri rifiutata. | F1 |
| 10.2 | **LIM-10**: benvenuto accettato e poi rifiutato in silenzio; anteprima in errore. | Controllo della lunghezza **dopo** i segnaposto al salvataggio; `try` nell'anteprima. | Testo che diventa 2001 caratteri: rifiutato. | F1 |
| 10.3 ⚡ | **LIM-11**: lo sticky cattura solo `Forbidden`. | `except discord.HTTPException` in `sticky_messages.py:63`. | Errore 400: nessuna eccezione. | F1 |
| 10.4 | REVIEW §4: sticky persi o doppi. | Un blocco per canale intorno a cancella-e-rimanda. | Dieci messaggi veloci: un solo sticky. | F1 |
| 10.5 | **LIM-12**, **LIM-13**: messaggi programmati e promemoria persi in silenzio. | `Range` fino a 1800 sul testo; avviso all'autore se l'invio fallisce; lista promemoria tagliata. | Invio fallito: l'autore lo sa. | F1 |
| 10.6 | D12: i ping di ruolo voluti dall'admin sono muti. | `allowed_mentions` con i ruoli in `scheduled_messages.py`, `greetings.py`, `sticky_messages.py`, solo se chi configura ha "Menziona tutti". | Ping di ruolo attivo; `@everyone` muto. | F1 |
| 10.7 | **LIM-17**, REVIEW §4: role menu. | `Range` su titolo (256), descrizione (2000), etichetta (80); emoji controllata; pubblicare **prima** di salvare l'opzione; dire la verità se la modifica fallisce; cancellare il menu quando resta senza opzioni; rispettare `toggle=False`. | Uno per caso. | F1 |
| 10.8 | Modalità dei reaction roles (modello: Carl-bot). | NF-14. | — | F9 |
| 10.9 | **LIM-25**, REVIEW §5: `/suggest` lavora prima di rispondere; due staff decidono insieme; testo oltre 4096. | `defer()`; `Range` fino a 2000; decisione con `UPDATE … WHERE stato = 'aperto' RETURNING`. Stessa cosa per le richieste di comandi. | Due clic insieme: una sola decisione. | F1 |
| 10.10 ⚡ | **LIM-23**: `/search` ricopia il testo cercato. | `Range[str, 1, 100]` sull'opzione. | Testo lungo rifiutato. | F1 |
| 10.11 | `/search` dà risultati sbagliati e mostra comandi vietati. | Rifatto come `/utility cerca-comando` (NF-06). | — | F8 |
| 10.12 | **LIM-22**: liste e pannello dell'owner vicini ai limiti. | `premium-list` e liste blacklist a pagine; controllo a 25 nel pannello premium; `Range` fino a 4000 sul codice di eval. | 40 moduli: risposta valida. | F1 |
| 10.13 | REVIEW §12 (1.2): `modules_updated` lo emette solo `/setup`. | Emetterlo anche da wizard, import, reset e rollback. | Evento ricevuto in ogni caso. | F1 |
| 10.14 | Il wizard copre 6 moduli su 32. Modello: Carl-bot, Wick, ServerStats. | Wizard per categoria che offre di creare i canali (dopo NF-01). | Ogni categoria ha il suo passo. | F9 |
| 10.15 | REVIEW §11: colonna `guild_config.prefix` morta. | Riusarla per il prefisso dei tag (NF-09) oppure toglierla con una migrazione. | — | F9 |
| 10.16 | **LIM-35**: un DM di benvenuto per ingresso anche durante un raid. | Sospendere i DM quando l'anti-raid è in allarme. ⚡ per `if member.bot: return` (LC-6). | Raid: nessun DM. | F1 |
| 10.17 | Immagine di benvenuto, embed, starboard, tag. | NF-11, NF-17, NF-08, NF-09. | — | F9 |

---

## 11. Feed e alert

**File:** `cogs/utility/feed_alerts.py`, `core/feed_watcher.py`,
`core/twitch_watcher.py`, `core/youtube_watcher.py`,
`core/safe_http.py`, `core/custom_webhook_server.py`.

| # | Cosa non va | Modifica | Test | Fase |
|---|---|---|---|---|
| 11.1 | **BUG-16**, **LIM-45**: quota YouTube finita in poche ore. | D5: leggere il feed RSS del canale, poi una `videos.list` per gruppo di 50 ID e guardare `liveBroadcastContent`. | 10 canali: una chiamata per giro. | F1 |
| 11.2 ⚡ | **LIM-46**: `first` non indicato. | Aggiungere `("first", "100")` ai parametri in `twitch_watcher.py:118`. | Parametro presente nella richiesta. | F1 |
| 11.3 | **LIM-46**: oltre 100 iscrizioni; 401 non gestito. | Togliere i doppioni, blocchi di 100, svuotare il token su 401. | 250 iscrizioni: tre richieste. | F1 |
| 11.4 | **LC-7**: i feed pubblicano anche con il modulo spento. | Controllo del modulo in ogni giro. | Modulo spento: nessun messaggio, nessuna quota. | F1 |
| 11.5 | REVIEW §4: se sparisce l'ultimo elemento visto, il feed ripubblica tutto. | Ricordare la data dell'ultimo pubblicato. | Elemento sparito: nessun doppione. | F1 |
| 11.6 | REVIEW §12 (10.9): modelli di messaggio solo per RSS e webhook. | Modello anche per Twitch e YouTube, con `core/template_renderer.py`. | Modello personalizzato usato. | F1 |
| 11.7 ⚡ | REVIEW §5: `/alerts add` mostra l'ID senza `RSS-`. | Aggiungere il prefisso al messaggio. | Messaggio con `RSS-3`. | F1 |
| 11.8 | **LIM-16**: nessun tetto di feed; lista oltre 4096. ⚡ (solo il taglio della lista) | Tetto per server (es. 25 gratis); lista tagliata. | 26º feed rifiutato. | F1 |
| 11.9 | **LIM-51**, PERF-7: una sessione per feed, nessun `User-Agent`, feed scaricati uno alla volta. | Sessione condivisa, `User-Agent` con il nome del bot, `ETag`; indirizzi uguali scaricati una volta. | Due server, stesso feed: uno scarico. | F1 |
| 11.10 | REVIEW §20: `canale.send` del webhook senza protezione. | `try/except` e risposta 502. | Canale senza permessi: nessun 500. | F1 |
| 11.11 | SEC-16 (residuo): token dei webhook in chiaro. | Salvare l'hash del token. | Ricerca per hash. | F5 |
| 11.12 | Kick, ruolo "in diretta", TikTok, Instagram, X. | NF-32. | — | F13 |

---

## 12. Backup e restore

**File:** `cogs/utility/backup.py`, `backup_mirror.py`, `restore.py`,
`core/backup_*.py`, `core/restore_*.py`, `core/oauth_crypto.py`. Tutto
in fase F3, decisione D8.

| # | Cosa non va | Modifica | Test |
|---|---|---|---|
| 12.1 | **LIM-39**: il flusso crea un server; impossibile. | Nuovo flusso: `/define-backup` salva lo snapshot come dati e, se richiesto, genera un link modello (`Guild.create_template`). Nel server nuovo l'admin lancia il comando di collegamento con un codice. Niente cessione di proprietà. | Collegamento con codice giusto, sbagliato, scaduto. |
| 12.2 | **LIM-39**: Creator ancora nel codice e obbligatorio. | Togliere `core/backup_creator_bot.py`, il cablaggio in `main.py`, `YOKAI_CREATOR_TOKEN` da `core/config.py` e `.env.example`, i "10 posti", `pulisci_server_orfani`, `elimina_server_creato`. | Il bot parte senza il token. Cricchetto dei metodi senza chiamanti aggiornato. |
| 12.3 | Un modello crea già ruoli e canali. | Mappa per **nome** in `core/backup_clone_logic.py`: riusare ciò che esiste, creare il resto. | Clonazione su server da modello: nessun doppione. |
| 12.4 | REVIEW §12 (11.3): ordine dei ruoli. | Impostare le posizioni dopo la creazione. | Gerarchia uguale (prova live). |
| 12.5 ⚡ | **LIM-28**: qualità audio copiata tale e quale. | `bitrate=min(canale.bitrate, int(target.bitrate_limit))` in `backup_clone_logic.py:165`. | Server con boost → senza boost: nessun errore. |
| 12.6 | **LIM-28**: 16 webhook in un canale; webhook del mirror non riusato. | Copiare al massimo 14 webhook; cercare "iYokai Mirror" prima di crearlo. | Canale con 15 webhook: clonazione completa. |
| 12.7 | **LIM-27**: nome del webhook con "discord" o "clyde". | Sostituire le due parole nel nome usato dal mirror. | Utente "Discord Fan": messaggio copiato. |
| 12.8 | **LIM-38**: canali offuscati. | Saltare `___hidden___`; chiedere al bot il permesso di vedere tutti i canali e dirlo se manca. | Canale offuscato: saltato e contato. |
| 12.9 | Permessi nuovi. | Il link d'invito chiede anche `CREATE_GUILD_EXPRESSIONS`. | Il link contiene il permesso. |
| 12.10 | **LIM-37**: i token OAuth non vengono mai rinnovati. | `grant_type=refresh_token` prima dell'uso se il token è scaduto o vicino alla scadenza; salvare il token nuovo. | Token scaduto: rinnovato e usato. |
| 12.11 | **LIM-7**: ciclo di `/restore-users`. | Passare da `discord.http` o rispettare `Retry-After`; pausa tra i DM; contare **dopo** l'esito; riepilogo in un messaggio nel canale. | 429 simulato: attesa e nuovo tentativo. |
| 12.12 | Regola di Discord: niente contatti senza permesso. | L'invito in DM solo a chi ha dato il consenso alla verifica. | Utente senza consenso: nessun DM. |
| 12.13 | **BUG-34**: dopo la promozione `/restore-users` rifiuta. | Conservare la coppia storica. Test sul database prima di cambiare. | Restore dopo la promozione. |
| 12.14 | REVIEW §12: la modalità "OAuth alla verifica" non fa niente di diverso. | Mostrare davvero il link di consenso alla fine della verifica. | Modalità attiva: link mostrato. |
| 12.15 | **LIM-52**, SEC-16 (residui): chiave non ruotabile; cifratura non legata alla riga; una riga rovinata blocca l'elenco. | Prefisso di versione nel dato cifrato; ID di server e utente come dato associato; saltare la riga rovinata con un avviso. | Due chiavi: entrambe leggibili. |
| 12.16 | **LIM-36**: invito classico senza gestire il tetto. Questa riga si fa in **F1**. | Catturare l'errore e spiegare. | Server a 1000 inviti: messaggio chiaro. |
| 12.17 | Modello Xenon: più copie, intervalli, messaggi salvati. | Più snapshot per server con data; salvataggio degli ultimi N messaggi per canale. | Due snapshot: si sceglie quale caricare. |

---

## 13. Owner

**File:** `cogs/utility/owner_premium.py`, `core/premium.py`.

| # | Cosa non va | Modifica | Test | Fase |
|---|---|---|---|---|
| 13.1 | **LIM-57**: `/owner` è a 25 su 25. | Sotto-gruppi `premium`, `blacklist`, `cog`, `system`, `radio`, `privacy`, `ai`; registrato solo nel server dell'owner. | Albero entro i limiti. | F7 |
| 13.2 | REVIEW §12 (17.5): solo il bot principale esce da un server in blacklist. | Far uscire anche i bot musicali. | Server in blacklist: escono tutti. | F1 |
| 13.3 ⚡ | REVIEW §5: `OWNER_ID` non numerico dà un errore poco chiaro. | Messaggio chiaro in `core/config.py`. | Valore "abc": messaggio che nomina la variabile. | F1 |
| 13.4 | Pagamento vero. | NF-22. | — | F10 |

---

## 14. Core

**File:** `main.py`, `core/*.py`.

| # | Cosa non va | Modifica | Test | Fase |
|---|---|---|---|---|
| 14.1 | **LIM-1**: 97 opzioni di testo senza `max_length`. | Un test "a cricchetto" sull'albero: ogni opzione di testo ha un massimo. Poi svuotarlo comando per comando. | Elenco `KNOWN_SENZA_MAX_LENGTH` che si svuota. | F1 |
| 14.2 | **BUG-13**: "non hai i permessi" trattato come errore imprevisto. | In `core/premium.py`: `CheckFailure`, `MissingPermissions`, `NoPrivateMessage` → messaggio effimero chiaro, log INFO. | Tre eccezioni, tre messaggi. | F1 |
| 14.3 | REVIEW §5: un errore "effimero" dopo un `defer` pubblico diventa visibile a tutti. | Nel gestore errori: cancellare la risposta pubblica e mandare un followup effimero. | Errore dopo `defer()`: effimero. | F1 |
| 14.4 | **LIM-47**: lo scheduler chiama Discord dentro una transazione. | Prenotare la riga (stato "in corso"), chiudere la transazione, eseguire, segnare l'esito. | Connessione libera durante l'azione. | F1 |
| 14.5 ⚡ | **LIM-53**: task non conservati. | Tenere il riferimento in `cogs/music/player.py:1094` e `cogs/utility/backup_mirror.py:24`. | Il task è in un insieme del cog. | F1 |
| 14.6 | **LIM-50**: 10 connessioni contro le 20 di Aiven gratuito. | Default 2–5 in sviluppo; nota in `.env.example`. | Valori letti da `.env`. | F1 |
| 14.7 | **LIM-55**: discord.py crede a 10 MiB. | Una funzione comune "manda file" che divide o rifiuta sopra 10 MiB. | File da 12 MiB: diviso. | F1 |
| 14.8 ⚡ | **LIM-56**, D11: testi superati nel codice. | Correggere la docstring di `cogs/moderation/clear.py` e il commento di `core/backup_reminder_logic.py`. | — | F1 |
| 14.9 | REVIEW §4: gara nella cache dei moduli; `bot_stats` cresce senza fine. | Blocco per server nella cache; coda con lunghezza massima. | Due cambi insieme; 1 milione di comandi. | F1 |
| 14.10 | PERF-1, PERF-2: una o più letture del database per ogni messaggio. | Cache delle impostazioni del server e dei tempi di attesa XP con `BoundedCache`. | Stesso risultato, meno query. | Continuo |
| 14.11 | PERF-3, GDPR-3: tabelle che crescono senza fine. | Lavoro di pulizia unico (NF-04); `event_log.id` a `BIGINT`. | Righe vecchie cancellate. | F5 |
| 14.12 | DB-2: una sola chiave esterna in 74 tabelle. | Chiavi esterne dove servono, con migrazioni. | Clan sciolto: nessuna riga orfana. | Continuo |
| 14.13 | REVIEW §9, §11: docstring vecchie, codice morto, copie. | File per file, quando lo si tocca. | Cricchetto `KNOWN_UNCALLED`. | Continuo |
| 14.14 | `core/i18n.py` con 4 frasi. | NF-06. | — | F8 |
| 14.15 | `NSFW_TOKEN` obbligatorio ma non usato. | Facoltativo fino a NF-23. ⚡ | Avvio senza la variabile. | F1 |

---

## 15. Fun

**File:** `cogs/fun/entertainment.py`, `core/image_search_fetcher.py`,
`core/animal_fetcher.py`.

| # | Cosa non va | Modifica | Test | Fase |
|---|---|---|---|---|
| 15.1 ⚡ | **LIM-24**: `/fun animal` e `/fun search-image` aspettano un sito esterno senza `defer`; il testo cercato va nel titolo. | `defer()` come prima riga e risposta con `followup`; `Range[str, 1, 100]` sul testo cercato. | `defer` per primo; testo di 101 caratteri rifiutato. | F1 |
| 15.2 | **LIM-48**: condizioni d'uso di Pixabay non rispettate. | Cache di 24 ore per ricerca; scaricare l'immagine e mandarla come allegato; riga di credito con il link a Pixabay; pausa per utente. | Stessa ricerca due volte: una sola chiamata. | F1 |

