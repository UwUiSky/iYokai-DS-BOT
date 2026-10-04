# Catalogo — Divertimento e immagini

Giochi di gruppo senza monete, comandi di testo, immagini e meme,
ricerche "da gioco", effetti sonori, telefono tra server, GIF di
reazione e di azione tra utenti. 139 voci. Bot letti: Yggdrasil, YAGPDB,
Carl-bot, Lawliet, NadekoBot, Red-DiscordBot, Dank Memer, Mimu.

Legenda: ❌ manca · 🟡 parziale. "Scheda": NF-xx = scheda di
`NUOVE_FUNZIONI.md`; M x.y = riga di `MODIFICHE_ESISTENTE.md`;
"nuova" = non c'è ancora in nessun piano.

iYokai oggi (per confronto): `/fun 8ball`, `coinflip`, `dice`, `rps`,
`joke`, `quote`, `fact`, `animal` (cane, gatto, volpe), `meme` (testo
sopra e sotto un'immagine), `grayscale`, `invert`, `blur`, `pixelate`,
`search-image` (Pixabay), `/ship`, `/rate`.

Note sul conteggio: i giochi con puntata in monete sono nel file 11.
Le GIF di reazione e di azione di Lawliet sono 55 comandi diversi: qui
hanno una riga ciascuna, corta, come chiesto. In iYokai sarebbero due
soli comandi (`/fun reazione` e `/fun azione`) con una scelta: con 25
scelte fisse per opzione serve l'autocompletamento. I 19 suoni di
Yggdrasil sono invece una riga sola (sono file audio, non funzioni).

Limite da ricordare: `/fun` avrà 20 figli su 25 dopo la fase F7. Le
funzioni nuove vanno dentro pochi sotto-comandi con una scelta
(`/fun gioca`, `/fun testo`, `/fun immagine`, `/fun azione`).

## 1. Giochi di gruppo e passatempi

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| FUN-001 | Quiz a domande con difficoltà a scelta | YAGPDB (`/trivia start`: facile, media, difficile) [YAGPDB], Red (`trivia`) [RED], NadekoBot (`.trivia`: 30 secondi a domanda, vince chi arriva a 10) [NADEKO] | ❌ manca | `/fun gioca quiz`; domande in italiano nel repository; bottoni A–D | NF-40 |
| FUN-002 | Classifica del quiz, del server e mondiale | YAGPDB (`/trivia rank`, `/trivia leaderboard`) [YAGPDB], Red (`trivia leaderboard server`, `global`) [RED], NadekoBot (`.tl`) [NADEKO] | ❌ manca | Scelta `tipo: quiz` in `/level leaderboard` | NF-40 |
| FUN-003 | Azzerare la classifica del quiz | YAGPDB (`/trivia resetleaderboard`) [YAGPDB] | ❌ manca | Comando admin con conferma | nuova |
| FUN-004 | Quiz a tema da elenchi pronti (giochi, anime, geografia, bandiere…) | Red (`trivia list`: oltre 50 elenchi) [RED] | ❌ manca | Categorie di domande; partire con 5–6 temi | NF-40 |
| FUN-005 | Elenchi di domande caricati dal server | Red (`triviaset custom upload`, `list`, `delete`) [RED] | ❌ manca | File YAML o JSON; `max_length` e controllo dei campi; tetto di domande | nuova |
| FUN-006 | Regole del quiz: punteggio per vincere, tempo per domanda, mostra la risposta, il bot gioca | Red (`triviaset maxscore`, `timelimit`, `revealanswer`, `botplays`, `stopafter`) [RED] | ❌ manca | Impostazioni del server per il quiz | nuova |
| FUN-007 | "Cards Against Humanity" in un canale, con pacchetti di carte | YAGPDB (`/cah create`, `/cah packs`, `/cah kick`, `/cah end`) [YAGPDB] | ❌ manca | Carte in italiano scritte da noi (quelle originali sono sotto licenza); mano in privato | nuova |
| FUN-008 | Variante a voto: i giocatori votano la carta migliore | YAGPDB (`/cah create -v`) [YAGPDB] | ❌ manca | Opzione del gioco sopra | nuova |
| FUN-009 | Campo minato fatto con gli spoiler | NadekoBot (`.minesweeper`) [NADEKO] | ❌ manca | Un solo messaggio; nessuno stato da salvare | nuova |
| FUN-010 | Gioco degli acronimi: tutti inventano una frase, poi si vota | NadekoBot (`.acrophobia`) [NADEKO] | ❌ manca | Modulo per la frase, bottoni per il voto | nuova |
| FUN-011 | Gara di battitura: chi ricopia più in fretta un testo | NadekoBot (`.typestart`, `.typestop`) [NADEKO] | ❌ manca | Testo come immagine (così non si copia e incolla); serve `message_content` | nuova |
| FUN-012 | Testi della gara di battitura aggiunti dal server | NadekoBot (`.typeadd`, `.typelist`, `.typedel`) [NADEKO] | ❌ manca | Elenco per server | nuova |
| FUN-013 | Tela di pixel del server: ognuno colora un pixel, pagando monete | NadekoBot (`.ncanvas`, `.nczoom`, `.ncsetpixel`, `.ncpixel`) [NADEKO] | ❌ manca | Immagine Pillow; pausa per utente | NF-40 |
| FUN-014 | Lo staff azzera la tela o toglie i pixel di un utente | NadekoBot (`.ncreset`, `.ncnuke`, `.ncsetimg`) [NADEKO] | ❌ manca | Comandi admin | nuova |
| FUN-015 | Gara giornaliera "chi tira il numero più alto", con classifica | Carl-bot (`games toproll`, `games leaderboard`) [CARL] | ❌ manca | Un tiro al giorno per utente | nuova |
| FUN-016 | Mazzo di carte del server: pesca fino a 10 carte, rimescola | NadekoBot (`.draw`, `.drawnew`, `.deckshuffle`) [NADEKO] | ❌ manca | Mazzo per canale in memoria | nuova |
| FUN-017 | Gara tra auto da collezione, con garage personale | Yggdrasil (`--race`, `--garage`) [YGG] | ❌ manca | Collezione di oggetti (NF-40) | NF-40 |
| FUN-018 | Gara di "fidget spinner" con classifica | Yggdrasil (`--spinner`, `--spinner scores`) [YGG] | ❌ manca | Durata casuale; classifica dei giri più lunghi | nuova |
| FUN-019 | Battaglia testuale a turni tra due utenti | Yggdrasil (`--deathbattle`) [YGG] | ❌ manca | Come il duello di ECO-104, senza monete | NF-40 |
| FUN-020 | "Punteggio di amicizia" tra due utenti | Yggdrasil (`--friendscore`) [YGG] | 🟡 parziale: c'è `/ship` | Variante di `/fun ship` con testi diversi | nuova |
| FUN-021 | "Smash or pass" su personaggi di anime, che cambiano ogni settimana | Lawliet (`smashorpass`) [LAWLIET] | ❌ manca | Tema delicato e immagini di terzi: bassa priorità | nuova |
| FUN-022 | "Quanto è probabile che sia…": percentuale scherzosa su un utente | Lawliet (`kira`) [LAWLIET] | 🟡 parziale: `/rate` dà un voto da 0 a 10 | È il "misuratore a tema libero" già previsto (`/fun misura`) | NF-40 |
| FUN-023 | Scegliere a caso tra più opzioni scritte dall'utente | Carl-bot (`pick`) [CARL], Red (`choose`) [RED], Yggdrasil (`--choose`) [YGG], NadekoBot (`.choose`) [NADEKO] | ❌ manca | `/fun scegli`; menzioni spente nella risposta | nuova |
| FUN-024 | Dadi in formato da gioco di ruolo (3d6+2) | YAGPDB (`/fun roll`) [YAGPDB], NadekoBot (`.roll`, `.rolluo`: fino a 30 dadi) [NADEKO] | 🟡 parziale: `/fun dice` tira un dado solo | Opzione `formula`; tetto di 30 dadi | nuova |
| FUN-025 | Numero casuale in un intervallo | Carl-bot (`roll`) [CARL], NadekoBot (`.nroll`) [NADEKO] | 🟡 parziale: `/fun dice [facce]` | Opzioni `da` e `a` | nuova |
| FUN-026 | Più monete lanciate insieme, con immagine | NadekoBot (`.flip`) [NADEKO] | 🟡 parziale: una moneta, solo testo | Opzione `quante` | nuova |
| FUN-027 | "Preferiresti…?" | YAGPDB (`/fun wouldyourather`) [YAGPDB], Mimu (esempio di autorisponditore) [MIMU] | ❌ manca | Domande in italiano; due bottoni con il conteggio | nuova |
| FUN-028 | Argomento di conversazione quando la chat è ferma | YAGPDB (`/fun topic`) [YAGPDB], Lawliet (`topic`) [LAWLIET] | ❌ manca | `/fun argomento`; elenco curato | nuova |
| FUN-029 | Consiglio a caso | YAGPDB (`/fun advice`) [YAGPDB] | ❌ manca | Elenco curato in italiano | nuova |
| FUN-030 | Frase motivazionale come immagine | YAGPDB (`/fun inspire`) [YAGPDB] | 🟡 parziale: `/fun quote` dà una citazione in testo | Citazione disegnata su uno sfondo | nuova |
| FUN-031 | Presa in giro scherzosa di un utente | YAGPDB (`/fun roast`) [YAGPDB], NadekoBot (`.yomama`) [NADEKO] | ❌ manca | Solo battute leggere; rispetta il blocco personale (FUN-137) | nuova |
| FUN-032 | "Lancia" un oggetto a caso a un utente | YAGPDB (`/fun throw`) [YAGPDB] | ❌ manca | Elenco di oggetti buffi | nuova |
| FUN-033 | Barzellette a tema (papà, Chuck Norris, videogiochi) | YAGPDB (`/fun dadjoke`) [YAGPDB], Lawliet (`dadjoke`) [LAWLIET], NadekoBot (`.chucknorris`, `.wowjoke`, `.randjoke`) [NADEKO] | 🟡 parziale: `/fun joke` senza categorie | Opzione `tema` | nuova |
| FUN-034 | Curiosità su gatti e cani | YAGPDB (`/fun catfact`, `/fun dogfact`) [YAGPDB], NadekoBot (`.catfact`) [NADEKO] | 🟡 parziale: `/fun fact` generico | Opzione `tema` | nuova |
| FUN-035 | Vignetta xkcd, a caso o per numero | YAGPDB (`/fun xkcd`) [YAGPDB], NadekoBot (`.xkcd`) [NADEKO] | ❌ manca | API pubblica di xkcd; contenuto in inglese | nuova |
| FUN-036 | Oggetto magico inventato, con descrizione | NadekoBot (`.magicitem`) [NADEKO] | ❌ manca | Elenco curato; adatto ai server di gioco di ruolo | nuova |
| FUN-037 | Link "cercalo su Google" da mandare a qualcuno | Red (`lmgtfy`) [RED], NadekoBot (`.lmgtfy`) [NADEKO] | ❌ manca | Solo un link costruito | nuova |

## 2. Testo

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| FUN-038 | Testo "largo" (caratteri a larghezza piena) | Carl-bot (`aesthetics`) [CARL] | ❌ manca | `/fun testo stile:largo`; risposta ≤ 2000 caratteri | nuova |
| FUN-039 | Testo in corsivo elegante | Carl-bot (`fancy`) [CARL] | ❌ manca | Stile di `/fun testo` | nuova |
| FUN-040 | Testo in corsivo grassetto | Carl-bot (`boldfancy`) [CARL] | ❌ manca | Stile di `/fun testo` | nuova |
| FUN-041 | Testo in gotico | Carl-bot (`fraktur`) [CARL] | ❌ manca | Stile di `/fun testo` | nuova |
| FUN-042 | Testo in gotico grassetto | Carl-bot (`boldfraktur`) [CARL] | ❌ manca | Stile di `/fun testo` | nuova |
| FUN-043 | Testo a doppio tratto | Carl-bot (`double`) [CARL] | ❌ manca | Stile di `/fun testo` | nuova |
| FUN-044 | Testo in maiuscoletto | Carl-bot (`smallcaps`) [CARL] | ❌ manca | Stile di `/fun testo` | nuova |
| FUN-045 | Testo scritto con le emoji delle lettere | Carl-bot (`emojify`) [CARL] | ❌ manca | Stile di `/fun testo`; attenzione ai 2000 caratteri | nuova |
| FUN-046 | Applauso tra una parola e l'altra | Carl-bot (`clap`) [CARL] | ❌ manca | Stile di `/fun testo` | nuova |
| FUN-047 | Parole separate da un carattere o emoji a scelta | Carl-bot (`space`) [CARL] | ❌ manca | Opzione `separatore` | nuova |
| FUN-048 | Testo in "owo" | Carl-bot (`owofy`) [CARL] | ❌ manca | Stile di `/fun testo` | nuova |

## 3. Immagini e meme

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| FUN-049 | Foto di uccelli | Yggdrasil (`--bird`) [YGG], NadekoBot (`.randombird`) [NADEKO] | 🟡 parziale: `/fun animal` ha cane, gatto, volpe | Aggiungere la specie; API gratuita; `defer()` (M 15.1) | nuova |
| FUN-050 | Foto di animali teneri a caso | Carl-bot (`aww`) [CARL] | 🟡 parziale: tre specie | Specie "a sorpresa" | nuova |
| FUN-051 | Cinque foto in un colpo | Carl-bot (`catbomb`, `dogbomb`, `awwbomb`) [CARL] | ❌ manca | Opzione `quante` (max 5); un solo messaggio con più immagini | nuova |
| FUN-052 | Foto di cibo a caso | NadekoBot (`.randomfood`) [NADEKO] | ❌ manca | Tipo in più di `/fun animal` (da rinominare `/fun foto`) | nuova |
| FUN-053 | Meme a caso da Internet | Yggdrasil (`--meme`) [YGG], Lawliet (`meme`) [LAWLIET], Dank Memer (`/meme`) [DANK] | 🟡 parziale: `/fun meme` crea un meme, non ne cerca | Fonte con contenuti controllati; mai fuori dai canali adatti | nuova |
| FUN-054 | Immagine "tenera" o di buonumore a caso | Lawliet (`wholesome`) [LAWLIET] | ❌ manca | Come FUN-053 | nuova |
| FUN-055 | Post di un subreddit a scelta | Lawliet (`reddit`) [LAWLIET], Red (`imgur subreddit`) [RED] | ❌ manca | Feed RSS di Reddit già usato dagli alert; subreddit NSFW solo nei canali NSFW | nuova |
| FUN-056 | Ricerca di GIF (una o a caso) | Red (`gif`, `gifr`) [RED] | ❌ manca | Serve una chiave (Giphy o Tenor); filtro contenuti al massimo | nuova |
| FUN-057 | Fusione di due Pokémon in un'immagine | Yggdrasil (`--pokefusion`) [YGG] | ❌ manca | Immagini di terzi: verificare i diritti prima | nuova |
| FUN-058 | Lapide "R.I.P." con il nome di un utente | Yggdrasil (`--rip`) [YGG] | ❌ manca | Modello Pillow | nuova |
| FUN-059 | Manifesto "Ricercato" con l'avatar | Yggdrasil (`--wanted`) [YGG] | ❌ manca | Modello Pillow | nuova |
| FUN-060 | Avatar con filtro arcobaleno | Lawliet (`rainbow`) [LAWLIET] | ❌ manca | Filtro in più accanto a `grayscale` e `invert` | nuova |
| FUN-061 | Avatar "triggered" (immagine che trema) | Lawliet (`trigger`) [LAWLIET] | ❌ manca | GIF animata con Pillow; attenzione al peso del file | nuova |
| FUN-062 | Immagine-reazione "qualcuno ha pingato tutti" | Lawliet (`everyone`) [LAWLIET] | ❌ manca | Immagine fissa | nuova |
| FUN-063 | Altri comandi-scherzo di Yggdrasil di cui il sito dà solo il nome | Yggdrasil (`--useless`, `--spoilers`, `--loading`, `--gold`, `--nitro`, `--icecream`, `--toast`) [YGG] (non verificato: effetto non descritto) | ❌ manca | Da decidere solo dopo averli visti dal vivo | nuova |
| FUN-064 | Molti generatori di immagini a partire dall'avatar o da un testo | Dank Memer ("image manipulation") [DANK] (non verificato: l'elenco dei singoli comandi non è leggibile) | 🟡 parziale: 4 filtri e il meme con testo | Aggiungere modelli uno alla volta, tutti con le regole di `core/safe_image.py` | nuova |
| FUN-065 | GIF a tema videogiochi, con l'emozione a scelta | Carl-bot (`games gif`, `league`, `leaguebomb`) [CARL] | ❌ manca | Come FUN-056 | nuova |

