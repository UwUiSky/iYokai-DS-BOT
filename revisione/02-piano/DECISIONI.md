# DECISIONI.md — Le scelte già fatte

Qui stanno le decisioni che guidano il lavoro. Chi scrive codice **non
deve chiedere di nuovo**: legge qui e procede.

- D1–D11: **prese il 04/10/2026 su delega dell'owner; l'owner può
  cambiarle.** Sono state riportate dal coordinatore della sessione di
  lavoro del 04/10.
- D12–D14: **proposte da questa revisione** per non lasciare voci in
  attesa. Sono l'opzione consigliata. L'owner va avvisato e può
  cambiarle.
- D8 (seconda versione), D15, D16, D17: **indicate dall'owner** la sera
  del 04/10/2026.
- D19, D20, D21, D22, D23, D24: **indicate dall'owner** il 05/10/2026.

Regola per il futuro: se serve una decisione nuova, si sceglie
l'opzione consigliata, la si scrive qui con la data, e si avvisa
l'owner.

| # | Tema | Decisione | Dove si applica |
|---|---|---|---|
| D1 | Nomi dei comandi | Opzione A: nome base inglese, traduzione italiana nativa di Discord. Chi usa Discord in italiano vede `/mod banna`, gli altri `/mod ban`. La lingua del **server** decide la lingua delle **risposte** del bot. | F8 |
| D2 | Gruppo `/mod` | Due gruppi. `/mod`: warn, timeout, mute, clear, lock, slowmode, casi, note. `/modban`: ban, tempban, softban, kick, unban. Così un proprietario può delegare il primo senza il secondo. | F7 |
| D3 | Forum dei log avanzati | Un post per **tipo** di log. | F6 |
| D4 | Vecchi nomi dei comandi | Nessuna compatibilità: i vecchi nomi spariscono. Il bot non ha ancora utenti. | F7 |
| D5 | Alert YouTube | Feed RSS per trovare i video nuovi, poi **una** chiamata `videos.list` per gruppo di ID (fino a 50). | F1 (BUG-16, `LIM-45`) |
| D6 | Conservazione dei dati | 90 giorni dopo l'uscita del bot da un server, poi cancellazione. Restano i ban e i kick di sicurezza (`retain_for_security`). | F5 |
| D7 | `/owner eval` e `/owner shell` | Spenti di default in produzione (`ENABLE_EVAL`). **Fatto** (`8a96320`, `2596734`). | — |
| D8 | Backup | Il server di backup lo crea un admin; **il bot Creator lo porta e lo tiene allo stato corrente**. Vedi sotto. | F3 |
| D9 | Intent `message_content` | Acceso. **Fatto nel codice** (`783329e`). L'owner deve attivarlo nel Developer Portal. | F1 |
| D10 | Musica | Un nodo wavelink **per ogni bot** per ogni server Lavalink. Scelta esplicita del nodo. Lavalink 4.2.0 o successivo. Vedi sotto. | F2 |
| D11 | Intent privilegiati | La regola di Discord guarda gli **utenti**: sotto 10.000 si accendono da soli, da 10.000 serve la domanda, da rifare ogni anno (changelog del 10/06/2026). Ogni documento che dice "100 server" per gli intent va corretto. | Tutti i documenti |
| D12 | Ping nei messaggi scritti dall'admin | In `/schedule-message`, benvenuti e sticky i ping di **ruolo** funzionano, se chi configura ha il permesso "Menziona tutti". `@everyone` e `@here` restano sempre muti. | F1 |
| D13 | Costi dell'AI | Si parte con i livelli gratuiti dei fornitori. Tetto di spesa mensile per server. Oltre il tetto: risposta locale senza AI. Le funzioni AI che costano sono premium. Niente AI prima della privacy policy. | F12 |
| D14 | Funzioni senza API gratuita (TikTok, Instagram, X) | Non si abbandonano: si offrono con feed "ponte" e webhook in ingresso, più una chiave API a pagamento facoltativa messa dall'owner. | F13 |
| D15 | Bot separato per log e moderazione | Nasce **iYokai Mod**: log, AutoMod e azioni di sicurezza girano su un bot diverso dal principale. I compiti sono divisi e ogni bot può sostituire l'altro. Vedi sotto. | F3 |
| D16 | Pannello web | Si fa dopo che il bot è completo. **Tutto** ciò che si configura con i comandi si configura anche dal pannello, in modo più semplice, più le opzioni che solo un sito permette. Per questo ogni impostazione passa da un solo punto del codice, usato sia dai comandi sia dal pannello. | F10, e ogni funzione nuova |
| D17 | Lavoro tracciato sulle issue | Il lavoro si segue sulle **issue di GitHub** (etichette e milestone per fase), non su file di piano. I file restano solo per l'analisi dettagliata e le regole. | Sempre |
| D18 | Funzioni richieste | Nessuna funzione richiesta dall'owner viene omessa o rimandata per scelta di chi scrive il codice. Se Discord la impedisce così com'è, si realizza l'alternativa più vicina e lo si dice. | Sempre |
| D19 | AI: si usa, non si addestra | iYokai usa servizi AI esistenti e ne salva i risultati per riusarli. Non addestra modelli. L'AI entra in ogni area, ma ogni funzione va anche con l'AI ferma. Vedi sotto. | F12, e ogni funzione nuova |
| D20 | Agenti specializzati | Il lavoro si fa con agenti specializzati (`.claude/agents/`), ognuno con i suoi parametri e con una memoria compressa in un file a parte (`.claude/memoria/`). Regole comuni in `.claude/regole/COMUNI.md`. | Sempre |
| D21 | Aggiornamento a caldo | L'owner aggiorna il bot da Discord. Strada consigliata: il bot prende da GitHub un commit già rivisto. Strada alternativa: file allegato dall'owner. In ogni caso: solo l'owner, controllo del codice, copia del vecchio, ritorno automatico se il caricamento fallisce, interruttore nel `.env`. Vedi sotto. | F9 |
| D22 | Voce di Yokai | Il bot manda messaggi vocali veri, con sotto i bottoni per trascrizione e traduzione. Sintesi sul server con un modello aperto, audio in cache. Voce femminile adulta; quattro toni scelti dall'admin; il tono `piccante` solo nei canali NSFW. Vedi sotto. | F12 |
| D23 | Boost del clan per tipo | Tre tipi di boost: **exp**, **coin**, **super** (exp + coin). Per ogni ambito (individuale e di gilda) un beneficio non si compra di nuovo finché il suo boost è attivo: chi ha il boost coin può comprare solo l'exp (e viceversa); chi ha il super non può comprare nessun altro. Vale anche per acquisti insieme. | F1 |
| D24 | Struttura dei comandi subito | La fase F7 passa **adesso**, dopo #144 e prima di F2. I comandi vanno nei 13 gruppi di `NUOVE_FUNZIONI.md`. Il bot configura da solo chi può usare `/admin`, `/mod`, `/modban`, `/security`, `/log` (passo di `/setup`): ruolo admin del bot e ruolo mod, oltre ai permessi di Discord. Il controllo del tetto di 100 comandi resta acceso. | F7 |

