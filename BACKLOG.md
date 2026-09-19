# BACKLOG.md — Proposte esterne, valutate

**Questo file non è `SPEC.md`.** `SPEC.md` resta il registro dello
scope deciso e il suo stato reale — niente entra lì senza essere
prima valutato e accettato qui.

## Origine

L'utente ha esposto `SPEC.md` (nella versione con 84/266 voci fatte)
a tre AI in sequenza — Gemini, poi ChatGPT (con la trascrizione
Gemini come contesto), poi Grok (con `SPEC.md` + le trascrizioni di
Gemini e ChatGPT come contesto, quest'ultima inizialmente incompleta
e poi integrata). Grok ha prodotto una sintesi propria (`SPEC_v2.md`,
339 voci) e una lista di priorità. Questo file valuta **le proposte
originali nelle tre trascrizioni**, non solo il filtro che Grok ne ha
fatto — alcune voci specifiche di Gemini e ChatGPT non erano
sopravvissute alla sintesi di Grok e sono state recuperate leggendo
le trascrizioni originali.

## Perché un file separato

Chiedere a un LLM "cosa miglioreresti" produce quasi sempre aggiunte,
mai "niente, va bene così" — è il tipo di domanda che lo garantisce.
Sommando le proposte delle tre AI, lo scope proposto passa da 266 a
oltre 400 voci mentre 188 di quelle originali non sono ancora
costruite. Tenerle in un file separato, con un verdetto esplicito
per ciascuna, evita che `SPEC.md` torni ad essere una lista dei
desideri invece di un registro di verità — il problema che ci sono
volute diverse sessioni per correggere la prima volta.

## Legenda verdetto

| Verdetto | Significato |
|---|---|
| `ACCETTATA` | Entra in `SPEC.md` come voce nuova, con priorità normale |
| `ACCETTATA-PRESTO` | Entra in `SPEC.md`, ma va anticipata: risolve un problema già presente ora o blocca altro |
| `FATTA` | Era `ACCETTATA`/`ACCETTATA-PRESTO`, ora costruita e pushata |
| `RIMANDATA` | Buona idea, momento sbagliato — condizione esplicita per riaprirla |
| `RESPINTA` | Non entra, con motivo tecnico/di prodotto specifico |
| `RIDIMENSIONATA` | L'idea è valida ma la versione proposta è sovradimensionata — entra una versione più piccola |

---

## 1. Performance e cache — `FATTA` (era `ACCETTATA-PRESTO`)

**Fonte**: osservazione mia propria, non delle tre AI, emersa
guardando il codice reale durante l'analisi.

Oggi, ad ogni singolo messaggio, `leveling` e `spam_trap` chiamano
entrambi `db.is_module_active_for_guild()` — due query per
messaggio. Su reazione, `verify` e `role_menus` fanno lo stesso. Con
qualche centinaio di server attivi sui 2 OCPU Ampere dichiarati,
diventa un collo di bottiglia misurabile, e peggiora con ogni cog
nuovo che condivide `on_message`/`on_raw_reaction_add`.

**Decisione**: mettere in cache la configurazione moduli per server
nella `BoundedCache` già costruita (§1.5), invalidata su `/setup`.
Non serve l'Event Bus a 4 livelli proposto da entrambi Gemini e
ChatGPT per risolvere questo — è un problema di caching, non di
architettura a eventi.

**Nota su Gemini §1.5.1/1.5.2**: proponeva anche un decoratore
`@cached(ttl=300)` generico per query frequenti. La versione TTL è
più generale di quella che costruiremo (solo invalidazione esplicita
su modifica, non scadenza temporale) — nota come possibile estensione
futura, non necessaria per risolvere il problema attuale.

---

## 2. Event Bus interno + architettura a 4 livelli — `RESPINTA` (nella forma proposta)

