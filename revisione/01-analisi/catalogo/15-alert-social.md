# Catalogo — Alert social

Avvisi di dirette e nuovi contenuti (Twitch, YouTube, Kick, Reddit,
RSS, TikTok, Instagram, X, Facebook, podcast…), ruolo "in diretta",
personalizzazione dei messaggi. 49 voci. Bot letti: Streamcord,
Pingcord, YAGPDB, Carl-bot, Red-DiscordBot, NadekoBot, Arcane, Lawliet,
MEE6.

Legenda: ❌ manca · 🟡 parziale. "Scheda": NF-xx = scheda di
`NUOVE_FUNZIONI.md`; M x.y = riga di `MODIFICHE_ESISTENTE.md`;
"nuova" = non c'è ancora in nessun piano.

iYokai oggi (per confronto): `/alerts add` (qualsiasi feed RSS/Atom,
quindi anche video YouTube e subreddit, con modello di messaggio
`{label} {title} {link}`), `/alerts add-twitch` (in diretta e fine
diretta, controllo ogni 90 secondi), `/alerts add-youtube-live` (con
chiave API), `/alerts list`, `/alerts remove`, `/alerts webhook-create`
(webhook in ingresso). Nessuna opzione per menzionare un ruolo.

## 1. Piattaforme

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| ALR-001 | Dirette su Kick | Streamcord [STREAMCORD], Pingcord (premium, beta) [PINGCORD], MEE6 (premium) [MEE6] | ❌ manca | `/admin alert aggiungi-kick`; quote di Kick da scrivere in `LIMITI.md` | NF-32 |
| ALR-002 | Nuovi video su TikTok | Pingcord [PINGCORD], MEE6 (premium) [MEE6] | ❌ manca | Nessuna API gratuita: feed "ponte" RSS o webhook in ingresso, con guida; chiave a pagamento facoltativa (D14) | NF-32 |
| ALR-003 | Nuovi post su Instagram | Pingcord (premium) [PINGCORD], MEE6 (premium) [MEE6] | ❌ manca | Come ALR-002 | NF-32 |
| ALR-004 | Nuovi post su X (Twitter) | Pingcord (premium, beta) [PINGCORD], MEE6 (premium) [MEE6], Sapphire [SAPPHIRE] | ❌ manca | Come ALR-002 | NF-32 |
| ALR-005 | Dirette e post delle Pagine Facebook | Pingcord [PINGCORD] | ❌ manca | Come ALR-002 | nuova |
| ALR-006 | Nuovi post su Bluesky | MEE6 (premium) [MEE6] | ❌ manca | Bluesky offre un feed RSS per profilo: funziona già con `/alerts add`; serve solo una scorciatoia che costruisce l'indirizzo | nuova |
| ALR-007 | Nuovi episodi di un podcast | MEE6 (premium) [MEE6], Pingcord (podcast di Spotify, premium, beta) [PINGCORD] | 🟡 parziale: i podcast hanno un feed RSS, ma va cercato a mano | `/admin alert aggiungi-podcast <nome>`: ricerca del feed e uso del motore RSS | nuova |
| ALR-008 | Dirette su Picarto | Red (`streamalert picarto`) [RED] | ❌ manca | Bassa priorità | nuova |
| ALR-009 | YouTube: Short separati dai video, da includere o no | YAGPDB ("also publish shorts") [YAGPDB], Arcane [ARCANE] | 🟡 parziale: il feed porta tutto insieme | Riconoscere gli Short dal link e filtrarli | nuova |
| ALR-010 | YouTube: dirette e "première" programmate, da includere o no | YAGPDB ("also publish livestreams", `.IsUpcoming`) [YAGPDB], Pingcord [PINGCORD] | 🟡 parziale: dirette solo con chiave API e quota che finisce (BUG-16) | D5: feed più `videos.list` a gruppi di 50 | M 11.1 |
| ALR-011 | Aggiungere un canale YouTube incollando qualsiasi link (video, Short, handle, playlist) | YAGPDB [YAGPDB], Carl-bot (`youtube add`) [CARL] | 🟡 parziale: serve l'ID del canale o l'indirizzo del feed | Ricavare l'ID dalla pagina del link (una richiesta, con `core/safe_http.py`) | nuova |
| ALR-012 | Twitch: pubblicare la registrazione (VOD) a fine diretta | YAGPDB [YAGPDB], Pingcord ("live and video") [PINGCORD] | ❌ manca | Una chiamata `Get Videos` a fine diretta | nuova |
| ALR-013 | Twitch: eventi Discord creati dal calendario del canale | Streamcord (Pro) [STREAMCORD] | ❌ manca | `Get Channel Stream Schedule`; permesso `CREATE_EVENTS` | nuova |
| ALR-014 | Reddit: scegliere se pubblicare con embed o come testo | YAGPDB [YAGPDB] | 🟡 parziale: un solo formato | Opzione `formato` | nuova |
| ALR-015 | Novità di anime e manga (notizie, nuovi episodi, uscite) | Lawliet (`animenews`, `crunchyroll`, `anilist`, `mangaupdates`) [LAWLIET] | 🟡 parziale: possibile solo se il sito ha un feed RSS | Scorciatoie verso feed noti | nuova |
| ALR-016 | Qualsiasi comando "di ricerca" usato come avviso periodico (meme, subreddit, immagini) | Lawliet (`alerts`: comando più argomento) [LAWLIET] | ❌ manca | Solo per poche sorgenti sicure (subreddit SFW, meme) | nuova |
| ALR-017 | Giochi gratis del momento (Epic, Steam…) | FreeStuff (non verificato: sito non letto) | 🟡 parziale: possibile con un feed RSS trovato a mano | Feed pronto scelto dall'owner; utile a una community di gioco | nuova |

