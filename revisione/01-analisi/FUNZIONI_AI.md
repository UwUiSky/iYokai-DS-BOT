# FUNZIONI_AI.md — Tutte le funzioni AI di cui si è parlato

L'owner ha detto: *«le feature AI delle quali avevamo discusso mancano
dalle liste»*. Aveva ragione. Questo file le raccoglie **tutte**,
rilette una per una dalle conversazioni originali, e dice per ognuna
dov'è oggi e come si fa in iYokai.

Regola seguita (D18): nessuna funzione discussa viene tolta. Se una
funzione così com'era non si può fare, o non è sicura, qui c'è la
versione più vicina che funziona.

Voce di `SPEC.md`: **§25**. Scheda: **NF-24**. Fase: **F12**. Le
funzioni **non** AI trovate nelle stesse fonti e assenti dalle liste
sono in [`VOCI_OMESSE.md`](VOCI_OMESSE.md).

## In sintesi

- Funzioni AI trovate nelle conversazioni: **100**. Più **8** chieste
  dall'owner il 05/10/2026 (§13, AI-R-101…108).
- Già in una lista, per intero: **39**. Di queste, 13 stavano solo nel catalogo
  dei concorrenti (`catalogo/18-ai.md`), senza un piano.
- In una lista solo in parte: **23**.
- In nessuna lista: **38**.
- Quindi **61 su 100** mancavano del tutto o in parte.

Chi le aveva volute:

| Origine | Quante | Di cui mancanti del tutto o in parte |
|---|---|---|
| Chieste dall'owner con parole sue | 9 | 6 |
| Proposte da Gemini e approvate dall'owner in blocco | 16 | 15 |
| Scritte da Gemini nel documento che l'owner gli aveva chiesto (SPEC_EXTRA); nessuna risposta dopo | 12 | 8 |
| Solo proposte da un'altra AI (ChatGPT, Grok), senza risposta dell'owner nelle fonti | 32 | 28 |
| Scritte nell'issue #50 (elenco "richieste / discusse") | 9 | 4 |
| Solo nel catalogo dei bot concorrenti | 18 | 0 |
| Nate nel piano o da una decisione | 4 | 0 |
| **Totale** | **100** | **61** |

Le più importanti che non erano in nessuna lista, o lo erano a metà:

1. **World Boss: evento di gruppo contro un mostro** (AI-R-054) — approvato dall'owner; solo nel vecchio `BACKLOG.md` come "rimandato".
2. **Dungeon di gruppo con scelte votate** (AI-R-058) — come sopra.
3. **Riepilogo del server, ogni giorno o ogni settimana** (AI-R-044) — §25 parlava solo di "riassunti di canali".
4. **La lore viene chiesta durante il setup** (AI-R-052) — chiesta dall'owner.
5. **Libreria dei contenuti generati, che cresce da sola** (AI-R-005) — chiesta dall'owner.
6. **Coda e limite per molte richieste insieme** (AI-R-022) — chiesta dall'owner.
7. **Cerca comando a parole, in qualsiasi lingua** (AI-R-026) — chiesta dall'owner; oggi c'è solo la ricerca con sinonimi.
8. **Bottone "Chiedi all'assistente" dentro il ticket** (AI-R-071) — con la bozza di risposta per lo staff.
9. **Richieste di cancellazione dei dati lette prima dall'AI** (AI-R-091) — chiesta dall'owner nell'issue #46.
10. **Livelli di privacy dell'AI per server** (AI-R-016) — senza questo l'AI è solo accesa o spenta.

## Da dove vengono

Ho riletto per intero, non a campione:

- **La prima conversazione di progetto con Grok** (file
  `attachment-e9682b7c.txt` e lo schema finale `attachment.txt`). Qui
  l'owner detta tutto il bot. **Di AI non si parla mai**: nessuna riga.
- **La conversazione con Gemini** (`project_spec-md_transcript_to_gemini.txt`).
  È la fonte principale. Gemini propone tre elenchi di idee. L'owner
  risponde «Tutto molto interessante» (r.358) e poi «mi piacciono molto
  tutte le idee che hai tirato fuori» (r.494). Nella stessa riga chiede
  la lore per server e chiede quali AI sono gratuite. Alla r.639 chiede
  più fornitori in cascata, il passaggio alle chiavi a pagamento, una
  "libreria" dei contenuti generati, e un albero dove «dalla categoria
  AI ci saranno dentro tutte le cose che dovrà fare tramite AI».
- **La conversazione con ChatGPT** (`gemini_transcript_and_spec-md_to_chatgpt.txt`).
  Da un certo punto in poi il file contiene **solo le risposte di
  ChatGPT**: i messaggi dell'owner mancano. Dove ChatGPT scrive "la tua
  idea" o "la direzione che descrivi" l'ho segnato come richiesta
  dell'owner **riportata**.
- **La conversazione finale con Grok** (`gemini_and_chatgpt_and_spec-md_to_grok_transcript.txt`)
  e la sua sintesi `SPEC_v2__1_.md` (qui "SPEC_v2").
- **L'issue #50** (`issue_50.md`) e l'issue #46 che cita.
- Nel repository: `SPEC.md` §25, `archivio/BACKLOG.md` (i vecchi
  verdetti), `NUOVE_FUNZIONI.md`, `DECISIONI.md`, `catalogo/18-ai.md`,
  `APP_UTENTE_E_DESKTOP.md`, `LIMITI.md`.

"r." è il numero di riga del file citato.

### Come leggere le tabelle

**Chi l'ha chiesta o proposta:**

- **Owner: chiesta** = l'owner l'ha chiesta con parole sue (c'è la citazione).
- **Owner: approvata in blocco** = l'ha proposta Gemini in uno dei tre
  elenchi che l'owner ha approvato tutti insieme.
- **Gemini, su richiesta dell'owner** = l'ha scritta Gemini nello
  `SPEC_EXTRA.md` che l'owner gli aveva chiesto («Creamene una versione
  due o extra», r.494; più dettaglio, r.639). Dopo quel documento la
  conversazione finisce: non c'è un sì o un no dell'owner.
- **Proposta** = l'ha proposta un'altra AI; nelle fonti non c'è una
  risposta dell'owner.
- **Issue #50** = è nell'elenco dell'issue, che non dice chi l'ha chiesta.
- **Catalogo** = ce l'ha un bot concorrente; nelle conversazioni non se
  ne parla.

**Dov'è oggi:** una voce di `SPEC.md`, una scheda `NF`, un codice del
catalogo, oppure **in nessuna lista**. `BACKLOG.md` è archivio: non
conta come lista, ma riporto il suo vecchio verdetto. La colonna
fotografa le liste **com'erano prima di questo lavoro** (05/10/2026).
Da allora ogni riga ha la sua voce in `SPEC.md` §25: la tabella è in
fondo a questo file.

**Parole usate nella colonna dei limiti:**

| Parola | Vuol dire |
|---|---|
| policy | Privacy policy pubblicata, con l'elenco dei fornitori AI (SPEC 19.7) |
| consenso | L'admin del server ha accettato l'uso dell'AI |
| D13 | Tetto di spesa; oltre il tetto risposta locale; le funzioni che costano sono premium |
| `message_content` | L'intent per leggere il testo dei messaggi (D9, acceso) |
| `defer()` | Discord vuole una risposta entro 3 secondi: il bot dice subito "sto lavorando" |
| 2000 o 4096 | Massimo di caratteri di un messaggio o della descrizione di un embed |

**Modello:** *testo*, *immagini*, *embedding* (confronto per
significato), *nessuno* (la funzione va anche senza AI). Nessuna
funzione discussa usa la *voce*.

Regole che valgono per ogni riga e non sono ripetute: iYokai **usa**
servizi AI esistenti, non addestra modelli (D19). Ciò che Discord vieta
è usare i messaggi per addestrare: per questo i messaggi degli utenti
vanno solo ai servizi che dichiarano di non farlo. Nessun comando nuovo
di primo livello; tutto parte spento.

