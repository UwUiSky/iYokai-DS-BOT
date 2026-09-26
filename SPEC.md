# SPEC.md — Specifica canonica iYokai + audit dello stato reale

**Questo file è la FONTE DI VERITÀ del progetto.**

Trascritto dallo schema ultra-dettagliato originale della conversazione
di progettazione, foglia per foglia, con a fianco lo stato verificato
contro il codice reale (non contro una roadmap riassunta).

## Perché questo file esiste

Le prime fasi di sviluppo sono state guidate da una roadmap
*riassunta* che io (Claude) avevo derivato dallo schema originale.
Quella compressione ha fatto sparire intere sezioni senza segnalarle
come rimandate, e ogni successivo "controllo" l'ho fatto ricostruendo
a memoria invece di rileggere lo schema — ripetendo lo stesso errore
tre volte di fila. Da qui in avanti: **ogni sessione parte da questo
file, non da un riassunto.**

## Legenda stato

| Simbolo | Significato |
|---|---|
| `[x]` | Fatto e testato |
| `[~]` | Parziale — esiste qualcosa ma non tutto quanto specificato |
| `[ ]` | Mancante — nessun codice |
| `[✗]` | Scartato deliberatamente, con motivo |

---

# A. iYOKAI BOT (guild-installed)

## §1 CORE SYSTEM

- `[x]` 1.1 Multi-Tenant Engine — isolamento config per Guild ID
- `[x]` 1.1 Attivazione/disattivazione feature per server (check runtime)
- `[✗]` 1.1 "Scaricamento moduli non utilizzati dalla memoria" — non
  fattibile: `load_extension` è per-processo, non per-guild. Sostituito
  dal check runtime. Vedi § Decisioni in PROGRESS.md
- `[x]` 1.2 Cog Manager — load / unload / reload
- `[x]` 1.2 Controllo stato attivazione modulo per server
- `[ ]` 1.2 Evento `modules_updated` — il setup scrive sul DB ma non
  emette nessun evento; nessun consumatore lo ascolta
- `[x]` **1.3 Memory Guard**
  - `[x]` Monitoraggio RAM ogni 60 secondi (psutil) — `core/memory_guard.py`, letto per davvero con `psutil.Process().memory_info().rss`, verificato con un test che legge la RAM vera del processo di test (nessun mock)
  - `[x]` Garbage collection forzata su soglia — evoluta a **quattro
    livelli** (NORMAL/WARNING/CRITICAL/EMERGENCY, BACKLOG.md §4):
    GC da WARNING in su, DM solo da CRITICAL (col cooldown di 30 min
    di prima), EMERGENCY bypassa sempre il cooldown
  - `[x]` Limitazione dimensione cache — `core/bounded_cache.py`
    (LRU vera, §1.5), collegata come consumatore reale a
    `core/invite_tracker.py`, che prima cresceva senza limiti con il
    numero di server
  - `[x]` Distruzione VoiceClient inutilizzati (canale rimasto senza
    membri umani)
  - `[x]` Alert DM al proprietario al superamento soglia (con
    cooldown di 30 minuti tra un alert e l'altro, per non spammare
    l'owner ad ogni tick se la RAM resta alta)
- `[x]` 1.4 Database Layer — pool asyncpg, localhost, query asincrone
- `[x]` 1.5 Cache Layer (LRU con dimensione massima) —
  `core/bounded_cache.py`, politica LRU vera verificata esplicitamente
  (un GET conta come uso recente quanto un SET)
- `[x]` 1.6 Error Handler Globale — `on_error` in `main.py` ora copre
  anche le eccezioni non catturate nei listener di eventi (non solo
  gli slash command), con alert DM all'owner e cooldown per
  event_method
- `[x]` 1.7 Logger Strutturato — JSON con rotazione
  (`core/json_log_formatter.py` + `RotatingFileHandler`, 10MB×5),
  nessuna nuova dipendenza. Convive con l'output testuale su stdout,
  non lo sostituisce
- `[x]` 1.8 Auto-Setup Engine
  - `[x]` Trigger `on_guild_join` + creazione record DB
  - `[x]` **Invio del messaggio di benvenuto all'ingresso** con
    fallback a catena (system_channel → primo canale scrivibile → DM
    owner). Bug reale trovato scrivendo il test: se l'invio sul
    system_channel falliva, la ricerca del canale alternativo poteva
    ritrovare lo stesso identico canale (quasi sempre incluso anche
    in `guild.text_channels`) e ritentarlo invece di passarne uno
    diverso — corretto escludendolo esplicitamente dalla ricerca
- `[x]` 1.9 Sharding (AutoShardedBot)

## §2 SETUP & DASHBOARD

- `[x]` 2.1 Pannello interattivo — select menu moduli, conferma, annulla
- `[ ]` 2.1 Bottone "Reset configurazione"
- `[ ]` 2.2 Wizard di configurazione guidata passo-passo
- `[ ]` 2.3 Lingua per server — colonna `language` esiste nel DB, nessun
  comando, nessun sistema i18n
- `[✗]` 2.4 Prefisso personalizzato — scartato: slash-command-only per
  non richiedere il Message Content Intent. **La colonna `prefix` in
  `guild_config` è morta e va rimossa o documentata come deprecata**
- `[ ]` 2.5 Esporta configurazione
- `[ ]` 2.6 Importa configurazione
- `[x]` 2.7 Log delle modifiche di setup (audit trail: chi ha
  attivato/disattivato cosa e quando) — esteso oltre la richiesta
  originale con il **rollback**: `/config history` + `/config
  rollback <id>` con conferma a due passaggi (BACKLOG.md §11)

## §3 PREMIUM SYSTEM

- `[x]` 3.1 Registry moduli + flag premium per modulo, tutto OFF di default
- `[x]` 3.2 Whitelist manuale per Server ID (add / remove)
- `[ ]` 3.2 Comando per **elencare** i server in whitelist (esistono
  add/remove ma non list)
- `[x]` 3.2 Attiva/disattiva natura premium di un singolo modulo
- `[ ]` 3.2 Visualizza stato premium di **tutti** i server
- `[x]` 3.3 Controllo runtime (`requires_module`)
- `[ ]` 3.1 Metodo sblocco: **Boost Nitro** sul server principale
  (`Member.premium_since`) — deciso esplicitamente, nessun codice
- `[ ]` 3.1 Metodo sblocco: 1.000.000 coin per modulo
- `[ ]` 3.1 Metodo sblocco: pagamento annuale per modulo
- `[ ]` 3.3 Ricarica delle flag premium dal DB all'avvio (il registry
  riparte sempre da `is_premium_active=False`; TODO già annotato nel
  codice ma mai chiuso)