## 2. Messaggio dell'avviso

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| ALR-018 | Menzionare un ruolo scelto a ogni avviso | YAGPDB (RSS, YouTube, Twitch) [YAGPDB], Red (`streamset mention role`) [RED], Arcane [ARCANE] | ❌ manca | Opzione `ruolo`; `allowed_mentions` solo per quel ruolo (D12) | M 10.6 |
| ALR-019 | Menzionare @everyone o @here | YAGPDB [YAGPDB], Red (`streamset mention all`, `mention online`) [RED], Carl-bot (`{everyone}`) [CARL] | ❌ manca | Solo se chi configura ha "Menziona tutti" | M 10.6 |
| ALR-020 | Messaggio personalizzato anche per Twitch e YouTube | Carl-bot (`twitch fmt`) [CARL], YAGPDB [YAGPDB], NadekoBot (`.streammsg`, `.streammsgall`) [NADEKO], Arcane (`{video.url}`, `{video.title}`, `{video.author}`) [ARCANE] | 🟡 parziale: il modello vale solo per RSS e webhook | Modello per ogni tipo, con `core/template_renderer.py` | M 11.6 |
| ALR-021 | Due testi: uno con la menzione e uno senza | Red (`streamset message mention`, `nomention`) [RED] | ❌ manca | Basta il segnaposto `{ruolo}` nel modello | nuova |
| ALR-022 | Segnaposto con gioco e titolo della diretta | YAGPDB (`.Game`, `.Title`) [YAGPDB], Carl-bot (`{game}`) [CARL] | 🟡 parziale: Twitch ha `{label} {title} {login}` | Aggiungere `{gioco}` | M 11.6 |
| ALR-023 | Segnaposto del video: miniatura, descrizione, durata | YAGPDB (`.VideoThumbnail`, `.VideoDescription`, `.VideoDurationSeconds`) [YAGPDB] | ❌ manca | Dati già nel feed Atom di YouTube (tranne la durata) | nuova |
| ALR-024 | Controllo completo dell'embed dell'avviso (ogni campo) | Pingcord (premium) [PINGCORD], Streamcord (colore, miniatura) [STREAMCORD] | ❌ manca | Collegare un embed salvato (NF-17) con i segnaposto | NF-17 |
| ALR-025 | Bottone "Guarda" sotto l'avviso | Red (`streamset usebuttons`) [RED] | ❌ manca | Bottone-link (non serve una vista persistente) | nuova |
| ALR-026 | Avviso cancellato da solo quando la diretta finisce | Red (`streamset autodelete`) [RED], NadekoBot (`.streamonlinedelete`) [NADEKO], Streamcord ("cleanup") [STREAMCORD] | ❌ manca | Salvare l'ID del messaggio e cancellarlo a fine diretta | nuova |
| ALR-027 | Messaggio "diretta finita" che si può accendere o spegnere | NadekoBot (`.streamoffline`) [NADEKO], Streamcord [STREAMCORD], Pingcord (premium) [PINGCORD] | 🟡 parziale: l'avviso di fine diretta c'è sempre | Interruttore per iscrizione | nuova |
| ALR-028 | Avvisi pubblicati da soli nei canali annunci (così arrivano ai server che li seguono) | Streamcord [STREAMCORD] | ❌ manca | `message.publish()` dopo l'invio; limite di Discord sulle pubblicazioni all'ora | nuova |
| ALR-029 | Testo fisso allegato a ogni avviso (per esempio un ping) | Lawliet (a pagamento) [LAWLIET] | ❌ manca | Coperto dal modello di messaggio | M 11.6 |

