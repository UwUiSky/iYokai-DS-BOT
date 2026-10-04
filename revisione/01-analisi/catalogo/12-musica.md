# Catalogo — Musica

Sorgenti, ricerca, coda, impostazioni del player, playlist, flotta di
bot. 90 voci. Bot letti: Red-DiscordBot (cog Audio), FredBoat,
JMusicBot, NadekoBot, Jockie Music, Hydra, Rythm.

Legenda: ❌ manca · 🟡 parziale. "Scheda": NF-xx = scheda di
`NUOVE_FUNZIONI.md`; M x.y = riga di `MODIFICHE_ESISTENTE.md`;
"nuova" = non c'è ancora in nessun piano; **"scelta dell'owner: no"**
= funzione scartata dall'owner in modo definitivo (SPEC §9.4, §9.6,
§9.7, §9.8): è in elenco solo per completezza e **non va proposta**.

iYokai oggi (per confronto): `/play` (titolo, link, playlist fino a 750
brani), `/skip`, `/stop`, `/pause`, `/resume`, `/queue`,
`/clear-queue`, `/shuffle` (una volta), `/loop track|queue`,
`/nowplaying` con barra, `/volume set|up|down` (0–200), `/disconnect`,
`/nonstop`, radio condivisa dell'owner (`/nonstop-main …`). Sorgenti:
YouTube (ricerca di default), SoundCloud, link diretti, Spotify solo se
il nodo Lavalink ha il plugin, file locali solo per la radio.

**YouTube e condizioni d'uso.** YouTube ha fatto chiudere Groovy e
Rythm nel 2021. Jockie non elenca YouTube tra le sue sorgenti; Hydra
oggi non parla più di musica sul suo sito. Dove una voce dipende da
YouTube è scritto nella colonna "Come farla". Regola già scritta in
`CONFRONTO_BOT.md` §7.3: mai vendere funzioni musicali legate a YouTube.

