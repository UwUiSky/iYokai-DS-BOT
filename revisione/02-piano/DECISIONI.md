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
- Precisazione dell'owner (08/11): IP dopo un **kick 180 giorni**, dopo un **ban 1 anno** dal ban (lo sblocco non lo
  cambia). **IP, e-mail e numeri di telefono** dell'account si danno a terzi **solo su richiesta di un giudice** e solo per
  la persona indicata; tutto il resto si dà su richiesta con `/privacy`. Nota di chi sviluppa (GDPR art. 15): la persona
  stessa ha diritto ai propri dati, IP compreso; si danno solo a lei, dopo aver verificato che è lei (login Discord dal
  pannello), mai ad altri senza ordine del giudice.