## 3. Filtri e frequenza

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| ALR-030 | Avviso solo se la diretta è di un certo gioco | Streamcord [STREAMCORD], YAGPDB ("Game Regex") [YAGPDB] | ❌ manca | Opzione `gioco`; il nome del gioco è già nella risposta di Twitch | nuova |
| ALR-031 | Avviso solo se il titolo contiene certe parole | Streamcord [STREAMCORD], YAGPDB ("Stream Title Regex") [YAGPDB], Pingcord (condizioni, premium) [PINGCORD] | ❌ manca | Opzione `parole`; confronto semplice, niente regex libere | nuova |
| ALR-032 | Ignorare le repliche | Red (`streamset ignorereruns`) [RED] | ❌ manca | Campo `type` della diretta Twitch | nuova |
| ALR-033 | Pausa minima tra due avvisi dello stesso canale | Streamcord ("cooldown") [STREAMCORD], Lawliet (intervallo minimo, a pagamento) [LAWLIET] | ❌ manca | Opzione `pausa`; evita i doppi avvisi quando la diretta cade e riparte | nuova |
| ALR-034 | Frequenza dei controlli scelta dall'owner | Red (`streamset timer`) [RED] | 🟡 parziale: tempi fissi nel codice (90 secondi, 5 minuti) | Valori in `.env`, con minimo | nuova |
| ALR-035 | Avvisi quasi immediati | Pingcord ("da istantaneo a 2 minuti") [PINGCORD] | 🟡 parziale: Twitch 90 secondi, feed 5 minuti | Con un indirizzo HTTPS pubblico: EventSub di Twitch e WebSub di YouTube (spinta invece di controllo) | nuova |
| ALR-036 | Spegnere e riaccendere un avviso senza cancellarlo | YAGPDB [YAGPDB] | ❌ manca | Colonna `attivo`; `/admin alert pausa` | nuova |
| ALR-037 | Spostare un avviso in un altro canale | Carl-bot (`twitch move`) [CARL], YAGPDB [YAGPDB] | ❌ manca | `/admin alert sposta` | nuova |
| ALR-038 | Fermare tutti gli avvisi di un canale o del server | Red (`streamalert stop`) [RED], NadekoBot (`.streamsclear`) [NADEKO] | ❌ manca | `/admin alert rimuovi-tutti` con conferma | nuova |
| ALR-039 | Elenco che mostra anche chi è in diretta adesso | Carl-bot (`twitch list`, `twitch online`) [CARL] | 🟡 parziale: `/alerts list` senza stato | Colonna "in diretta ora" dall'ultima lettura | nuova |
| ALR-040 | Controllare a mano se un canale è in diretta | Red (`twitchstream`, `youtubestream`, `picarto`) [RED], NadekoBot (`.streamcheck`) [NADEKO], Lawliet (`twitch`, `youtube`) [LAWLIET] | ❌ manca | `/utility diretta <canale>` | nuova |
| ALR-041 | Tetto di avvisi per server, con piano a pagamento | Streamcord (5 gratis) [STREAMCORD], Carl-bot (Twitch 1 gratis e 5 premium; YouTube 5 e 20) [CARL], YAGPDB (Twitch 3 e 15; YouTube 10 e 250; RSS 2 e 10) [YAGPDB], Arcane (YouTube 2) [ARCANE] | ❌ manca: nessun tetto (LIM-16) | Tetto per server (es. 25 gratis) | M 11.8 |

