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

**Aggiornamento (D55, 01/11/2026).** I servizi che nel livello gratuito addestrano sui dati sono
ammessi come ripiego: il router preferisce sempre chi non addestra, e sui server con privacy
«senza_messaggi» chi addestra non si usa mai. Resta fermo che iYokai non addestra niente.

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
`cerca-comando` e `chiedi` (col trattino, per stare in cima alla lista;
il resto dei nomi è normale). `cerca-comando` non funziona in DM. Nascondere
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
funzioni per tutti stanno nel sotto-gruppo **`/utility ai`**; `chiedi` resta dov'è e usa
l'AI quando è accesa; nei ticket `/ticket assistente`.

**Fornitori.** L'owner non ha ancora dato l'elenco: il motore li legge dal `.env`
(`AI_FORNITORI` e una serie `AI_*_<NOME>` per ciascuno), tutti nel formato compatibile
OpenAI, quindi si aggiungono senza toccare il codice. Senza fornitori il bot parte e ogni
comando AI dà la sua risposta senza AI.

**Addestramento (più stretto di D19; allentato da D55).** Ogni fornitore dichiara nel `.env`
`AI_ADDESTRA_<NOME>=no|si`. Dal 01/11/2026 (D55) anche chi addestra è ammesso, ma solo come ripiego.

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

## D42 — Strumenti dello staff con l'AI dentro `/ai staff` (29/10/2026)

Riassunto di un incidente, regola di AutoMod assistita e ricerca nei log stanno in `/ai staff incidente|regola|cerca-log`
(admin), al posto di `/security panico riassunto`, `/automod proponi` e `/log cerca domanda`: quei gruppi sono al limite
di peso (D25) o pieni. Stessa funzione, altro percorso. L'AI propone; la regola AutoMod si attiva solo con il bottone;
la ricerca nei log non mostra il contenuto dei messaggi. Senza AI: elenco in ordine di tempo, parole per scegliere il
filtro, filtri dai nomi e dagli ID scritti. Da avvisare l'owner.

## D43 — Libreria dei giochi AI e premi (29/10/2026)

Mostri, storie e stanze scritti dall'AI da zero stanno in tabelle senza server (`ai_mostri`, `ai_storie`, `ai_storie_nodi`)
e valgono in ogni server con lo stesso tema (D19: nessun testo di utenti). «XP per 24 ore» del mistero diventa un premio
XP una tantum. Il boss di rete lo pubblica solo l'owner. Tutto parte spento e funziona con l'AI ferma (mostri e storie pronti).

## D44 — Voce di Yokai e processo AI separato (29/10/2026)

Il motore di sintesi vocale è un modello aperto scelto da `.env`; resta spento finché l'owner non sceglie la voce (D22).
Il processo AI separato (25.21) resta rimandato: bastano coda e misure già fatte (25.22); si riapre se le misure lo chiedono.

## D45 — iYokai App: dati personali e musica (28/10/2026)

Precisa B.2-B.10 (#107). Il profilo globale (livello, clan, medaglie) lo vede un'altra persona **solo se il
proprietario lo ha acceso** (`profilo_pubblico`, spento di base); lo storico dei comandi si salva solo se acceso,
al massimo 100 righe, 90 giorni. Le richieste di assistenza aprono un thread nel canale `SUPPORT_CHANNEL_ID`
(spento se 0). Menu del messaggio: Discord ne accetta 15 per tipo, discord.py 2.7.1 ne conta 5: l'albero dell'app
(`AlberoApp`) alza il tetto locale a 15. **Musica (C17, C18):** i testi delle canzoni non si copiano (diritti): si
dà il link di ricerca. L'Activity «radio iYokai» sta nel pannello (`/attivita/radio`, SDK MIT in
`pannello_web/static/`); discord.py non crea il comando d'ingresso: lo crea il Portal (Activities, mappa URL).
Da avvisare l'owner.

## D46 — iYokai Desktop: accesso, avvisi e staff (28/10/2026)

Precisa D.1-D.11 (#108). **Accesso:** un codice personale (`dsk_…`) creato dal comando dell'app e mostrato una
volta; il servizio salva solo l'impronta SHA-256 (migrazione 0452). Sostituisce l'accesso OAuth2 dal programma
(nessun segreto nel programma, nessun redirect locale). **Tempo reale:** attesa lunga (fino a 20 s) invece di
connessione permanente. **Avvisi:** menzioni, risposte e parole chiave si salvano solo per chi li accende, con
testo breve per 90 giorni (registro dei dati); si mostrano solo se la persona è ancora nel server e vede il canale.
**Staff:** il programma chiede, agisce il bot con i permessi veri della persona (blocca/sblocca canale, timeout,
annuncio, mai menzioni); ogni richiesta è registrata. Il programma non usa mai il token dell'account Discord.
Le funzioni con scope `rpc` restano spente («da attivare») finché Discord non approva l'applicazione.

## D47 — Pannello: pagina per modulo, editor, wiki statica (28/10/2026)

Precisa 24.2, 24.5 e #147. **Pagine per modulo:** `core/config_impostazioni.py` elenca le chiavi di
`SETTINGS_SCHEMA` che il sito mostra (bool, numeri, testi, scelte, canali e ruoli del server); le chiavi che
decidono chi può fare cosa e le liste restano ai comandi. Stessi controlli dello schema, stesso storico.
**Editor:** embed salvati e messaggio di benvenuto con anteprima, con gli stessi controlli e lo stesso archivio dei
comandi; i ping di ruolo del benvenuto restano spenti dal sito. **Wiki statica:** `scripts/genera_wiki.py` scrive
un sito dall'albero dei comandi con gli stessi modelli del pannello.
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

## D51 — Chiusura di 23.17: missioni a tre livelli, serie protetta, pass di 90 giorni, carico solo per ADMIN (1/11/2026, scelta di chi sviluppa)

Completa «i dettagli da non perdere» di `VOCI_OMESSE.md`. **Una finestra sola:** `/level progressi` non ha più parametri; apre un menu
(missioni, traguardi, serie, pass, profilo globale) con i bottoni della sezione aperta. Così `/level` pesa 6.444 caratteri (limite 6.800).
`/economia progressi` ha `attivo` e `obiettivo_server` (tutti e due facoltativi; senza niente dice com'è).

- **Missioni:** del giorno, **della settimana** (dal lunedì, UTC) e **di tutto il server**. Ogni evento conta sulla missione del giorno e su
  quella della settimana. Quelle del server sommano ciò che ognuno ha fatto *fino al tetto della sua missione della settimana*: nessuno
  vince da solo («contano le attività di qualità, non la quantità»). Premio a chi ha dato almeno il 10% della sua missione. Obiettivo del
  server: impostazione `progressi_obiettivo_server` (messaggi a settimana, di base 1.000, da 50 a 100.000; vocale al 60%), un solo punto
  di scrittura (D16).
- **Serie:** niente più bonus in monete (i premi sono **solo estetici**): oggetti del profilo a 7, 14, 30, 60, 100 giorni (non si comprano).
  Regola delle **36 ore**: la serie sale se la riscossione arriva entro 36 ore dall'ultima, altrimenti riparte da 1. **Protezione
  comprabile:** lo scudo costa 150 monete, se ne tengono al massimo 2, ognuno copre un giorno saltato (24 ore) e si consuma solo se
  basta a salvare la serie. **Promemoria a 20 ore:** messaggio privato, *solo per chi lo accende* nella sezione Serie, una volta per
  riscossione. Poiché il `/level daily` ha l'attesa di 24 ore, a 20 ore il messaggio dice «tra circa N ore puoi riscuotere» e quanto
  resta prima di perdere la serie.
- **Pass di 90 giorni, 50 livelli:** stagioni fisse di 90 giorni dal 1/1/2026 (chiave «AAAA-MM» dell'inizio). Gli XP del pass si contano
  a parte (nuova colonna), non dalla classifica mensile, per rispettare i 90 giorni esatti. 500 XP a livello. Traccia libera: 10 + 2n
  monete a livello. **Traccia premium:** 20 + 4n monete e oggetti estetici ai livelli 10, 25 e 50; si apre con il **boost** del server
  (gratis) o con **500.000 monete** (come da richiesta, una volta per stagione). I livelli già fatti si pagano anche sulla traccia
  premium dopo l'apertura.
- **Traguardi:** per categoria (Livello, Serie, Missioni, Pass, Segreti) e **nascosti** (scudo, settimana piena, missione del server,
  traccia premium): compaiono solo quando si ottengono; prima si dice quanti restano.
- **Carico dello staff:** `/mod carico` richiede il livello **ADMIN** (decisione dell'owner), risposta privata, mai classifica. Mostra casi,
  appelli, ticket, tempo medio alla prima risposta, ticket riaperti (colonna `tickets.riaperto_volte`, 0482), sanzioni proprie annullate
  in appello, voto medio dei ticket e una **proposta di turni** (4 fasce di 6 ore UTC, le due persone più attive; avviso sulle fasce scoperte).
- **Vista forum (8.17):** un post archiviato o bloccato si riapre; se non si riapre si dimentica e se ne crea uno nuovo; un forum con
  tag obbligatori riceve il primo tag non riservato; dopo un rifiuto la vista di quel forum si ferma 10 minuti con un solo avviso nei log.

Tabelle: 0483 (colonne di `progress_serie` e `progress_stagione`, nuova `progress_server_riscatti`, tutte nel registro dei dati); 0484 dà alle serie di prima (solo il giorno) l'ora di mezzogiorno UTC, così non si azzerano.
## D52 — Scelte dell'owner per l'AI, bozze di codice, processo separato (01/11/2026)

`/ai modello` (solo owner, dentro `/ai` perché `/owner` è pieno) cambia a caldo modello, fascia e tipi di ogni fornitore
e il tetto di lunghezza delle risposte; le scelte stanno in `ai_globale` (migrazione 0428) sopra il `.env` e passano da
un solo punto (`imposta_scelte_owner`). Audio: serve il motore della voce (D44), senza quota; musica e video restano
accettati nella configurazione ma senza trasporto, perché non c'è un servizio adatto al costo che l'owner accetta.
Le bozze di codice (AI-R-107) partono solo da richieste già approvate dall'owner e non si uniscono mai da sole.
Il processo AI separato (25.21) è `[✗]`: era una proposta, non una richiesta dell'owner; con la coda di 25.22 le misure
non lo chiedono, e un secondo processo duplicherebbe pool, cache e quote su una macchina da 2 CPU.

## D53 — Paese dell'account nella verifica, contro i raid (01/11/2026, richiesta dell'owner)
L'owner vuole sapere almeno il **paese** di chi entra (non la città): in un raid gli
account arrivano quasi sempre da un paese diverso da quello del server.
- Il server dichiara il suo paese (o più paesi) nelle impostazioni della verifica.
- Il paese si ricava dall'IP **solo** durante la verifica web, con una banca dati
  locale (nessun servizio esterno). Si salva solo il codice del paese (es. `IT`),
  mai l'IP in chiaro, mai la città. Segnale debole in più: la lingua del client
  Discord (`interaction.locale`), che non richiede IP.
- Se in poco tempo arrivano molte verifiche da paesi diversi da quelli del server
  (soglia configurabile), il bot mette le entrate in attesa e avvisa gli admin, che
  approvano o rifiutano. Non blocca mai da solo per il paese: è un indizio (come D50).
- Privacy: dato minimo, scritto nell'informativa, cancellato con `/privacy`;
  registrato nel data registry. Sostituisce il `[✗]` "ISP / localizzazione" per la
  parte paese; ISP e città restano non raccolti.

## D54 — File dedicato con i servizi AI gratuiti (01/11/2026, richiesta dell'owner)
Niente processo AI separato (25.21 resta `[✗]`, confermato dall'owner). Serve invece
un file dedicato (`config/ai_fornitori.env.example`) con tutti i servizi AI che hanno
un livello gratuito (grandi aziende, aziende cinesi e altri): indirizzo, modelli,
tipi di lavoro, limiti al minuto e al giorno, se addestrano sui dati (D19). L'owner
mette solo la chiave. Il router sceglie il servizio per tipo di lavoro e quota rimasta.
Le chiavi a pagamento restano spente finché non le pagano gli abbonamenti premium.

## D57 — Livelli di abbonamento scelti dal pannello, per funzione (01/11/2026, richiesta dell'owner)
All'avvio tutto il bot è gratuito per tutti. Più avanti l'owner sceglie dal pannello web,
funzione per funzione, il livello: gratuito, premium, VIP 5 o VIP 20 (es. AI a pagamento:
servizi economici su VIP 5, servizi costosi su VIP 20).
- Un solo punto del codice legge il livello di ogni funzione (D16), usato da comandi e pannello.
- Il bot mostra da solo i comandi per livello: `/premium` elenca i comandi premium,
  `/vip` quelli di VIP 5 e VIP 20, aggiornati quando l'owner cambia il pannello, senza riavvio.
- Si predispone ora (livello di default = gratuito per tutto), si attiva con il pannello.
- I comandi premium/VIP restano nel loro gruppo (`/music`, `/ai`, …): il livello si controlla quando il
  comando parte (un solo punto, `core/livelli_funzione.py`), con un messaggio chiaro se manca.
- `/premium` e `/vip` sono gruppi con pochi sotto-comandi fissi (`elenco` con `area` a completamento, `info`):
  l'elenco è a pagine (embed entro i limiti, bottoni, menu di al massimo 25 voci) e si costruisce dalla
  tabella `livelli_funzione`. Con 30, 100 o 665 funzioni l'albero non cambia (limiti di 25 figli e 8.000
  caratteri mai toccati). Si registra o si toglie solo il gruppo intero (nessuna funzione premium/VIP:
  nessun gruppo), con una sola sincronizzazione per cambio e attesa minima.

## D58 — Bot multilingue: una cartella per lingua, comandi tradotti, richiesta di lingue nuove (01/11/2026, richiesta dell'owner)
Lingue di partenza: le stesse del sito (repo iYokai-Site, `src/i18n`): it, en, de, es-ES, fr,
ja, ko, ru, uk, zh-CN. Tutte sono tra le lingue che Discord supporta per i nomi dei comandi.
- Struttura: `locales/<lingua>/testi.json` (risposte, embed, finestre, bottoni) e
  `locales/<lingua>/comandi.json` (nome, descrizione, opzioni, scelte di ogni comando, più
  la spiegazione lunga per `/info` e `/cerca-comando`). L'owner corregge una lingua aprendo
  solo il suo file. Ripiego: lingua → en → it. Un controllo segna le chiavi mancanti o
  uguali all'italiano ("da tradurre") per ogni lingua.
- Comandi nella lingua di chi scrive: si usano le localizzazioni native di Discord
  (`name_localizations`, `description_localizations`). L'utente vede e scrive il comando
  nella sua lingua; al bot arriva sempre il nome base, quindi il comando parte uguale.
  Vincoli: nome 1-32 caratteri, regola dei caratteri di Discord, nomi delle opzioni unici
  per lingua; per il tetto di 8.000 caratteri conta, campo per campo, la versione più lunga
  tra tutte le lingue: un test lo controlla con margine (D25/D56).
- `/info` e `/cerca-comando` leggono la spiegazione dal file della lingua dell'utente; la
  ricerca in linguaggio naturale funziona in ogni lingua (parole chiave per lingua + AI se
  accesa) e propone i comandi con un menu.
- Lingua mancante: l'utente apre un modulo "richiedi una lingua"; la richiesta va all'owner;
  approvata, uno script crea `locales/<lingua>/` con tutte le chiavi da tradurre. Per le
  lingue che Discord non supporta nei nomi dei comandi si traducono solo i testi.
- Traduzione: uno script usa i servizi AI configurati (D54) per riempire le chiavi mancanti,
  segnandole "da rivedere"; i test controllano segnaposto, lunghezze e regole di Discord.
- Ordine: dopo il riordino dei comandi (D56), per non tradurre due volte i nomi.
## D55 — Ammessi anche i servizi AI che addestrano, solo come ripiego (01/11/2026, decisione dell'owner)
L'owner ammette anche i servizi che nel livello gratuito addestrano sui dati: iYokai non addestra
niente e non manda alla AI ogni messaggio, solo le richieste delle funzioni. La protezione resta:
- `AI_ADDESTRA_<NOME>=si` non scarta più il fornitore, lo segna «addestra»; senza `no` o `si` si scarta.
- Il router mette **sempre** prima chi non addestra; chi addestra serve solo se gli altri mancano o sono senza quota.
- Server con privacy AI «senza_messaggi»: chi addestra non riceve mai nulla di quel server.
- `AI_AMMETTI_ADDESTRANO=si|no` (iniziale: `si`) li spegne tutti in un colpo, utile alla revisione di Discord.
- D19 resta valida: iYokai non addestra modelli. Aggiornata con un rimando a D55.

## D56 — Gruppi per tema e per chi li usa; tetto di 60 comandi di primo livello (01/11/2026, richiesta dell'owner)

Aggiorna D25. Un gruppo di primo livello nuovo si può creare **per tema** o **per
pubblico**, non solo quando un gruppo supera i 6.800 caratteri. Regole:

1. Un gruppo è **per tutti** (nessun permesso predefinito) **o per lo staff**
   (permesso predefinito e livello). Un comando che chiede il livello admin, mod o
   sicurezza non sta in un gruppo per tutti. I comandi solo per l'owner del bot (OWNER_ID, non il founder di un server) stanno
   in `/owner`, divisi in sotto-gruppi per area (`/owner ai`, `/owner premium`, …); `/owner` si
   registra solo nel server dell'owner e ogni comando controlla OWNER_ID. L'uso normale
   dell'AI resta in `/ai`; chiavi, modelli, quote e parametri globali vanno in `/owner ai`.
2. Tetto: **60 comandi di primo livello globali** (Discord ne ammette 100). I 40 posti
   restano liberi per le esigenze future. Oggi 33.
3. Ogni gruppo e sotto-gruppo punta a **18 figli** (Discord: 25). Sopra i 18 si
   divide in sotto-gruppi; sopra i 25 non si va mai.
4. Peso: il limite vero è **8.000 caratteri** per gruppo (Discord). A 6.800 scatta solo un
   **avviso** (non un tetto): si può arrivare fino a 8.000, cercando di restarci sotto con
   margine per le traduzioni (D58). Vicino a 8.000 si sposta un blocco intero in un gruppo nuovo.
5. Profondità massima 3: gruppo, sotto-gruppo, comando.
6. Nomi italiani brevi, la parola d'uso dove esiste (`gif`, `giveaway`). I gruppi
   staff di un'area per tutti hanno il nome dell'area col trattino (`ticket-gestione`).
7. Un elenco che cresce (GIF, giochi, filtri, effetti) è un'opzione a completamento,
   non un comando per voce.
8. Ogni gruppo nuovo passa dal `guardiano-limiti` e ha la sua riga in
   `MAPPA_COMANDI_F7.md` §5.

Primo uso (riordino del 01/11/2026): nascono `/immagini`, `/giochi`, `/sondaggi`,
`/assistente`, `/monete`, `/gif` (per tutti) e `/messaggi`, `/giveaway`,
`/ticket-gestione`, `/ticket-pannelli`, `/filtri` (staff, `manage_guild`, livello
admin). 152 comandi cambiano percorso; i comandi spenti nella politica dei server
seguono il nome nuovo. Già approvato per dopo: se `/economia` supera 6.800, il blocco
`economia livelli` diventa il gruppo `/xp`.
Il quinto caso di D25 (`/gestione ruoli` resta dov'è) è superato: tutto sui ruoli sta in `/ruoli`.
In più (D57): nascono `/premium` e `/vip`, per tutti, che elencano i comandi del loro livello (solo quando serve).
Visibilità (01/11/2026, owner): ogni gruppo ha il permesso predefinito del suo livello (per tutti: nessuno;
mod: `moderate_members`, o `kick`/`ban` se più adatto; admin: `manage_guild`; `/owner` solo nel server
dell'owner con controllo di OWNER_ID), così Discord nasconde da solo i comandi a chi non li può usare.
Discord applica i permessi solo al primo livello: per questo un gruppo non mescola utenti e staff (un test
lo controlla). Lo staff «whitelistato» senza quei permessi li vedrà con l'aggiornamento dei permessi dal
pannello (OAuth `applications.commands.permissions.update`): si farà col pannello.

## D59 — Livelli: Gratuito, Premium, Ultra, VIP e chiave propria (01/11/2026, richiesta dell'owner)
Aggiorna D57 (VIP 5 diventa **Ultra**, VIP 20 diventa **VIP**). All'avvio tutto è gratuito, AI gratuite comprese.
- **Premium:** abbonamento mensile o annuale, lifetime a prezzo concordato con l'owner, oppure boost Nitro di
  uno dei due server indicati dall'owner. Sblocca i moduli che l'owner segna come premium.
- **Ultra (5 €):** crea un fondo per crediti a consumo sui servizi AI economici; più quota AI.
- **VIP (20 €):** accesso ai modelli grandi (servizi a pagamento dei big), con la quota divisa fra 3-4 servizi
  (es. 30 % ciascuno), mai il 100 % della spesa del livello.
- **Chiave propria:** un utente o un server che mette la sua chiave API ottiene il livello VIP per sé e per il suo
  server, con il 100 % dei suoi crediti. La chiave si salva cifrata, si usa solo per chi l'ha messa, non va mai nei
  log, si toglie con un comando o dal pannello. Valgono D19 e D55.
- Un solo punto decide il livello di un server o di un utente (fonti: abbonamento, boost, lifetime, chiave propria)
  e un solo punto decide il livello di ogni funzione (D57): issue #151.
- Il router AI sceglie i servizi permessi dal livello (gratuiti per tutti; a consumo da Ultra; grandi da VIP o con
  chiave propria) e tiene il conto della spesa per livello (D13).

## D60 — Comandi dello staff sotto il loro ruolo: prefisso nel nome del gruppo (01/11/2026, richiesta dell'owner)
L'owner vuole trovare i comandi dello staff «a un clic», sotto il ruolo: `/admin <modulo> <sottocategoria>`. Un solo
`/admin` non entra nei limiti di Discord (8.000 caratteri e 25 figli per comando; lo staff pesava circa 69.600).
Alternativa più vicina (D18): il **ruolo diventa il prefisso del nome del gruppo**. Discord filtra per l'inizio del
nome: scrivendo `/admin` compaiono tutti i gruppi `admin-…`.
1. Gruppi admin: `/admin-<modulo>` (es. `/admin-ticket pannelli crea`). Gruppi mod: `/mod-<modulo>`. Proprietario del
   server: un solo gruppo `/founder <modulo> <azione>`. Owner del bot: `/owner` (D56, invariato).
2. I gruppi per tutti non hanno prefisso (`/ticket apri`, `/music play`) e nessun loro nome inizia con `admin`, `mod`
   o `founder` (un test lo controlla). Per questo `/moduli` diventa `/admin-moduli` e `/modban` diventa `/mod-ban`.
3. Il prefisso non si traduce (D58): in ogni lingua `admin-`, `mod-`, `founder`. Si traduce solo il resto.
4. Permessi predefiniti: `admin-` `manage_guild` (eccezioni scritte: `admin-sicurezza`,
   `admin-antinuke`, `admin-antiraid`, `admin-backup` `administrator`); `mod-` `moderate_members` (`mod-ban`:
   `ban_members`); `founder` `administrator`.
5. **Founder** = `guild.owner_id` (Discord lo dichiara). `Livello.FOUNDER` fa passare solo lui: non l'owner del bot,
   non il ruolo admin del bot. Gli altri amministratori vedono `/founder` perché Discord fa usare tutto a chi ha
   `administrator`, ma il codice li rifiuta. Col pannello (OAuth `applications.commands.permissions.update`) si potrà
   nascondere `/founder` a tutti tranne al proprietario: si farà col pannello.
6. Valgono le regole D56 (≤ 60 globali, 18 figli, avviso 6.800, profondità 3). Aggiorna D56 punto 6: i gruppi staff
   si chiamano `<ruolo>-<modulo>`, non più `<area>-gestione`. Nessun testo di Discord supera 100 caratteri; se un
   gruppo supera 6.800 si accorciano le descrizioni delle opzioni (le spiegazioni lunghe vanno nell'aiuto di `/info`).
7. Politica dei comandi: il gruppo `admin-bot` resta sempre acceso (altrimenti un admin spegne la politica stessa);
   gli altri `admin-…` si possono spegnere.
8. Primo uso: 25 gruppi staff (20 `admin-`, 4 `mod-`, `/founder`) al posto di 19; 377 comandi cambiano percorso; i
   comandi spenti nella politica seguono il nome nuovo (migrazione 0488). Comandi globali 39 (43 con `/gif`,
   `/premium`, `/ultra`, `/vip`). Le eccezioni messe dagli admin in Impostazioni → Integrazioni si perdono (gli ID
   dei gruppi sono nuovi): si annuncia prima con `/owner system announce`. `/cerca-comando` trova anche i nomi vecchi.

## D61 — Copia sicura delle immagini nei log e nei backup (01/11/2026, richiesta dell'owner)
Le immagini degli utenti sono il punto d'ingresso più comune per gli attacchi (decoder bucati, file
travestiti). Regole per log, backup e pannello:
- Si salvano **i byte così come arrivano**, senza aprirli con Pillow: nessun decoder tocca un file solo
  per conservarlo. Nome casuale, impronta SHA-256, tetto di dimensione, tipo riconosciuto dai primi byte
  e solo da un elenco chiuso (PNG, JPEG, GIF, WEBP); il resto si salva come file generico.
- Le anteprime si fanno solo con `safe_open_image` (formati chiusi, tetto di pixel) in un processo a
  parte con limiti di memoria e di tempo, e si **ricodificano** in PNG (spariscono metadati e contenuto nascosto).
- Il pannello e il sito non mostrano mai il file originale in linea: download con
  `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy: sandbox`,
  da un sotto-dominio separato senza cookie di sessione. Mai SVG o HTML caricati dagli utenti in linea.
- Cartella fuori dalla radice del sito; conservazione a tempo e cancellazione con `/privacy` (data registry).
- Aggiornamenti di sicurezza delle librerie (Pillow, aiohttp, …) si applicano subito, senza aspettare il giro.

## D62 — Difesa dalle immagini trappola e dalle truffe a tema giveaway (01/11/2026, richiesta dell'owner)
L'owner ha subito il furto degli account collegati subito dopo aver copiato un'immagine ricevuta su Discord.
Il client di Discord (Electron/Chromium) decodifica l'immagine anche per copiarla: un file costruito apposta
può sfruttare un difetto del decoder (precedente reale: libwebp, CVE-2023-4863). Il bot non può correggere il
client, ma può fermare il file prima che lo aprano i membri:
- **Filtro immagini sospette (AutoMod):** ogni allegato immagine si controlla in un processo a parte, senza
  mostrarlo: tipo vero dai primi byte contro l'estensione, dati in coda dopo la fine dell'immagine (file
  "poliglotti"), blocchi o metadati anomali, dimensioni dichiarate assurde, decodifica di prova con
  `safe_open_image` e limiti. Se è sospetto: il messaggio si cancella, l'autore riceve un avviso, lo staff un log
  (senza ripubblicare il file).
- **Libreria delle immagini trappola:** impronta (SHA-256 e impronta percettiva) delle immagini segnalate; come
  D39, 3 owner diversi la rendono condivisa, l'owner del bot la rende certa. Un'immagine certa si blocca ovunque.
- **QR e truffe giveaway:** i QR code nelle immagini si leggono; un link verso login, regali Nitro o giveaway
  falsi si blocca. Parole e schemi delle truffe note (es. finti giveaway di personaggi famosi) entrano nel
  filtro truffe, multilingue.
- **Account rubati che spammano:** spam-trap e anti-raid già attivi; in più il primo messaggio con immagine
  sospetta di un account mette l'utente in timeout e avvisa lo staff.
- **Percorso unico per ogni immagine scaricata dal bot (log, backup, ticket, filtro):** 1) i byte vanno in una
  **cartella di quarantena** sul server, fuori dal sito, mai aperti dal processo del bot; 2) l'analisi gira in una
  **sandbox**: processo separato, utente di sistema senza permessi, niente rete, sola lettura sulla quarantena,
  tetti di memoria e di tempo; 3) se l'immagine è pulita, nei log va **una copia ricodificata** (PNG nuovo fatto
  nella sandbox: è la "foto" dell'immagine, senza il file originale), mai l'originale; 4) se è sospetta o
  malevola, nei log va solo l'avviso "immagine con contenuto malevolo" con autore, canale, impronta e motivo,
  senza file; l'originale resta in quarantena per il tempo minimo e poi si cancella. Vale anche D61.
- Precisazione dell'owner (01/11): `/admin-ruoli` di base chiede «Gestisci server» come gli altri gruppi admin;
  ogni server può dare l'accesso a chi gestisce i ruoli dalle Integrazioni di Discord.
- Nomi `/cerca-comando` e `/chiedi` (scelta dell'owner 01/11): niente trattino iniziale. La doppia `/` non è
  ammessa da Discord (nei nomi solo lettere, numeri, `-`, `_`). Migrazione 0491 per i percorsi salvati.

## D63 — Blocco AutoMod del catalogo: regole con condizioni e azioni (01/11/2026, scelta di chi sviluppa)
Disegno: tabella `automod_regole` (filtro o regola personale; evento, condizioni, azioni, contatore in JSONB),
`automod_liste`; un solo modulo per eseguire le azioni (`core/automod_azioni.py`); 7 comandi nuovi solo in
`/admin-automod` (regole, liste, riepilogo, azzera, gruppo, pulizia, immagini) con editor a pannello.
Le regex dei server girano solo con `re2`. Un'azione che fallisce per permessi si sospende per 10 minuti.
AMD-018 (stato online e attività) richiede l'intent Presenze: si fa dietro un interruttore **spento di base**;
finché è spento il bot non chiede l'intent a Discord. Filtro immagini (D62): un processo nuovo per immagine,
servizio di sistema `iyokai-sandbox` con utente senza permessi e senza rete; ripiego dichiarato se manca.
Correzione (02/11/2026, orchestratore): il filtro immagini trappola vale per **tutti**, staff, proprietario e canali o
ruoli esenti compresi (un account staff rubato è il caso tipico); le esenzioni AutoMod non valgono qui. Azione uguale:
cancella, avviso e log; timeout se l'immagine è malevola.

## D64 — Verifica web: VPN e proxy bloccati subito (01/11/2026, richiesta dell'owner)
Durante la verifica web, chi arriva da una VPN o da un proxy (pubblico o privato, anche Tor e reti di data center)
viene **bloccato subito**, senza una prima volta concessa. La pagina gli dice di spegnere VPN o proxy e riprovare.
Gli admin ricevono un avviso: «<utente> ha provato a verificarsi con VPN/proxy rilevato ed è stato bloccato».
- Rilevazione a strati, prima locale: elenchi di reti di data center/hosting per ASN (banca dati ASN locale),
  elenchi pubblici di VPN e proxy, nodi di uscita Tor (elenco ufficiale), intestazioni di proxy nella richiesta
  (Via, Forwarded, X-Forwarded-For dal client), fuso orario del browser diverso dal paese dell'IP.
  Poi, se l'owner mette una chiave, un servizio esterno di controllo (es. proxycheck.io, IPQualityScore,
  vpnapi.io) con cache e tetti giornalieri.
- Nessun metodo è perfetto: proxy residenziali e alcune VPN private possono passare; reti aziendali, CGNAT
  mobili e iCloud Private Relay possono sembrare proxy. Per questo l'avviso agli admin ha un bottone «Lascia
  passare» per i casi sbagliati, e il server può spegnere la regola (di base è accesa).
- Privacy: l'IP si usa solo in quel momento; si salva solo "VPN/proxy: sì", il metodo e la data (D53, D19).
  L'uso di un servizio esterno va scritto nell'informativa.

## D65 — Blocchi della verifica: ticket in privato e storico condiviso dei falsi positivi (02/11/2026, richiesta dell'owner)
- **Ogni blocco** durante la verifica (VPN/proxy D64, paese D53, account doppio, captcha, qualsiasi motivo) dice
  all'utente di scrivere in privato al bot: il messaggio apre un ticket (ModMail) con lo staff del server dove
  voleva entrare, con il motivo del blocco già allegato.
- **Storico condiviso:** quando lo staff di un server lascia passare un utente segnalato (es. iCloud Private Relay
  scambiato per VPN), il bot lo ricorda. Negli altri server con iYokai quella persona passa la verifica, ma gli
  admin ricevono un avviso: «già accettato da N server nonostante VPN/proxy rilevato: può usarla anche per altro»,
  con lo storico (date, motivi, esito). Gli admin hanno così un elenco di avvisi su queste persone.
- **Privacy (scelta di chi sviluppa):** di base l'avviso dice **quanti** server l'hanno accettato, non quali,
  perché i nomi rivelerebbero gli altri server di quella persona. Un server può scegliere di farsi nominare negli
  avvisi degli altri (consenso del server). Lo storico si cancella con `/privacy` e scade (data registry).
- Precisazione dell'owner (02/11): l'owner del bot (OWNER_ID) vede sempre anche i **nomi** dei server nello
  storico, con un comando in `/owner` (sotto-gruppo adatto, es. `/owner privacy` o `/owner verifica`) e nel pannello
  owner. Gli admin dei server vedono il numero, i nomi solo dei server che lo consentono.

## D66 — Blocchi Moderazione (#115) e Ticket (#120): scelte di base (02/11/2026, scelta di chi sviluppa, da confermare all'owner)
Disegno: scratchpad `disegno_mod_ticket.md` (guardiano). Nessun gruppo nuovo; menu col tasto destro: «Segnala
messaggio», «Apri ticket», «Scheda moderazione». Scelte prese secondo la raccomandazione del guardiano:
clear fino a 1.000 messaggi (al massimo 100 più vecchi di 14 giorni); motivo obbligatorio di base (il server può
renderlo facoltativo); l'utente vede le sue sanzioni (acceso, senza note e casi nascosti); moderazione anonima
spenta; prove non immagine (PDF, TXT) conservate grezze, mai aperte, solo dal pannello, 180 giorni; scadenza casi
AutoMod 0 (mai, il server sceglie); ZIP dei ticket solo con immagini ricodificate; Google Drive più avanti con OAuth
dal pannello, ora archivio interno + canale archivio (D18); Bloxlink con chiave per server cifrata; ticket a thread
come opzione (issue a parte); dehoist automatico spento.

## D67 — Storico condiviso più severo, IP solo per l'owner, account rubati (02/11/2026, richiesta dell'owner)
Aggiorna D64/D65.
- **«Lascia passare» condiviso:** vale negli altri server solo se nello storico ci sono **almeno 3 approvazioni**
  di server diversi, date in **momenti diversi** (non nella stessa ora), da server con **founder diversi** e da
  **admin diversi** (chi ha premuto il bottone). Sotto la soglia vale solo nel server che l'ha dato.
- **IP:** si salvano (cifrati) per sicurezza e li vede **solo l'owner del bot** (`/owner`, pannello owner), mai gli
  admin dei server, mai nei log. Cancellazione: su richiesta con `/privacy`, oppure 30 giorni dopo che il server
  viene eliminato o che la persona esce dal server. Dopo un **kick o un ban** i dati **restano**.
  Nota di chi sviluppa: per il GDPR conviene un tetto anche per i ban (es. finché il ban è attivo e 30 giorni dopo
  lo sblocco) e una richiesta `/privacy` di chi è bannato si gestisce a mano (interesse legittimo di sicurezza).
- **Invito al ticket in privato:** obbligatorio per **ogni** blocco della verifica, anche captcha e bottone su
  Discord, non solo la verifica web.
- **Account rubato (truffe tipo finti giveaway):** di solito spamma messaggi inoltrati, uguali, ovunque. Il bot:
  1) **un solo avviso riassuntivo** per persona: «account probabilmente compromesso, immagini malevole, N invii in
  M canali», senza allegare né ricodificare le immagini (niente log da 100 righe, niente banda sprecata);
  2) **limita subito** la persona (timeout di Discord: è Discord stesso a mostrarle il blocco quando prova a
  scrivere) e cancella ciò che riesce a mandare;
  3) le manda in privato: «Sei stato limitato da iYokai per una presunta violazione del tuo account: cambia la
  password, attiva l'autenticazione a due fattori, controlla le app autorizzate; poi scrivimi qui»; il messaggio in
  privato apre il ticket con lo staff dei server dove è stata limitata.
  Limite di Discord: un bot non può mostrare un errore a schermo con testo suo su un messaggio normale; la cosa più
  vicina è il timeout di Discord (avviso di sistema) + il messaggio privato con le istruzioni (D18).
