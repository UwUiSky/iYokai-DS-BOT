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
  - `[x]` Garbage collection forzata su soglia
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
- `[ ]` 2.7 Log delle modifiche di setup (audit trail: chi ha
  attivato/disattivato cosa e quando)

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
- `[ ]` 5.1 **Softban** (ban+unban per cancellare i messaggi)
- `[ ]` 5.1 **Mute via ruolo** (oggi solo timeout nativo; lo schema
  chiedeva entrambi)
- `[x]` 5.2 Case system — numerazione atomica per server, ricerca per
  numero, storico per utente
- `[x]` 5.3 Note utente
- `[x]` 5.4 Report system
- `[x]` 5.5 Lock / Unlock canale
- `[x]` 5.6 Slowmode
- `[x]` 5.7 Clear avanzato con filtri
- `[x]` 5.8 DM all'utente moderato
- `[ ]` 5.9 **"Reason obbligatorio"** — richiesto esplicitamente dallo
  schema. Io l'ho reso OPZIONALE in tutti i comandi
  (`reason: str | None = None`). Contraddizione mia, non un'omissione
  neutra: va deciso se rendere il campo obbligatorio o documentare la
  deviazione
- `[ ]` 5.10 Moderation logs su canale dedicato (i casi vanno nel DB e
  l'esito nel canale del comando, ma non esiste un canale mod-log
  configurabile separato dal log generale)

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

## §7 SECURITY SUITE — Spam Trap (§7.3) quasi completo, il resto mancante

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
- `[~]` 7.3 **Spam Trap** — quasi completo, vedi le foglie sotto per
  l'unica parte ridotta di scope
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
  - `[~]` **Transcript HTML** — timestamp, nome+nickname, contenuto
    con escaping rigoroso anti-XSS: fatto e testato esplicitamente.
    **Non fatto**: avatar visibile e immagini come thumbnail
    rigenerate server-side — richiederebbe Pillow come nuova
    dipendenza e una decisione su come distribuirla, non ancora presa
    (dichiarato nel codice, non spacciato per completo)
  - `[ ]` Opzione ban globale via fingerprint — dipende da §4
    Anti-Alt (fingerprint cross-server), non costruito. Il ban resta
    per-server, correttamente, dato che non esiste ancora nulla da
    cui recuperare un fingerprint
- `[ ]` 7.4 Permission Auditor + alert permessi pericolosi
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
- `[ ]` 8.17 Distinzione log semplificato `[Free]` vs completo `[Premium]`
  — oggi il modulo è uno solo, senza i due livelli previsti

## §9 MUSIC — **INTERA SEZIONE MANCANTE**

- `[ ]` 9.1 Multi-VoiceClient manager (5 applicazioni separate)
- `[ ]` 9.2 Assegnazione istanza libera per canale (tabella
  `music_sessions`, logica "se bot1 occupato → bot2")
- `[ ]` 9.3 Coda indipendente per canale vocale
- `[ ]` 9.4 Comandi: play, search, skip, forceskip, stop, pause,
  resume, queue, remove, clear, shuffle, move, nowplaying (con barra
  di progresso), loop track, loop queue, volume, seek, lyrics
- `[ ]` 9.5 Sorgenti: YouTube, Spotify (solo risoluzione titolo),
  SoundCloud, URL, file locali
- `[ ]` 9.6 Filtri audio (bassboost, nightcore, vaporwave, 8D)
- `[ ]` 9.7 DJ role
- `[ ]` 9.8 Voteskip
- `[ ]` 9.9 Auto-leave a canale vuoto
- `[ ]` 9.10 Modalità 24/7 con cap istanze concorrenti
- `[ ]` 9.11 Stream 24/7 con musica di proprietà (singolo decoder condiviso)
- `[ ]` 9.12 Backend Lavalink

## §10 ALERTS & SOCIAL — **INTERA SEZIONE MANCANTE**