## 4. Schede e strumenti per i videogiochi

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| FUN-066 | Statistiche di un giocatore di Fortnite | Carl-bot (`fortnite`) [CARL] | ❌ manca | API con chiave; cache; `defer()` | nuova |
| FUN-067 | Statistiche di un giocatore di osu! | NadekoBot (`.osu`, `.osu5`, `.gatari`) [NADEKO], Lawliet (`osu`) [LAWLIET] | ❌ manca | API con chiave | nuova |
| FUN-068 | Scheda di un Pokémon e delle sue abilità | NadekoBot (`.pokemon`, `.pokemonability`) [NADEKO], Lawliet (`pokemon`) [LAWLIET] | ❌ manca | API pubblica (PokéAPI) | nuova |
| FUN-069 | Debolezze di un Pokémon o di un tipo | Lawliet (`weaknessmon`, `weaknesstype`) [LAWLIET] | ❌ manca | Tabella dei tipi nel codice | nuova |
| FUN-070 | Carte di Hearthstone e di Magic | NadekoBot (`.hearthstone`, `.magicthegathering`) [NADEKO] | ❌ manca | API pubbliche | nuova |
| FUN-071 | Orari e rotazioni di eventi di un gioco (World of Warcraft, Splatoon 2) | Carl-bot (`incursion`, `invasion`, `reset`) [CARL], Lawliet (`maps`, `salmon`, `splatnet`) [LAWLIET] | ❌ manca | Per iYokai avrebbe senso sul gioco della community (Marathon), se esiste una fonte pubblica | nuova |
| FUN-072 | Scelta a caso di classe o specializzazione di un gioco | Carl-bot (`pickmyclass`, `pickmyspec`) [CARL] | ❌ manca | Elenco per gioco, scelto dal server | nuova |
| FUN-073 | Scheda di un anime o di un manga | NadekoBot (`.anime`, `.manga`, `.anilist`) [NADEKO], Lawliet (`anilist`) [LAWLIET] | ❌ manca | API pubblica di AniList | nuova |