- **Tetti scelti da chi sviluppa per la parte IP (02/11/2026, r16verifica, da confermare all'owner):** persona che
  esce o bot tolto dal server 30 giorni; **kick 180 giorni**; **ban finché è attivo e 30 giorni dopo lo sblocco**; tetto
  assoluto 365 giorni dall'ultimo uso; al massimo 20 IP per persona e server. `/utility privacy cancella` non toglie le
  righe di chi è bannato o espulso (si valuta a mano). Chiave: `VERIFY_IP_ENCRYPTION_KEY` (senza chiave non si salva).
  La soglia dello storico: «momenti diversi» = almeno un'ora fra due approvazioni qualsiasi del gruppo.
- **Comportamento esatto delle scadenze IP (revisione r16verifica, 08/11/2026).** Coerente con D67: dopo kick e ban
  i dati restano; i tetti sono quelli sopra. Ordine di precedenza: (1) **ban attivo**: nessuna scadenza, il tetto dei
  365 giorni NON lo tocca; un'uscita o un kick dopo il ban non lo cambiano; (2) **sblocco**: 30 giorni; (3) **kick**
  (dal registro azioni di Discord, entro 30 secondi; senza permesso vale come uscita): 180 giorni, un'uscita dopo non
  lo accorcia, un rientro non lo toglie; (4) **uscita**: 30 giorni; rientro o nuova verifica web la tolgono;
  (5) persona presente: tetto di 365 giorni dall'ultima verifica; (6) **bot fuori dal server** da 30 giorni
  (`guild_presence.left_at`, lo stesso conto dei 90 giorni, rimesso a posto all'avvio): via tutte le righe del
  server, ban compresi; il rientro del bot non allunga nessuna scadenza. Eventi persi a bot spento: vale il tetto di
  365 giorni (un ban dato a bot spento non è visto). `/utility privacy cancella`: via tutte le righe tranne `ban` e
  `kick`. Esportazione `/privacy` della persona: server, esito, date, motivo e scadenza, **non** l'IP (né in
  chiaro né cifrato): il diritto di accesso all'IP stesso (GDPR art. 15) si soddisfa a mano dall'owner con
  `/owner system storico-vpn`. Nessun'altra via mostra l'IP agli admin.
- **Falsi positivi dell'account rubato (revisione r17automod, 08/11/2026, scelta di chi revisiona):** nessuna esenzione
  dello staff, ma chi ha «Gestisci messaggi» nel canale va limitato solo con lo stesso messaggio in **5** canali (un
  annuncio in 3 canali è normale); i **canali annunci** e i loro thread non contano (le immagini malevole sì); un testo
  senza link né @everyone conta solo da **40** caratteri («buongiorno a tutti» in tre canali non è spam), con un link
  o un inoltro da 12. Bot e webhook (anche i crosspost dei canali seguiti) non contano mai.
- **Ticket dopo la limitazione in più server (revisione r17automod, 08/11/2026):** un blocco per persona **e per server**
  (migrazione 0531). Il ModMail tiene una sola conversazione aperta per persona (un DM va a un canale solo), quindi:
  un server → il ticket si apre subito col motivo; più server → menu (≤ 25) per scegliere lo staff; gli altri restano
  e il messaggio dopo la chiusura apre il prossimo (validità 24 ore, poi il ModMail normale).
- Precisazione dell'owner (08/11): IP dopo un **kick 180 giorni**, dopo un **ban 1 anno** dal ban (lo sblocco non lo
  cambia). **IP, e-mail e numeri di telefono** dell'account si danno a terzi **solo su richiesta di un giudice** e solo per
  la persona indicata; tutto il resto si dà su richiesta con `/privacy`. Nota di chi sviluppa (GDPR art. 15): la persona
  stessa ha diritto ai propri dati, IP compreso; si danno solo a lei, dopo aver verificato che è lei (login Discord dal
  pannello), mai ad altri senza ordine del giudice.

## D68 — Motivi pronti con severità e sanzione di base (08/11/2026, richiesta dell'owner)
I motivi pronti delle sanzioni (`/mod-casi motivi`) hanno anche una **severità** (lieve, media, grave, gravissima) e
una **sanzione con durata** (es. «Spam» → timeout 1 ora). Il bot porta un elenco **preimpostato** per severità, uguale
per tutti i server all'inizio (es. lieve: warn; media: timeout 1 h; grave: timeout 24 h o kick; gravissima: ban);
ogni server può cambiare, togliere o aggiungere motivi. Scegliendo un motivo pronto il bot propone quella sanzione e
quella durata, che lo staff può cambiare prima di confermare.

## D69 — Blocco Utility (#128): scelte di base (09/11/2026, raccomandazioni del guardiano, da confermare all'owner)
Disegno: scratchpad `disegno_utility.md` (28 blocchi B1–B28, migrazioni 0540–0563). Scelte: 7 gruppi nuovi
(`/web`, `/tag`, `/eventi`, `/admin-tag`, `/admin-automazioni`, `/admin-inviti`, `/admin-giochi`; radici 47 su 60);
cambi di percorso con migrazione della politica e annuncio; tag creati da un ruolo scelto dal server (di base solo
staff); meteo MET Norway + Nominatim (Open-Meteo vieta l'uso commerciale); film Wikipedia + TVmaze (TMDB solo con
chiave); prezzi cripto CoinGecko con chiave dell'owner (col Premium: piano pagato o chiave propria, D59);
accorciatore is.gd spento di base con controllo phishing; correzione dei link spenta di base; risposte globali
dell'owner spegnibili dal server (max 20); eventi creati da chi ha `create_events`; pesi dei sondaggi per ruolo;
autore dei suggerimenti anonimi visibile solo agli admin, con registro; script dei tag in linguaggio nostro (italiano
+ alias inglesi, niente Jinja); il menu degli eventi dei log va diviso prima di aggiungere voci (25/25).

## D70 — Divertimento (#131): fonti delle GIF e servizi dei giochi (09/11/2026, scelta dell'owner)
- Le GIF di reazione e azione restano **gratuite per tutti** (mai nel Premium). Si predispongono **tutte** le fonti:
  nekos.best, waifu.pics, otakugifs, Giphy, Klipy e le altre gratuite trovate, ognuna con un interruttore dell'owner;
  poi si tiene chi funziona meglio. Nota di chi sviluppa: alcuni termini (es. nekos.best) vietano l'«uso commerciale»
  e un bot con abbonamenti potrebbe contare come commerciale anche se le GIF sono gratis: il rischio lo valuta l'owner,
  per questo ogni fonte si spegne con un interruttore senza toccare il codice. Giphy e Klipy: serve il loro permesso
  scritto per un bot; la richiesta la manda l'owner (testo pronto in docs).
- **Giochi:** si predispongono i servizi utili ai giochi più diffusi e ai tripla A 2020–2027 (statistiche, profili,
  stato dei server, notizie e patch, giochi gratis della settimana), in un file dedicato con le chiavi da incollare
  (come D54). Ogni servizio si accende solo con la sua chiave; chi richiede un'approvazione (es. Riot) resta spento
  finché l'owner non l'ottiene. Filtro NSFW sempre attivo fuori dai canali NSFW.
- Altre scelte del disegno (DF2–DF10) come raccomandato: telefono per ultimo e spento di base, pacchetto carte
  «adulti» spento, chiavi osu!/Fortnite dell'owner.
- Precisazione dell'owner (09/11): le fonti **NSFW** (GIF e immagini per adulti, es. Rule34, endpoint NSFW di
  waifu.im/nekos e simili) stanno in un elenco **separato**, usato solo dal bot NSFW e solo nei canali con limite
  d'età. Regola fissa di chi sviluppa, non spegnibile: elenco di tag vietati che esclude **sempre** qualsiasi
  contenuto con minori o che li richiami (es. loli, shota, child e simili, in tutte le lingue), più gore estremo e
  non consensuale; una ricerca con un tag vietato non parte. È un obbligo di legge (in Italia anche la pornografia
  «virtuale» con minori è reato) e delle regole di Discord.

## D71 — Livelli (#124): scelte aperte del catalogo (09/11/2026, opzione consigliata, da confermare dall'owner)

- Voto al bot (LIV-019): codice pronto per top.gg (webhook con segreto in `.env`), spento finché iYokai non è sull'elenco.
- Premium (D59): solo 042, 044 a ogni ora e 072 (import da altri bot). Tutto il resto gratuito; spostabile dal pannello.
- Reputazione: spenta di base. Dare punti: tutti. Togliere punti: solo il ruolo scelto dall'admin.
- XP testo e vocale separati: il passato resta nel totale; le due nuove classifiche partono da zero.
- LIV-088 coperta da LIV-082: una sola classifica, nessun doppione.
- Peso di `/admin-livelli` misurato in B1: 3.729, nessun sotto-gruppo serve.

## D72 — Economia (#125): scelte aperte del catalogo (10/11/2026, opzione consigliata, da confermare dall'owner)

- Monete solo virtuali: nessun gioco d'azzardo con denaro vero, nessun acquisto di monete con denaro, nessun cambio in denaro.
- Voto al bot (048/049): come D71, codice pronto per top.gg, spento finché iYokai non è su un elenco.
- Interessi del deposito e premi degli eventi: pagati dalla cassa del server, mai creati dal nulla.
- Premium: solo 050 e 037; il resto gratuito, spostabile dal pannello.
- Banca nuova: i saldi già esistenti restano contanti.
- Oggetti donati al fondo premi (120): convertiti in credito e tolti dall'inventario.
- Se `/admin-economia` supera 6.800: prima il sotto-gruppo `negozio`, poi la radice `/admin-eventi`.

## D73 — Musica (#126): fonti e albero (10/11/2026; Spotify chiesto dall'owner, il resto opzione consigliata, da confermare)

- Spotify, Apple Music, Tidal e Deezer: solo metadati (LavaSrc); l'audio si cerca su un'altra fonte (ISRC, poi titolo). Mai la masterDecryptionKey né il cookie arl di Deezer.
- YouTube solo tramite il plugin di Lavalink; SoundCloud, Bandcamp, Twitch, Vimeo, link diretti: diretti. Yandex: codice pronto, spento di base (richiede un account personale).
- Mixcloud: non fattibile ora (nessun plugin verificato); si riprova quando ne esce uno.
- Chiavi solo nell'.env di Lavalink; il bot sa solo se ci sono. App Spotify e account Apple Developer li crea l'owner.
- `/music` resta ≤18 figli: la coda va nel sotto-gruppo `/music coda`.
- Premium: nessuna funzione musicale per ora; spostabile dal pannello.

## D74 — Ogni allegato degli utenti passa dalla sandbox e si ricodifica; log con il webhook dell'utente (10/11/2026, scelta dell'owner)

