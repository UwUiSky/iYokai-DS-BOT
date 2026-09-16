# iYokai-DS-BOT
YOKAI ECOSYSTEM — Schema tecnico verificato
Revisione: 16 settembre 2026
Cosa cambia rispetto alla versione precedente: ogni voce è ora marcata con un tag di fattibilità reale sulle API Discord, non solo Free/Premium. Tre moduli sono stati riscritti perché come erano descritti non sono implementabili.
---
Legenda
Tag	Significato
`[OK]`	Fattibile così com'è descritto
`[LIM]`	Fattibile ma con limiti tecnici che cambiano il comportamento atteso
`[NO]`	Non fattibile con un bot pubblico — serve riprogettare
`[LEG]`	Fattibile tecnicamente ma con esposizione legale seria (GDPR / Developer Policy)
`[NP]`	Non progettato — vedi sezione "Cosa non ho messo nello schema e perché"
Free / Premium restano come prima: `[Free]`, `[Cand. Premium]`.
---
0. BLOCCHI CRITICI — da leggere prima di scrivere una riga di codice
0.1 — Verifica Discord a 100 server (blocco principale)
Un bot non può superare i 100 server senza passare la verifica di Discord, e il Message Content Intent richiede approvazione separata con descrizione dell'uso. L'obiettivo 10.000 server passa obbligatoriamente da lì.
Il problema: nella stessa applicazione hai
raccolta IP / ISP / geolocalizzazione e blacklist globale cross-server,
clonazione in tempo reale dei messaggi degli utenti su un secondo server,
contenuti NSFW automatici,
distribuzione di un self-bot.
Una richiesta di verifica con questo profilo viene respinta con altissima probabilità, e una segnalazione può portare alla disabilitazione dell'applicazione. Questo è il rischio numero uno del progetto, non la RAM.
Strategia consigliata: verifica il bot con il set "pulito" (moderation, automod, ticket, livelli, vocali temporanei, log, music), e tieni fuori dall'applicazione verificata tutto ciò che è marcato `[LEG]` / `[NP]`.
0.2 — Il bot principale non può creare server (ma un bot dedicato sì)
`POST /guilds` è utilizzabile solo da bot presenti in meno di 10 server. Sopra quella soglia l'endpoint risponde errore. Non è un rate limit, è una restrizione fissa. Yokai Bot, a regime, non potrà mai creare un server.
Correzione rispetto alla prima stesura: un bot può trasferire la ownership di un server creato da lui (`PATCH /guilds/{id}` con `owner_id`, valido solo se il bot è owner e il server è stato creato dal bot). Questo rende possibile un'applicazione dedicata — Yokai Creator — che crea, cede e esce, restando sempre sotto soglia.
Vincolo assoluto: il Creator non può MAI restare owner. Il conteggio dei 10 server è sui server in cui il bot si trova, e un owner non può uscire da un server che possiede. Se il Creator trattiene la ownership "fino al momento del restore", si blocca dopo 9 clienti e l'endpoint smette di rispondere per sempre.
Vedi §11 per il flusso completo.
0.3 — Un bot = una sola connessione vocale per server
Un account bot può avere una sola voice connection per guild. Più canali vocali contemporanei nello stesso server richiedono più applicazioni bot distinte, ognuna con il suo token. È esattamente il motivo per cui Mackie/Jockie sono 4 bot separati: non è una scelta di design, è l'unico modo.
Quello che è vero: un solo bot può stare in canali vocali di server diversi contemporaneamente senza problemi.
0.4 — Sharding e RAM
Oltre ~2.500 server lo sharding è obbligatorio. A 10.000 server servono almeno 5 shard. Su Oracle Always Free (Ampere A1, 4 OCPU / 24 GB massimi condivisi) è fattibile solo con:
member cache disattivata (`chunk_guilds_at_startup=False`, member cache flags a `none`),
message cache azzerata o minima,
`intents.presences = False`.
Nota: le istanze Always Free possono essere recuperate da Oracle se inattive e non hanno SLA. Per 10.000 server è un host non adatto in produzione.
---
A. YOKAI BOT (Guild-installed Bot)
```
YOKAI BOT
│
├── 1. CORE SYSTEM                                                    [Free]
│   ├── 1.1 Multi-Tenant Engine                                       [OK]
│   │   ├── Isolamento configurazione per Guild ID
│   │   ├── Attivazione/disattivazione feature per server
│   │   └── NOTA [LIM]: i cog NON si caricano/scaricano per server.
│   │       load_extension è globale al processo. Il pattern corretto è:
│   │       tutti i cog caricati una volta + check per-guild in un decorator
│   │       che esce subito se il modulo non è attivo. Il risparmio di RAM
│   │       promesso dal "carica solo i cog del server X" non esiste.
│   ├── 1.2 Cog Manager                                               [OK]
│   │   ├── Load / Unload / Reload globale (per deploy e hotfix)
│   │   ├── Registry moduli con metadati (nome, premium_flag, intents richiesti)
│   │   └── Evento modules_updated → invalida cache config guild
│   ├── 1.3 Memory Guard                                              [OK]
│   │   ├── Monitoraggio RSS ogni 60s (psutil)
│   │   ├── gc.collect() su soglia
│   │   ├── Cache LRU con dimensione massima per tipo
│   │   ├── Disconnessione VoiceClient idle
│   │   └── Alert DM owner su soglia
│   ├── 1.4 Database Layer (PostgreSQL + asyncpg)                     [OK]
│   │   ├── Pool 5-10 connessioni (3 è troppo poco con 5 shard)
│   │   ├── Bind su 127.0.0.1
│   │   └── Tutte le query dietro un repository layer (mai SQL nei cog)
│   ├── 1.5 Cache Layer (in-memory LRU; Redis solo se multi-processo)  [OK]
│   ├── 1.6 Error Handler globale                                     [OK]
│   ├── 1.7 Logger strutturato (JSON, rotazione)                      [OK]
│   ├── 1.8 Sharding Manager                                          [OK]  ← AGGIUNTO
│   │   ├── AutoShardedBot
│   │   ├── Gestione resume / reconnect per shard
│   │   └── Health check per shard
│   └── 1.9 Auto-Setup Engine                                         [LIM]
│       ├── Trigger on_guild_join
│       ├── Invio pannello setup
│       │   └── [LIM] Non esiste un modo garantito di raggiungere
│       │       l'inviter. Ordine di fallback: system_channel →
│       │       primo canale testuale scrivibile → DM all'owner
│       │       (che può avere i DM chiusi). Serve anche /setup manuale.
│       └── Creazione record configurazione
│
├── 2. SETUP & DASHBOARD                                              [Free]
│   ├── 2.1 Pannello interattivo                                      [OK]
│   │   ├── Select Menu moduli (max 25 opzioni per menu → paginare)
│   │   ├── Bottoni Conferma / Annulla / Reset
│   │   └── [LIM] I Modal accettano max 5 campi di testo, solo testo.
│   │       Niente select o bottoni dentro un Modal.
│   ├── 2.2 Wizard guidato passo-passo                                [OK]
│   ├── 2.3 Lingua del server (i18n)                                  [OK]
│   ├── 2.4 Prefisso personalizzato                                   [LIM]
│   │   └── I comandi a prefisso richiedono Message Content Intent.
│   │       Consiglio: slash-command-only e niente prefisso → una
│   │       ragione in meno per cui la verifica ti viene negata.
│   ├── 2.5 Export configurazione (JSON)                              [OK]
│   ├── 2.6 Import configurazione                                     [OK]
│   └── 2.7 Audit log delle modifiche di setup                        [OK]
│
├── 3. PREMIUM SYSTEM (predisposto, tutto OFF all'avvio)
│   ├── 3.1 Metodi di sblocco
│   │   ├── Pagamento annuale per modulo                              [LIM]
│   │   │   └── Discord ha il suo sistema (Premium Apps / SKU) con
│   │   │       revenue share. Pagamento esterno (Stripe/PayPal) è
│   │   │       ammesso ma la gestione IVA/fatturazione è a tuo carico
│   │   │       e in Italia serve partita IVA sopra soglie minime.
│   │   ├── 1.000.000 coin del server per modulo                      [LIM]
│   │   │   └── ATTENZIONE: l'economia è per-server e un admin può
│   │   │       darsi coin a piacere. Così com'è, è uno sblocco gratis
│   │   │       mascherato. Va legato a metriche non manipolabili
│   │   │       (ore vocali reali) o rimosso.
│   │   ├── Boost Nitro sul server principale                         [OK]
│   │   │   └── Rilevabile via Member.premium_since; revoca automatica
│   │   │       alla scadenza tramite on_member_update
│   │   └── Whitelist manuale per Server ID (solo Owner)              [OK]
│   ├── 3.2 Controlli Owner                                           [OK]
│   │   ├── Add / Remove Server ID in Premium List
│   │   ├── Toggle flag premium per singolo modulo (globale)
│   │   ├── Vista stato premium di tutti i server
│   │   └── Log di ogni modifica (chi, cosa, quando)
│   └── 3.3 Controllo runtime                                         [OK]
│       ├── is_premium_module(module) → bool
│       ├── guild_has_access(guild_id, module) → bool
│       └── Decorator @requires_module("nome") su ogni comando
│
├── 4. VERIFY + ANTI-ALT
│   ├── 4.1 Verify Base (solo Discord)                                [Free] [OK]
│   │   ├── Button Verify
│   │   ├── Captcha (immagine generata + Modal, oppure bottone-scelta)
│   │   ├── Controllo età account
│   │   ├── Controllo mutual servers                                  [LIM]
│   │   │   └── Il bot vede solo i server in comune con SE STESSO,
│   │   │       non tutti i server dell'utente. Segnale debole.
│   │   ├── Invite Tracker                                            [LIM]
│   │   │   └── Richiede MANAGE_GUILD + cache inviti + diff sul join.
│   │   │       Non risolve: vanity URL, join simultanei, membership
│   │   │       screening, inviti già scaduti. Affidabilità ~90%.
│   │   └── Reaction Verify [deprecabile: le reaction richiedono
│   │       intent aggiuntivi, meglio solo bottoni]
│   ├── 4.2 Verify Avanzato — IP / ISP / Geo / Fingerprint            [Cand. Premium] [LEG]
│   │   ├── Tecnicamente: sì, ma SOLO via Web Panel. Confermato:
│   │   │   né Bot API né User-Installable App espongono IP.
│   │   ├── RISCHIO LEGALE (sei in Italia → GDPR pieno):
│   │   │   ├── L'IP è dato personale (art. 4 GDPR, confermato CGUE)
│   │   │   ├── Il device fingerprinting richiede consenso esplicito
│   │   │   │   ex ePrivacy, non basta il legittimo interesse
│   │   │   ├── Serve informativa privacy, base giuridica, registro
│   │   │   │   trattamenti, retention definita, procedura di
│   │   │   │   cancellazione su richiesta
│   │   │   ├── Tu diventi titolare del trattamento per gli utenti
│   │   │   │   di TUTTI i server che attivano il modulo
│   │   │   └── La Discord Developer Policy limita la raccolta di dati
│   │   │       oltre il necessario alla funzione dichiarata
│   │   └── RACCOMANDAZIONE: se lo fai, fallo con hash irreversibile
│   │       del fingerprint (mai IP in chiaro in DB), retention 90
│   │       giorni, opt-in esplicito nella pagina di verifica, e una
│   │       privacy policy vera. Altrimenti non farlo.
│   ├── 4.3 Anti-Alt cross-server                                     [Cand. Premium] [LEG]
│   │   └── Una blacklist globale che banna su server terzi in base a
│   │       un fingerprint è il punto più esposto dell'intero progetto,
│   │       sia verso Discord sia verso il Garante. Alternativa più
│   │       sicura: il match segnala allo staff, non banna in automatico.
│   ├── 4.4 Whitelist / Blacklist locale                              [Free] [OK]
│   └── 4.5 Log verify                                                [Free] [OK]
│
├── 5. MODERATION
│   ├── 5.1 Azioni base                                               [Free] [OK]
│   │   ├── Warn / Kick / Ban / Softban / Tempban / Timeout / Mute
│   │   └── [LIM] Timeout nativo: massimo 28 giorni
│   ├── 5.2 Case System + note + storico                              [Cand. Premium] [OK]
│   ├── 5.3 Report System                                             [Free] [OK]
│   ├── 5.4 Lock / Unlock canale                                      [Free] [OK]
│   ├── 5.5 Slowmode                                                  [Free] [OK]
│   └── 5.6 Clear avanzato                                            [Cand. Premium] [LIM]
│       └── bulk_delete funziona solo su messaggi < 14 giorni.
│           Oltre: cancellazione uno per uno, 5 req/s per canale.
│
├── 6. AUTOMOD
│   ├── 6.1 Filtri base                                               [Free] [OK]
│   │   └── SUGGERIMENTO: anti-invite, anti-link, anti-badwords,
│   │       anti-mention-spam si possono delegare all'AutoMod NATIVO
│   │       di Discord via API (POST /guilds/{id}/auto-moderation/rules).
│   │       Vantaggi enormi: non serve Message Content Intent, il
│   │       blocco avviene prima della pubblicazione, zero carico sul
│   │       tuo processo. Questa è la scelta giusta per un bot pubblico.
│   ├── 6.2 Filtri custom lato bot (zalgo, caps, attachment spam)     [Cand. Premium] [LIM]
│   │   └── Richiedono Message Content Intent → solo per quello che
│   │       l'AutoMod nativo non copre
│   └── 6.3 Azioni multiple configurabili                             [Cand. Premium] [OK]
│
├── 7. SECURITY SUITE
│   ├── 7.1 Anti-Raid                                                 [Free base] [OK]
│   │   ├── Join rate limit (finestra scorrevole)
│   │   ├── Account age check
│   │   ├── Pattern username / avatar identici
│   │   ├── Lockdown automatico (verification_level + permessi)
│   │   └── Quarantine role
│   ├── 7.2 Anti-Nuke                                                 [Cand. Premium] [LIM]
│   │   ├── Rilevamento via audit log su delete di massa
│   │   ├── [LIM] L'audit log arriva con ritardo variabile (secondi).
│   │   │   Un nuke veloce fa in tempo a completare. Puoi limitare il
│   │   │   danno, non impedirlo del tutto.
│   │   ├── Contromisura: rimozione permessi dell'esecutore + ban
│   │   └── Recovery [LIM]: ricrei canali e ruoli, ma i MESSAGGI
│   │       cancellati non sono recuperabili. Mai.
│   ├── 7.3 SPAM TRAP                                                 [Cand. Premium] → sezione dedicata §7.3 sotto
│   ├── 7.4 Permission Auditor                                        [Cand. Premium] [OK]
│   └── 7.5 Security Score                                            [Cand. Premium] [OK]
│
├── 8. LOGGING
│   ├── 8.1 Log semplificato (join/leave/ban/kick/ruoli)              [Free] [OK]
│   └── 8.2 Log completo                                              [Cand. Premium] [LIM]
│       ├── [LIM] Message delete/edit: il contenuto è disponibile solo
│       │   se il messaggio era in cache. Su 10.000 server la message
│       │   cache va tenuta piccolissima → molti log usciranno come
│       │   "contenuto non disponibile". È il comportamento normale
│       │   anche dei bot grandi.
│       ├── [LEG] Conservare contenuto messaggi in DB per i log è
│       │   soggetto a Developer Policy + GDPR. Retention breve e
│       │   dichiarata.
│       └── Eventi coperti: message delete/bulk/edit, member
│           join/leave/update, role CRUD, channel CRUD, invite
│           create/delete/use, voice join/leave/move/mute,
│           webhook CRUD, emoji/sticker/soundboard CRUD, guild update,
│           thread CRUD, automod action
│
├── 9. MUSIC                                                          → RIPROGETTATO
│   ├── 9.1 Un solo VoiceClient per server                            [Free] [OK]
│   │   └── Comandi: play, search, skip, forceskip, stop, pause,
│   │       resume, queue, remove, clear, shuffle, move, nowplaying,
│   │       loop track, loop queue, volume, seek, lyrics
│   ├── 9.2 Multi-canale nello stesso server                          [NO]
│   │   └── IMPOSSIBILE con un solo bot. Se lo vuoi davvero serve il
│   │       modello Jockie/Mackie: N applicazioni bot separate
│   │       (Yokai Music #1..#4), stesso codebase, stesso DB, invito
│   │       separato. I comandi di ognuna rispondono solo per il
│   │       proprio VoiceClient. Costo: N volte i gateway, N volte la
│   │       RAM, N verifiche Discord separate a 100 server.
│   ├── 9.3 Backend audio                                             [LIM]
│   │   └── Consiglio forte: Lavalink (processo Java separato) invece
│   │       di ffmpeg in-process. Su 2 OCPU l'encoding in-process per
│   │       decine di stream ti satura la CPU e fa lagare tutto il bot.
│   │       Con 12 GB e 2 core, il music è la feature che ti costa di
│   │       più: valuta di tenerlo Premium fin da subito.
│   ├── 9.4 Filtri audio (bassboost, nightcore, vaporwave, 8D)        [Cand. Premium] [OK con Lavalink]
│   ├── 9.5 DJ role + voteskip                                        [Free] [OK]
│   ├── 9.6 Auto-leave canale vuoto                                   [Free] [OK]
│   └── 9.7 Modalità 24/7                                             [Cand. Premium] [LIM]
│       └── YouTube: lo scraping per streaming è contro i ToS di
│           YouTube e viene attivamente bloccato (blocchi IP su IP
│           datacenter — Oracle è datacenter). Aspettati downtime
│           ricorrenti. Alternative più stabili: SoundCloud, Bandcamp,
│           stream radio, file caricati. Spotify NON permette lo
│           streaming audio via API: si può solo risolvere il titolo
│           e cercarlo altrove.
│
├── 10. ALERTS & SOCIAL
│   ├── 10.1 Twitch live/offline                                      [Free] [OK]
│   │   └── EventSub webhook (no polling). API ufficiale, gratuita.
│   ├── 10.2 YouTube nuovo video / live                               [Free] [OK]
│   │   └── PubSubHubbub su feed RSS del canale. Gratis, push.
│   ├── 10.3 Reddit                                                   [Cand. Premium] [OK]
│   ├── 10.4 RSS generico / webhook custom                            [Cand. Premium] [OK]
│   ├── 10.5 TikTok                                                   [Cand. Premium] [LIM]
│   │   └── Nessuna API pubblica per "nuovi video di un creator".
│   │       Solo scraping → fragile, si rompe spesso, contro ToS.
│   └── 10.6 Instagram                                                [NO]
│       └── L'API Graph copre solo account business che TU possiedi.
│           Monitorare account di terzi non è possibile legalmente.
│           Da togliere dallo schema o da implementare via servizi
│           terzi a pagamento (RSS.app, Apify).
│
├── 11. BACKUP SYSTEM                                                 → RIPROGETTATO [Cand. Premium]
│   ├── 11.1 Creazione automatica del server di backup                [NO]
│   │   └── POST /guilds è riservato ai bot in <10 server. Il tuo bot
│   │       pubblico non potrà mai creare un server.
│   ├── 11.2 ALTERNATIVE REALI (scegline una)
│   │   ├── A) Snapshot + restore guidato  ← CONSIGLIATA
│   │   │   ├── Il bot esporta la struttura in JSON (ruoli, permessi,
│   │   │   │   categorie, canali, emoji, sticker, impostazioni)
│   │   │   ├── L'owner crea a mano un server vuoto (5 secondi)
│   │   │   ├── Invita il bot e lancia /restore <snapshot_id>
│   │   │   └── Il bot ricostruisce tutto. Nessun limite API violato.
│   │   ├── B) Guild Template nativo di Discord
│   │   │   ├── Il bot genera/aggiorna un template ufficiale
│   │   │   └── [LIM] I template NON includono emoji, sticker,
│   │   │       soundboard, webhook, membri
│   │   └── C) Pool di bot-account dedicati al backup
│   │       └── Ogni account può creare max 10 server. Per 100 server
│   │           clienti servono 10+ applicazioni. Ingestibile e
│   │           facilmente letto da Discord come aggiramento. Sconsigliato.
│   ├── 11.3 Clonazione messaggi in tempo reale via webhook           [LEG] [LIM]
│   │   ├── [LIM] Rate limit 5 richieste / 5 secondi per canale.
│   │   │   Su un server attivo il mirror accumula ritardo e perde
│   │   │   messaggi in burst.
│   │   ├── [LIM] Gli allegati hanno URL firmati che SCADONO (~24h):
│   │   │   il mirror mostrerà immagini rotte dopo un giorno se non
│   │   │   li riscarichi e riospiti tu.
│   │   └── [LEG] Duplicare in tempo reale i messaggi di tutti gli
│   │       utenti su un server terzo, riproducendo la loro identità,
│   │       è trattamento di dati personali senza consenso. Questa è
│   │       la feature che più probabilmente ti fa chiudere
│   │       l'applicazione se segnalata.
│   ├── 11.4 User Backup + restore via OAuth2 guilds.join             [LEG] [LIM]
│   │   ├── Tecnicamente: sì. Servono scope guilds.join, refresh token
│   │   │   persistente, bot presente nel server target con permesso
│   │   │   CREATE_INSTANT_INVITE.
│   │   ├── [LIM] I token scadono; senza refresh periodico lo snapshot
│   │   │   è inutilizzabile al momento del bisogno.
│   │   ├── [LIM] Il join massivo è pesantemente rate-limitato:
│   │   │   ripristinare migliaia di utenti richiede ore.
│   │   └── [LEG] Discord ha storicamente colpito i servizi di questo
│   │       tipo. Conservare token OAuth di terzi è anche un obbligo
│   │       di sicurezza serio (cifratura a riposo, notifica breach).
│   └── 11.5 Comandi: /backup-create, /backup-list, /restore,
│            /define-main, /define-backup                             [OK]
│
├── 12. TEMPORARY VOICE CHANNELS                                      [Free] [OK]
│   ├── 12.1 Modalità Automatica (canale generatore → crea + sposta)
│   ├── 12.2 Modalità Manuale (pannello + bottone, nessuno spostamento)
│   ├── 12.3 Entrambe sempre visibili a tutti
│   │   └── VERIFICATO: i problemi di disconnessione su spostamento
│   │       forzato sono segnalati su PlayStation e su mobile, non
│   │       solo su PS. Non nascondere nulla in base alla piattaforma
│   │       è la scelta corretta. La selezione piattaforma resta utile
│   │       come ruolo informativo, non come filtro di visibilità.
│   ├── 12.4 Notifica: messaggio effimero + DM opzionale              [LIM]
│   │   └── Non puoi generare un "messaggio di sistema" di Discord.
│   │       Puoi solo mandare un ephemeral o un DM.
│   ├── 12.5 Pannello di gestione del proprio canale
│   │   ├── Rinomina / limite utenti / lock / unlock
│   │   ├── Kick utente / trasferimento proprietà
│   │   └── Whitelist e blacklist per canale
│   ├── 12.6 Eliminazione automatica quando vuoto
│   └── 12.7 [LIM] Limiti hard di Discord: 500 canali per server,
│            50 canali per categoria. Serve un cap configurabile.
│
├── 13. TICKET SYSTEM
│   ├── 13.1 Ticket base (pannello, apertura, claim, close)           [Free] [OK]
│   ├── 13.2 Categorie multiple, priorità, add/remove utente          [Free] [OK]
│   ├── 13.3 Transcript HTML                                          [Cand. Premium] [LIM]
│   │   └── Stesso problema degli allegati con URL firmati: vedi §7.3.5
│   ├── 13.4 Statistiche (tempo di risposta, per operatore)           [Cand. Premium] [OK]
│   └── 13.5 [LIM] 50 canali per categoria → su ticket alti serve
│            rotazione su più categorie
│
├── 14. UTILITY & SERVER MANAGEMENT
│   ├── 14.1 Reaction / Button / Select Roles                         [Free] [OK]
│   ├── 14.2 Welcome / Goodbye / Boost messages                       [Free] [OK]
│   ├── 14.3 Autoresponder                                            [Free] [LIM: msg content intent]
│   ├── 14.4 Custom Commands — sistema di RICHIESTA                   [Free] [OK]
│   │   ├── /richiedi-comando apre un Modal
│   │   ├── Campi: nome comando, descrizione, esempio d'uso
│   │   ├── Invio automatico nel canale #suggestions del server Yokai:
│   │   │   nome server, ID server, nome utente, ID utente,
│   │   │   descrizione, timestamp
│   │   ├── Bottoni staff: Approva / Rifiuta / Chiedi chiarimenti
│   │   └── Notifica di ritorno al richiedente via DM
│   ├── 14.5 Snipe / Editsnipe / Reactionsnipe                        [Free] [LIM]
│   │   └── Solo su messaggi in cache + msg content intent.
│   │       [LEG] Lo snipe ripubblica messaggi che un utente ha
│   │       deliberatamente cancellato: valuta un opt-out.
│   ├── 14.6 Ghost ping detection                                     [Free] [OK]
│   ├── 14.7 Sticky messages                                          [Free] [OK]
│   ├── 14.8 Suggestion system                                        [Free] [OK]
│   ├── 14.9 Poll                                                     [Free] [OK — usa il Poll nativo di Discord]
│   ├── 14.10 Reminder                                                [Free] [OK]
│   └── 14.11 Messaggi programmati                                    [Cand. Premium] [OK]
│
├── 15. LEVELS / ECONOMY / GILDE / CLASSIFICHE
│   ├── 15.1 XP e livelli (testuale + vocale)                         [Free] [OK]
│   │   └── [LIM] XP da messaggi senza msg content intent: puoi
│   │       contare i messaggi (evento on_message arriva sempre),
│   │       non leggerne il contenuto. Per l'XP basta.
│   ├── 15.2 Economy base: daily, work, shop, pay, leaderboard        [Free] [OK]
│   ├── 15.3 Giveaway (con requisiti ruolo/livello)                   [Free] [OK]
│   ├── 15.4 CLASSIFICHE                                              [Free] [OK]
│   │   ├── Classifica mensile utenti — reset automatico a fine mese
│   │   ├── Classifica totale all-time utenti
│   │   ├── Top 3 membri più attivi (XP o Coin, scelta del server)
│   │   ├── Classifica gilde mensile
│   │   ├── Classifica gilde totale
│   │   ├── Annuncio automatico vincitori a fine mese
│   │   └── [LIM] Il "reset" deve archiviare in una tabella storica,
│   │       non cancellare: altrimenti perdi i dati per l'all-time
│   └── 15.5 SISTEMA GILDE / CLAN                                     [Cand. Premium]
│       ├── 15.5.1 Creazione gilda + categoria privata dedicata       [OK]
│       ├── 15.5.2 Ruoli                                              [OK]
│       │   ├── Capo Clan (uno per gilda)
│       │   ├── Admin Clan (N per gilda)
│       │   └── REGOLA GERARCHICA (corretta come richiesto):
│       │       i ruoli Capo Clan di gilde diverse sono di PARI
│       │       livello tra loro. Stessa cosa per gli Admin Clan.
│       │       Nessuna gilda ha autorità su un'altra, a prescindere
│       │       dall'ordine di creazione.
│       │       [LIM] Discord ordina i ruoli in modo strettamente
│       │       verticale: due ruoli NON possono avere la stessa
│       │       posizione. L'uguaglianza si ottiene così:
│       │         • un unico ruolo "Capo Clan" condiviso da tutti i
│       │           capiclan + un unico ruolo "Admin Clan" condiviso
│       │         • zero permessi globali su entrambi
│       │         • tutti i permessi reali dati come OVERWRITE sul
│       │           singolo utente nella propria categoria
│       │       Così nessuno può agire fuori dalla propria sezione e
│       │       la gerarchia verticale non crea disparità.
│       │       [LIM] Limite di 250 ruoli per server.
│       ├── 15.5.3 Guadagno ×2 di XP e Coin nei canali della gilda    [OK]
│       ├── 15.5.4 Tesoreria di gilda                                 [OK]
│       │   ├── Deposito da qualunque membro
│       │   ├── Prelievo/spesa solo Capo Clan e Admin Clan
│       │   └── Log completo movimenti
│       ├── 15.5.5 Acquisto canali                                    [OK]
│       │   ├── Tipi: testuale, vocale, forum
│       │   ├── Costo coin ×2 per ogni canale successivo dello
│       │   │   stesso tipo: 10.000 → 20.000 → 40.000 → 80.000 → …
│       │   ├── Requisito ore vocali accumulate nella gilda:
│       │   │     1° canale →    10 ore
│       │   │     2° canale →    20 ore
│       │   │     3° canale →    40 ore
│       │   │     4° canale →   160 ore   (×4)
│       │   │     5° canale →   640 ore   (×4)
│       │   │     6° canale → 2.560 ore   (×4)
│       │   │     n° canale → formula: 40 × 4^(n-3) per n ≥ 4
│       │   ├── Le ore sono cumulative di gilda (10 persone × 1h = 10h)
│       │   └── [LIM] Cap obbligatorio: 50 canali per categoria,
│       │       500 per server. Oltre il 6°-7° canale i requisiti
│       │       diventano comunque irraggiungibili, quindi il cap
│       │       tecnico non darà mai fastidio.
│       ├── 15.5.6 Boost acquistabili                                 [OK]
│       │   ├── Boost XP individuale (durata + moltiplicatore)
│       │   ├── Boost Coin individuale
│       │   ├── Boost XP di gilda (tutti i membri)
│       │   └── Boost Coin di gilda
│       ├── 15.5.7 Isolamento totale tra gilde                        [OK]
│       ├── 15.5.8 Anti-farm                                          [OK] ← AGGIUNTO
│       │   ├── Nessun XP vocale se soli nel canale
│       │   ├── Nessun XP se mutati/sordi (self_mute / self_deaf)
│       │   ├── Nessun XP in canale AFK
│       │   ├── Cooldown XP testuale (60s)
│       │   └── Cap giornaliero di ore vocali conteggiabili per utente
│       └── 15.5.9 Comandi: /gilda crea, invita, espelli, promuovi,
│                  tesoreria, deposita, compra-canale, boost, info,
│                  classifica, sciogli
│
├── 16. FUN & IMMAGINI
│   ├── 16.1 Mini-giochi, meme, animal, ship, rate, 8ball,
│   │        image manipulation                                       [Free] [OK]
│   ├── 16.2 Immagini SFW (ricerca + random)                          [Free] [OK]
│   └── 16.3 NSFW / Rule 34                                           [NP] → vedi sezione finale
│
└── 17. OWNER / GLOBAL ADMIN                                          [Solo proprietario]
    ├── 17.1 Eval / Exec                                              [OK]
    │   └── [LIM] Shell remota su un bot pubblico: se il tuo account
    │       Discord viene compromesso, chi entra ha root sulla VM.
    │       Metti almeno un secondo fattore (conferma via canale
    │       privato dedicato o chiave a tempo).
    ├── 17.2 Gestione Premium List (add / remove Server ID)
    ├── 17.3 PANNELLO FLAG PREMIUM                                    [OK]
    │   ├── Comando: /owner premium
    │   ├── Pannello interattivo riservato (check user_id == OWNER_ID)
    │   ├── Lista paginata di tutti i moduli con stato Free/Premium
    │   ├── Toggle della flag premium per singolo modulo (globale)
    │   ├── Vista server whitelistati
    │   ├── Vista server che perderebbero accesso attivando la flag
    │   ├── Conferma a due step per ogni modifica
    │   └── Log persistente di ogni cambio (modulo, da→a, timestamp)
    ├── 17.4 Blacklist globale utenti e server
    ├── 17.5 Forced cog load / unload / reload
    ├── 17.6 Annuncio globale
    ├── 17.7 Statistiche globali (guild count, shard health, RAM,
    │        latenza, comandi/minuto, errori)
    └── 17.8 Leave guild forzato
```
---
§7.3 — SPAM TRAP (specifica dettagliata)
Questa è la parte nuova dell'ultimo messaggio. L'ho scritta per intero perché è quella dove le differenze tra "come lo immagini" e "cosa permette l'API" contano di più.
7.3.1 Configurazione — `/setup` → sezione Spam Trap
Campo	Tipo	Comportamento se non selezionato
Canale trappola	Select canali	Il bot crea `#spam-trap`
Canale log	Select canali	Il bot crea `#spam-log`
Permessi applicati a `#spam-trap` alla creazione:
Permesso	@everyone
View Channel	✅
Send Messages	✅ (deve essere possibile scrivere, è la trappola)
Create Invite	❌
Manage Webhooks	❌
Attach Files / Embed Links	✅ (serve per loggare cosa hanno inviato)
Permessi applicati a `#spam-log`: visibile solo ai ruoli con `administrator`, più il bot. `@everyone` → View Channel negato.
`[LIM]` Un permesso `Manage Webhooks` negato a `@everyone` non blocca chi ha Administrator. Nessun override batte Administrator, mai.
7.3.2 Embed di presidio (in inglese, come richiesto)
In `#spam-trap` — colore rosso acceso (`#FF2D00`):
```
# DO NOT WRITE IN THIS CHANNEL — YOU WILL BE BANNED

This channel is part of the automated security system of <server name>.
Any message sent here results in an immediate and permanent ban.
It exists to detect and stop raids, spam and scam campaigns.

This is an automated message. Please use the regular channels of the
server to talk with the community.
```
L'header grande si ottiene con `# ` a inizio riga nella description dell'embed (Discord supporta i markdown heading negli embed).
In `#spam-log` — colore blu/verde tenue (`#3BA55D`):
```
Security Log Channel

This channel collects the reports generated by the spam trap system.
For every triggered ban you will find here: user tag and ID, user ID,
join date, ban date, invite code used and its creator, the content that
triggered the trap, and the number of deleted messages.
```
7.3.3 Sequenza di intervento
L'ordine qui sotto non è modificabile, perché il punto 2 dopo il punto 3 non funziona:
```
1. on_message in #spam-trap (utente non-bot, non-staff)
   └── Cattura immediata del contenuto in memoria
       (testo, allegati, timestamp, message_id)

2. ⚠️ DM ALL'UTENTE — PRIMA DEL BAN, OBBLIGATORIO
   └── Dopo il ban non esiste più un server in comune e il bot
       NON PUÒ PIÙ APRIRE UN DM. Se mandi il DM dopo, non arriva
       e l'intero sistema di ban appeal non parte.
       Una volta che il canale DM esiste, l'utente può continuare a
       scrivere al bot anche da bannato: l'appeal funziona.

3. Ban (reason: "Spam trap triggered")
   └── delete_message_seconds = 604800
       ⚠️ IL MASSIMO CONSENTITO DA DISCORD È 7 GIORNI, NON 30.
          I 30 giorni richiesti non sono ottenibili da questo parametro.

4. Purge supplementare (vedi 7.3.4)

5. Cleanup delle tracce
   ├── Webhook creati dall'utente → identificati via audit log
   ├── Inviti creati dall'utente → revocati
   ├── Canali/ruoli creati dall'utente → segnalati allo staff
   │   (cancellarli in automatico è pericoloso: falsi positivi)
   └── [LIM] Audit log: massimo 45 giorni di storico, richiede
       VIEW_AUDIT_LOG

6. Embed di log in #spam-log
   ├── Tag utente + menzione
   ├── User ID
   ├── Data di creazione account
   ├── Data di join nel server
   ├── Data/ora del ban
   ├── Codice invito usato + creatore dell'invito
   ├── Contenuto che ha fatto scattare la trappola
   │   (testo + nomi allegati + hash SHA-256 degli allegati)
   ├── Numero di messaggi cancellati, per canale
   └── Allegato: transcript HTML (vedi 7.3.5)
```
7.3.4 La cancellazione a 30 giorni — cosa è davvero possibile
Questo è il punto che va ridimensionato. Sono tre limiti sommati:
`delete_message_seconds` sul ban copre al massimo 7 giorni.
`bulk_delete` funziona solo su messaggi più recenti di 14 giorni. Oltre, è cancellazione uno a uno.
Non esiste un endpoint di ricerca messaggi per i bot. La search di Discord è riservata al client utente. Il bot non può chiedere "dammi tutti i messaggi di questo user ID".
Quindi, per arrivare a 30 giorni, le uniche due strade sono:
Strada A — indicizzazione preventiva `[LEG]`
Il bot salva in PostgreSQL `(message_id, channel_id, user_id, timestamp)` di ogni messaggio del server. Al ban, legge gli ID dal DB e cancella mirato. Funziona, è veloce, ed è quello che fanno i bot seri.
Costi: un server attivo genera milioni di righe; conservare metadati dei messaggi di tutti gli utenti ricade sotto Developer Policy e GDPR (metti retention 30 giorni e dichiarala).
Strada B — scansione history al momento del ban `[LIM]`
Il bot scorre `channel.history(after=now-30d)` su ogni canale. Su un server con 50 canali e molto traffico significa minuti, non "tempo zero", e consuma tutto il budget di rate limit.
Raccomandazione: ban istantaneo + 7 giorni via `delete_message_seconds` (quello sì, è immediato e copre il 99% dei raid, che durano minuti) + Strada A come modulo premium per chi vuole i 30 giorni.
Sulla velocità: il ban è istantaneo, e in un raid è quello che conta. La cancellazione no: il limite è 5 richieste ogni 5 secondi per canale. Con 400 messaggi su 4 canali in bulk delete sei sui 2-4 secondi. Con messaggi vecchi oltre i 14 giorni, uno alla volta, sei sui minuti.
7.3.5 Transcript HTML — fattibile, ma attenzione a un dettaglio
Generare l'HTML con timestamp, username, nickname, avatar e immagini inline: sì, fattibile.
Il problema: gli URL degli allegati Discord sono firmati e scadono (parametri `ex`, `is`, `hm`, validità circa 24 ore). Un transcript che linka il CDN mostrerà immagini rotte il giorno dopo. Per averle visibili davvero devi scaricarle e riospitarle tu.
E qui la tua preoccupazione va rovesciata: incorporare le immagini non infetta il PC dell'admin (il browser renderizza, non esegue), ma ospitare sul tuo server file arbitrari caricati da spammer ti rende responsabile del loro contenuto. Un raid può caricare materiale illegale, e te lo ritrovi sul tuo disco Oracle.
Tre opzioni, in ordine di sicurezza:
Opzione	Immagini visibili	Rischio
Solo metadati (nome file, dimensione, hash SHA-256, tipo MIME)	❌	Nessuno — consigliata
Thumbnail rigenerata server-side (decodifica → ridimensiona → ricodifica in WebP, strip metadata)	✅	Basso, ma ospiti comunque il contenuto
Riospitare il file originale	✅	Alto — sconsigliato
La rigenerazione della thumbnail neutralizza anche i file polyglot (l'immagine viene decodificata e ricodificata, qualunque payload nascosto muore). Se vuoi le immagini nel transcript, fai così, e metti una retention di 7 giorni sui file.
L'HTML va comunque generato con escaping rigoroso di ogni campo (nickname, contenuto messaggio): un nickname con `<script>` dentro un transcript aperto dall'admin è XSS vera.
7.3.6 Ban Appeal
```
Utente bannato → riceve DM (inviata prima del ban)
   ├── Motivo: messaggio in un canale di sicurezza di <server>
   ├── Nome del server (mai l'ID)
   └── "Rispondi a questo messaggio per fare appello"
        │
        └── Il bot riceve il DM
             ├── Rate limit: 1 appello per utente per server, 24h
             ├── Apre un THREAD privato in #spam-log
             │   (meglio del DM agli admin: resta nel server, è
             │    consultabile da tutto lo staff, non intasa i DM)
             ├── Allega il transcript completo dei messaggi cancellati
             │   con timestamp, testo e riferimenti agli allegati
             └── Bottoni staff: Sbanna / Rifiuta / Rispondi
                  └── Sbanna → il bot rimuove il ban e notifica l'utente
```
`[LIM]` Se l'utente ha i DM chiusi verso non-amici, il messaggio del punto 2 non parte. Il sistema deve degradare bene: logga "DM non recapitato" e procede col ban.
---
Cosa non ho messo nello schema, e perché
1. Yokai Selfbot Module — rimosso
Non lo progetto. Le ragioni, in ordine di gravità:
Manda in ban i tuoi utenti paganti. I self-bot violano i ToS di Discord e la rilevazione è automatizzata. Vendere un prodotto la cui conseguenza prevedibile è la perdita dell'account del cliente è, in Italia, un problema contrattuale prima ancora che tecnico.
Distrugge il resto del progetto. Se Discord collega la distribuzione del self-bot alla tua applicazione verificata, non perdi il modulo: perdi il bot, l'account sviluppatore e i 10.000 server.
Il "cifrato e blindato" non regge. Un `.exe` PyInstaller si decompila in minuti, e comunque il token utente deve stare in chiaro in memoria per essere usato.
Nighty non è un modello di sostenibilità: quel tipo di servizio vive finché Discord non interviene.
Cosa puoi fare legittimamente al posto suo, e che copre buona parte del valore percepito:
Rich Presence vera tramite Discord Social SDK / attività registrata: l'utente esegue un piccolo client ufficiale collegato alla tua applicazione e ottiene una presence personalizzata, senza user token e senza rischio ban.
Activities (attività in-call) tramite l'Embedded App SDK.
Tutto il resto della personalizzazione profilo (avatar, banner, bio) è già offerto da Discord con Nitro: non è un mercato dove competere aggirando la piattaforma.
Se decidi comunque di farlo, fallo da un'identità e un'infrastruttura completamente separate da Yokai, mai collegate.
2. NSFW / Rule 34 con auto-post casuale — non progettato come richiesto
La ricerca manuale in canale age-restricted è cosa comune. Il post automatico casuale a intervalli no, e non lo progetto in quella forma per una ragione specifica: i booru tipo Rule34 contengono tag di contenuti sessuali che raffigurano minori (categorie come `loli`/`shota`), inclusi nei risultati "random". Il possesso e la distribuzione di quel materiale, anche in forma disegnata, è reato in Italia (art. 600-quater.1 c.p., pornografia virtuale). Un timer che pesca a caso e pubblica ti rende l'editore di quello che esce.
Se vuoi comunque questo modulo, queste sono condizioni non negoziabili:
allowlist di tag, non blocklist (si dichiara cosa può uscire, non cosa non deve);
blocklist aggiuntiva hardcoded e non modificabile dai server;
niente modalità "random puro" — sempre vincolata ai tag scelti dall'admin e filtrata;
solo canali con flag NSFW verificato a runtime a ogni post;
log di ogni immagine pubblicata con hash, per poter risalire e rimuovere.
Aggiungo che questo modulo, da solo, rende molto più difficile la verifica dell'applicazione a 100 server. Se l'obiettivo sono i 10.000 server, i due obiettivi sono in conflitto: scegline uno.
3. Instagram alerts — rimosso
Nessuna API permette di monitorare account di terzi. Vedi §10.6.
4. Avatar per-server del bot — rimosso
Grok ti ha detto che esistono i "per-guild bot profiles". Non è confermato per i bot: le discussioni sull'API mostrano che i per-guild avatar sono in sola lettura per le applicazioni e non impostabili. Quello che è garantito è il nickname per server (`guild.me.edit(nick=...)`), che va benissimo per l'identità "Bot di <Server X>".
---
Riepilogo delle modifiche che ho fatto allo schema
#	Voce	Modifica
1	Backup System — creazione server	`[NO]` — bot in >10 server non possono creare guild. Sostituito con snapshot + restore guidato
2	Music multi-canale stesso server	`[NO]` — una voice connection per guild. Serve il modello multi-bot
3	Cancellazione messaggi 30 giorni	Ridotto a 7 giorni nativi + indicizzazione DB per andare oltre
4	DM di notifica ban	Spostato prima del ban (dopo è impossibile)
5	Caricamento cog per-server	Riscritto: check runtime, non load/unload per guild
6	Avatar per-server del bot	Rimosso, non disponibile per i bot
7	Instagram alerts	Rimosso, nessuna API
8	Ruoli gilda "pari livello"	Risolto con ruolo unico condiviso + overwrite per utente
9	Selfbot Module	Rimosso, con alternative legittime indicate
10	NSFW auto-post random	Non progettato in forma random; condizioni indicate
11	Sharding Manager	Aggiunto (mancava, obbligatorio oltre 2.500 server)
12	Anti-farm economia gilde	Aggiunto (mancava, l'XP vocale è banalmente farmabile)
13	AutoMod nativo Discord	Aggiunto come base dei filtri, risparmia il message content intent
14	Lavalink per il music	Aggiunto come raccomandazione architetturale
15	Transcript HTML	Aggiunta gestione URL firmati scaduti + thumbnail rigenerate
16	Sblocco premium con coin	Segnalato come aggirabile dagli admin
17	Verifica Discord a 100 server	Aggiunto come blocco critico §0.1
---
Da dove partirei, concretamente
Nell'ordine, perché ogni fase abilita la successiva:
Core + DB + setup + premium flags — l'infrastruttura, senza feature.
Moderation + AutoMod nativo + Logging semplificato — il set che ti fa passare la verifica.
Ticket + Vocali temporanei + Reaction roles — alto valore percepito, zero rischio.
Livelli + Economy + Classifiche — poi Gilde sopra, quando l'economia è stabile.
Verifica Discord a ~90 server.
Music (con Lavalink) e Alerts.
Security Suite + Spam Trap — dopo, perché è quella che tocca l'audit log e va testata con calma.
Snapshot/Restore al posto del backup automatico.
Web panel, solo se decidi di affrontare la parte fingerprint con una privacy policy vera.
---
---
REV. 2 — Decisioni prese
Data: 16 settembre 2026. Questa sezione prevale su quanto scritto sopra dove i due testi divergono.
R2.1 — Mappa delle applicazioni Discord
Il progetto non è più un bot solo. Sono otto identità distinte, ognuna con il suo token, il suo invito e la sua soglia di verifica a 100 server.
#	Applicazione	Tipo	Ruolo	Verifica a 100 server
1	Yokai Bot	Guild bot pubblico	Tutto il core: setup, moderation, automod, security, log, ticket, vocali temporanei, livelli, economia, gilde, alert, utility	Sì — è quella che deve passare pulita
2	Yokai Creator	Guild bot privato	Crea il server di backup, cede la ownership, invita Yokai Bot, esce. Sempre sotto i 10 server.	No — non deve mai superare i 10
3-7	Yokai Music #1..#5	Guild bot pubblici	Una connessione vocale ciascuno. Aggiunti automaticamente da Yokai Bot al setup del modulo music.	Sì, cinque volte
8	Yokai NSFW	Guild bot pubblico	Solo modulo R34/NSFW, isolato per non contaminare la review dell'app principale	Sì, separatamente
—	Yokai Desktop	App locale (RPC)	Presence personalizzata via socket IPC del client Discord. Nessun user token.	Non applicabile
—	Yokai Panel	Web app	Verify avanzato, OAuth2, dashboard owner	Non applicabile
Yokai Bot è l'orchestratore: al setup genera gli inviti delle applicazioni ausiliarie e verifica che siano entrate, ma i moduli restano indipendenti.
R2.2 — Backup: flusso definitivo
```
FASE SETUP (una sola volta, all'attivazione del modulo)
 1. L'owner OG lancia /backup setup su Yokai Bot
 2. Yokai Bot accoda la richiesta al Creator
 3. Yokai Creator crea il server "Backup - <Nome OG>"
 4. Genera un invito monouso a scadenza breve → DM all'owner OG
 5. L'owner OG entra nel server di backup
 6. PATCH owner_id → l'owner OG diventa owner IMMEDIATAMENTE
 7. Il Creator invita Yokai Bot nel backup
 8. Il Creator ESCE → slot liberato, coda avanza

FASE OPERATIVA
 • Yokai Bot clona struttura (ruoli, permessi, categorie, canali,
   emoji, sticker, soundboard)
 • Mirror messaggi in tempo reale via webhook, se attivato

FASE RESTORE
 • /restore → ripopola struttura e utenti
 • Nessun trasferimento di ownership: il server è già del cliente
```
Vincoli operativi:
Creazioni serializzate, una alla volta. Coda persistente in DB con stato (`pending` → `created` → `transferred` → `released`) e timeout: se l'owner non entra entro 15 minuti, il Creator cancella il server e libera lo slot.
Rate limit su `POST /guilds` non documentato e molto stretto → throttling prudente (es. una creazione ogni pochi minuti) e monitoraggio dei 429.
Se il Creator resta bloccato a 9-10 server per owner che non completano, tutto il modulo si ferma: il timeout del punto sopra non è opzionale.
Mirror in tempo reale — limiti da progettare, non da scoprire dopo:
5 richieste / 5 secondi per canale via webhook.
Coda per canale con politica di scarto dichiarata: in caso di burst, i messaggi eccedenti vengono compattati in un riepilogo invece di essere persi silenziosamente.
Allegati: URL firmati con scadenza ~24h. Il mirror mostrerà immagini rotte il giorno dopo se non li riscarichi e riospiti.
Resta il punto `[LEG]`: duplicare i messaggi degli utenti su un server terzo riproducendone l'identità è trattamento di dati personali. Opt-in a livello di server, dichiarato agli utenti nel server originale.
R2.3 — Music: 5 istanze + stream proprietario
5 applicazioni separate, aggiunte da Yokai Bot al setup. Ognuna gestisce una sola connessione vocale per server.
Lavalink obbligatorio, in passthrough Opus dove possibile. I filtri audio impongono ricodifica: premium e con cap.
24/7: cap duro sul numero di istanze concorrenti a livello globale (valore iniziale suggerito: 50), oltre il quale la richiesta va in coda. Non basta renderlo premium.
Stream 24/7 con musica di proprietà (composta, prodotta e pubblicata dall'utente, diritti detenuti): un singolo decoder condiviso distribuito a N server invece di N decoder. Elimina sia il problema legale sia gran parte del costo CPU. È la modalità 24/7 di default.
YouTube resta disponibile per il play on-demand, con l'avvertenza dei blocchi su IP datacenter.
R2.4 — NSFW: applicazione separata
Modulo spostato su Yokai NSFW, applicazione a sé, aggiungibile in fase di setup.
Filtro a due strati, entrambi obbligatori:
Allowlist di categorie/tag decisa dall'owner del server — solo ciò che è esplicitamente ammesso può uscire.
Blocklist hardcoded non modificabile dai server, applicata sopra l'allowlist, che scarta il risultato se i tag dell'immagine contengono voci vietate anche quando non erano nella query.
Entrambi gli strati valgono sia sulla ricerca manuale sia sull'auto-post. Verifica del flag NSFW del canale a runtime, a ogni singolo post. Log con hash di ogni immagine pubblicata per poter risalire e rimuovere.
R2.5 — Presence: RPC al posto del selfbot
Yokai Desktop, app locale che parla con il socket IPC del client Discord (`discord-rpc`). Nessun user token, nessun rischio ban.
Copre: activity personalizzata (giocando / ascoltando / guardando / competendo), immagini grande e piccola con testi al passaggio, bottoni, timestamp, rotazione automatica di più stati, profili salvati.
Non copre, e non esiste via legittima: custom status testuale con emoji, bio animate, cambio avatar/banner a rotazione.
Vie ufficiali complementari da valutare più avanti:
User-installable app (`USER_INSTALL`): comandi personali disponibili ovunque, anche in DM.
Activities (Embedded App SDK): app interattive dentro il canale vocale.
Linked Roles: metadati verificati dal tuo servizio, visibili sul profilo — ottimo aggancio per il verify avanzato.
Application Subscriptions: monetizzazione nativa, gestisce pagamenti e rinnovi.
R2.6 — Verify avanzato: separazione degli scope OAuth2
Elemento chiave emerso: Discord non vede cosa raccoglie il web panel. Ciò che viene valutato in review sono gli scope richiesti.
Scope	Usato da	Impatto in review
`identify`	Verify avanzato + fingerprint	Nessuno, è lo scope più comune
`guilds.join`	Solo modulo backup/restore utenti	Alto — è lo scope dei servizi di mass-join
Vanno richiesti in flussi separati, mai insieme. `guilds.join` solo a chi attiva esplicitamente il restore utenti.
Configurazione del fingerprint (decisa):
IP mai in chiaro nel database. Solo hash del fingerprint composito (canvas, WebGL, font, audio context).
L'IP è un segnale debole: CGNAT mobile, IPv6 dinamici, VPN. Peso basso nello scoring.
Un match produce segnalazione allo staff, non ban automatico.
Ban automatico consentito solo su match multipli e solo entro lo stesso server.
Nessun ban automatico cross-server.
Retention 90 giorni, opt-in esplicito in pagina, privacy policy pubblicata.
R2.7 — Anti-farm XP vocale (regole definitive)
L'XP vocale matura solo se tutte queste condizioni sono vere:
l'utente non è `self_deaf`
nel canale c'è almeno un'altra persona non mutata
il canale non è l'AFK channel
non sono trascorse più di 2 ore consecutive nello stesso canale (oltre, XP azzerato finché non cambia canale)
non è stato superato il cap giornaliero (suggerito: 6 ore conteggiabili per utente)
Nota: la ricezione audio non è supportata ufficialmente per i bot, quindi non è possibile rilevare chi sta effettivamente parlando. Le condizioni sopra sono il miglior proxy disponibile.
R2.8 — AutoMod ibrido (plug and play)
Al setup Yokai Bot legge le regole AutoMod native esistenti e:
crea quelle mancanti previste dal suo preset
aggiorna quelle presenti unendo le proprie voci a quelle già configurate dall'owner, senza mai sovrascrivere
Richiede `MANAGE_GUILD`. Le regole vanno consolidate: i limiti Discord sono nell'ordine di ~6 regole keyword per server, una sola per spam e una per mention-spam, circa 1000 voci per lista e ~10 pattern regex. Una regola per categoria non è praticabile.
Divisione delle responsabilità:
contenuto (parole, link, inviti, mention) → AutoMod nativo
comportamento (stesso messaggio su più canali, raid coordinato, spam di allegati, pattern temporali) → logica del bot
R2.9 — Message Content Intent: come formulare la richiesta
L'intent verrà richiesto, ma la motivazione dichiarata deve essere quella reale e canonica:
> logging dei messaggi cancellati e modificati, automod comportamentale, sistemi anti-spam basati su pattern
La formulazione da non usare, perché configura raccolta massiva di dati e viene respinta:
> archiviazione di tutti i messaggi del server su un server di backup
Il mirror di backup resta una feature opt-in di un modulo separato, non la giustificazione dell'intent.
R2.10 — Ordine di sviluppo aggiornato
Fase	Contenuto	Applicazione
0	Schema database + repository layer + migrazioni	—
1	Core, sharding, setup, premium flags, memory guard	Yokai Bot
2	Moderation + AutoMod ibrido + logging semplificato	Yokai Bot
3	Ticket, vocali temporanei, reaction roles	Yokai Bot
4	Livelli, economia, classifiche, poi Gilde	Yokai Bot
5	Richiesta verifica + Message Content Intent a ~90 server	Yokai Bot
6	Music (Lavalink) + stream proprietario 24/7	Music #1..#5
7	Alert social (Twitch EventSub, YouTube PubSubHubbub)	Yokai Bot
8	Security Suite completa + Spam Trap	Yokai Bot
9	Web panel, verify avanzato, privacy policy	Yokai Panel
10	Backup: Creator + snapshot + mirror	Yokai Creator
11	NSFW	Yokai NSFW
12	Presence RPC	Yokai Desktop