## §4 VERIFY + FINGERPRINT + ANTI-ALT — Verify Base completo, il resto dipende dal Web Panel

- `[x]` 4.1 Verify Base
  - `[x]` Button verify — `VerifyPanelView`, persistente (stesso
    pattern di ticket/vocali temporanei)
  - `[x]` Reaction verify — `on_raw_reaction_add`. **Non supporta il
    captcha**: una reazione non è un'Interaction, non può aprire un
    Modal — combinazione rifiutata esplicitamente a `/verify setup`
    con un messaggio chiaro, non implementata a metà
  - `[x]` Captcha — testuale (domanda di somma generata al click,
    diversa ogni volta), solo in modalità button per il motivo sopra.
    Nessuna immagine: evita Pillow come nuova dipendenza solo per
    questo
  - `[x]` Controllo età account
  - `[x]` Controllo mutual servers — confermato il limite già noto:
    il bot vede solo quanti server IN CUI SI TROVA LUI contengono
    anche l'utente, non tutti i server dell'utente in assoluto
  - `[x]` Invite tracker (cache inviti + diff al join) — costruito
    come infrastruttura condivisa in `core/invite_tracker.py`
    (durante lo sviluppo di Spam Trap §7.3, che ne aveva bisogno per
    primo)
- `[ ]` 4.2 Verify Avanzato (richiede Web Panel) — non tentato,
  dipendenza non costruita
  - `[ ]` Raccolta IP / ISP / localizzazione
  - `[ ]` Browser fingerprint / device fingerprint
  - `[ ]` OAuth2 scope `identify`
  - `[ ]` Salvataggio fingerprint (hash, mai IP in chiaro)
- `[ ]` 4.3 Sistema Anti-Alt — dipende da §4.2, non costruito
  - `[ ]` Database fingerprint
  - `[ ]` Match → segnalazione allo staff (NON ban automatico
    cross-server; vedi § Decisioni)
  - `[ ]` Rilevamento pattern sospetti
- `[x]` 4.4 Whitelist utenti — bypassa tutti i controlli, verificato
  che vinca anche in combinazione con la blacklist (vedi 4.5)
- `[x]` 4.5 Blacklist utenti — **vince sempre**, anche su un utente
  erroneamente anche whitelistato: verificato esplicitamente con un
  test dedicato, non assunto
- `[x]` 4.6 Log completo di ogni tentativo di verify — tabella
  `verify_attempts` + embed nel canale log configurato, per ogni
  esito (successo o fallimento)

## §5 MODERATION