## 4. Ruolo "in diretta"

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| ALR-042 | Ruolo dato ai membri mentre sono in diretta, tolto alla fine | Streamcord ("Live Role") [STREAMCORD], YAGPDB ("Currently Streaming Role") [YAGPDB], NadekoBot (`.streamrole`) [NADEKO] | ❌ manca | `/admin alert ruolo-live`; si basa sullo stato "in diretta" di Discord: serve l'intent delle presenze | NF-32 |
| ALR-043 | Ruolo "in diretta" solo per chi ha un certo ruolo | Streamcord (lista bianca) [STREAMCORD], YAGPDB ("Allowed Role") [YAGPDB], NadekoBot (ruolo di partenza) [NADEKO] | ❌ manca | Opzione `solo-ruolo` | NF-32 |
| ALR-044 | Membri o ruoli esclusi dal ruolo "in diretta" | Streamcord (lista nera, Pro) [STREAMCORD], YAGPDB ("Ignore Role") [YAGPDB], NadekoBot (`.streamroleblacklist`) [NADEKO] | ❌ manca | Elenco di esclusi | NF-32 |
| ALR-045 | Ruolo "in diretta" solo per certi giochi o parole nel titolo | YAGPDB [YAGPDB], NadekoBot (`.streamrolekeyword`) [NADEKO], Streamcord (Pro) [STREAMCORD] | ❌ manca | Stessi filtri di ALR-030 e ALR-031 | nuova |
| ALR-046 | Utenti che ricevono il ruolo anche senza la parola chiave | NadekoBot (`.streamrolewhitelist`) [NADEKO] | ❌ manca | Elenco di eccezioni | nuova |
| ALR-047 | Annuncio in un canale quando un membro del server va in diretta | Streamcord [STREAMCORD], YAGPDB ("Streaming Feed") [YAGPDB] | ❌ manca | Stesso evento del ruolo; pausa per membro | nuova |
| ALR-048 | Più configurazioni di ruolo "in diretta" nello stesso server | Streamcord (fino a 5, Pro) [STREAMCORD] | ❌ manca | Tabella con più regole | nuova |
| ALR-049 | Riconoscere affiliati e partner Twitch con i "ruoli collegati" di Discord | Streamcord [STREAMCORD] | ❌ manca | Linked Roles: l'utente collega il suo account Twitch (vedi E3 in `APP_UTENTE_E_DESKTOP.md`) | NF-36 |

## Fonti

Lette il 4 e 5/10/2026.

- `[STREAMCORD]` Streamcord — https://streamcord.io · https://top.gg/bot/375805687529209857
- `[PINGCORD]` Pingcord — https://pingcord.xyz · https://pingcord.xyz/premium
- `[YAGPDB]` YAGPDB — https://help.yagpdb.xyz/docs/notifications/youtube/ · `/twitch/` · `/streaming/` · `/reddit/` · `/rss/` (letti dal sorgente ufficiale https://github.com/botlabs-gg/yagpdb-docs-v2)
- `[CARL]` Carl-bot — https://docs.carl.gg/notifications.md
- `[RED]` Red-DiscordBot — https://docs.discord.red/en/stable/cog_guides/streams.html (letto dal sorgente https://github.com/Cog-Creators/Red-DiscordBot)
- `[NADEKO]` NadekoBot — https://nadeko.bot/commands e sorgente ufficiale https://github.com/Kwoth/NadekoBot
- `[ARCANE]` Arcane — https://docs.arcane.bot/plugins/youtube · https://docs.arcane.bot/premium
- `[LAWLIET]` Lawliet — sorgente ufficiale https://github.com/Aninoss/lawliet-bot (`configuration_en_us.properties`, voci `alerts_*`; `external_services_en_us.properties`)
- `[MEE6]` MEE6 — https://help.mee6.xyz/en/articles/710936-mee6-free-vs-premium-plans-comparison
- `[SAPPHIRE]` Sapphire — https://top.gg/bot/678344927997853742 (solo la scheda)

Non letti su fonte ufficiale:
- **FreeStuff** (giochi gratis): la lettura del sito non è stata
  permessa; la riga ALR-017 è segnata "non verificato".
- **Streamcord**: la documentazione `docs.streamcord.io` non è stata
  letta; le voci vengono dalla pagina principale e dalla scheda top.gg.
- **Pingcord**: la documentazione `docs.pingcord.xyz` non è stata letta.
- **MEE6**: solo l'elenco delle piattaforme nella tabella dei piani.

## Conteggio

49 righe: 36 ❌ e 13 🟡.