## 5. Effetti sonori e telefono tra server

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| FUN-074 | Suoni pronti da far partire in vocale | Yggdrasil (19 comandi: `--airhorn`, `--brainpower`, `--cena`, `--cheer`, `--cricket`, `--duel`, `--easy`, `--fakeerror`, `--fakeping`, `--knocking`, `--laurel`, `--leeroy`, `--myleg`, `--numberone`, `--oof`, `--tooslow`, `--trombone`, `--vsauce`, `--yanny`) [YGG] | ❌ manca | `/fun suono <nome>`; usa un bot musicale libero; suoni liberi da diritti | NF-35 |
| FUN-075 | Suoni caricati dal server (file o link diretto) | YAGPDB (50 gratis, 250 premium) [YAGPDB], Yggdrasil (`-soundadd`) (terzi) [YGG-T] | ❌ manca | `/admin musica suono aggiungi`; durata e peso massimi; tetto per server | NF-35 |
| FUN-076 | Ruoli che possono, o non possono, usare un certo suono | YAGPDB ("Allowed roles", "Disallowed roles") [YAGPDB] | ❌ manca | Due elenchi per suono | nuova |
| FUN-077 | Elenco dei suoni disponibili | YAGPDB (`/soundboard`) [YAGPDB] | ❌ manca | Autocompletamento (25 voci) | NF-35 |
| FUN-078 | Fermare il suono in corso | YAGPDB (`/soundboardreset`) [YAGPDB] | ❌ manca | `/fun suono ferma` | NF-35 |
| FUN-079 | "Telefono": due canali di server diversi si parlano tramite il bot | Yggdrasil (`--speakerphone`, `--userphone`) [YGG] | ❌ manca | Messaggi rimandati con webhook; filtro AutoMod su tutto; consenso dei due server; registro per gli abusi | nuova |
| FUN-080 | Varianti del telefono | Yggdrasil (`--eyephone`, `--flipphone`, `--scramblephone`, `--voicephone`, `--fuwwyphone`) [YGG] (non verificato: effetto non descritto) | ❌ manca | Da decidere dopo FUN-079 | nuova |