---

## D8 in dettaglio — Backup con il Creator che tiene il server aggiornato

**Cosa è cambiato in Discord:** dal luglio 2025 un bot non può più
**creare** un server. discord.py 2.6 segna deprecati `create_guild` e
`Guild.delete`. Tutto il resto del lavoro di backup resta possibile.

**Come funziona:**
1. Un admin **crea il server di backup**. Può partire da un link
   "modello di server" che il bot genera con `Guild.create_template`,
   così ruoli e canali nascono già pronti.
2. L'admin invita nel server nuovo **iYokai Creator** (e il bot
   principale) con il link che il bot gli dà.
3. Nel server nuovo lancia il comando di **collegamento** con un codice
   generato nel server principale. Nasce la coppia principale → backup.
4. Il **Creator porta il server di backup allo stato corrente**: ruoli,
   canali, permessi, emoji, sticker, suoni, e i messaggi copiati **in
   ordine cronologico** con i webhook.
5. Da lì in poi lo **tiene aggiornato**: mirror dei messaggi nuovi e
   controllo periodico delle differenze di struttura.
6. Snapshot settimanale dei membri, `/restore-users` e promozione
   lavorano su quella coppia.

**Perché il Creator e non il bot principale:** i limiti di frequenza di
Discord valgono per ogni bot separatamente. Il lavoro pesante di copia
gira sul token del Creator e non rallenta comandi, log e moderazione.

