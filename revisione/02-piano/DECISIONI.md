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