## 6. GIF di reazione e di azione tra utenti

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| FUN-081 | GIF di reazione: l'utente fa il "dab" | Lawliet (`dab`) [LAWLIET] | ❌ manca | `/fun reazione tipo:dab`; GIF da una raccolta con licenza chiara | nuova |
| FUN-082 | GIF di reazione: l'utente è in imbarazzo | Lawliet (`awkward`) [LAWLIET] | ❌ manca | `/fun reazione tipo:awkward`; GIF da una raccolta con licenza chiara | nuova |
| FUN-083 | GIF di reazione: l'utente dice di sì | Lawliet (`yes`) [LAWLIET] | ❌ manca | `/fun reazione tipo:yes`; GIF da una raccolta con licenza chiara | nuova |
| FUN-084 | GIF di reazione: l'utente dice di no | Lawliet (`no`) [LAWLIET] | ❌ manca | `/fun reazione tipo:no`; GIF da una raccolta con licenza chiara | nuova |
| FUN-085 | GIF di reazione: l'utente piange | Lawliet (`cry`) [LAWLIET] | ❌ manca | `/fun reazione tipo:cry`; GIF da una raccolta con licenza chiara | nuova |
| FUN-086 | GIF di reazione: l'utente balla | Lawliet (`dance`) [LAWLIET] | ❌ manca | `/fun reazione tipo:dance`; GIF da una raccolta con licenza chiara | nuova |
| FUN-087 | GIF di reazione: l'utente sorride | Lawliet (`smile`) [LAWLIET] | ❌ manca | `/fun reazione tipo:smile`; GIF da una raccolta con licenza chiara | nuova |
| FUN-088 | GIF di reazione: l'utente fa il compiaciuto | Lawliet (`smug`) [LAWLIET] | ❌ manca | `/fun reazione tipo:smug`; GIF da una raccolta con licenza chiara | nuova |
| FUN-089 | GIF di reazione: l'utente è arrabbiato | Lawliet (`angry`) [LAWLIET] | ❌ manca | `/fun reazione tipo:angry`; GIF da una raccolta con licenza chiara | nuova |
| FUN-090 | GIF di reazione: l'utente si mette la mano in faccia | Lawliet (`facepalm`) [LAWLIET] | ❌ manca | `/fun reazione tipo:facepalm`; GIF da una raccolta con licenza chiara | nuova |
| FUN-091 | GIF di reazione: l'utente scappa | Lawliet (`run`) [LAWLIET] | ❌ manca | `/fun reazione tipo:run`; GIF da una raccolta con licenza chiara | nuova |
| FUN-092 | GIF di reazione: l'utente arrossisce | Lawliet (`blush`) [LAWLIET] | ❌ manca | `/fun reazione tipo:blush`; GIF da una raccolta con licenza chiara | nuova |
| FUN-093 | GIF di reazione: l'utente sbadiglia | Lawliet (`yawn`) [LAWLIET] | ❌ manca | `/fun reazione tipo:yawn`; GIF da una raccolta con licenza chiara | nuova |
| FUN-094 | GIF di reazione: l'utente fissa | Lawliet (`stare`) [LAWLIET] | ❌ manca | `/fun reazione tipo:stare`; GIF da una raccolta con licenza chiara | nuova |
| FUN-095 | GIF di reazione: l'utente dorme | Lawliet (`sleep`) [LAWLIET] | ❌ manca | `/fun reazione tipo:sleep`; GIF da una raccolta con licenza chiara | nuova |
| FUN-096 | GIF di reazione: l'utente ride | Lawliet (`laugh`) [LAWLIET] | ❌ manca | `/fun reazione tipo:laugh`; GIF da una raccolta con licenza chiara | nuova |
| FUN-097 | GIF di reazione: l'utente perde sangue dal naso (stile anime) | Lawliet (`nosebleed`) [LAWLIET] | ❌ manca | `/fun reazione tipo:nosebleed`; GIF da una raccolta con licenza chiara | nuova |
| FUN-098 | GIF di reazione: l'utente fa spallucce | Lawliet (`shrug`) [LAWLIET] | ❌ manca | `/fun reazione tipo:shrug`; GIF da una raccolta con licenza chiara | nuova |
| FUN-099 | GIF di reazione: l'utente sorseggia una bevanda | Lawliet (`sip`) [LAWLIET] | ❌ manca | `/fun reazione tipo:sip`; GIF da una raccolta con licenza chiara | nuova |
| FUN-100 | GIF di reazione: l'utente si annoia | Lawliet (`bored`) [LAWLIET] | ❌ manca | `/fun reazione tipo:bored`; GIF da una raccolta con licenza chiara | nuova |
| FUN-101 | GIF di reazione: l'utente salta | Lawliet (`jump`) [LAWLIET] | ❌ manca | `/fun reazione tipo:jump`; GIF da una raccolta con licenza chiara | nuova |
| FUN-102 | GIF di reazione: l'utente mette il broncio | Lawliet (`pout`) [LAWLIET] | ❌ manca | `/fun reazione tipo:pout`; GIF da una raccolta con licenza chiara | nuova |
| FUN-103 | GIF di reazione: l'utente beve | Lawliet (`drink`) [LAWLIET] | ❌ manca | `/fun reazione tipo:drink`; GIF da una raccolta con licenza chiara | nuova |
| FUN-104 | GIF di reazione: l'utente canta | Lawliet (`sing`) [LAWLIET] | ❌ manca | `/fun reazione tipo:sing`; GIF da una raccolta con licenza chiara | nuova |
| FUN-105 | GIF di reazione: l'utente supplica | Lawliet (`beg`) [LAWLIET] | ❌ manca | `/fun reazione tipo:beg`; GIF da una raccolta con licenza chiara | nuova |
| FUN-106 | GIF di reazione: l'utente è nervoso | Lawliet (`nervous`) [LAWLIET] | ❌ manca | `/fun reazione tipo:nervous`; GIF da una raccolta con licenza chiara | nuova |
| FUN-107 | GIF di reazione: l'utente mangia | Lawliet (`nom`) [LAWLIET] | ❌ manca | `/fun reazione tipo:nom`; GIF da una raccolta con licenza chiara | nuova |
| FUN-108 | GIF di reazione: l'utente festeggia | Lawliet (`celebrate`) [LAWLIET] | ❌ manca | `/fun reazione tipo:celebrate`; GIF da una raccolta con licenza chiara | nuova |
| FUN-109 | GIF di reazione: l'utente dà dello sciocco ("baka") | Lawliet (`baka`) [LAWLIET] | ❌ manca | `/fun reazione tipo:baka`; GIF da una raccolta con licenza chiara | nuova |
| FUN-110 | GIF di azione verso un altro utente: abbraccia | Lawliet (`hug`) [LAWLIET] | ❌ manca | `/fun azione tipo:hug utente:…`; rispetta il blocco personale | nuova |
| FUN-111 | GIF di azione verso un altro utente: coccola | Lawliet (`cuddle`) [LAWLIET] | ❌ manca | `/fun azione tipo:cuddle utente:…`; rispetta il blocco personale | nuova |
| FUN-112 | GIF di azione verso un altro utente: fa una carezza sulla testa | Lawliet (`pat`) [LAWLIET] | ❌ manca | `/fun azione tipo:pat utente:…`; rispetta il blocco personale | nuova |
| FUN-113 | GIF di azione verso un altro utente: bacia | Lawliet (`kiss`) [LAWLIET] | ❌ manca | `/fun azione tipo:kiss utente:…`; rispetta il blocco personale | nuova |
| FUN-114 | GIF di azione verso un altro utente: dichiara affetto a | Lawliet (`love`) [LAWLIET] | ❌ manca | `/fun azione tipo:love utente:…`; rispetta il blocco personale | nuova |
| FUN-115 | GIF di azione verso un altro utente: sposa | Lawliet (`marry`) [LAWLIET] | ❌ manca | `/fun azione tipo:marry utente:…`; rispetta il blocco personale | nuova |
| FUN-116 | GIF di azione verso un altro utente: punzecchia | Lawliet (`poke`) [LAWLIET] | ❌ manca | `/fun azione tipo:poke utente:…`; rispetta il blocco personale | nuova |
| FUN-117 | GIF di azione verso un altro utente: fa il solletico a | Lawliet (`tickle`) [LAWLIET] | ❌ manca | `/fun azione tipo:tickle utente:…`; rispetta il blocco personale | nuova |
| FUN-118 | GIF di azione verso un altro utente: lecca | Lawliet (`lick`) [LAWLIET] | ❌ manca | `/fun azione tipo:lick utente:…`; rispetta il blocco personale | nuova |
| FUN-119 | GIF di azione verso un altro utente: morde | Lawliet (`bite`) [LAWLIET] | ❌ manca | `/fun azione tipo:bite utente:…`; rispetta il blocco personale | nuova |
| FUN-120 | GIF di azione verso un altro utente: mordicchia | Lawliet (`nibble`) [LAWLIET] | ❌ manca | `/fun azione tipo:nibble utente:…`; rispetta il blocco personale | nuova |
| FUN-121 | GIF di azione verso un altro utente: schiaffeggia | Lawliet (`slap`) [LAWLIET] | ❌ manca | `/fun azione tipo:slap utente:…`; rispetta il blocco personale | nuova |
| FUN-122 | GIF di azione verso un altro utente: dà un pugno a | Lawliet (`punch`) [LAWLIET] | ❌ manca | `/fun azione tipo:punch utente:…`; rispetta il blocco personale | nuova |
| FUN-123 | GIF di azione verso un altro utente: lancia qualcosa a | Lawliet (`throw`) [LAWLIET] | ❌ manca | `/fun azione tipo:throw utente:…`; rispetta il blocco personale | nuova |
| FUN-124 | GIF di azione verso un altro utente: lancia via | Lawliet (`yeet`) [LAWLIET] | ❌ manca | `/fun azione tipo:yeet utente:…`; rispetta il blocco personale | nuova |
| FUN-125 | GIF di azione verso un altro utente: dà il cinque a | Lawliet (`highfive`) [LAWLIET] | ❌ manca | `/fun azione tipo:highfive utente:…`; rispetta il blocco personale | nuova |
| FUN-126 | GIF di azione verso un altro utente: saluta con la mano | Lawliet (`wave`) [LAWLIET] | ❌ manca | `/fun azione tipo:wave utente:…`; rispetta il blocco personale | nuova |
| FUN-127 | GIF di azione verso un altro utente: premia con una fragola | Lawliet (`reward`) [LAWLIET] | ❌ manca | `/fun azione tipo:reward utente:…`; rispetta il blocco personale | nuova |
| FUN-128 | GIF di azione verso un altro utente: regala delle rose a | Lawliet (`roses`) [LAWLIET] | ❌ manca | `/fun azione tipo:roses utente:…`; rispetta il blocco personale | nuova |
| FUN-129 | GIF di azione verso un altro utente: dà un colpetto in testa a ("bonk") | Lawliet (`bonk`) [LAWLIET] | ❌ manca | `/fun azione tipo:bonk utente:…`; rispetta il blocco personale | nuova |
| FUN-130 | GIF di azione verso un altro utente: strizza le guance a | Lawliet (`squish`) [LAWLIET] | ❌ manca | `/fun azione tipo:squish utente:…`; rispetta il blocco personale | nuova |
| FUN-131 | GIF di azione verso un altro utente: si siede in braccio a | Lawliet (`lapsit`) [LAWLIET] | ❌ manca | `/fun azione tipo:lapsit utente:…`; rispetta il blocco personale | nuova |
| FUN-132 | GIF di azione verso un altro utente: arresta | Lawliet (`arrest`) [LAWLIET] | ❌ manca | `/fun azione tipo:arrest utente:…`; rispetta il blocco personale | nuova |
| FUN-133 | GIF di azione verso un altro utente: fa un massaggio a | Lawliet (`massage`) [LAWLIET] | ❌ manca | `/fun azione tipo:massage utente:…`; rispetta il blocco personale | nuova |
| FUN-134 | GIF di azione verso un altro utente: ruba a | Lawliet (`steal`) [LAWLIET] | ❌ manca | `/fun azione tipo:steal utente:…`; rispetta il blocco personale | nuova |
| FUN-135 | GIF di azione verso un altro utente: fa il gesto del rombo ("Merkel") a | Lawliet (`merkel`) [LAWLIET] | ❌ manca | `/fun azione tipo:merkel utente:…`; rispetta il blocco personale | nuova |
| FUN-136 | Azioni create dal server (nome, testo e GIF propri) | Lawliet (`customrp`) [LAWLIET], Mimu (esempi di autorisponditore `.poke`, "embed action") [MIMU] | ❌ manca | Tag (NF-09) con immagine a caso da un elenco | NF-09 |
| FUN-137 | Bloccare chi può usare le azioni su di te | Lawliet (`rpblock`) [LAWLIET] | ❌ manca | Elenco personale; controllato da ogni comando che prende di mira un utente | nuova |
| FUN-138 | Scegliere il genere dei personaggi nelle GIF | Lawliet (`rpgender`) [LAWLIET] | ❌ manca | Preferenza personale facoltativa; non è un dato da chiedere: meglio GIF neutre | nuova |
| FUN-139 | Spegnere le azioni tra utenti in un server | Lawliet (gestione dei comandi per categoria, `cman`) [LAWLIET] | ❌ manca | Interruttore del modulo in `/admin setup` | nuova |