## 1. Motore e infrastruttura

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Dov'è oggi | Come farla in iYokai | Prerequisiti e limiti |
|---|---|---|---|---|---|---|
| AI-R-001 | Router con più fornitori in cascata | Prova il primo fornitore; se è occupato o lento passa al successivo (Groq, poi Gemini Flash, poi OpenRouter o Hugging Face). | **Owner: chiesta** (Gemini r.639: «se una non è disponibile … si appoggia a una delle altre in automatico»). Dettaglio: Gemini §A1.1 (r.721), SPEC_v2 §F1.1, Grok r.12, issue #50 | SPEC 25.1, NF-24 | `core/ai_router.py`; elenco dei fornitori in ordine; chiavi nel `.env`; `/owner ai fornitori`. Modello: testo | Policy con l'elenco dei fornitori; consenso; D13. Le quote gratuite cambiano spesso: vanno scritte in `LIMITI.md` e ricontrollate |
| AI-R-002 | Risposta locale di riserva, senza AI | Se tutti i fornitori sono fermi o il tetto è finito, il bot risponde con testi pronti, scelti anche in base al tema della lore. | Gemini, su richiesta dell'owner: §E1.4 (r.564), §A1.1 (r.726: «Risposta locale deterministica da Dizionario DB»); SPEC_v2 §F1.1, §F2.4 | SPEC 25.1, D13 | Tabella `ai_fallback_texts` (funzione, tema, testo); usata anche quando l'AI è spenta. Modello: nessuno | Nessuno: funziona anche prima della policy |
| AI-R-003 | Pausa automatica del fornitore che dà errori | Dopo un errore 429 o 503, o una risposta più lenta di 2 secondi, il fornitore va in pausa 60 secondi e le richieste passano al successivo senza che l'utente se ne accorga. | Gemini, su richiesta dell'owner: §A1.2 (r.727); SPEC_v2 §F1.2; ChatGPT r.1775 e r.4939 (interruttore automatico per i servizi esterni, AI compresa) | In parte: SPEC 25.1 dice "cascata" ma non la pausa né i tempi | Stato per fornitore in memoria (`chiuso`, `aperto`, `in prova`); tempi in `core/config.py`. Modello: nessuno | Con `defer()` ci sono 15 minuti, ma l'utente non deve aspettare più di pochi secondi |
| AI-R-004 | Cache delle risposte | Una domanda già fatta (stesso testo, stesso server, stesso tema) riceve la risposta salvata, senza chiamare l'AI. | Gemini, su richiesta dell'owner: r.526, §H1.2, §A1.3 (r.730: tabella `ai_semantic_cache`, valida 24 ore); SPEC_v2 §F1.3; issue #50 | SPEC 25.2, NF-24 | `core/ai_cache_logic.py`; chiave = hash del testo ripulito + server + tema; scadenza. Modello: embedding (solo per il confronto "simile", in un secondo momento) | Mai salvare in cache testi con dati personali; pulizia giornaliera (NF-04) |
| AI-R-005 | Libreria dei contenuti generati, che cresce da sola | Ogni mostro, stanza o descrizione generata viene salvata e riusata la volta dopo, anche da altri server con lo stesso tema. | **Owner: chiesta** (Gemini r.639: «creando poi in un domani una libreria»; «viene generata e poi viene riscontrata»). Gemini r.647 ("Prompt Deduplication") | In parte: SPEC 25.2 parla solo di risposte a domande | Tabella `ai_content_library` (tipo, tema, testo, quante volte usato); `/owner ai libreria` per rivedere e togliere voci. Modello: nessuno al riuso | Nella libreria solo testi di gioco, mai nomi o messaggi di utenti; riuso tra server solo per i temi pronti, non per i temi scritti a mano da un admin |
| AI-R-006 | Smistamento delle domande: prima regole e database, AI solo se serve | Le domande semplici ricevono una risposta da regole o dal database. L'AI entra solo dove serve (giochi, riepiloghi, domande ambigue). | Gemini, su richiesta dell'owner: r.528 ("Prompt Routing"); ChatGPT r.7804 (modello piccolo per cercare, modello grande solo se la richiesta è ambigua) | **In nessuna lista** | Funzione `scegli_strada()` in `core/ai_router.py`: FAQ esatta, ricerca comandi, poi AI. Modello: nessuno / testo | Riduce i costi: va fatto insieme al tetto di spesa |
| AI-R-007 | Un solo punto di chiamata per tutti i moduli | Ogni modulo chiama la stessa funzione e non sa quale fornitore risponde. Nessun modulo parla da solo con un fornitore. | Gemini, su richiesta dell'owner: r.649 (`AIProvider.generate_response`); Grok r.55 («Un unico AI Engine Router ben fatto basta»); SPEC_v2 nota 6 | NF-24 ("un motore unico") | `core/ai_router.py` è l'unico file che importa le librerie dei fornitori; un test lo controlla. Modello: nessuno | — |
| AI-R-008 | Passaggio alle chiavi a pagamento con un interruttore | L'owner passa dai livelli gratuiti alle chiavi a consumo senza cambiare il codice delle funzioni. | **Owner: chiesta** (Gemini r.639: «in un secondo momento mi appoggerò ad API a consumo»). Gemini §A1.4 (r.735: `USE_PAID_KEYS`); SPEC_v2 §F1.4; issue #50 | In parte: D13 dice di partire dal gratuito; l'interruttore non è scritto | `/owner ai fornitori`: per ogni fornitore "gratis", "a pagamento", "spento"; chiavi solo nel `.env`. Modello: testo, immagini | D13: prima il tetto di spesa, poi le chiavi a pagamento |
| AI-R-009 | Conteggio dell'uso | Per ogni chiamata il bot segna server, funzione, fornitore e token stimati. | Gemini, su richiesta dell'owner: §A1.4 (r.734: `ai_usage_logs`); SPEC_v2 §F1.4; ChatGPT r.7306 ("AI tokens used") | SPEC 25.4, NF-24 | `core/ai_cost_logic.py`, tabella `ai_usage`; solo numeri, mai il testo della richiesta. Modello: nessuno | Tabella che cresce: aggregare per giorno (NF-04) |
| AI-R-010 | Tetto di spesa per server | Ogni server ha un massimo al giorno e al mese. Finito il tetto, il bot dà la risposta locale e lo dice. | Proposta: ChatGPT r.6238 ("Guild Daily AI Budget"), r.7184; issue #50 («budget token per guild»). Decisione D13 | SPEC 25.4, D13 | `/admin ai tetto` (entro il massimo deciso dall'owner); `/owner ai spesa`. Modello: nessuno | D13: oltre il tetto niente AI; il messaggio deve essere chiaro |
| AI-R-011 | Quota per utente | Ogni utente ha un numero di richieste al giorno, per non consumare da solo il tetto del server. | Proposta: ChatGPT r.6238 ("User Daily AI Budget"); catalogo AI-002 (MEE6) | Catalogo AI-002 (non ancora in un piano) | Contatore per utente in `core/ai_cost_logic.py`; valore scelto dall'admin. Modello: nessuno | Risposta privata quando la quota è finita |
| AI-R-012 | Quota per funzione | Il tetto del server si divide tra le funzioni (per esempio 50 % ticket, 20 % riepilogo, 30 % assistente), così una non toglie tutto alle altre. | Proposta: ChatGPT r.6238 ("Module Budget") | **In nessuna lista** | Percentuali in `/admin ai tetto`; valori di partenza decisi dall'owner. Modello: nessuno | La somma non supera il 100 % |
| AI-R-013 | Filtri di sicurezza in ingresso e in uscita | Prima dell'invio il bot toglie dati personali e blocca richieste vietate. Dopo, controlla la risposta. | Issue #50 («Guardrail (no PII leak, rate limit, deny-list prompt)»); ChatGPT r.6209 | SPEC 25.3, NF-24 | `core/ai_guardrail_logic.py`; menzioni, ID, email, link di invito tolti o sostituiti. Modello: nessuno | Risposta sempre con `allowed_mentions` vuoto; testo entro 2000 o 4096 |
| AI-R-014 | Lista delle richieste vietate e limite di richieste per utente | Un elenco di frasi e argomenti che il bot rifiuta sempre, più una pausa tra una richiesta e l'altra. | Issue #50 («deny-list prompt», «rate limit») | In parte: SPEC 25.3 parla di filtri in generale | Lista fissa nel codice più lista del server (`/admin ai filtri`); pausa per utente. Modello: nessuno | La lista fissa non si può spegnere |
| AI-R-015 | Regola "l'AI propone, una persona conferma" | L'AI non banna, non dà ruoli, non cambia permessi o impostazioni, non manda messaggi da sola. Propone; il bot controlla regole e permessi; una persona conferma; solo allora l'azione parte. | Proposta: ChatGPT r.6209–6237 ("AI Guardrails"); issue #50, dipendenza 4; BACKLOG §12 | In parte: il catalogo la applica caso per caso (AI-013, AI-018); non è scritta come regola del motore | Il router restituisce solo testo o una "proposta" con dati; i bottoni di conferma stanno nel cog che la riceve. Modello: nessuno | I permessi sono sempre quelli di chi preme "Conferma" |
| AI-R-016 | Livelli di privacy dell'AI per server | L'admin sceglie cosa l'AI può leggere: niente; solo numeri; solo i messaggi dei canali scelti; solo il ticket in cui viene chiamata; tutto il contesto autorizzato. | Proposta: ChatGPT r.6259–6271 ("AI Privacy Mode": «Mai leggere automaticamente tutto lo storico») | **In nessuna lista** (SPEC 25.9 ha solo acceso o spento) | `/admin ai privacy`; valore di partenza: "solo il ticket o il messaggio su cui viene chiamata". Modello: nessuno | Policy; consenso. Il livello più largo va chiesto con una conferma scritta |
| AI-R-017 | Consenso dell'admin prima di accendere l'AI | La prima volta l'admin vede a chi vanno i dati e deve accettare. Senza consenso l'AI resta spenta. | Issue #50 («DPA / informativa privacy»); BACKLOG §8 e §10 | SPEC §25 (prerequisiti), NF-24, D13 | Bottone "Accetto" in `/admin ai stato`; data e autore salvati. Modello: nessuno | Serve la policy pubblicata (SPEC 19.7) |
| AI-R-018 | Tempo di conservazione del contesto dell'AI | Il server sceglie per quanto il bot tiene il testo usato dall'AI: da 0 a 30 giorni. | Proposta: ChatGPT r.6401 («AI Context: 0–30 giorni») | **In nessuna lista** | Impostazione in `/admin ai privacy`; valore di partenza 0 (niente su disco). Modello: nessuno | Va scritto nel registro dei dati personali (NF-04) |
| AI-R-019 | Interruttori per server, per canale e per singola funzione | Tutto parte spento. L'admin accende l'AI per il server, sceglie i canali e accende le funzioni una per una. | Piano NF-24; catalogo AI-017 (MEE6); ChatGPT r.4608–4636 (ogni modulo fatto di funzioni che si accendono da sole) | SPEC 25.9, catalogo AI-017 | `/admin ai interruttori`. Modello: nessuno | — |
| AI-R-020 | Modulo AI in manutenzione o a mezzo servizio, senza fermare il resto | Se l'AI è ferma, ticket, moderazione e log continuano. All'avvio il bot dice se i fornitori rispondono. | Proposta: ChatGPT r.7055 ("AI maintenance"), r.7063, r.7111 | **In nessuna lista** | Stato del modulo in `/owner ai fornitori`; ogni funzione AI ha il suo ramo "senza AI". Modello: nessuno | — |
| AI-R-021 | AI in un processo separato | Il lavoro dell'AI gira in un processo a parte, così una chiamata lenta non rallenta il bot. | Proposta: ChatGPT r.1054–1060 e r.4433–4436 ("worker" per Music, Backup, Notifications, AI) | **In nessuna lista** (BACKLOG §2: l'idea dei livelli fu respinta, ma "tra processi" restava aperta) | Prima versione nello stesso processo, con coda. Si separa solo se le misure lo chiedono. Modello: nessuno | Macchina con 2 CPU: da misurare prima |
| AI-R-022 | Coda e limite per molte richieste insieme | Se molti server chiedono nello stesso momento, le richieste si mettono in fila. Ogni server ha un massimo di richieste insieme. | **Owner: chiesta** (Gemini r.639: «50 server in contemporanea vogliono farsi una partitina»). ChatGPT r.7184 («AI requests: max 100/day») | **In nessuna lista** | Coda in `core/ai_router.py` con un semaforo per server e uno globale; messaggio "sei in fila". Modello: nessuno | `defer()` subito; se l'attesa supera il limite, risposta locale |
| AI-R-023 | AI come diritto premium a parte, con periodo di prova | Le funzioni AI che costano sono un premium separato dal resto. Un server può provarle per pochi giorni. | Proposta: ChatGPT r.2631 (`ai_tools`), r.7250 (`premium_ai`), r.7297 («AI Ticket Assistant — 3 days»); catalogo AI-003 (MEE6: abbonamento personale e del server) | In parte: D13 e catalogo AI-003; la prova non c'è | Due diritti in NF-22: del server e personale; prova una sola volta per server. Modello: nessuno | Vendere dentro Discord richiede l'app verificata |