- `[x]` 5.1 Warn, Kick, Ban, Tempban, Timeout, Unban, Untimeout
- `[x]` 5.1 **Softban** (ban+unban immediato per cancellare i messaggi)
- `[x]` 5.1 **Mute via ruolo** — ruolo "Muted" auto-creato con
  overwrite su ogni canale esistente al momento della creazione
  (canali creati dopo non ereditano l'overwrite, limite noto)
- `[x]` 5.2 Case system — numerazione atomica per server, ricerca per
  numero, storico per utente
- `[x]` 5.3 Note utente
- `[x]` 5.4 Report system
- `[x]` 5.5 Lock / Unlock canale
- `[x]` 5.6 Slowmode
- `[x]` 5.7 Clear avanzato con filtri
- `[x]` 5.8 DM all'utente moderato
- `[x]` 5.9 **"Reason obbligatorio"** — `reason: str` (non più
  `str | None`) su warn/kick/ban/tempban/unban/timeout/softban/
  mute-role/unmute-role, con validazione minimo 3 caratteri.
  `/untimeout` (revoca, non azione punitiva) e `/lock` (stato del
  canale, non azione su un utente) restano con reason opzionale per
  scelta dichiarata, non nella lista esplicita dello schema
- `[x]` 5.10 Moderation logs su canale dedicato — `/mod-log-setup`,
  ogni azione pubblica una copia del case embed lì, oltre alla
  risposta nel canale del comando

## §6 AUTOMOD

- `[x]` 6.1 Anti-badwords (via AutoMod nativo Discord, con merge a tre vie)
- `[x]` 6.2 Anti-invite (via AutoMod nativo, regex)
- `[ ]` 6.3 Anti-link generico (whitelist/blacklist domini)
- `[ ]` 6.4 Anti-spam messaggi
- `[ ]` 6.5 Anti-spam emoji
- `[ ]` 6.6 Anti-spam sticker
- `[ ]` 6.7 Anti-caps
- `[ ]` 6.8 Anti-zalgo
- `[ ]` 6.9 Anti-mass-mention
- `[ ]` 6.10 Anti-attachment-spam
- `[ ]` 6.11 Filtri personalizzati per canale
- `[ ]` 6.12 Filtri personalizzati per ruolo
- `[ ]` 6.13 Azioni multiple configurabili (delete + warn + mute + ban)
- `[ ]` 6.14 Log delle azioni automod
- `[x]` 6.15 Smart AutoMod Escalation Ladder (BACKLOG.md §11) — scala
  di severità crescente **nel tempo** in base a quante volte un
  utente ha già triggerato l'AutoMod nativo, con reset dopo un
  periodo configurabile di buona condotta. Concettualmente diversa
  da 6.13 (che è più azioni insieme su UN trigger, non su trigger
  ripetuti nel tempo) — voce nuova, non una ridefinizione di 6.13

## §7 SECURITY SUITE — Spam Trap (§7.3) completo, il resto mancante

- `[ ]` 7.1 Anti-Raid
  - `[ ]` Join rate limit (finestra scorrevole)
  - `[ ]` Account age check all'ingresso
  - `[ ]` Rilevamento pattern username
  - `[ ]` Rilevamento pattern avatar
  - `[ ]` Lockdown automatico
  - `[ ]` Quarantine role
  - `[ ]` Alert staff
- `[ ]` 7.2 Anti-Nuke
  - `[ ]` Protezione canali (create/delete di massa)
  - `[ ]` Protezione ruoli
  - `[ ]` Protezione webhook
  - `[ ]` Protezione emoji / sticker / soundboard
  - `[ ]` Rilevamento mass ban / mass kick
  - `[ ]` Recovery automatico (ricreazione canali/ruoli)
  - `[ ]` Whitelist utenti/bot fidati
- `[x]` 7.3 **Spam Trap** — completo (solo il ban globale via
  fingerprint resta escluso, per la dipendenza esplicita da §4 sotto)
  - `[x]` `/setup` con selezione canale trappola e canale log — via
    parametri `discord.TextChannel` opzionali (rendono nativamente
    come selettore canale di Discord, non un menù a tendina
    testuale, ma stessa funzione)
  - `[x]` Creazione automatica `#spam-trap` (visibile a everyone, no
    inviti, no webhook) se non selezionato
  - `[x]` Creazione automatica `#spam-log` (solo administrator) se
    non selezionato
  - `[x]` Embed di presidio in `#spam-trap`, rosso, in inglese, con
    header grande "DO NOT WRITE IN THIS CHANNEL"
  - `[x]` Embed informativo in `#spam-log`, colore tenue, in inglese
  - `[x]` Sequenza fissa: cattura contenuto → **DM PRIMA del ban** →
    ban con `delete_message_seconds` → purge supplementare → cleanup →
    log
  - `[x]` Cancellazione messaggi 30 giorni (indicizzazione
    `message_id` in DB; nativo copre max 7 giorni, la purge
    supplementare copre 7-30)
  - `[x]` Log con: tag, user ID, data creazione account, data join,
    data ban, codice invito usato, **creatore dell'invito**, contenuto
    che ha fatto scattare la trappola, numero messaggi cancellati per canale
  - `[x]` Cleanup webhook creati dall'utente (via audit log)
  - `[x]` Cleanup inviti creati dall'utente (via audit log)
  - `[x]` Ban appeal: DM → thread privato in `#spam-log`, con bottoni
    staff (Unban/Reject/Reply), rate limit 1 appello/24h. Bottoni su
    una `View` NON persistente (timeout 7 giorni) — scelta dichiarata,
    non equivalente ai pannelli persistenti di ticket/vocali: un
    appeal è per natura più breve, non vale la complessità di bottoni
    persistenti per-caso dinamici
  - `[x]` **Transcript HTML** — timestamp, nome+nickname, contenuto
    con escaping rigoroso anti-XSS, allegati immagine rigenerati come
    thumbnail WebP (Pillow, `core/image_thumbnail.py`), avatar
    dell'utente mostrato una volta per report nell'intestazione. Le
    thumbnail sono incorporate come data URI dentro l'HTML stesso —
    non riospitate da nessuna parte, coerente con "mai riospitare il
    file originale"
  - `[ ]` Opzione ban globale via fingerprint — dipende da §4
    Anti-Alt (fingerprint cross-server), non costruito. Il ban resta
    per-server, correttamente, dato che non esiste ancora nulla da
    cui recuperare un fingerprint
- `[x]` 7.4 Permission Auditor + alert permessi pericolosi —
  `/permission-heatmap` (ruoli con permessi critici + quanti membri
  li possiedono) + DM diretto all'owner quando un membro riceve un
  ruolo con permesso critico
- `[ ]` 7.5 Security Score / health check configurazione server

## §8 LOGGING

- `[x]` 8.1 Member join
- `[x]` 8.2 Member leave
- `[x]` 8.3 Member ban / unban
- `[x]` 8.4 Member update — ruoli e nickname, nello stesso evento
  senza uscire in anticipo se solo uno dei due cambia
- `[x]` 8.5 Role create / delete
- `[ ]` 8.6 Role **update** (nome, colore, permessi)
- `[ ]` 8.7 Channel create / delete / update
- `[ ]` 8.8 Invite create / delete / use
- `[ ]` 8.9 **Voice state**: join / leave / move / mute / deafen
- `[ ]` 8.10 Webhook create / update / delete
- `[ ]` 8.11 Emoji create / delete / update
- `[ ]` 8.12 Sticker create / delete / update
- `[ ]` 8.13 Soundboard create / delete / update
- `[ ]` 8.14 Thread events
- `[ ]` 8.15 Server update (impostazioni guild)
- `[ ]` 8.16 Message delete / bulk delete / edit — **rimandato
  deliberatamente**: richiede il Message Content Intent, da chiedere
  solo quando un modulo lo giustifica (vedi § Decisioni)
- `[x]` 8.17 Log eventi unificato multi-indice (BACKLOG.md §3) — ogni
  evento (8.1-8.5, 8.15 quando esisterà) salvato UNA VOLTA nel DB,
  consultabile da più angolazioni (membro, canale, ruolo, tempo).
  `/logs user`, `/logs channel`, `/logs export` (JSON completo).
  Retention differenziata: 30gg Free, 180gg Premium, pulizia
  giornaliera automatica. **Proiezione su Forum Discord per
  canali/case NON costruita** — decisione esplicita nell'analisi
  (BACKLOG.md §3): "membri" è l'unica dimensione ad alta cardinalità
  che avrebbe fatto esplodere i thread durante un raid, "canali" e
  "case" restano un'estensione futura separata
- `[ ]` 8.17 Distinzione log semplificato `[Free]` vs completo `[Premium]`
  — oggi il modulo è uno solo, senza i due livelli previsti

## §9 MUSIC — architettura multi-istanza fatta, comandi ridotti (deliberatamente)

**Nota di stato**: costruita l'architettura multi-istanza (bot
principale + 5 worker nello stesso processo, instradamento
automatico) e un set di comandi RIDOTTO rispetto allo schema
originale — deliberatamente, su richiesta esplicita dell'utente:
"non voglio filtri audio, non voglio appesantire il bot per niente,
tanto la gente ormai raramente li usa" — niente search/forceskip/
remove/clear/shuffle/move/nowplaying-con-barra/loop-track/seek/
lyrics/filtri/DJ-role/voteskip, solo i comandi che la gente usa
davvero: play, skip, stop, pause, resume, queue, volume (con
up/down oltre a impostare un valore), disconnect, nonstop.

- `[x]` 9.1 Multi-VoiceClient manager (5 applicazioni separate) —
  `core/music_worker_bot.py`, 5 istanze nello stesso processo
  (non 5 processi separati — vedi PROGRESS.md per il perché)
- `[x]` 9.2 Assegnazione istanza libera per canale (tabella
  `music_sessions`, logica "se bot1 occupato → bot2") —
  `core/music_fleet.py` + `core/repositories/music_session_repo.py`
- `[x]` 9.3 Coda indipendente per canale vocale — ogni `wavelink.
  Player` (uno per worker/server) ha la propria coda, indipendente
  dalle altre per costruzione