- `[ ]` 10.1 Twitch live (EventSub webhook)
- `[ ]` 10.2 Twitch offline
- `[ ]` 10.3 YouTube nuovo video (PubSubHubbub)
- `[ ]` 10.4 YouTube live
- `[ ]` 10.5 TikTok nuovi video (nessuna API ufficiale — scraping fragile)
- `[✗]` 10.6 Instagram — nessuna API permette di monitorare account
  di terzi. Scartato, vedi audit di fattibilità
- `[ ]` 10.7 Reddit
- `[ ]` 10.8 Custom RSS / webhook
- `[ ]` 10.9 Messaggi personalizzabili per ogni alert

## §11 BACKUP SYSTEM — **INTERA SEZIONE MANCANTE**

- `[ ]` 11.1 iYokai Creator: crea server → cede ownership → invita
  iYokai Main → esce (sempre sotto i 10 server)
- `[ ]` 11.2 Coda serializzata persistente con timeout 24h
- `[ ]` 11.3 Clonazione ruoli + permessi
- `[ ]` 11.4 Clonazione categorie + canali
- `[ ]` 11.5 Clonazione emoji
- `[ ]` 11.6 Clonazione sticker
- `[ ]` 11.7 Clonazione soundboard
- `[ ]` 11.8 Clonazione webhook
- `[ ]` 11.9 Mirror messaggi in tempo reale via webhook con identità
  utente (con politica di scarto sui burst, rate limit 5/5s per canale)
- `[ ]` 11.10 User backup: snapshot periodico (settimanale) dei
  verificati non bannati/kickati
- `[ ]` 11.11 Restore massivo utenti via OAuth2 `guilds.join`
- `[ ]` 11.12 Comandi `/define-main`, `/define-backup`, `/restore-users`
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

## §14 UTILITY & SERVER MANAGEMENT — **INTERA SEZIONE MANCANTE**

- `[ ]` 14.1 Reaction Roles
- `[ ]` 14.2 Button Roles
- `[ ]` 14.3 Select Menu Roles
- `[ ]` 14.4 Welcome messages
- `[ ]` 14.5 Goodbye messages
- `[ ]` 14.6 Boost messages
- `[ ]` 14.7 Autoresponder (con wildcards e condizioni)
- `[ ]` 14.8 **Custom Commands — sistema di RICHIESTA** (progettato in
  dettaglio): modal con nome comando + descrizione + esempio → embed
  automatico nel canale `#suggestions` del server principale con nome
  server, ID server, nome utente, **ID utente** (perché il nome può
  cambiare), descrizione, timestamp → bottoni staff approva/rifiuta →
  notifica di ritorno al richiedente
- `[ ]` 14.9 Snipe
- `[ ]` 14.10 Editsnipe
- `[ ]` 14.11 Reactionsnipe
- `[ ]` 14.12 Ghost ping detection
- `[ ]` 14.13 Sticky messages
- `[ ]` 14.14 Suggestion system (per i server clienti, distinto da 14.8)
- `[ ]` 14.15 Poll (usare il Poll nativo di Discord)
- `[ ]` 14.16 Reminder
- `[ ]` 14.17 Scheduled messages
- `[ ]` 14.18 Server stats (+ grafici)

## §15 LEVELS / ECONOMY / GILDE / CLASSIFICHE

- `[x]` 15.1 XP e livelli (testuale + vocale)
- `[x]` 15.2 Anti-farm XP vocale (self_deaf, soli nel canale, AFK, 2h
  stesso canale, cap giornaliero)