## 2. Assistente e helpdesk

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Dov'è oggi | Come farla in iYokai | Prerequisiti e limiti |
|---|---|---|---|---|---|---|
| AI-R-024 | Risposte alle domande frequenti del server | Un utente chiede "come si diventa VIP?" o "quali sono le regole?" e il bot risponde con le informazioni del server. | Proposta: Gemini r.337–339 ("AI Support Agent"). **Owner: approvata** (r.494: «come tengo il VIP … a quella frase o similitudini risponde») | SPEC 25.5, NF-24 | `/utility chiedi`; fonti: FAQ del server, regole, elenco dei comandi. Modello: testo | Policy; consenso; `defer()`; risposta entro 2000 caratteri |
| AI-R-025 | Base di conoscenza caricata dall'admin | L'admin scrive domande e risposte, regole e guida. L'AI risponde usando solo quei testi. | Proposta: Gemini r.339 («addestrabile sulle FAQ del server»), §D1.1 (r.838). **Owner: approvata in blocco** (Gemini r.494: «mi piacciono molto tutte le idee che hai tirato fuori») | In parte: catalogo TKT-079 (base di conoscenza senza AI, non in un piano); SPEC 25.5 | `/admin ai faq`; tabella `ai_faq` (server, domanda, risposta); tetto di voci; funziona anche senza AI con la ricerca per parole. Modello: testo; embedding facoltativo | "Addestrabile" vuol dire "testi passati al momento": Discord vieta di addestrare modelli con i messaggi |
| AI-R-026 | Cerca comando a parole, in qualsiasi lingua | L'utente scrive cosa vuole fare ("come blocco i link ai nuovi?") e il bot indica i comandi giusti. | **Owner: chiesta** (riportata da ChatGPT r.7620: «Il sistema "Cerca comando" basato su AI»; r.7626: «/ai cerca comando»; r.8165). SPEC_v2 §B.6 e nota 2 | In parte: SPEC 21.5 e NF-06 (ricerca con sinonimi, senza AI); SPEC 25.5 | `/utility cerca-comando`: prima la ricerca di oggi; se non trova, l'AI sceglie dal registro dei comandi. Modello: testo; embedding facoltativo | Policy; consenso; solo i comandi che l'utente può usare |
| AI-R-027 | Registro unico dei comandi letto dall'AI | Ogni comando ha una scheda: descrizione, esempi, permessi, moduli che servono, sinonimi, comandi collegati. L'AI sceglie solo da lì e non inventa comandi. | Proposta: ChatGPT r.7666, r.7696–7724, r.8134–8151 («Non deve mai "indovinare" un comando»); SPEC_v2 §1.10.3 | In parte: NF-06 (`core/command_search_logic.py` ha già i sinonimi) | Estendere il registro di NF-06 con esempi, dipendenze e comandi collegati. Modello: nessuno | Nome 32, descrizione 100: le schede lunghe stanno nel file dei testi, non nel comando |
| AI-R-028 | Risposta con al massimo 3 comandi e bottoni che aprono la configurazione | La risposta mostra pochi comandi, spiegati in una riga, con un bottone per aprire subito il pannello giusto. | Proposta: ChatGPT r.7797–7821 («I pulsanti … trasformano l'AI da semplice chatbot in interfaccia»); SPEC_v2 §B.6 | In parte: catalogo AI-013 (bottone "Esegui") | View con al massimo 3 bottoni; il bottone apre il modulo o il pannello del comando. Modello: nessuno | 5 bottoni per riga; scadenza della View |
| AI-R-029 | Stato del comando nella risposta | Accanto a ogni comando: disponibile, già configurato, bloccato da un permesso, bloccato dal premium, spento dal server, manca un modulo. | Proposta: ChatGPT r.7847–7858; SPEC_v2 §B.6 | In parte: SPEC 21.5 mostra solo i comandi che l'utente può usare | Funzione comune in `core/command_search_logic.py` che legge moduli, permessi e premium. Modello: nessuno | — |
| AI-R-030 | Ricerca che guarda il server e propone di attivare ciò che manca | Il bot controlla moduli accesi, canali già impostati e lingua. Se la funzione non è attiva lo dice e chiede "vuoi attivarla?". | Proposta: ChatGPT r.7823–7845 ("ricerca contestuale") | **In nessuna lista** | Stesse funzioni di lettura usate dal pannello web (D16). Modello: nessuno | L'attivazione passa dai permessi di chi preme il bottone |
| AI-R-031 | Richiesta composta: più comandi in fila e "Configura tutto" | L'utente descrive un risultato ("chi entra riceve il ruolo Membro e un messaggio privato"). Il bot elenca i passi, controlla i permessi e offre un bottone per farli tutti. | Proposta: ChatGPT r.8082–8113 ("iYokai Command OS") | **In nessuna lista** | L'AI produce una lista di passi presi dal registro; ogni passo è un comando vero, eseguito con conferma. Modello: testo | Regola "propone, una persona conferma"; al massimo 5 passi |
| AI-R-032 | Scoperta delle funzioni: "cosa posso fare qui?" | L'utente chiede cosa c'è da fare nel server e il bot elenca le attività attive oggi (missioni, eventi, giochi, musica). | Proposta: ChatGPT r.8549–8566 ("Engagement Discovery Engine"); SPEC_v2 §18.2 | **In nessuna lista** | Stessa ricerca dei comandi, filtrata sui moduli attivi; funziona anche senza AI con un elenco fisso. Modello: testo | — |
| AI-R-033 | Domanda libera all'AI | Testo a richiesta: una spiegazione, una poesia, una risposta. | Catalogo AI-001 (MEE6 `/write`); piano NF-24. ChatGPT r.7495 ("Advanced AI assistant", solo il nome) | Catalogo AI-001, NF-24 | `/utility chiedi`. Modello: testo | Policy; consenso; quota per utente; 2000 o 4096 |
| AI-R-034 | Il bot risponde in chat quando viene menzionato | Chiacchierata con il bot nei canali scelti. | Catalogo AI-009 (NadekoBot, MEE6, Yggdrasil) | Catalogo AI-009, NF-24 | Interruttore per canale; pausa per utente. Modello: testo | Serve `message_content`; policy; consenso |
| AI-R-035 | Memoria corta della conversazione | Il bot ricorda gli ultimi scambi del canale per rispondere a tono. | Catalogo AI-011 (NadekoBot, MEE6) | Catalogo AI-011 (non ancora in un piano) | Ultimi N scambi per canale, solo in memoria. Modello: testo | Mai su disco; legata al tempo di conservazione del contesto |
| AI-R-036 | Chiedere a parole di eseguire un comando | "Metti in timeout Mario per 10 minuti": l'AI riconosce il comando e lo propone con un bottone "Esegui". | Catalogo AI-013 (NadekoBot `.prompt`) | Catalogo AI-013 (non ancora in un piano) | Estensione di "cerca comando"; i permessi restano quelli dell'utente. Modello: testo | Regola "propone, una persona conferma" |
| AI-R-037 | Costruzione del server con l'AI | L'admin descrive il server e l'AI propone canali e ruoli. L'admin conferma e il bot li crea. | Catalogo AI-025 (PeakBot, fonte di terzi) | Catalogo AI-025 (non ancora in un piano) | Usa le funzioni del backup (D8) per creare la struttura. Modello: testo | 500 canali, 250 ruoli; conferma obbligatoria |
| AI-R-038 | Messaggi "nello stile" di un utente | Il bot scrive un messaggio imitando lo stile di una persona. | Catalogo AI-024 (Lawliet `imitate`) | Catalogo AI-024 (segnata "da non fare senza consenso") | Solo sull'utente che lancia il comando, con i suoi messaggi recenti e il suo consenso. Modello: testo | Mai su un'altra persona; serve `message_content`; policy |

## 3. Moderazione e sicurezza con AI

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Dov'è oggi | Come farla in iYokai | Prerequisiti e limiti |
|---|---|---|---|---|---|---|
| AI-R-039 | Aiuto alla moderazione: l'AI segnala, lo staff decide | L'AI legge i messaggi segnalati (o un campione) e avvisa lo staff con un motivo. Non cancella e non punisce. | Issue #50 («Assistenza automod (suggerimenti, non ban autonomo non supervisionato)»); catalogo AI-018 (Maki) | Catalogo AI-018 (non ancora in un piano) | Avviso nel canale staff con bottoni Ignora / Warn / Timeout (stesso schema del catalogo AMD-047). Modello: testo | Serve `message_content`; policy; consenso; costo per messaggio alto: solo sui messaggi segnalati |
| AI-R-040 | Classificazione delle segnalazioni degli utenti | Ogni segnalazione fatta con `/utility report` arriva allo staff con un'etichetta (spam, insulti, truffa, altro) e un'urgenza. | Issue #50 («Classificazione report utenti») | **In nessuna lista** | Campo `categoria` e `urgenza` proposti dall'AI nel messaggio allo staff; lo staff può cambiarli. Modello: testo | Policy; consenso. Senza AI: l'utente sceglie la categoria da un menu |
| AI-R-041 | Riassunto di un incidente | Dopo un raid o un attacco il bot scrive cosa è successo: eventi in ordine, utenti coinvolti, azioni già fatte, cosa resta da fare. | Proposta: ChatGPT r.6180–6192 ("AI Incident Summary", `/incident summarize`) | **In nessuna lista** | `/security panico riassunto`: legge gli eventi di sicurezza già salvati nel database. Modello: testo | Solo dati dei log, visibili allo staff; senza AI: elenco in ordine di tempo |
| AI-R-042 | Assistente per le regole di AutoMod | L'admin scrive cosa vuole ottenere ("niente link dai nuovi"). L'AI propone la regola. L'admin la guarda e la attiva. | Proposta: ChatGPT r.6201–6207 ("AI Rule Assistant": «non la attiva automaticamente») | **In nessuna lista** | `/security automod proponi`: l'AI riempie le stesse opzioni dei comandi di AutoMod; bottone "Attiva". Modello: testo | Regola "propone, una persona conferma"; 6 regole a parole chiave per server (limite di Discord) |

## 4. Riassunti e ricerca

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Dov'è oggi | Come farla in iYokai | Prerequisiti e limiti |
|---|---|---|---|---|---|---|
| AI-R-043 | Riassunto di un canale a richiesta | Chi è stato via chiede il riassunto delle ultime ore di un canale. | Piano NF-24; issue #50 («Riassunti … canale»); ChatGPT r.7559 ("Summarization") | SPEC 25.6, NF-24 | `/utility riassumi`; legge solo i canali che l'utente può vedere. Modello: testo | Serve `message_content`; policy; consenso; tetto di messaggi letti; risposta privata |
| AI-R-044 | Riepilogo del server, ogni giorno o ogni settimana | A un'ora fissa (per esempio le 9) il bot pubblica in un canale il riepilogo del periodo. | Proposta: Gemini r.473–481 ("AI Daily Digest"), §H3.1, §D2.1 (r.843: ore 09:00, canale `#daily-recap`); SPEC_v2 §F3.1; Grok r.17; issue #50. **Owner: approvata in blocco** (Gemini r.494: «mi piacciono molto tutte le idee che hai tirato fuori») | In parte: SPEC 25.6 dice "riassunti di canali", non il riepilogo a orario | `/admin ai riepilogo` (canale, ora, frequenza, canali da leggere); lavoro dello scheduler, eseguito da un solo bot. Modello: testo | Serve `message_content`; policy; consenso; solo i canali scelti dall'admin; embed entro 4096 |
| AI-R-045 | Contenuto del riepilogo fatto di numeri | Meme più votato, utente più attivo, clan cresciuto di più, discussione più lunga. Sono conteggi: non serve leggere il testo dei messaggi. | Proposta: Gemini r.477–481, r.845; SPEC_v2 §F3.1. **Owner: approvata in blocco** (Gemini r.494: «mi piacciono molto tutte le idee che hai tirato fuori») | In parte: catalogo LIV-061 (top 10 della settimana pubblicata da sola) | Dati da NF-25 (statistiche), starboard (NF-08) e classifiche dei clan; l'AI scrive solo il tono, nel tema della lore. Modello: nessuno; testo per il tono | Si può fare prima del motore, senza AI |
| AI-R-046 | Avviso su parole chiave quando una discussione si accende | Ogni utente registra fino a 3 parole. Quando in un canale se ne parla molto (più di 10 messaggi), riceve un avviso. | Proposta: Gemini r.483–485 ("Ping Intelligente"), §H3.2, §D2.2–D2.3 (r.846–849); SPEC_v2 §F3.2. **Owner: approvata in blocco** (Gemini r.494: «mi piacciono molto tutte le idee che hai tirato fuori») | In parte: `APP_UTENTE_E_DESKTOP.md` §2.3 ("parole chiave personali", fase F9) e SPEC D.5; manca la soglia dei 10 messaggi | Comando dentro `/utility` (parole chiave personali); contatore per canale e parola in memoria. Modello: nessuno | Serve `message_content`; avviso in DM solo se l'utente lo accetta; mai per canali che l'utente non vede |
| AI-R-047 | Ricerca nei log con una domanda | Lo staff chiede "cosa è successo tra Mario e Luca negli ultimi tre giorni?" e riceve gli eventi in ordine. | Proposta: ChatGPT r.6193–6199 ("AI Log Search": «cerca soltanto nei dati autorizzati») | **In nessuna lista** | `/log cerca domanda:`: l'AI traduce la domanda in filtri (utenti, date, tipi); la ricerca la fa il database. Modello: testo | L'AI non legge il database: propone i filtri. Risposta solo allo staff |
| AI-R-048 | Ricerca assistita sul web o su una base di conoscenza | Il bot cerca un'informazione e risponde con un riassunto e le fonti. | Issue #50 («Ricerca assistita (web/knowledge) via API free/paid») | In parte: catalogo UTL-216 ("cerca qualsiasi cosa", legato a NF-24) | Opzione `cerca: sì` di `/utility chiedi`; servizio di ricerca con chiave a quota. Modello: testo | Quote del servizio in `LIMITI.md`; link passati dal controllo phishing (NF-31) |

## 5. Lore, giochi e narrazione

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Dov'è oggi | Come farla in iYokai | Prerequisiti e limiti |
|---|---|---|---|---|---|---|
| AI-R-049 | Lore del server: tema scelto dall'admin | Ogni server sceglie l'ambientazione. Giochi e testi del bot la seguono. | **Owner: chiesta** (Gemini r.494: «poter scegliere in base al server la lore stessa»). Gemini §E1, §A2; SPEC_v2 §F2; Grok r.13; issue #50 | SPEC 25.7, NF-24, catalogo AI-010 | `/admin ai lore`; tabella `guild_lore_config`. BACKLOG §8: tabella e comando accettati anche prima del motore. Modello: nessuno (la scelta); testo (l'uso) | Testo passato dai filtri |
| AI-R-050 | Temi pronti | Yokai e mitologia giapponese (di partenza), Cyberpunk, Dungeons & Dragons, Invasione aliena, Pirati, Fantascienza spaziale. | Gemini, su richiesta dell'owner: r.533–535, §E1.2, §A2.2 (r.740–744); SPEC_v2 §F2.2. Il tema Yokai di partenza lo chiede l'**owner** (r.494: «la lore degli Yokai … dato che il bot stesso si chiama Yokai») | In parte: SPEC 25.7 non elenca i temi | Menu a tendina in `/admin ai lore`; ogni tema ha il suo dizionario di riserva. Modello: nessuno | 25 voci per menu |
| AI-R-051 | Tema libero scritto dall'admin | L'admin scrive una frase o un testo (fino a 1000 caratteri) che descrive l'ambientazione. | **Owner: chiesta** (Gemini r.494: «una frase, quindi campo capacitivo»). Gemini §A2.2 (r.745) | SPEC 25.7, catalogo AI-010 | Modulo con un campo di testo. Modello: nessuno | `max_length` sul campo; filtri sul testo |
| AI-R-052 | La lore viene chiesta durante il setup | Quando si attiva una funzione a tema, o al primo avvio, il bot chiede il tema. | **Owner: chiesta** (Gemini r.494: «durante il setup viene chiesta una parola … una frase»). Gemini r.531; SPEC_v2 §1.8.1 | **In nessuna lista** | Un passo nel wizard (SPEC 22.16) e nel messaggio di benvenuto del bot. Modello: nessuno | Passo saltabile: senza scelta vale il tema Yokai |
| AI-R-053 | La lore entra in ogni testo dell'AI del server | Boss, dungeon, riepilogo e risposte nei ticket usano il tono del tema. | Gemini, su richiesta dell'owner: §E1.3, §A2.3 (r.747: `get_guild_context`); SPEC_v2 §F2.3; Grok r.13 | In parte: SPEC 25.7 | Una funzione in `core/ai_router.py` aggiunge il tema a ogni richiesta. Modello: testo | Il tema non deve poter scavalcare i filtri di sicurezza |
| AI-R-054 | World Boss: evento di gruppo contro un mostro | Un mostro compare in un canale. Tutti lo combattono insieme con i bottoni: attacco, magia (costa monete), difesa o cura. | Proposta: Gemini r.283–287, §F1.3, §B1.2 (r.757–760); SPEC_v2 §16.11; Grok r.14. **Owner: approvata in blocco** (Gemini r.494: «mi piacciono molto tutte le idee che hai tirato fuori») | **In nessuna lista** (BACKLOG §7 e §8: rimandata; issue #50: "rimandati") | `/fun gioca boss`; View persistente; stato in tabella `boss_events`. Modello: nessuno | 5 bottoni per riga; un evento per canale; aggiornare il messaggio al massimo ogni pochi secondi |
| AI-R-055 | World Boss: comparsa a orario e avvio a mano | Il boss compare da solo ogni giorno o ogni settimana (per esempio venerdì alle 21). Lo staff può anche avviarlo. | Proposta: Gemini r.285, §F1.1, §B1.1 (r.754); SPEC_v2 §16.11. **Owner: approvata in blocco** (Gemini r.494: «mi piacciono molto tutte le idee che hai tirato fuori») | **In nessuna lista** | `/admin ai boss` (canale, giorni, ora); scheduler. Modello: nessuno | Fuso orario del server |
| AI-R-056 | World Boss: mostro creato dall'AI secondo la lore | Nome, aspetto e frasi del mostro nascono dal tema del server e, se si vuole, da cosa è successo nel server. | Gemini, su richiesta dell'owner: §F1.2 (r.572), §B1.1 (r.755); SPEC_v2 §16.11; issue #50 («narrativi basati su eventi server») | **In nessuna lista** | Chiamata al router con il tema; risultato salvato nella libreria; senza AI: mostri pronti del tema. Modello: testo | Policy; consenso; D13. "Eventi del server" = solo numeri (livelli, clan), non il testo dei messaggi |
| AI-R-057 | World Boss: danno secondo il livello, vita secondo i membri attivi | Chi ha un livello più alto fa più danno. La vita del boss dipende da quanti membri sono stati attivi negli ultimi 7 giorni. | Proposta: Gemini r.285 (danno secondo il livello), §F1.4, §B1.3 (r.762); Grok r.14 («HP scalati sul numero di utenti attivi recenti»). **Owner: approvata in blocco** (Gemini r.494: «mi piacciono molto tutte le idee che hai tirato fuori») | **In nessuna lista** | Formule in `core/boss_logic.py`, provate con i test. Modello: nessuno | Dati di attività da NF-25 |
| AI-R-058 | Dungeon di gruppo con scelte votate | Il bot descrive una stanza e propone le scelte ("porta a sinistra", "attacca"). Il gruppo vota con i bottoni, a tempo. | Proposta: Gemini r.432–436, §F1.6, §B1.4 (r.764–765). **Owner: approvata in blocco** (Gemini r.494: «mi piacciono molto tutte le idee che hai tirato fuori»). **Owner** (r.639: «una partitina a … Angels and Dragons in versione Allen Invasion», dettato a voce: Dungeons & Dragons) | **In nessuna lista** (BACKLOG §7 e §8: rimandata) | `/fun gioca dungeon`; un canale scelto dall'admin; voto con bottoni o menu. Modello: nessuno | 25 opzioni per menu; una partita per canale |
| AI-R-059 | Dungeon: la storia continua scritta dall'AI | Dopo ogni voto l'AI scrive la stanza successiva, nel tema del server. | Proposta: Gemini r.434 («il bot genera stanze procedurali»), §B1.4 (r.766); SPEC_v2 §16.11. **Owner: approvata in blocco** (Gemini r.494: «mi piacciono molto tutte le idee che hai tirato fuori») | **In nessuna lista** | Router con il riassunto della partita; senza AI: stanze pronte prese dalla libreria. Modello: testo | Policy; consenso; D13; testo entro 4096 |
| AI-R-060 | Dungeon: esito secondo classi e livelli di chi vota | La riuscita di un'azione dipende da chi sta partecipando in quel momento: classe scelta e livello. | Proposta: Gemini r.436, r.538 («i nomi delle classi»). **Owner: approvata in blocco** (Gemini r.494: «mi piacciono molto tutte le idee che hai tirato fuori») | **In nessuna lista** | Classe scelta dall'utente tra 3–4 del tema; calcolo in `core/dungeon_logic.py`. Modello: nessuno | — |
| AI-R-061 | Misteri: frammenti di storia nascosti dall'admin | L'admin nasconde indizi o codici. Quando la community risolve l'enigma, tutto il server riceve un premio a tempo (XP in più per 24 ore, un canale segreto). | Proposta: Gemini r.438–442. **Owner: approvata in blocco** (Gemini r.494: «mi piacciono molto tutte le idee che hai tirato fuori») | **In nessuna lista** | `/admin ai misteri`: codice, premio, durata; gli utenti rispondono con un comando di `/fun`. Modello: nessuno; testo facoltativo per scrivere gli indizi | Premio con scadenza gestita dallo scheduler |
| AI-R-062 | Personaggi AI creati dagli utenti | Un personaggio con biografia e carattere con cui chattare. | Catalogo AI-014 (MEE6 "AI Characters") | Catalogo AI-014 (non ancora in un piano) | All'inizio un solo personaggio per server (la lore); poi più personaggi con webhook. Modello: testo | 15 webhook per canale; filtri; quota |
| AI-R-063 | Installare e togliere personaggi dal server | L'admin sceglie quali personaggi sono attivi. | Catalogo AI-015 (MEE6) | Catalogo AI-015 (non ancora in un piano) | `/admin ai personaggi`. Modello: nessuno | Tetto per server |
| AI-R-064 | Boss ed eventi di gioco uguali in più server | Lo stesso boss "di rete" pubblicato per tutti i server che lo vogliono. Ogni server combatte la sua copia; in comune c'è solo un contatore con i totali. | Proposta: Grok r.151 («World Boss globali periodici»), r.164–166 (gruppi misti tra server); Gemini r.345–347 (alleanze tra server, nell'elenco approvato in blocco) | **In nessuna lista** (BACKLOG §12: alleanze e gruppi tra server respinti) | L'owner pubblica il boss; l'admin sceglie se partecipare; nessun dato di utenti passa tra server. Modello: testo | Versione ridotta di un'idea respinta: vedi "Idee respinte o rimandate" |

## 6. Immagini, voce e media

Per la **voce** (da voce a testo, lettura ad alta voce) nelle fonti non
c'è niente. Il karaoke con punteggio non usa l'AI: è in
`VOCI_OMESSE.md` (OM-046). La lettura del testo di un'immagine
(`APP_UTENTE_E_DESKTOP.md`, A9) usa una libreria sul server, non un
fornitore AI: non è contata qui.

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Dov'è oggi | Come farla in iYokai | Prerequisiti e limiti |
|---|---|---|---|---|---|---|
| AI-R-065 | Immagine generata da una descrizione | L'utente scrive cosa vuole vedere e riceve un'immagine. | Issue #50 («Generazione immagini (API free iniziale → paid)»); catalogo AI-004 (MEE6 `/imagine`) | SPEC 25.8, NF-24, catalogo AI-004 | `/fun immagina`; filtro sul testo prima e sull'immagine dopo. Modello: immagini | Policy; consenso; D13; file sotto 10 MiB; `defer()` |
| AI-R-066 | Variazioni di un'immagine appena generata | Bottoni sotto il risultato per averne altre versioni. | Catalogo AI-005 (MEE6) | Catalogo AI-005 (non ancora in un piano) | Bottoni sotto l'immagine. Modello: immagini | Ogni variazione conta nella quota |
| AI-R-067 | Ingrandimento dell'immagine generata | Un bottone per averla più grande. | Catalogo AI-006 (MEE6) | Catalogo AI-006 (non ancora in un piano) | Bottone "Ingrandisci". Modello: immagini | Costo a parte; 10 MiB |
| AI-R-068 | Ingrandire e ripulire un'immagine caricata | L'utente carica un'immagine e la riceve più nitida. | Catalogo AI-007 (Lawliet, oggi spento) | Catalogo AI-007 (non ancora in un piano) | Solo se un fornitore lo offre a basso costo. Modello: immagini | Regole di `core/safe_image.py` |
| AI-R-069 | Quota di immagini e pacchetti in più | Un numero di immagini a settimana e la possibilità di comprarne altre. | Catalogo AI-008 (Lawliet, MEE6) | Catalogo AI-008 (non ancora in un piano) | Quota per utente e per server; acquisto solo con il premium vero (NF-22). Modello: nessuno | — |
| AI-R-070 | Immagine del boss nell'annuncio | L'annuncio del World Boss ha un'immagine disegnata dal bot (non dall'AI). | Gemini, su richiesta dell'owner: §B1.1 (r.756: «grafica generata via Pillow»); SPEC_v2 nota 8 | **In nessuna lista** | `core/boss_image.py` con Pillow, fuori dal ciclo principale. Modello: nessuno | Regole di `core/safe_image.py`; `defer()` |