- `[~]` 9.4 Comandi: play, search, skip, forceskip, stop, pause,
  resume, queue, remove, clear, shuffle, move, nowplaying (con barra
  di progresso), loop track, loop queue, volume, seek, lyrics —
  **fatti**: play, skip, stop, pause, resume, queue, volume (set/up/
  down), disconnect. **Deliberatamente NON fatti** (richiesta
  esplicita, comandi usati raramente): search distinto da play,
  forceskip, remove, clear, shuffle, move, nowplaying con barra,
  loop track/queue singolo (il loop coda intera esiste via
  /nonstop), seek, lyrics
- `[~]` 9.5 Sorgenti: YouTube, Spotify (solo risoluzione titolo),
  SoundCloud, URL, file locali — YouTube funziona via la ricerca di
  default di Lavalink; Spotify richiederebbe un plugin (LavaSrc) sul
  nodo Lavalink usato, non verificabile se presente su un nodo
  pubblico di terzi senza controllarlo direttamente; **file locali
  ORA fatti** per la radio condivisa (`/nonstop-main add-local`),
  instradati specificamente verso il nodo Lavalink locale — i nodi
  pubblici non hanno accesso al filesystem della macchina
- `[✗]` 9.6 Filtri audio (bassboost, nightcore, vaporwave, 8D) —
  scartato su richiesta esplicita dell'utente, non un limite tecnico
- `[✗]` 9.7 DJ role — scartato, stesso motivo di 9.6
- `[✗]` 9.8 Voteskip — scartato, stesso motivo di 9.6
- `[x]` 9.9 Auto-leave a canale vuoto — `core/music_fleet.
  handle_inactive_player()`, agganciato identicamente su tutti e 6 i
  bot (main + 5 worker). Il timeout (300s di default) è gestito
  internamente da wavelink/Lavalink; qui solo la reazione:
  disconnette e libera il worker nella flotta
- `[~]` 9.10 Modalità 24/7 con cap istanze concorrenti — `/nonstop
  on|off` (loop continuo sulla coda del worker attivo) fatto; il cap
  a 5 istanze concorrenti esiste implicitamente (TOTAL_WORKERS), ma
  non è un limite configurabile a parte
- `[x]` 9.11 Stream 24/7 con musica di proprietà (singolo decoder
  condiviso) — `/nonstop-main add-track|add-local|remove-track|
  list-tracks|start|stop`. "Condiviso" ottenuto con un orologio
  logico (`core/main_radio_logic.py`): non un unico decode audio
  fisicamente multicast a più canali (impossibile con l'architettura
  Lavalink — ogni bot ha la propria connessione voce), ma ogni
  server che entra calcola dove dovrebbe essere la riproduzione ORA
  (stessa traccia, stessa posizione, in base al tempo reale
  trascorso) e joina seekando esattamente lì — stesso risultato
  percepito dall'ascoltatore: tutti sentono la stessa cosa nello
  stesso punto. Verificato con un test end-to-end: un secondo server
  che entra 90 secondi dopo riceve la posizione corretta, non
  riparte da zero
- `[x]` 9.12 Backend Lavalink — l'intero cog si basa su Lavalink via
  wavelink, nodi pubblici in cascata + nodo locale (vedi PROGRESS.md)

## §10 ALERTS & SOCIAL — parzialmente fatta

- `[x]` 10.1 Twitch live — via polling Twitch Helix "Get Streams"
  (non EventSub webhook, vedi nota tecnica sotto). Testato con
  credenziali fittizie su richiesta esplicita dell'utente (server
  locale finto che imita l'API reale); funzionerà con le sue
  credenziali vere una volta registrate su dev.twitch.tv
- `[x]` 10.2 Twitch offline — stesso meccanismo di 10.1
- `[x]` 10.3 YouTube nuovo video — via il feed Atom nativo di YouTube
  (`youtube.com/feeds/videos.xml?channel_id=...`), nessuna chiave API
- `[ ]` 10.4 YouTube live — non affidabile via RSS (non indica lo
  stato live), richiederebbe la YouTube Data API con quota a
  consumo. Rimandato
- `[✗]` 10.5 TikTok nuovi video — scartato: nessuna API ufficiale
  gratuita per leggere le pubblicazioni di terzi, solo scraping
  fragile. Confermato dall'utente come vincolo accettato, non un
  limite di sforzo
- `[✗]` 10.6 Instagram — nessuna API permette di monitorare account
  di terzi. Scartato, vedi audit di fattibilità
- `[x]` 10.7 Reddit — via il feed RSS nativo di Reddit
  (`reddit.com/r/nome/new/.rss`), nessuna chiave API
- `[~]` 10.8 Custom RSS / webhook — la parte RSS è fatta (`/alerts
  add`, qualsiasi URL RSS/Atom); la parte "webhook" (ricezione push
  da terzi) non è stata costruita, stesso motivo tecnico sotto
- `[x]` 10.9 Messaggi personalizzabili per ogni alert — placeholder
  `{label}` `{title}` `{link}` nel template (RSS), `{label}` `{title}`
  `{login}` (Twitch)
- `[✗]` 10.13 X/Twitter — **voce nuova**, non nello schema originale,
  aggiunta su richiesta esplicita dell'utente. Scartata: la lettura
  via API richiede un abbonamento a pagamento nel tier utile (il
  tier gratuito non permette di leggere i post di terzi in modo
  utilizzabile per il monitoraggio). Nessuna alternativa gratuita
  affidabile nota (i bridge non ufficiali tipo Nitter sono instabili
  e spesso bloccati da X). Confermato dall'utente come vincolo
  accettato

**Nota tecnica, vale per Twitch/YouTube/Reddit/RSS**: lo schema
originale chiedeva EventSub (Twitch) e PubSubHubbub (YouTube),
entrambi webhook PUSH — richiedono un endpoint HTTPS pubblico
raggiungibile da Twitch/Google, che questo bot non ha (nessun server
web, solo un client Gateway Discord). Aggiungerlo significherebbe
dominio, certificato TLS, apertura di una porta sulla VM — un cambio
di infrastruttura, non solo di codice. Sostituito con **polling**
periodico (`core/feed_watcher.py` ogni 5 minuti, `core/twitch_
watcher.py` ogni 90s), che raggiunge lo stesso risultato per
l'utente finale senza cambiare il deployment.

## §11 BACKUP SYSTEM — orchestrazione automatizzabile completa