## 1. Sorgenti e ricerca

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| MUS-001 | Link di Deezer | Jockie [JOCKIE] | ❌ manca | Plugin LavaSrc sul nodo proprio (M 8.9); servono le credenziali del servizio | nuova |
| MUS-002 | Link di Tidal | Jockie [JOCKIE] | ❌ manca | Come MUS-001 | nuova |
| MUS-003 | Link di Apple Music | Jockie [JOCKIE] | ❌ manca | Come MUS-001 | nuova |
| MUS-004 | Link di Spotify sempre funzionanti | Jockie [JOCKIE], Red (`audioset spotifyapi`) [RED] | 🟡 parziale: solo se il nodo ha il plugin; `spotify:` oggi diventa una ricerca YouTube (LIM-43) | Nodo proprio con LavaSrc; attenzione: LavaSrc cerca l'audio su un'altra sorgente, da scegliere diversa da YouTube | M 8.4 |
| MUS-005 | Link di Bandcamp | Jockie [JOCKIE], Red (`llset config source bandcamp`) [RED] | ❌ manca | Sorgente nativa di Lavalink: basta accenderla sul nodo | nuova |
| MUS-006 | Link di Vimeo | Jockie [JOCKIE], Red [RED] | ❌ manca | Come MUS-005 | nuova |
| MUS-007 | Link di Mixcloud | Jockie [JOCKIE] | ❌ manca | Serve un plugin del nodo | nuova |
| MUS-008 | Audio di una diretta Twitch | Red (`llset config source twitch`) [RED] | ❌ manca | Sorgente nativa di Lavalink | nuova |
| MUS-009 | File audio allegato a un messaggio Discord | Jockie [JOCKIE] | ❌ manca | Opzione `file` in `/music play`; è un link diretto: controllare tipo e dimensione | nuova |
| MUS-010 | Ricerca e ascolto di radio dal mondo | Jockie (oltre 37.000 stazioni) [JOCKIE], NadekoBot (`.radio`, da link) [NADEKO] | 🟡 parziale: solo la radio dell'owner; un link di radio funziona con `/play` | `/music radio <nome>` con un elenco pubblico di stazioni; nessun problema di YouTube | nuova |
| MUS-011 | Accendere e spegnere ogni sorgente | Red (`llset config source …`: youtube, soundcloud, bandcamp, twitch, vimeo, http, local) [RED] | ❌ manca | `/owner radio sorgenti`; serve per spegnere YouTube in un colpo se arriva una diffida | nuova |
| MUS-012 | Scegliere su quale servizio cercare un titolo | JMusicBot (`scsearch` per SoundCloud) [JMB] | ❌ manca: un titolo viene sempre cercato su YouTube Music | Opzione `sorgente` in `/music play` e valore predefinito del server; permette un default diverso da YouTube | nuova |
| MUS-013 | Ricerca con elenco di risultati tra cui scegliere | Red (`search`) [RED], FredBoat (`select`) [FRED], JMusicBot (`search`) [JMB], NadekoBot (`.queuesearch`) [NADEKO] | ❌ manca | — | scelta dell'owner: no |
| MUS-014 | Scegliere una playlist per genere da un elenco di categorie | Red (`genre`, da Spotify) [RED] | ❌ manca | Menu a tendina con playlist scelte dall'owner | nuova |
| MUS-015 | Paese usato per le ricerche Spotify, per server e per utente | Red (`audioset countrycode`, `mycountrycode`) [RED] | ❌ manca | Impostazione del server (default IT) | nuova |
| MUS-016 | Preferire le versioni "solo audio" ai video musicali | Red (`audioset lyrics`) [RED] | ❌ manca | Filtro sul titolo del risultato; riguarda solo le ricerche YouTube | nuova |
| MUS-017 | Dividere un video lungo nei brani elencati nella descrizione | FredBoat (`playsplit`) [FRED] | ❌ manca | Dipende da YouTube: sconsigliata | nuova |
| MUS-018 | Riprodurre una cartella di file locali o cercare tra i file | Red (`local folder`, `local play`, `local search`) [RED], NadekoBot (`.local`, `.localplaylist`) [NADEKO] | 🟡 parziale: file locali solo nella radio (e oggi non trovati, BUG-10) | Dopo M 8.4: `/owner radio cartella` | M 8.4 |
| MUS-019 | Gioco "indovina la canzone" | Jockie [JOCKIE] | ❌ manca | `/fun gioca canzone`; brevi estratti dei brani dell'owner | nuova |

