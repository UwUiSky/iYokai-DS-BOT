# Parole d'odio: come funziona la difesa

Questo documento spiega le regole, non elenca le parole. Le liste stanno nei file
`data/automod_parole_odio.txt` (insulti sempre vietati) e `data/automod_parole_sospette.txt`
(parole che sono anche cognomi o parole normali).

## I tre livelli

1. **Blocco preventivo (AutoMod di Discord).** Una frase palesemente d'odio, cioè un insulto
   razzista della lista di base vicino a una minaccia o a un incitamento (in un verso o
   nell'altro), viene fermata *prima* dell'invio. Chi scrive vede il banner di Discord con il
   testo scelto dal server (fino a 150 caratteri). Il bot non vede quel messaggio.
   - Si accende con `/automod odio blocco`. Di base è spento.
   - Il testo predefinito è: «Primo richiamo: la tua affermazione risulta razzista. Rispetta le regole del server.»
   - Il bot crea e tiene allineata una regola chiamata «iYokai — Odio». Conta come una delle 6
     regole a parole chiave che Discord permette: se il server le ha già tutte, il bot lo dice.
   - La regola riconosce solo la scrittura normale. Le versioni camuffate le prende il livello 2.
2. **Insulto da solo (filtro del bot).** Gli insulti della lista di base si cancellano subito,
   anche camuffati (cifre al posto delle lettere, spazi, simboli).
3. **Parola sospetta.** Una parola che può essere un cognome o un uso normale non si cancella a
   priori: il bot chiede all'AI di giudicare il contesto.
   - «Simone Negri lavora al supermercato»: passa. Una frase che offende delle persone: il
     messaggio viene cancellato.
   - Chi ha scritto riceve un richiamo nel canale, che sparisce dopo 10 secondi (se il canale non
     lo permette, arriva in privato). Il richiamo viene contato.
   - Con l'AI ferma il messaggio si cancella ma il richiamo **non** si conta (può essere un cognome).
   - Un testo oltre i 2000 caratteri, o che prova a dare ordini all'AI («ignora le istruzioni…»,
     parentesi graffe, «verdetto»), non si manda all'AI: si cancella (lato sicuro). Anche una
     risposta dell'AI che non è esattamente il JSON atteso vale il lato sicuro.
   - Con 3 richiami in 60 minuti scatta un timeout di 60 minuti. I tre numeri si cambiano con
     `/automod odio richiami`. Chi può gestire il server non riceve il timeout automatico.
   - **Con l'AI ferma, spenta o in errore il bot sceglie il lato sicuro:** cancella il messaggio e
     lo dice. Il server sceglie se mandare messaggi all'AI (consenso dell'admin, D19): senza
     consenso vale lo stesso lato sicuro.
   - La decisione si ricorda per frase (ignorando maiuscole e punteggiatura), quindi la stessa
     frase non si paga due volte. Il testo, prima dell'invio, perde i dati personali.
   - Il lavoro dell'AI non conta sulla quota della singola persona.
   - Se la lista di base è spenta, anche le parole sospette non vengono controllate.

## La libreria mondiale

Le parole e le varianti (in più lingue) stanno in una tabella globale, con uno stato:

| Stato | Cosa vuol dire |
|---|---|
| base | voce messa dal proprietario del bot, vale in tutti i server |
| candidata | variante nuova trovata dall'AI, vale solo nei server che l'hanno segnalata |
| approvata | vale in tutti i server |
| rifiutata | non vale mai e non risale con nuove segnalazioni |

Come cresce:

- Quando l'AI giudica un insulto può indicare altre parole offensive del messaggio. Il bot le
  accetta solo se stanno davvero nel testo e se i filtri non le conoscono già: entrano come
  **candidate**.
- Una candidata diventa **globale** quando la segnalano server di **almeno 3 proprietari diversi**
  (contano solo i server con almeno 25 membri), oppure quando la approva il proprietario del bot.
  Un server solo, anche se segnala cento volte, conta uno; tre server dello stesso proprietario
  contano uno.
- Non diventano mai candidate: parole sotto le 4 lettere, solo numeri, parole comuni («ciao»,
  «gente», «people»…) e parole lecite della lista di base.
- Un server non può riempire la libreria: al massimo 200 candidate per server.
- Dalla libreria non si salvano testi di messaggi né utenti: solo la variante, la lingua e gli ID
  dei server che l'hanno segnalata.

Il proprietario del bot gestisce la libreria con `/automod odio libreria` (elenca le candidate con
il numero di server, approva, rifiuta, aggiungi una voce di base). Il comando risponde solo a lui.

## Limiti di Discord che contano qui

Sono nella lista `revisione/01-analisi/LIMITI.md`, sezione 1.7: 6 regole a parole chiave per server,
10 espressioni regolari per regola, 260 caratteri l'una (sintassi Rust, senza «lookaround»), parole
fino a 60 caratteri, testo del blocco fino a 150 caratteri.