**Nota di stato**: costruite sia la clonazione (§11.3-11.8) sia
l'intera orchestrazione automatizzabile attorno (§11.1, §11.2,
§11.12) — tutto quello che NON richiede una decisione architetturale
delicata è ora fatto. Restano deliberatamente rimandati §11.9
(mirror messaggi con identità utente) e §11.10/§11.11 (backup e
restore utenti via OAuth2 — storage di token OAuth altrui è un tema
di sicurezza reale, da discutere con l'utente, non da presumere).

**Limite reale della piattaforma Discord**, verificato con una
ricerca prima di progettare, non aggirabile dal codice: **un bot non
può autoinvitarsi in un server**. "Cede ownership → invita iYokai
Main" nella pratica significa: Creator crea e clona, genera un URL
di invito OAuth per Main, un umano deve cliccarlo — il codice fa
tutto il resto in automatico attorno a quel singolo passaggio
necessario.

- `[x]` 11.1 iYokai Creator: crea server → cede ownership → invita
  iYokai Main → esce (sempre sotto i 10 server) — `core/backup_
  orchestrator.py` (`start_backup_job()` + `finalize_backup_job()`,
  divise attorno al passaggio umano necessario sopra), `core/backup_
  creator_bot.py`
- `[x]` 11.2 Coda serializzata persistente con timeout 24h —
  `core/repositories/backup_repo.py` (tabella `backup_jobs`) +
  `core/backup_queue_worker.py` (un job alla volta, tick ogni 60s).
  Migliorato su richiesta esplicita dell'utente con un promemoria di
  scadenza (countdown, un solo DM per job) e il controllo di
  capacità di Creator (max 10 server): se è già al limite, il worker
  aspetta e avvisa una sola volta invece di tentare comunque
- `[x]` 11.3 Clonazione ruoli + permessi — `clone_roles()`, salta
  @everyone (esiste già) ma ne applica comunque i permessi al
  default_role di destinazione, salta i ruoli "managed"
- `[x]` 11.4 Clonazione categorie + canali — `clone_categories_and_
  channels()`, categorie create prima dei canali, overwrite di
  permessi rimappati tramite la mappa ruoli
- `[x]` 11.5 Clonazione emoji — `clone_emoji()`
- `[x]` 11.6 Clonazione sticker — `clone_stickers()`
- `[x]` 11.7 Clonazione soundboard — `clone_soundboard()`
- `[x]` 11.8 Clonazione webhook — `clone_webhooks()`, nome e canale
  rimappato (l'URL del webhook stesso non è copiabile, va
  riconfigurato a mano dove serve)
- `[ ]` 11.9 Mirror messaggi in tempo reale via webhook con identità
  utente (con politica di scarto sui burst, rate limit 5/5s per canale)
- `[ ]` 11.10 User backup: snapshot periodico (settimanale) dei
  verificati non bannati/kickati
- `[ ]` 11.11 Restore massivo utenti via OAuth2 `guilds.join`
- `[~]` 11.12 Comandi `/define-main`, `/define-backup`,
  `/restore-users` — i primi due fatti; `/restore-users` non
  costruito, dipende da §11.11 (OAuth2), rimandato con essa
- `[ ]` 11.13 Auto-propagazione: backup diventa main → crea nuovo backup

## §12 TEMPORARY VOICE CHANNELS

- `[x]` 12.1 Modalità automatica (generatore → crea + sposta)
- `[x]` 12.2 Modalità manuale (pannello + bottone persistente)
- `[x]` 12.3 Entrambe sempre visibili a tutti
- `[ ]` 12.4 **Notifica personale alla creazione del canale** —
  richiesta esplicitamente ("il classico messaggino di sistema che ti
  dice che il tuo canale è stato generato e si chiama XYZ"). La
  modalità manuale risponde ephemeral; **la modalità automatica sposta
  l'utente in totale silenzio**
- `[ ]` 12.5 Selezione piattaforma all'ingresso (PC / Console / Mobile)
  — nella decisione finale non filtra più la visibilità, ma restava
  come ruolo informativo
- `[x]` 12.6 Gestione canale: rename, limite utenti, lock, unlock, kick, transfer
- `[x]` 12.7 Eliminazione automatica a canale vuoto
- `[ ]` 12.8 Cap configurabile canali per categoria (limite Discord: 50)

## §13 TICKET SYSTEM

- `[x]` 13.1 Pannello apertura con bottone persistente
- `[ ]` 13.2 **Select menu categorie** — lo schema prevedeva la scelta
  tra più categorie di ticket; implementato solo un bottone unico
- `[x]` 13.3 Creazione canale privato
- `[x]` 13.4 Claim
- `[x]` 13.5 Add / Remove utente
- `[x]` 13.6 Rename
- `[x]` 13.7 Priorità
- `[x]` 13.8 Close
- `[ ]` 13.9 Force close (distinto da close normale)
- `[ ]` 13.10 **Transcript automatico** alla chiusura
- `[ ]` 13.11 Invio transcript nel canale log + DM all'utente
- `[ ]` 13.12 Statistiche ticket (tempo di risposta, per operatore)
- `[ ]` 13.13 Configurazione ruoli di supporto multipli (oggi uno solo)

## §14 UTILITY & SERVER MANAGEMENT — Role Menus + Greetings fatti, il resto mancante

- `[x]` 14.1 Reaction Roles — `on_raw_reaction_add`/`remove`
- `[x]` 14.2 Button Roles — View dinamica persistente per-messaggio
  (`bot.add_view(view, message_id=...)`, pattern nuovo rispetto ai
  pannelli "bottone fisso" già in uso altrove)
- `[x]` 14.3 Select Menu Roles — multi-selezione con sincronizzazione
  che non tocca mai ruoli del membro estranei al menu (verificato
  esplicitamente con un test dedicato)
- `[x]` 14.4 Welcome messages — canale + DM opzionale, segnaposto
  `{user}`/`{username}`/`{server}`/`{membercount}`
- `[x]` 14.5 Goodbye messages
- `[x]` 14.6 Boost messages — rilevato su `premium_since` che passa
  da `None` a valorizzato, non il caso opposto
- `[ ]` 14.7 Autoresponder (con wildcards e condizioni)
- `[x]` 14.8 **Custom Commands — sistema di RICHIESTA** (progettato in
  dettaglio): modal con nome comando + descrizione + esempio → embed
  automatico nel canale `#suggestions` del server principale con nome
  server, ID server, nome utente, **ID utente** (perché il nome può
  cambiare), descrizione, timestamp → bottoni staff approva/rifiuta →
  notifica di ritorno al richiedente
- `[ ]` 14.9 Snipe
- `[ ]` 14.10 Editsnipe
- `[ ]` 14.11 Reactionsnipe
- `[ ]` 14.12 Ghost ping detection
- `[x]` 14.13 Sticky messages — `/sticky set|remove`, debounce minimo
  (5s) per non cancellare+reinviare ad ogni singolo messaggio in un
  canale attivo
- `[x]` 14.14 Suggestion system (per i server clienti, distinto da
  14.8) — `/suggestion-setup`, `/suggest`, bottoni persistenti
  approva/rifiuta + reazioni native 👍👎 per il voto
- `[x]` 14.15 Poll — Poll nativo di Discord (`discord.Poll`), fino a
  5 opzioni, nessuna logica propria: voto/conteggio/chiusura gestiti
  interamente da Discord
- `[x]` 14.16 Reminder — `/reminder set|list|cancel`, riusa lo
  scheduler generico esistente (nessuna tabella nuova). Consegna via
  DM, fallback nel canale se i DM sono chiusi
- `[x]` 14.17 Scheduled messages — `/schedule-message set|list|cancel`,
  riusa lo stesso scheduler dei Reminder (nessuna tabella nuova).
  Diversamente dal Reminder (personale, via DM), pubblica in un
  CANALE del server
- `[x]` 14.18 Server stats (+ grafici) — `/serverstats`: numeri del
  server + grafico a barre della crescita giornaliera (disegnato con
  Pillow, non matplotlib — nessuna nuova dipendenza pesante)

## §15 LEVELS / ECONOMY / GILDE / CLASSIFICHE

- `[x]` 15.1 XP e livelli (testuale + vocale)
- `[x]` 15.2 Anti-farm XP vocale (self_deaf, soli nel canale, AFK, 2h
  stesso canale, cap giornaliero)
- `[x]` 15.3 Economy: daily, work, pay, balance
- `[x]` 15.4 Shop — `/shop list|buy|add-item|remove-item`, oggetti
  con prezzo e un ruolo opzionale da concedere all'acquisto
- `[x]` 15.5 Giveaway (con requisiti di ruolo/livello) — `/giveaway`,
  pulsante persistente "Partecipa" (sopravvive a un riavvio del bot,
  registrato di nuovo per ogni giveaway ancora attivo), requisiti di
  livello E ruolo verificati insieme al momento dell'iscrizione
- `[x]` 15.6 Drop messages — piccola probabilità (0.5%) per
  messaggio idoneo, pulsante "primo che clicca vince", coin
  accreditati atomicamente
- `[x]` 15.7 Classifica mensile (via `period_key`, senza reset schedulato)
- `[x]` 15.8 Classifica totale all-time
- `[x]` 15.9 Top 3 con medaglie, XP e/o coin a scelta
- `[ ]` 15.10 **Classifica Gilde** (mensile + totale)
- `[x]` 15.11 Annuncio automatico dei vincitori a fine mese —
  `/monthly-winners set|disable`, podio XP e coin del mese appena
  concluso, tick orario idempotente (uno solo per mese anche con
  riavvii); la prima configurazione non annuncia retroattivamente il
  mese già passato
- `[x]` 15.12 Notifica di level-up per XP vocale — mandata nel canale
  vocale stesso (i canali vocali moderni hanno la propria chat
  integrata), l'unico posto sensato per un task periodico su più
  server
- `[x]` 15.13 Ruoli-premio per livello raggiunto — `/level-roles
  add|remove|list`, cumulativo (ogni ruolo fino al nuovo livello,
  non solo il più alto), agganciato sia a XP testuale sia vocale
- `[~]` **15.14 SISTEMA GILDE / CLAN — intera sottosezione**
  (motore economico di backend calibrato e testato — 30 XP + 2 coin
  a tick/minuto in vocale di gilda, decadimento lineare dopo 3h filate
  nello stesso canale, tetto 720 tick/giorno, deficit di creazione
  15.000 coin/24h, costi canale 25k/50k/200k/800k — comandi Discord
  `/clan crea|info|membri|classifica|sciogli|tesoreria dona|invita|
  espelli|promuovi`, il worker di eliminazione automatica per chi non
  colma il deficit in tempo, e ORA anche i ruoli Discord Capo Clan/
  Admin Clan con i comandi di gestione membri)
  - `[x]` Creazione gilda + categoria privata dedicata — `/clan crea`
    valida il tag, crea la categoria Discord (view negata a
    `@everyone`, concessa al fondatore e al bot) PRIMA di scrivere il
    record (se la categoria fallisce non resta un clan senza spazio
    reale), poi `create_clan` con deficit di creazione e finestra di
    grazia di 24h
  - `[x]` Eliminazione automatica se il deficit non è colmato in
    tempo — `core/guild_clan_expiry_worker.py` (nuovo, tick orario):
    elimina canali + categoria Discord (se esistono ancora) e poi il
    record, per i clan non ufficializzati la cui finestra è scaduta
  - `[x]` Ruoli Capo Clan / Admin Clan — **pari tra gilde diverse**
    (`core/guild_clan_role_service.py`, nuovo): un ruolo Discord
    condiviso "Capo Clan" e uno "Admin Clan" per TUTTO il server,
    riusati da ogni clan (Discord non permette due ruoli alla stessa
    posizione) — l'isolamento reale passa dagli OVERWRITE PER-UTENTE
    sulla categoria del proprio clan (`sync_member_clan_role`/
    `clear_member_clan_presence`), mai dal ruolo condiviso in sé, che
    non dà nessun permesso su nessun canale. Applicato a `/clan crea`
    (Capo Clan al fondatore), `/clan invita` (accesso base),
    `/clan promuovi` (Admin Clan + overwrite estesi o declassamento),
    `/clan espelli` e `/clan sciogli` (rimozione completa)
  - `[x]` Isolamento totale: nessun capo/admin può agire su altre
    gilde — ogni comando di gestione membri recupera SEMPRE la gilda
    del chiamante via `get_member_clan_in_guild` e opera solo sulla
    categoria/membri di quella gilda; un Admin Clan non può espellere
    un altro Admin Clan (serve il Capo), solo il Capo Clan può
    promuovere/retrocedere
  - `[x]` Comandi di gestione membri: `/clan invita` (Capo/Admin,
    rispetta il tetto `max_members`, rifiuta chi è già in un'altra
    gilda del server), `/clan espelli` (Capo/Admin, il Capo Clan non
    può essere espulso, un Admin non può espellere un altro Admin),
    `/clan promuovi` (solo Capo Clan, ruolo admin/mod/member, rispetta
    i tetti `MAX_ADMINS_PER_CLAN`/`MAX_MODS_PER_CLAN` in
    `guild_clan_logic.py`)
  - `[~]` Guadagno ×2 XP e coin nei canali della propria gilda —
    `guild_clan_voice_worker.py` applica il tick per la presenza
    vocale, agganciato a `clan_voice_activity_repo`; **manca** il
    lato testuale (nessun hook sui messaggi nei canali di gilda)
  - `[~]` Tesoreria: deposito da tutti, prelievo solo capo/admin, log
    movimenti — `/clan tesoreria dona` scala il saldo personale e
    accredita la tesoreria (ufficializzando il clan in automatico se
    il deficit viene colmato); consultabile via `/clan info`.
    **Manca** ancora un comando di PRELIEVO per capo/admin
  - `[~]` Decadimento mensile 10% sulla tesoreria NON spesa —
    `guild_clan_treasury_decay_worker.py`, idempotente per periodo
    (`clans.last_decay_period`), calcolo atomico sotto `FOR UPDATE`,
    ORA deposita il delta nella cassa di server (SPEC.md §15.15)
  - `[~]` Acquisto canali: testuale / vocale / forum — costo e
    progressione già in `guild_clan_logic.py`/`increment_channels_unlocked`;
    **manca** il comando di acquisto e la creazione reale del canale
  - `[~]` Costo coin raddoppiato/quadruplo per canale successivo
    (25.000 → 50.000 → 200.000 → 800.000) — costanti già definite,
    solo il comando che le applica manca
  - `[ ]` Requisito **ore vocali accumulate in gilda** come sblocco
    canale (separato dal semplice guadagno XP/coin — serve un
    conteggio ore dedicato, non ancora agganciato a nessuna soglia
    di acquisto)
  - `[ ]` Boost individuale XP / Coin acquistabile
  - `[ ]` Boost di gilda XP / Coin acquistabile
  - `[~]` Comandi: `/clan crea|info|membri|classifica|sciogli|tesoreria
    dona|invita|espelli|promuovi` fatti — **mancano ancora**
    compra-canale, boost
- `[ ]` **15.15 Decadimento economico + cassa di server** (scope
  emerso in conversazione con l'utente dopo la stesura iniziale
  dello schema, non presente nell'elenco originale)
  - `[x]` Decadimento settimanale 10% sui coin PERSONALI di
    QUALUNQUE membro del server (in un clan o no) — logica pura
    (`apply_weekly_personal_decay`, `week_key` in
    `core/leveling_logic.py`: mai negativo, mai sotto 1, sempre
    intero — 10% di 105 → 10 o 11, mai 10,5), persistenza atomica
    (`LevelingRepository.apply_weekly_decay`, colonna
    `last_weekly_decay_period` per riga) e worker (
    `core/weekly_personal_decay_worker.py`, stesso pattern tick
    orario/idempotente per periodo del worker di tesoreria di clan)
    tutti fatti e testati
  - `[x]` Cassa di server: `core/repositories/guild_chest_repo.py`
    (tabelle `guild_chest` + `guild_chest_ledger`), alimentata da
    ENTRAMBI i decadimenti — quello settimanale personale
    (`weekly_personal_decay_worker`) e quello mensile della
    tesoreria di clan (`guild_clan_treasury_decay_worker`, aggiornato
    per depositare il delta nella cassa del server del clan). Saldo
    e ultimi movimenti consultabili con `/cassa saldo`
  - `[~]` Uso della cassa: premi per eventi organizzati nel server
    e/o acquisto di mesi di bot premium — lo sblocco premium è
    fatto (`/cassa sblocca-premium`); **manca** ancora un comando di
    spesa dedicato ai premi evento (oggi la cassa ha solo
    `deposit`/`spend`, nessun comando Discord per un prelievo-premio)
  - `[x]` Sblocco premium a doppio cancello: **tempo** dal join del
    bot nel server (1° mese dopo 6 mesi, 2° dopo 1 anno, 3° dopo 2
    anni, confermato da `core.premium_pricing_logic.TIER_MONTHS_
    REQUIRED`) **E** costo in coin dalla cassa (500.000/5.000.000/
    50.000.000 sotto i 1.000 membri, ×10 per fascia successiva —
    numeri confermati dall'utente), arrotondato in eccesso a
    multipli di 25.000. `core.premium_purchase_service.
    purchase_premium_tier` orchestra i controlli (tempo, tier già
    comprato, saldo) prima di toccare la cassa; `guild_has_premium_
    access` in `core/premium.py` ora controlla anche questo stato
    oltre alla whitelist manuale — comando: `/cassa sblocca-premium`

## §16 FUN & IMMAGINI — parzialmente fatta

- `[ ]` 16.1 Mini-giochi
- `[ ]` 16.2 Image manipulation
- `[ ]` 16.3 Comandi meme
- `[ ]` 16.4 Comandi animal
- `[x]` 16.5 Ship — percentuale deterministica via hash, non casuale
  ad ogni chiamata
- `[ ]` 16.6 Howgay — deliberatamente non fatto: troppo vicino a un
  attributo protetto (l'orientamento sessuale) per un giochino
  casuale, anche se comune in altri bot Discord
- `[x]` 16.7 Rate — punteggio 0-10 deterministico via hash
- `[ ]` 16.8 Altri comandi di intrattenimento classici
- `[ ]` 16.9 Ricerca immagini SFW
- `[ ]` 16.10 NSFW / Rule 34 → **applicazione separata iYokai NSFW**
  - `[ ]` Solo canali con flag NSFW, verificato a runtime a ogni post
  - `[ ]` Comando ricerca: `r34 <termine>` → immagine casuale
  - `[ ]` Auto-post configurabile: intervallo (numero + minuti/ore),
    sottocategorie scelte o random
  - `[ ]` **Filtro a due strati obbligatori**: allowlist decisa dal
    server + blocklist hardcoded non modificabile, su ricerca manuale
    E auto-post
  - `[ ]` Log con hash di ogni immagine pubblicata

## §17 OWNER / GLOBAL ADMIN

- `[x]` 17.1 Gestione Premium List (add / remove)
- `[x]` 17.2 Toggle flag premium per modulo
- `[x]` 17.3 Eval / Exec / Shell (con secondo fattore di conferma) —
  `/owner eval`/`/owner shell`, il codice/comando va mostrato per
  intero prima dell'esecuzione (bottoni Esegui/Annulla), ogni
  invocazione loggata in modo persistente
- `[x]` 17.4 Blacklist globale utenti — cache come per i moduli,
  blocca ogni interazione tramite `BlacklistAwareCommandTree`
- `[x]` 17.5 Blacklist globale server — uscita automatica su
  `on_guild_join` se già in blacklist, uscita immediata se aggiunto
  mentre il bot è già dentro
- `[x]` 17.6 Forced cog load / unload / reload — `/owner cog-load|
  cog-unload|cog-reload`. Due bug sistemici trovati e corretti
  facendolo: i nomi dei metodi Python collidevano con hook di ciclo
  di vita riservati di `discord.py` (`cog_load`/`cog_unload`,
  rompeva ogni cog del bot), e sia `registry.register()` che
  `scheduler.register_handler()` sollevavano su un reload legittimo
  (ogni cog con un modulo premium/handler scheduler era rotto)
- `[x]` 17.7 Annuncio globale a tutti i server — `/owner announce`,
  riusa la stessa catena di fallback del messaggio di benvenuto
  (system_channel → primo canale scrivibile → DM proprietario),
  estratta in un metodo generico su `iYokaiBot`
- `[x]` 17.8 Statistiche globali (guild count, shard health, RAM,
  latenza, comandi/minuto, errori) — `/owner stats`, contatori a
  finestra scorrevole di 60s (`core/bot_stats.py`)
- `[x]` 17.9 Leave guild forzato
- `[x]` 17.10 Pannello premium interattivo con conferma a due step e
  log persistente di ogni modifica — `/owner premium-panel`, Select
  + conferma, `premium_toggle_history` (append-only, distinta dallo
  stato più recente)

---

# B. iYOKAI APPLICATION (user-installable) — **MAI TRACCIATA**

- `[ ]` B.1 Applicazione con scope `USER_INSTALL`: comandi disponibili
  in qualsiasi server, DM, group DM, anche dove il bot non è invitato
- `[ ]` B.2 Utility personali
- **Nota**: menzionata nella discussione sulle alternative al selfbot,
  poi mai inserita in nessuna lista di cose da fare — nemmeno nella
  tabella delle applicazioni del progetto

---

# C. WEB PANEL (iYokai Panel) — **MAI INIZIATO**

- `[ ]` C.1 Pagina di verify avanzato (IP, ISP, geo, fingerprint)
- `[ ]` C.2 Flusso OAuth2 `identify` (verify)
- `[ ]` C.3 Flusso OAuth2 `guilds.join` separato (restore utenti)
- `[ ]` C.4 Dashboard owner: premium list, toggle moduli premium
- `[ ]` C.5 Privacy policy pubblicata + informativa GDPR (prerequisito
  legale per C.1, non opzionale)

---

# D. iYOKAI DESKTOP (presence via RPC) — **MAI INIZIATO**

- `[✗]` D.0 Modulo selfbot con user token — **scartato**: viola i ToS
  Discord, fa bannare l'utente finale, e metterebbe a rischio l'intera
  applicazione verificata
- `[ ]` D.1 App locale che usa il socket IPC del client Discord
- `[ ]` D.2 Custom presence: giocando / ascoltando / guardando /
  competendo, immagini grande e piccola, testi, bottoni, timestamp
- `[ ]` D.3 Rotazione automatica di più stati
- `[ ]` D.4 Profili salvati
- `[✗]` D.5 Custom status testuale con emoji, bio animate, cambio
  avatar/banner a rotazione — **impossibile senza user token**, nessuna
  via legittima esiste

---

# E. ALTRE APPLICAZIONI DA CREARE

- `[ ]` iYokai Creator (backup) — vedi §11
- `[ ]` iYokai Music #1-5 — vedi §9
- `[ ]` iYokai NSFW — vedi §16.10

---

# Conteggio sintetico

Ricalcolato meccanicamente (script che conta i marcatori `[x]`/`[~]`/
`[ ]` per sezione), non a occhio — così resta verificabile da chiunque
rilancia lo stesso conteggio.

| Sezione | Fatto | Parziale | Mancante |
|---|---|---|---|
| §1 Core | 18 | 0 | 1 |
| §2 Setup | 2 | 0 | 5 |
| §3 Premium | 4 | 0 | 6 |
| §4 Verify | 10 | 0 | 9 |
| §5 Moderation | 12 | 0 | 0 |
| §6 AutoMod | 3 | 0 | 12 |
| §7 Security | 14 | 0 | 18 |
| §8 Logging | 6 | 0 | 12 |
| §9 Music | 6 | 3 | 0 |
| §10 Alerts | 5 | 1 | 1 |
| §11 Backup | 8 | 1 | 4 |
| §12 Voice temp | 5 | 0 | 3 |
| §13 Ticket | 7 | 0 | 6 |
| §14 Utility | 13 | 0 | 5 |
| §15 Levels/Gilde | 20 | 8 | 5 |
| §16 Fun/NSFW | 2 | 0 | 13 |
| §17 Owner | 10 | 0 | 0 |
| B/C/D/E | 0 | 0 | 14 |
| **Totale** | **145** | **13** | **114** |

Su 272 voci totali: **145 fatte, 13 parziali, 114 mancanti** — circa
il 56% dello schema (contando i parziali a metà peso). §11 Backup
System ha l'intera orchestrazione automatizzabile completa —
restano solo le parti che richiedono decisioni architetturali con
l'utente (mirror messaggi, backup/restore utenti via OAuth2). §15
Levels: il Sistema Gilde/Clan (§15.14) ha ora il motore economico
(repository/worker: tesoreria, XP di gilda, tracciamento vocale,
decadimento mensile), i comandi Discord `/clan crea|info|membri|
classifica|sciogli|tesoreria dona`, il worker di eliminazione
automatica per chi non colma il deficit in tempo, E ORA anche i
ruoli Discord condivisi Capo Clan/Admin Clan (overwrite per-utente
sulla categoria del proprio clan per l'isolamento reale, il ruolo
condiviso è solo un'etichetta) con i comandi `/clan invita|espelli|
promuovi`. Mancano ancora l'acquisto canali e i boost individuali/di
gilda. §15.15 (non nello schema originale, emersa in conversazione)
è COMPLETO: decadimento settimanale personale, cassa di server
alimentata da entrambi i decadimenti, e sblocco premium a doppio
cancello (tempo dal join + costo dalla cassa) — comandi `/cassa
saldo` e `/cassa sblocca-premium`. Resta solo un comando dedicato per
spendere la cassa su premi evento.

Correzione del 21/09: il marcatore parziale (`` `[~]` ``) era definito nella
legenda ma non era mai stato usato — §9.4/9.5 e §10.8 erano marcati
come completamente fatti quando in realtà erano solo iniziati.
Audit a campione sul resto del documento (§5, §6, §12, §13, §15) non
ha trovato altri casi: i comandi/funzionalità elencati nelle voci
controllate esistono davvero nel codice.

