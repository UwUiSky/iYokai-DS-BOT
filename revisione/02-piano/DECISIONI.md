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
- D19, D20, D21, D22, D23: **indicate dall'owner** il 05/10/2026.

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