- Vale per ogni file che arriva da un utente e che il bot prende in mano (log, backup, ticket, ModMail, transcript, pannello): immagini, PDF, audio, video, documenti, archivi. I file creati dal bot stesso sono esclusi.
- Il processo del bot non apre mai un file utente: lo apre solo il processo a parte (sandbox D62, con limiti di memoria, tempo e dimensione) e ne fa una copia ricodificata. L'originale non si conserva e non si rimanda.
- PDF: ricostruito da zero, senza JavaScript, azioni, allegati interni, moduli e metadati; se la ricostruzione fallisce, pagine rese come immagini. Audio: ricodificato in Opus. Video: ricodificato (H.264/AAC) con tetto di durata e dimensione. Documenti Office e archivi: non si ricodificano in modo sicuro, quindi si tengono solo nome pulito, tipo, dimensione e impronta (nessun file).
- Tipo sempre dai primi byte, mai dal nome; un file travestito o che la sandbox non riesce a ricodificare non si conserva e lascia una riga di avviso nel log.
- Log a nome dell'utente (spento di base, interruttore per server): il messaggio di log esce dal webhook del canale con nome e avatar dell'utente, impostati a ogni invio (nessuna modifica del webhook). Un webhook per canale, nome 1–80 caratteri senza «discord»/«clyde», menzioni sempre spente, tetto di invio per non superare i limiti; il messaggio dice chiaramente che è un log, perché non sembri scritto dall'utente.
- Precisazioni D74 (10/11/2026, opzione consigliata, da confermare): il «modo B» delle immagini (bot che apre il figlio da sé) si toglie, resta solo la sandbox separata. Audio oltre 10 minuti e video oltre 2 minuti: si tiene solo l'inizio, con la nota «tagliato». Copie di ticket e ModMail: 30 giorni come i log. Video solo per ticket, ModMail e backup; nei log di massa solo la scheda (nome, tipo, durata). Tetto giornaliero di tempo-sandbox per server. Interruttore del log a nome utente in `/admin-log webhook`. File inviati sotto 9,5 MiB. PDF: prima la ricostruzione (testo cercabile); solo se fallisce, pagine come immagini. JSON e testo di import scritti dallo staff restano letti dal bot, con tetto di dimensione e solo come testo.
- Risposte dell'owner a D74 (17/11/2026): (1) HTML e SVG sempre rifiutati; il testo semplice resta solo scheda. (2) Un'estensione pericolosa nel nome è un rifiuto anche se i byte sono testo. (3) BMP, TIFF, ICO e AVIF (e HEIC se possibile) si ricodificano in PNG invece di restare scheda: fatti BMP, TIFF, ICO, AVIF (stessi tetti di pixel, byte e tempo, una sola pagina, uscita PNG dai soli pixel). HEIC/HEIF resta scheda: serve `pillow-heif`, libreria nuova da approvare (domanda aperta). (4) Dove il bot mostra o inoltra il link di Discord a un allegato di un utente, il link all'originale si toglie: resta la scheda (nome pulito, tipo vero, peso). Il file si manda solo su richiesta e solo riconvertito dalla sandbox; per le immagini vere il bot mostra la copia rifatta.
- Scelte prudenti D74, ultime voci (17/11/2026, da confermare): (a) `/ticket rispondi allegato:` manda all'utente solo la copia rifatta (video compreso); senza copia lo staff legge «File non inviabile: motivo» e all'utente non arriva nulla. (b) Log a nome utente: `log_webhook_utente`, spento di base, in `/admin-log webhook a_nome_utente`, scritto da `core.log_webhook.imposta_a_nome_utente` (punto unico); vale solo per messaggio modificato e cancellato, solo se i log via webhook sono accesi; nome = nome visibile pulito (NFKC, senza caratteri di controllo, senza «discord»/«clyde»), al massimo 80 caratteri con « · log»; un messaggio al secondo per canale, 20 in attesa, oltre escono raggruppati senza identità; con file allegati o bottoni il log esce come prima (senza identità). Spegnere il webhook non cambia l'interruttore del nome (non ha effetto senza webhook). (c) Copie di ticket e ModMail: ogni allegato (al massimo 5 per messaggio e 30 per transcript) passa da `allegati_sicuri.conserva` (video compreso), origine `ticket`/`modmail`, 30 giorni e cancellazione `/privacy` come i log (stessa tabella `allegati_copie`); per i ModMail l'utente della riga è chi ha scritto al bot. (d) «Richiedi copia sicura» è un menu del tasto destro sul bot principale (solo «Gestisci messaggi», risposta nascosta, 5 allegati, copie sotto 9,5 MiB, tetto `sandbox_secondi_giorno`, pausa di 10 secondi per utente, video solo in ticket e ModMail). Discord ammette 15 menu per tipo (LIMITI tab. 76) ma discord.py 2.7.1 ne conta 5: il limite di 15 sta ora in `BlacklistAwareCommandTree` (`core/blacklist_tree.py`), usato dal bot principale e da iYokai App; `tests/support/full_tree.py` usa lo stesso albero.
- Conversioni sicure, parte 2b (17/11/2026, scelta dell'orchestratore su delega dell'owner): il processo del bot non apre mai il file; ogni conversione gira nel processo a parte con i criteri della sandbox D62 (processo nuovo per file, tetti di memoria, CPU e tempo vero, niente rete, uscita con tetto, ucciso o scaduto = niente copia). Solo il servizio di sistema: senza servizio non c'è ripiego, resta la scheda. **PDF:** ricostruito con `pypdf` in un documento nuovo (pagine copiate; via JavaScript, `/AA`, `/OpenAction`, `/Launch`, `/URI` e ogni annotazione con azione, `/EmbeddedFiles`, `/AcroForm`, `/Metadata`, `/Names`); tetti 20 MiB in entrata e 200 pagine; cifrato o storto = niente copia; il ripiego «pagine come immagini» NON si fa ora (aperto). **Audio:** `ffmpeg` → Opus in Ogg, mono o stereo, al massimo 10 minuti (oltre: si taglia e il nome dice `-tagliato`), senza metadati, una sola traccia. **Video:** `ffmpeg` → H.264 + AAC in MP4, al massimo 2 minuti e 720p, senza metadati, sottotitoli, allegati e capitoli; solo per ticket, ModMail e backup (nei log di massa resta la scheda). **Testo:** lo stesso testo in UTF-8 con estensione `.txt`, tetto 256 KiB, senza caratteri di controllo né invisibili. **ffmpeg:** sempre con lista di argomenti (mai shell), `-nostdin`, `-protocol_whitelist file,pipe`, formato in entrata esplicito scelto dai byte (nessun playlist, concat, hls o dash), cartella temporanea privata del lavoro. **Uscita** sotto 9,5 MiB (e al massimo 9,5 MiB di copie per messaggio), altrimenti niente copia. **Tetto giornaliero di tempo-sandbox per server:** impostazione `sandbox_secondi_giorno` (di base 600 s, 0-3600, 0 = mai), oltre solo scheda. **HEIC/HEIF:** `pillow-heif` 1.8.1 fissata, importata solo nel worker della sandbox; entra nell'elenco chiuso come gli altri formati.
- Scelte prudenti 17/11/2026 (orchestratore): (a) `-safe 1` non si passa: ffmpeg lo rifiuta con un demuxer che non è `concat` («Option safe not found»); resta la protezione vera, cioè formato esplicito + whitelist dei protocolli + rifiuto di ogni testo travestito da media. (b) Un testo con estensione pericolosa (`.py`, `.sh`…) resta un rifiuto (risposta 2 dell'owner, più prudente della scheda del lavoro): la copia `.txt` vale per il testo con estensione normale. (c) Il tempo usato oggi per server sta in memoria (si azzera al riavvio del bot): niente tabella nuova senza una migrazione riservata. (d) Il tempo-sandbox conta le sole conversioni, non l'analisi delle immagini.

## D75 — Benvenuto e ruoli (#123): scelte aperte del catalogo (17/11/2026, opzione prudente, da confermare dall'owner)

- **Gruppo `/admin-menu-ruoli`:** `/admin-ruoli` pesava 8.162 caratteri (limite 8.000 di Discord). Le sette funzioni nuove dei menu (modelli, canale dei ruoli, aggiungi-molti, opzione, sposta, ripara, svuota) stanno in un gruppo nuovo, senza spostare i comandi già in uso (`/admin-ruoli menu …` resta com'è).
- **Messaggio di altri (RUO-072, 073):** un menu a reazioni si può agganciare a un messaggio scritto da altri. Il bot non lo modifica né lo cancella: mette e toglie solo le sue reazioni. Bottoni e tendina restano solo sui messaggi del bot.
- **Emoji di altri server (RUO-075):** si accetta con `emoji_esterna: sì` solo nei menu a reazioni; la reazione la mette l'admin a mano, il bot la riconosce dall'evento.
- **Argomento dei canali (RUO-027):** l'avviso esce solo per i canali che `@everyone` vede (un canale privato non rivela il suo argomento), senza menzioni, al massimo uno al minuto per canale. Non passa dal router dei log (non è un log).
- **Primo messaggio (RUO-024):** il segno «nuovo membro» sta solo in memoria, 24 ore, tetto 5.000: nessun dato su disco.
- **Ruoli ricordati (RUO-040, 041):** elenco ammessi (se c'è, solo questi) e esclusi (mai questi), 20 per elenco; il ruolo di mute si ridà sempre e non si può escludere.
- **Ruoli vocali (RUO-044):** 10 per server (nel catalogo 1 gratis e 10 premium: qui un tetto unico). Dopo un riavvio il bot rimette a posto al massimo 200 ruoli, 0,6 secondi tra uno e l'altro.
- **Menu temporaneo (RUO-070):** la scadenza sta nel menu e nello scheduler; se la scadenza viene spostata, l'azione vecchia si ignora.
- **Calcoli (RUO-022):** solo somme e sottrazioni di interi fino a 12 cifre, al massimo 10 operazioni, mai `eval`.,

## D80 — Livelli (#124) giro r3liv: guadagno di XP, reazioni, card (17/11/2026, opzione prudente, da confermare dall'owner)

- Formule dei livelli (LIV-004): «classica» (quella di sempre, di base), «lineare» 25L²+75L, «esponenziale» 500·(1,2^L−1), «costante» 200 XP a livello. Il cambio ricalcola il livello salvato di tutti dall'XP totale, con lo stesso blocco degli azzeramenti (`blocca_azzeramento`).
- XP a parola (LIV-006): parole da 3 lettere in su, tetto 100 XP per messaggio (come il massimo di «testo»); bonus impegno (LIV-007) fisso, una volta sola; mai oltre 150 XP per messaggio. L'attesa tra due guadagni resta quella del server.
- XP dei comandi slash (LIV-017): spento di base; usa la STESSA attesa e lo stesso contatore dei messaggi (un comando e un messaggio insieme pagano una volta sola).
- Prefissi di altri bot (LIV-018): al massimo 10, lunghi al massimo 8, niente spazi né caratteri invisibili; una parola di una lettera sola o fatta di cifre è rifiutata (bloccherebbe quasi tutto).
- Elenco bianco (LIV-021): usa lo stesso elenco dei canali esclusi con `canali_modo=solo_questi`; elenco vuoto = nessun blocco (prudente: non spegne l'XP del server per errore). Un ruolo escluso vale sempre.
- Anti-farm spento (LIV-012): salta solo «assordato» e il conteggio dei muti; il canale AFK resta escluso e restano i tetti di minuti di sempre. Soglia di persone (LIV-011) da 1 a 10, di base 2.
- Reazioni (LIV-008/009): spente di base; attesa per persona e per verso (60-3600 s, di base 300) e tetto di 50 al giorno per verso, nella stessa scrittura del database; mai sul proprio messaggio, mai da o verso un bot; l'autore deve essere noto. La classifica per reazioni conta solo quelle che hanno dato XP.
- Classifiche vocale e reazioni (LIV-059/060): solo «di sempre». `azzera server` azzera XP e livelli, non minuti e reazioni.
- Card (LIV-051/054/055/056): colore del testo/anello e velo (0-100) sono per utente; sfondo e colore del server valgono per chi non ha il suo; «auto» = colore medio dell'icona (letto nel processo delle immagini, in memoria per icona).

## D86 — Economia e giochi (#125) giro r5eco: regole del server, giochi, inventario (17/11/2026, opzione prudente, da confermare dall'owner)

- Tetto al saldo (ECO-003): sta DENTRO ogni scrittura che accredita (`somma_con_tetto_sql`): chi è già sopra il tetto non perde monete ma non ne riceve altre. Un `/monete pay` verso chi arriverebbe oltre il tetto è rifiutato (non brucia monete). Le modifiche dello staff non hanno tetto.
- Saldo di partenza (ECO-002): una volta per persona e per server, a chi entra dopo l'attivazione (i membri già presenti non lo ricevono); non conta nella classifica del mese. I bot non hanno monete.
- Saldo di chi esce (ECO-014): «tieni» di base; «cancella» azzera il saldo all'uscita (anche col ban). Le monete cancellate spariscono: non vanno alla cassa.
- Serie di giorni (ECO-025): riusa la serie e gli scudi già esistenti (`progress_serie`); il bonus è `bonus_serie × giorni di fila` fino a `serie_max`, solo se i progressi del server sono accesi. ECO-027 (vacanza) non fatta: gli scudi fanno già la stessa cosa.
- Premi settimanale e mensile (ECO-026): attese fisse di 7 e 30 giorni; spenti (0) di base.
- Puntate e pausa (ECO-021/022): 1-10.000 e 5 s di base (come prima), il server può portarle fino a 1.000.000 e 0-3600 s. La puntata si controlla nel comando, il saldo e la pausa nella stessa UPDATE. Casualità dei giochi: `random.SystemRandom`.
- Giochi nuovi (ECO-090/099/100): roulette europea (colore/pari/metà/dozzine/colonne ×2-×3, numero ×36), carta (colore ×1,9, seme ×3,8, valore ×12), scala (resa media 0,96). Tutti con vantaggio del banco, provato nei test. Restano fuori i giochi a più passi (blackjack, torre, più alto o più basso): servono partite aperte salvate nel database.
- Inventario (ECO-058): entrano solo gli oggetti senza ruolo e senza riga da consegnare, nella stessa transazione dell'acquisto. Rivendita (ECO-072): sempre il 50% del prezzo di oggi (arrotondato per difetto), una sola scrittura per pezzo. Regalo (ECO-070): mai a se stessi né ai bot, righe bloccate in ordine di ID; un oggetto si può dichiarare non regalabile (ECO-071). Togliere un oggetto dal negozio svuota gli inventari di quell'oggetto.
- Azzeramenti (ECO-012, ECO-086): servono il permesso «Gestisci server» riletto al momento e il nome del server scritto a mano. L'azzeramento delle monete non tocca XP e livelli.
- Drop e lasciti (ECO-052/053/055): drop di base 0,5% per messaggio, 10-50 monete come prima, ora regolabili (per mille 0-100, importi, pausa, un solo canale). Le monete lasciate stanno nel database: le prende il primo che clicca (non chi le ha lasciate), dopo 5 minuti tornano a chi le ha lasciate, una volta sola, anche dopo un riavvio. I forzieri dello staff (max 5 a comando) creano monete dal nulla come i drop.
- Evento di monete (ECO-057): uno per server, tetto totale fino a 1.000.000, pausa di 30 s per persona (in memoria), si chiude da solo al tetto. I nuovi comandi admin stanno in `/admin-giochi` perché `/admin-economia` è a 18 figli.
- Furto (ECO-031): SPENTO di base; solo contanti (la banca è al sicuro); quota di base 10% (1-50%) fino a 5000, riesce nel 40% dei casi (1-90%); servono almeno 50 contanti a entrambi; il ladro paga una multa pari a metà quota alla vittima se fallisce; la vittima è protetta per un'ora e riceve un DM. Pausa del ladro: 1 ora.
- Colpo (ECO-030) e avventura (ECO-032): premio da 2-4 volte (colpo) o 1-2 volte (avventura) la paga del lavoro; riescono nel 40% (impostabile) e 55%; multa = metà del premio, mai oltre i contanti, versata alla cassa del server. Pause di 2 h e 1 h.
- Lavori (ECO-029): scala di 5 lavori per turni fatti (0, 10, 30, 70, 150 turni: paga al 100%, 130%, 170%, 220%, 300%); «dimettiti» riparte da zero. Il licenziamento non c'è.
- Elemosina e cerca (ECO-040/041): pause di 10 e 30 minuti; importi piccoli (fino a 10 e fino a 100).
- Duelli (ECO-104/106): lo sfidato accetta con un bottone che solo lui può premere (60 s); la posta passa dal perdente al vincitore in una transazione che blocca le due righe in ordine di ID e controlla che ENTRAMBI abbiano la posta al momento; 3 tiri da 20 a testa, 50% per parte, nessuna commissione; la posta è limitata a 100.000 e, col tetto al saldo, passa solo fino al tetto del vincitore. Posta in oggetti (ECO-104) e partita a turni non fatte.
- Partite a più passi (ECO-088/089/094/098): la puntata si toglie all'apertura e la riga della partita sta in `economia_partite_aperte` (una per persona); la chiusura cancella la riga e paga nella stessa transazione; se il bot si ferma, la puntata intera torna a chi giocava entro 15 minuti (task ogni 5 minuti e all'avvio). Scadenza dei bottoni (2 minuti) = si incassa o si sta. Blackjack: banco su tutti i 17, naturale 3:2, raddoppio e resa sulle prime due carte, divisione non fatta. Alto-basso e torre: ogni passo paga 0,95 diviso la probabilità vera, quindi resa media 95% con qualunque strategia.
- Stipendi e messaggi (ECO-033..038): massimo 10 ruoli con stipendio o tassa (da -100000 a 100000), in contanti o in banca; si riscuote ogni 20 ore; la tassa non porta sotto zero e va alla cassa; pagamento automatico a un'ora in UTC (non c'è un fuso per server), un giro al giorno per server; monete per messaggio solo nei canali scelti (massimo 25), pausa per persona e tetto giornaliero nella stessa scrittura.
- Tris e forza 4 (ECO-107/108/109): la puntata (0 = per gioco) si toglie a entrambi all'accettazione con due partite aperte; a fine partita si chiude prima chi perde (0) poi chi vince (doppio), così un errore a metà non crea monete; chi non muove entro 2 minuti perde. Forza 4 usa 7 bottoni (colonne) e il campo 6x7 a testo.
- Potenziamenti (ECO-081): due (lavoro, premio periodico), 5 livelli, +10% a livello, costo 500, 1000, 2000, 4000, 8000 (alla cassa). Scrigno (ECO-077): 100 monete, resa media 0,92, pausa 30 s, solo monete di gioco. Cambio del giorno (ECO-082): rivendita tra 40% e 60% del prezzo, scelta dalla data e dal server (nessuno stato salvato); vendita automatica (ECO-083) e borsa (ECO-084/085) non fatte.
- Lotteria (ECO-118/121): spenta di base (prezzo 0); un'estrazione al giorno per server a mezzanotte UTC (lavoro ogni 10 minuti), massimo 10 biglietti a persona al giorno, vincitore a sorte (`secrets`) in proporzione ai biglietti, premio 90% di quanto speso e 10% alla cassa; registro delle ultime estrazioni (90 giorni). Rimborso (ECO-117): 0-20% della perdita NETTA dei giochi dall'ultimo rimborso pagato; il punto di partenza si sposta solo quando il rimborso è pagato, così nessuna sequenza di giochi guadagna.
- Piccoli guadagni (ECO-042/043/044/046/047): ognuno con la sua pausa presa nella stessa transazione del pagamento (scava 1 h, meme 30 min, coccole 15 min, bersaglio 20 min, gratta 60 s); gratta e vinci costa 20 con resa media 0,85; l'oggetto trovato scavando non c'è (solo monete). ECO-045, 048-051, 054, 056 non fatte (servono servizi esterni, premium o interfacce a parte).
- Azioni degli oggetti (ECO-060): un oggetto dà monete (1-100000, pezzo e monete nella stessa transazione) o dà/toglie un ruolo; per i ruoli si controlla prima `check_role_assignable` (gerarchia e permessi pericolosi) e il pezzo si consuma solo se il ruolo si può dare; se Discord rifiuta dopo, il pezzo torna all'inventario.
- Animali (ECO-122..124, 130, 131): 4 specie (gatto 300, volpe 800, civetta 500, rana 200, il prezzo va alla cassa), un posto di base e fino a 2 posti in più (1000 e 2000); fame, pulizia e gioco calano di 4, 2 e 3 punti l'ora e si calcolano alla lettura; cura una volta all'ora per tipo (il cibo costa 5), attività ogni 2 ore (serve salute >= 30); bonus a lavoro e premio solo con salute >= 30, +10% a livello, mai oltre 15%. Adozione, cuccioli, lotte e incontri (ECO-126..129) non fatti: servono interazioni tra utenti da progettare a parte.
- Pesca (ECO-132..134, 138): 3 luoghi, 6 specie con prezzi fissi (2-120), pausa di 15 minuti, deposito di 200 pesci, vendita di tutto il deposito con una sola scrittura; guida con le specie viste e classifica del giorno. Attrezzi, esche, acquario e pesca automatica (ECO-135..137, 139..141) non fatti. Resa attesa al massimo ~18 monete per lancio (circa 70 l'ora).
- Deposito vincolato (ECO-005): 7 giorni, +10%, un solo deposito per persona, si prende dalla banca e torna alla banca (nessuna moneta nuova in contanti); gli interessi sono creati dal gioco come ogni vincita. Sasso-carta-forbici con puntata (ECO-097): 1,9 volte se si vince, pareggio restituisce (resa media 0,97). Classifica solo con i presenti (ECO-013): si chiedono il triplo di righe e si tolgono gli usciti.
- Riffa (ECO-119): premio pagato dalla cassa del server (controllata all'inizio e di nuovo al pagamento), una riffa alla volta per server, vincitore con `secrets` tra chi ha cliccato e non è in blacklist; non è salvata nel database (un riavvio la perde, ma nessuna moneta si è mossa). Rapine di gruppo e partite amichevoli (ECO-119) non fatte.
- Blocchi, amici, matrimonio (ECO-153..155): il blocco è personale (vale in tutti i server), a senso unico, massimo 100: chi ha bloccato non riceve da lui pagamenti, regali, sfide, richieste di amicizia o matrimonio; richieste con bottone solo per il destinatario (2 minuti); amici massimo 50 a persona, tra amici i pagamenti non hanno tassa; il matrimonio costa 200 a testa (alla cassa, nella stessa transazione) e scade se non mantenuto ogni 14 giorni; niente inviti (non ci sono inviti di gioco). Il blocco delle sole persone con cui si gioca non copre le citazioni o i messaggi: non è moderazione.
- Prestigio (ECO-148/149): da 10.000 tra contanti e banca (poi 20.000, 30.000, 40.000, 50.000), azzera contanti, banca, potenziamenti e turni di lavoro, +5% permanente a lavoro e premio per livello (massimo 5). Gli oggetti, gli animali e le statistiche restano. Azzera-dati (ECO-159): cancella le righe di gioco di una persona in un server con una parola di conferma; non sostituisce la cancellazione GDPR completa (`/utility privacy`).
- Storico dei movimenti (ECO-007): una riga per ogni accredito o spesa fatto con le funzioni comuni di accredito e spesa (daily, lavoro, pagamenti, giochi a più passi, negozio...) nella stessa transazione, tenuta 30 giorni; non registra i minuti in vocale (una riga al minuto per persona sarebbe troppo) né le modifiche dello staff. Il canale con il registro di tutti i movimenti (ECO-006) non è fatto: servirebbe un'uscita nel router dei log con volumi alti.
- Portafoglio (ECO-017): immagine 720x260 disegnata con Pillow fuori dal ciclo principale (`run_image_task`), senza avatar né immagini di altri utenti; usa l'immagine della moneta già validata del server.
- Tetto vocale (ECO-161): scelto dal server da 30 a 1440 minuti al giorno (di base 360), vale per XP e monete.
- Controllo anti-automazione (ECO-158): spento di base; probabilità in millesimi (0-500) nei comandi di guadagno (lavoro, daily, scava, meme, coccole, elemosina, cerca); domanda con tre risposte, un solo tentativo, risposta giusta = 10 minuti senza altri controlli (in memoria). Nessuna moneta si muove prima della verifica: il comando si ferma e va ripetuto. Non è una protezione contro un bot che sa leggere: è un freno alle automazioni più semplici.
- **Voci ECO: stato dopo il giro r6eco (aggiornato 22/11/2026; i dettagli delle scelte sono in D104 e D105):**
  - **Fatte in r6eco:** ECO-018 (gettoni, seconda moneta globale), 027 (vacanza), 039 (comandi di guadagno del server), 045 (diretta), 054 (codice in chat), 056 (bonus a tempo da prendere in chat), 074 (mercato), 075, 076, 078 (negozio avanzato), 083 (vendita automatica), 084, 085 (borsa finta e ordini), 087 (casa, in emoji), 091, 101, 102, 103, 105, 110, 111, 112 (sala giochi), 113, 114 (impiccato e quiz), 120 (fondo premi), 125-129 (animali avanzati), 135-137, 139-141 (pesca avanzata), 142 (personaggi), 144, 145 (eventi a tempo e raro), 146 (fattoria), 147 (avventura a scelte), 152 (righe del profilo).
  - **Non fatte, con il motivo:** ECO-048/049 (voto su un elenco di bot esterno: il bot non è in nessun elenco), ECO-050 (lavoro automatico: opzione premium da progettare con `dev-core`), ECO-051 (sondaggio settimanale dell'owner), ECO-160 (sospensione con richiesta di revisione: sta in `/owner`, area di `dev-core`), ECO-080 (negozio sul sito: pannello web, area di `dev-web`), ECO-006 (canale con tutti i movimenti: servirebbe un'uscita nel router dei log con volumi alti), ECO-093 (roulette russa: tema delicato, scelta prudente di non farla).

## D104 — Economia e giochi (#125) giro r6eco: voci ECO realizzate (21/11/2026, opzione prudente)

- **Fatte (aggiornano le righe «non fatta» di D86):** ECO-075 (rotazione: oggetti segnati «a rotazione», ogni giorno ne restano in vetrina N scelti da server e data; un'offerta lampo riapre un oggetto nascosto), ECO-076 (offerta lampo: sconto 1-90%, durata, usi massimi presi con una UPDATE condizionata dentro l'acquisto; bottone valido finché il bot non si riavvia, `/monete shop buy` vale sempre), ECO-078 (ricette: massimo 25 per server, 5 ingredienti, solo oggetti senza ruolo né elenco, costo facoltativo; tutto in una transazione). Il prezzo effettivo si calcola in `core/negozio_logic.prezzo_con_sconto` e si applica in `shop_repo.prezzo_di_oggi_in`.
- **Sala giochi `/sala`:** ECO-091 (roulette, un giro per tutti), ECO-102/103 (corsa con gli animali, spirito se non se ne ha uno), ECO-101/105 (lotta fino a 6: la «creatura» è il proprio animale, forza 50-70% dal livello), ECO-110 (bomba), ECO-111 (carte a turni, mano in privato), ECO-112 (bingo, cartella come testo: alternativa all'immagine). Puntata tolta a tutti in una sola transazione (`partite_repo.apri_gruppo`, righe in ordine di ID), chi non può pagare esce dalla sala, nessuna partita sotto il minimo. Piatto tutto al vincitore (nessuna commissione, nessuna moneta nuova); la roulette ha il vantaggio del banco. Chi non muove in 30 s esce; partita massima 11 minuti poi puntate rimborsate; all'avvio le righe `sala:` rimaste si rimborsano. Una partita per canale. Blocco personale rispettato all'ingresso. ECO-113/114: impiccato e quiz di gruppo senza puntata, premio 20 per impiccato vinto e 10 per risposta giusta, tetto 300 al giorno per tipo (`economia_premi_giorno`); parole e domande in `data/impiccato_it.json` e `data/quiz_it.json` (nessun servizio esterno).
- **Mercato (ECO-074) e fondo (ECO-120):** `/mercato`: annuncio con oggetto in custodia (max 5 a persona, 1-7 giorni, solo oggetti regalabili), compra, offerte con monete in custodia (max 10 per annuncio), accetta, ritira, scadenza ogni 10 minuti. Mai a se stessi, blocchi nei due versi, righe delle monete bloccate in ordine di ID. Nessuna commissione. Donazioni di monete alla cassa e di oggetti al fondo (inventario dell'utente 0); lo staff li consegna con `/admin-negozio fondo dai`.
- **ECO-039:** comandi di guadagno del server (max 10, 0-10000 monete, pausa da 1 minuto a 7 giorni): `/admin-negozio guadagno crea`, `/monete rischio guadagna` (non sono tag: i tag non hanno azione monete). **ECO-152:** `/level righe`, sei righe scelte e ordinate dall'utente.

## D105 — Economia e giochi (#125) giro r6eco: animali, pesca e mondo (22/11/2026, opzione prudente)

- **Animali (ECO-125..129):** pet sitter 40 monete al giorno (1-7 giorni, alla cassa: i bisogni restano pieni). Lotta tra animali senza puntata (forza 50-70% dal livello, esperienza a entrambi, pausa di un'ora per animale, nessun consenso richiesto ma blocchi rispettati). Incontro: l'altro giocatore accetta con un bottone; una volta al giorno per coppia di animali, 25% di cucciolo. I cuccioli e gli animali abbandonati stanno in una coda di adozione (user_id 0, massimo 20 per server): adotta il primo che arriva con un posto libero, mai chi l'ha lasciato.
- **Pesca (ECO-135..137, 139..141):** punti delle sfide = 1 ogni 20 pesci + 1 per specie trovata; 4 abilità (occhio, pazienza, capiente, mercante). Perle (moneta dedicata, 1 ogni 5 monete di valore del pesce) solo per attrezzi: esca 5, rete 30, canna 20/40/80. Pass del mese (traccia gratuita): 10 livelli da 100 punti, premio 20 monete per livello. Rete: un lancio all'ora (massimo 12) allo stagno, riscosso al comando. Acquario in testo (alternativa all'immagine). Storico 30 giorni.
- **Mondo:** gettoni globali (non si convertono, valgono in tutti i server; si guadagnano dai personaggi e dalle avventure) per la casa (12 mobili, stanza in emoji). Diretta: 30 monete più 5 per giorno di fila fino a 130. Vacanza: 20 monete al giorno (max 90) alla cassa, il tempo di vacanza non conta per la serie del premio giornaliero. Fattoria: 3 posti, fiore/grano/zucca (costo alla cassa, resa fissa). Personaggi: 6, un tentativo al giorno per ciascuno (giusto o sbagliato lo consuma), dati in `data/personaggi_it.json`. Avventura a scelte da `data/avventure_it.json`, premio una volta ogni 6 ore.
- **Borsa finta:** 5 titoli, prezzi uguali per tutti i server, passo orario a caso (±5%, tra metà e doppio del prezzo base, con `SystemRandom`), commissione 3%, massimo 1000 quote per titolo, 5 ordini a soglia a persona che scattano ai passi dei prezzi. Un ordine che non si può eseguire sparisce. Vendita automatica: massimo 5 regole, cambio tra 40 e 60, vende tutti i pezzi con il cambio del giorno (lavoro orario).
- **Eventi in chat:** codice (il primo che lo scrive giusto), bonus a tempo (+1-100% a lavoro e premio, il tuo e quello del server insieme al massimo 100%), evento raro. Il primo vince con una UPDATE condizionata. Eventi casuali del server: spenti di base, un canale scelto, al massimo uno ogni 6 ore (una volta su tre), mai senza il canale. Il bottone non sopravvive a un riavvio.

## D85 — Musica (#126), giro r4mus: scelte prudenti (17/11/2026, orchestratore su delega, da confermare dall'owner)

- MUS-048 (qualità audio per server): non si fa. Con Lavalink la qualità è del nodo, non del server; un'impostazione per server non avrebbe effetto.
- MUS-057/058: gli annunci «ora in riproduzione» sono **spenti di base** (nessun messaggio non chiesto); si accendono con `/admin-musica impostazioni annunci:` e `canale-annunci:` (il bot deve poter scrivere nel canale). Il messaggio parte dal bot principale, senza menzioni, al massimo uno ogni 3 secondi per server; un brano ripetuto (loop) non si annuncia di nuovo.
- MUS-060: la copertina del brano è mostrata solo se l'indirizzo è https, corto e senza spazi; non la scarichiamo noi.
- Il mescola fisso si spegne quando la coda finisce, anche se il bot resta connesso (MUS-038).
- MUS-007 (Mixcloud): resta non fatta (D73, nessun plugin verificato). MUS-017 (dividere un video lungo): non si fa, dipende da YouTube (regola CONFRONTO_BOT §7.3).
- MUS-040/041: «brani simili» no (dipendono da YouTube); a coda finita parte una playlist del server scelta (`playlist-di-riserva`), solo se in canale c'è qualcuno, a caso, al massimo 50 brani, una volta ogni 20 secondi per server.
- MUS-045: playlist del server «Oggi», spenta di base, riparte vuota a ogni giorno UTC, senza chi ha chiesto il brano.
- MUS-042: coda salvata nel database, spenta di base; dopo un riavvio si rimette con `/music coda ripristina` (il bot non rientra da solo in vocale: serve una persona nel canale).
- MUS-084: codice di 8 caratteri (≈40 bit); chi lo usa riceve una copia; tentativi frenati a uno ogni 5 secondi per utente.
- MUS-086: al massimo 5 collaboratori per playlist; solo il proprietario rinomina, cancella, condivide, aggiorna.
- MUS-081: playlist del server (25 al massimo): salvano e cancellano chi ha «Gestisci server», le caricano tutti.
- MUS-069: il log si manda come file ephemeral (non in DM), solo la coda da 256 KB, ripulito dalle chiavi.
- MUS-067: il conteggio dei player sta in `/owner radio stato` (non in `/owner system`, file di un'altra area).
- Non fatte in r4mus, scelta prudente (da confermare): MUS-018 (cartelle di file locali: un utente non sceglie mai una sorgente `local`, D73/sicurezza); MUS-015 (il paese delle ricerche Spotify e' una scelta del nodo LavaSrc, non del server); MUS-090 (bot musicali di colore diverso: nome e avatar dei worker sono dell'owner nel portale Discord, nessun codice); MUS-017 (vedi sopra).
- Restano da fare: MUS-010 (radio dal mondo, serve un elenco pubblico da scegliere), MUS-014 (menu per genere, playlist scelte dall'owner), MUS-019 (gioco «indovina la canzone»), MUS-065 (jukebox a monete, serve l'API dell'economia).

- **Calcoli (RUO-022):** solo somme e sottrazioni di interi fino a 12 cifre, al massimo 10 operazioni, mai `eval`.

## D90 — Alert social (#129): avvisi quasi immediati (ALR-035), 17/11/2026, opzione prudente, da confermare dall'owner

- La spinta (EventSub di Twitch, WebSub di YouTube) vuole un indirizzo HTTPS pubblico che risponda a Twitch e Google, con firma da controllare e iscrizioni da rinnovare. Il bot non ha oggi un ingresso web per questo: aprirlo è un cambio di infrastruttura (dominio, certificato, porta) da decidere con l'owner.
- **Alternativa più vicina (D18), fatta:** i controlli sono più frequenti a scelta dell'owner, con variabili d'ambiente (`ALERT_TWITCH_SECONDI` minimo 30, `ALERT_KICK_SECONDI` 60, `ALERT_PICARTO_SECONDI` 60, `ALERT_YOUTUBE_SECONDI` e `ALERT_FEED_SECONDI` 120, `ALERT_EVENTI_TWITCH_SECONDI` 600). Mai sotto il minimo: protegge le quote (LIM-16, LIM-46).

## D91 — Vocali temporanei (#127): pagina web (VOC-020), 17/11/2026

- La pagina sta in `pannello_web` (area di dev-web, NF-20), non in questo giro. Tutte le impostazioni dei vocali passano già da `voice_temp_repo` (D16), usato dai comandi `/admin-vocali`: la pagina userà gli stessi metodi. Alternativa regolare oggi: `/admin-vocali crea` (categoria e generatore in un colpo) e `/admin-vocali opzioni`.

## D92 — Alert social (#129): scelte aperte del catalogo, 17/11/2026, opzione prudente

- **Gruppo `/admin-alert`:** `/admin-moduli alert` ha già 10 comandi e pesa quasi 5.000 caratteri; le funzioni nuove stanno in un gruppo nuovo (messaggio, formato, sposta, ferma-tutti, diretta, eventi-twitch, bluesky, podcast, youtube, subreddit, feed-noto, picarto, e il sotto-gruppo `ruolo-live`). I comandi già in uso non si spostano.
- **Tetti (ALR-041):** 25 avvisi per tipo e 50 in tutto; con il premium del server 100 e 200. Il controllo del premium che si rompe vale il piano gratuito.
- **@everyone e @here (ALR-019):** mai, nemmeno con «Menziona tutti» (D12). Si usa un ruolo, scelto da chi ha il permesso di pingarlo. I testi presi da fuori (titoli, descrizioni, giochi) hanno le menzioni neutralizzate: non possono far partire il ruolo dell'avviso.
- **Controllo a mano (ALR-040):** `/admin-alert diretta`, non `/utility diretta`: `/utility` è pieno e un comando per tutti spenderebbe la quota di Twitch/YouTube. Solo staff, memoria di 60 secondi per canale, una richiesta ogni 10 secondi per server. YouTube vuole l'ID del canale (UC…); da un link si ricava con `/admin-alert youtube`.
- **Comando di ricerca periodico (ALR-016):** solo subreddit di immagini e meme da un elenco fisso (8), ogni post come embed. Mai testo libero verso altri siti.
- **Feed noti (ALR-015, 017):** sei feed pubblici scelti dall'owner (anime, manga, giochi gratis). Da provare su Discord: i siti possono cambiare indirizzo.
- **Testo fisso (ALR-029):** coperto dal modello di messaggio (500 caratteri) con `{ruolo}`.
- **Facebook (ALR-005):** come TikTok, Instagram e X: nessuna interfaccia gratuita, guida al feed «ponte» e al webhook.
- **Linked Roles (ALR-049):** richiede il collegamento OAuth dell'utente a Twitch e pagine web che il bot non ha. Alternativa da fare con `dev-web` (E3 in `APP_UTENTE_E_DESKTOP.md`); non in questo giro.

## D93 — Ruolo «in diretta» automatico (#129, ALR-042..048), 17/11/2026

- Si basa sullo stato «in diretta» di Discord (attività Streaming): serve l'intent delle presenze, che si accende con lo stesso interruttore dell'automod (`AUTOMOD_STATO_ATTIVO`). Senza, i comandi avvisano e le regole non scattano.
- Fino a 5 regole per server; 25 esclusi e 25 eccezioni per regola. Gli esclusi vincono su tutto; le eccezioni saltano solo parole e gioco, non il ruolo richiesto.
- Le regole stanno in memoria 60 secondi; i cambi di presenza senza una diretta (la grande maggioranza) finiscono prima di ogni lettura. Ogni 15 minuti il bot rimette a posto chi ha il ruolo senza essere più in diretta. L'annuncio ha una pausa per membro e per regola (predefinita 6 ore) e mai menzioni.
- Il ruolo scelto non può essere @everyone, gestito da un'app, o sopra il ruolo più alto del bot.

## D94 — Picarto e calendario Twitch (#129, ALR-008, 013), 17/11/2026

- **Picarto:** nessuna chiave né richieste a gruppi: una richiesta per canale (la stessa per più server), al massimo 40 per giro a rotazione, 4 insieme, ogni 3 minuti.
- **Eventi dal calendario Twitch:** sono eventi esterni del server (con il link del canale), al massimo 5 nuove puntate per avviso a ogni giro (ogni 30 minuti), solo entro 14 giorni, mai oltre i 100 eventi del server di Discord. Serve «Gestisci eventi» per il bot. Una richiesta per canale, anche se più server lo seguono.

## D87 — Statistiche (#130) giro r1sta: scelte del catalogo (17/11/2026, opzione prudente, da confermare dall'owner)

- Dove stanno i comandi: nessun gruppo nuovo. Filtri, accesso, campioni online, regole ed esportazione in `/admin-moduli statistiche`; contatori in `/admin-moduli contatori` (peso del gruppo 6.6k: non aggiungere altro lì, il prossimo va in un gruppo nuovo). Anonimato in `/utility privacy statistiche`. Viste in `/utility serverstats` (opzioni, non comandi).
- Contatori: tetto 20 per server (erano 5; una categoria ne usa fino a 7). La migrazione 0701 toglie il vincolo sui tipi della 0087, che in produzione bloccava ticket, ruoli, canali ed emoji. Il nome si rifà solo se è cambiato e al massimo ogni 10 minuti (orologio a scatti di 10).
- Twitch (STA-045): il token dell'app non dà i follower (serve il permesso del canale): il contatore mostra gli spettatori in diretta. YouTube: iscritti con una chiamata `channels.list` ogni 50 canali, chiave nell'intestazione.
- Gioco (STA-046): alternativa vicina, Minecraft dal servizio pubblico mcsrvstat.us (l'indirizzo è un pezzo di percorso, validato e codificato), al massimo 30 indirizzi per giro.
- Ultimo arrivato (STA-052): il nome da mostrare di un membro finisce nel nome del canale, che lo vede chi vede il canale. Chi non vuole spegne il tipo.
- Menu col tasto destro (STA-011): Discord non ha menu sui canali; «Statistiche del canale» si apre su un messaggio e mostra il canale che lo contiene.
- Presenze (STA-007): senza l'intent delle presenze la vista «giochi» dice perché non c'è; con l'intent mostra una fotografia di adesso, senza salvare nulla. STA-008: campione orario di `approximate_presence_count`, solo dove l'admin lo accende, 90 giorni.
- Anonimato (STA-028): vale per tutti i server e per il passato perché la maschera si applica quando si mostra; i numeri restano nei totali, il nome no (nemmeno nel CSV).
- Accesso (STA-013): chi gestisce il server vede sempre; se l'admin sceglie dei ruoli, solo loro (comando, menu e bottoni).
- Filtri (STA-025..027): modo «solo» con elenco vuoto non limita nulla (non spegne le statistiche per errore); una categoria nell'elenco vale per i suoi canali.
- Esportazione (STA-057): ZIP con le tabelle delle statistiche del server, regole, contatori e impostazioni (solo numeri e ID). Il resto resta nei suoi comandi (`/admin-bot config export`, `/logs export`, `/admin-inviti esporta`). Elenco membri in file (STA-058): solo con «Gestisci server».
- Non fatte qui: STA-012 (pagina web pubblica) e STA-061 (API) dipendono dal pannello web (dev-web); restano all'issue del pannello. STA-060: gli ID sono già nelle schede.

## D95 — Log (#119): scelte aperte del catalogo, 18/11/2026, opzione prudente

- **LOG-016 (un canale per ogni evento):** `/admin-log rotta evento: canale:`. Una rotta per evento (i 25 interruttori di `/admin-log eventi`), solo un canale di testo di quel server (mai un forum, mai un canale nascosto). La rotta prende il posto del canale del gruppo; se il canale non c'è più o il bot non può scrivere, il log torna al canale del gruppo (e l'avviso al proprietario parte una volta per rotta). Serve comunque un canale dei log già scelto. Le liste «includi / escludi» per canale di Zeppelin non si fanno: «escludi» è l'interruttore dell'evento (LOG-017), «includi» è la rotta; un evento in più canali insieme non c'è (una sola scrittura per evento, D15).
- **LOG-026 (testo scritto dal server):** `/admin-log formato evento: testo: data:`. Fino a 300 caratteri, segnaposto solo da un elenco chiuso (`{titolo}`, `{descrizione}`, `{data}` e una parola per ogni riga dell'evento), sostituiti con `core/template_renderer.py` (mai `str.format`, mai `eval`). Il testo prende il posto delle righe dell'embed; titolo e colore restano. La data ha 7 formati di Discord. Il pannello web con l'editor completo resta a NF-20.
- **LOG-028 (istantanee online):** `/admin-log istantanea` crea una pagina `/istantanea/<segreto>` del pannello web. Il segreto sono 256 bit, si mostra una sola volta a chi ha dato il comando e nel database resta l'impronta SHA-256. **Mai pubblica:** serve sempre l'accesso con Discord, e a ogni apertura si ricontrolla chi può vedere. Tre scelte: solo chi gestisce il server (base), chi gestisce il server più chi ha un ruolo, i membri del server che hanno il link. «Chiunque abbia il link» senza Discord non c'è (alternativa regolare: i membri con il link). Al massimo 5 istantanee attive per server, 200 messaggi ciascuna, da 1 a 7 giorni (base 3), un file di testo sotto 1 MiB. Dentro: autore, ora, testo e nomi dei file (D74: mai i file); i messaggi di utenti o canali ignorati dai log non entrano. Link sbagliato, scaduto o negato: stessa risposta. Il testo sta in tabella propria (registro dei dati): cancellato con l'istantanea, con il server e con la richiesta di cancellazione dell'autore.
- **LOG-010 e LOG-011:** già scritti dal codice di moderazione nel log di moderazione (M 1.8). Un timeout di Discord che finisce da solo non manda nessun evento: non lascia riga (resta aperto, serve un timer del lato moderazione).
- Revisione 18/11: chi non gestisce il server apre l'istantanea solo se può leggere il canale da cui viene (anche con accesso «membri» o «ruolo»); canale cancellato = chiusa per i membri.

## D97 — Musica (#126), giro r5mus: radio dal mondo, generi, indovina la canzone, jukebox (18/11/2026, opzione prudente, da confermare dall'owner)

- **MUS-010 (radio dal mondo):** `/music radio nome:` usa l'elenco pubblico radio-browser.info (gratuito, senza chiave). Ogni richiesta passa da `safe_get` (tetto 400 KB) e ogni indirizzo di stream da `url_e_sicuro`, sia prima di mostrarlo sia quando entra in coda. Si accettano `https` e `http` (oggi `/music play` e la radio dell'owner accettano già `http`, `sources.http` è acceso) ma solo sulle porte 80 e 443 (le sole che `safe_http` ammette); gli stream HLS e le stazioni segnate «non funzionanti» sono scartati. 10 stazioni per pagina, al massimo 10 pagine (100 stazioni), una ricerca ogni 3 secondi per utente, memoria di 5 minuti (64 voci). Non si manda il «click» al servizio. Il server «solo siti conosciuti» (MUS-064) rifiuta le radio: è voluto.
- **MUS-014 (playlist per genere):** tabella `music_genere_playlist` (migrazione 0730) scritta solo dall'owner con `/owner radio genere`. Solo link `https` di una playlist o di un album di una fonte nota (`classifica_link`) che passano `url_e_sicuro`. Tetti: 25 generi (un menu a tendina), 25 playlist per genere, 200 in tutto. Il menu `/music genere` e' per chi ha dato il comando; la playlist entra in coda come un link di `/music play`, con tutti i controlli del server.
- **MUS-065 (jukebox):** spento di base (`prezzo-jukebox` 0). Il prezzo (1-100.000 monete) vale **per richiesta**, anche se e' una playlist (non per brano): alternativa piu' vicina, perche' una playlist caricata da un link puo' avere 200 brani. Vale per ogni richiesta che passa da `MusicCog.accoda` (comando, canale richieste, playlist salvate, radio dal mondo, generi); non per la riserva, la coda ripristinata e la radio dell'owner. Nessuno e' esentato (nemmeno gli admin). L'addebito e' una scrittura condizionata alla cassa del server, prima della ricerca; il rimborso (brano non in coda, errore, comando annullato) rimette le monete all'utente e le toglie dalla cassa (mai sotto zero; se la cassa le ha gia' spese l'utente e' rimborsato lo stesso). Se il processo muore tra pagamento e rimborso le monete restano alla cassa (raro, scritto nel log solo se il rimborso fallisce). Il tetto di saldo del server (ECO-003) puo' ridurre un rimborso.
- **MUS-019 (indovina la canzone):** il comando sta in `/fun` (non serve un gruppo nuovo). Usa i brani della playlist dell'owner (`main_radio_tracks`); il titolo da indovinare e' la sua etichetta (se e' «Artista - Titolo» valgono anche le due parti). I file locali (`local:`) sono esclusi: solo il nodo locale li legge e il player dei bot musicali non e' sempre li'. 1-10 giri senza brani ripetuti, 15 s di estratto da un punto a caso, 30 s per rispondere, 1 punto al primo, 5 tentativi a persona per giro; i punti restano nel messaggio finale e non si salvano (nessun premio in monete, niente punteggio che cresce). Una partita per server, 60 s di pausa tra due, 5 in tutto il bot; parte solo se nel canale vocale non c'e' gia' musica. Non si addebita il jukebox. Durante la partita i comandi e gli annunci che mostrano titoli restano zitti. Il messaggio del canale richieste (`/admin-musica canale-richieste`) potrebbe ancora mostrare il titolo: va provato live.

## D96 — Configurazione, permessi e premium (#122, giro r1cfg), 18/11/2026, opzione prudente, da confermare dall'owner

- **Risposte del server (CFG-013, 014, 033):** `/admin-bot config risposte`. «Solo private» cambia la prima risposta e i messaggi dopo (`defer`, `send_message`, `followup`). La cancellazione automatica arriva a 600 secondi (il token dell'interazione dura 15 minuti) e vale solo per le risposte pubbliche. I colori sono premium (modulo `aspetto`); non esiste un solo punto che costruisce gli embed, quindi si ricolorano solo il verde e il rosso di base di Discord (`discord.Color.green()` e `red()`), gli altri colori restano. Le regole si applicano in `interaction_check`; se il database non risponde il comando va avanti con le risposte normali.
- **Ruoli richiesti per comando (CFG-012):** `/admin-bot politica ruolo-richiesto`. Vale per il comando e per il gruppo; basta uno dei ruoli (massimo 10 per comando, 100 comandi). Il proprietario del bot, quello del server e chi ha «Gestisci server» non si bloccano mai; `admin-bot` e `owner` non si limitano. Se il ruolo richiesto viene cancellato dal server il comando **resta chiuso** ai non-staff (opzione prudente: meglio un comando chiuso che aperto per sbaglio).
- **Staff e permessi (CFG-022, 023, 025, 026):** i «moderatori dichiarati» e i «gestori del bot» sono i tre ruoli che già esistono (admin, mod, ban): `/admin-bot config staff` li mostra con i gruppi che aprono e li cambia dal punto unico `imposta_ruolo` (il ruolo admin lo sceglie solo chi ha «Amministratore»). I livelli con nome di CFG-025 sono i `Livello` del bot; non si aggiunge un livello «aiutante». `/admin-bot config permessi` dice il livello di un membro e il motivo.
- **Non fatta, CFG-024** (permesso per singola azione di moderazione a un ruolo): serve toccare i controlli dei comandi di moderazione (area di `dev-moderazione`); un'impostazione senza effetto sarebbe peggio di niente. Si fa con quell'area.
- **Lingua di partenza (CFG-029):** un server **nuovo** parte dalla lingua di Discord (italiano → `it`, inglese → `en`, ogni altra lingua → `en`, perché non ha ancora testi suoi). I server già presenti non cambiano.
- **Posti premium di una persona (CFG-034, 035):** l'owner li concede con `/owner premium grant utente: posti:` (1-10, mensile, annuale o permanente; 0 li toglie); la persona li mette con `/admin-bot premium assegna` e li toglie con `togli-posto`; `stato` mostra chi ha messo il posto. Un server ha un solo posto; al massimo un cambio all'ora per persona; chi toglie può togliere solo un suo posto. Il controllo sta in `guild_has_premium_access`, mai dal lato utente. Tabelle 0720, nel registro dei dati come contabili (restano se la persona chiede la cancellazione).
- **Esportazione e importazione (CFG-043):** l'esportazione aggiunge `riferimenti` (nome di ogni canale e ruolo citato). L'importazione tiene un ID solo se esiste nel server di arrivo, altrimenti cerca **un solo** canale o ruolo con lo stesso nome e tipo, altrimenti toglie la voce (e la conta nel messaggio). I controlli sui ruoli del bot e sul ruolo admin girano sul valore già rimappato. Le tabelle dei moduli (comandi personalizzati, pannelli, ecc.) **non** sono nel file: per quelle c'è il backup del server.
- **Non fatte per scelta:** CFG-036 (Patreon: serve un account e una chiave dell'owner; resta la concessione a mano e i codici CFG-038), CFG-039 (premium col voto: serve la chiave di un sito di elenchi; mai legato all'NSFW), CFG-040 e 041 (piani, tetti e prezzi: il bot non conosce i prezzi, è una scelta commerciale dell'owner). CFG-015, 016, 017, 044 (alias, canali scorciatoia, prefisso, duplica) toccano i comandi personalizzati e i pannelli di altre aree. CFG-001, 002, 003, 006, 027 sono pagine del pannello web (`dev-web`).

## D98 — Benvenuto e ruoli (#123), giro r2ben (20/11/2026, opzione prudente, da confermare dall'owner)

- **RUO-012 (immagini del benvenuto):** `/admin-benvenuto immagini` (aggiungi, togli, elenco), al massimo 10 per server (tabella `greetings_images`, 0742; il tetto si controlla nella stessa transazione, con blocco per server). Si salva SOLO la copia: l'allegato passa da `core/safe_image` (`prepara_sfondo`: 16 megapixel, ritaglio, JPEG sotto 3 MB); l'originale non si conserva mai (D74). A ogni ingresso se ne sceglie una a caso: con il biglietto del benvenuto acceso fa da sfondo (al posto dello sfondo unico), con il biglietto spento è allegata così com'è. Un errore di lettura non ferma il benvenuto.
- **RUO-045 (ruolo personale):** lo staff concede il permesso con `/admin-menu-ruoli personale` (e lo toglie con `togli`, che cancella anche il ruolo); il membro usa `/utility identita ruolo-mio` (nome, colore, elimina). Il ruolo nasce con permessi vuoti, senza evidenza e non menzionabile; a ogni modifica i permessi si rimettono a zero. Sta subito sotto il ruolo più alto del bot. Nome pulito (niente menzioni, `@`, invisibili, apici inversi; al massimo 100 caratteri), colore `#RRGGBB` o `#RGB`. Tetto 250 ruoli personali per server (e mai oltre i 250 ruoli di Discord). Pausa di 5 minuti tra due modifiche della stessa persona (presa in modo atomico nel database). Chi lascia il server perde permesso e ruolo. Se qualcuno dà permessi pericolosi al ruolo, il bot non lo assegna più (`check_role_assignable`, `self_service=True`). Il gruppo `/utility` non ha sotto-gruppo nuovo: due comandi diretti (`ruolo-mio`, `colore`).
- **RUO-046 (colore del nome):** un menu «unique» diventa tavolozza con `/admin-menu-ruoli colori`; `/utility identita colore` (completamento con al massimo 25 voci) cambia il colore in una sola richiesta a Discord, senza toccare gli altri ruoli. Un ruolo fuori tavolozza, un menu chiuso (`lock`) o i ruoli ammessi/esclusi del menu lo bloccano. Ogni ruolo passa da `check_role_assignable` con `self_service=True` (dentro `_applica`).
- **RUO-047 (creazione guidata):** `/admin-menu-ruoli guidata`: tipo, testo (finestra), canale, ruoli (fino a 25), emoji (una per riga). La View è legata a chi l'ha avviata, ricontrolla a ogni passo che gestisca ancora il server e si chiude dopo 10 minuti. Riusa `_aggiungi_coppie`: se un ruolo non passa i controlli il menu non resta. Bottoni senza emoji ricevono un'emoji pronta (RUO-089); le reazioni le vogliono tutte.
- **RUO-053 (immagine nel menu):** `/admin-menu-ruoli immagine` da allegato (tetto di peso di `safe_image`) o da indirizzo (`url_e_sicuro` e `safe_richiesta_byte`, mai reti private). Si salva solo la copia PNG rifatta (`core/ruoli_immagini.py`, 1280 px, 3 MB) e il messaggio la porta come allegato `menu.png` dentro l'embed. Non si può su un menu agganciato a un messaggio di altri.
- **RUO-069 (gruppo di menu):** `/admin-menu-ruoli gruppo` (nome vuoto = scollega), al massimo 10 menu per gruppo. Chi prende un ruolo di un menu perde quelli che ha degli altri menu del gruppo, in **una sola richiesta** a Discord (`member.edit(roles=...)`): se fallisce non resta senza ruolo. Un blocco per (gruppo, membro) mette in fila i clic. Due scelte insieme dentro un gruppo si rifiutano.
- **RUO-083 (più ruoli per opzione):** `/admin-menu-ruoli ruoli-extra`: una opzione dà al massimo 5 ruoli in tutto (il suo più 4). Ogni ruolo passa da `check_role_assignable` alla configurazione e a ogni assegnazione (un ruolo diventato pericoloso si salta, gli altri passano). Si danno e si tolgono insieme. I ruoli in più seguono la loro opzione (tolti con essa).
- **SIC-041 (phishing, azione in più):** `/admin-filtri phishing azione_extra:` (nessuna, timeout, kick, ban), spenta di base. Si aggiunge alle azioni della regola del phishing (cancella + timeout di base; nessun doppione). Passa dal motore unico: mai su staff (`manage_guild`/`administrator`), proprietario, owner del bot né chi sta sopra il bot. Scrive il caso di moderazione (origine `automod`) e un messaggio nel log di moderazione, con motivo di al massimo 512 caratteri.
- Migrazioni usate: 0740 (ruoli in più, gruppo, colori, immagine del menu), 0741 (ruoli personali), 0742 (immagini del benvenuto).

## D99 — Pannello web (giro r1web: #122, #124, #127, #130), 20/11/2026, opzione prudente, da confermare dall'owner

- **Ruoli del pannello (CFG-002):** due liste di ruoli per server, «sola lettura» e «lettura e scrittura» (massimo 10 per lista; un ruolo ha un solo livello). Chi ha «Gestisci server», il ruolo admin del bot o è proprietario scrive sempre. **Solo loro** cambiano le liste, le pagine «statistiche pubbliche», «classifica web» e «chiave API»: chi ha solo la scrittura non può rendere pubblico niente. Il livello si ricalcola a ogni richiesta (ruolo tolto = accesso perso alla richiesta dopo, con la cache di 30 secondi dei membri). `GET` chiede la lettura, `POST` la scrittura. «Non esiste» e «non puoi» hanno la stessa risposta 403.
- **Politica dei comandi nel pannello (CFG-027):** ogni pagina di scrittura ha il gruppo di comandi che la rispecchia (`GRUPPO_PER_MODULO`, `GRUPPO_PER_AREA`, un test controlla che esistano). Se la politica del server spegne quel gruppo, o chiede un ruolo che chi scrive non ha, o lo ignora, la scrittura è rifiutata; leggere resta possibile. Owner del bot, proprietario del server e chi ha «Gestisci server» sono esenti dai ruoli (come per i comandi), ma un comando spento vale per tutti, tranne `admin-bot`. Le pagine senza un gruppo preciso (lingua, ruoli del bot, accesso) non passano dalla politica.
- **Panoramica (CFG-003):** moduli accesi e spenti, consigli del punteggio di sicurezza (gli stessi di `/admin-sicurezza score`, 5 secondi al massimo: se non arrivano la pagina si apre lo stesso), azioni rapide, ultime 5 modifiche.
- **Vocali (VOC-020):** nome, blocco, copia del generatore, registro, tetto per categoria e aspetto del pannello, con le funzioni di controllo di `/admin-vocali opzioni`. Generatore e categoria restano al comando (servono i canali veri). Il comando e il pannello scrivono con lo stesso repository ma non con la stessa funzione: portare il comando su `core/web_panel_vocali.applica` è un passo per `dev-musica`/vocali.
- **Statistiche pubbliche (STA-012):** due interruttori separati, pagina e lista dei membri (di base spenti). Pagina `/stats/<id server>` senza accesso, solo con il modulo `server_stats` acceso. Mostra i canali che `@everyone` vede (mai i privati), messaggi al giorno degli ultimi 30 giorni, e solo se acceso i membri più attivi con il nome del server (mai l'ID); chi è anonimo per STA-028 compare come «utente anonimo». Spenta, inesistente o modulo spento: stessa pagina 404.
- **Classifica web (LIV-062):** `/c/<indirizzo>`, XP di sempre, 50 righe, modulo `leveling` acceso. Indirizzo da 3 a 32 caratteri (minuscole, numeri, trattini; non all'inizio né alla fine, non doppi), unico in tutto il bot (indice unico, nessuna corsa), senza nomi riservati (percorsi del sito, `iyokai…`, `discord…`, solo numeri). Gli anonimi di STA-028 restano anonimi. Non è un'opzione premium: l'owner può limitarla dopo.
- **API (STA-061):** una chiave per server (`iyk_` + 256 bit), mostrata una sola volta nella risposta alla creazione (mai in un indirizzo, mai in un avviso o nei log) e salvata come impronta SHA-256 con le prime 8 lettere per riconoscerla. Crearne una nuova ferma la vecchia. `GET /api/v1/stats` con `Authorization: Bearer`, sola lettura (altri metodi 405), 60 richieste al minuto per IP prima ancora di guardare la chiave e 30 al minuto per server. Stessi dati della pagina pubblica; i membri solo se l'interruttore è acceso, con l'ID solo per chi non è anonimo. Ogni risposta sbagliata è un 401 uguale.
- **Avvisi del pannello (CFG-006):** per categoria (sicurezza, modifiche) e per server ognuno sceglie «nel sito», «in DM» o niente (di base niente). Chi produce un avviso chiama `core.web_panel_avvisi.avvisa`: riceve solo chi ha ancora accesso al pannello (se non si può verificare dalla memoria del bot, niente). Nel sito 30 giorni e 50 avvisi per persona; DM al massimo 3 all'ora per persona e server, senza menzioni. **Email: non c'è.** Nessun servizio di posta è configurato e la pagina lo dice; quando l'owner ne sceglie uno basta `email_disponibile()` e la verifica dell'indirizzo. Oggi producono avvisi: chiave API, indirizzo e statistiche pubbliche. Gli altri produttori (allarmi di sicurezza, modifiche) vanno collegati dalle rispettive aree.
- **Non fatta, ALR-049 (Linked Roles di Twitch):** il pannello ha solo l'OAuth di Discord con `identify`; serve un'app Twitch con chiave dell'owner, il suo OAuth (con `state`, token cifrati a riposo) e la registrazione dei metadati dei ruoli collegati. Non è una base che esista: si fa insieme alla chiave Twitch dell'owner.

## D100 — Controllo dell'area utility (#128, giro r2utl), 21/11/2026, opzione prudente, da confermare dall'owner

- **UTL-110 (@everyone e @here nei messaggi programmati):** non si fa, nemmeno con «Menziona tutti». Vale D12 e la regola di ALR-019: `@everyone` e `@here` restano sempre muti; i ruoli si pingano (se chi configura può). Alternativa: un ruolo scelto da chi ha il permesso.
- **UTL-121 (creazione guidata del giveaway con finestra a 5 campi):** si tiene `/admin-giveaway avvia` con le sue opzioni (premio, durata, vincitori, requisiti, ruoli, immagine) e i modelli (`/admin-giveaway modello`): fa tutto ciò che farebbe la finestra e di più. Una finestra ha al massimo 5 campi e non ha ruoli né immagini.
- **UTL-216 («cerca qualsiasi cosa», video):** non si fa. Serve una ricerca web o video con chiave a quota; resta `/fun search-image` con le sue fonti e le ricerche su Wikipedia. Si riprende con l'AI (NF-24) quando c'è la privacy policy.
- **UTL-025 (tag che cancella N messaggi):** il catalogo diceva «non proporre»; c'è già `cancella_messaggi` con il permesso «Gestire i messaggi» a chi usa il tag, non oltre 14 giorni, al massimo 100. Resta.
- **Pausa dei tag (UTL-012):** per utente (di base), per canale o per tutto il server (`/admin-tag tag opzioni ambito_pausa`).
- **Nomi alternativi (UTL-009):** al massimo 3 per tag, unici nel server, non uguali al nome di un tag. Vale per `/tag usa` e per il prefisso.
- **Divieti dei tag (UTL-014) e esclusioni delle risposte automatiche (UTL-064, 065):** 10 voci per elenco (ruoli, canali, utenti). Un thread segue il suo canale padre.
- **Orari dei tag (UTL-049):** oltre al cron c'è la forma guidata «ogni giorno 09:30» o «lun, gio 18:00».
- **Canale scorciatoia (UTL-070):** innesco `canale_testo`: ogni messaggio (non di bot, non di sistema) scritto in quel canale fa partire il tag col testo (200 caratteri) come argomento.
- **Colore e pausa degli embed (UTL-084, 085):** un colore per server (`/admin-messaggi embed colore`), usato solo se l'embed non ne ha uno; un invio al minuto per server con `pubblica`.
- **Fuori dal mio perimetro, da fare dagli agenti che li hanno:** UTL-204 (`/mod esporta-chat`, moderazione), UTL-205 (opzione `utente` in `/utility messaggio`, file `snipe.py`), UTL-226 e UTL-228 (`/admin-bot config pulisci` e «anche i dati» in `reset`, file `config_history.py`).
- Migrazioni: 0760 (tag), 0761 (risposte automatiche), 0762 (colore embed), 0763 (innesco canale), 0764 (bacheca).

## D106 — Controllo delle aree chiuse di moderazione, AutoMod e verifica (#115, #116, #118, giro r2mod), 22/11/2026, opzione prudente, da confermare dall'owner

- **AMD-030 (Google Safe Browsing):** non si fa ora. Serve una chiave API con quota dell'owner e va scritta in `LIMITI.md`; senza chiave resta la lista di phishing locale.
- **VER-025 (impronte tra server):** non si fa. Per privacy (D19) l'impronta dello stesso IP è diversa in ogni server: confrontare tra server vorrebbe dire conservare una chiave comune e rompere questa garanzia.
- **VER-027 (ruoli collegati di Discord):** non si fa ora. Servono l'OAuth del pannello con `role_connections.write` e la registrazione dei metadati dell'applicazione, come per ALR-049 (D99).
- **Appelli (MOD-008, MOD-063):** `appello: no` su ban, tempban e timeout segna il caso (migrazione 0800). L'appello per i timeout è spento di base (`/mod-ban appelli timeout`); accettarlo toglie il timeout solo se chi decide sta sopra l'utente.
- **Scala dei warn (MOD-033, MOD-035):** un gradino con `finestra_giorni` (1-90) conta le infrazioni degli ultimi N giorni (date in `automod_violazioni_date`, 0801); scatta il livello più alto raggiunto. `azzera_dopo_scatto` azzera conteggio e date dopo una sanzione, i casi restano.
- **Chat esportata (UTL-204):** dei file allegati restano nome pulito, tipo e peso (D74); un file sotto 9,5 MB, risposta solo per chi comanda.
- Migrazioni usate: 0800 (ban senza appello), 0801 (scala con finestra e azzeramento).
- **Permesso per singola azione (CFG-024, VER-018):** tabella `moderation_ruoli_azioni` (0802). Un ruolo con l'azione `timeout`, `warn`, `mute`, `kick`, `ban`, `tempban`, `softban`, `unban` usa quel comando anche senza il permesso di Discord né il ruolo mod; non apre gli altri. L'azione `verifica` apre solo `verify manuale` e `verify invia`. Il controllo sta in `core/command_access.controlla`; restano i controlli di gerarchia dei comandi, il permesso del bot e il rifiuto per le azioni di massa. Lo dà chi gestisce il server, mai per `@everyone` né per un ruolo pari o sopra chi lo dà (salvo il proprietario), al massimo 25 ruoli.
- **Difese di emergenza dell'AutoMod (AMD-057, AMD-071):** una sola chiave `automod_emergenza`. Blocco per menzioni: da 5 a 500 menzioni in 5-300 secondi, blocco da 1 a 1440 minuti, bot e amministratori non contano, un blocco ogni 10 minuti. Panico: da 3 a 50 persone in un minuto, dura 10 minuti, solo timeout di 10 minuti agli account sospetti (meno di 7 giorni o senza avatar) che violano ancora una regola.
- **Verifica (VER-002, 003, 006, 007, 023, 028):** il captcha ha lunghezza 4-8, misura piccola/media/grande e colore scuro abbastanza da leggersi; un codice nuovo tiene i tentativi già usati (3 rinnovi al massimo); il testo della pagina web è fino a 1000 caratteri e 20 righe, mostrato con l'escape; il ruolo avvisato per gli account doppi lo sceglie chi può «Menziona tutti».
- **Avviso in un canale (MOD-060):** `/mod-sanzioni opzioni avvisi`: l'avviso della sanzione va nel canale con la menzione della sola persona; se non si può scrivere resta il DM.
- Migrazioni usate anche: 0802 (permessi per azione). Non fatte in questo giro: MOD-016, 051, 053, 091, 092, 094, 095, 096, 103, 104, AMD-031 (restano aperte in #115 e #116).

## D103 — Controllo dell'area divertimento e immagini (#131, giro r5eco), 21/11/2026, opzione prudente, da confermare dall'owner

- Sulle 91 voci FUN senza codice: 86 esistevano già (o sono state completate) e ora hanno il codice accanto a una prova (`tests/test_fun_controllo_area17.py` e `tests/test_fun_controllo_area17_db.py`). Una (FUN-027 «Preferiresti») era a metà: ora ha i due bottoni con il conteggio (un voto per persona, cambiabile, bot esclusi, 10 minuti). Due (FUN-031, FUN-032, scherzi) non rispettavano il blocco personale di FUN-137: corretto con lo stesso controllo delle GIF.
- GIF senza fonte (FUN-101, 104, 105, 115, 127, 128, 132, 133, 134, 135): la voce, il nome e la frase nelle due lingue ci sono ma nessun servizio con licenza chiara offre una raccolta per quella categoria; rispondono con la sola frase. Il test le tiene in un cricchetto (`SENZA_FONTE`): quando arriva una fonte vanno tolte dall'elenco.
- Non realizzate, con il motivo: FUN-013/014 (tela di pixel del server: serve una tela persistente, un'immagine che cresce nel tempo e regole di moderazione dei pixel; da progettare con l'area web), FUN-017 (auto da collezione: una collezione di oggetti con garage, da fare quando il negozio avrà le categorie di oggetti), FUN-019 (battaglia a turni con bottoni: il duello a tiri con posta di `/giochi sfide duello` e il tris/forza 4 coprono la sfida tra due utenti; il combattimento a turni resta da progettare), FUN-078 (fermare un suono: un suono della soundboard di Discord dura pochi secondi e non si può interrompere), FUN-075 (suoni caricati dal server: si usa la soundboard di Discord del server; nessun file di terzi sul nostro disco).

## D102 — Musica (#126), giro r6mus: coda, posizione, DJ, voto, testi, pausa e stato (21/11/2026, opzione prudente, da confermare dall'owner)

- **Comandi nuovi e posti:** `/music` aveva già 22 figli (tetto 25): i comandi nuovi stanno nei sotto-gruppi. `/music coda togli|ultimo|miei|sposta|cima|subito` e un nuovo sotto-gruppo `/music brano ricomincia|vai-a|cerca|testo|karaoke`. Niente comandi nuovi in `/owner`. Le impostazioni nuove sono opzioni di `/admin-musica impostazioni` (22 su 25). Il `remove-track` che c'era è della radio dell'owner: non si tocca.
- **Chi tocca la coda (MUS-024, 028, 022):** DJ (ruolo scelto dal server), staff («Gestisci server») e chi è solo nel canale con il bot toccano ogni brano; gli altri solo i brani che hanno messo loro (il brano senza richiedente è considerato non loro). Vale anche con la modalità DJ spenta.
- **Subito (MUS-023):** interrompe il brano di tutti, quindi lo fanno solo i privilegiati (DJ, staff, solo nel canale), anche con la modalità DJ spenta.
- **Modalità DJ (MUS-051):** `/admin-musica impostazioni modalita-dj ruolo-dj togli-ruolo-dj`; spenta di base. Un solo punto: `MusicCog._controlli_base(dj=True)` e `_gate_dj`; la regola è in `core/music_dj_logic.py`. Con la modalità accesa sono riservati: stop, pausa, riprendi, svuota coda, mescola, loop, volume, disconnetti, skipto, previous, ricomincia, vai-a, coda salta/pulisci (già «Gestisci server»). **Restano aperti** `play` e simili (aggiungere brani), `skip` (c'è il voto), togliere e spostare i propri brani. Senza ruolo DJ valgono solo staff e chi è solo.
- **Voto per saltare (MUS-052):** `voto-salto` da 1 a 100, di base 50 (percentuale degli ascoltatori umani, arrotondata in su, almeno 1). Un voto per persona, vale solo se è ancora nel canale, sparisce se il brano cambia o dopo 10 minuti. Chi ha messo il brano, i DJ, lo staff e chi è solo saltano subito. I voti sono in memoria (si perdono al riavvio).
- **Posizione (MUS-033, 034):** `vai-a punto:` accetta `1:30`, `1:02:03`, `90` (secondi) e `+0:30` / `-0:15` (dal punto attuale); il risultato resta tra 0 e la fine meno un secondo. Le dirette (non cercabili) sono rifiutate. Sono comandi del player: seguono la modalità DJ.
- **Ricerca con scelta (MUS-013):** `/music brano cerca testo:` cerca per titolo (i link vanno a `/music play`), su un nodo del bot principale (solo ricerca), mostra fino a 10 risultati in un menu effimero, solo di chi ha cercato, 60 secondi; la scelta passa da `accoda` (stessi controlli di `/music play`: sito, parole vietate, durata, jukebox). Una ricerca ogni 3 s per utente.
- **Testi (MUS-046):** LRCLIB, vedi LIM-60. `/music brano testo` lo vede solo chi lo chiede (troncato); `/music brano karaoke` è pubblico, uno per server (un secondo dice «già in corso»). Se il brano è YouTube il titolo si ripulisce (tolti «Official Video», «Topic» ecc.) e si accetta un testo con durata entro 5 s.
- **Pausa a canale vuoto (MUS-053):** impostazione `pausa-canale-vuoto`, **accesa di base** (non cambia nulla di ciò che l'utente non vede, e il bot oggi comunque spreca il canale). Riprende al rientro solo se la pausa l'ha messa il bot; una pausa messa a mano non si tocca. Non vale per radio e 24/7.
- **Stato dei bot (MUS-061):** impostazione `stato-bot`, **spenta di base**. Solo i bot della flotta, mai il principale; al massimo un cambio ogni 15 s per bot (vale l'ultimo); si toglie a coda finita o quando il bot esce dal canale. **Attenzione:** lo stato di un bot è lo stesso in tutti i server dove sta: chi li condivide vede il titolo. Per questo è spento di base e non si mostra durante «indovina la canzone».
- **Ordine «equa»:** uno spostamento a mano resta finché non entra un nuovo brano; con la coda equa il riordino la rimette «a giro».
- Nessuna migrazione: tutto sta nelle impostazioni del server (colonna `settings`, validate in `config_history.py` e descritte in `config_impostazioni.py`).


## D101 — Controllo dell'area ticket e ModMail (#120, giro r2tkt), 21/11/2026, opzione prudente, da confermare dall'owner

- **TKT-072 (transcript online con ricerca): FATTA il 23/11 con D111 e D114** (testo qui sotto = la scelta di allora, superata). **TKT-085 (rispondere dal pannello web): fatta in r2web.** Scelta di allora: non fatte. Il bot non conserva il testo dei messaggi (SPEC §23, D74): una pagina con ricerca per utente, voto e motivo obbliga a salvare in database il testo dei ticket (dati personali, con scadenza e consenso) o a rileggerlo da Discord a ogni richiesta; rispondere dal web richiede scrittura a nome dello staff con sessione, CSRF e tempo reale. Sono del pannello web (NF-20, `dev-web`). Oggi: transcript su richiesta (`/ticket transcript`, TKT-069) e nel canale dei log. Da fare solo con il pannello e una scelta dell'owner sulla conservazione.
- **TKT-077:** «chiusi con una sola risposta» non si può contare (i messaggi non si salvano). Al suo posto «chiusi senza risposta dello staff». Le ore di punta sono in UTC.
- **TKT-014:** un modulo non è una tabella a parte: `modulo-copia` copia le domande da un pannello a un altro (poi sono indipendenti). Più semplice e senza modifiche a cascata.
- **TKT-015:** il limite per utente resta di tutto il server (`/admin-ticket limite`, vincolo nel database); il tetto di un pannello è TKT-017.
- **TKT-076:** tutti gli interruttori del log partono spenti (finora nel log andava solo il transcript). Canale: tipo «ticket» del router, o il canale dei log del server.
- **TKT-086:** riassunto AI alla chiusura solo se il pannello lo accende (`/admin-ai staff riassunto-ticket`), spento di base: il testo del ticket va al fornitore AI. Passa dalla porta unica dell'AI (tetti e regole del server); uscita pulita da menzioni di massa e inviti.
- **TKT-087:** già fatta come `/ticket assistente` (bozza solo per lo staff, mai inviata); non si crea `/ticket suggerisci`.
- **TKT-083:** con «inoltra tutto» acceso un messaggio che comincia con `//` resta nota interna; il canale si riconosce dal nome o dall'argomento.
- **TKT-012:** i menu dentro le finestre funzionano in discord.py 2.7.1 (verificato); un campo a scelta ha 2-25 voci, utente/ruolo/canale si scrivono come nomi puliti, mai menzioni.
- **Difetto corretto:** `AllowedMentions(users=[...])` lascia `everyone` e `roles` accesi: sollecito (testo che può venire dall'AI), regole di inattività, benvenuto e richiesta di chiusura ora li spengono.
- Migrazioni usate: 0770 (opzioni ModMail), 0771 (aspetto pannelli, campi del modulo), 0772 (tieni aperto, questionario, log azioni), 0773 (riassunto AI).

## D108 — Controllo delle aree backup/restore (#121) e AI (#132), giro r2bkp, 22/11/2026, opzione prudente, da confermare dall'owner

- **BKP-022 (raccolta pubblica di modelli con categorie, ricerca, lingua, voti):** nel bot ci sono tre modelli pronti (Comunità, Gioco, Studio) e i modelli propri con codice; si usano anche modelli di Discord (nome, codice o link `discord.new`). La raccolta pubblica con ricerca e voti vive nel pannello web e non è fatta: serve una pagina del pannello (dev-web), che oggi non ha una sezione backup.
- **BKP-023 (pubblicare un modello con revisione prima che compaia):** non si fa nel bot. Un codice condivisibile c'è già (`/admin-backup modello pubblica`), ma la revisione dell'owner prima della pubblicazione richiede la pagina del pannello (stesso motivo di BKP-022).
- **BKP-041 (gestione dei backup dal pannello web):** non fatta: manca la sezione nel pannello (dev-web). I comandi usano già funzioni semplici di `core/` (`backup_struttura_repo`, `backup_struttura_logic`) che la pagina può chiamare senza duplicare.
- **BKP-039 (pagina di consenso su un indirizzo web proprio del server):** non fatta. Serve un dominio per server, il certificato e il proxy: lavoro di infrastruttura, non di codice del bot. Alternativa già presente: il bot con marchio proprio (`whitelabel_bot`) e la pagina di consenso sul dominio di iYokai.
- **BKP-040 (regole di ammissione per paese, rete o VPN):** il restore non raccoglie IP né paese (un test lo garantisce sulle colonne). L'alternativa è il controllo VPN e di paese della verifica web (VER-026), che il consenso del restore segue.
- **BKP-004 (cancellare canali e ruoli già presenti):** non si offre. Il caricamento non cancella mai niente: riusa per nome e crea il resto. Più sicuro; chi vuole ripartire da zero cancella a mano.
- **Permessi pericolosi:** un ruolo nuovo con admin, gestione, ban, menzioni di massa nasce senza quei permessi se chi carica non è l'owner del server; i ruoli già esistenti non ne ricevono mai di nuovi; un ruolo con permessi pericolosi non si dà ai membri da chi non è l'owner. L'owner che carica ha il suo consenso nel menu «Carica».
- **AI-003 (abbonamento personale e del server):** il diritto del server esiste (modulo premium `ai` + prova di 7 giorni). L'uso personale (app utente, DM) c'è con quota e preferenza personali. Vendere un abbonamento personale dentro Discord richiede l'app verificata (AI-R-023): non si fa. Resta a pagamento solo il diritto del server.
- **AI-010 (carattere del bot, 2000 caratteri):** il testo libero della lore resta a 1000 caratteri (AI-R-051, scelta dell'owner), passato dai filtri dei dati personali. Alzare il tetto è una riga (`imposta_lore` e `Range` del comando).
- **AI-017:** nuovi interruttori per funzione in `/admin-ai interruttore` (scrivi, chiedi, traduci, riassumi, spiega, stile, immagina, ricerca, ticket, giochi), controllati dalla porta unica; menzione, bandiere, moderazione e traduzione automatica restano con i loro comandi.
- Migrazioni: 0810 (copie automatiche), 0811 (sincronia dei canali), 0812 (interruttori AI).

## D107 — Pannello web (giro r2web: #120, #121, #122, #129, #132), 22/11/2026, opzione prudente, da confermare dall'owner

- **BKP-041 (backup dal web):** elenco, scheda (solo i conteggi, mai i dati) ed eliminazione con pagina di conferma e CSRF. Permessi **identici ai comandi** `lista` ed `elimina`: azione «crea» di BKP-018 (il proprietario del server; un admin con «Amministratore» solo se il livello del server lo consente), riletti a ogni richiesta, più il livello admin del pannello. **Niente caricamento dal web:** caricare cambia il server e resta al comando. «Non esiste» e «non puoi» hanno la stessa risposta. L'eliminazione scrive nel registro dei backup («dal web»). Raccolta pubblica dei modelli (BKP-022/023): non fatta.
- **TKT-085 (rispondere ai ticket dal sito):** solo lo staff di quel ticket (stessa regola di `_membro_staff`: «Gestisci server», squadra del pannello o ruoli di supporto; con «solo admin» solo gli admin dei ticket), riletto a ogni richiesta. Il messaggio esce dal bot nel canale del ticket come «**nome** (dal sito): testo», con tutte le menzioni spente, al massimo 1500 caratteri, 10 risposte al minuto per persona. Il testo dei ticket non si salva né si mostra (D74): la pagina scrive soltanto, niente tempo reale. Ticket inesistente, chiuso, di un altro server o non tuo: stessa pagina 404. Risposta anonima: non si fa (il nome c'è sempre).
- **ALR-049 (ruoli collegati Twitch):** pagina `/ruoli-collegati` (serve l'accesso al pannello). Passi: Twitch (nessun permesso in più; si legge il tipo di canale dal profilo) poi Discord (`identify role_connections.write`), ognuno con `state` firmato (HMAC con `OAUTH_ENCRYPTION_KEY`), a scadenza di 10 minuti, monouso, legato all'utente della sessione; il token Discord deve essere della stessa persona. Metadati registrati sull'applicazione: `twitch_affiliato` e `twitch_partner` (booleani). Token di Twitch e di Discord solo cifrati (AES-256-GCM, dato associato utente+campo), mai esportati con «I miei dati». «Scollega» azzera il collegamento su Discord (se il token vale ancora) e cancella la riga. Il tipo è quello del momento del collegamento: per aggiornarlo si ricollega (nessun aggiornamento automatico in questo giro). Senza `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET` e `OAUTH_ENCRYPTION_KEY` la pagina lo dice (solo i nomi). Indirizzi da registrare: `<WEB_PANEL_PUBLIC_URL>/ruoli-collegati/twitch` nella console Twitch e `…/ruoli-collegati/discord` nel Developer Portal.
- **AI-017 sul web:** `/server/<id>/ai/interruttori`, da `imposta_interruttore` (punto unico).
- **24.2:** schede per `logging_basic`, `logging_advanced` e `leveling` (solo chiavi già nello schema). Gli altri moduli senza scheda non hanno impostazioni validate nello schema: restano al comando.
- Migrazioni: 0753 (ruoli collegati Twitch).

- **Ultime voci di #115 e #116 (giro r2mod, parte 3):** MOD-016 quarantena a mano (ruoli salvati prima, 0804); MOD-091/092/094/095/096 blocchi mirati sul servizio del blocco totale (opzioni nel JSON dello stato, tabella dei ruoli, 0803; kick o ban di chi entra solo se chi comanda e il bot hanno il permesso; permessi critici tolti solo ai ruoli sotto il bot e rimessi come bit); MOD-103/104 storico dei nomi (90 giorni) e soprannome e mute vocale a chi rientra (30 giorni), spenti di base (0805); MOD-051 registro della chat col caso, spento di base (0806, 30 giorni); MOD-053 colore e icona dei casi nel log; AMD-031 siti che catturano l'IP, per adulti o con malware.
- **AMD-031 resta in parte:** la lista dei malware è vuota di proposito (data/siti_malware.txt): la sceglie l'owner (fonte e quota in LIMITI.md). Le liste dei siti che catturano l'IP e dei siti per adulti sono di partenza, da allargare a mano.
- Migrazioni usate in tutto: 0800-0806 (restano 0807-0809).


## D109 — Collaudo interattivo delle prove dal vivo (#94), 22/11/2026, opzione prudente, da confermare dall'owner

- Il collaudo è lo script `scripts/collaudo.py`, in un **terminale separato**. Il bot non lo lancia e non esegue il suo codice: con `COLLAUDO=1` e un terminale vero (`sys.stdin.isatty()`) scrive solo un avviso nel log (`core/collaudo_avviso.py`). Motivo: `input()` dentro il processo del bot bloccherebbe un thread e mescolerebbe le domande con i log.
- Le prove si leggono da `VERIFICA_LIVE.md`. Superata: non si ripropone e la riga diventa `- [x]` (`--non-modificare` per non toccare il file). Errore: issue via API REST (`urllib`, nessuna libreria nuova) con etichette `verifica-live` e `bug`; se manca il token o la rete, l'errore resta salvato e si invia con `--invia-in-sospeso`.
- Stato in `collaudo/stato.json`, storico in `collaudo/storico.jsonl` (cartella in `.gitignore`). Il token non è mai stampato né salvato; il testo dell'owner è troncato a 4000 caratteri.
- Il token deve avere solo `Issues: Read and write` sul repository. Test e codice delle prove non si cancellano mai.

## D111 — Decisioni dell'owner sulle 19 voci senza codice (22/11/2026, VINCOLANTI)

- **FUN-068, FUN-070:** esistono già in `/web scheda`; si segna solo il codice.
- **UTL-226 (pulizia della configurazione da canali e ruoli cancellati):** sì, ma con **7 giorni di ritardo**. Un server colpito da un nuke deve poter ripristinare tutto. Se dopo 7 giorni canali o ruoli non sono tornati, si pulisce.
- **UTL-228 (azzerare tutti i dati del bot per un server):** sì, con **30 giorni di ritardo**. Copre account dell'owner rubati e server nukati, perché l'assistenza di Discord è lenta. Fino a quel momento i dati restano e la richiesta si può annullare.
- **CFG-032 (strumenti del bot con marchio proprio: risincronizza i comandi, registro degli errori):** sì.
- **FUN-078 (fermare il suono in corso):** sì. Lo ferma chi l'ha fatto partire, oppure chiunque se non c'è più nessuno che lo controlla (stessa logica dei brani della musica).
- **FUN-019 (battaglia testuale a turni tra due utenti):** sì.
- **AMD-030 e sicurezza dei link (obiettivo: nessuno deve farsi truffare da un link passato dal bot o in un canale che il bot gestisce):** sì, a più livelli:
  - Google Safe Browsing: la struttura è pronta, la chiave la mette l'owner nel file delle chiavi (`.env`) sul server;
  - liste pubbliche gratuite senza chiave: URLhaus, Phishing Army, OpenPhish e simili, che riempiono anche la lista dei siti con malware;
  - Cloudflare e gli altri servizi di controllo dei link (con chiave facoltativa);
  - le liste italiane AGCOM e ADM dei siti oscurati.
  Ogni servizio è facoltativo e si spegne da solo se manca la chiave. Cache e tetti per non superare le quote.
- **VER-027 (verifica con i ruoli collegati di Discord):** sì, sulla base OAuth già fatta per Twitch (ALR-049).
- **TKT-072 (trascrizioni consultabili online):** sì.
  - Trascrizioni conservate **cifrate, con scadenza di 90 giorni**, visibili solo allo staff dal pannello.
  - In più, trascrizione in **file HTML** con orario (minuti e secondi), autore e testo. Le **immagini e gli screenshot sono incorporati** nella trascrizione, sempre e solo la copia ricodificata in sandbox (D74), mai l'originale. Gli altri allegati (zip, video, …) compaiono solo con il nome del file.
- **BKP-039 (pagina di consenso):** da spiegare all'owner prima di farla.
- **MUS-018 (cartella di file locali):** sì, **solo l'owner** del bot. L'owner mette un brano nella cartella del server, il bot aggiorna da solo l'elenco dei brani disponibili e li può mettere in riproduzione insieme agli altri (anteprime di brani non ancora pubblicati). Gli utenti non vedono mai percorsi né file.
- **MUS-090 e identità dei bot:** ogni bot (main, mod, …) ha già il suo logo, impostato dall'owner nel Developer Portal.
  - Al setup del bot main, il server può scegliere per ogni bot se tenere nickname e logo originali o metterne di suoi. Si usano il nickname e l'avatar **del server** (profilo del bot nel server), non il nome vero del bot.
  - **I bot musicali sono esclusi:** si chiamano tutti «iYokai Music», hanno lo stesso logo, entrano in scala se uno è occupato, e ai comandi risponde sempre il bot main.
- **FUN-017 (gara di auto da collezione):** sì, con garage nel database e la possibilità di usare **le foto delle proprie auto**, solo come copia ricodificata (D74).
- **FUN-013, FUN-014 (tela di pixel del server):** sì, progettata bene: tela salvata, moderazione dei pixel, pagina web.
- **VER-025 (rete tra server): SÌ, CATEGORICA.**
  - Se un utente fa danni in un server dove c'è il bot (tossicità, spam di server propri, truffe, raggiri), gli owner degli altri server dove l'utente e il bot sono presenti vengono **avvisati**.
  - Se un account risulta **compromesso** (rubato, nuke), il **timeout scatta in tutti i server** in cui c'è il bot, non solo in quello colpito.
  - A parte c'è una **rete facoltativa**: un server sceglie se applicare in automatico i ban decisi negli altri server della rete.
- **MUS-015 (paese delle ricerche):** impostazione **globale** (brani ascoltabili in tutto il mondo). Un server può chiedere un **filtro per paese**: le ricerche controllano che il brano sia disponibile in quel paese (esempio: Turchia).
- **MUS-017:** NON si spezza il video. Lunghezza massima del video **8 ore**. Se la **descrizione** del video contiene l'elenco dei brani con gli orari, il bot può usare quell'elenco (capitoli) invece del video intero.

## D117 — Battaglia a turni, auto da collezione e tela di pixel (#131, giro r1fun), 23/11/2026, opzione prudente, da confermare dall'owner

Attuano D111 (FUN-019, FUN-017, FUN-013, FUN-014).

- **Battaglia (FUN-019):** `/giochi sfide battaglia membro puntata` e `/giochi sfide battaglie`. Ognuno parte con 100 punti vita. A turno: attacco (8-14 danni), difesa (+3 PV e il prossimo colpo subito si dimezza) o abilità (18-26 danni, 25% di mancare, ricarica di 3 turni propri). 40 secondi per turno: chi non agisce perde. Al massimo 16 turni in tutto, poi vince chi ha più PV (a pari PV, pareggio): così la partita sta sempre dentro i 15 minuti dopo i quali le puntate aperte vengono rimborsate. Con la puntata le monete di entrambi si tolgono insieme in una transazione (`partite_repo.apri_gruppo`, se uno non può non si toglie niente a nessuno) e si pagano insieme (`chiudi_gruppo`): chi vince prende il doppio, nel pareggio ognuno la sua. Se il bot si riavvia a metà, le puntate tornano indietro. Il blocco personale vale in entrambe le direzioni. Statistiche vinte e perse per server (tabella `fun_battaglie_stat`); il pareggio non conta.

- **Auto da collezione (FUN-017):** nuovo gruppo `/auto` (primo livello 54 su 60; `/giochi` era a 18 figli) con `catalogo`, `compra`, `garage`, `vedi`, `potenzia`, `gara`, `foto`, `foto-togli`; per lo staff `/admin-giochi auto togli-foto`. Catalogo fisso di 12 auto di fantasia in 4 rarità (comune, rara, epica, leggendaria) da 150 a 12.000 monete, con velocità, accelerazione e tenuta. Tre parti da potenziare fino al livello 5 (motore +4 velocità, gomme +4 accelerazione, assetto +4 tenuta): costo = base della rarità (60, 120, 250, 500) × (livello attuale + 1). Acquisto e potenziamento sono una transazione con UPDATE condizionata sul saldo (riga dell'auto bloccata con `FOR UPDATE`). La gara ha tre prove (rettilineo, partenza, curve) con un tiro da 0 a 30 su ogni punteggio; vince chi ne vince di più. **Contro il banco niente puntata e niente premio** (nessuna moneta nasce dal nulla; le monete del bot non si comprano con soldi veri); contro un membro la puntata si toglie a entrambi insieme e si paga insieme (come la battaglia), e lo sfidato corre con la sua auto più forte. Pausa di 10 secondi tra due gare contro il banco.
- **Foto delle auto (D74):** l'allegato (fino a 8 MB) passa per `esamina_allegato`: tipo dai primi byte, ricodifica in sandbox; se non è un'immagine vera e pulita si rifiuta. Si conserva solo il PNG ricodificato e ridotto a 640 px (tabella `fun_auto_foto`, mai l'originale né il link di Discord). Si toglie con `/auto foto-togli`; lo staff (admin) può togliere una foto o tutte quelle di un utente. **Canali senza limite d'età:** non esiste un riconoscimento automatico dei contenuti; si applica la stessa regola delle immagini di `/immagini post`: ogni foto mostrata in un messaggio pubblico ha il bottone «Segnala» e con 3 persone diverse sparisce (chiave per server, utente e impronta della foto: una foto diversa riparte da zero). **Da confermare dall'owner:** se serve di più (per esempio mostrare le foto solo nei canali con limite d'età o dopo un controllo dello staff) si aggiunge un interruttore del server.

- **Tela di pixel (FUN-013, FUN-014):** nuovo gruppo `/tela` (`vedi`, `colora`, `pixel`, `stato`; primo livello 55 su 60) e per lo staff `/admin-giochi tela azzera|togli-utente|blocca|sblocca|impostazioni`. Una tela 100×100 per server, 16 colori fissi (palette del sito: il colore 0 è il fondo vuoto), salvata nel database (`tela_pixel`, con chi ha messo ogni pixel). Pausa di base 5 minuti (da 30 s a 1 ora, la sceglie lo staff). Pagando si salta la pausa: `costo-minuto` monete (di base 10, 0 = non si può) per ogni minuto cominciato che resta; pausa, blocco, pagamento e pixel sono una transazione con la riga della persona bloccata (`FOR UPDATE`) e UPDATE condizionata sul saldo; la casella ha chiave (server, x, y): due pixel insieme sulla stessa casella ne lasciano uno (vince l'ultimo). `/tela vedi` disegna con Pillow in `run_image_task` (800 px, zoom 1-4, coordinate ai margini). Lo staff può: svuotare (serve `conferma: sì`), togliere tutti i pixel di una persona (la casella torna vuota, non si ripristina quella di prima), bloccare e sbloccare. Chi chiede la cancellazione dei dati: i pixel restano senza autore; il blocco resta registrato.
- **Pagina web della tela:** `/tela/<id server>` e `/tela/<id server>/immagine.png` in `core/web_panel_tela.py` (una sola riga in `build_app`), spenta di base: la accende `/admin-giochi tela impostazioni pubblica:sì`. Sola lettura (nessuna rotta di scrittura), HTML senza script, nome del server sotto escape, CSP del pannello, numeri della richiesta tagliati dentro la tela, limite per indirizzo (30 pagine e 20 immagini al minuto) e immagine tenuta in memoria 15 secondi. Spenta o server sconosciuto: stessa risposta «Pagina non trovata».

## D113 — BKP-039, pagina di consenso del ripristino (23/11/2026, scelta dell'owner)

- La pagina di consenso per il rientro dei membri dopo un ripristino sta sul dominio del bot, all'indirizzo **`iyokai.dev/join/<nomeserver>`**, con nome, icona e colori del server. Niente domini propri dei server.
- `<nomeserver>` è un nome breve scelto dal server, validato come gli altri indirizzi brevi (LIV-062): unico, 3–32 caratteri, minuscole, cifre e trattini, senza nomi riservati. Se il server non lo sceglie, si usa l'ID.
- Un dominio proprio del server potrà essere aggiunto in futuro come opzione premium.

## D112 — Controllo dei link (AMD-030) e rete di protezione tra server (VER-025) — scelte prudenti (22/11/2026)

Attuano D111. Dove D111 lascia aperto, si è scelta l'opzione più prudente.

**Controllo dei link (core/controllo_link.py)**
- Un solo punto: `valuta(url)` dà sicuro, sospetto o pericoloso, con fonte e categoria. Cache dei verdetti: pericoloso 6 ore, il resto 1 ora, servizi senza risposta 2 minuti.
- Ordine: domini ufficiali e whitelist del server (nessuna quota spesa), liste locali e scaricate, euristica del phishing, poi i servizi con chiave: Google Safe Browsing, Cloudflare Intel, VirusTotal. Si ferma al primo «pericoloso».
- Liste pubbliche ogni 12 ore con `safe_http`, tetto 8 MB, cache su disco in `data/cache_liste/` (fuori da git). Fonti: URLhaus (CC0), Phishing Army e OpenPhish (uso non commerciale: l'owner le spegne con `LINK_LISTE_ATTIVE` se il bot diventa a pagamento), Phishing.Database (MIT). AGCOM e ADM: struttura pronta, senza indirizzo stabile verificato restano spente finché l'owner non mette l'indirizzo.
- Non usati: PhishTank (iscrizioni chiuse), URLScan.io (analisi lente e pubbliche).
- Accorciatori: il redirect si segue solo con `safe_http.safe_segui_redirect` (3 salti, tetto di 30 al minuto in tutto il bot) e mai per i siti che catturano l'IP. I rimandi noti (google.com/url?q=) si leggono dal parametro, senza rete.
- AutoMod: violazione «Link pericolosi», di base spenta (scelta del server: spenta / solo pericolosi / anche sospetti). Azioni di partenza: cancella e avvisa.
- Chi pubblica testo o link di utenti (tag, risposte automatiche, embed, alert, saluti, pannello) toglie o rifiuta i link pericolosi.

**Rete di protezione (VER-025, core/rete_protezione.py)**
- Categorie gravi: truffa, raggiro, frode, spam di altri server, tossicità grave, account compromesso. La categoria si ricava dal motivo del caso; un avviso (warn) o una nota non fanno partire niente, serve una sanzione (ban, kick, timeout...).
- Avvisi: ricezione accesa di base, spegnibile dal server. Tetti: 5 avvisi al giorno per server che riceve, 10 segnalazioni al giorno per server che segnala, lo stesso utente e la stessa categoria una volta al giorno. Il server d'origine ha almeno 50 membri e il bot dentro da almeno 7 giorni. Il proprietario del bot blocca un server con `/owner rete`. Il nome del server d'origine compare solo se l'origine lo permette (`mostra_origine`, di base no).
- Account compromesso: timeout in ogni server dove c'è l'utente (anche senza adesione: D111 lo vuole categorico), durata del server da 1 a 672 ore, base 24. Mai su proprietari, bot o chi sta sopra il bot. Caso con origine «rete», avviso agli owner con tasto per toglierlo.
- Rete dei ban: solo su adesione. Ban solo dove l'utente è già presente (scelta prudente: niente ban preventivi). Di base «proposta con tasto»; «automatico» a scelta del server. Proposta una sola volta per terna (utente, origine, destinazione); un ban di rete non ne fa partire altri.
- Dati: tabelle `rete_*` in `data_registry`; segnalazioni e proposte 90 giorni, poi si cancellano; l'utente può chiedere la cancellazione (base legittimo interesse per la sicurezza, da confermare con il garante/consulente: nota dell'owner). Mai il testo dei messaggi.

## D114 — Trascrizioni dei ticket: scelte aperte di TKT-072 (23/11/2026, opzione consigliata, da confermare dall'owner)

- **Cosa si conserva:** le pagine HTML complete (testo, orari, immagini ricodificate in sandbox D74), cifrate in blocco con AES-256-GCM e legate al server e al ticket (un dato copiato su un'altra riga non si apre). In chiaro restano solo: server, ticket, numero, utente, pannello, date. Voto e motivo di chiusura si leggono dal ticket per la ricerca.
- **Chiave:** `TICKET_TRASCRIZIONI_KEY` nel `.env`; se manca si usa `OAUTH_ENCRYPTION_KEY`; se mancano entrambe **non si conserva niente** (il file nel canale dei log parte lo stesso). Più chiavi separate da virgola per ruotarla.
- **Durata:** di base 90 giorni; il server può accorciarla (1-90) o spegnere la conservazione dalla pagina `/server/<id>/ticket/trascrizioni` (solo admin del pannello). Vale per le trascrizioni future. La pulizia è quella del registro dati (`scade_il`).
- **Chi vede:** solo lo staff del singolo ticket (stessa regola di `core/web_panel_ticket.py`, «solo admin» compreso), riletto a ogni richiesta. Chi ha aperto il ticket non la vede dal sito (nel pannello non c'è l'utente semplice). «Non esiste», «scaduta», «non puoi» e «illeggibile» hanno la stessa risposta.
- **Cancellazione su richiesta:** `/utility privacy cancella` toglie le trascrizioni dei ticket aperti dall'utente (registro dati, `utente="cancella"`). Non si esportano: dentro ci sono anche i messaggi di altre persone.
- **File HTML di base:** il formato di base delle opzioni del pannello passa da «testo» a «entrambi» (colonna DB e valore di base). Chi aveva scelto «testo» a mano lo tiene.
- **Immagini:** al massimo 2 MiB l'una e 8 MiB il file; quelle che non entrano restano solo nome, tipo e peso. Nessun allegato non immagine ha mai un link o i byte nel file.
- **Non fatto:** un comando per le opzioni (oggi solo dal sito); la trascrizione del ModMail (solo ticket).

## D110 — Avviso all'utente e bottone «Traduci» (#116, #115, giro r3automod), 22/11/2026, opzione prudente, da confermare dall'owner

- **Una sola valutazione per messaggio:** le violazioni si calcolano una volta sola (filtri, parole, regole personali insieme). L'avviso elenca tutte le regole scattate (al massimo 5, nomi fino a 50 caratteri, senza menzioni).
- **Avviso:** Discord non ha messaggi «solo per te» fuori dalle interazioni, quindi va in DM (`core/automod_avviso.py`, via `try_dm_message`). Se i DM sono chiusi: messaggio breve nel canale con la sola menzione della persona, cancellato dopo 8 secondi. Mai il contenuto del messaggio cancellato.
- **Impostazione** (`automod_avviso_attivo`, acceso di base; `automod_avviso_testo`, fino a 500 caratteri; segnaposto chiusi `{server} {canale} {regole} {utente}`; comando `/admin-automod avviso`, anche nel pannello). Testo e nomi delle regole nella lingua del server.
- **Tetto per persona:** un avviso ogni 30 secondi e al massimo 5 in 10 minuti (in memoria, con tetto di 20.000 persone). Bot e webhook non si avvisano.
- **Non si raddoppia:** se la regola ha già parlato all'utente (azioni `dm`, `warn`, `kick`, `ban`, `ban_tempo`, `avviso_canale`) l'avviso si salta. Il percorso delle parole d'odio ha già il suo richiamo.
- **Errori:** un errore dell'avviso non ferma mai la cancellazione, il log o le altre regole.
- **Traduci:** bottone persistente (custom_id `iyokai:modtraduci`, `core/moderazione_traduci.py`, registrato da `cogs/moderation/traduci.py`). Risposta effimera, senza menzioni, nella lingua del client (`interaction.locale`). Lingua del bot (it, en): i testi fissi tornano dal catalogo (riconosciuti per testo esatto o modello); il testo libero (motivi dei moderatori) e le altre lingue passano dallo snodo AI (`tipo traduzione`, funzione `traduci`, cache dello snodo, consenso e privacy del server rispettati). AI spenta o senza fornitore: lo dice con il motivo dello snodo. Limite 5 al minuto per persona. Nessun permesso in più: mostra solo il testo già pubblico.
- **Dove c'è il bottone:** esiti pubblici delle sanzioni (`invia_esito`), registro di moderazione (`post_to_mod_log`), log AutoMod e parole d'odio, allarmi anti-nuke e blocco del server (allarme e canale di avviso). `traducibile(guild, **kw)` è il punto unico per aggiungerlo altrove. La quarantena non ha un messaggio pubblico suo: segue i log di sicurezza (da fare se l'owner lo vuole).
- Migrazioni: nessuna (restano 0807-0809).

## D115 — Musica (#126), giro r7mus: MUS-018, MUS-015, MUS-017 — scelte aperte (23/11/2026, attuano D111, da confermare dall'owner)

- **MUS-018, cartella dell'owner.** Cartella = `MUSICA_CARTELLA_OWNER`, se vuota `MAIN_RADIO_LOCAL_FOLDER` (la stessa cartella inediti della radio). Il nodo la vede come `LAVALINK_LOCAL_ROOT` (Docker: `/audio/local`; il compose monta `MUSICA_CARTELLA_OWNER`, poi `MAIN_RADIO_LOCAL_FOLDER`). Scansione ogni 5 minuti e `/owner radio cartella aggiorna`. Ammessi mp3, flac, ogg, opus, wav, m4a, aac; mai file nascosti; fino a 3 livelli; tetti 500 file, 300 MiB per file, 20 GiB in tutto; un link simbolico vale solo se il percorso vero (realpath) resta dentro la cartella.
- **Tutti i file della cartella sono «Anteprime».** Per non mostrare un brano si toglie dalla cartella (niente interruttore per brano). L'interruttore c'e' per tutte: `/owner radio cartella anteprime-no` lascia le anteprime solo all'owner. **Di base sono accese** (l'owner ha chiesto una playlist proposta agli utenti; i file li ha messi lui). Si usano con `/music coda anteprime` (nel gruppo `coda`: `/music playlist` e' gia' a 18 figli).
- **Mescolare con gli altri brani.** Un brano locale suona solo su un player del nodo locale. Se il bot sta gia' suonando da un nodo pubblico, il comando lo dice e chiede di fermare la musica; se la sessione nasce con le anteprime (o su un player gia' sul nodo locale) i brani si mescolano liberamente con quelli di YouTube e delle altre fonti, perche' il nodo locale cerca anche le altre fonti.
- **Cosa vedono gli utenti.** Solo il titolo: dai metadati di Lavalink se sembra un titolo (mai un percorso, un nome di file o `local:`), altrimenti il nome del file ripulito (senza estensione, cartelle, simboli del testo di Discord). Percorso, uri, copertina e identificatore reale si tolgono dal brano prima della coda; la scelta del brano e' un id del database o un titolo, mai un percorso. Un brano locale non entra in playlist salvate, coda salvata, playlist «Oggi», esportazioni.
- **Titoli all'esterno.** Un brano locale non si cerca nei testi (LRCLIB) e non si manda a servizi esterni: vedi `music_lyrics_logic` (il comando testo risponde «brano non cercabile»). Il titolo puo' comparire nell'annuncio e come stato dei music bot, se il server li accende.
- **MUS-015, paese delle ricerche.** Di base nessun limite (brani ascoltabili in tutto il mondo). L'owner puo' mettere un paese globale (`/owner radio paese`, tabella `music_owner_impostazioni`); un server puo' scegliere il suo (`/admin-musica impostazioni paese:`, anche dal pannello): il server vince sul globale. Si scarta un brano solo se la fonte dice chiaramente che non si ascolta nel paese; senza dato il brano passa.
- **Cosa dicono le fonti.** Deezer: l'API pubblica da' `available_countries` per i brani (il bot li legge prima di cercarli altrove). Spotify: le chiavi stanno solo su Lavalink (D73) e LavaSrc non passa i mercati al bot, quindi per Spotify il filtro non ha dati; il paese di Spotify resta una scelta del nodo (`countryCode` di LavaSrc, globale). YouTube: la fonte non dice i paesi, quindi nessun filtro. Se un plugin mette `availableMarkets`, `available_markets`, `availableCountries`, `available_countries` o `markets` in `pluginInfo`, il dato si usa subito. Il filtro vale per `/music play` (e per i link Deezer), non per la ricerca con scelta.
- **MUS-017, video lunghi.** Non si scarica e non si taglia (D111). Lunghezza massima 8 ore (`MAX_VIDEO_MS`), per ogni brano non diretta, anche dentro una playlist (gli altri si aggiungono e si dice quanti sono stati scartati); 8 ore esatte passano. La ricerca dell'elenco parte solo per un brano singolo YouTube di 10 minuti o piu' (le playlist e gli altri servizi no).
- **Da dove viene l'elenco.** Lavalink non da' la descrizione del video. Si usa prima `pluginInfo.chapters` (capitoli di Lavalink, in millisecondi), poi la descrizione letta con l'API di YouTube e `YOUTUBE_API_KEY` (la stessa degli avvisi YouTube; la chiave sta in un'intestazione, mai nell'indirizzo). Senza chiave e senza capitoli non succede niente. Tetti: descrizioni in memoria per 1 ora, al massimo 1.500 richieste al giorno per questa funzione (quota gratuita 10.000), risposta fino a 150 KB, testo letto 20.000 caratteri e 1.000 righe.
- **Regole dell'elenco.** Almeno 3 voci; massimo 100; orari che crescono (una riga fuori ordine, doppia, a meno di 5 secondi dalla precedente o oltre la durata del video si salta); orario all'inizio della riga (anche con numero d'elenco, parentesi o punto elenco) oppure, se nessuna riga comincia cosi', alla fine. Formati `m:ss`, `mm:ss`, `h:mm:ss`, minuti fino a 999 senza ore. Titoli senza link, menzioni, simboli del testo di Discord, al massimo 100 caratteri.
- **Come suonano.** Le voci sono lo stesso video (`encoded` identico) con inizio e fine in `extras`; `PlayerCapitoli` le fa partire con `start` e le ferma con `end` di Lavalink (anche dopo un loop o un cambio di nodo). Posizione e `seek` sono relativi al brano. La proposta e' un messaggio nascosto con due bottoni, solo per chi ha messo il video, valido 90 secondi; se il video e' ancora in coda le voci prendono il suo posto, se sta suonando le voci passano in testa e il primo brano parte subito.


## D116 — Pulizia ritardata, azzeramento dei dati, strumenti del marchio, stop dei suoni (UTL-226, UTL-228, CFG-032, FUN-078; giro r3utl, 23/11/2026, opzione prudente)

Attuano D111. Dove D111 lascia aperto, si è scelta l'opzione più prudente.

**UTL-226 (pulizia della configurazione, 7 giorni)**
- `/admin-bot config pulisci` sostituisce `config pulizia`. Senza opzioni mostra cosa verrà tolto e quando; non cambia niente.
- Si segna la data in cui un canale o ruolo citato manca (`config_orfani`, 0830). Un ID tornato (o non più citato, per esempio rimappato da un ripristino) perde il segno: se sparisce di nuovo i 7 giorni ripartono.
- Un giro ogni 6 ore toglie dalla configurazione solo ciò che manca da 7 giorni ed è ancora assente in quel momento (canali non in memoria: `fetch_channel`). Un server non caricato non si tocca. Ogni modifica ha la sua riga nello storico (`changed_by` vuoto, `rollback` la annulla).
- «Pulire subito» (`subito:sì`): solo il proprietario del server (non un admin), con bottone di conferma. È l'unico modo di pulire prima dei 7 giorni.

**UTL-228 (azzeramento dei dati, 30 giorni)**
- Si estende `/admin-bot config reset` con `anche_i_dati` (chiede) e `annulla_dati` (annulla). Con `anche_i_dati` la configurazione NON si azzera subito: tutto va via allo scadere dei 30 giorni, così annullare riporta davvero allo stato di prima. Il reset semplice della configurazione resta com'era.
- Chiede e conferma solo il proprietario del server (mai un admin, nemmeno l'owner del bot: non possiede il server), scrivendo il nome del server uguale al vero. Annulla il proprietario del server o dell'owner del bot. Tutto si ricontrolla alla conferma della finestra.
- Avvisi: messaggio privato al proprietario all'inizio e 3 giorni prima; se non si può, una riga nel canale dei log del server (senza menzioni). Un admin vede solo lo stato.
- Proprietario cambiato (evento `on_guild_update`, o controllo all'esecuzione se il bot era spento): la richiesta passa a «sospesa», si toglie dalla coda e il nuovo proprietario è avvisato. Per riprenderla il nuovo proprietario ripete `reset anche_i_dati:sì` con il nome del server: i 30 giorni ripartono da capo.
- La verità è nel database (`richieste_azzeramento`), non nella coda: l'esecuzione ricontrolla stato, scadenza e proprietario con la riga bloccata, in una transazione con la cancellazione. Un server non in memoria non si cancella (lo scheduler riprova); un giro ogni 6 ore esegue le richieste scadute che la coda non ha eseguito.
- Cosa va via è deciso da `data_registry` (cancellazione per server): restano ban e kick di sicurezza, premium, registri contabili e le tabelle «conserva». Il bot resta nel server e riparte da zero.

**CFG-032 (strumenti del bot con marchio)**
- Sono due azioni nuove di `/admin-bot premium marchio` (il comando che c'è già): «risincronizza i comandi» e «ultimi errori». Lo stato era già `azione:stato`.
- Permessi: oltre al livello admin del gruppo, solo il proprietario del server o chi ha collegato il bot con marchio (`created_by`). Un admin qualunque non può: l'applicazione del marchio è di chi l'ha portata.
- La risincronizzazione ignora l'impronta salvata ma la riscrive; una alla volta per server, attesa di 5 minuti solo se riuscita (come `config sincronizza`).
- Il registro degli errori sta in memoria (20 per server) e salva solo ora, origine (codice fisso), tipo di errore e, per Discord, stato HTTP e codice. Mai il testo dell'errore (può contenere pezzi di richieste), mai il token, mai ID. Si svuota al riavvio; per un registro che resta servirebbe una tabella (non fatta: i log del bot hanno già il tipo dell'errore).
- Il pannello web (D16) non ha ancora i due strumenti: usano `GestoreMarchio.risincronizza` e `marchio_errori.elenco`.

**FUN-078 (fermare il suono in corso)**
- Discord non ha una chiamata per interrompere un suono della soundboard (D103). Alternativa più vicina: il suono in corso è «l'ultimo partito nel canale, da meno di 8 secondi» (un suono dura al massimo 5,2 s). Se il bot musicale è entrato solo per quel suono, lo si ferma facendolo uscire dal canale (da provare dal vivo che il suono si interrompa). Se il bot sta suonando musica in quel canale non si tocca: uscire fermerebbe anche la musica, e lo si dice all'utente.
- Chi può: chi l'ha avviato (anche se è uscito dal canale); staff e DJ (la stessa regola dei brani, `_privilegi`: «Gestire il server», ruolo DJ, o da solo nel canale); chiunque nel canale se chi l'ha avviato non c'è più. Chi sta in un altro canale vocale non ferma questo suono, nemmeno lo staff. Il controllo si rifà a ogni pressione del bottone.
- Il gruppo `/music` arriva a 24 figli (limite 25, obiettivo 18 già superato prima: serve spostare comandi se ne arrivano altri).
- FUN-068 e FUN-070 esistono in `/web scheda`: segnati con `# FUN-068` e `# FUN-070` in `tests/test_fun_controllo_area17.py`.


## D118 — Identità dei bot, verifica con i ruoli collegati e pagina di rientro: scelte aperte (giro r3web, 23/11/2026, opzione consigliata, da confermare dall'owner)

Attuano D111 (MUS-090, VER-027) e D113 (BKP-039). Dove le decisioni lasciano aperto, si è scelta l'opzione più prudente.

- **MUS-090 (#126):** `/admin-bot setup identita-bot` (sotto-gruppo `setup`, che passa da 2 a 3 comandi; nessun comando in `/owner`). Bot con scelta: Mod, Creator, NSFW, App. Il main ha già `/admin-bot config nickname-bot` e `/admin-bot premium aspetto`. I bot musicali non si registrano mai (`core/bot_identita.py` solleva) e la richiesta su di loro risponde «esclusi». Si cambiano solo nickname e avatar **del server** (`Member.edit` di discord.py 2.7.1, cioè `PATCH /guilds/{id}/members/@me`; nessuna chiamata HTTP diretta serve). **Non è premium** (a differenza dell'avatar del main): D111 non lo chiede; se l'owner lo vuole, si aggiunge il controllo del modulo `aspetto`. Permesso: «Gestisci server», riletto a ogni chiamata. Pausa: 4 cambi ogni 10 minuti per server e bot; «torna all'originale» non è mai bloccato dalla pausa. Il logo passa dalla pipeline D74 (byte, peso, sandbox) e si carica la **copia PNG ricodificata**: un GIF animato perde l'animazione; se la sandbox non risponde il logo è rifiutato. Niente tabella: il profilo sta in Discord. Il Creator c'è nei server solo durante un backup.
- **VER-027 (#118):** tre metadati: `verifica_superata` (booleano), `eta_account_giorni` (intero «almeno», dall'ID dell'account) e `avatar_presente` (booleano). Con i due di Twitch fanno 5, **il massimo di Discord**: nessun altro metadato si potrà aggiungere senza toglierne uno. «Verifica superata» vale se la persona ha superato la verifica di **almeno un server** con il bot (da `verify_attempts` al momento del collegamento, poi dal gancio in `cogs/security/verify.py`). L'avatar si aggiorna alla verifica o ricollegando. Il passo su Discord usa lo **stesso indirizzo di ritorno** di Twitch (`…/ruoli-collegati/discord`) con `state` di scopo diverso: niente nuovo Redirect da registrare. La verifica non richiede Twitch. Un solo collegamento per persona su Discord: Twitch e verifica scrivono un corpo unico (`corpo_unico`). Token cifrati con dato associato `verifica_token`; migrazione 0754.
- **BKP-039 (#121):** pagina `/join/<nome>`, accesa dal server in `/server/<id>/join` (stessi permessi dei backup, riletti a ogni richiesta). **La pagina è spenta di base**: non basta avere il bot, perché con l'ID si potrebbero provare tutti i server. Senza nome vale l'ID (con un nome scelto l'ID non vale più). Nome: stesse regole di LIV-062 più nomi riservati del sito e del ripristino; si accettano maiuscole nel modulo e si salvano minuscole. Colori: principale e di sfondo (`#rrggbb`), serviti da `/join/<nome>/colori.css` (la CSP non ammette stili nella pagina) con il colore del testo scelto dalla luminosità. Disponibile solo se il ripristino del server non è «solo invito classico». Per entrare serve l'accesso al pannello (serve a legare il consenso a chi lo dà, come SEC-19): un cookie ricorda `/join/<nome>` (solo quella forma, nessun redirect libero) e dopo l'accesso si torna lì. Da «Autorizzo il rientro» parte `build_authorize_url` del ripristino, in sola modalità consenso, sulla callback di sempre: niente cambia nella sua sicurezza. Nome inesistente, pagina spenta, bot assente, modalità classica e funzione non configurata danno la stessa 404. Dominio proprio del server (premium): non fatto, come in D113. Migrazione 0755.
- Migrazioni usate: 0754 e 0755 (restano 0756-0759).


## D119 — Voci solo nei documenti (giro r1doc), 23/11/2026, opzione consigliata, da confermare dall'owner

Controllo voce per voce delle 89 voci citate solo nei documenti. Tabella in `revisione/01-analisi/catalogo/CONTROLLO_AREE_CHIUSE.md`, sezione «Voci solo nei documenti».

**Motivi che non reggono (regola D18: si fanno):** «tocca file di altre aree» (CFG-015/016/017: erano già fatte dai tag, CFG-044), «da progettare con dev-core» (ECO-050, ECO-160), «area di dev-web» (ECO-080), «volumi alti» (ECO-006: si manda un riepilogo ogni minuto), «tema delicato» (ECO-093: nome e grafica neutri, come dice il catalogo), «non c'era tempo» (UTL-024, UTL-111). Restano non fatte solo le voci che dipendono da una chiave o da un account dell'owner, da una scelta commerciale o da una regola di sicurezza: CFG-036, CFG-040, CFG-041, UTL-110, UTL-121 (l'alternativa fa di più), UTL-216, FUN-138.

**Conflitto tra decisioni.** D71 e D72 chiedono il codice del voto al bot «pronto e spento», D86 lo dà per non fatto («il bot non è in nessun elenco»). Oggi il codice non c'è. Scelta consigliata: un solo modulo «voto» sul pannello web (un indirizzo che riceve il voto con un segreto nel `.env`, spento senza segreto) che alimenta LIV-019 (bonus XP per 12 ore), ECO-048 (monete), ECO-049 (riscatto automatico) e CFG-039 (premium a tempo, mai legato all'NSFW). Voce grande, non fatta in questo giro.

**Scelte fatte nelle voci realizzate**
- LIV-013: due colonne (`xp_testo`, `xp_vocale`), migrazione 0850. Il passato resta nel totale e le due classifiche partono da zero (D71). L'XP dato dallo staff non entra nelle due classifiche. Il livello mostrato accanto è calcolato dal solo XP di quel tipo, con la formula e il tetto del server. Il totale e il livello «vero» non cambiano.
- LIV-053: otto sfondi disegnati da Pillow (nessun file nel repository), scelti per completamento (nessun peso in più nei gruppi, D56). Valgono per la card personale e per quella del server; chi ha caricato un'immagine sua la sostituisce con quella pronta.
- LIV-061: `vincitori-set settimanale:sì` (e `vincitori-off settimanale:sì`) invece di un comando nuovo. Parte il lunedì, per la settimana ISO appena finita, una volta sola (tabella `top_settimanale_conf`, 0851). Alla prima attivazione la settimana appena finita conta come già annunciata. Menzioni spente.
- LIV-090: la presentazione resta di 140 caratteri (il catalogo diceva 60) e ora passa dal filtro delle parole vietate del server.
- LIV-091: gli XP globali sono la somma dei soli XP positivi e si vedono solo nel profilo globale personale (`/level progressi sezione:globale`); non c'è un profilo globale visibile agli altri (D57).
- CFG-011: `canale_bot` e `comandi_canale_bot` dentro `/admin-bot config risposte`. Senza elenco vale per tutti i comandi; con l'elenco, solo per quei comandi o gruppi. Nel canale giusto nulla cambia; il «solo private» del server vince sempre. I pannelli permanenti e i sondaggi restano pubblici come per CFG-013.
- VOC-017: si toglie un'azione a un ruolo (non si dà un permesso). Così chi non ha ruoli nell'elenco può tutto, come prima. Chi ha «Gestisci canali» non è mai fermato. Il controllo sta nel punto unico che serve sia i comandi sia il pannello a bottoni.
- LIV-046: colonna `livello_vocale` sul ruolo premio (0852). Il livello vocale si calcola dall'XP vocale con la formula e il tetto del server. Chi ha il ruolo e perde il livello vocale (azzeramento) lo perde. Il ricontrollo parte a ogni minuto vocale che dà XP, tramite `sincronizza_premi` (al massimo ogni 10 minuti per membro, lettura dei requisiti in memoria per 5 minuti).
- MUS-043: la coda come file `coda.txt` con un'opzione di `/music queue` (il gruppo `/music` è pieno, 24 figli); senza i nomi di chi ha chiesto i brani.
- FUN-030: `immagine:sì` su `/fun citazioni caso`; senza avatar (la citazione può essere di qualcuno che ha lasciato il server).
- AI-022: il menu «Traduci» di App accoda i messaggi di fila dello stesso autore (al massimo 6, 1.500 caratteri) se il bot può leggere la cronologia del canale; se no traduce solo il messaggio scelto.

**Scelte aperte (non fatte, serve l'owner)**
- LOG-029 (archivio dei messaggi di un utente su 3 giorni a ogni sanzione). Opzione consigliata: non tenere il testo di tutti su disco. Alla sanzione si salva, come per MOD-051 (`moderation_chat_log`, cifrato, 30 giorni), il solo registro del canale; niente archivio dell'utente su tutti i canali. L'alternativa è leggere a richiesta la cronologia dei canali (lento, molte chiamate). Va confermata.
- Reputazione (LIV-076…088, 13 voci), progetto: tabelle `reputazione_punti`, `reputazione_registro` (90 giorni, `utente=cancella`), `reputazione_impostazioni` e `reputazione_premi`; due gruppi nuovi `/rep` (dai, togli, mostra, classifica, registro) e `/admin-rep` (imposta, cancella, azzera, impostazioni, premio); spenta di base, dare punti a tutti, togliere solo con il ruolo scelto (D71); pausa da 1 ora a 7 giorni, massimo per comando, mai a se stessi né ai bot, «grazie @utente» con `message_content` e solo nei canali scelti. Due gruppi nuovi contano sul tetto di 60 di primo livello (D56): prima di farli si controlla `tests/test_command_tree_invariants.py`.

## D120 — Reputazione, voto al bot, import e annuncio (giro r1rep), 23/11/2026, opzione consigliata, da confermare dall'owner

Chiude le scelte aperte di D119 sulla reputazione e sul voto. Migrazioni 0870 (reputazione), 0871 (annuncio), 0872 (voto).

**Reputazione (LIV-076…088).** Cinque tabelle (`reputazione_impostazioni`, `_punti`, `_registro`, `_pausa`, `_premi`), tutte nel registro dei dati; il registro dura 90 giorni e si cancella con l'utente. Gruppi nuovi `/rep` (dai, togli, mostra, classifica, registro) e `/admin-rep` (imposta, cancella, azzera, impostazioni, premio): 2 gruppi nuovi, il tetto di 60 è rispettato (`tests/test_command_tree_invariants.py`). Spenta di base. Tutti possono dare; togliere solo chi ha il ruolo scelto o gestisce il server (D71). Pausa tra 1 ora e 7 giorni per chi dà (una sola scrittura condizionata), tetto di punti nelle 24 ore, massimo per comando (1-10). Mai a se stessi né ai bot. Chi ha bloccato qualcuno (`economia_blocchi`) non riceve da lui. «Grazie @utente»: spento di base, vale solo nei canali scelti (massimo 20), con una sola persona nominata, e risponde con una reazione. Ruoli per soglia: massimo 10 per server, ricontrollati con `check_role_assignable`. LIV-088 è coperta da LIV-082 (D71). La classifica è `/rep classifica` (D119), non una scelta di `/level leaderboard`.

**Annuncio (LIV-032, 033).** Due colonne in `leveling_settings` (`levelup_embed`, `levelup_immagine`). L'embed è uno di quelli salvati con `/admin-messaggi embed`, con gli stessi segnaposto del testo. L'immagine è una card piccola (800x160) disegnata fuori dal ciclo principale; se il disegno o l'embed falliscono l'annuncio parte lo stesso, solo con il testo.

**Import (LIV-072).** Solo da un file JSON o CSV caricato dall'admin (mai da API di altri bot, mai da un indirizzo): 2 MB, 50.000 righe, id e xp validati uno per uno, un errore blocca tutto. Non toglie mai XP (come il ripristino), si può ripetere, un solo import alla volta per server. Il comando è `/admin-livelli azzera importa`. Funzione `livelli_importa`: di base gratuita come ogni funzione; D71 la vuole Premium e l'owner la sposta dal pannello.

**Profilo globale (LIV-089).** `/level progressi carta:sì`: la card del profilo con XP e monete di tutti i server (solo i positivi) e i traguardi; visibile solo a chi la chiede (D57).

**Voto al bot (LIV-019, ECO-048, ECO-049, CFG-039), un solo modulo.** Risolve il conflitto D71/D72/D86: il codice c'è ed è spento. Un piccolo server web proprio (non il pannello: il pannello parte solo con le chiavi OAuth) ascolta `POST /voto` su `WEB_BIND_HOST:VOTO_PORT` (8422) e parte solo se `VOTO_SEGRETO` (almeno 8 caratteri) è nel `.env`. Accetta il segreto top.gg nell'intestazione Authorization o la firma `x-topgg-signature` (HMAC-SHA256, tolleranza 5 minuti); i tentativi sbagliati si limitano per indirizzo. Un voto vale una volta: due richieste dello stesso sito per la stessa persona entro 11 ore sono lo stesso voto. Il voto è al bot, non a un server: chi vota riscatta il premio in un server con `/monete conto voto` (entro 7 giorni), oppure sceglie `automatico:sì` e il premio arriva da solo in quel server (ECO-049). Ogni server sceglie il premio con `/admin-giochi voto`: monete, XP, bonus XP in % per N ore (LIV-019, di base 10% per 12 ore) e giorni di premium per il server (CFG-039, 0-30; mai legato all'NSFW). Il premio e il segno «riscattato» stanno nella stessa transazione; il premium a tempo si dà subito dopo. Il fine settimana non vale doppio: un premio per voto. Il premio del server è spento di base.

## D121 — Giro r1med: voci medie rimaste (23/11/2026, opzione consigliata, da confermare dall'owner)

Attua D119 per le voci medie. Elenco delle voci e dei motivi in fondo, aggiornato a ogni voce chiusa.

### LOG-029: decisione dell'owner (23/11/2026, VINCOLANTE), scelta aperta di D119 chiusa
- **Si fa.** A ogni sanzione (warn, timeout, kick, ban, tempban) si salva, legato al caso, l'archivio degli eventi dei messaggi dell'utente degli ultimi 3 giorni, costruito dal **registro eventi già salvato** (`event_log`: messaggi cancellati e modificati), su tutti i canali che il server registra. Niente raccolta nuova, niente chiamate alla cronologia di Discord.
- **Che cosa c'è dentro, controllato nel codice.** Il registro eventi salva per ogni messaggio il momento, il canale, l'autore e l'id del messaggio, **non il testo** (`cogs/logging/message_logs.py`, D74: il bot non conserva il testo dei messaggi). L'archivio quindi dice quando, dove e che cosa è successo (cancellato o modificato) con l'id del messaggio; il testo non c'è, perché non è mai stato salvato. Lo si dice nel file stesso e nella risposta. Se l'owner vuole anche il testo serve una raccolta nuova (cifrata, con scadenza): è un'altra decisione, non presa qui.
- **Apertura.** Solo dallo staff: `/mod-casi caso chat numero: archivio:sì`, file privato. La funzione sta in `core/moderation_archivio_utente.py` (D16: la usa anche il pannello web). Per gli allegati valgono le regole di D74 (nel registro non ce ne sono: solo identificatori).
- **Conservazione.** Il dato resta finché esiste il caso (come sanzione e motivo). I 30 giorni partono da eventi come la chiusura del server o una richiesta di azzeramento (UTL-228) e la cancellazione dei dati di un utente (`utente="cancella"`), non dalla sanzione. Il tetto di 3 giorni vale solo per ciò che si copia.

### Voci fatte e voci non fatte (D121)
- **ECO-006**: fatta: riepilogo a lotti (D86 temeva un messaggio per movimento: ora ce n'è uno al minuto per server, tetto 300 movimenti per giro, il resto al giro dopo). Se il bot non può scrivere il lotto resta e si riprova.
- **ECO-050**: fatta: premium (D72), 4 ore, nel worker del bot (non nello scheduler a righe: serve un solo giro periodico per tutti). Ritentare un giro non paga due volte (la riga si sposta prima di pagare).
- **SIC-021**: fatta: l'uso non può passare da `/owner` (l'owner senza account non lo apre): la verifica è uno script sul server e il cambio di `OWNER_ID` resta manuale, come dice il catalogo («controllo a mano»). Comando dentro `/owner system`: nessun figlio nuovo di `/owner`.
- **MUS-016**: fatta: filtro sul titolo dei risultati (parole intere), impostazione del server accesa a scelta, spenta di base.
- **RUO-005**: fatta: tetto 2048 come `safe_image`; il layout resta quello 1024x400, scalato senza deformarlo.
- **CFG-044**: fatta: duplica per pannello e per risposta pronta; il bottone pubblicato e i ticket aperti non si copiano. Il comando sta nel gruppo `admin-ticket pannelli`, già esistente.
- **VOC-014**: fatta: stanza di scorta con proprietario il bot, presa da chi entra. Trovato e corretto un difetto di r1doc: il blocco VOC-017 (azione/ruolo) stava nel comando dei generatori invece che in `opzioni` (NameError su `ruolo`); sistemati anche 10 test senza DB.
- **ECO-160**: fatta: la sospensione sta in `/admin-giochi` (staff del server) e la revisione arriva allo staff, non all'owner del bot; ferma solo `/monete`, `/giochi`, `/clan`.
- **UTL-024**: fatta come elenco chiuso (D18): ruolo, messaggio, reazione; mai un comando qualsiasi. Il ruolo e la risposta singoli dei tag (UTL-016, UTL-022) restano; queste azioni sono in più (fino a 3). Chi usa il tag è il bersaglio: nessuna azione colpisce altri.
- **UTL-111**: fatta: poche azioni sicure, fino a 5 (il catalogo: sblocca canale, togli ruolo; in più dai ruolo e messaggio). Mai comandi di moderazione.
- **ECO-051**: fatta come premio di un sondaggio del server (D18: alternativa più vicina). Un sondaggio dell'owner su tutti i server non esiste: il bot non ha una rete di server dove mandare un sondaggio unico senza che lo staff lo scelga.
- **TKT-088**: fatta, con il vincolo dell'owner: serve una chiave Bloxlink nel `.env`; senza resta spenta. Il collegamento Discord-Roblox è di Bloxlink (il bot non lo conosce); l'API di Roblox è pubblica.
- **ECO-093**: fatta: tema delicato risolto con nome e grafica neutri («Tamburo», una sfera rossa in una casella), come dice il catalogo.
- **ECO-080**: fatta: il sito mostra il negozio in sola lettura; comprare resta su Discord (il sito non tocca le monete di nessuno).
- **SIC-016**: fatta: nessun sistema nuovo, si riusa BKP-008 e il caricamento esistente. L'avviso dell'anti-nuke non cita ancora il comando (resta una riga di testo da aggiungere in `cogs/security/anti_nuke.py`).

### Esito del giro r1med (23/11/2026)
- **Fatte (15 delle 16 voci della scheda, più LOG-029 per scelta dell'owner e la correzione dell'AutoMod):** LOG-029, ECO-006, ECO-050, ECO-051 (come premio di un sondaggio del server), ECO-080, ECO-093, ECO-160, CFG-044, MUS-016, RUO-005, SIC-016, SIC-021, UTL-024, UTL-111, VOC-014, TKT-088 (spenta senza chiave Bloxlink).
- **Non fatta, nessun motivo che regga: TKT-073** (copia del transcript su Google Drive). Il lavoro resta: OAuth Google dell'admin del server dal pannello web, token cifrato, caricamento nella cartella scelta, spenta finché l'owner non mette le chiavi Google nel `.env`. Va nel prossimo giro con `dev-web` per le pagine del consenso.
- **Chiavi per l'owner:** `BLOXLINK_API_KEY` nel `.env` (TKT-088; vuota = funzione spenta). Nessuna altra chiave nuova in questo giro.
- **Cose trovate e corrette lungo la strada:** il blocco VOC-017 (azione/ruolo) di r1doc era finito nel comando dei generatori (NameError su `ruolo`) invece che in `/admin-vocali opzioni`; 10 test dei vocali non avevano il database dopo VOC-017.

## D122 — Scelte dell'owner del 23/11/2026 (VINCOLANTI)

- **LOG-029, testo dei messaggi:** si conserva **anche il testo**, cifrato.
  - Nei canali che il server registra, il testo dei messaggi (con modifiche e cancellazioni) si salva cifrato, con una finestra a scorrimento.
  - A ogni sanzione, i messaggi dell'utente degli ultimi 3 giorni si copiano cifrati nell'archivio del caso, che resta come storico finché esiste il caso.
  - Si decifra solo all'apertura da parte dello staff autorizzato, dal pannello web tramite link, come le trascrizioni dei ticket (TKT-072).
  - Allegati sempre secondo D74.
  - Valgono le regole dei 30 giorni dell'owner (chiusura del server, azzeramento UTL-228).
- **Foto delle auto (FUN-017):** nessun interruttore per i canali con limite d'età. Ogni foto passa da un **controllo automatico dei contenuti per adulti**: classificatore tramite lo snodo AI, se c'è un fornitore con moderazione delle immagini. Se la foto risulta per adulti viene rifiutata o tolta, e si chiede un'altra foto. Restano le segnalazioni e la rimozione dello staff.
- **Prezzi di auto e tela:** vanno bene quelli scelti (auto da 150 a 12.000 monete; tela: pausa di 5 minuti, 10 monete per ogni minuto saltato). Si possono cambiare in ogni momento.

## D124 — Scelte dell'owner sulle voci lasciate fuori (23/11/2026, VINCOLANTI)

- **VOC-006:** non si fa. Il canale vocale ha già la sua chat di testo, due canali non servono.
- **UTL-121 (creazione guidata a passi):** sì. Una procedura guidata con bottoni e finestre, passo per passo, per creare un giveaway. Lo stesso schema serve per il **primo setup del bot** e per **modificare un setup già fatto**. Resta anche il comando unico con le opzioni.
- **UTL-216 («cerca qualsiasi cosa»):** sì. La ricerca usa i servizi AI con ricerca web tramite lo snodo AI (custode-ai); l'owner aggiungerà molte chiavi di servizi gratuiti. Senza un servizio adatto il comando lo dice.
- **FUN-138:** sì, come preferenza di ogni utente che la vuole: genere dei personaggi, personaggi preferiti e tipo di GIF (anime o non anime, …). Senza preferenze tutto resta come oggi.
- **CFG-036 (Patreon):** si prepara tutto, spento finché l'owner non mette le chiavi.
- **CFG-040, CFG-041:** si fanno secondo **D59**:
  - livelli **Gratuito, Premium, Ultra, VIP** e chiave propria;
  - Premium mensile, annuale o a vita, oppure con il boost di un server dell'owner;
  - limiti numerici diversi per livello (copie, messaggi, pannelli, …) scelti dall'owner dal pannello o con i comandi;
  - prezzi e sconti sono numeri che sceglie l'owner, non scritti nel codice.
- **UTL-110 (messaggi programmati con @everyone o @here):** sì. Solo il proprietario del server, o chi ha il permesso «Menziona @everyone» riletto al momento dell'invio; tetto di invii; log.

## D127 — Scelte dell'owner del 23/11/2026 sera (VINCOLANTI)

- **MUS-049, MUS-050, TKT-073:** restano fuori. Per TKT-073 l'utente scarica la trascrizione e la carica dove vuole.
- **BKP-022/023, raccolta dei modelli:** sì.
  - Raccolta di modelli di server, con voti e revisione prima della pubblicazione.
  - L'owner li modifica e li usa come modelli per creare un server e per ripristinare canali e ruoli tolti da un nuke.
- **BKP-004:** spiegazione da dare all'owner, poi si decide (cosa caricare di un backup, e se cancellare canali e ruoli già presenti; di base non si cancella).
- **BKP-040, regole di ammissione alla pagina di consenso per paese, rete o VPN:** sì, con il controllo VPN e di rete della verifica web (VER-026), senza conservare gli IP.
- **AI-003, chiave propria:** un server o un utente può usare le proprie chiavi API dei servizi AI al posto di quelle dell'owner, e così sblocca le funzioni VIP (D59).
- **AI-010, lunghezza della lore:** 1.000 caratteri di base, 2.000 da Premium in su. La lore viaggia con ogni richiesta all'AI: raddoppiarla per tutti raddoppia il costo di ogni risposta.
- **GIF (FUN-101, 104, 105, 115, 127, 128, 132, 133, 134, 135):**
  - elenco di tutti i servizi di GIF possibili, gratuiti e con chiave;
  - ogni servizio si attiva da solo quando l'owner mette la sua chiave nel `.env`;
  - il bot usa quelli che trova disponibili.
- **FUN-075, suoni:** sì. Oltre alla soundboard del server si possono usare i suoni delle soundboard degli altri server dove c'è il bot: menu con anteprima testuale, bottone di ascolto e bottone d'invio.
- **ECO-112 (bingo) ed ECO-087 (casa):** anche come immagini, generate con Pillow fuori dal ciclo principale.
- **MUS-034 (scala delle sanzioni) e moderazione:**
  - **mute a ruolo a tempo**;
  - **shadowban**: toglie l'accesso a tutti i canali di testo e vocali e lascia solo un canale di testo e un vocale dedicati, visibili agli shadowbannati e agli admin;
  - i ruoli tolti vanno nel log, per poterli ripristinare;
  - i canali dedicati sono esclusi dal sistema degli XP;
  - gerarchia e permessi come ogni sanzione.
- **MUS-015:** il filtro per paese vale per ogni servizio che dà il dato (Deezer già fatto; dove Spotify o altri lo danno, si aggiunge).
- **ALR-049:**
  - i dati Twitch e Kick si aggiornano anche dopo il collegamento, con un giro periodico usando i token salvati;
  - se il bot vede che un utente ha Twitch o Kick collegati al suo account Discord (connessioni del profilo, solo con OAuth `connections`), lo invita a collegarsi al pannello;
  - il bot poi lo integra nei server in comune con l'utente.
- **TKT-085:** la risposta dal sito diventa in tempo reale (aggiornamento della pagina, o webhook verso il canale) e può essere anonima, come le risposte anonime del modmail.
- **Liste AGCOM e ADM:** l'owner cerca gli indirizzi e li mette lui.

## D130 — Raccolta dei modelli (BKP-022/023) e regole di ammissione (BKP-040), giro r3bkp, 23/11/2026, opzione prudente, da confermare dall'owner

Attua D127.
- **Proposta (BKP-023):** `/admin-backup raccolta proponi copia: nome: descrizione:` (chi può creare copie, BKP-018). La struttura si **ricostruisce da zero** con i soli campi noti: niente ID, membri, ban, messaggi, emoji, impostazioni, permessi di singoli utenti; nei nomi e negli argomenti dei canali si tolgono caratteri invisibili, menzioni (`@everyone`, `<@…>`) e link; `@everyone` non porta mai permessi pericolosi; negli overwrite di canale non si concede mai un permesso pericoloso. Tetti: 100 ruoli, 50 categorie, 200 canali, 50 canali per categoria; nomi doppi o vuoti rifiutati. Al massimo 3 proposte in attesa per server. Nome 3-60, descrizione 300.
- **Revisione:** la decide l'owner del bot **dal pannello** (`/proprietario/modelli`: approva, rifiuta, toglie un approvato, modifica nome, descrizione e struttura; ogni modifica rifà la stessa ricostruzione). Niente comando `/owner`: il gruppo è quasi pieno e la struttura si modifica meglio in una pagina. Un modello non approvato non si vede né si vota né si usa, da nessuno tranne l'owner.
- **Elenco e voti:** `/admin-backup raccolta elenco|vota|usa|mie` (per chi può usare `/admin-backup`; il voto è uno per persona e per modello, ripetuto conta una volta). Elenco pubblico in sola lettura nel pannello, `modelli`, senza accesso (solo nome, descrizione, lingua, conteggi, voti; mai la struttura).
- **Uso:** «Crea la struttura» (riusa per nome, crea il resto, come gli altri modelli) oppure «Solo ciò che manca» dopo un nuke: aggiunge ruoli, categorie e canali assenti, **non tocca** nessun ruolo o canale esistente né `@everyone`, non cancella; **solo il proprietario del server** lo conferma. Un ruolo con permessi pericolosi nasce **senza** quei permessi a meno che il proprietario del server prema «Confermo i ruoli con permessi pericolosi» (la chiede solo a lui; per tutti gli altri non c'è).
- **Dati:** tabelle `backup_raccolta` e `backup_raccolta_voti` (0950); il modello va via con il server proponente (90 giorni dopo l'uscita), il voto con la persona.
- **BKP-040 (regola di ammissione):** interruttore del server «Chiedi di non usare VPN o proxy prima del consenso» nella pagina del pannello `/server/<id>/join` (spento di base, colonna `join_controllo_rete`, 0951). Al clic su «Autorizzo il rientro» si chiama lo stesso `verify_vpn.rileva` della verifica web (VER-026: elenchi, ASN, Tor, intestazioni dei proxy fidati, servizio esterno già configurato). **Nessun IP salvato**: non si usa `verify_vpn_staff.controlla` (che cifra l'IP), non si scrive nello storico VPN né si avvisa lo staff; l'IP vive solo in memoria per quella richiesta. Se bloccata: 403 con «spegni VPN o proxy e riprova», senza dire il metodo e senza creare il link OAuth. Se il controllo non riesce: la persona non passa. Le regole per **paese** non si fanno: servirebbe il paese dall'IP e un dato in più sul consenso (resta la regola VPN/rete, come chiede D127).

## D123 — Giro r2log029: scelte aperte di LOG-029 e FUN-017 (23/11/2026, opzione consigliata, da confermare dall'owner)

Attua D122. Tutto ciò che D122 non fissa è deciso qui.

### LOG-029, testo dei messaggi cifrato
- **Chiave:** `LOG_TESTI_KEY`; se manca si usa `TICKET_TRASCRIZIONI_KEY` e poi `OAUTH_ENCRYPTION_KEY` (D114). Senza nessuna chiave il testo **non si salva** (mai in chiaro). Più chiavi separate da virgola per ruotarla. La chiave non entra mai nel database.
- **Cosa si cifra:** una riga per evento (scritto, modificato, cancellato) in `log_messaggi_testi`, AES-256-GCM legata a server, messaggio, autore ed evento (una riga copiata altrove non si apre). In chiaro restano server, canale, messaggio, autore, tipo di evento e momento. Allegati: solo nome pulito, tipo e peso, dentro il dato cifrato (D74: mai byte né link).
- **Quali messaggi:** quelli dei canali che il server registra: log avanzato acceso e almeno uno tra «messaggi cancellati» e «messaggi modificati» acceso, canale, categoria, utente, ruolo e prefisso non ignorati, niente bot. Testo al massimo 4.000 caratteri.
- **Finestra e tetti:** 7 giorni a scorrimento, pulizia dal registro dei dati (`Scadenza("creato", 7)`); in più al massimo 20.000 righe per server (potatura oraria, restano le più recenti). Scrittura a lotti ogni 15 secondi (una transazione per lotto, mai una scrittura per messaggio); in attesa al massimo 300 righe per server e 5.000 in tutto, oltre si scarta (un picco in un server non toglie spazio agli altri). Allo scarico del cog il lotto in attesa si scrive.
- **Copia nel caso:** a ogni sanzione (warn, timeout, kick, ban, tempban) i messaggi dell'utente degli ultimi 3 giorni (al massimo 1.000, 2 MB) si decifrano e si ricifrano in un solo dato legato a server e caso (`moderation_archivio_utente.testi_cifrato`). Restano finché esiste il caso (stessa riga, stessa cancellazione: caso tolto, `/privacy` dell'utente, chiusura del server e azzeramento UTL-228 come D121). Il file del comando non ha il testo.
- **Apertura:** solo staff. Dal comando esistente `/mod-casi caso chat archivio:sì` (risposta privata con il link, se `WEB_PANEL_PUBLIC_URL` c'è). Dal pannello: `/server/<id>/moderazione/archivio/<caso>`, decifrata all'apertura. Chi vede: «Gestisci server» o «Modera i membri» ADESSO (rilettura a ogni richiesta, oltre al livello del pannello). Caso inesistente, senza testo, altro server, utente non autorizzato, chiave cambiata o dato alterato: la stessa pagina 404. CSP senza script e senza risorse esterne, `sandbox`, `no-store`, ogni testo con escape.
- **Registro dei dati e base giuridica:** `log_messaggi_testi` e `moderation_archivio_utente` cancellano su richiesta dell'utente (`/privacy`) e con il server; il dato cifrato non si esporta (dentro c'è anche ciò che hanno scritto altri). Base giuridica scritta nelle note del registro: sicurezza e moderazione del server (GDPR art. 6.1.f).
- **Non fatto:** la pagina non mostra le risposte di altri utenti né il contesto intorno ai messaggi (solo ciò che ha scritto l'utente). Gli allegati non si scaricano.

### FUN-017, controllo delle foto
- **Come:** tipo di lavoro nuovo dello snodo AI, `moderazione_immagine` (`AI_TIPI_<NOME>=moderazione_immagine`), endpoint `/moderations` compatibile OpenAI. «Per adulti» = categoria `sexual` o `sexual/minors` segnalata, oppure punteggio `sexual` da 0,5 o `sexual/minors` da 0,2.
- **Chi vede la foto:** solo fornitori che non addestrano sui dati e gratuiti (è la foto di una persona). Non conta sulla quota di nessuno e non dipende dall'interruttore AI del server (è una protezione, non una funzione di chat).
- **Nessun fornitore o servizio fermo (scelta aperta, D123):** la foto **passa come oggi**, con segnalazioni (3 persone) e staff, e resta «da controllare»: al primo controllo riuscito, alla prossima visualizzazione, se risulta per adulti si toglie. Alternativa non scelta: rifiutare tutte le foto finché non c'è un fornitore (toglierebbe la funzione, contro D18).
- **Foto già salvate:** colonna `controllata_il` (0902), vuota per quelle vecchie: alla prossima visualizzazione si controllano; per adulti si tolgono, pulite si segnano. Una foto sostituita riparte da non controllata o controllata.
- **Fornitore consigliato:** nessuno acceso di base. Nel file `config/ai_fornitori.env.example` c'è la voce `MODERA_IMG` in commento (omni-moderation); l'owner sceglie.

### Chiavi per l'owner
- `LOG_TESTI_KEY` nel `.env` (consigliata una chiave diversa dalle altre; vuota = si usa quella delle trascrizioni). Per il link: `WEB_PANEL_PUBLIC_URL`.
- Per le foto: un fornitore di moderazione immagini nel file dei fornitori AI (chiave a scelta dell'owner).


## D128 — Mute a ruolo come gradino della scala e shadowban (#115, giro r3mod), 23/11/2026, opzione prudente, da confermare dall'owner

- **Mute a ruolo a tempo (MUS-034 nella scheda; è la scala delle sanzioni):** il mute con il ruolo «muto» aveva già la durata (MOD-014). Ora è anche un gradino della scala (`/admin-sicurezza escalation set-step action:Mute (ruolo) duration_minutes:`), tetto 28 giorni come gli altri gradini (il comando `/mod-sanzioni mute` arriva a 1 anno). Un solo punto: `core/moderation_mute_azione.py` (ruolo, stato `mute_stato` con la fine, caso e scadenza nello scheduler). Dopo un riavvio la scadenza vale: stato e coda stanno nel database. Il caso è del tipo `mute_role` (così la fine lo chiude). Il moderatore del warn deve poter «moderare i membri» (come per il timeout).
- **Shadowban:** `/mod-sanzioni shadowban dai|togli|canali` (sotto-gruppo nuovo di `/mod-sanzioni`, che ora ha 9 figli e 3 sotto-gruppi). Livello come la quarantena (mod). Azione `shadowban` concedibile a un ruolo con CFG-024.
  - Il membro perde tutti i ruoli (tranne quelli gestiti da Discord) e riceve il ruolo «Shadowban», che nega `view_channel` su ogni canale tranne i due dedicati. I ruoli tolti si scrivono PRIMA in `moderation_shadowban` (0930), con chiave unica `(server, utente)`: due shadowban insieme sulla stessa persona ne fanno passare uno solo; chi è già dentro non perde i ruoli salvati. I ruoli tolti stanno anche nel log di moderazione.
  - I due canali (testo e vocale) li crea il bot se mancano (nome «shadowban») o li sceglie lo staff con `/mod-sanzioni shadowban canali`; la scelta toglie a `@everyone` la vista su quei canali (sono visibili solo a shadowbannati e admin). Ruolo e canali stanno in `moderation_shadowban_config`. I canali nati dopo ricevono il blocco da `on_guild_channel_create`. Chi è in vocale è spostato nel vocale dedicato.
  - Si toglie con `togli` o alla scadenza: ridà solo i ruoli che il bot può ridare oggi. Chi esce e rientra resta in shadowban fino alla fine.
  - Mai su proprietario, bot, chi sta sopra il bot o alla pari; prima si controllano i permessi del bot («Gestire i ruoli» e «Gestire i canali»).
  - XP e statistiche: i due canali e il ruolo sono esclusi sempre (anche con i canali XP in modo «solo questi»); `ConfigLivelli.canali_sempre_esclusi` e `ActivitySettings.sempre_esclusi`.
  - **Limiti noti:** un ruolo gestito (booster, integrazione) non si può togliere: se ha un permesso esplicito su un canale, può ancora vederlo (il bot lo dice solo se la modifica dei ruoli fallisce). I thread privati a cui l'utente era già stato aggiunto non si toccano. Lo shadowban non è un gradino della scala (solo il mute lo è).
- Migrazione usata: 0930.

## D129 — GIF di tutti i servizi, suoni di altri server, bingo e casa come immagini (giro r2fun, #131, #125), 23/11/2026, opzione prudente, da confermare dall'owner

- **GIF (D127):** i servizi senza chiave (nekos.best, purrbot, waifu.pics, otakugifs) sono accesi; Giphy e Tenor si accendono da soli quando la loro chiave (`GIF_GIPHY_KEY`, `GIF_TENOR_KEY`) è nel `.env` (`GIF_<FONTE>_ATTIVO=no` li spegne). Ordine: prima le fonti con la categoria giusta (a turno), poi quelle di ricerca libera come ripiego. Ogni fonte ha un tetto di richieste all'ora (`GIF_<FONTE>_QUOTA_ORA`; Giphy 90, sotto le 100 della chiave beta), cache, `safe_get` e domini ammessi. Tutto SFW (rating g su Giphy, `contentfilter=high` su Tenor, categorie senza parole per adulti).
- **Tenor:** da gennaio 2026 non accetta nuovi clienti API (pagina ufficiale letta il 23/11/2026): l'adattatore c'è per chi ha già una chiave. **Klipy, waifu.im, nekosia: nessun adattatore** (documentazione o condizioni non leggibili): si aggiungono quando c'è una pagina chiara o un permesso scritto.
- **Le 10 voci:** FUN-104 (canta) ha una categoria vera (otakugifs «sing»). Le altre 9 (salta, supplica, sposa, fragola, rose, arresta, massaggio, ruba, rombo) non hanno una categoria in nessun servizio gratuito letto: le coprono Giphy e Tenor con la ricerca libera (serve una chiave). Senza chiave rispondono con la sola frase; restano nel cricchetto `SENZA_FONTE` (ora significa «senza categoria»).
- **Suoni di altri server (FUN-075):** `/music suono-altri` (il gruppo `/music` va a 25 figli, il tetto di Discord; i gruppi di primo livello sono già 58+2, nessun gruppo nuovo). Di base **un server NON mette a disposizione i suoi suoni**: lo sceglie un admin con `/admin-musica suono-condividi condividi:sì`. Un server può anche chiudere ai suoi membri i suoni degli altri (`usa-esterni:no`, di base sì). Il nome del server d'origine si mostra solo se è pubblico (funzione `DISCOVERABLE`), altrimenti «un altro server». «Ascolta in anteprima» manda il file **solo a chi lo chiede** (in memoria, mai su disco; se il file non si legge, il link); «Invia» fa suonare nel canale vocale di chi preme, con lo stesso percorso di `/music suono` (servono i permessi «Usa soundboard» e «Usa suoni esterni» a lui). Pausa di 15 s e 12 suoni all'ora per persona (anteprime comprese), in tutti i server; più la pausa di 10 s già di `/music suono`. Al clic si ricontrolla che il server d'origine condivida ancora. **Da provare dal vivo:** se Discord accetta un suono esterno quando il bot musicale che suona non è nel server d'origine (nel caso peggiore il bot dice «non riuscito»).
- Migrazione 0940 (`suoni_condivisione`).

- **Bingo e casa come immagini (ECO-112, ECO-087):** cartella 528x336 e stanza 688x528, misura fissa, Pillow in `run_image_task`; se il disegno fallisce restano il testo del bingo e le emoji della casa. I nomi dei mobili stanno nei testi (`mon_casa_m_*`), non nell'immagine; niente emoji disegnate (il font non le ha).

## D133 — Scelte dell'owner del 24/11/2026

- **BKP-004:** nel menu delle parti da caricare si aggiunge anche la scelta «cancella prima canali e ruoli che ci sono già» (come Xenon). Di base è spenta; la può usare solo il proprietario del server, con una conferma esplicita; i ruoli gestiti e quelli sopra il bot non si toccano. Sostituisce il «non offerto di proposito» di D108. Fatto il 24/11 (SPEC §11.18).
- **ECO-101 e ECO-105:** si fanno (creature di fantasia al posto dei galli; mischia fino a 6 con regole su misura).
- **AI-010:** confermata la scelta di D127 (lore 1000 caratteri gratis, 2000 da Premium in su).

## D125 — Scelte aperte nel giro r1premium (23/11/2026, da confermare dall'owner)
Scelte fatte con l'opzione consigliata; l'owner le cambia con un comando o un valore.
- **Limiti predefiniti = valori di oggi per tutti i livelli** (10 copie di backup, 25 serie programmate, 25 pannelli ticket, 2 invii con @everyone al giorno). Cambiano solo quando l'owner li imposta con `/owner premium piano azione:limite`.
- **Nessun prezzo nel codice.** Prezzi in centesimi e sconti (percentuale, livello, periodo, durata) si scrivono con `/owner premium piano`. Il bot li mostra in `/premium info`; non incassa: il pagamento resta fuori (D5, `/owner premium grant`) o Patreon.
- **Chiave propria = VIP** per la persona e per i server di cui è proprietaria, finché la chiave c'è. La chiave sta cifrata (AES-GCM, `OAUTH_ENCRYPTION_KEY`, dato associato ambito+id+servizio), mai nei log, mai nell'esportazione dei dati, si toglie con `/admin-bot premium chiave azione:togli` o dal pannello. Il router AI (custode-ai) la legge con `core.ai_chiavi_proprie.chiave_per(servizio, guild_id=, user_id=)`: prima quella della persona, poi quella del server, poi quelle dell'owner. Il collegamento al router resta da fare in quell'area.
- **Patreon: grazia di 45 giorni.** Ogni evento del webhook rinnova la concessione `patreon` per 45 giorni; se i rinnovi spariscono il livello scade da solo. Le disdette (eventi `delete`, stato non attivo) lo tolgono subito. I livelli Patreon si associano con `/owner premium piano azione:patreon chiave:<tier> livello:<livello>`. Un account Patreon appartiene a una sola persona Discord (l'ultimo collegamento vince). Il collegamento parte dal pannello (`patreon_service.crea_stato` + `url_collegamento`) e torna a `/patreon/callback`; lo scollegamento è `patreon_service.scollega`.
- **@everyone programmato:** vale il permesso di chi ha programmato, riletto all'invio. Se manca o il tetto è raggiunto, il messaggio parte lo stesso ma con la menzione resa inerte e l'autore è avvisato in privato. Il posto del tetto si restituisce se l'invio fallisce.
- **Boost:** si sommano `MAIN_GUILD_ID` e `PREMIUM_BOOST_GUILD_IDS` (ID separati da virgola). Il boost dà Premium al server il cui proprietario lo fa, come prima.
- **Livello di una persona che non è proprietaria** non passa al server (i posti premium restano il modo di dare il Premium a un server, CFG-034).


## D132 — `/owner` sotto i 6.800 caratteri senza gruppi nuovi (23/11/2026, opzione consigliata, da confermare dall'owner)
`/owner` pesava 7.898 su 8.000. Scelta: **accorciare** descrizioni, scelte e traduzioni en-US (via i prefissi «Solo proprietario», testi lunghi delle opzioni, nomi delle scelte), senza togliere funzioni. Peso finale 6.333. Nessun secondo gruppo owner: i gruppi di primo livello restano 60 su 60 (D56) e nessuno è stato unito. Se `/owner` torna sopra 6.800, si sposta un sotto-gruppo intero (`radio`, il più pesante) in un gruppo nuovo, dopo aver unito due gruppi piccoli e affini.
Chiavi AI proprie (D125): il router le usa. Chi ha messo la chiave di un servizio la usa per quel servizio (prima la persona, poi il server), con tutti i suoi crediti, fuori da quote e pause dell'owner e senza costo per l'owner. Mai per altri, mai nei log. Se la chiave manca o non funziona, si passa ai fornitori dell'owner.

## D131 — Giro r4web: ALR-049, TKT-085, MUS-015, AI-010 (attuano D127; 23/11/2026, opzione consigliata, da confermare dall'owner)

- **ALR-049, giro periodico.** Ogni 12 ore (il primo 5 minuti dopo l'avvio del sito), al massimo 500 persone per giro (le meno recenti per prime), mezzo secondo di pausa tra una e l'altra. Per ognuno: rinnovo del token Twitch se scade, lettura di tipo e nome del canale, scrittura su Discord **solo se qualcosa è cambiato** (meno richieste). Token revocato (rinnovo con risposta 400, o 401 dopo un solo rinnovo) o canale diverso da quello collegato: i valori di Twitch tornano a «no» su Discord (se il suo token vale ancora) e la riga si cancella. Un 401 sul rinnovo è un errore delle nostre chiavi, non una revoca: nessuno si scollega. Guasti passeggeri (rete, 5xx): si conta l'errore e si riprova al giro dopo. Al primo 429 il giro si ferma. Di base parte con il sito (`giro_ruoli_collegati`), serve il pannello acceso e le chiavi Twitch.
- **ALR-049, invito.** Non si cambia l'accesso al pannello: nella pagina dei ruoli collegati un bottone facoltativo chiede a Discord `identify connections` (stesso indirizzo di ritorno, `state` di altro scopo, monouso, legato alla sessione). Si leggono solo i **tipi** delle connessioni e si salvano due sì/no (`ha_twitch`, `ha_kick`); il token si revoca subito. Senza il clic il bot non legge niente; «Dimentica» cancella. L'invito è un avviso nella pagina (nessun messaggio privato non richiesto). «Integra nei server in comune»: la pagina elenca i server in comune dove esiste un ruolo con un requisito di collegamento (`Role.tags`); è Discord ad assegnare il ruolo appena i valori sono aggiornati.
- **ALR-049, Kick: non fatto.** Kick ha un'API OAuth pubblica (con PKCE), ma i canali non dicono se sono affiliati o partner, i metadati dei ruoli collegati sono già 5 (il massimo di Discord) e l'elenco delle connessioni di Discord non include Kick tra i tipi documentati (se un giorno comparirà, il «sì» di Kick si vede già nella pagina). Si fa solo se l'owner sceglie quale metadato togliere e cosa chiedere a Kick (per esempio «ha un canale»).
- Migrazioni usate: 0960.
- **TKT-085, tempo reale: controllo breve con ETag, non SSE né WebSocket.** La scheda del ticket chiede `.../stato` ogni 5 secondi (fino a 30 se non cambia niente; fermo se la scheda è nascosta); risposta 200 con ETag oppure 304. Nessuna connessione aperta: niente tetto di connessioni da gestire. Limite 40 richieste al minuto per persona (più il limite generale per IP). Il contenuto è solo lo stato: aperto o chiuso, chi ha in carico, ultimo messaggio dell'utente, ultima attività. **Il testo dei messaggi non si mostra** (D74, D101): si legge nel canale; la scheda dice «l'utente ha scritto». «Non esiste» e «non puoi» hanno la stessa 404. La CSP della sola scheda ammette `script-src 'self'` e `connect-src 'self'` (script nel file statico, mai in linea).
- **TKT-085, risposta con webhook.** Il bot usa un suo webhook per canale (`iYokai Ticket`, creato al primo bisogno, riconosciuto dal proprietario e dal nome; in un thread vale il canale padre con `thread=`). Il token del webhook sta solo in memoria. Nome: «Mario (dal sito)» con la sua foto; anonimo: «Staff» con l'icona del server (come il modmail, ma senza il nome del server). Tutte le menzioni spente, 1500 caratteri, 10 risposte al minuto per persona, permessi e CSRF riletti a ogni richiesta. Serve «Gestisci webhook» al bot nel canale: senza, o se Discord rifiuta il nome, esce come messaggio normale del bot («Staff (dal sito)» se anonimo). **Anche la risposta anonima ha un autore nei log del bot** (utente, server, ticket): lo staff non lo vede nel canale, chi gestisce il bot sì.
- **MUS-015, Spotify (D127 + D73).** D73 teneva le chiavi solo su Lavalink. Per avere `available_markets` serve la Web API di Spotify, quindi **servono le chiavi anche nel bot**: sono **facoltative** (le stesse `SPOTIFY_CLIENT_ID` e `SPOTIFY_CLIENT_SECRET`, già nell'`.env.example`). Senza, il filtro per paese vale come prima (Deezer e plugin che danno il dato) e i brani Spotify passano. Con le chiavi e un paese scelto dal server (o globale), i brani Spotify che non dichiarano i paesi vengono arricchiti prima del filtro. Credenziali «client credentials» (nessun dato dell'utente), solo due indirizzi fissi, mai un indirizzo scelto da un utente. Tetti: 50 brani per richiesta, al massimo 2 richieste per comando, 2.000 al giorno, attesa massima 5 secondi, cache di un giorno (5.000 brani), pausa al 429. Se Spotify non risponde o non dice i paesi (elenco vuoto), il brano passa. Con la politica di Spotify per le app in modalità sviluppo (quota e accesso possono cambiare) la funzione può smettere di dare dati senza rompere la musica: la prova dal vivo è in `VERIFICA_LIVE.md`. Altre fonti senza dato (Apple Music, Tidal, YouTube): nessun filtro.
- **AI-010, lunghezza della lore (D127).** Il tetto riguarda le parole scritte dall'admin: **1.000 caratteri di base, 2.000 per i server con Premium** (stessa regola di `guild_has_premium_access`: acquisto del server, abbonamento, posto, boost, whitelist; con lo sblocco «alpha» di tutti i moduli, oggi, tutti hanno 2.000). Il testo del tema pronto si aggiunge e non toglie spazio. Il controllo è uno solo (`imposta_lore`), usato dal comando e dal pannello: oltre il tetto il salvataggio si rifiuta con un messaggio che dice il numero (e, senza Premium, che con Premium arriva a 2.000); prima si tagliava in silenzio. Il campo del comando ammette 2.000 (Discord non sa il livello del server). **Quando finisce il Premium** la lore lunga resta salvata, ma ogni richiesta all'AI riceve solo i primi 1.000 caratteri; per salvarne una nuova bisogna accorciarla. In caso di errore nel leggere il livello vale 1.000. I livelli Premium separati (Premium, Pro…) non esistono ancora nel codice: «da Premium in su» vale per ogni forma di Premium; se arriveranno più livelli si cambia `lore_massima`.
- Migrazioni usate in r4web: 0960 (restano 0961-0969).

## D135 — Chiavi AI proprie verificate e Patreon dal pannello (#122, controllo finale), 24/11/2026, opzione consigliata, da confermare dall'owner

Corregge D59 e D127 su tre punti.
- **Una chiave propria dà il VIP solo se il servizio l'ha accettata.** Al salvataggio la chiave si prova presso il servizio (elenco dei modelli: non consuma token). Valgono solo i servizi della tabella dei fornitori (`AI_FORNITORI`): un nome inventato è rifiutato. Si salva con `verificata = true` (colonna in 0970; le chiavi già presenti ripartono come non verificate e vanno rimesse). Il router usa solo chiavi verificate; se il servizio risponde 401/403 la chiave si segna non valida e il VIP decade. Un errore di rete o 5xx non la invalida.
- **Un account Patreon ricollegato a un altro Discord toglie la concessione `patreon` al vecchio utente.**
- **Pannello:** pagina personale `/premium` con «Collega Patreon» / «Scollega» (POST con CSRF, stato monouso di 10 minuti). Senza le chiavi di Patreon le rotte non esistono (stessa 404). Il ritorno da Patreon resta nel piccolo server di `patreon_server.py`, che rimanda a `/premium?patreon=ok`.

## D134 — Creature di fantasia (ECO-101) e combattimento a più giocatori con regole su misura (ECO-105), giro r8eco, 24/11/2026, owner: vanno fatte (D18)

Sostituisce per queste due voci la scelta di D104 («la creatura è il proprio animale»): `/sala lotta` resta com'è, le due voci hanno ora i loro comandi.
- **ECO-101, creature (yokai e spiriti, mai galli):** 8 specie (kitsune, tanuki, kappa, tengu, nure-onna, oni, karakasa, bakeneko). Si **comprano al negozio** come ogni oggetto: lo staff sceglie l'azione «Evoca una creatura» con la specie (`/admin-giochi oggetto-azione azione:Evoca una creatura specie:N`), chi compra lo usa con `/monete usa`. Pezzo consumato e creatura creata nella stessa transazione; con 5 creature (il tetto per persona) il pezzo **non** si consuma.
- **Forza:** da 50 a 70 alla nascita (a caso), **+1 a ogni vittoria**, tetto **90**. **Sconfitta: -10 di forza; sotto 30 la creatura fugge e si perde** (si cancella: l'oggetto va ricomprato). Chi vince prende la posta; la posta è sempre in monete del bot (mai comprate con soldi veri).
- **Scontro:** `/giochi sfide scontro membro posta [creatura]` (la tua più forte di base), `/giochi sfide creature` (elenco, forza, vittorie). Solo lo sfidato sceglie la sua creatura dal menu (accettare e scegliere sono un gesto solo); chi sfida può annullare. Vince la creatura A con probabilità forzaA/(forzaA+forzaB). Una sola transazione: creature bloccate in ordine di ID, saldi bloccati in ordine di ID, controllo che **entrambi** abbiano la posta, tetto al saldo del vincitore, forze, fuga e storico (`economia_lotte_creature`). Blocco personale (ECO-155) rispettato.
- **ECO-105, `/sala combattimento puntata [vite] [giri] [oggetti]`:** da 2 a 6 giocatori, regole scelte da chi crea e mostrate nella sala d'attesa: puntata, **vite** 1-5 (di base 3), **giri** 3-20 (di base 10: i giri sono le mosse di tutti, a turno), **oggetti** sì/no (di base no). Iscrizione a tempo (45 s) con Entra/Esci, **avvio dal creatore** (Avvia, o allo scadere se ci sono almeno 2 giocatori). Turni con bottoni (un bottone per ogni avversario in piedi): il colpo va a segno 7 volte su 10 e toglie una vita. Con gli **oggetti ammessi** ognuno ha, una volta a partita e gratis, una **pozione** (+1 vita, mai oltre le vite iniziali) e uno **scudo** (para il prossimo colpo subito); usarli costa il turno. Gli oggetti sono quelli della partita, non quelli dell'inventario del negozio.
- **Tempi:** 30 secondi a turno: chi non muove **esce**. Fine: ultimo in piedi, o a fine giri chi ha più vite (i pari dividono il piatto, il resto di una divisione va ai primi). Il vincitore prende il **piatto intero** (nessuna commissione). **Annulla** vale solo nella sala d'attesa: a partita iniziata il bottone non c'è più (il creatore eliminato non può riprendersi la puntata). Restano come rimborso a tutti solo la partita oltre 11 minuti e l'errore. La partita si chiude in modo atomico alla mossa vincente (flag `finita` prima di ogni await, controllato da ogni bottone) e `chiudi_gruppo` paga una sola volta (le righe si cancellano con `DELETE ... RETURNING`: pagamento o rimborso, uno solo vince). Puntate tolte a tutti insieme all'avvio (`partite_repo.apri_gruppo`), una partita per canale, rimborso all'avvio del bot per le righe `sala:` rimaste.
- **Dati:** `economia_creature`, `economia_lotte_creature` (0965), CHECK di `shop_items.azione` esteso a `creatura`; tutte nel registro dei dati (si cancellano con l'utente, si esportano).


## D136 — Shadowban: chi sceglie i canali, scadenza e autoruoli (#115, controllo finale), 24/11/2026, opzione prudente, da confermare dall'owner

- **`/mod-sanzioni shadowban canali`:** oltre al livello mod, chi comanda deve avere «Gestisci canali» su **ogni canale scelto** (riletto con `permissions_for` al comando e di nuovo dopo la conferma). Se un canale scelto è oggi visibile a `@everyone` (nessun divieto esplicito), il bot mostra un riepilogo con Conferma/Annulla (60 secondi) prima di nasconderlo; un canale già nascosto non chiede conferma. Il blocco sugli altri canali tocca solo il ruolo Shadowban del bot, non i permessi di altri.
- **`togli`:** la scadenza programmata si annulla solo dopo che lo shadowban è stato tolto davvero; se Discord rifiuta, la scadenza resta e si può riprovare.
- **Ruoli automatici o su richiesta (tutti):** a chi è in shadowban non si danno ruoli da autoruoli, ruolo «verificato» (la verifica non si completa), menu a tasti (risposta riservata «sei in shadowban»), premi (World Boss, giveaway, reputazione, classifica, livelli, negozio, oggetti), conteggio, ticket, inviti, comandi personalizzati, ruoli vocali, attività, in diretta, compleanno, clan, ruolo personale, sincronizzazione tra server, ruolo a scelta. Un solo punto: `add_roles_se_libero` / `ruoli_negati` in `core/moderation_shadowban.py` (stato letto dal database a ogni richiesta, quindi vale in qualunque ordine arrivino gli eventi; se il database non risponde si lascia passare). Un test di struttura (`tests/test_shadowban_ruoli_automatici.py`) vieta `add_roles` diretto in quei file.
- **Restano libere:** le azioni dello staff fatte a mano (`/ruoli`, accettare una candidatura, ripristino di un backup, azioni di sicurezza, anti-raid/anti-nuke, quarantena e mute). Il ruolo «non verificato» (restrittivo) si può dare comunque.

## D137 — Riordino dei comandi per famiglie e 10 comandi diretti (#122), 24/11/2026, approvato dall'owner

Cambia D56 sui limiti e sposta i gruppi. Nessuna funzione si toglie: si sposta o si rinomina il gruppo.
- **Regola.** Ogni comando sta nella sua FAMIGLIA, che è il prefisso del nome del gruppo (Discord ammette solo 3 livelli: gruppo, sotto-gruppo, comando): `music-playlist`, `giochi-sala`, `giochi-mondo`, `giochi-animali`, `utility-web`, `utility-server`, `monete-clan`, `admin-sicurezza-antiraid`, `admin-ticket-pannelli`, ecc.
- **Mappa e migrazione dei percorsi.** La mappa completa (419 coppie) è nella migrazione `0972_percorsi_comandi_riordino_d137.sql`: seguono comandi spenti, ruoli richiesti, registro modifiche, ultimo comando usato e conteggio dei comandi per giorno. Test: `tests/test_migrazione_percorsi_d137.py`.
- **Unioni.** `/chiedi` e `/cerca-comando` diventano `/help` (testo libero: con l'AI risponde l'assistente, altrimenti la ricerca per descrizione; senza testo il pannello). `/monete conto portafoglio` sparisce: `/monete balance immagine:sì`.
- **Scelte di nome.** `/admin-giochi evento` (avvia, chiudi, riffa) si fonde nel sotto-gruppo `evento` già presente in `/admin-economia-negozio` (codice, bonus, casuali, server): stesso nome, nessuna perdita. `/admin-ruoli menu` entra in `/admin-ruoli-menu` senza rinomine (nessuna collisione con `aggiungi-molti`, `opzione`, ecc.). `/admin-livelli premi` (modo di assegnazione) diventa `/admin-livelli premi modo`; i comandi di `/admin-ruoli premio` entrano nel sotto-gruppo `premi`. `/giochi dado` diventa `/giochi dado-del-giorno`. `/music queue`, `clear-queue`, `skipto` diventano `/music coda mostra`, `svuota`, `salta-a`. `/admin-tag` sparisce: `tag` è `/admin-messaggi-tag`, `risposte` è `/admin-automazioni risposte`.
- **`/owner-radio`** è un gruppo del solo server dell'owner, come `/owner` (controllo OWNER_ID, mai nell'albero globale; `GRUPPI_SOLO_OWNER`). Come `/owner` e `/admin-bot` non si spegne mai con la politica dei comandi (`/admin-bot-config` compreso).
- **Comandi diretti (10).** `/play`, `/skip`, `/stop`, `/pause`, `/resume`, `/queue`, `/ban`, `/kick`, `/mute`, `/shadowban` sono comandi di primo livello che chiamano la STESSA funzione del comando lungo, con gli stessi controlli (permesso predefinito, livello staff, lista nera, abbonamento). Politica dei comandi spenti e statistiche guardano il percorso vero (spento `music play` = spento `/play`). Il nome è uguale in tutte le lingue; la descrizione è quella del comando lungo. Una sola tabella: `core/comandi_diretti.py` (`DIRETTI`).
- **Limiti (sostituiscono quelli di D56).** Comandi di primo livello globali: tetto 100 (limite Discord), avviso a 90, contando `/premium` e `/vip`; `/owner` e `/owner-radio` stanno solo nel server dell'owner. Figli: al massimo 25 per gruppo (18 resta un obiettivo, un avviso). Profondità 3. Peso: ogni gruppo si calcola come se ogni traduzione fosse più lunga del 30% della versione più lunga tra it ed en, per ogni campo (nome 32, descrizione 100, nome scelta 100; i valori delle scelte non si traducono), o con la traduzione vera se più lunga; limite 8.000, avviso a 6.800. Dopo il riordino: 54 gruppi globali, il più pesante `/admin-alert` a 7.478.
- **Effetti da sapere.** Le sospensioni dei giochi (`RADICI_DI_GIOCO`) ora valgono anche per `/monete mercato` e `/giochi tela` (stanno sotto `monete` e `giochi`).

## D139 — Sandbox obbligatoria, niente ripiego grafico (25/11/2026, richiesta dell'owner)

Ogni file degli utenti (immagini, allegati, avatar, sfondi) si apre solo nel servizio `iyokai-sandbox`.
Se il servizio non risponde, il lavoro si rifiuta con un messaggio chiaro e una riga nel log: rank card,
avatar, sfondi dei benvenuti e level-up non si disegnano con un ripiego, si saltano. Il servizio lavora
al massimo su 3 file insieme, con 2 GB di memoria. Il cancello dei download (4 insieme, 48 MiB in volo)
vale per i log dei messaggi; per ticket, ModMail e backup è il prossimo passo.