## 7. Ticket e staff

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Dov'è oggi | Come farla in iYokai | Prerequisiti e limiti |
|---|---|---|---|---|---|---|
| AI-R-071 | Bottone "Chiedi all'assistente" dentro il ticket | Prima di chiamare lo staff l'utente può chiedere all'AI, che risponde con le regole e la guida del server. I casi semplici si chiudono così. | Proposta: Gemini r.339, §H2.2, §D1.1 (r.837–838); SPEC_v2 §13.14; Grok r.17. **Owner: approvata in blocco** (Gemini r.494: «mi piacciono molto tutte le idee che hai tirato fuori») | In parte: catalogo AI-019 (risposte AI nei ticket, non in un piano) | Bottone nel primo messaggio del ticket; fonti: base di conoscenza. Modello: testo | Policy; consenso; livello di privacy "solo il ticket" |
| AI-R-072 | Prima risposta automatica nei ticket | All'apertura l'AI risponde da sola alle domande su regole e primi passi. | Proposta: Gemini r.339 («l'AI risponde automaticamente»), §H2.1 (r.617). **Owner: approvata in blocco** (Gemini r.494: «mi piacciono molto tutte le idee che hai tirato fuori») | In parte: catalogo AI-019 | Opzione per pannello in `/admin ticket`; lo staff vede sempre la risposta. Modello: testo | Un solo messaggio automatico per ticket |
| AI-R-073 | Bozza di risposta per lo staff | Lo staff preme un bottone e riceve una bozza. La conferma o la corregge prima di inviarla. | Gemini, su richiesta dell'owner: §D1.2 (r.839–840); SPEC_v2 §13.14; issue #50 («bozza risposta staff») | In parte: catalogo AI-019 ("lo staff può correggerla") | Bottone visibile solo allo staff; bozza in un modulo modificabile. Modello: testo | Campo del modulo fino a 4000 caratteri |
| AI-R-074 | Smistamento dei ticket | All'apertura l'AI propone categoria e urgenza. Lo staff può cambiarle. | Issue #50 («Helpdesk / triage ticket») | **In nessuna lista** | Usa le categorie e la priorità che il ticket ha già (SPEC 13.2, 13.7). Modello: testo | Senza AI resta la scelta dell'utente dal menu |
| AI-R-075 | Riassunto del ticket nel transcript | Il transcript si apre con due righe: di cosa si trattava e come è finita. | Proposta: ChatGPT r.6153–6157 («Summary», «Resolution»); piano NF-24 | SPEC 25.6, NF-24 | Chiamata alla chiusura, prima di cancellare il canale. Modello: testo | Policy; consenso; se l'AI è ferma il transcript esce senza riassunto |

## 8. Livelli, economia e community

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Dov'è oggi | Come farla in iYokai | Prerequisiti e limiti |
|---|---|---|---|---|---|---|
| AI-R-076 | Nomi a tema per moneta, punti e titoli | Il tema dà un nome alla moneta, ai punti esperienza e ai titoli dei livelli. | Gemini, su richiesta dell'owner: §E1.4 (r.564), §A2.1 (r.738: `currency_name`, `rank_title_prefix`), §B3.1 ("Titolo Lore"); SPEC_v2 §F2.1 | In parte: catalogo ECO-001 (nome della moneta scelto dal server, non in un piano) | Colonne in `guild_lore_config`; i testi di `/level` le leggono. Modello: nessuno | Nome fino a 20 caratteri; si può fare prima del motore |
| AI-R-077 | Premi del World Boss | Alla sconfitta: monete e XP a chi ha partecipato, trofei alla cassa del clan, ruoli a tempo, oggetti da collezione. | Proposta: Gemini r.287, §F1.5, §B1.3 (r.763). **Owner: approvata in blocco** (Gemini r.494: «mi piacciono molto tutte le idee che hai tirato fuori») | **In nessuna lista** | Accrediti in una sola transazione; oggetti nel profilo (NF-40). Modello: nessuno | Tetto ai premi per evento; `check_role_assignable` per i ruoli |
| AI-R-078 | Frammenti di lore da collezionare | Pezzi di storia che si sbloccano facendo attività diverse. Raccolti tutti, aprono una storia o un titolo raro. | Proposta: Grok r.132–133; SPEC_v2 §16.14 | **In nessuna lista** | Oggetti di tipo "frammento" nella collezione (NF-40); testi presi dalla libreria. Modello: nessuno; testo per scriverli | — |
| AI-R-079 | Spirito Yokai: affinità che cresce con l'attività | Ogni utente sviluppa un legame con uno spirito secondo ciò che fa (vocale, scrittura, giochi). Dà titoli e piccoli vantaggi e colora i testi dell'AI. | Proposta: Grok r.124–126; SPEC_v2 §16.13 | **In nessuna lista** | Calcolo dai contatori che già esistono; spirito scelto o proposto, sempre cambiabile. Modello: nessuno; testo per il tono | È una lettura del comportamento: solo conteggi, su richiesta dell'utente, mai usata per permessi o moderazione |
| AI-R-080 | Traguardo "primo comando scoperto con l'AI" | Una medaglia per chi usa per la prima volta la ricerca a parole. | Proposta: ChatGPT r.8314 | **In nessuna lista** | Una riga nella tabella dei traguardi (NF-41). Modello: nessuno | — |

## 9. Traduzione e lingue

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Dov'è oggi | Come farla in iYokai | Prerequisiti e limiti |
|---|---|---|---|---|---|---|
| AI-R-081 | Traduci un messaggio o un testo | Dal menu del messaggio o con un comando l'utente ottiene la traduzione. | Proposta: Grok r.160 («/translate (se si integra un provider free)»); SPEC_v2 §B.4 | SPEC B.2, `APP_UTENTE_E_DESKTOP.md` A1 e C9 | Servizio di traduzione con tetto; l'AI come riserva. Modello: testo | 5 messaggi dopo la prima risposta dove l'app non è nel server |
| AI-R-082 | Traduzione automatica dei messaggi di un canale | Nei canali scelti ogni messaggio viene tradotto. | Catalogo AI-020 (NadekoBot) | Catalogo AI-020 (non ancora in un piano) | Traduzione come risposta del bot. Modello: testo | Serve `message_content`; quota del servizio |
| AI-R-083 | Traduzione reagendo con una bandiera | Una reazione con la bandiera di un paese fa tradurre il messaggio in quella lingua. | Catalogo AI-021 (NadekoBot) | Catalogo AI-021 (non ancora in un piano) | Evento della reazione; pausa per messaggio. Modello: testo | Quota del servizio |
| AI-R-084 | Traduzione che raccoglie i messaggi successivi dello stesso autore | Più messaggi di fila dello stesso autore tradotti insieme. | Catalogo AI-022 (Lawliet) | Catalogo AI-022, NF-36 | Miglioria della voce "Traduci" dell'app utente. Modello: testo | — |
| AI-R-085 | Elenco delle lingue per la traduzione | L'utente vede e sceglie le lingue disponibili. | Catalogo AI-023 (NadekoBot) | Catalogo AI-023, NF-36 | Completamento automatico dell'opzione `lingua`. Modello: nessuno | 25 voci alla volta |
| AI-R-086 | Riconoscere la lingua della domanda | Il bot capisce in che lingua è scritta la domanda e la porta alla lingua interna prima di cercare. | Proposta: ChatGPT r.7779–7785 («Language Detection», «Traduzione/normalizzazione interna») | **In nessuna lista** | Passo in `core/command_search_logic.py`; prima i sinonimi di NF-06, poi l'AI. Modello: testo | — |
| AI-R-087 | Cache delle traduzioni | Un testo già tradotto non viene tradotto di nuovo. | Proposta: ChatGPT r.8124 («Translation Cache») | **In nessuna lista** | Stessa tabella della cache delle risposte, con la coppia di lingue nella chiave. Modello: nessuno | Scadenza; niente dati personali in cache |
| AI-R-088 | L'AI risponde nella lingua giusta | Risposte nella lingua del server; per i comandi personali nella lingua dell'utente. | Catalogo AI-016 (MEE6); ChatGPT r.7730–7741 («risponde nella lingua preferita dall'utente») | Catalogo AI-016, NF-24 | La lingua (NF-06) viene passata a ogni richiesta. Modello: testo | — |

## 10. Owner e analisi

Nelle fonti non c'è nessuna funzione di **analisi** fatta con l'AI
(statistiche spiegate, previsioni). Le statistiche proposte sono
conteggi normali: vedi NF-25 e `VOCI_OMESSE.md`.

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Dov'è oggi | Come farla in iYokai | Prerequisiti e limiti |
|---|---|---|---|---|---|---|
| AI-R-089 | Scelta del modello e della lunghezza delle risposte | L'owner decide quale modello usare e quanto può essere lunga una risposta. | Catalogo AI-012 (NadekoBot) | Catalogo AI-012, NF-24 | `/owner ai modello`. Modello: nessuno | `/owner` ha 7 sotto-gruppi: nessun figlio nuovo, tutto dentro `ai` |
| AI-R-090 | Spesa e uso visti dall'owner | L'owner vede quanto consuma ogni server e ogni funzione, e quanto resta. | Proposta: ChatGPT r.7304–7312 ("Usage Metering"); Gemini §A1.4 | In parte: SPEC 25.4 (conteggio) | `/owner ai spesa`: elenco a pagine. Modello: nessuno | Embed entro 4096; pagine da 10 righe |
| AI-R-091 | Richieste di cancellazione dei dati lette prima dall'AI | Quando un utente chiede la cancellazione dei suoi dati, l'AI prepara per l'owner un riassunto della richiesta. Decide l'owner. | **Owner: chiesta** (issue #46, "Specifica utente": «AI in seguito per elaborare»); issue #50 | **In nessuna lista** | `/owner privacy richieste` mostra riassunto e proposta; `/owner privacy approva` resta a mano. Modello: testo | L'AI non cancella nulla; il testo della richiesta va a un fornitore: serve la policy |

## 11. App utente e Desktop

Per il **Desktop** nelle fonti non c'è nessuna funzione AI oltre alla
traduzione rapida.

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Dov'è oggi | Come farla in iYokai | Prerequisiti e limiti |
|---|---|---|---|---|---|---|
| AI-R-092 | Cerca comando e scoperta delle funzioni dentro l'app utente | La ricerca a parole funziona anche dall'app installata sull'utente, in ogni server e in DM. | Proposta: SPEC_v2 §B.6; ChatGPT r.8003 (`/i command-search`) | In parte: `APP_UTENTE_E_DESKTOP.md` C13 (cerca comando senza AI) | Stessa funzione di `/utility cerca-comando`. Modello: testo | Dove il bot non c'è: 5 messaggi dopo la prima risposta; nessuna lettura del canale |
| AI-R-093 | Assistente AI personale | Un assistente privato che l'utente usa ovunque, anche in DM. | Proposta: ChatGPT r.3327 («AI privata») | **In nessuna lista** (il catalogo AI-003 parla solo dell'abbonamento personale) | Comando dell'app utente; quota personale. Modello: testo | Policy; il consenso qui lo dà l'utente; 5 messaggi dopo la prima risposta |
| AI-R-094 | Preferenza personale: assistente acceso o spento | Ogni utente può spegnere per sé le risposte dell'AI. | Proposta: ChatGPT r.8779 («AI Assistant: Attivo») | **In nessuna lista** | Una voce nelle impostazioni personali (`APP_UTENTE_E_DESKTOP.md` C15). Modello: nessuno | — |
| AI-R-095 | Spiega o riassumi un messaggio | Dal menu del messaggio: una spiegazione o un riassunto di quel solo messaggio. | Piano: `APP_UTENTE_E_DESKTOP.md` A8 | SPEC B.2, `APP_UTENTE_E_DESKTOP.md` A8 | Voce del menu sul messaggio. Modello: testo | Solo quel messaggio; risposta privata |
| AI-R-096 | "Spiega questo Yokai": scheda di lore a richiesta | L'utente chiede di una creatura o di un termine del tema e riceve una scheda. | Proposta: Grok r.162; SPEC_v2 §B.4 («lookup lore») | **In nessuna lista** | Comando dell'app utente e di `/fun`; prima la libreria, poi l'AI. Modello: testo | Tema Yokai di partenza dove il bot non c'è |
| AI-R-097 | Desktop: traduzione rapida | Un tasto traduce il testo copiato. | Domanda dell'owner del 04/10 (`APP_UTENTE_E_DESKTOP.md`, domanda 2: «traduzioni») | SPEC D.8 | Chiamata al servizio iYokai. Modello: testo | Invio automatico a nome dell'utente: vietato |

## 12. Pannello web

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Dov'è oggi | Come farla in iYokai | Prerequisiti e limiti |
|---|---|---|---|---|---|---|
| AI-R-098 | Pagina AI del pannello | Dal sito l'admin accende l'AI, sceglie canali, tetto, livello di privacy e lore. | Decisione D16 (dell'owner): tutto ciò che si fa con i comandi si fa anche dal pannello | SPEC 24.2, D16 | Stesse funzioni di `/admin ai`. Modello: nessuno | Stessi controlli dei comandi |
| AI-R-099 | Riepilogo del server visibile sul pannello | Il riepilogo giornaliero o settimanale si legge anche dal sito. | Proposta: Gemini r.475 («nel canale comunicati o via Web Panel»). **Owner: approvata in blocco** (Gemini r.494: «mi piacciono molto tutte le idee che hai tirato fuori») | **In nessuna lista** | Ultimi riepiloghi salvati per server. Modello: nessuno | Visibile solo a chi può vedere il canale del riepilogo |
| AI-R-100 | Pagina "Uso dell'AI" nel centro privacy | L'owner del server vede quali funzioni usano i contenuti, per quanto vengono tenuti e quali dati vanno a servizi esterni. | Proposta: ChatGPT r.6407–6425 ("Privacy Center": «AI Usage») | **In nessuna lista** | Pagina del pannello che legge il registro dei dati (NF-04) e l'elenco dei fornitori. Modello: nessuno | Deve dire le stesse cose della policy |

## 13. Richieste dell'owner del 05/10/2026

Dette dall'owner a voce il 05/10/2026. Principio (D19): l'AI entra in
ogni area del bot per migliorare il servizio; ciò che produce si
**salva e si riusa**, così nel tempo servono meno chiamate.

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Dov'è oggi | Come farla in iYokai | Prerequisiti e limiti |
|---|---|---|---|---|---|---|
| AI-R-101 | Scelta del servizio per tipo di lavoro e per fascia | Lo snodo guarda il tipo di richiesta e la manda al servizio adatto: una chiacchiera va al servizio meno pregiato; codice, immagini, audio, musica e video vanno ai servizi fatti per quello. | **Owner: chiesta** (05/10) | In parte: AI-R-001 e AI-R-006 parlavano solo di cascata e di "regole prima dell'AI" | `core/ai_router.py`: ogni chiamata dichiara tipo e fascia; tabella dei servizi in configurazione. Dettaglio in `.claude/agents/custode-ai.md`. Modello: tutti | Serve l'elenco dei servizi dall'owner |
| AI-R-102 | Quote dei servizi contate in anticipo | Per ogni servizio il bot conosce richieste e token al minuto, all'ora, al giorno o alla settimana. Conta l'uso e, vicino al limite (85 %), passa al servizio successivo prima di ricevere un errore. | **Owner: chiesta** (05/10) | In parte: AI-R-003 metteva in pausa solo **dopo** un errore | `core/ai_cost_logic.py`: contatori per finestra; lettura dei limiti dichiarati dal servizio nelle risposte. Modello: nessuno | I limiti dei livelli gratuiti cambiano: li ricontrolla la sentinella |
| AI-R-103 | Controllo delle chiavi e avviso all'owner | Ogni ora il bot controlla che ogni chiave funzioni e quanta quota resta. Se una chiave non va o sta finendo, scrive all'owner in privato. Una volta al giorno manda il riepilogo dell'uso. | **Owner: chiesta** (05/10) | **In nessuna lista** | Worker nel bot; chiamata che non consuma token (elenco dei modelli). Modello: nessuno | Le chiavi stanno solo nel `.env` |
| AI-R-104 | Risposte standard imparate dallo staff nei ticket | Quando un moderatore risponde a una richiesta ricorrente (per esempio i requisiti per l'affiliazione di un canale Twitch, con il pacchetto delle grafiche), il bot propone di salvarla come risposta standard. Al ticket successivo sullo stesso tema la dà subito, con gli stessi allegati. | **Owner: chiesta** (05/10) | In parte: AI-R-025 (testi caricati dall'admin a mano) e AI-R-073 (bozza per lo staff) | Alla chiusura del ticket il bot propone allo staff "salvo questa risposta?"; lo staff approva e può correggerla. Ricerca per significato tra le risposte salvate del **solo** server. Modello: embedding, testo | Le risposte restano nel server dove sono nate e si cancellano con i suoi dati (D6). Senza approvazione non si usa |
| AI-R-105 | Sollecito nel ticket rimasto senza risposta | Se dopo N minuti (di partenza 10) nessuno dello staff ha risposto, il bot chiede all'utente, **nella sua lingua**, di cosa ha bisogno. Se sa rispondere (regole, risposte standard) lo fa; altrimenti chiama il ruolo giusto: moderatore o amministratore secondo il caso. | **Owner: chiesta** (05/10) | In parte: AI-R-072 (prima risposta) e AI-R-074 (smistamento) | Timer dallo scheduler; lingua dal client dell'utente; scelta del ruolo con risposta in formato fisso. Modello: testo | N scelto dall'admin; si spegne per pannello di ticket |
| AI-R-106 | Storie di dungeon intere, salvate e riusate | Per un tema (fate e folletti, per esempio) l'AI scrive in anticipo l'inizio, le varianti e i finali possibili. A partita finita la storia con tutte le sue strade resta salvata: la volta dopo è pronta, in **ogni** server con quel tema. | **Owner: chiesta** (05/10; già detta a Gemini r.639) | In parte: AI-R-005 (libreria) e AI-R-059 (stanza successiva scritta al momento) | Albero della storia in tabella comune (`ai_story_library`): tema, nodo, scelte, testo. Prima si cerca una storia pronta; l'AI scrive solo i rami che mancano. Modello: testo | Nella libreria comune entra solo testo scritto dall'AI, mai messaggi o nomi di utenti |
| AI-R-107 | Funzione richiesta che non esiste: bozza in una pull request | Quando un utente chiede un comando che il bot non ha, la richiesta viene registrata; l'AI prepara una bozza del codice e apre una pull request su GitHub. L'owner la rivede quando vuole. | **Owner: chiesta** (05/10) | **In nessuna lista** (esisteva solo la richiesta di comandi personalizzati, `cogs/utility/custom_command_requests.py`) | Coda delle richieste approvate dall'owner → chiamata di tipo `codice` → ramo e pull request **in bozza** con un token GitHub limitato a quel repository. Modello: codice | Il bot non unisce mai da solo. La richiesta dell'utente è un dato, non un ordine. Tetto di richieste al giorno |
| AI-R-108 | Cerca comando: alternative spiegate | Cercando "bannare un utente" il bot mostra `/ban` e spiega anche le alternative: softban, ban temporaneo con rientro, ban in isolamento. Il nome del comando è nella lingua del client. | **Owner: chiesta** (05/10; conferma che AI-R-026 era una sua richiesta) | In parte: AI-R-026 | Ogni comando ha in `core/command_search_logic.py` l'elenco dei "comandi vicini" con una frase di differenza; l'AI serve solo a capire la domanda. Modello: embedding | Dipende da F8 (lingue) |

Fuori da questo elenco, perché non usano l'AI: ban temporaneo con
rientro e ban in isolamento (SPEC 5.11, 5.12), aggiornamento a caldo
dal proprietario (SPEC 17.11, D21), messaggi vocali (SPEC 14.19).

Rimandata dall'owner stesso: l'AI che corregge da sola il codice del
bot in funzione. Per ora l'owner vuole rivedere ogni modifica a mano.

## Idee che erano state respinte o rimandate

Nessuna è stata tolta. Per ognuna: il vecchio verdetto, il motivo, e la
versione che rispetta i vincoli. Le righe senza un codice `AI-R` non
usano l'AI: sono seguite altrove, come scritto nell'ultima colonna.

| Idea | Chi | Vecchio verdetto | Perché | Versione che rispetta i vincoli | Dove è seguita |
|---|---|---|---|---|---|
| L'intero motore AI | Gemini, ChatGPT, Grok; l'owner lo chiede (Gemini r.639) | BACKLOG §8: rimandato | Tre motivi: serve leggere i messaggi; i messaggi vanno a fornitori esterni (GDPR); dipende da livelli gratuiti che possono cambiare | È la fase F12. L'intent è acceso (D9). Prima la policy e il consenso. Tetto di spesa e risposta locale (D13). Interruttore per le chiavi a pagamento | Tutto questo file |
| AI che modera da sola e punisce | Nessuno la chiede. ChatGPT r.7416–7418 la sconsiglia («Troppo rischiosa») | BACKLOG §12: respinta. Issue #50, dipendenza 4 | Sbaglia, e nessuno ricontrolla | L'AI segnala, lo staff decide. Nessuna azione parte senza una persona | AI-R-039, AI-R-015 |
| World Boss e Dungeon | Gemini; owner: approvati in blocco | BACKLOG §7: rimandati («per ultimi»); BACKLOG §8 | Costosi da bilanciare; il bot non aveva ancora server; il testo veniva dall'AI | In piano dopo il motore. Le regole del gioco non usano l'AI. Se l'AI è ferma si usano mostri e stanze già pronti | AI-R-054–AI-R-060, AI-R-077 |
| Riepilogo giornaliero e avviso su parole chiave | Gemini; owner: approvati in blocco | BACKLOG §8: rimandati | Leggono i messaggi di tutti | Solo i canali scelti dall'admin. La parte fatta di numeri non legge il testo. Nessun testo salvato | AI-R-044, AI-R-045, AI-R-046 |
| Boss ed eventi condivisi tra server; gruppi misti tra server | Grok r.151, r.164–166; Gemini r.345–347 | BACKLOG §12: respinti (alleanze e gruppi tra server) | Lavoro di manutenzione continuo; dati che passano tra server | Boss "di rete": ogni server combatte la sua copia; in comune solo i totali; partecipa chi vuole | AI-R-064; `VOCI_OMESSE.md` OM-057 |
| Reputazione globale calcolata dalle sanzioni; segno "fedina pulita"; punteggio di fiducia tra server | Gemini r.405–407; Grok r.127–129, r.145–146; SPEC_v2 §B.2 | BACKLOG §9: **respinta**, non rimandata. ChatGPT r.7899 è d'accordo | Un ban ingiusto ti seguirebbe in ogni server. È una decisione automatica su una persona (GDPR, art. 22). Un admin scorretto potrebbe rovinare qualcuno ovunque | Profilo globale con **soli dati positivi**, scelti dall'utente: livelli, medaglie, collezioni. Nessuna sanzione esce dal server. Il punteggio di rischio resta dentro il server, lo vede solo lo staff, e non fa partire niente da solo | SPEC B.6 e 23.17 (NF-41); `VOCI_OMESSE.md` OM-012 |
| L'AI legge tutto lo storico del server | ChatGPT r.6269 lo mette come livello più largo («Full Authorized Context») | Mai valutata | Troppi dati verso l'esterno | Di partenza l'AI vede solo il ticket o il messaggio su cui è chiamata. Il livello largo si accende con una conferma scritta | AI-R-016 |
| Messaggi "nello stile" di un utente | Catalogo AI-024 (Lawliet) | Catalogo: «da non fare senza il consenso» | Usa i messaggi di una persona | Solo su chi lancia il comando | AI-R-038 |
| AI "addestrata" sui contenuti del server | Gemini r.339 usa la parola «addestrabile» | Mai stata la richiesta dell'owner | L'owner non vuole addestrare un modello: vuole usare servizi esistenti e tenere uno storico da riusare (D19). Ciò che Discord vieta è l'addestramento sui messaggi | I testi vengono passati al momento della domanda e le risposte utili si salvano per riusarle. Nessun addestramento | AI-R-025 |
| Dipendere solo dai livelli gratuiti | Gemini r.510–522 | BACKLOG §8, punto 3: rischio | Se un fornitore cambia le regole, tutto si ferma insieme | Più fornitori, risposta locale, tetto di spesa, interruttore per le chiavi a pagamento | AI-R-001, AI-R-002, AI-R-008 |
| Premi automatici allo staff "più efficiente" | Gemini r.400; Grok r.111 | BACKLOG §11: la misura sì, i premi automatici no | Spinge a punire di più per guadagnare di più | Solo la misura, privata. I premi li dà l'admin a mano | SPEC 23.17 (NF-41) |
| Tribunale dei pari | Gemini r.460–464; in SPEC_v2 è tra le funzioni AI (§F3.3) ma non usa l'AI | BACKLOG §12: respinto | Membri scelti a caso che ribaltano lo staff | Parere di un secondo gruppo dentro l'appello; decide lo staff | `VOCI_OMESSE.md` OM-011 |

## Ordine consigliato dentro la fase F12

La fase F12 dipende da F5 (privacy policy) e F8 (lingue). Dentro la
fase l'ordine consigliato è questo. Il **passo 0 non manda niente a
nessun fornitore**: si può fare anche prima della policy.

**Passo 0 — Subito, senza AI e senza policy.** Nessun dato esce dal bot. Si può costruire prima del motore.

- AI-R-002, AI-R-005, AI-R-009, AI-R-010, AI-R-011, AI-R-012, AI-R-014, AI-R-015, AI-R-016, AI-R-017, AI-R-018, AI-R-019, AI-R-025, AI-R-027, AI-R-029, AI-R-045, AI-R-046, AI-R-049, AI-R-050, AI-R-051, AI-R-052, AI-R-076, AI-R-094.

**Passo 1 — Il motore.** Si scrive e si prova con fornitori finti. Si accende con dati veri solo dopo policy e consenso.

- AI-R-001, AI-R-003, AI-R-004, AI-R-006, AI-R-007, AI-R-008, AI-R-013, AI-R-020, AI-R-022, AI-R-053, AI-R-088, AI-R-089, AI-R-090.

**Passo 2 — Prime funzioni con l'AI.** **Serve la policy pubblicata e il consenso dell'admin.**

- AI-R-024, AI-R-026, AI-R-028, AI-R-030, AI-R-033, AI-R-043, AI-R-071, AI-R-072, AI-R-073, AI-R-074, AI-R-075, AI-R-081, AI-R-086, AI-R-087, AI-R-095.

**Passo 3 — Staff, riepiloghi e owner.** Serve policy e consenso. Il riepilogo a orario legge più messaggi: va acceso canale per canale.

- AI-R-039, AI-R-040, AI-R-041, AI-R-042, AI-R-044, AI-R-047, AI-R-048, AI-R-091, AI-R-098, AI-R-099, AI-R-100.

**Passo 4 — Giochi a tema.** Le regole di gioco non usano l'AI; i testi sì (policy, consenso, D13).

- AI-R-031, AI-R-032, AI-R-054, AI-R-055, AI-R-056, AI-R-057, AI-R-058, AI-R-059, AI-R-060, AI-R-061, AI-R-064, AI-R-070, AI-R-077, AI-R-078, AI-R-079, AI-R-080.

**Passo 5 — Il resto.** Immagini, personaggi, traduzione automatica, app utente, premium.

- AI-R-021, AI-R-023, AI-R-034, AI-R-035, AI-R-036, AI-R-037, AI-R-038, AI-R-062, AI-R-063, AI-R-065, AI-R-066, AI-R-067, AI-R-068, AI-R-069, AI-R-082, AI-R-083, AI-R-084, AI-R-085, AI-R-092, AI-R-093, AI-R-096, AI-R-097.

**Cosa chiede per forza la policy prima:** ogni riga con modello
*testo* o *immagini*, perché un testo scritto da un utente o preso dal
server va a un fornitore esterno. Le righe con modello solo *nessuno*
(45 su 100) non mandano niente fuori.

**Fatto quando** (resta la regola di F12): con tutti i fornitori spenti
il bot dà la risposta locale; il tetto di spesa di un server non viene
mai superato; nessuna azione parte senza la conferma di una persona.

## Idee aggiuntive (non discusse)

**Queste non vengono dalle fonti.** Le aggiungo io: sono usi comuni
dell'AI che nessuno ha nominato. Non hanno un codice `AI-R` e non sono
in `SPEC.md`. Decide l'owner se farle entrare.

| # | Idea | Cosa farebbe | Modello | Attenzione |
|---|---|---|---|---|
| 1 | Messaggi vocali trascritti | Un messaggio vocale diventa testo, a richiesta, dal menu del messaggio | voce | Solo quel messaggio; policy; costo per minuto |
| 2 | Lettura ad alta voce in vocale | Il bot legge un testo nel canale vocale | voce | Usa un bot musicale libero; filtri sul testo |
| 3 | Descrizione delle immagini | Per chi non vede: il bot descrive un'immagine a richiesta | immagini → testo | Solo quell'immagine; policy |
| 4 | Seconda opinione sui link sospetti | Dopo la lista di phishing (NF-31), l'AI guarda i link dubbi | testo | Solo segnalazione allo staff |
| 5 | Avviso "clima teso" in un canale | Lo staff riceve un avviso quando una discussione degenera | testo | Solo canali scelti; mai un'azione automatica |
| 6 | Immagini non adatte fuori dai canali NSFW | Segnalazione allo staff | immagini | Costo alto; falsi positivi; solo segnalazione |
| 7 | Missioni scritte dall'AI secondo la lore | Le missioni (NF-41) hanno testi a tema | testo | Regole e premi restano fissi |
| 8 | Nomi e descrizioni degli oggetti del negozio a tema | L'admin chiede una proposta e la corregge | testo | Conferma dell'admin |
| 9 | Benvenuto a tema proposto all'admin | L'AI propone il testo di benvenuto nel tono della lore | testo | L'admin lo salva: nessuna chiamata a ogni ingresso |
| 10 | Riassunto delle candidature | Le risposte a un modulo (NF-34) arrivano allo staff con due righe di sintesi | testo | Policy; decide lo staff |
| 11 | Suggerimenti doppi raggruppati | I suggerimenti simili vengono proposti come uno solo | embedding | Conferma dello staff |
| 12 | Statistiche spiegate a parole | "Questo mese i nuovi membri sono rimasti di più" | testo | Solo numeri aggregati, nessun nome |
| 13 | Titolo automatico di ticket e thread | Un titolo breve al posto di `ticket-0001` | testo | Rinomina 2 ogni 10 minuti per canale (`LIM-3`) |

## Dove sta ogni codice in `SPEC.md`

Dal 05/10/2026 ogni riga di questo file ha una voce in `SPEC.md` §25.
Le voci 25.1–25.9 c'erano già e raccolgono più righe.

| Codice | Voce | Codice | Voce | Codice | Voce | Codice | Voce |
|---|---|---|---|---|---|---|---|
| AI-R-001 | 25.1 | AI-R-026 | 25.25 | AI-R-051 | 25.7 | AI-R-076 | 25.69 |
| AI-R-002 | 25.1 | AI-R-027 | 25.26 | AI-R-052 | 25.47 | AI-R-077 | 25.70 |
| AI-R-003 | 25.10 | AI-R-028 | 25.27 | AI-R-053 | 25.48 | AI-R-078 | 25.71 |
| AI-R-004 | 25.2 | AI-R-029 | 25.28 | AI-R-054 | 25.49 | AI-R-079 | 25.72 |
| AI-R-005 | 25.11 | AI-R-030 | 25.29 | AI-R-055 | 25.50 | AI-R-080 | 25.73 |
| AI-R-006 | 25.12 | AI-R-031 | 25.30 | AI-R-056 | 25.51 | AI-R-081 | 25.74 |
| AI-R-007 | 25.1 | AI-R-032 | 25.31 | AI-R-057 | 25.52 | AI-R-082 | 25.75 |
| AI-R-008 | 25.13 | AI-R-033 | 25.5 | AI-R-058 | 25.53 | AI-R-083 | 25.76 |
| AI-R-009 | 25.4 | AI-R-034 | 25.32 | AI-R-059 | 25.54 | AI-R-084 | 25.77 |
| AI-R-010 | 25.4 | AI-R-035 | 25.33 | AI-R-060 | 25.55 | AI-R-085 | 25.78 |
| AI-R-011 | 25.14 | AI-R-036 | 25.34 | AI-R-061 | 25.56 | AI-R-086 | 25.79 |
| AI-R-012 | 25.15 | AI-R-037 | 25.35 | AI-R-062 | 25.57 | AI-R-087 | 25.80 |
| AI-R-013 | 25.3 | AI-R-038 | 25.36 | AI-R-063 | 25.58 | AI-R-088 | 25.81 |
| AI-R-014 | 25.16 | AI-R-039 | 25.37 | AI-R-064 | 25.59 | AI-R-089 | 25.82 |
| AI-R-015 | 25.17 | AI-R-040 | 25.38 | AI-R-065 | 25.8 | AI-R-090 | 25.83 |
| AI-R-016 | 25.18 | AI-R-041 | 25.39 | AI-R-066 | 25.60 | AI-R-091 | 25.84 |
| AI-R-017 | 25.9 | AI-R-042 | 25.40 | AI-R-067 | 25.61 | AI-R-092 | 25.85 |
| AI-R-018 | 25.19 | AI-R-043 | 25.6 | AI-R-068 | 25.62 | AI-R-093 | 25.86 |
| AI-R-019 | 25.9 | AI-R-044 | 25.41 | AI-R-069 | 25.63 | AI-R-094 | 25.87 |
| AI-R-020 | 25.20 | AI-R-045 | 25.42 | AI-R-070 | 25.64 | AI-R-095 | 25.88 |
| AI-R-021 | 25.21 | AI-R-046 | 25.43 | AI-R-071 | 25.65 | AI-R-096 | 25.89 |
| AI-R-022 | 25.22 | AI-R-047 | 25.44 | AI-R-072 | 25.66 | AI-R-097 | 25.90 |
| AI-R-023 | 25.23 | AI-R-048 | 25.45 | AI-R-073 | 25.67 | AI-R-098 | 25.91 |
| AI-R-024 | 25.5 | AI-R-049 | 25.7 | AI-R-074 | 25.68 | AI-R-099 | 25.92 |
| AI-R-025 | 25.24 | AI-R-050 | 25.46 | AI-R-075 | 25.6 | AI-R-100 | 25.93 |

## Conteggio

100 righe `AI-R`: 39 già in una lista, 23 in parte, 38 in nessuna lista.
12 idee respinte o rimandate, tutte con la versione che rispetta i vincoli.
13 idee aggiuntive, non discusse.