**Fonte**: Grok §1.10 (da ChatGPT punti 1-2, "separare in quattro
livelli" + "vero Event Bus interno").

Discord Adapter → Core (Tenant Context, Entitlements, Event Bus,
Lifecycle) → Application Modules → Domain/Infrastructure Services,
con eventi tipizzati (`MemberJoinedEvent`, ecc.) e moduli che non si
chiamano più direttamente.

**Perché la respingo così com'è**: è un pattern da sistema
distribuito multi-team. iYokai è un singolo processo Python con cog
che già comunicano correttamente tramite gli eventi nativi di
discord.py (`on_message`, `on_member_join`, ecc.) — che **sono già**
un event bus, fornito dalla libreria, testato da milioni di bot.
Aggiungerne uno nostro sopra significa: (a) reinventare
`discord.py`'s dispatch, (b) un nuovo strato da testare e mantenere,
(c) nessun beneficio misurabile per un bot a singolo processo.

Il problema concreto che questa proposta vuole risolvere (moduli
troppo accoppiati, query duplicate) è risolto dal punto 1 sopra, a
costo molto minore.

**Non del tutto respinta però**: se in futuro il progetto si
separasse davvero in processi diversi (music instance, backup
instance — già previsto nello schema originale come applicazioni
separate), un event bus tra PROCESSI (non tra cog dello stesso
processo) tornerebbe ad avere senso. Rivalutare solo a quel punto.

---

## 3. Logging strutturato — `FATTA` (DB) + `RIDIMENSIONATA, NON COSTRUITA` (Forum)

**Fonte**: ChatGPT punti 1-14 (il cuore della sua trascrizione), Grok
§8 EDIT.

### La parte DB — `ACCETTATA`
Multi-indice su PostgreSQL (member/channel/message/role/case/tempo),
un evento salvato una volta, consultabile da più angolazioni.
`/logs user:`, `/logs channel:`, Audit Timeline, retention/export
configurabile (Free 30gg / Premium 180gg+) sono conseguenze quasi
gratuite di uno schema fatto bene. **Ha anche valore legale**:
l'export è la forma naturale per rispondere a una richiesta di
accesso GDPR.

### La parte Forum — `RIDIMENSIONATA`
Sia Grok sia ChatGPT propongono un post/thread Discord per entità
(canale, membro, case) come "vista leggibile" sopra al DB. ChatGPT
stesso lo mette in guardia (punto 38, "non basarti sulla cache
object come unica verità") ma poi lo propone comunque per i membri.
**Non sono d'accordo con quella parte, e correggo il compromesso di
entrambi**: "membri" è l'unica dimensione ad alta cardinalità qui.

- Un server da 50.000 membri = 50.000 thread potenziali.
- I thread Discord si auto-archiviano; riattivarli per scrivere
  costa una chiamata API in più.
- Il caso peggiore è quello che conta: durante un raid da centinaia
  di join, il sistema dovrebbe creare centinaia di thread — proprio
  quando il logging serve di più, sbatte sul rate limit.

**Decisione**: Forum sì per **canali** e **Moderation Case** (bassa
cardinalità, vita lunga, consultati spesso). Forum no per **membri**
e **messaggi** — restano solo DB + comando di ricerca. Da verificare
sull'API reale (limiti thread-per-forum) prima di impegnarsi, non
dare per buoni i numeri a memoria.

### Punti tecnici di ChatGPT da portare dentro comunque
- **Outbox Pattern** (punto 46): scrivere l'evento nel DB e
  l'azione-verso-Discord nella STESSA transazione, un worker separato
  la esegue e la marca completata. Buona pratica reale contro
  "salvato nel DB ma il messaggio Discord non è mai partito per un
  crash a metà". **ACCETTATA**, va nel design della parte DB.
- **Distinzione Audit Log vs Activity Log** (punti 10-11): l'audit
  log di Discord non è affidabile come unica fonte (ha un ritardo,
  può mancare l'attore). **ACCETTATA** — già implicito in come
  usiamo l'audit log nello Spam Trap (solo per arricchire, mai come
  unica fonte), va reso esplicito come principio del modulo Logging.

---

## 4. Memory Guard più sofisticato — `RIDIMENSIONATA`

**Fonte**: ChatGPT punti 18-19.

Propone soglie a 4 livelli (NORMAL/WARNING/CRITICAL/EMERGENCY) con
risposta scalata (riduci cache → sospendi task non essenziali → GC →
chiudi connessioni inattive → restart graceful solo come ultima
risorsa) invece di un singolo controllo soglia+alert. Più un Memory
Leak Detector con `tracemalloc` in una modalità diagnostica separata
(non sempre attiva, troppo pesante).

**Valutazione**: l'idea delle soglie scalate è **genuinamente
migliore** di quello che abbiamo (oggi: soglia singola, GC forzato,
alert DM). Costa relativamente poco da implementare visto che
`core/memory_guard.py` esiste già. **ACCETTATA**, ma ridimensionata:
non tutte le ~10 metriche elencate da ChatGPT (heap allocation,
python object count, queue sizes, HTTP session count...) — solo RSS
(già fatto), pool DB usato/libero, e task count, che sono le tre che
il nostro codice può già misurare senza nuove dipendenze.

Il Memory Leak Detector con `tracemalloc` è **RIMANDATA**: utile in
un secondo momento se emergono leak reali in produzione, non da
costruire preventivamente senza un problema misurato.

---

## 5. Moderazione — coincidenza con gap già noti — `FATTA` (era `ACCETTATA`)

**Fonte**: Gemini §5.9-5.11, §8.4 (seconda versione dettagliata) —
**queste coincidono con voci che avevamo già in `SPEC.md` come `[ ]`
prima di leggere le trascrizioni**, scoperte indipendentemente da
noi durante l'audit originale.

- **§5.9 Reason obbligatorio + validazione minimo 3 caratteri** —
  `ACCETTATA`. Coincide con una nostra nota già scritta ("ho reso
  reason opzionale, contraddicendo lo schema originale"). La
  convalida a 3 caratteri è un dettaglio ragionevole in più.
- **§5.10 Canale mod-log dedicato** — `ACCETTATA`. Sensato,
  economico, colma un buco reale (oggi l'esito di un comando di
  moderazione resta nel canale del comando, non in un log
  centralizzato).
- **§5.11 Softban + mute via ruolo** — `ACCETTATA`. Già `[ ]` nella
  nostra `SPEC.md`, confermato indipendentemente da Gemini.
- **§8.4 Role update (nome/colore/permessi)** — `ACCETTATA`. Stessa
  storia: già `[ ]` da noi.

Il fatto che un'AI indipendente, partendo dallo stesso `SPEC.md`,
sia arrivata alle stesse identiche voci mancanti è un segnale di
qualità del documento, non una novità da festeggiare come scoperta.

---

## 6. Security Suite estesa — `ACCETTATA` (parziale)

**Fonte**: ChatGPT punto 34 (Risk Engine), punto 35 (Anti-Nuke con
modalità Quarantine).

- **Anti-Nuke con Quarantine mode** (isolare permessi invece di
  bannare subito su un'azione sospetta) — `ACCETTATA`. Riduce i falsi
  positivi rispetto a un ban/kick immediato su un pattern sospetto,
  ed è coerente con lo stile già adottato nel progetto (Verify:
  segnalazione allo staff, non azione automatica distruttiva).
- **Risk Engine generico** (un punteggio di rischio configurabile che
  alimenta più moduli di sicurezza insieme) — `RIMANDATA`. Utile in
  astratto, ma senza Anti-Raid e Anti-Nuke costruiti per primi (sono
  ancora `[ ]` in `SPEC.md` §7.1-7.2) non c'è ancora niente da cui il
  Risk Engine dovrebbe aggregare segnali. Si ridiscute dopo che
  quelle due sezioni esistono.

---

## 7. Retention Layer (Quest, Achievement, Battle Pass, Streak, Collection, Identity Rank...) — `RIMANDATA`

**Fonte**: Grok §18 (15 voci), Gemini §F1-F4/§B1-B4, ChatGPT punti
"retention a tre livelli" + 20 sotto-punti.

Tutte tecnicamente legittime per un bot orientato alla community. Ma
nessuna delle tre AI ha detto la cosa che conta di più qui:

> **La retention serve a trattenere utenti che hai già. Il bot è a
> zero server in produzione.**

Le sezioni a zero nel nostro `SPEC.md` — Music, Backup, Alert social
— sono i motivi per cui un admin *invita* un bot. Battle Pass e
Streak sono il motivo per cui gli utenti *restano dopo*. Costruire il
secondo prima del primo ottimizza la ritenzione di utenti che non
esistono ancora.

C'è anche un vincolo di sequenza che nessuna delle tre AI ha
considerato: iYokai Main deve passare la **review di Discord per
superare i 100 server**. Ogni feature aggiunta prima di quella
review allarga la superficie da far verificare e la ritarda.

**Condizione per riaprire**: dopo che Music, Alert social, Backup, e
Security Suite completa sono `[x]`, e il bot ha superato la review
Discord per i 100 server. A quel punto, priorità dentro il Retention
Layer stesso (mia valutazione, se richiesta): Shop + Daily/Streak
prima di tutto il resto (economia esistente già costruita, estensione
naturale), Achievement/Quest dopo, Battle Pass/World Boss/Dungeon per
ultimi (i più costosi da bilanciare e mantenere).

**Sotto-voce isolata, valutata a parte**: **§F3.3 Mercato Aste
Player-to-Player** (Gemini) — introduce scambio di beni virtuali tra
utenti con tassa di transazione. `RIMANDATA` con la stessa
condizione, ma segnalo un rischio in più che nessuno ha menzionato:
un mercato tra utenti è la superficie naturale per il riciclaggio di
coin tra account collegati (farm su un account, trasferisci il
valore a un altro tramite un'asta finta). Se mai costruito, serve un
limite di prezzo min/max legato al valore reale degli oggetti, non
lasciato libero.

---

## 8. AI Engine & Lore System — `RIMANDATA`, con un problema di fondo non discusso da nessuno

**Fonte**: Grok §F1-F3, Gemini §E1/§A1-A2/§H1-H3, ChatGPT (guardrail,
cost controller, AI Router in Tier S).

Router multi-provider con fallback a cascata (Groq → Gemini Flash →
OpenRouter/HF → risposta locale), cache semantica su Postgres, Lore
Engine parametrico iniettato in ogni chiamata.

**Il problema architetturale che tutte e tre condividono**: **World
Boss/Dungeon e Daily Digest richiedono di generare testo dal
contenuto reale del server** (riassumere messaggi, descrivere eventi
in base a cosa succede). Questo significa:

1. **Serve il Message Content Intent** — la stessa regola che il
   documento di Grok elenca come nota #7 ("nessuna feature deve
   renderlo obbligatorio finché non strettamente necessario") viene
   *contraddetta* dalle sue stesse proposte F3.1/F3.2 due sezioni
   prima. Nessuno dei tre l'ha notato.
2. **I messaggi dei tuoi utenti finiscono su Groq e Google.** Tu
   operi dall'Italia — è un rapporto titolare↔responsabile del
   trattamento sotto GDPR: serve base giuridica, informativa
   esplicita agli admin dei server clienti, verosimilmente un DPA con
   i provider. Nessuna delle tre trascrizioni lo menziona.
3. **Dipendenza core su free tier di terzi.** I free tier di Groq
   sono già cambiati più volte in passato. Se le feature di punta del
   motore (World Boss, Dungeon, Digest) girano sopra un'API gratuita
   di terzi, il giorno in cui i termini cambiano il motore smette di
   funzionare su tutti i server insieme. L'interruttore
   `USE_PAID_KEYS` proposto da tutti e tre è una buona intuizione ma
   sposta il problema, non lo risolve: a quel punto il costo dei
   token per 1000 server lo paghi tu.

**Decisione**: l'intero pilastro AI resta `RIMANDATA` fino a quando
non c'è una privacy policy pubblicata (prerequisito legale, non
opzionale — vedi punto 10) E una decisione esplicita su chi paga i
token oltre il free tier. Il **Lore Engine parametrico da solo**
(§E1/§A2 — solo la tabella `guild_lore_config` + comando `/lore
setup` con preset, SENZA il motore AI dietro) è invece a basso rischio
e potrebbe essere costruito prima, come infrastruttura pronta per
quando l'AI Engine sarà sbloccato: **ACCETTATA** solo per la parte
tabella+comando, il resto resta legato al motore AI.

---

## 9. Identità cross-server & Reputazione — `RESPINTA` (reputazione) + `RIMANDATA` (passport)

**Fonte**: Grok B.2 (Passport), risposta libera di Grok ("Reputation &
Trust Score"), ChatGPT punti sulla User App.

### Reputazione derivata da sanzioni — `RESPINTA`, non rimandata
`SPEC.md` §4.3 dice già esplicitamente: *"Match → segnalazione allo
staff (NON ban automatico cross-server)"* — una decisione presa
apposta durante l'audit originale. Sia il Passport di Grok
("Reputazione globale basata su assenza di sanzioni recenti... flag
clean record... i server possono dare privilegi automatici a
Reputation alta") sia il "Trust Score" della sua risposta libera
**reintroducono lo stesso meccanismo attraverso una porta diversa**.
Nessuna delle due proposte cita l'altra, ma sono la stessa cosa.

È una lettera scarlatta portatile: bannato ingiustamente su un
server → il flag ti segue ovunque, deciso da un algoritmo su cui
l'utente non ha voce. È anche profilazione automatizzata con effetti
significativi sotto GDPR Art. 22 (decisione di accesso presa
automaticamente da un punteggio calcolato) — serve base giuridica e
diritto di revisione umana, che nessuno dei tre ha discusso. E resta
una superficie d'attacco: un admin malevolo emette sanzioni finte
per affossare la reputazione globale di qualcuno su OGNI server.

**Non rimando questa: la taglio.** Nel Passport, se mai costruito,
entrano solo dati positivi, di proprietà dell'utente, opt-in
(livelli, badge, collezioni) — mai propagazione di sanzioni o
punteggi derivati da moderazione.

### Passport / profilo globale (solo la parte positiva) — `RIMANDATA`
Livello globale, badge, collezione — legittimo, ma dipende da avere
prima un `USER_INSTALL` funzionante (§B.1, ancora `[ ]`) e
un'economia/livelli stabile su cui aggregare dati cross-server.
Condizione: dopo Music/Backup/Alert (stessa ragione del punto 7).

---

## 10. Privacy & compliance — `ACCETTATA-PRESTO`, prerequisito bloccante

**Fonte**: ChatGPT punto 14 (Privacy Manager centrale), mia
osservazione sui punti 8 e 9 sopra.

Nessuna delle tre AI tratta questo come **prerequisito bloccante** —
tutte lo trattano come una voce tra le tante (`SPEC.md` §C.5 la
elenca in fondo alla sezione Web Panel). Con AI di terzi nel motore
(punto 8) e un profilo cross-server (punto 9), diventa grande in
fretta: quali dati, per quanto, condivisi con chi, diritto di
cancellazione, base giuridica per ciascun trattamento.

**Decisione**: qualunque lavoro su AI Engine o Passport resta
bloccato finché non esiste almeno una bozza di privacy policy e un
elenco esplicito dei trattamenti dati per modulo. Non serve essere
perfetti da subito, serve che esista prima di spedire la prima
chiamata a un'API esterna con dati di un utente.

---

## 11. Strumenti admin lock-in — `FATTA` (3 su 4, l'ultima è rimandata per scelta)

**Fonte**: risposta libera di Grok (Staff Workload Intelligence,
Config Diff & Rollback, Permission Risk Heatmap, Smart Escalation
Ladder), ChatGPT punto 25 (Permission Resolver).

- **Config Diff & Rollback** — `FATTA`. È l'evoluzione naturale
  di §2.7 (Log modifiche setup) già `[ ]` nella nostra SPEC — non è
  una voce nuova, è un dettaglio in più su una già prevista.
- **Permission Risk Heatmap** — `FATTA`. Estende naturalmente
  §7.4 Permission Auditor già previsto.
- **Smart AutoMod Escalation Ladder** (scala configurabile di azioni
  per infrazione, con reset dopo buona condotta) — `FATTA`. Estende
  §6 AutoMod (nuova voce §6.15, nessun corrispettivo esistente da
  riusare), coerente con l'architettura ibrida (nativo + bot-side)
  già decisa per quel modulo.
- **Staff Workload Intelligence** (misura carico ticket/sanzioni per
  moderatore, suggerisce rotazioni, eventuali bonus automatici dallo
  staff fund) — `RIMANDATA`. Utile ma con un rischio non discusso:
  bonus automatici basati su "efficienza" delle sanzioni possono
  incentivare un moderatore a sanzionare di più per guadagnare di
  più. Se mai costruito, la parte di misura/dashboard sì, la parte di
  bonus automatico no (resta decisione manuale dell'admin).

---

## 12. Scartate esplicitamente — nessuna condizione di riapertura

Elencate dalle tre AI stesse come "da non fare", con cui concordo, più
le mie:

- **Selfbot / user token per qualunque funzione** — viola i ToS
  Discord, fa bannare l'utente finale. Già scartato nello schema
  originale, tutte e tre le AI confermano.
- **Community Jury completamente automatica** (giuria di pari che
  ribalta sanzioni admin) — un bot che permette a utenti selezionati
  casualmente di ribaltare decisioni dello staff è un prodotto che
  gli admin disattivano il primo giorno: sono loro i responsabili del
  proprio server. Aggiunge rischio di brigading coordinato.
  **RESPINTA**, non "Premium opzionale" come proposto da Grok — se
  un admin non la vuole per il proprio server (la maggioranza, mi
  aspetto), costruirla comunque è sforzo sprecato.
- **AI che modera autonomamente** — ChatGPT stesso la scarta ("troppo
  rischiosa"), concordo.
- **Ranking pubblico dello staff** — ChatGPT stesso la scarta
  ("incentiva comportamenti sbagliati"), concordo.
- **20 sistemi di valuta diversi / social network interno / streaming
  video proprietario** — fuori scope, nessun valore differenziale per
  un bot Discord.
- **Cross-Server Alliance / matchmaking cooperativo tra server** —
  ROI basso rispetto allo sforzo di manutenzione permanente che
  richiede (non solo sviluppo una tantum: supporto continuo).
- **Real Estate di canali, Karaoke con analisi audio, Bounty system
  tra utenti** — concordo con la valutazione di Grok: carini sulla
  carta, sforzo sproporzionato al beneficio.
- **Marketplace di plugin di terze parti** (ChatGPT punti 108-110) —
  introduce esecuzione di codice non fidato nello stesso processo.
  Fuori discussione finché non esiste un vero sandboxing (altro
  processo, altri permessi) — e anche allora, è un progetto a sé, non
  una feature.

---

## 13. Non ancora deciso — richiede test reali prima di un verdetto

- **Architettura a istanze multiple invisibili all'utente** (ChatGPT:
  "iYokai Platform" con Creator/Main/Music×5/NSFW dietro un solo
  nome percepito) — è già la direzione presa dallo schema originale
  (le 8 applicazioni separate). Non è una proposta nuova, è una
  descrizione più elegante di quello che avevamo già deciso. Nessuna
  azione richiesta, solo terminologia.
- **Outbox Pattern, Idempotenza esplicita, Dead Letter Queue** — validi
  in astratto, ma "quanto" di ciascuno serve dipende dal volume reale
  che il bot gestirà. Da rivalutare con dati veri (log di errori,
  frequenza di eventi duplicati) una volta in produzione, non
  costruiti preventivamente su un problema ancora ipotetico.
- **Testing matrix estesa, feature flags, canary deployment** — buone
  pratiche generiche di ingegneria, ma per un solo sviluppatore che fa
  deploy manuale su una singola VM, "canary deployment" non ha un
  target su cui girare. Rivalutare se/quando il deploy diventa
  automatizzato o multi-istanza.

---

## Riepilogo numerico

| Verdetto | Conteggio approssimativo di cluster |
|---|---|
| `ACCETTATA` / `ACCETTATA-PRESTO` | 11 cluster |
| `RIDIMENSIONATA` | 3 cluster |
| `RIMANDATA` | 7 cluster |
| `RESPINTA` | 8 cluster |
| Non deciso / richiede dati reali | 3 cluster |

Le voci `ACCETTATA`/`ACCETTATA-PRESTO` che richiedono lavoro concreto
a breve termine, in ordine di priorità mia (da discutere, non
imposta):

1. Cache configurazione moduli (§1) — risolve un problema già presente
2. Softban + mute via ruolo + reason obbligatorio + mod-log channel (§5) — chiude gap già noti in `SPEC.md`
3. Config Diff & Rollback, Permission Heatmap, Escalation Ladder (§11) — estendono moduli già previsti
4. Logging multi-indice su DB, senza il Forum per membri/messaggi (§3)
5. Memory Guard a soglie scalate, versione ridotta (§4)