**Ordine dei messaggi e rate limit:** discord.py gestisce già i 429:
aspetta il tempo indicato e riprova, bucket per bucket. Se i messaggi
vengono mandati **uno dopo l'altro** (ogni `await webhook.send(...,
wait=True)` prima del successivo) l'ordine finale è corretto anche
quando interviene il rate limit; è solo più lento. Vietato mandarli in
parallelo. Le chiamate fatte a mano con aiohttp (oggi in
`/restore-users`) **non** hanno questa protezione: vanno riportate su
discord.py o devono rispettare `Retry-After`.

**Cosa viene tolto dal codice:** la creazione del server
(`create_guild`), il passaggio di proprietà, la cancellazione dei
server, la coda con i "10 posti", la pulizia dei server orfani (già
disattivata il 04/10). BUG-26, BUG-28 e BUG-29 riguardavano quel
flusso: superati. **Il Creator e `YOKAI_CREATOR_TOKEN` restano.**

**Attenzioni:**
- Un modello crea già ruoli e canali: la copia non deve duplicarli.
  Serve una mappa per **nome**, non per ID.
- Il Creator non è proprietario del server: per emoji e sticker gli
  serve `CREATE_GUILD_EXPRESSIONS`, e serve un ruolo alto per i ruoli.
- Al massimo 15 webhook per canale: il mirror riusa il suo.
- La coppia va ricordata anche dopo una promozione (BUG-34).
- Dal 16/11/2026 i canali che il bot non vede arrivano "offuscati":
  il Creator deve poter vedere tutti i canali del server principale,
  altrimenti copia segnaposto (`LIM-38`).

## D15 in dettaglio — iYokai Mod, il bot di log e moderazione

**Perché:** se il bot principale finisce in rate limit, o ha un
problema, log e moderazione non devono fermarsi. E viceversa.

**Divisione dei compiti** (stesso processo, stesso codice, stesso
database, token diversi):

| Bot | Compiti |
|---|---|
| **iYokai** (principale) | Comandi, bottoni e menu, configurazione, ticket, livelli ed economia, utility, divertimento |
| **iYokai Mod** (nuovo, `YOKAI_MOD_TOKEN`) | Scrittura dei log, AutoMod, anti-raid, anti-nuke, spam-trap, scadenze di tempban e mute |
| **iYokai Creator** | Backup: copia, mirror, aggiornamento del server di backup |
| **iYokai Music 1–5** | Riproduzione |

**Sostituzione:** ogni compito ha un bot titolare e uno di riserva. Un
piccolo modulo (`core/bot_roles.py`) sceglie chi agisce: il titolare se
è nel server, ha il permesso e non è bloccato da un rate limit lungo;
altrimenti la riserva. Se in un server c'è solo il bot principale,
fa tutto lui come oggi.

**Regole per non fare danni:**
- Tutti i bot ricevono gli stessi eventi: ogni evento ha **un solo**
  bot che lo gestisce, altrimenti i log escono doppi.
- A un comando risponde sempre il bot a cui il comando appartiene.
- Il blocco di Discord per troppe richieste sbagliate (10.000 in 10
  minuti) vale per **indirizzo IP**, quindi è comune a tutti i bot sulla
  stessa macchina: gli errori 401, 403 e 429 vanno evitati, non solo
  spostati su un altro bot.
- I webhook hanno limiti propri, separati dal bot: i canali di log
  usano un webhook per canale, con più righe raggruppate per invio.
- `/setup` dà i link di invito di tutti i bot necessari e dice quali
  funzioni restano ridotte se un bot manca.

## D10 in dettaglio — Musica

**Problema:** oggi tutti i nodi Lavalink sono collegati con il bot
principale (`cogs/music/player.py:1099`). I 5 bot musicali usano quella
sessione, quindi Lavalink si presenta a Discord con l'identità
sbagliata. Quasi certamente non esce audio (`LIM-40`).

**Decisione:**
- Un `wavelink.Node(client=<bot>)` per ogni bot e per ogni server
  Lavalink, con identificatore proprio.
- Ogni player nasce sul nodo del suo bot
  (`wavelink.Player(nodes=[nodo])`). Niente scelta automatica.
- Ogni nodo si collega in un task suo, con tentativi limitati: un nodo
  morto non blocca gli altri.
- Lavalink 4.2.0 o successivo (cifratura vocale DAVE, obbligatoria dal
  01/03/2026). `wavelink>=3.5.1` in `requirements.txt`.
- I brani locali della radio passano solo dal nodo locale.

## D11 in dettaglio — Due regole diverse, da non confondere

| Regola | Soglia | Cosa serve |
|---|---|---|
| Verifica dell'app | 100 server | Privacy policy, termini, identità verificata, 2FA. Senza, il bot non entra nel 101° server. |
| Intent privilegiati | 10.000 utenti | Domanda a Discord con motivazione, da rifare ogni anno. Sotto la soglia basta l'interruttore nel Portal. |

`REVIEW.md` L7 e `PIANO_FIX.md` R4 parlano di "100 server" per
l'intent: è il testo vecchio. Vale questa tabella.

## D19 in dettaglio — AI: si usa, non si addestra

**Il punto.** La regola di Discord per gli sviluppatori dice di non
usare i contenuti dei messaggi per **addestrare** modelli. iYokai non
addestra niente: manda una richiesta a un servizio esistente e usa la
risposta. È permesso.

**L'unica attenzione.** Molti livelli gratuiti usano ciò che ricevono
per migliorare i propri modelli. Se il bot manda lì i messaggi degli
utenti, l'addestramento lo fa il fornitore con dati arrivati da noi.
Per questo ogni servizio ha in tabella la voce "può ricevere messaggi":
- **sì** (dichiara di non addestrare su ciò che riceve): può ricevere
  ticket, segnalazioni, testi da riassumere;
- **no**: riceve solo richieste senza messaggi di utenti (storie,
  mostri, immagini, codice, domande generiche).
Prima di ogni invio si tolgono comunque menzioni, ID, email e inviti.

**Cosa si salva e chi lo riusa.**

| Contenuto | Dove vale |
|---|---|
| Scritto dall'AI da zero (storie, stanze, mostri, risposte generiche, traduzioni dei testi del bot) | In **tutti** i server: libreria comune |
| Nato dai messaggi di un server (risposte dello staff nei ticket, riassunti, base di conoscenza) | **Solo** in quel server; si cancella con i suoi dati (D6) |
| Conti dell'uso | Solo numeri, mai il testo |

**Regole.**
- Prima la cache e la libreria, poi le regole e il database, per
  ultima la chiamata all'AI.
- L'AI propone, una persona decide: nessuna punizione e nessuna
  risposta "ufficiale" parte da sola. Le risposte imparate dai ticket
  si usano dopo l'approvazione dello staff.
- Uno snodo unico sceglie il servizio per tipo di lavoro e per quota
  rimasta, e controlla le chiavi (`.claude/agents/custode-ai.md`).
- Il codice scritto dall'AI arriva solo come pull request in bozza.
  La correzione automatica del bot in funzione è rimandata dall'owner.
- Ogni scheda di funzione nuova dice dove l'AI aiuta e cosa succede
  quando l'AI è ferma.
- Restano valide D13 (tetto di spesa, premium) e la privacy policy con
  l'elenco dei fornitori prima di accendere l'AI in un server.

## D21 in dettaglio — Aggiornamento a caldo

**Scopo:** aggiornare il bot senza entrare nel server a mano e senza
fermarlo.

**Come:**
1. *Da GitHub (consigliata).* L'owner dà il comando; il bot prende da
   `main` il commit indicato (solo avanzamento lineare), e ricarica i
   cog cambiati. Il codice ha così storia, revisione e test.
2. *Da file allegato.* L'owner allega i file già pronti; il bot li
   mette al posto dei vecchi e ricarica il cog.

**Protezioni, in tutti e due i casi:**
- solo `OWNER_ID`; spento se nel `.env` manca `ENABLE_HOT_PATCH=1`
  (come `/owner eval`, D7);
- solo file `.py` dentro `cogs/` e `core/`; il codice viene compilato
  prima di sostituire;
- copia del file vecchio; se il cog non si carica, il bot rimette la
  copia e lo dice;
- ogni aggiornamento finisce nel registro (chi, quando, quali file,
  quale commit);
- una modifica a `core/` o a `main.py` non si ricarica a caldo in modo
  affidabile: il bot lo dice e propone il riavvio (pochi secondi).

**Limite:** `/owner` ha già 25 sotto-comandi. L'aggiornamento entra
come opzione di `/owner cog-reload`, senza comandi nuovi.

**Rischio da conoscere:** chi entra nell'account Discord dell'owner può
far girare codice sul server. Per questo l'interruttore nel `.env` e
l'autenticazione a due fattori sull'account.

## D22 in dettaglio — Voce di Yokai

**Cosa:** Yokai parla. Ogni vocale è un vero messaggio vocale di
Discord; sotto c'è un messaggio con "Trascrivi" e "Nella mia lingua",
che risponde solo a chi preme, nella lingua del suo client.

**Come:**
- Motore scelto dall'owner (05/10, dopo le prove): **Piper, voce
  italiana Paola**, con un filtro audio e i profili per contesto.
  Locale, sul processore, dentro il bot (in un thread a parte e in
  coda). Niente servizi cloud, niente chiavi, niente quote. Il motore
  sta dietro un'interfaccia: si può cambiare senza toccare il resto.
  Scartati alla prova: Kokoro, Dii, e i motori pesanti (Qwen3-TTS,
  Chatterbox) perché il server non ha una scheda video.
- Stesso testo, stessa voce, stessa lingua → stesso file, dalla cache.
- La trascrizione è il testo di partenza: non serve ascoltare l'audio.
- Il testo passa dai filtri del server prima di diventare voce.
- Ogni vocale ha sempre il suo testo a portata di bottone: nessuno
  resta escluso.

**La voce:** giovane donna adulta, calda, morbida, sicura di sé,
leggermente seducente; mai infantile, mai da anime, mai robotica
(specifica dell'owner in `VOCE_YOKAI.md`). Toni: `dolce`, `scherzosa` (di
partenza), `provocante`, `piccante`. Li sceglie l'admin del server.
`piccante` (volgarità e allusioni esplicite) vale solo nei canali
segnati NSFW e sul bot NSFW: Discord è aperto dai 13 anni, e fuori da
quei canali la voce parla a tutti.

**Moderazione:** la voce può accompagnare un avviso, con tono fermo;
il testo resta sempre e fa fede.

**Specifica e note di realizzazione:** `revisione/02-piano/VOCE_YOKAI.md`.
**Elenco completo degli usi e ordine dei lavori:** issue #142.


## D23 in dettaglio — Boost del clan per tipo

Chiesto dall'owner il 05/10/2026 (sera).
- Tipi: `exp` (×2 ai punti esperienza), `coin` (×2 alle coin), `super`
  (×2 a tutte e due). Durata 24 h, come oggi.
- Regola, per ambito (individuale per membro, di gilda per clan): un
  boost si può comprare solo se **nessuno dei suoi benefici** è già
  attivo. Quindi: coin attivo → si può comprare solo exp; exp attivo →
  solo coin; super attivo → niente; coin o exp attivo → il super no.
  Niente somma delle durate (sostituisce il cumulo di 48 h).
- Individuale e di gilda si moltiplicano tra loro, come prima.
- Prezzi (scelta consigliata, costanti in `core/guild_clan_boost_logic.py`):
  individuale exp 6.000, coin 6.000, super 10.000 (il prezzo di oggi);
  di gilda exp 60.000, coin 60.000, super 100.000. Il super costa meno
  dei due singoli insieme.
- Il boost che esiste oggi (×2 a tutto) diventa un `super` già attivo.
- Nessun comando nuovo: `/clan boost individuale` e `/clan boost gilda`
  prendono un'opzione `tipo` con tre scelte.

## D24 in dettaglio — Struttura dei comandi subito

Chiesto dall'owner il 05/10/2026 (notte): "scegli te". Scelta: fare F7 ora.
- Motivo: i nuovi comandi (voce, AI, backup, musica) nascono già nel
  gruppo giusto, niente doppio lavoro; il tetto di 100 non si supera
  mai, quindi il bot si può provare dal vivo in ogni momento.
- Il controllo del tetto di 100 **non** si spegne.
- Accesso: i gruppi si vedono per permesso di Discord (`default_permissions`)
  e il bot controlla da sé il ruolo scelto dall'admin. Il bot non può
  nascondere comandi per ruolo da solo (serve l'OAuth dell'admin): il
  rifiuto "non puoi" è il controllo interno. Un solo punto di codice:
  `core/command_access.py`, usato dai comandi e dal futuro pannello (D16).
- Il passo di `/setup` propone di creare o scegliere "ruolo admin del bot"
  e "ruolo mod": chi non lo configura ha comunque i permessi di Discord
  come base sicura.
- Nessuna compatibilità con i vecchi nomi (D4).
- Ordine: un agente alla volta sui file dei cog (i comandi si spostano);
  prima il quadro in `core/`, poi le aree.

**Aggiornamento D24 (guardiano-limiti, 05/10/2026):** con 13 gruppi `/admin`
supera gli 8000 caratteri per comando (9241 oggi, solo con i comandi che
già esistono). Si passa a **16 gruppi**: `/admin` si divide in `/admin`,
`/gestione` (ticket, voice, economia, ruoli, benvenuto) e `/moduli`
(alert e le funzioni nuove), e `automod` resta di primo livello. Restano
84 posti liberi su 100. Tutta la mappatura `comando di oggi → nuovo
percorso` è in `revisione/02-piano/MAPPA_COMANDI_F7.md`. Si toglie il
prefisso `[Admin] ` / `[OWNER] ` dalle descrizioni (8 caratteri per comando).
Il test dei caratteri per comando (massimo 8000, allarme a 6800) e dei nomi
unici tra figli si aggiunge in `tests/test_command_tree_invariants.py`.

**Aggiornamento D24 (owner, 06/10/2026):** `/cerca-comando` (cerca un comando
dalla descrizione) e `/chiedi` (informazioni sul bot e dialogo, come il
vecchio Clyde di Discord) sono comandi di **primo livello**, fuori dai
gruppi, e devono essere i primi due della lista. Il bot non può impostare
l'ordine: lo decide Discord (di norma alfabetico, poi per uso). Quindi:
restano singoli e con questi nomi; **da verificare dal vivo** l'ordine
reale (voce in `VERIFICA_LIVE.md`). Se Discord ordina per nome, si
scelgono nomi che vengono prima degli altri (es. i gruppi che iniziano per
"a" si possono rinominare o i due comandi prendere un nome corto che inizia
per "a"/"b"); la scelta si fa dopo la prova, con una sola riga da cambiare
in `core/command_groups.py`. Primo livello: 16 gruppi + 2 = 18 su 100.

**Aggiornamento D24 (owner, 06/10/2026, 00:14) — comandi in cima:** l'owner
vuole che digitando `/` compaiano per primi "ultimo comando usato",
`/cerca-comando`, `/chiedi`, poi le categorie (admin, mod…), e che il suo bot
sia il primo tra i bot del server. Cosa può fare il bot e cosa no:
- L'ordine della lista `/` e l'ordine dei bot nel selettore li decide il
  **client di Discord** (comandi usati di recente dall'utente, poi per app e
  per nome). **Nessuna API permette a un bot di cambiarli.** Non si promette.
- "Ultimo comando usato": Discord lo mostra già da solo per ogni utente.
- Quello che si fa nel bot: `/cerca-comando` **senza testo** apre un pannello
  (messaggio effimero) con i **comandi usati di recente dall'utente**
  (da `command_usage`, per server e utente, con tetto e pulizia) e i
  **bottoni delle categorie** che l'utente può usare (Admin, Mod, Sicurezza,
  Gestione… solo se `command_access.puo_usare`), ognuno con l'elenco dei suoi
  comandi in pagine. Con il testo cerca per descrizione (F12 per la parte AI).
  `/chiedi` mostra lo stesso pannello come suggerimento. Nessun comando nuovo.
- Nomi dei comandi pensati per l'ordine alfabetico: dopo la prova dal vivo.

**Aggiornamento D24 (owner, 06/10/2026, 00:27) — `/cerca-comando` come help evoluto:**
- Senza testo: pannello solo per chi lo apre, con l'**ultimo** comando usato
  (uno solo, cliccabile) e i bottoni delle categorie che può usare.
- Con testo: l'opzione `testo` ha il completamento (≤25 suggerimenti) e il
  risultato mostra i comandi trovati con descrizione e **variabili** (opzioni:
  nome, descrizione, obbligatoria o no). Ogni comando è una **menzione
  cliccabile** (`</gruppo comando:ID>`): da cellulare e da PC un tocco lo inserisce
  nella barra del messaggio. Gli ID si leggono dall'albero registrato
  (`fetch_commands`) e la cache si ricarica allo scadere del tempo (1 ora) o quando manca l'ID di un comando
  (comando nuovo dopo una sync, al massimo una volta al minuto).
- Bottone "Apri nella wiki" se `WIKI_BASE_URL` è impostato: la wiki del sito
  (F10) si **genera dall'albero dei comandi** (percorso, descrizione, livello
  d'accesso, opzioni) con `scripts/genera_wiki.py`: una sola fonte (D16),
  quindi comandi e documentazione non divergono mai.
- La ricerca si fa prima con regole (nome, descrizione, sinonimi italiani,
  somiglianza) e solo dopo con l'AI (F12). Nessun comando nuovo.
- Prove sull'ordine in lista: nomi ammessi da Discord (regex ufficiale:
  lettere minuscole, numeri, `-`, `_`, `ʼ`, devanagari, thai); Discord ordina i
  comandi di un'app **in ordine alfabetico** e mostra in cima i "più usati"
  dell'utente. Se `_`, `-` o i numeri vengono prima delle lettere lo dice la
  prova `scripts/prova_ordine_comandi.py` (voce in `VERIFICA_LIVE.md`).

**D24, nota finale (11/10/2026).** I due comandi di primo livello si chiamano
`-cerca-comando` e `-chiedi` (col trattino, per stare in cima alla lista;
il resto dei nomi è normale). `-cerca-comando` non funziona in DM. Nascondere
i comandi per ruolo con un controllo su database non è possibile: il
controllo parte dopo che il comando è stato lanciato. La strada vera è
l'OAuth dell'admin con permessi per ruolo (issue #148); per ora valgono
`default_permissions` e il controllo interno.

## D25 — Nuovi gruppi di primo livello quando uno supera i 6.800 caratteri (13/10/2026)

Discord conta 8.000 caratteri per comando di primo livello, figli compresi.
Con le funzioni nuove `/gestione` e `/admin` superavano il limite. Scelta:
si può aggiungere un **gruppo** di primo livello (restano 100 posti, siamo a 17)
quando un gruppo supera i 6.800 caratteri; si sposta un blocco intero, non
singoli comandi. Primo caso: `/economia` (da `/gestione economia`: XP, monete,
negozio, giveaway per lo staff). `/admin comandi` e `/admin messaggi` vanno in
`/moduli`. Il gruppo nasce con permesso `manage_guild` e livello admin.

**Secondo caso (14/10/2026): `/antinuke`.** `/security` arrivava a 6.824 caratteri con
`canale-allarmi` (#59 3.18) e doveva ancora ricevere `/security panico` (NF-29). Si sposta
il blocco intero `/security antinuke *` in un gruppo di primo livello `/antinuke` (stessi
12 comandi più `canale-allarmi`, stesso permesso `administrator` e livello sicurezza).
`/security` resta con anti-raid, panico, verifica, ban globale, heatmap, score, spam-trap.

**Terzo caso (14/10/2026): `/antiraid`.** Con i filtri all'ingresso e i segnali di raid
(#117, SIC-023…038) e `/security verify tempi` (#118) `/security` arrivava a 7.126 caratteri.
Si sposta il blocco intero `/security antiraid *` in un gruppo di primo livello `/antiraid`
(16 comandi, stesso permesso `administrator` e livello sicurezza). `/security` resta con
panico, verifica, ban globale, escalation, heatmap, score, spam-trap.

**Quarto caso (15/10/2026): `/backup`.** `/admin` era a 6.577 caratteri e il backup doveva
ricevere modelli e sincronia (NF-39), copie datate, esportazioni e importazioni (#121, M 12.17).
Il blocco intero `/admin backup *` (main, crea, collega, promuovi, restore-modo,
restore-utenti) diventa il gruppo di primo livello `/backup` (permesso `administrator`,
livello admin), con le funzioni nuove dentro. `/admin` scende sotto i 5.600 caratteri.

**Quinto caso (21/10/2026): `/ruoli`.** `/gestione` è a 6.325 caratteri (con le condizioni
dei ruoli automatici) e gli strumenti sui ruoli del catalogo #123 (dare e togliere, a tempo,
azzerare, operazioni di massa, creare, modificare, diagnosi, ruoli a scelta) pesano 1.840
caratteri: insieme arriverebbero a 8.165, oltre il limite di 8.000. Il blocco nuovo nasce già come gruppo di primo livello `/ruoli` (permesso
`manage_roles`, livello admin). `/gestione ruoli` resta con menu di ruoli, ruoli automatici e
ruoli-premio: spostarlo toccherebbe tre cog di aree diverse senza guadagno per l'utente. Il
comando per i membri (prendere i ruoli a scelta) sta in `/utility ruolo`.

## D26 — Motore AI: gruppo `/ai`, fornitori dal `.env`, chi addestra non entra (14/10/2026)

**Gruppo.** La configurazione dell'AI (consenso, canali, limiti, privacy, lore, parole
vietate, funzioni automatiche, moderazione, traduzione, personaggi, base di conoscenza,
costruzione del server: 13 comandi, ~2.500 caratteri) doveva stare in `/admin ai`, ma
`/admin` è a 6.432 caratteri: con il blocco AI supera i 6.800. Per D25 il blocco intero
diventa un gruppo di primo livello **`/ai`** (permesso `manage_guild`, livello admin). Le
funzioni per tutti stanno nel sotto-gruppo **`/utility ai`**; `-chiedi` resta dov'è e usa
l'AI quando è accesa; nei ticket `/ticket assistente`.

**Fornitori.** L'owner non ha ancora dato l'elenco: il motore li legge dal `.env`
(`AI_FORNITORI` e una serie `AI_*_<NOME>` per ciascuno), tutti nel formato compatibile
OpenAI, quindi si aggiungono senza toccare il codice. Senza fornitori il bot parte e ogni
comando AI dà la sua risposta senza AI.

**Addestramento (più stretto di D19).** Un fornitore entra solo se nel `.env` c'è
`AI_ADDESTRA_<NOME>=no`: chi addestra sui dati ricevuti non si usa per niente, nemmeno per
i testi senza messaggi degli utenti. Così non serve la doppia lista "può ricevere messaggi".

**Spesa.** Tetto mensile per server in centesimi; 0 (il valore iniziale) vuol dire solo
fornitori gratuiti (D13). Le chiavi a pagamento si usano solo con
`AI_USA_CHIAVI_PAGAMENTO=si`. Il modulo `ai` si può rendere premium dall'owner.
## D27 — Il pannello web nasce dentro il bot (14/10/2026)

L'issue #91 diceva «repository separato e privato». Scelta consigliata, presa ora: il pannello
gira **nello stesso processo** del bot (`core/web_panel_server.py`, aiohttp come gli altri
server web), spento finché mancano le variabili del `.env`. Motivi: chiama davvero gli stessi
punti unici dei comandi (D16) senza un'API da tenere allineata, il bot vede i cambi subito,
nessun token di Discord salvato (solo `identify`). Se l'owner vuole il sito in un repository a
parte, si sposta la cartella `pannello_web/` e il pannello parla col bot da `core/panel_bridge.py`.
Da confermare con l'owner.

## D28 — Il ruolo admin del bot lo sceglie solo chi ha «Amministratore» (14/10/2026)

Il ruolo admin del bot vale anche per i comandi di livello SECURITY, che senza il ruolo
chiedono «Amministratore». Chi ha solo «Gestisci server» poteva scegliere come ruolo admin
un ruolo suo e prendersi i comandi di sicurezza. Scelta: **mettere un ruolo admin nuovo**
(diverso da quello attuale) richiede «Amministratore» o essere il proprietario del server.
Toglierlo o lasciarlo uguale no (non apre nulla). La regola sta in un punto solo,
`core.command_access.errore_ruolo_admin`, usato da `imposta_ruolo` (pannello web),
`/admin config import` e `/admin config rollback`. `/setup` non tocca questo valore.
Ruoli mod e ban: invariati (bastano i permessi di `/admin`).

## D29 — La scala dei warn manuali fa solo ciò che il moderatore può fare (22/10/2026)

Con `/security escalation enable warn_manuali:True` un `/mod warn` sale la scala di
escalation (M 1.10). La scala la esegue il bot: senza regole, un moderatore con il solo
permesso di dare timeout potrebbe far espellere o bannare qualcuno a forza di warn, e
`/mod massa warn` farebbe fino a 50 kick o ban senza il tetto delle azioni in massa.
Scelta: **il gradino parte solo se il moderatore che ha dato il warn potrebbe farlo da sé**
(permesso di Discord: «Metti in timeout», «Espelli», «Banna»; e la gerarchia dei ruoli,
ricontrollata al momento). **Dai warn in massa kick e ban non partono mai.** In tutti e due
i casi il warn resta registrato con il suo caso, l'infrazione resta contata, e l'esito dice
al moderatore cosa chiedeva la scala e perché non è partito. Vale per tutti i gradini: un
gradino di timeout non accorcia mai un timeout più lungo già in corso (anche per l'AutoMod).
La regola sta in un punto solo, `cogs/automod/escalation.py` (`scala_per_warn_manuale`).


## D30 — Il 24/7 in un canale vuoto è premium (27/10/2026)

> **Confermata dall'owner (28/10/2026), con precisazione:** il bot musicale principale fa la radio live dell'owner, sempre 24/7, e nessun server lo controlla. Le 5 istanze (e quelle che si aggiungeranno) restano 24/7 solo con il premium.

`/music nonstop on` mette la coda in loop. Un bot musicale che resta in un canale
vuoto occupa per sempre uno dei 5 bot musicali, che sono gli stessi per tutti i server:
cinque persone, in cinque server, potrebbero lasciare tutti gli altri senza musica.
Scelta: **il loop vale per tutti; restare nel canale vuoto (niente uscita per inattività,
niente pulizia del controllo memoria) solo per i server con premium**
(`guild_has_premium_access`). Senza premium il comando lo dice e il bot esce come
sempre quando il canale resta vuoto. La radio del bot principale non cambia.
Da avvisare l'owner.

## D31 — La lista di base delle parole d'odio non si apre voce per voce (28/10/2026)

> **Superata da D35 (28/10/2026, owner):** una frase lecita che contiene una parola d'odio NON basta a farla passare (es. «questa banda di negri…»). Il contesto lo giudica l'AI (D35).

La lista di base del filtro delle parole vietate (AMD-014, `data/automod_parole_odio.txt`)
è accesa con l'AutoMod. Una voce di base **non** si può mettere da sola tra le parole lecite
del server (né da comando né da import): altrimenti un admin la spegnerebbe senza conferma.
Le **frasi** lecite che la contengono restano permesse (es. «rio negro»): così si tolgono i
falsi positivi senza aprire la parola. Per spegnere tutta la base serve `conferma: true`, e
via import la cambia solo il proprietario del server (CHIAVI_SOLO_PROPRIETARIO).
## D32 — Link d'invito personali «finto vanity» dal sito (28/10/2026)

L'indirizzo personalizzato vero di Discord (vanity) vuole il boost di livello 3 e ce n'è uno solo per
server. Alternativa (D18): ogni membro ha un link `<WEB_PANEL_PUBLIC_URL>/invito/<nome-server>-<nome-utente>`
che il sito gira a un invito Discord vero, dedicato a lui. Regole:
- Lo slug è unico in tutto il bot (non contiene l'ID del server), minuscolo, solo a-z 0-9 e trattini;
  le collisioni si risolvono con `-2`, `-3`… Non cambia mai: chi cambia nome tiene il vecchio indirizzo.
- L'invito Discord lo crea il bot (senza scadenza né limite d'usi) alla prima apertura e lo riusa;
  se sparisce lo ricrea. Se Discord non risponde non se ne creano di nuovi a raffica.
- Modulo, ruolo richiesto e permesso «Crea invito» (del bot **e del membro**, nello stesso canale)
  si ricontrollano a ogni apertura: il bot non crea per un membro un invito che lui non potrebbe
  creare. Il canale dell'invito è uno che vede @everyone, se c'è (l'anteprima ne mostra il nome).
  La pagina pubblica non mostra nomi, ha un limite per IP e dice solo perché non funziona.
- Al massimo 500 link personali con un invito Discord per server (Discord ne tiene 1000, LIM-36).
  Un invito si considera vivo per 5 minuti dopo l'ultima verifica (o fino all'evento di cancellazione),
  e solo se è di quel server: il sito gira solo a `discord.gg/<codice>` creato dal bot.
- L'ingresso con un invito del bot si attribuisce al proprietario del link; il tipo (personale,
  normale, vanity, sconosciuto) sta in `invite_joins.kind`. Il vanity vero si segue a parte.
- Privacy: il link si cancella con il membro (e quando esce dal server) e dopo 365 giorni senza uso;
  chi cancella i suoi dati sparisce come invitato e come invitante diventa `0` (D6).
Codice: `core/invite_service.py`, `core/web_panel_inviti.py`, comandi `/level inviti link|storico|opzioni`.
## D33 — I log possono uscire da un webhook del server (28/10/2026)

Con `/log webhook attivo:True` i canali di log scrivono tramite un webhook creato dal bot nel canale
stesso (serve «Gestisci webhook»). Motivo: i webhook hanno un limite di frequenza loro e portano
fino a 10 embed per messaggio, quindi un raid non esaurisce il limite del bot.
Scelte: le righe ravvicinate (2 secondi) si raggruppano in un messaggio solo (10 embed e 5.500
caratteri al massimo); i messaggi con bottoni restano sul canale normale; se il webhook è cancellato
o non risponde, i log tornano subito al canale e il webhook si dimentica. Il token è cifrato con la
chiave OAuth (`core/oauth_crypto.py`, dato associato server+canale); senza chiave la funzione non si
accende. Spegnendo, i webhook creati dal bot si cancellano. Punto unico: impostazione `log_webhook`.
## D34 — `/log ignora` non nasconde gli eventi di sicurezza (28/10/2026)
Dal giro r10 `/log ignora` (canali, categorie, utenti, ruoli) vale anche per voce, canali,
thread e membri. Così però un ruolo «Staff» ignorato toglieva dal log i ruoli dati e i
timeout dello staff, e un canale ignorato toglieva i cambi dei suoi permessi.
Scelta: **restano sempre nel log** i ruoli dati e tolti, i timeout, i cambi dei permessi
di un canale, i canali cancellati, il mute e il deafen dati dal server. `/log ignora`
nasconde il resto (soprannomi, ingressi e uscite in voce, mute proprio, canali e thread
creati o modificati). La regola sta in `cogs/logging/advanced_logs.py` (`VOCE_SEMPRE_NEL_LOG`,
canali) e `cogs/logging/basic_logs.py` (`on_member_update`).

## D35 — Parole d'odio: due livelli, contesto giudicato dall'AI (28/10/2026, owner)

1. **Blocco preventivo (AutoMod nativo):** le frasi palesemente d'odio (insulto + minaccia o
   incitamento) si bloccano prima dell'invio, con il banner di sistema di Discord e un testo
   personalizzato (≤150 caratteri, es. «Primo richiamo: la tua affermazione risulta razzista…»).
   Solo il nativo può mostrare quel banner, e lì il bot non vede il messaggio.
2. **Parola sospetta da sola (lato bot):** il messaggio arriva al bot, l'AI giudica il contesto.
   Cognome o uso normale («Simone Negri lavora al supermercato») → passa. Insulto → cancellato,
   richiamo all'utente che si cancella da solo, richiamo contato; N richiami in un tempo X →
   timeout (configurabile). Con l'AI ferma: cancella e avvisa (lato sicuro).
3. **Libreria mondiale multilingue** delle parole bandite e delle loro varianti, che cresce: una
   variante nuova trovata dall'AI entra come «candidata» e diventa globale dopo segnalazioni da
   più server o con l'approvazione dell'owner (un server solo non può avvelenare la lista).
   La libreria è documentata.

## D36 — Link d'invito personali: lo decide il server (28/10/2026, owner)

Precisa D32. Opzione del server: tutti hanno il link personale / solo chi ha «Crea invito» /
solo un ruolo / spento. Il link personale funziona anche se il server toglie «Crea invito» a
tutti: l'invito Discord lo crea il bot. Il tetto di 500 link per server resta.

## D37 — Messaggi di ban e di addio (28/10/2026, owner)

Di base escono tutti e due: prima il «martello» (immagine o gif), poi l'addio scherzoso
(«Ciao, è stato bello vederti»). Il server sceglie: entrambi, solo uno, nessuno, e la grafica
di ciascuno.

## D38 — Moneta del server: nome senza emoji, immagine propria (28/10/2026, owner)

Il nome della moneta resta solo testo. Quando il server configura le monete il bot chiede il
nome e un'immagine; l'immagine compare negli embed accanto al saldo. Senza immagine si usa la
moneta di iYokai.

## D39 — Parole d'odio: dove sta la libreria e cosa succede senza AI (28/10/2026, scelta di chi sviluppa; da confermare all'owner)

Precisa D35. Scelte fatte dove D35 lasciava aperto:
- Il proprietario del bot gestisce la libreria (approva, rifiuta, aggiunge) con `/automod odio libreria`,
  che risponde solo a lui. `/owner` ha già 25 sotto-comandi su 25 e non se ne aggiungono; una pagina
  nel pannello `/proprietario` può chiamare lo stesso codice (`odio_libreria_repo`) in futuro.
- Le parole «sospette» (cognomi e parole normali) stanno in un file a parte, `data/automod_parole_sospette.txt`;
  gli insulti della lista di base restano cancellati subito, senza chiamare l'AI. Così l'AI si paga solo dove serve.
- «AI ferma» vale per ogni caso in cui il giudizio non arriva: AI spenta nel server, senza consenso, quota finita,
  fornitori fermi, errore o risposta illeggibile. Il messaggio si cancella e l'utente è avvisato (lato sicuro, D35).
- Una candidata vale solo nei server che l'hanno segnalata (come parola sospetta, quindi sempre giudicata dall'AI);
  con 3 server diversi o con l'approvazione diventa una voce globale. Una rifiutata non risale.
  Precisazione (revisione, 28/10/2026): i 3 server devono avere **proprietari diversi** e almeno 25
  membri (migrazione 0391); parole corte, comuni o lecite non diventano candidate. Con l'AI ferma il
  messaggio si cancella senza contare il richiamo.
- Il blocco nativo usa solo gli insulti certi della lista di base (non le parole sospette), vicino a una minaccia.



> **Confermata dall'owner (28/10/2026):** con l'AI spenta o senza consenso ogni messaggio con una
> parola sospetta si cancella, cognomi compresi. Una variante segnalata da 3 proprietari diversi
> diventa **condivisa** (vale in tutti i server ma la giudica sempre l'AI); diventa **certa**
> (approvata, cancellata senza AI) solo con l'approvazione dell'owner (migrazione 0392).

## D41 — Immagine della moneta e istanze musicali oltre 5 (28/10/2026)

Precisa D38 e D30. **Moneta:** l'immagine sta in `guild_coin_images` (PNG 128x128, al massimo 64 KiB,
ridotta con `core/safe_image.py`); compare **sempre come miniatura** dell'embed (file `moneta.png`),
con un aiuto solo: `core/moneta_server.aggiungi_moneta`. Senza immagine: `assets/moneta_iyokai.png`
(disegnata da `scripts/genera_moneta_iyokai.py`). Il nome rifiuta emoji, codici `:nome:` e menzioni.
Si imposta con `/level impostazioni xp immagine_moneta:` (o `senza_immagine:`).
**Istanze:** `MUSIC_TOKEN_1..5` obbligatori, `MUSIC_TOKEN_6..20` facoltativi (tetto 20, senza buchi).
La radio del bot principale resta solo di `/owner radio` (un test controlla che i comandi dei server
usino solo il player dei worker). Da avvisare l'owner.

## D48 — Vista dei log su forum: un post per canale o per caso (28/10/2026, scelta di chi sviluppa)

Chiude 8.17. La proiezione su forum scartata in BACKLOG §3 vale solo per i **membri** (troppi post, raid).
Per **canali** e **casi** di moderazione, che sono pochi, `/log vista-forum` apre un post per ciascuno. Tetto di 200 post
per vista e per server; scrittura da una coda unica (500 posti, un messaggio al secondo) perché i forum hanno limiti stretti
e un raid non deve riempire la memoria. Il registro degli eventi e quello dei casi avvisano il servizio dopo la loro scrittura:
senza una scelta del server non succede niente. I log di sempre (canale di testo o forum per tipo) non cambiano. Cambiare forum
scorda i post del vecchio; spegnere la vista lascia i post su Discord.

## D49 — Missioni, serie, traguardi e stagione: spenti di base, monete piccole (28/10/2026, scelta di chi sviluppa)

Chiude la parte «missioni, traguardi, serie, battle pass, profilo globale positivo» di 23.17 (NF-41).
Un solo comando per i membri, `/level progressi sezione:` (missioni di oggi, traguardi, serie, stagione, profilo globale),
e uno per lo staff, `/economia progressi attivo:` (impostazione `progressi_attivi`, **spenta di base**: i premi sono monete
nuove e solo il server decide se vuole farle uscire). Regole:
- **Missioni** del giorno (UTC), tre fisse: 15 messaggi che danno XP (30 coin), 30 minuti in vocale (40), la ricompensa
  giornaliera (20). Gli eventi si contano nei punti dove il livellamento li assegna già (`add_text_xp`, `add_voice_minutes`,
  `claim_daily`), in memoria, e si scrivono ogni 20 secondi; 20.000 voci al massimo in attesa. Il premio esce una volta sola:
  segna «riscossa» e paga nella stessa transazione.
- **Serie**: giorni di fila con `/level daily`; ogni 7 giorni un bonus di 5 coin per giorno di serie (tetto 200).
- **Traguardi**: 9, con emoji (livelli 5/10/25/50, serie 7/30, missioni 10/100, una stagione completa). Senza monete.
- **Stagione** (il «battle pass»): è il mese; 10 gradini, il gradino n si raggiunge con n x 1.500 XP del mese e vale n x 40 coin.
- **Profilo globale**: lo vede solo chi lo chiede (messaggio privato), solo numeri positivi (server, livello più alto, serie più lunga,
  traguardi); niente nomi di server, niente monete, niente sanzioni.
Le tabelle `progress_*` (0481) sono nel registro dei dati: si cancellano con l'utente e si esportano; missioni e stagioni scadono.
Nessun premio in soldi veri e niente giochi d'azzardo (vincoli di NF-40 invariati).

## D50 — Punteggio di rischio e carico dello staff: un aiuto, non un giudice (28/10/2026, scelta di chi sviluppa)

Chiude il resto di 23.17. `/mod rischio member:` (da 0 a 100, con i motivi) unisce i segnali che il bot già ha: warn attivi, timeout
degli ultimi 90 giorni, espulsioni, ban e tempban passati, trappola anti-spam, età dell'account, primo giorno nel server e doppi trovati
dalla verifica web nello stesso server. Fasce: basso sotto 25, medio da 25, alto da 55. **Nessuna azione parte dal punteggio**
(coerente con NF-21: niente ban automatici per impronta) e la risposta è privata, per lo staff. `/mod carico giorni:` mostra per ogni
persona dello staff casi aperti, appelli decisi e ticket presi in carico, con la quota sul totale; senza classifica a premi e senza
contare i casi della scala automatica. Entrambi usano il modulo del case system. Le letture stanno in `staff_carico_repo` (nessuna tabella nuova).