- `[x]` 15.3 Economy: daily, work, pay, balance
- `[ ]` 15.4 **Shop** — nessun posto dove spendere i coin
- `[ ]` 15.5 **Giveaway** (con requisiti di ruolo/livello)
- `[ ]` 15.6 Drop messages
- `[x]` 15.7 Classifica mensile (via `period_key`, senza reset schedulato)
- `[x]` 15.8 Classifica totale all-time
- `[x]` 15.9 Top 3 con medaglie, XP e/o coin a scelta
- `[ ]` 15.10 **Classifica Gilde** (mensile + totale)
- `[ ]` 15.11 **Annuncio automatico dei vincitori a fine mese**
- `[ ]` 15.12 Notifica di level-up per XP vocale (oggi solo testuale)
- `[ ]` 15.13 Ruoli-premio per livello raggiunto
- `[ ]` **15.14 SISTEMA GILDE / CLAN — intera sottosezione**
  - `[ ]` Creazione gilda + categoria privata dedicata
  - `[ ]` Ruoli Capo Clan / Admin Clan — **pari tra gilde diverse**
    (ruolo unico condiviso + overwrite per-utente sulla propria
    categoria; Discord non permette due ruoli alla stessa posizione)
  - `[ ]` Isolamento totale: nessun capo/admin può agire su altre gilde
  - `[ ]` Guadagno ×2 XP e coin nei canali della propria gilda
  - `[ ]` Tesoreria: deposito da tutti, prelievo solo capo/admin, log movimenti
  - `[ ]` Acquisto canali: testuale / vocale / forum
  - `[ ]` Costo coin raddoppiato per ogni canale dello stesso tipo
    (10.000 → 20.000 → 40.000 → …)
  - `[ ]` Requisito **ore vocali accumulate in gilda**: 10 → 20 → 40,
    poi ×4 per ogni canale successivo (160 → 640 → 2.560 …).
    **Conteggio SEPARATO** da quello di `leveling_totals`: sono "ore
    in canali di gilda", non ore vocali generiche
  - `[ ]` Boost individuale XP / Coin acquistabile
  - `[ ]` Boost di gilda XP / Coin acquistabile
  - `[ ]` Comandi: crea, invita, espelli, promuovi, tesoreria,
    deposita, compra-canale, boost, info, classifica, sciogli

## §16 FUN & IMMAGINI — **INTERA SEZIONE MANCANTE**

- `[ ]` 16.1 Mini-giochi
- `[ ]` 16.2 Image manipulation
- `[ ]` 16.3 Comandi meme
- `[ ]` 16.4 Comandi animal
- `[ ]` 16.5 Ship
- `[ ]` 16.6 Howgay
- `[ ]` 16.7 Rate
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
- `[ ]` 17.3 Eval / Exec / Shell (con secondo fattore di conferma)
- `[ ]` 17.4 Blacklist globale utenti
- `[ ]` 17.5 Blacklist globale server
- `[ ]` 17.6 Forced cog load / unload / reload
- `[ ]` 17.7 Annuncio globale a tutti i server
- `[ ]` 17.8 Statistiche globali (guild count, shard health, RAM,
  latenza, comandi/minuto, errori)
- `[ ]` 17.9 Leave guild forzato
- `[ ]` 17.10 Pannello premium interattivo con conferma a due step e
  log persistente di ogni modifica (oggi comandi separati, nessun
  pannello, nessun log delle modifiche)

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
| §2 Setup | 1 | 0 | 6 |
| §3 Premium | 4 | 0 | 6 |
| §4 Verify | 10 | 0 | 9 |
| §5 Moderation | 8 | 0 | 4 |
| §6 AutoMod | 2 | 0 | 12 |
| §7 Security | 11 | 2 | 19 |
| §8 Logging | 5 | 0 | 12 |
| §9 Music | 0 | 0 | 12 |
| §10 Alerts | 0 | 0 | 8 |
| §11 Backup | 0 | 0 | 13 |
| §12 Voice temp | 5 | 0 | 3 |
| §13 Ticket | 7 | 0 | 6 |
| §14 Utility | 0 | 0 | 18 |
| §15 Levels/Gilde | 6 | 0 | 19 |
| §16 Fun/NSFW | 0 | 0 | 15 |
| §17 Owner | 2 | 0 | 8 |
| B/C/D/E | 0 | 0 | 14 |
| **Totale** | **79** | **2** | **185** |

Su 266 voci totali: **79 fatte, 2 parziali, 185 mancanti** — circa il
30% dello schema (fatto+parziale). Restano parziali solo due voci,
entrambe nello Spam Trap ed entrambe in attesa della stessa decisione
(Pillow come nuova dipendenza per rigenerare le immagini nel
transcript): il "ban globale via fingerprint" resta invece `[ ]`
puro, dato che dipende da §4 Anti-Alt non ancora costruito.