## 2. Coda e riproduzione

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| MUS-020 | Entrare nel canale vocale senza far partire niente | Red (`summon`) [RED], FredBoat (`join`) [FRED], NadekoBot (`.join`) [NADEKO] | ❌ manca | `/music entra`; assegna un bot libero della flotta | nuova |
| MUS-021 | Mettere un brano nuovo in cima alla coda | FredBoat (`playnext`) [FRED], JMusicBot (`playnext`) [JMB], NadekoBot (`.queuenext`) [NADEKO] | ❌ manca | Opzione `prossimo: sì` in `/music play`. Non è tra gli scartati, ma è vicino a "move": chiedere all'owner | nuova |
| MUS-022 | Portare in cima un brano già in coda | Red (`bump`) [RED] | ❌ manca | — (è uno spostamento) | scelta dell'owner: no |
| MUS-023 | Far partire subito un brano, interrompendo quello in corso | Red (`bumpplay`) [RED] | ❌ manca | — (è un "forceskip") | scelta dell'owner: no |
| MUS-024 | Togliere un brano dalla coda | Red (`remove`) [RED], JMusicBot (`remove`) [JMB], NadekoBot (`.songremove`) [NADEKO] | ❌ manca | — | scelta dell'owner: no |
| MUS-025 | Togliere l'ultimo brano che hai messo per sbaglio | NadekoBot (`.wrongsong`) [NADEKO] | ❌ manca | — (variante di "remove") | scelta dell'owner: no |
| MUS-026 | Togliere dalla coda tutti i propri brani | Red (`queue cleanself`) [RED] | ❌ manca | — (variante di "remove") | scelta dell'owner: no |
| MUS-027 | Togliere i brani di chi non è più nel canale vocale | Red (`queue clean`) [RED], JMusicBot (`forceremove`) [JMB] | ❌ manca | Come pulizia automatica quando un utente esce; chiedere all'owner (vicino a "remove") | nuova |
| MUS-028 | Spostare un brano in un'altra posizione | JMusicBot (`movetrack`) [JMB], NadekoBot (`.trackmove`) [NADEKO] | ❌ manca | — | scelta dell'owner: no |
| MUS-029 | Saltare direttamente al brano numero N | Red (`skip <n>`) [RED], JMusicBot (`skipto`) [JMB], FredBoat [FRED] | ❌ manca | Opzione `a` in `/music skip` | nuova |
| MUS-030 | Saltare un intervallo di brani o tutti i brani di un utente | FredBoat (`skip n-m`, `skip @utente`) [FRED] | ❌ manca | Opzioni di `/music skip`; solo per chi gestisce il server | nuova |
| MUS-031 | Tornare al brano precedente | Red (`prev`) [RED] | ❌ manca | `/music precedente`; tenere gli ultimi brani in memoria | nuova |
| MUS-032 | Elenco dei brani già suonati | FredBoat (`history`) [FRED] | ❌ manca | Scheda "già suonati" in `/music queue` | nuova |
| MUS-033 | Ricominciare il brano da capo | FredBoat (`restart`) [FRED] | ❌ manca | — (è un "seek" a zero) | scelta dell'owner: no |
| MUS-034 | Andare a un punto del brano, avanti o indietro | Red (`seek`) [RED], FredBoat (`seek`, `forward`, `rewind`) [FRED], JMusicBot (`seek`) [JMB] | ❌ manca | — | scelta dell'owner: no |
| MUS-035 | Cercare un brano dentro la coda | Red (`queue search`) [RED], NadekoBot (`.queuefind`) [NADEKO] | ❌ manca | Opzione `cerca` in `/music queue` | nuova |
| MUS-036 | Vedere quanta parte della coda ha messo ogni utente | Red (`percent`) [RED] | ❌ manca | Riga in fondo a `/music queue` | nuova |
| MUS-037 | Coda "equa": i brani di utenti diversi si alternano | NadekoBot (`.qfp`) [NADEKO], JMusicBot (`queuetype`) [JMB] | ❌ manca | Impostazione del server `coda: normale/equa` | nuova |
| MUS-038 | Mescola come modalità che resta accesa | Red (`shuffle`) [RED], FredBoat (`shuffle`, `reshuffle`) [FRED] | 🟡 parziale: `/shuffle` mescola una volta | Opzione `resta: sì/no` | nuova |
| MUS-039 | Mescolare solo i propri brani | JMusicBot (`shuffle`) [JMB] | ❌ manca | Opzione `solo-miei` | nuova |
| MUS-040 | Continuare da soli con brani simili quando la coda finisce | Red (`autoplay`, `audioset autoplay toggle`) [RED], NadekoBot (`.queueautoplay`) [NADEKO] | ❌ manca | Solo da una playlist scelta (MUS-041): i "simili" di YouTube dipendono da YouTube | nuova |
| MUS-041 | Playlist che parte da sola quando la coda è vuota | Red (`audioset autoplay playlist`) [RED], JMusicBot (`autoplaylist`, `setdefault`) [JMB] | 🟡 parziale: `/nonstop` ripete la coda attuale | Impostazione `playlist-di-riserva`; dipende da NF-19 | NF-19 |
| MUS-042 | Coda che si ritrova dopo un riavvio del bot | Red (`audioset persistqueue`) [RED] | ❌ manca | Salvare la coda nel database a ogni cambio | nuova |
| MUS-043 | Esportare la coda come link o file | FredBoat (`export`) [FRED] | ❌ manca | File di testo allegato (sotto 10 MiB) | nuova |
| MUS-044 | Durata massima di un brano accettato | Red (`audioset maxlength`) [RED] | ❌ manca | Impostazione in secondi | nuova |
| MUS-045 | Playlist automatica "tutto quello che è stato suonato oggi" | Red (`audioset dailyqueue`) [RED] | ❌ manca | Dipende da NF-19 | nuova |
| MUS-046 | Testo della canzone | NadekoBot (`.lyrics`) [NADEKO], JMusicBot (`lyrics`) [JMB] | ❌ manca | — | scelta dell'owner: no |

