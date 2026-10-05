# VOCI_OMESSE.md — Funzioni non AI trovate nelle fonti e assenti da ogni lista

Rileggendo le conversazioni originali per le funzioni AI
([`FUNZIONI_AI.md`](FUNZIONI_AI.md)) ho segnato anche ogni altra
funzione discussa. Qui ci sono solo quelle che **non stanno in nessuna
lista di oggi**. Regola seguita (D18): niente va perso; se una cosa non
si può fare così com'era, c'è la versione più vicina che funziona.

## In sintesi

- Funzioni non AI assenti da ogni lista: **65** (codici `OM-001`…`OM-065`).
- Chieste dall'owner con parole sue: **3**.
- Proposte da Gemini e approvate dall'owner in blocco: **15**.
- Solo proposte da un'altra AI, senza risposta dell'owner nelle fonti: **47**.
- In più, in fondo: i **dettagli** di voci già in lista che le fonti
  precisano, le **richieste dell'owner che oggi stanno solo nel
  catalogo**, e le **proposte tecniche** che non sono funzioni per
  l'utente.

| Area | Voci |
|---|---|
| Log | 7 |
| Moderazione e casi | 4 |
| Sicurezza | 6 |
| Ticket | 2 |
| Backup | 3 |
| Configurazione, primo avvio e strumenti dell'owner | 10 |
| Premium e modi di sostenere il server | 5 |
| Privacy | 2 |
| Clan | 2 |
| Economia e giochi | 6 |
| Community: ingresso, eventi, ricordi | 12 |
| Profilo e identità | 3 |
| App utente e Desktop | 2 |
| Voce e alert | 1 |
| **Totale** | **65** |

**Un punto da decidere.** `BACKLOG.md` dice che le voci respinte
"erano proposte di altre AI, non richieste dell'owner". Ma nella
conversazione con Gemini l'owner, davanti ai tre elenchi di idee,
risponde: «mi piacciono molto tutte le idee che hai tirato fuori»
(r.494). In quegli elenchi ci sono anche idee poi respinte: stanza in
affitto (OM-043), karaoke (OM-046), taglie (OM-044), tribunale dei pari (OM-011),
reputazione globale. Qui sono tutte elencate con la versione che
rispetta i vincoli. Serve che l'owner dica se quel "mi piacciono
tutte" valeva come richiesta.

## Come ho controllato