## Fonti

Lette il 5/10/2026.

- `[YGG]` Yggdrasil — https://ygg.fun (il sito avvisa che il bot è "in riscrittura": alcune funzioni possono non essere attive)
- `[YGG-T]` Yggdrasil (terzi) — https://thelinuxcode.com/use-yggdrasil-discord-bot/ (dicembre 2023)
- `[YAGPDB]` YAGPDB — https://help.yagpdb.xyz/docs/core/all-commands/ · https://help.yagpdb.xyz/docs/fun/soundboard/ · https://help.yagpdb.xyz/docs/welcome/premium/ (letti dal sorgente ufficiale https://github.com/botlabs-gg/yagpdb-docs-v2)
- `[CARL]` Carl-bot — https://docs.carl.gg/fun.md · https://docs.carl.gg/games.md
- `[LAWLIET]` Lawliet — sorgente ufficiale https://github.com/Aninoss/lawliet-bot (`interactions_`, `gimmicks_`, `external_services_`, `splatoon_2_`, `configuration_en_us.properties`)
- `[NADEKO]` NadekoBot — https://nadeko.bot/commands e sorgente ufficiale https://github.com/Kwoth/NadekoBot
- `[RED]` Red-DiscordBot — https://docs.discord.red/en/stable/cog_guides/general.html · `/trivia.html` · `/image.html` · `/audio.html` (letti dal sorgente https://github.com/Cog-Creators/Red-DiscordBot)
- `[DANK]` Dank Memer — https://dankmemer.lol/blogs/rewrite-changelog · https://top.gg/bot/270904126974590976
- `[MIMU]` Mimu — https://docs.mimu.bot/llms.txt

Non letti su fonte ufficiale:
- **Yggdrasil**: la pagina `ygg.fun/commands` dà errore 404. I comandi
  in tabella sono quelli nominati sulla pagina principale; di alcuni il
  sito dà solo il nome (righe segnate "non verificato").
- **Dank Memer**: l'elenco dei comandi di immagini non è leggibile
  (pagina che si carica solo con JavaScript).
- **UnbelievaBoat** (categoria "Fun", 9 comandi) e **Dyno**: nomi non
  leggibili, nessuna riga.
- Le varianti "yaoi" e "yuri" e le categorie NSFW di Lawliet non sono in
  tabella: riguardano l'istanza NSFW (NF-23).

## Conteggio

139 righe: 127 ❌ e 12 🟡.