## 3. Impostazioni del player

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| MUS-047 | Volume massimo scelto dal server | Red (`audioset maxvolume`) [RED] | 🟡 parziale: tetto fisso a 200 | Impostazione in `/admin musica` | nuova |
| MUS-048 | Qualità audio predefinita | NadekoBot (`.musicquality`) [NADEKO] | ❌ manca | Con Lavalink si regola sul nodo, non per server: bassa priorità | nuova |
| MUS-049 | Equalizzatore a bande con preset salvati | Red (`eq set`, `save`, `load`, `list`, `delete`, `reset`) [RED] | ❌ manca | — | scelta dell'owner: no |
| MUS-050 | Filtri audio (bassboost, nightcore, 8D…) | Maki [MAKI] | ❌ manca | — | scelta dell'owner: no |
| MUS-051 | Ruolo DJ e modalità DJ | Red (`audioset dj`, `audioset role`) [RED], JMusicBot (`setdj`) [JMB] | ❌ manca | — | scelta dell'owner: no |
| MUS-052 | Voto per saltare, con percentuale | Red (`audioset vote`) [RED], JMusicBot (`setskip`) [JMB] | ❌ manca | — | scelta dell'owner: no |
| MUS-053 | Pausa automatica quando il canale resta vuoto | Red (`audioset emptypause`) [RED] | ❌ manca | Evento `on_voice_state_update`; riprende al rientro | nuova |
| MUS-054 | Tempo di attesa prima di uscire da un canale vuoto, scelto dal server | Red (`audioset emptydisconnect`) [RED], NadekoBot (`.autodisconnect`) [NADEKO] | 🟡 parziale: 300 secondi fissi | Impostazione (da 30 a 3600 secondi) | nuova |
| MUS-055 | Scelta: uscire o restare quando la coda finisce | Red (`audioset dc`) [RED] | ❌ manca | Impostazione sì/no | nuova |
| MUS-056 | Il bot entra "sordo" in vocale | Red (`audioset autodeafen`) [RED] | ❌ manca | `self_deaf=True` alla connessione | nuova |
| MUS-057 | Spegnere gli annunci "ora in riproduzione" | Red (`audioset notify`) [RED] | ❌ manca | Impostazione sì/no | nuova |
| MUS-058 | Canale fisso dove arrivano gli annunci della musica | NadekoBot (`.setmusicchannel`, `.unsetmusicchannel`) [NADEKO], JMusicBot (`settc`) [JMB] | ❌ manca | Canale dal router (NF-01); coincide con il canale richieste | NF-19 |
| MUS-059 | Musica permessa in un solo canale vocale | JMusicBot (`setvc`) [JMB] | ❌ manca | Elenco di canali vocali ammessi | nuova |
| MUS-060 | Copertina del brano nei messaggi | Red (`audioset thumbnail`) [RED] | ❌ manca | Miniatura nell'embed di `/music nowplaying` | NF-19 |
| MUS-061 | Titolo del brano come stato del bot | Red (`audioset status`) [RED] | ❌ manca | Solo sui bot musicali della flotta (uno per canale); non sul bot principale, che è in molti server | nuova |
| MUS-062 | Parole vietate o permesse nei titoli dei brani | Red (`audioset restrictions blacklist`, `whitelist`: `add`, `delete`, `list`, `clear`) [RED] | ❌ manca | Due elenchi per server (max 50 voci) | nuova |
| MUS-063 | Elenchi di parole vietate validi per tutto il bot | Red (`audioset restrictions global …`) [RED] | ❌ manca | `/owner radio blocca-parola` | nuova |
| MUS-064 | Solo link di siti conosciuti | Red (`audioset restrict`) [RED] | ❌ manca: i controlli di `core/safe_http.py` valgono solo per i feed | Lista di domini ammessi anche per `/music play` | nuova |
| MUS-065 | "Jukebox": mettere un brano in coda costa monete | Red (`audioset jukebox`) [RED] | ❌ manca | Impostazione `prezzo`; addebito nella stessa transazione; i proventi alla cassa del server | nuova |
| MUS-066 | Riepilogo di tutte le impostazioni musicali | Red (`audioset settings`) [RED], JMusicBot (`settings`) [JMB] | ❌ manca | `/admin musica stato` | nuova |
| MUS-067 | Statistiche: in quanti server il bot sta suonando | Red (`audiostats`) [RED] | ❌ manca: `/owner stats` non mostra i player attivi | Riga in più in `/owner system` | nuova |
| MUS-068 | Riavviare il collegamento a Lavalink da comando | Red (`audioset restart`) [RED] | ❌ manca | `/owner radio riconnetti`; dopo M 8.2 | nuova |
| MUS-069 | Ricevere in DM il log del server Lavalink | Red (`audioset logs`) [RED] | ❌ manca | Solo per il nodo locale; file sotto 10 MiB | nuova |
| MUS-070 | Vedere le impostazioni di collegamento ai nodi | Red (`llset info`) [RED] | ❌ manca | `/owner radio nodi` (senza password) | nuova |