Fonti lette per intero: le stesse di `FUNZIONI_AI.md` (prima
conversazione con Grok, Gemini, ChatGPT, Grok finale, le due vecchie
SPEC, issue #50). "r." è il numero di riga del file citato.

Una funzione è "assente" se non la trovo in nessuno di questi:
`SPEC.md` (senza le note storiche), `02-piano/NUOVE_FUNZIONI.md`,
`02-piano/MODIFICHE_ESISTENTE.md`, `01-analisi/catalogo/*.md`,
`01-analisi/APP_UTENTE_E_DESKTOP.md`. Per ognuna ho cercato più parole,
in italiano e in inglese (per esempio: *asta, aste, auction, mercato*).
Se una lista ne contiene anche solo una versione vicina, la voce **non
è qui**: al massimo è nei "dettagli" in fondo.

`BACKLOG.md` è archivio e non conta come lista. Ne riporto il vecchio
verdetto.

Chi l'ha chiesta o proposta: come in `FUNZIONI_AI.md`. **Owner:
chiesta** = parole sue. **Owner: approvata in blocco** = proposta di
Gemini dentro gli elenchi approvati tutti insieme (Gemini r.494).
**Proposta** = un'altra AI, senza risposta dell'owner nelle fonti.

## 1. Log

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Vecchio verdetto | Come farla | Fase |
|---|---|---|---|---|---|---|
| OM-001 | Log su forum con un post per ogni membro e uno per ogni canale | Nel forum dei log dei membri ogni persona ha il suo post con tutta la sua storia. Nel forum dei canali ogni canale ha il suo post. Il post di un canale cancellato resta, segnato come archiviato. | **Owner: chiesta** (ChatGPT r.13: «dentro contiene i log di ogni singolo membro»). ChatGPT r.75–167, r.3770–3814; SPEC_v2 §8 | BACKLOG §3: ridimensionata (forum sì per canali e casi, no per membri e messaggi: troppi post durante un raid). Poi D3: un post per **tipo** di log | Versione più vicina che regge: post per canale e per caso di moderazione sempre; post del membro creato **quando serve** (primo caso, oppure bottone "Apri scheda" in `/log cerca`). Mappa post↔entità in tabella; etichette del forum per tipo di evento. Il limite di post attivi per server va verificato e scritto in `LIMITI.md` | F6 |
| OM-002 | Quanto contenuto mostrare nei log | Per ogni tipo di log l'admin sceglie: testo intero, visibile solo allo staff alto, oscurato, solo i dati senza il testo. | Proposta: ChatGPT r.4306–4329 | Nessun verdetto: non era stata valutata | Opzione in `/log canale`; vale per i messaggi cancellati e modificati (NF-02) | F6 |
| OM-003 | Ruoli di accesso ai log e registro di chi li consulta | Non tutto lo staff vede tutto: c'è chi legge, chi vede anche il testo dei messaggi, chi esporta. Ogni ricerca sui log di un utente resta scritta. | Proposta: ChatGPT r.4330–4371, r.6433–6442 | Nessun verdetto: non era stata valutata | Permessi su `/log cerca` ed `/log esporta` delegati dalle Integrazioni; tabella `log_access` (chi, quando, su chi); tetto alle esportazioni all'ora | F6 |
| OM-004 | Gravità di ogni evento | Ogni evento ha un livello (informazione, avviso, critico, sicurezza). Si può filtrare per livello. | Proposta: ChatGPT r.6767–6787 | Nessun verdetto: non era stata valutata | Colonna `gravita` nell'evento; filtro in `/log cerca`; colore dell'embed | F6 |
| OM-005 | Tre livelli di raccolta dei messaggi | Minimo: solo chi, dove, quando. Normale: anche il testo dei messaggi cancellati o modificati. Completo: copia intera, tenuta poco tempo. | Proposta: ChatGPT r.1400–1444, r.6739–6765 | Nessun verdetto: non era stata valutata | Impostazione per server in NF-02; il livello completo solo con conferma e scadenza breve (NF-04) | F6 |
| OM-006 | Eventi collegati tra loro | Da un caso di moderazione si arriva ai messaggi che l'hanno causato, e dal messaggio al caso. | Proposta: ChatGPT r.557–582, r.3714–3742 | Nessun verdetto: non era stata valutata | Colonna `evento_collegato` nello storico; link nel messaggio di log | F6 |
| OM-007 | Scheda per ogni incidente di sicurezza | Un raid o un attacco ha una sua scheda: primo e ultimo evento, utenti coinvolti, azioni fatte, come è finito. | Proposta: ChatGPT r.2249–2275 | Nessun verdetto: non era stata valutata | Tabella `security_incidents`; un post nel forum della sicurezza (router di NF-01) | F6 |

## 2. Moderazione e casi

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Vecchio verdetto | Come farla | Fase |
|---|---|---|---|---|---|---|
| OM-008 | Prova a vuoto di una regola | Una regola nuova può girare senza agire: il bot dice su quanti messaggi e utenti avrebbe agito. Poi l'admin la attiva. | Proposta: ChatGPT r.5292–5317 | Nessun verdetto: non era stata valutata | Opzione `prova: sì` sui filtri di `/security automod`; conteggi salvati per 7 giorni | F13 |
| OM-009 | Simulazione di un attacco | Lo staff prova raid, spam o ingressi a raffica con eventi finti: il bot dice cosa sarebbe scattato, senza toccare il server. | Proposta: ChatGPT r.5319–5355 | Nessun verdetto: non era stata valutata | `/security antiraid simula`: usa le stesse funzioni di decisione con dati finti | F13 |
| OM-010 | Avviso di possibile conflitto d'interesse | Se un moderatore gestisce un caso o un appello su una persona con cui ha avuto uno scontro da poco, il bot lo segnala. Non blocca. | Proposta: ChatGPT r.6330–6347 | Nessun verdetto: non era stata valutata | Controllo sullo storico dei casi tra le due persone; nota nel mod-log | F13 |
| OM-011 | Tribunale dei pari | Chi riceve una sanzione leggera chiede il giudizio di alcuni membri scelti a caso, che votano. | Proposta: Gemini r.460–464, r.862–869; SPEC_v2 §F3.3. **Owner: approvata in blocco** (Gemini r.494) | BACKLOG §12: respinta (membri a caso che ribaltano lo staff; rischio di voti organizzati). Grok r.35: solo premium e molto configurabile. ChatGPT r.6300–6328: la giuria dà un parere, decide lo staff, niente monete | Versione più vicina: nell'appello (NF-30) un secondo gruppo dà un **parere**. Il gruppo lo sceglie l'admin (staff non coinvolto, o membri fidati). Voto anonimo con bottoni. Decide sempre lo staff. Nessun premio | F14 |

## 3. Sicurezza

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Vecchio verdetto | Come farla | Fase |
|---|---|---|---|---|---|---|
| OM-012 | Livello di fiducia dei membri dentro il server | Ogni membro ha un livello (nuovo, verificato, attivo, affidabile…) che apre alcune funzioni: mandare link, creare thread, partecipare ai giveaway. | Proposta: ChatGPT r.5110–5137 | BACKLOG §9: respinta la reputazione **tra server** calcolata dalle sanzioni. Un livello solo locale, fatto di dati positivi, non era stato valutato | Regole scelte dall'admin (giorni nel server, verifica fatta, livello XP). Solo dentro il server. Mai deciso da un punteggio nascosto: l'utente vede cosa gli manca | F13 |
| OM-013 | Controllo dei webhook | Elenco dei webhook del server con chi li ha creati, quando sono stati usati, quali sono fermi o sospetti. Possibilità di rigenerarli. | Proposta: ChatGPT r.5583–5608 | Nessun verdetto: non era stata valutata | Comando dentro `/security` (per esempio `/security score webhook`); lettura con il permesso "Gestire webhook"; solo segnalazione | F13 |
| OM-014 | Regole di allarme sugli inviti | Un invito usato moltissime volte in pochi minuti, o creato da un account appena arrivato, fa scattare un avviso. | Proposta: ChatGPT r.5610–5644 | Nessun verdetto: non era stata valutata | Soglie in `/security antiraid`; dati da `core/invite_tracker.py` | F13 |
| OM-015 | Elenco degli altri bot e delle app del server | Per ogni bot: permessi, ruoli, chi l'ha aggiunto, quando. Avviso se un bot riceve "Amministratore" o se il suo ruolo sale sopra quello di iYokai. | Proposta: ChatGPT r.5646–5686 | Nessun verdetto: non era stata valutata | Completa il filtro "chi aggiunge bot" del catalogo (SIC-025) con un elenco consultabile | F13 |
| OM-016 | Simulatore dei permessi | "Questo utente può fare questa azione in questo canale?" Il bot risponde sì o no e spiega da dove viene il permesso o il blocco. | Proposta: ChatGPT r.5481–5525 | Nessun verdetto: non era stata valutata | Estende la diagnosi del catalogo (CFG-018) a un utente e un'azione qualsiasi | F9 |
| OM-017 | Verifica con conferma dell'email | Tra i modi di verifica: l'utente dimostra di avere un'email confermata su Discord. | Proposta: ChatGPT r.5139–5161 | Nessun verdetto: non era stata valutata | Solo con la verifica su web (NF-21): scope OAuth `email`, si legge soltanto "confermata sì o no" | F10 |

## 4. Ticket

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Vecchio verdetto | Come farla | Fase |
|---|---|---|---|---|---|---|
| OM-018 | Stati del ticket e tempi massimi di risposta | Un ticket è "in attesa dello staff", "in attesa dell'utente", "passato a un livello più alto", "risolto". Ogni priorità ha un tempo massimo di prima risposta; se scade il ticket sale di livello. | Proposta: ChatGPT r.2071–2109, r.6100–6122 | Nessun verdetto: non era stata valutata | Colonna `stato`; scadenze con lo scheduler; avviso al ruolo più alto. Il catalogo ha solo la categoria "in attesa dell'utente" (TKT-029) | F13 |
| OM-019 | Assegnazione del ticket secondo il carico | Il ticket va a chi dello staff ha meno ticket aperti e segue quella categoria. | Proposta: ChatGPT r.6123–6139 | Nessun verdetto: non era stata valutata | Conteggio dei ticket aperti per operatore (dati di SPEC 13.12); proposta con bottone "Prendi" | F13 |

## 5. Backup

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Vecchio verdetto | Come farla | Fase |
|---|---|---|---|---|---|---|
| OM-020 | Verifica di un backup | Un comando controlla che un backup sia leggibile e completo: ruoli, canali, riferimenti. | Proposta: ChatGPT r.5769–5796 | Nessun verdetto: non era stata valutata | Comando dentro `/admin backup`; rilegge lo snapshot e prova a ricostruirlo a vuoto | F3 |
| OM-021 | Anteprima del ripristino | Prima di ripristinare il bot mostra cosa creerà, cosa cambierà e dove c'è un conflitto. Poi chiede conferma. | Proposta: ChatGPT r.3205–3223 | Nessun verdetto: non era stata valutata | Confronto tra snapshot e stato attuale (lo stesso che serve al Creator per "tenere aggiornato", D8) | F3 |
| OM-022 | Piano di ripristino guidato | Dopo un disastro il bot guida passo per passo: permessi, backup valido, ruoli, canali, verifica finale, avviso allo staff. | Proposta: ChatGPT r.5797–5814 | Nessun verdetto: non era stata valutata | Sequenza di passi con bottoni dentro `/admin restore` | F3 |

## 6. Configurazione, primo avvio e strumenti dell'owner

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Vecchio verdetto | Come farla | Fase |
|---|---|---|---|---|---|---|
| OM-023 | Anteprima del setup | Prima di creare canali e ruoli il bot elenca cosa verrà creato e quali permessi gli mancano. | Proposta: ChatGPT r.3077–3101 | Nessun verdetto: non era stata valutata | Passo "anteprima" nel wizard (SPEC 22.16) | F9 |
| OM-024 | Controllo di coerenza del setup | Un comando confronta ciò che il bot crede di avere con ciò che c'è davvero: canale mancante, ruolo cancellato, permessi cambiati. Propone di ricreare. | Proposta: ChatGPT r.3103–3143 | Nessun verdetto: non era stata valutata | Comando dentro `/admin config`; elenco con stato per risorsa; nessuna ricreazione senza conferma | F9 |
| OM-025 | Configurazione ritrovata quando il bot viene reinvitato | Se il bot torna in un server da cui era uscito, propone di riprendere la configurazione di prima. | Proposta: ChatGPT r.6940–6952 | Nessun verdetto: non era stata valutata | Possibile solo entro i 90 giorni di D6; bottoni Sì / No nel messaggio di benvenuto | F5 |
| OM-026 | Manutenzione per singolo modulo e modalità "sola lettura" | L'owner mette in manutenzione un solo modulo. Se il database ha problemi, economia e clan passano in sola lettura: si guarda il saldo ma non si paga. | Proposta: ChatGPT r.3971–4014, r.7046–7059 | Nessun verdetto: non era stata valutata | Interruttore dentro `/owner system`; controllo comune in testa ai comandi che scrivono | F7 |
| OM-027 | Modalità debug per un server | L'owner accende per un server un registro più dettagliato (tempi dei comandi, eventi), senza dati sensibili. | Proposta: ChatGPT r.3698–3712 | Nessun verdetto: non era stata valutata | Dentro `/owner system`; si spegne da sola dopo un tempo | F7 |
| OM-028 | Rapporto di diagnosi per l'assistenza | L'admin genera un rapporto (versione, moduli attivi, permessi mancanti, errori recenti) da mandare al supporto. Nessun contenuto privato. | Proposta: ChatGPT r.7314–7348 | Nessun verdetto: non era stata valutata | Comando dentro `/admin config`; file sotto 10 MiB | F9 |
| OM-029 | Stato e attività del bot impostati dall'owner | L'owner sceglie cosa mostra il bot sotto il nome ("sta guardando…") e lo fa ruotare. | Proposta: Grok, primo schema (attachment-e9682b7c r.1193: «Shard / status management»; r.1486: «Status / Activity management»). Sparita dallo schema finale senza un motivo scritto | Nessun verdetto: non era stata valutata | Dentro `/owner system` (nessun figlio nuovo in `/owner`); cambio di presenza non più di una volta ogni pochi minuti | F7 |
| OM-030 | Comandi preferiti | Ogni utente salva i comandi che usa di più e li ritrova in un elenco. | Proposta: ChatGPT r.8004, r.8091; SPEC_v2 §B.4 («saved commands») | Nessun verdetto: non era stata valutata | Stella sul risultato di `/utility cerca-comando`; elenco personale | F8 |
| OM-031 | Notifiche raggruppate e scelte per tipo | Dieci avvisi di fila diventano uno solo ("hai raggiunto il livello 10"). Ogni utente sceglie quali tipi di avviso ricevere. | Proposta: ChatGPT r.3386–3436 | Nessun verdetto: non era stata valutata | Un punto solo per gli avvisi agli utenti, con attesa breve e raggruppamento; preferenze accanto agli "avvisi personali" (`APP_UTENTE_E_DESKTOP.md` E2) | F9 |
| OM-032 | Scoperta delle funzioni senza AI | Il bot suggerisce: "hai già usato benvenuto e livelli, potresti provare gli eventi". Avvisa quando il server accende una funzione nuova. | Proposta: ChatGPT r.8519–8545 | Nessun verdetto: non era stata valutata | Elenco fisso per modulo; un avviso per funzione nuova, mai ripetuto | F9 |

## 7. Premium e modi di sostenere il server

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Vecchio verdetto | Come farla | Fase |
|---|---|---|---|---|---|---|
| OM-033 | Periodo di prova dei moduli premium | Un server prova un modulo premium per alcuni giorni, una volta sola. | Proposta: ChatGPT r.7292–7300 | Nessun verdetto: non era stata valutata | Colonna `prova_fino_al` nei diritti (NF-22) | F10 |
| OM-034 | Giorni di tolleranza alla scadenza del premium | Se il pagamento salta, il premium non si spegne subito: 48 ore di tolleranza, poi sola lettura. Configurazioni e storico restano. | Proposta: ChatGPT r.7253–7271 | Nessun verdetto: non era stata valutata | Stato "in tolleranza" in `core/premium_entitlement_service.py` | F10 |
| OM-035 | Abbonamenti VIP del server con pagamento esterno | Il proprietario di un server collega Stripe o Ko-fi: chi paga il **server** riceve da solo ruolo VIP e canali riservati. | Proposta: Gemini r.384–386, r.637. **Owner: approvata in blocco** (Gemini r.494) | Grok r.36: «sì, ma solo dopo che il core è stabilissimo». BACKLOG non la cita | Webhook in ingresso con firma (lo stesso server di SPEC 10.8); ruolo con `check_role_assignable`; in alternativa gli abbonamenti al server di Discord, dove ci sono | F14 |
| OM-036 | Sponsor del mese | Il proprietario del server sceglie uno sponsor: una riga a piè di pagina negli embed automatici del bot. | Proposta: Gemini r.388. **Owner: approvata in blocco** (Gemini r.494) | Nessun verdetto: non era stata valutata | Testo fino a 100 caratteri nel piè dell'embed, passato dai filtri dei link | F14 |
| OM-037 | Badge "Powered by iYokai" | Un server che mostra il link del bot nel benvenuto o nelle regole riceve un piccolo vantaggio. | Proposta: Gemini r.350–352. **Owner: approvata in blocco** (Gemini r.494) | Nessun verdetto: non era stata valutata | Controllo del testo configurato nel benvenuto; premio solo estetico. Prima va controllato che le regole di Discord per gli sviluppatori lo permettano | F14 |

## 8. Privacy

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Vecchio verdetto | Come farla | Fase |
|---|---|---|---|---|---|---|
| OM-038 | Tempo di conservazione scelto dal server per tipo di dato | L'admin sceglie per quanto tenere log dei messaggi, casi, voce (per esempio 30, 365, 90 giorni), entro i massimi dell'owner. | Proposta: ChatGPT r.1503–1512, r.6390–6405 | Nessun verdetto: non era stata valutata | Impostazioni lette dal lavoro di pulizia di NF-04; D6 resta il massimo dopo l'uscita del bot | F5 |
| OM-039 | "Cosa conserva il bot" a comando | Un comando dice a ogni utente, in parole semplici, quali dati il bot tiene su di lui e per quanto. | Proposta: ChatGPT r.1491–1496, r.6427–6431 | Nessun verdetto: non era stata valutata | Voce in più di `/utility privacy`; testo generato dal registro dei dati (NF-04) | F5 |

## 9. Clan

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Vecchio verdetto | Come farla | Fase |
|---|---|---|---|---|---|---|
| OM-040 | Guerra tra clan per un territorio | Ogni settimana i clan puntano una parte della cassa per un canale speciale. Vince il clan più attivo: +20 % di XP e monete e un colore per 7 giorni. | Proposta: Gemini r.308–312, r.597–600, r.803–809; SPEC_v2 §15.16; Grok r.16. **Owner: approvata in blocco** (Gemini r.494) | BACKLOG §7: rimandata con tutto il gruppo "retention" | Comando dentro `/clan`; calcolo la domenica con lo scheduler; attività dai contatori dei clan; tetto alla puntata | F14 |
| OM-041 | Albero delle abilità del clan | La cassa del clan sblocca potenziamenti a livelli: più monete per i membri, più posti, audio migliore nei vocali del clan. | Proposta: Gemini r.314–322, r.602–606, r.811–821; SPEC_v2 §15.15; Grok r.16. **Owner: approvata in blocco** (Gemini r.494) | BACKLOG §7: rimandata | Comando dentro `/clan`; costi a livelli. La qualità audio oltre 96 kbps dipende dai boost del server (`LIM-28`) | F14 |

## 10. Economia e giochi

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Vecchio verdetto | Come farla | Fase |
|---|---|---|---|---|---|---|
| OM-042 | Pronostici con le monete su eventi del server | Lo staff apre un pronostico (chi vince il torneo). Gli utenti puntano monete. Una parte va alla cassa del server. | Proposta: Gemini r.371–375. **Owner: approvata in blocco** (Gemini r.494) | Grok r.168–170: tra le cose che «non metterei» (scommesse quasi d'azzardo). BACKLOG non la cita | Solo monete del server, mai comprate con soldi veri (regola di Discord); solo eventi aperti dallo staff; tetto alla puntata | F14 |
| OM-043 | Stanza in affitto con le monete | Un utente o un gruppo affitta un canale per 30 giorni e ne sceglie nome, argomento e chi può entrare. | Proposta: Gemini r.365–369. **Owner: approvata in blocco** (Gemini r.494) | BACKLOG §12: respinta («sforzo sproporzionato»). Grok r.37: da rimandare | Versione più vicina: riusa l'acquisto dei canali dei clan (SPEC §15) per una "stanza personale" a tempo; 50 canali per categoria, 500 per server | F14 |
| OM-044 | Taglie tra utenti | Un utente mette monete in palio per chi batte un amico in un gioco. | Proposta: Gemini r.466–468. **Owner: approvata in blocco** (Gemini r.494) | BACKLOG §12: respinta | Versione più vicina: la sfida con puntata che il catalogo ha già (ECO-109); nessun bersaglio che non ha accettato | F14 |
| OM-045 | Suoni in vocale pagati con le monete, con "scudo" | Far partire un suono costa monete. Chi non li vuole compra uno scudo. | Proposta: Gemini r.447–451. **Owner: approvata in blocco** (Gemini r.494) | Grok r.37: secondario. BACKLOG non la cita | Opzione prezzo su `/fun suono` (NF-35); lo scudo meglio gratuito, come impostazione personale | F13 |
| OM-046 | Karaoke | Il bot fa partire la base e alla fine dà un punteggio a chi ha cantato. | Proposta: Gemini r.453–455. **Owner: approvata in blocco** (Gemini r.494) | BACKLOG §12: respinta (analisi dell'audio) | Versione più vicina: base dal bot musicale, testo a schermo, voto dei presenti con i bottoni. Nessun ascolto né registrazione della voce | F14 |
| OM-047 | Controllo delle frodi con le monete | Il bot nota passaggi di monete avanti e indietro tra gli stessi account o guadagni fuori misura, e apre una segnalazione per lo staff. | Proposta: ChatGPT r.5838–5860 | Nessun verdetto: non era stata valutata | Controllo giornaliero sullo storico dei movimenti; solo segnalazione | F13 |

## 11. Community: ingresso, eventi, ricordi

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Vecchio verdetto | Come farla | Fase |
|---|---|---|---|---|---|---|
| OM-048 | Percorso di ingresso a tappe | Il nuovo membro vede una lista: leggi le regole, presentati, scegli i ruoli, visita un canale. Alla fine riceve una medaglia. | Proposta: ChatGPT r.5960–5978, r.8625–8651; SPEC_v2 §18.1.11 | BACKLOG §7: rimandata con il gruppo "retention" | Messaggio con bottoni per ogni tappa; stato per membro; va d'accordo con Verify e con i ruoli automatici (NF-07) | F13 |
| OM-049 | Benvenuto diverso secondo l'invito usato | Chi entra con l'invito del gruppo gaming riceve un benvenuto diverso da chi entra con quello generale. | Proposta: ChatGPT r.5980–5995 | Nessun verdetto: non era stata valutata | Testo di benvenuto per codice d'invito (dati di `core/invite_tracker.py`); tetto di varianti | F9 |
| OM-050 | Programma mentori | Un membro esperto si offre di seguire i nuovi. Riceve una medaglia e obiettivi di accoglienza. Solo per chi vuole. | Proposta: ChatGPT r.8599–8623; SPEC_v2 §18.1.10 | BACKLOG §7: rimandata | Ruolo "mentore" e abbinamento a richiesta; nessuna gerarchia obbligata | F14 |
| OM-051 | Ricordi del server | Una linea del tempo con i momenti importanti: fondazione, 1.000 membri, primo torneo. | Proposta: ChatGPT r.8653–8675; SPEC_v2 §18.1.12 | BACKLOG §7: rimandata | Voci scritte dallo staff più quelle automatiche (traguardi di membri); comando in `/utility` | F14 |
| OM-052 | Anniversari | Il bot ricorda l'anniversario di ingresso di un membro e quello di fondazione del server. | Proposta: ChatGPT r.8677–8695; SPEC_v2 §18.1.13 | BACKLOG §7: rimandata | Stesso lavoro giornaliero dei compleanni (NF-26); visibile nel profilo, senza ping | F13 |
| OM-053 | Eventi di stagione | Un calendario che torna ogni anno (primavera, estate, Notte degli Yokai a ottobre, inverno) con missioni e oggetti a tempo. | Proposta: ChatGPT r.8466–8486; SPEC_v2 §18.1.8 | BACKLOG §7: rimandata | Configurazione per periodo sopra missioni e collezioni (NF-41, NF-40) | F14 |
| OM-054 | Ruoli per anzianità più livello | Un ruolo dato a chi è nel server da un certo tempo e ha raggiunto un certo livello ("Veterano: 2 anni e livello 50"). | Proposta: Gemini r.394, r.634. **Owner: approvata in blocco** (Gemini r.494) | BACKLOG §7: rimandata | Condizione in più nei premi di livello (SPEC §15) o nei ruoli per attività (NF-25) | F13 |
| OM-055 | Calendario personale degli eventi | L'utente si segna gli eventi del server e riceve promemoria ("il boss è tra 40 minuti", "stai per perdere la serie"). | Proposta: Grok r.130–131 | Nessun verdetto: non era stata valutata | Bottone "Ricordamelo" sugli annunci di evento; usa i promemoria che ci sono già | F13 |
| OM-056 | Bacheca personale | Un elenco delle cose successe all'utente: medaglia sbloccata, missione finita, evento nuovo, funzione nuova. | Proposta: ChatGPT r.8697–8711; SPEC_v2 §18.1.14 | BACKLOG §7: rimandata | Comando personale; stessa fonte degli avvisi raggruppati | F14 |
| OM-057 | Sfide tra server | Tutti i server che usano iYokai lavorano a un obiettivo comune; il premio è estetico. | Proposta: ChatGPT r.8713–8735; Grok r.147–153; Gemini r.345–347 (alleanze tra server). **Owner: approvata in blocco** (Gemini r.494) | BACKLOG §12: respinte le alleanze tra server (manutenzione continua) | Versione più vicina: obiettivo pubblicato dall'owner; ogni server partecipa se l'admin vuole; tra server passano solo i totali, mai dati di utenti | F14 |
| OM-058 | Momenti di una diretta salvati con un comando | Durante una diretta di un membro, un comando salva il momento e lo pubblica nel canale dei momenti migliori. | Proposta: Gemini r.409–411. **Owner: approvata in blocco** (Gemini r.494) | Nessun verdetto: non era stata valutata | Twitch crea una clip solo a nome di un account Twitch collegato (permesso `clips:edit`): quello di chi usa il comando o dello streamer. Per YouTube non c'è un modo: si pubblica il link con il minuto | F14 |
| OM-059 | Classifica di chi porta contenuti e persone | Una classifica di chi condivide di più i contenuti del server. | Proposta: Gemini r.413. **Owner: approvata in blocco** (Gemini r.494) | Nessun verdetto: non era stata valutata | "Condividere" non si può misurare. Versione più vicina: classifica degli inviti (NF-27) più messaggi nei canali media (NF-25) | F13 |

## 12. Profilo e identità

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Vecchio verdetto | Come farla | Fase |
|---|---|---|---|---|---|---|
| OM-060 | Gradi dell'identità | Oltre al livello, un grado personale che sale nel tempo (da "Viandante" a "Mitico") e sblocca personalizzazioni. | Proposta: ChatGPT r.8400–8434; SPEC_v2 §18.1.6 e §B.2 | BACKLOG §7 e §9: rimandata (solo dati positivi) | Colonna nel profilo globale (SPEC B.6); nomi dei gradi presi dalla lore | F14 |
| OM-061 | Profili pronti da cambiare al volo | L'utente salva più versioni del suo profilo iYokai (di tutti i giorni, gaming, Halloween) e passa dall'una all'altra. | Proposta: ChatGPT r.8436–8464; SPEC_v2 §18.1.7 | BACKLOG §7: rimandata | Riguarda la scheda iYokai (sfondo, cornice, medaglie, titolo). Avatar e bio di Discord non si possono cambiare (SPEC D.12) | F14 |
| OM-062 | Identità del server nel profilo dei membri | Ogni server ha tema, stemma e banner. Nel profilo l'utente vede i suoi server con stemma, medaglie prese lì, tempo passato. | Proposta: ChatGPT r.8737–8766; SPEC_v2 §18.1.15 | BACKLOG §7: rimandata | Impostazioni estetiche del server; nel profilo globale solo i server che l'utente sceglie di mostrare | F14 |

## 13. App utente e Desktop

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Vecchio verdetto | Come farla | Fase |
|---|---|---|---|---|---|---|
| OM-063 | iYokai Desktop riservato a chi ha il premium | Il programma per PC si scarica e si usa solo con il boost del server del bot o con un pagamento mensile o annuale. | **Owner: chiesta** per il modulo selfbot (attachment-e9682b7c r.3902: «solo esclusivamente premium … dietro a discord boost … o dietro pagamento mensile/annuale»). Il selfbot è scartato; il Desktop lo sostituisce | Il selfbot è `[✗]` (SPEC D.0). La regola di accesso non è stata riportata sul Desktop | Diritto personale in NF-22, controllato all'accesso del Desktop | F13 |
| OM-064 | Desktop: programma chiuso, con licenza, anche su Linux | Eseguibile per Windows, usabile con Wine, codice non pubblico, licenza legata all'account. | **Owner: chiesta** per il modulo selfbot (attachment-e9682b7c r.2964: «criptato, cifrato … eseguibile .exe per Windows»; «selfhostare») | Come sopra. `APP_UTENTE_E_DESKTOP.md` dice solo "Windows prima, poi macOS e Linux" | Licenza = accesso con Discord più diritto premium. "Su un server proprio" non si può: lo stato personalizzato richiede il client Discord acceso sullo stesso PC. Le rotazioni e le notifiche girano sul servizio iYokai | F13 |

## 14. Voce e alert

| ID | Funzione | Cosa fa | Chi l'ha chiesta o proposta | Vecchio verdetto | Come farla | Fase |
|---|---|---|---|---|---|---|
| OM-065 | Attesa prima di cancellare un vocale temporaneo vuoto | Il canale vuoto resta qualche decina di secondi, così chi esce e rientra subito non lo perde. | Proposta: ChatGPT r.4230–4249 | Nessun verdetto: non era stata valutata | Scadenza `cancella_dopo` e un solo lavoro di pulizia (accanto a M 7.5) | F9 |

## 15. Aree controllate dove non manca niente, o quasi

In queste aree ho controllato le fonti voce per voce. **Non ho trovato
funzioni assenti dalle liste**, tranne le poche già contate nelle
tabelle sopra e richiamate qui. Non aggiungo righe per fare numero.

| Area | Cosa ho controllato | Esito |
|---|---|---|
| Musica | Albero dell'owner (§9), punti di ChatGPT sull'architettura (r.1088–1139) | Tutto in `SPEC.md` §9 o nel catalogo. Filtri, ruolo DJ e voto per saltare sono scelte dell'owner già scritte |
| AutoMod | Albero dell'owner (§6), ChatGPT r.2142–2174, r.4996–5040 | Tutto in §6 o nel catalogo. Resta solo la "prova a vuoto" (OM-008) |
| Verifica | Albero dell'owner (§4), ChatGPT r.3266–3287 | Tutto in §4, NF-18, NF-21 o nel catalogo. Resta solo la conferma dell'email (OM-017) |
| Benvenuto e ruoli | Albero dell'owner (§14), Gemini, ChatGPT | Tutto in lista, tranne il benvenuto per invito (OM-049) e i ruoli per anzianità (OM-054) |
| Livelli e classifiche | Richieste dell'owner (r.1686 della prima conversazione), Gemini | Tutto in §15, NF-12, NF-15 o nel catalogo |
| Alert social | Albero dell'owner (§10), ChatGPT r.3365–3384 | Tutto in §10, NF-32 o nel catalogo. I momenti di una diretta sono in OM-058 |
| Statistiche | Gemini r.327–335, ChatGPT r.5907–5958 | Le funzioni ci sono (NF-25, catalogo). Restano dei dettagli: vedi la tabella più sotto |
| Spam-trap | Richiesta lunga dell'owner (r.3946–3958 della prima conversazione) | Tutto in §7.3 |
| NSFW | Richiesta dell'owner (r.3119 della prima conversazione) | Tutto in §16.10 e NF-23 |
| Divertimento e immagini | Albero dell'owner (§16) | Tutto in §16 o nel catalogo |
| Pannello web | Albero dell'owner (C), ChatGPT r.3224–3246 | Tutto in §24, C e nel catalogo. Le pagine nuove legate all'AI sono in `FUNZIONI_AI.md` |

## 16. Dettagli di voci già in lista

La funzione c'è già in una lista. Le fonti però dicono qualcosa in più,
che la lista non riporta. Non sono voci nuove: sono da tenere presenti
quando si costruisce quella voce.

| Voce già in lista | Dettaglio trovato nelle fonti | Fonte |
|---|---|---|
| Moduli accesi per server (SPEC §1.1; catalogo CFG-008) | **Owner:** «funzionalità on off per ogni singola features». Un interruttore per ogni funzione dentro un modulo (XP dei messaggi, XP vocale, premi…), non solo per il modulo intero | Prima conversazione r.983; ChatGPT r.4608–4636 |
| Richieste di comandi all'owner (SPEC 14.8) | Terza risposta dello staff oltre ad approva e rifiuta: "chiedi modifiche" | Prima conversazione r.1543 |
| Serie di giorni (NF-41; catalogo ECO-025) | Protezione della serie comprabile con le monete; promemoria dopo 20 ore; azzeramento dopo 36 ore; premi solo estetici a 7, 14, 30, 60, 100 giorni | Gemini r.588–591, r.790–797; ChatGPT r.8231–8251 |
| Battle pass (NF-41; catalogo ECO-136) | Stagione di 90 giorni, 50 livelli; traccia gratuita e traccia "premium del server" sbloccata con il boost o con 500.000 monete | Gemini r.289–293, r.578–581, r.768–776 |
| Missioni (NF-41) | Tre tipi: del giorno, della settimana, di tutto il server (obiettivo comune, premio per tutti). Contano le attività di qualità, non la quantità | ChatGPT r.6019–6032, r.8253–8291 |
| Traguardi (NF-41; catalogo ECO-151) | Categorie; traguardi nascosti da scoprire | ChatGPT r.5997–6018, r.8293–8327 |
| Profilo (NF-40; catalogo LIV-089) | Cornici per l'avatar, titoli, effetti, temi; link social e scelte di privacy; negozio di sfondi e cornici | Gemini r.295–299, r.778–783; ChatGPT r.7911–7930, r.8329–8358 |
| Mercato tra giocatori (catalogo ECO-074) | Forma ad asta, con tassa del 5 % trattenuta dal bot. BACKLOG §7: servono un prezzo minimo e massimo, contro il passaggio di monete tra account collegati | Gemini r.301–303, r.784–788 |
| Ricette e oggetti (catalogo ECO-078) | Materiali diversi secondo il canale in cui si è attivi | Gemini r.377–381 |
| Eventi con iscrizioni (catalogo UTL-113) | Lista d'attesa, presenze, premi e medaglie per chi partecipa, numeri dopo l'evento; eventi nativi di Discord creati da soli per boss e serate | Gemini r.341–343; ChatGPT r.6034–6053, r.8488–8517 |
| Giveaway avanzati (NF-28) | Requisito "nessun caso di moderazione attivo"; estrazione con seme pubblico; verbale del vincitore | ChatGPT r.6055–6075 |
| Sondaggi (catalogo UTL-088 e vicine) | Quorum; risultati esportabili; "decisioni dello staff" con verbale | ChatGPT r.6076–6099 |
| Statistiche (NF-25; catalogo UTL-178, STA-024) | Quanti nuovi restano dopo 7, 30, 90 giorni, per mese di ingresso; confronto con il mese prima; pagina sul pannello | Gemini r.327–335, r.628–630; ChatGPT r.5907–5958; SPEC_v2 §C.6 |
| Carico dello staff (NF-41) | Tempo di risposta, ticket riaperti, sanzioni annullate in appello, soddisfazione; mai una classifica pubblica; proposta di turni | Gemini r.396–400, r.859–860; ChatGPT r.6273–6299; Grok r.109–112 |
| Appelli (NF-30) | Stati dell'appello, revisore assegnato, comando per vederne lo stato | ChatGPT r.3923–3946, r.6349–6367 |
| Casi di moderazione (SPEC §5; catalogo MOD-038) | Archivio delle prove con impronta dei file e scadenza; etichette, priorità e seconda revisione del caso | ChatGPT r.5163–5243 |
| Regole di AutoMod (catalogo AMD-075) | Regole scritte come "evento + condizioni + azioni" | ChatGPT r.5245–5291 |
| Blocco del server (NF-29) | Quattro livelli: leggero, medio, duro, ripristino | ChatGPT r.5718–5743 |
| Backup automatici (catalogo BKP-008) | Copie delle sole differenze; quante tenerne: 7 del giorno, 4 della settimana, 3 del mese | ChatGPT r.3179–3203 |
| Diagnosi (catalogo CFG-018) | Avviso se un intent è spento, con l'elenco delle funzioni che ne risentono | ChatGPT r.6578–6610 |
| Statistiche globali dell'owner (SPEC 17.8) | Stato di database, Lavalink, code e fornitori in un solo comando | ChatGPT r.2703–2728, r.4887–4930 |
| Log raggruppati (catalogo LOG-025; M 5.6) | Una riga sola per ogni permanenza in vocale: canale, entrata, uscita, durata | ChatGPT r.2455–2486, r.4184–4207 |
| Ricerca nei log (`/log cerca`) | Un messaggio fisso con i bottoni: cerca utente, canale, ID del messaggio, periodo, moderatore | ChatGPT r.281–318, r.5357–5391 |
| Molte lingue (catalogo CFG-028) | Ordine proposto: spagnolo, francese, tedesco, portoghese; poi giapponese e coreano | ChatGPT r.7743–7752 |
| Impostazioni personali (`APP_UTENTE_E_DESKTOP.md` C15) | Notifiche ridotte; server preferiti | ChatGPT r.8768–8781 |
| Punto reputazione dato dai membri (catalogo LIV-076) | Medaglie per chi aiuta ("utile", "mentore"), con limiti contro gli scambi di favori | ChatGPT r.8568–8598 |
| XP (SPEC §15) | Controlli in più contro l'abuso: età dell'account, messaggi tutti uguali, guadagno fuori misura | ChatGPT r.2064–2070, r.5886–5906 |

## 17. Richieste dell'owner che oggi stanno solo nel catalogo

Non sono "assenti": il catalogo le elenca. Ma sono segnate "nuova",
cioè senza una scheda e senza una fase. Sono richieste dell'owner:
vanno messe in piano.

| Richiesta | Parole dell'owner | Dov'è oggi | Proposta |
|---|---|---|---|
| Il bot prende da solo il nome e l'immagine del server, durante il setup | Prima conversazione r.1: «il server X avrà il bot che si chiamerà X con l'immagine di X» | Catalogo CFG-021 (nickname) e CFG-030 (avatar, banner e descrizione per server): entrambe "nuova". NF-38 copre solo il bot con token proprio | Un passo del wizard: "usa nome e icona di questo server". Fase F9. Il profilo del bot per server va provato con discord.py 2.7.1 |

## 18. Proposte tecniche (non sono funzioni per l'utente)

ChatGPT ha proposto molte regole di architettura. Non sono funzioni che
un utente vede, quindi non hanno un codice `OM`. Le elenco perché
niente vada perso, con il verdetto di `BACKLOG.md`.

| Proposta | Fonte | Verdetto di `BACKLOG.md` |
|---|---|---|
| Quattro livelli e bus di eventi interno; registro degli schemi degli eventi; codici di correlazione | ChatGPT r.755–924, r.4637–4795 | §2: respinti nella forma proposta (un solo processo usa già gli eventi di discord.py). Da rivedere se i bot diventano processi separati |
| Evento salvato una volta e letto da più indici; tabelle divise per mese | ChatGPT r.926–997, r.1520–1548 | §3: parte database fatta |
| "Outbox", operazioni ripetibili senza danni, coda dei lavori falliti con comandi per riprovarli | ChatGPT r.1203–1254, r.2545–2572, r.4796–4885 | §13: da decidere con dati veri di produzione |
| Gestore centrale dei limiti di Discord con priorità (prima sicurezza e moderazione, poi log e statistiche) | ChatGPT r.1140–1202, r.4968–4994 | Non valutata. Vicina a D15 (bot separato per log e moderazione) |
| Gestore dei lavori in background, spegnimento ordinato, blocchi distribuiti, scheduler che riparte dopo un riavvio | ChatGPT r.1577–1610, r.1710–1767, r.6979–7045 | Non valutata. Lo scheduler che riparte dopo un riavvio c'è già (`core/scheduler.py`) |
| Memory Guard a più soglie e cercatore di perdite di memoria | ChatGPT r.1612–1708 | §4: soglie fatte; cercatore rimandato |
| Redis per pause, blocchi e code | ChatGPT r.1550–1575 | Non valutata. Un servizio in più sulla stessa macchina |
| Diritti premium separati dai pagamenti; quattro stati di una funzione (acquistata, attiva, configurata, funzionante) | ChatGPT r.2574–2636, r.7227–7252 | Non valutata. In parte in NF-22 |
| Dipendenze tra moduli dichiarate; ciclo di vita e stato di salute di ogni modulo; controllo all'avvio | ChatGPT r.2638–2728, r.7077–7124 | Non valutata |
| Metriche, tracciamento degli errori, registro strutturato | ChatGPT r.2729–2803, r.7125–7169 | Registro strutturato fatto (SPEC 1.7); il resto non valutato |
| Schema e validazione di ogni impostazione; migrazioni con versione | ChatGPT r.2804–2889 | Fatte o in piano (`core/config_schema.py`, migrazioni versionate) |
| Registro dei comandi e instradamento unico di bottoni e moduli, con versione nel `custom_id` | ChatGPT r.2961–3037 | Non valutata. Il registro dei comandi serve anche all'AI: vedi `FUNZIONI_AI.md` AI-R-027 |
| Prove più ampie (contratto, concorrenza, guasti simulati), rilascio graduale, interruttori di funzione | ChatGPT r.3438–3598, r.6515–6557 | §13: da rivedere quando il rilascio sarà automatico |
| Cifratura dei dati sensibili, gestore dei segreti, rotazione dei token, firma dei webhook in ingresso | ChatGPT r.4016–4048, r.6444–6513 | In parte in SPEC 19.9 (SEC-16, `LIM-52`) |
| Mai fidarsi della cache: eventi "raw", lettura diretta di riserva, nomi e avatar salvati al momento dell'evento, segno per gli oggetti cancellati | ChatGPT r.2276–2299, r.4112–4183, r.6833–6921 | Non valutata. Regole di codice da tenere in `LIMITI.md` |
| Isolamento dei dati per server anche nel database | ChatGPT r.7196–7225 | Non valutata |
| Negozio di moduli e plugin di terzi | ChatGPT r.7350–7401 | §12: respinto (codice non fidato nello stesso processo) |

## Conteggio

65 righe `OM`. 27 dettagli di voci già in lista. 1 richiesta dell'owner ferma nel catalogo. 17 proposte tecniche. 11 aree controllate senza voci mancanti.