## 4. Playlist salvate

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| MUS-071 | Salvare la coda attuale come playlist | Red (`playlist queue`) [RED], NadekoBot (`.playlistsave`) [NADEKO] | ❌ manca | `/music playlist salva`; tetto di brani per playlist | NF-19 |
| MUS-072 | Salvare una playlist partendo da un link | Red (`playlist save`) [RED] | ❌ manca | Opzione `link` del comando sopra | NF-19 |
| MUS-073 | Creare una playlist vuota | Red (`playlist create`) [RED], JMusicBot (`playlist make`) [JMB] | ❌ manca | `/music playlist crea` | NF-19 |
| MUS-074 | Aggiungere un brano a una playlist | Red (`playlist append`) [RED], JMusicBot (`playlist append`) [JMB] | ❌ manca | `/music playlist aggiungi` | NF-19 |
| MUS-075 | Togliere un brano da una playlist | Red (`playlist remove`) [RED] | ❌ manca | `/music playlist togli` | NF-19 |
| MUS-076 | Togliere i doppioni da una playlist | Red (`playlist dedupe`) [RED] | ❌ manca | Fatto da solo al salvataggio | NF-19 |
| MUS-077 | Rinominare una playlist | Red (`playlist rename`) [RED] | ❌ manca | Nome ≤ 50 caratteri | NF-19 |
| MUS-078 | Caricare una playlist nella coda | Red (`playlist start`) [RED], NadekoBot (`.playlistload`) [NADEKO], JMusicBot (`playlist`) [JMB] | ❌ manca | `/music playlist carica` | NF-19 |
| MUS-079 | Elenco delle playlist e dettaglio dei brani | Red (`playlist list`, `playlist info`) [RED], NadekoBot (`.playlists`, `.playlistshow`) [NADEKO] | ❌ manca | `/music playlist elenco`, a pagine | NF-19 |
| MUS-080 | Cancellare una playlist | Red (`playlist delete`) [RED], NadekoBot (`.playlistdelete`) [NADEKO] | ❌ manca | `/music playlist elimina` | NF-19 |
| MUS-081 | Playlist del server, oltre a quelle personali | Red (ambiti utente, server, globale; `playlist copy`) [RED] | ❌ manca | Colonna `ambito`; quelle del server le gestisce l'admin | NF-19 |
| MUS-082 | Scaricare una playlist come file e ricaricarla | Red (`playlist download`, `playlist upload`) [RED] | ❌ manca | File JSON; `max_length` e controllo dei campi all'import | nuova |
| MUS-083 | Aggiornare una playlist dal suo link di origine | Red (`playlist update`) [RED] | ❌ manca | Rilettura del link salvato | nuova |
| MUS-084 | Codice per condividere una playlist con altri | Jockie [JOCKIE] | ❌ manca | Codice breve casuale; chi lo usa ne riceve una copia | NF-19 |
| MUS-085 | Preferiti: salvare il brano in ascolto con un clic | Jockie ("custom favorites") [JOCKIE] | ❌ manca | Bottone ❤ sul messaggio del player | NF-19 |
| MUS-086 | Playlist a più mani | Rythm ("collaborative playlists") [RYTHM] | ❌ manca | Elenco di utenti che possono modificare | nuova |
| MUS-087 | Cancellare tutte le playlist in un colpo | NadekoBot (`.deleteplaylists`) [NADEKO] | ❌ manca | Parte di `/utility privacy cancella` | NF-04 |

## 5. Flotta e canale richieste

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| MUS-088 | Più bot musicali nello stesso server, uno per canale vocale | Jockie (4 gratis, altri con il premium) [JOCKIE] | 🟡 parziale: 5 bot, ma oggi uno per server e quasi certamente senza audio (LIM-40) | D10: un nodo per bot, un bot per canale | M 8.1 |
| MUS-089 | Canale richieste con messaggio "player" e bottoni | Hydra (storico, 2023) (terzi) [HYDRA-T] | ❌ manca | Vista persistente; 5 bottoni per riga; aggiornamento ogni pochi secondi | NF-19 |
| MUS-090 | Bot musicali di colore diverso, a scelta | Jockie [JOCKIE] | 🟡 parziale: i 5 bot esistono, senza scelta | Solo estetica: nome e avatar dei worker | nuova |

## Fonti

Lette il 4/10/2026.

- `[RED]` Red-DiscordBot — https://docs.discord.red/en/stable/cog_guides/audio.html (letto dal sorgente https://github.com/Cog-Creators/Red-DiscordBot, `docs/cog_guides/audio.rst`)
- `[FRED]` FredBoat — sorgente ufficiale https://github.com/freyacodes/FredBoat (`FredBoat/src/main/resources/lang/en_US.properties`)
- `[JMB]` JMusicBot — sorgente ufficiale https://github.com/jagrosh/MusicBot
- `[NADEKO]` NadekoBot — https://nadeko.bot/commands
- `[JOCKIE]` Jockie Music — https://www.jockiemusic.com · https://top.gg/bot/411916947773587456
- `[HYDRA-T]` Hydra (terzi) — https://maketecheasier.com/add-hydra-bot-discord-server/ (già in `CONFRONTO_BOT.md`); il sito ufficiale https://hydra.bot e https://hydra.bot/premium oggi non parlano di musica
- `[RYTHM]` Rythm — https://rythm.fm
- `[MAKI]` Maki — dato già in `CONFRONTO_BOT.md` §3.9

Non letti su fonte ufficiale:
- **Jockie Music**: la pagina dei comandi (`jockiemusic.com/commands`,
  "150+ comandi") e la FAQ si caricano solo con JavaScript. Le voci di
  Jockie vengono dalla pagina principale e dalla scheda top.gg. I suoi
  singoli comandi (effetti, coda, raccolte) **non sono in tabella**.
- **Hydra**: `hydra.bot/commands` dà errore 404; nessuna funzione
  musicale è descritta sul sito ufficiale.
- **Rythm**: solo le poche righe della pagina principale; se la musica
  sia in licenza non è scritto.
- **Maki**: pagina dei comandi non leggibile.

## Conteggio

90 righe: 81 ❌ e 9 🟡.
