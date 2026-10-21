# Elenco comandi — iYokai

Generato automaticamente da `scripts/generate_command_list.py` il 2026-10-21 00:52 UTC, interrogando l'albero comandi VERO del bot dopo aver caricato ogni cog — non un elenco scritto a mano. Da rigenerare dopo ogni commit che aggiunge, rimuove o rinomina un comando.

**Totale: 511 comandi in 23 categorie.**

## Admin

- **`/admin config canale-report`** — Imposta il canale delle segnalazioni.
- **`/admin config canale-suggerimenti`** — Imposta il canale dei suggerimenti.
- **`/admin config export`** — Esporta la configurazione di questo server in un file.
- **`/admin config history`** — Mostra le ultime modifiche alla configurazione.
- **`/admin config import`** — Importa una configurazione da un file esportato con /admin config export.
- **`/admin config nickname-bot`** — Cambia il nome del bot in questo server.
- **`/admin config pulizia`** — Toglie dalla configurazione canali e ruoli che non esistono più.
- **`/admin config reset`** — Azzera la configurazione di questo server.
- **`/admin config rollback`** — Ripristina il valore precedente di una modifica.
- **`/admin config sincronizza`** — Riscrive i permessi dei comandi di questo server.
- **`/admin lingua set`** — Imposta la lingua di questo server.
- **`/admin lingua show`** — Mostra la lingua impostata per questo server.
- **`/admin messaggi annulla`** — Annulla un messaggio programmato.
- **`/admin messaggi programma`** — Programma un messaggio.
- **`/admin messaggi programmati`** — Mostra i messaggi programmati di questo server.
- **`/admin messaggi sticky-set`** — Imposta lo sticky message di un canale.
- **`/admin messaggi sticky-togli`** — Rimuove lo sticky message di un canale.
- **`/admin musica canale-richieste`** — Canale dove si scrive un titolo per metterlo in coda, con il player.
- **`/admin musica impostazioni`** — Cambia le impostazioni musicali del server.
- **`/admin musica riepilogo`** — Mostra tutte le impostazioni musicali del server.
- **`/admin premium marchio`** — Usa un bot con il tuo nome e il tuo avatar (premium).
- **`/admin premium riscatta`** — Riscatta un codice premium per questo server.
- **`/admin premium stato`** — Mostra come è sbloccato il premium in questo server.
- **`/admin setup attiva`** — Attiva o disattiva i moduli del bot, per categoria.
- **`/admin setup wizard`** — Configura passo-passo i moduli principali del bot.
- **`/admin ticket chiudi-tutti`** — Chiudi i ticket aperti (fino a 25 alla volta).
- **`/admin ticket chiusura-auto`** — Chiudi i ticket fermi da N minuti (0 = spenta).
- **`/admin ticket dm`** — Accendi o spegni il ModMail (ticket in DM).
- **`/admin ticket dm-blocca`** — Blocca o sblocca un utente dal ModMail.
- **`/admin ticket modulo-aggiungi`** — Aggiungi una domanda al modulo (max 5).
- **`/admin ticket modulo-mostra`** — Mostra le domande del modulo di un pannello.
- **`/admin ticket modulo-rimuovi`** — Togli una domanda dal modulo.
- **`/admin ticket pannello-crea`** — Crea un pannello di ticket.
- **`/admin ticket pannello-lista`** — Elenca i pannelli di ticket del server.
- **`/admin ticket pannello-pubblica`** — Pubblica qui i bottoni di uno o più pannelli.
- **`/admin ticket pannello-rimuovi`** — Elimina un pannello e il suo modulo.
- **`/admin ticket risposta-elimina`** — Elimina una risposta standard.
- **`/admin ticket risposta-modifica`** — Correggi una risposta standard.
- **`/admin ticket risposte-lista`** — Elenca le risposte standard del server.
- **`/admin ticket sollecito`** — Sollecito dopo N minuti senza staff (0 = spento).
- **`/admin ticket standard`** — Risposte standard imparate dallo staff.
- **`/admin ticket voto`** — Voto a stelle in DM alla chiusura.

## Ai

- **`/ai attiva`** — Accende o spegne l'AI nel server (serve il consenso).
- **`/ai canale`** — Spegne o riaccende l'AI in un canale.
- **`/ai conoscenza aggiungi`** — Aggiunge una voce alla base di conoscenza.
- **`/ai conoscenza elenco`** — Le voci della base di conoscenza.
- **`/ai conoscenza togli`** — Toglie una voce dalla base di conoscenza.
- **`/ai costruisci`** — L'AI propone ruoli e canali da una descrizione; tu confermi.
- **`/ai funzioni`** — Accende le funzioni automatiche: risposta alla menzione, bandiere.
- **`/ai limiti`** — Tetto di spesa e quote: per utente, funzione, immagini.
- **`/ai lore`** — Tono e ambientazione del server per ogni testo dell'AI.
- **`/ai moderazione`** — L'AI segnala allo staff i messaggi sospetti di un canale.
- **`/ai personaggio`** — Installa, toglie o cancella un personaggio AI del server.
- **`/ai privacy`** — Messaggi degli utenti all'AI, memoria e lunghezza delle risposte.
- **`/ai stato`** — Stato dell'AI nel server: fornitori, scelte e uso del mese.
- **`/ai traduzione`** — Traduce da solo ogni messaggio di un canale in una lingua.
- **`/ai vietate`** — Parole o argomenti che l'AI deve rifiutare.

## Aiuto (primo livello)

- **`/-cerca-comando`** — Cerca un comando per descrizione.
- **`/-chiedi`** — Chiedi aiuto: ti mostro i comandi giusti.

## Antinuke

- **`/antinuke canale-allarmi`** — Sceglie dove arrivano gli allarmi dell'Anti-Nuke (canale o forum).
- **`/antinuke casi`** — Registro degli attacchi fermati: elenco o dettaglio di un caso.
- **`/antinuke enable`** — Attiva o disattiva l'Anti-Nuke.
- **`/antinuke guardie`** — Protezioni su azioni singole: permessi dei ruoli, ruoli ai membri, link, bot.
- **`/antinuke limits`** — Configura la soglia di rilevamento per una categoria.
- **`/antinuke punish-action`** — Cosa fare all'autore di un'azione distruttiva di massa.
- **`/antinuke recovery`** — Attiva/disattiva la ricreazione automatica di canali/ruoli cancellati durante un attacco.
- **`/antinuke rilascia`** — Toglie la quarantena all'autore di un caso e gli rimette i ruoli.
- **`/antinuke status`** — Mostra la configurazione attuale dell'Anti-Nuke.
- **`/antinuke trusted-add`** — Esenta un utente, un bot o un webhook dai controlli Anti-Nuke.
- **`/antinuke trusted-list`** — Elenca chi è esentato dai controlli Anti-Nuke e con quali limiti.
- **`/antinuke trusted-remove`** — Rimuove un utente, un bot o un webhook dalla lista fidati Anti-Nuke.

## Antiraid

- **`/antiraid account-age`** — Età minima dell'account per non essere considerato sospetto.
- **`/antiraid alert-channel`** — Canale dove ricevere gli alert di sicurezza (Anti-Raid + Anti-Nuke).
- **`/antiraid avatar-check`** — Attiva/disattiva il rilevamento avatar assente.
- **`/antiraid elenco`** — File con tutti gli account dei raid nelle ultime ore.
- **`/antiraid enable`** — Attiva o disattiva l'Anti-Raid.
- **`/antiraid filtro-ingresso`** — Azione per un filtro all'ingresso (vale anche fuori da un raid).
- **`/antiraid join-rate`** — Configura il limite di join in un intervallo di tempo.
- **`/antiraid lockdown-action`** — Cosa fare quando un raid viene rilevato.
- **`/antiraid nomi-vietati`** — Lista di parole o schemi (con *) vietati nei nomi di chi entra.
- **`/antiraid ping-ruoli`** — Ruoli dello staff pingati al primo allarme di un raid (vuoto: nessuno).
- **`/antiraid quarantine-hold`** — Impedisce a chi non è fidato di togliere la quarantena a mano.
- **`/antiraid rilascia`** — Toglie la quarantena a un membro (il modo giusto, col blocco attivo).
- **`/antiraid segnala`** — Segnala a chi gestisce il bot un raid che non è stato riconosciuto.
- **`/antiraid segnali`** — Segnali di raid sugli ultimi ingressi e azione su chi è entrato prima.
- **`/antiraid status`** — Mostra la configurazione attuale dell'Anti-Raid.
- **`/antiraid username-check`** — Attiva/disattiva il rilevamento pattern username sospetti.

## AutoMod

- **`/automod esenzioni channel-add`** — Esenta un canale da tutti i filtri AutoMod avanzati.
- **`/automod esenzioni channel-remove`** — Rimuove l'esenzione di un canale.
- **`/automod esenzioni role-add`** — Esenta un ruolo da tutti i filtri AutoMod avanzati.
- **`/automod esenzioni role-remove`** — Rimuove l'esenzione di un ruolo.
- **`/automod filtri actions-set`** — Configura quali azioni eseguire quando un filtro avanzato scatta.
- **`/automod filtri anti-attachment`** — Configura l'anti-attachment-spam (troppi allegati in poco tempo).
- **`/automod filtri anti-caps`** — Configura l'anti-caps (troppo maiuscolo).
- **`/automod filtri anti-link-domain`** — Aggiunge o rimuove un dominio dalla whitelist/blacklist link.
- **`/automod filtri anti-link-mode`** — Imposta la modalità del filtro link.
- **`/automod filtri anti-mention`** — Configura l'anti-mass-mention (troppi utenti taggati in un messaggio).
- **`/automod filtri anti-spam-emoji`** — Configura l'anti-spam emoji (troppe emoji in un messaggio).
- **`/automod filtri anti-spam-messages`** — Configura l'anti-spam messaggi (troppi messaggi in poco tempo).
- **`/automod filtri anti-spam-sticker`** — Configura l'anti-spam sticker (troppi sticker in poco tempo).
- **`/automod filtri anti-zalgo`** — Attiva o disattiva l'anti-zalgo (testo con segni diacritici anomali).
- **`/automod filtri canale-media`** — Canale solo media, senza allegati o normale.
- **`/automod filtri contenuto`** — Embed e inoltri controllati dai filtri; tipi di file vietati.
- **`/automod filtri forma-testo`** — Limiti sulla forma del messaggio: a-capo, lunghezza, spoiler (0 = spento).
- **`/automod filtri invites`** — Attiva o disattiva il blocco automatico degli inviti Discord.
- **`/automod filtri messaggi`** — Ripetuti, troppo corti, link e menzioni contati nel tempo (0 = spento).
- **`/automod filtri phishing`** — Attiva o disattiva il blocco dei link di phishing (finti regali, finti login).
- **`/automod log-channel`** — Imposta il canale dove pubblicare il log delle azioni AutoMod avanzate.
- **`/automod mute-duration`** — Imposta la durata del timeout usato dall'azione 'mute' dell'AutoMod.
- **`/automod parole add`** — Aggiunge una parola vietata.
- **`/automod parole list`** — Mostra le parole vietate configurate.
- **`/automod parole remove`** — Rimuove una parola vietata.
- **`/automod status`** — Mostra la configurazione attuale dei filtri AutoMod avanzati.
- **`/automod sync`** — Forza una sincronizzazione manuale delle regole AutoMod.

## Backup

- **`/backup annulla`** — Ferma il caricamento in corso (ciò che è già fatto resta).
- **`/backup carica`** — Ricarica in questo server una copia salvata, scegliendo le parti.
- **`/backup chat-carica`** — Ricarica una chat salvata in un canale, anche diverso.
- **`/backup chat-salva`** — Salva gli ultimi messaggi di un canale (fino a 1000) per ricaricarli dopo.
- **`/backup collega`** — Collega QUESTO server come backup, con il codice ricevuto dal server principale.
- **`/backup copia-canale`** — Copia un canale con i permessi; una categoria con i suoi canali.
- **`/backup copia-ruolo`** — Copia un ruolo con i permessi e, a scelta, i permessi nei canali.
- **`/backup crea`** — Prepara il backup: codice di collegamento e link per il nuovo server.
- **`/backup elimina`** — Elimina una copia salvata.
- **`/backup esporta`** — Esporta struttura, canali, ruoli, ban o reazioni in un file.
- **`/backup importa`** — Importa la struttura da un file JSON, scegliendo cosa applicare.
- **`/backup lista`** — Le copie salvate di questo server, con la data.
- **`/backup main`** — Registra questo server come 'main' per il Backup System.
- **`/backup modello`** — Modelli: condividi una copia con un codice o carica quella di un altro server.
- **`/backup permessi`** — Chi può creare e chi può caricare i backup (solo l'owner).
- **`/backup promuovi`** — Promuove QUESTO server (finora backup) a nuovo main, se il main originale è perso.
- **`/backup registro`** — Chi ha usato backup, modelli e sincronie (ultimi 20, 365 giorni).
- **`/backup restore-modo`** — Scegli come questo server gestisce il restore utenti via OAuth2.
- **`/backup restore-utenti`** — Ripristina in QUESTO server gli utenti dell'ultimo snapshot di un altro server.
- **`/backup salva`** — Salva una copia datata della struttura di questo server.
- **`/backup sincronia`** — Tieni uguali ban e ruoli con un altro tuo server.
- **`/backup stato`** — Avanzamento dell'ultimo caricamento in questo server.

## Clan

- **`/clan bacheca disable`** — Disattiva l'annuncio automatico della top 3 gilde.
- **`/clan bacheca set`** — Imposta il canale dove annunciare la top 3 gilde del mese.
- **`/clan boost gilda`** — Acquista un boost ×2 per 24h per TUTTI i membri, dalla tesoreria.
- **`/clan boost individuale`** — Acquista un boost personale ×2 per 24h sul tuo tick vocale di gilda.
- **`/clan classifica`** — Classifica delle gilde per XP (mensile o totale).
- **`/clan compra-canale`** — Sblocca un nuovo canale extra per la tua gilda.
- **`/clan crea`** — Crea una nuova gilda/clan.
- **`/clan espelli`** — Espelli un membro dalla tua gilda.
- **`/clan info`** — Mostra le informazioni di una gilda.
- **`/clan invita`** — Invita un membro nella tua gilda.
- **`/clan lascia`** — Lascia la gilda di cui fai parte.
- **`/clan membri`** — Mostra i membri di una gilda.
- **`/clan promuovi`** — Cambia il ruolo di un membro della tua gilda.
- **`/clan sciogli`** — Sciogli la tua gilda.
- **`/clan tesoreria dona`** — Dona coin personali alla tesoreria della tua gilda.
- **`/clan tesoreria trasferisci`** — Trasferisci coin dalla tesoreria a un'altra TUA gilda (anche su un altro server).

## Economia

- **`/economia assegna-lobby`** — Premio partecipazione: assegna coin a chi è in vocale ORA, dalla cassa del server.
- **`/economia assegna-winner`** — Premio vincitore: assegna coin a un membro, dalla cassa del server.
- **`/economia cassa-premium`** — Sblocca un mese di bot premium spendendo dalla cassa.
- **`/economia giveaway`** — Avvia un giveaway.
- **`/economia giveaway-modello`** — Modelli di giveaway: salva, elenca, elimina, avvia.
- **`/economia giveaway-programmati`** — Giveaway programmati: elenca (anche quelli in errore) o annulla.
- **`/economia monete`** — Modifica il saldo di un membro.
- **`/economia shop-add`** — Aggiunge un oggetto allo shop.
- **`/economia shop-edit`** — Cambia un oggetto dello shop (prezzo, scorte, ruolo richiesto...).
- **`/economia shop-remove`** — Rimuove un oggetto dallo shop.
- **`/economia vincitori-off`** — Disattiva l'annuncio dei vincitori del mese.
- **`/economia vincitori-set`** — Imposta il canale dove annunciare i vincitori del mese.
- **`/economia xp`** — Modifica XP e livello di un membro.

## Divertimento

- **`/fun 8ball`** — Fai una domanda alla palla magica 8.
- **`/fun animal`** — Mostra un'immagine casuale di un animale.
- **`/fun blur`** — Applica una sfocatura a un'immagine.
- **`/fun casuale`** — Preferiresti, argomento, consiglio, oggetto magico.
- **`/fun coinflip`** — Lancia una moneta: testa o croce.
- **`/fun conteggio`** — Gioco del conteggio: scegli il canale dove contare a turno 1, 2, 3...
- **`/fun dice`** — Tira un dado.
- **`/fun effetto`** — Effetto sull'avatar: arcobaleno, R.I.P., ricercato, triggered.
- **`/fun fact`** — Mostra una curiosità a caso.
- **`/fun gioca`** — Gioca le tue coin: monetina, dadi o slot.
- **`/fun grayscale`** — Trasforma un'immagine in scala di grigi.
- **`/fun invert`** — Inverte i colori di un'immagine.
- **`/fun joke`** — Racconta una barzelletta a caso.
- **`/fun meme`** — Genera un meme con testo sopra/sotto.
- **`/fun misura`** — Misura da 0 a 100% quanto c'è di una cosa a tua scelta.
- **`/fun numero`** — Un numero a caso in un intervallo.
- **`/fun pixelate`** — Pixela un'immagine.
- **`/fun quote`** — Mostra una citazione a caso.
- **`/fun rate`** — Valuta qualcosa da 0 a 10.
- **`/fun rps`** — Carta, forbici, sasso contro il bot.
- **`/fun scegli`** — Scelgo a caso tra le opzioni che scrivi.
- **`/fun scherzo`** — Uno scherzo innocuo verso un utente.
- **`/fun search-image`** — Cerca un'immagine SFW su Pixabay.
- **`/fun ship`** — Calcola la compatibilità tra due utenti.
- **`/fun testo`** — Scrivi un testo in uno stile speciale.

## Gestione

- **`/gestione benvenuto addio`** — Configura il messaggio di addio.
- **`/gestione benvenuto anteprima`** — Mostra un'anteprima di come apparirebbe un messaggio.
- **`/gestione benvenuto benvenuto`** — Configura il messaggio di benvenuto.
- **`/gestione benvenuto boost`** — Configura il messaggio di boost.
- **`/gestione benvenuto immagine`** — Aggiungi al benvenuto un'immagine con avatar, nome e numero del membro.
- **`/gestione ruoli auto-aggiungi`** — Aggiungi un ruolo dato in automatico a chi entra.
- **`/gestione ruoli auto-elenco`** — Mostra i ruoli automatici del server.
- **`/gestione ruoli auto-ricorda`** — Ridai i ruoli a chi esce e rientra entro un certo tempo.
- **`/gestione ruoli auto-rimuovi`** — Togli un ruolo dato in automatico a chi entra.
- **`/gestione ruoli auto-sincronizza`** — Dai i ruoli automatici anche ai membri già nel server.
- **`/gestione ruoli livello-add`** — Assegna un ruolo a chi raggiunge un livello.
- **`/gestione ruoli livello-list`** — Mostra i ruoli-premio configurati su questo server.
- **`/gestione ruoli livello-remove`** — Rimuove un ruolo-premio configurato.
- **`/gestione ruoli menu-accesso`** — Limita un menu a certi ruoli o escludine altri.
- **`/gestione ruoli menu-aggiungi`** — Aggiungi un'opzione a un role menu.
- **`/gestione ruoli menu-crea`** — Crea un nuovo role menu.
- **`/gestione ruoli menu-elenco`** — Mostra i menu di ruoli del server, con gli ID.
- **`/gestione ruoli menu-elimina`** — Elimina un role menu.
- **`/gestione ruoli menu-modifica`** — Cambia titolo, descrizione o comportamento di un menu già pubblicato.
- **`/gestione ruoli menu-togli`** — Rimuovi un'opzione da un role menu.
- **`/gestione ticket categoria-add`** — Aggiungi (o aggiorna) una categoria di ticket.
- **`/gestione ticket categoria-list`** — Elenca le categorie di ticket configurate.
- **`/gestione ticket categoria-remove`** — Rimuovi una categoria di ticket.
- **`/gestione ticket limite`** — Quanti ticket aperti alla volta può avere ogni utente (predefinito 1).
- **`/gestione ticket panel`** — Pubblica il pannello per l'apertura dei ticket in questo canale.
- **`/gestione ticket ruolo-add`** — Aggiungi un ruolo di supporto.
- **`/gestione ticket ruolo-list`** — Elenca i ruoli di supporto configurati.
- **`/gestione ticket ruolo-remove`** — Rimuovi un ruolo di supporto.
- **`/gestione ticket setup`** — Configura la categoria (e opzionalmente il ruolo di supporto) per i ticket.
- **`/gestione ticket stats`** — Statistiche del sistema di ticket.
- **`/gestione voice cap`** — Imposta il numero massimo di vocali temporanei per categoria.
- **`/gestione voice opzioni`** — Nome dei nuovi canali, canali che nascono bloccati, canale di registro.
- **`/gestione voice panel`** — Pubblica il pannello per la creazione manuale di un vocale.
- **`/gestione voice piattaforme`** — Configura i ruoli informativi PC/Console/Mobile per i vocali temporanei.
- **`/gestione voice setup`** — Configura il canale generatore e la categoria dei vocali temporanei.

## Livelli

- **`/level attese`** — Quando potrai di nuovo usare daily e work.
- **`/level balance`** — Mostra i tuoi coin.
- **`/level calcola`** — Quanti messaggi o minuti in vocale mancano per arrivare a un livello.
- **`/level cassa`** — Mostra il saldo della cassa del server.
- **`/level collezione compra`** — Compra un badge o uno sfondo con le tue coin.
- **`/level collezione equipaggia`** — Metti un badge o uno sfondo sul tuo profilo (senza oggetto lo togli).
- **`/level collezione negozio`** — Mostra badge e sfondi in vendita e quelli che hai.
- **`/level compleanno imposta`** — Registra il tuo compleanno (solo giorno e mese).
- **`/level compleanno mostra`** — Mostra il compleanno che hai registrato.
- **`/level compleanno rimuovi`** — Cancella il tuo compleanno.
- **`/level daily`** — Riscuoti la ricompensa giornaliera.
- **`/level impostazioni annuncio`** — Dove e quando annunciare i level-up.
- **`/level impostazioni card`** — Mostra o nascondi in questo server gli sfondi con immagine di card e profili.
- **`/level impostazioni escludi`** — Un canale, una categoria o un ruolo non dà XP (rifallo per toglierlo).
- **`/level impostazioni moltiplicatore`** — XP moltiplicati in un canale o per un ruolo (fattore 1 = toglie la regola).
- **`/level impostazioni mostra`** — Mostra le impostazioni dei livelli di questo server.
- **`/level impostazioni negozio`** — Chiedi conferma prima di ogni acquisto nel negozio (si può spegnere).
- **`/level impostazioni premi`** — Ruoli-premio: tienili tutti o tieni solo quello più alto.
- **`/level impostazioni xp`** — Quanti XP e coin si guadagnano, e come si sommano i moltiplicatori.
- **`/level inviti classifica`** — I 10 membri che hanno invitato più persone.
- **`/level inviti utente`** — Quante persone ha invitato un membro.
- **`/level leaderboard`** — Mostra la classifica del server.
- **`/level livelli-recenti`** — Gli ultimi 25 level-up del server.
- **`/level pay`** — Trasferisci coin a un altro utente.
- **`/level premi`** — Mostra i ruoli-premio dei livelli e i moltiplicatori di XP attivi.
- **`/level profilo`** — Mostra il profilo di un membro; con «presentazione» cambi il tuo.
- **`/level rank`** — Mostra la rank card: livello, XP, posizione e coin.
- **`/level shop buy`** — Acquista un oggetto dello shop.
- **`/level shop list`** — Mostra gli oggetti disponibili nello shop.
- **`/level work`** — Lavora per guadagnare qualche coin.

## Log

- **`/log archivio-canale`** — Scarica in un file gli ultimi messaggi di un canale, anche quelli appena cancellati.
- **`/log canale`** — Imposta il canale (o il forum) dei log del server.
- **`/log cerca canale`** — Mostra lo storico eventi di un canale.
- **`/log cerca utente`** — Mostra lo storico eventi di un utente.
- **`/log crea-canali`** — Crea una categoria privata con un canale per ogni tipo di log.
- **`/log crea-forum`** — Crea un forum privato per i log: un post per ogni tipo.
- **`/log esporta`** — Esporta lo storico eventi completo del server come file JSON.
- **`/log eventi`** — Accendi o spegni ogni singolo evento dei log.
- **`/log ignora`** — Cosa il log dei messaggi non registra (canali, utenti, ruoli, testi).
- **`/log stato`** — Mostra dove vanno i log del server.

## Moderazione

- **`/mod avvisi azzera`** — Toglie tutti i warn attivi di un membro (serve «Gestire il server»).
- **`/mod avvisi classifica`** — I membri con più warn attivi.
- **`/mod avvisi togli`** — Toglie un singolo warn (per numero di caso).
- **`/mod blocco attiva`** — Blocca tutti i canali, gli inviti e gli ingressi del server.
- **`/mod blocco togli`** — Riapre il server com'era prima del blocco.
- **`/mod caso classifica-staff`** — Classifica dei moderatori per numero di azioni, o casi di uno solo.
- **`/mod caso elimina`** — Elimina un caso (serve «Gestire il server»).
- **`/mod caso motivo`** — Cambia il motivo di un caso già registrato.
- **`/mod caso storico`** — Mostra lo storico casi di un membro.
- **`/mod caso vedi`** — Mostra i dettagli di un singolo caso.
- **`/mod clear`** — Cancella un numero di messaggi, con filtri opzionali.
- **`/mod lock`** — Blocca la possibilità di scrivere in un canale.
- **`/mod massa timeout`** — Mette in timeout più membri insieme (max 28 giorni).
- **`/mod massa warn`** — Assegna un warn a più membri insieme.
- **`/mod mute`** — Silenzia un membro con un ruolo dedicato (alternativa al timeout).
- **`/mod nota aggiungi`** — Aggiunge una nota su un utente.
- **`/mod nota elenca`** — Elenca le note su un utente.
- **`/mod nota modifica`** — Cambia il testo di una nota.
- **`/mod nota rimuovi`** — Toglie una nota (il numero è nell'elenco delle note).
- **`/mod nota svuota`** — Cancella tutte le note di un membro (serve «Gestire il server»).
- **`/mod slowmode`** — Imposta lo slowmode su un canale.
- **`/mod timeout`** — Mette in timeout un membro (max 28 giorni).
- **`/mod unlock`** — Sblocca la possibilità di scrivere in un canale.
- **`/mod unmute`** — Rimuove il ruolo mute da un membro.
- **`/mod untimeout`** — Rimuove il timeout da un membro.
- **`/mod warn`** — Assegna un warn a un membro.

## Ban (modban)

- **`/modban appelli canale`** — Sceglie il canale staff per gli appelli (vuoto per spegnerli).
- **`/modban appelli elenco`** — Mostra gli ultimi appelli del server.
- **`/modban ban`** — Banna permanentemente un membro.
- **`/modban kick`** — Espelle un membro dal server.
- **`/modban massa ban`** — Banna più utenti insieme, anche fuori dal server (ID o menzioni).
- **`/modban massa kick`** — Espelle più membri insieme (ID o menzioni).
- **`/modban massa unban`** — Toglie il ban a più utenti insieme (ID).
- **`/modban softban`** — Banna e sbanna subito un membro, per cancellarne i messaggi recenti.
- **`/modban tempban`** — Banna un membro per una durata definita.
- **`/modban unban`** — Rimuove il ban da un utente.

## Moduli

- **`/moduli alert elenco`** — Elenca gli avvisi del server.
- **`/moduli alert feed`** — Segui un feed RSS/Atom.
- **`/moduli alert guida-social`** — Avvisi per TikTok, Instagram e X.
- **`/moduli alert kick`** — Avvisa quando un canale Kick va in diretta.
- **`/moduli alert opzioni`** — Opzioni di un avviso: ruolo, fine diretta, bottone.
- **`/moduli alert rimuovi`** — Rimuove un avviso o un webhook.
- **`/moduli alert ruolo-live`** — Ruolo dato a chi è in diretta.
- **`/moduli alert twitch`** — Avvisa quando uno streamer Twitch va live.
- **`/moduli alert webhook`** — Crea un webhook per pubblicare da servizi esterni.
- **`/moduli alert youtube-live`** — Avvisa quando un canale YouTube va live.
- **`/moduli candidature crea`** — Crea un modulo o una candidatura.
- **`/moduli candidature elenco`** — I moduli di questo server.
- **`/moduli candidature elimina`** — Elimina un modulo e le sue risposte.
- **`/moduli comandi crea`** — Crea un comando personalizzato.
- **`/moduli comandi elenco`** — Mostra i comandi personalizzati del server.
- **`/moduli comandi elimina`** — Elimina un comando personalizzato.
- **`/moduli comandi modifica`** — Cambia un comando personalizzato.
- **`/moduli comandi prefisso`** — Scegli il prefisso per usare i comandi scrivendo nel canale.
- **`/moduli comandi risposta-crea`** — Crea una risposta automatica.
- **`/moduli comandi risposta-elimina`** — Elimina una risposta automatica.
- **`/moduli comandi risposte`** — Mostra le risposte automatiche del server.
- **`/moduli compleanni canale`** — Scegli il canale degli auguri (vuoto per spegnerli).
- **`/moduli compleanni ruolo`** — Un ruolo per 24 ore a chi compie gli anni (vuoto per toglierlo).
- **`/moduli contatori crea`** — Crea un canale che mostra un numero.
- **`/moduli contatori elenco`** — Mostra i contatori del server.
- **`/moduli contatori elimina`** — Smetti di aggiornare un contatore (il canale resta).
- **`/moduli embed crea`** — Crea un embed e guarda l'anteprima.
- **`/moduli embed elenco`** — Mostra gli embed salvati.
- **`/moduli embed elimina`** — Elimina un embed salvato (il messaggio pubblicato resta).
- **`/moduli embed modifica`** — Cambia un embed salvato (e il messaggio già pubblicato).
- **`/moduli embed pubblica`** — Manda un embed salvato in un canale.
- **`/moduli starboard disattiva`** — Spegni la bacheca.
- **`/moduli starboard imposta`** — Scegli il canale della bacheca e la soglia di stelle.
- **`/moduli starboard soglia`** — Cambia quante stelle servono per finire in bacheca.
- **`/moduli statistiche diagnosi`** — Perché le statistiche non si contano?
- **`/moduli statistiche elenco`** — Mostra regole ed esclusioni delle statistiche.
- **`/moduli statistiche impostazioni`** — Escludi canali o ruoli dalle statistiche.
- **`/moduli statistiche ruolo-aggiungi`** — Dai un ruolo a chi è attivo e toglilo a chi smette.
- **`/moduli statistiche ruolo-elimina`** — Elimina una regola dei ruoli per attività.

## Musica

- **`/music clear-queue`** — Svuota la coda, senza toccare la traccia in riproduzione.
- **`/music disconnect`** — Disconnette il music bot dal canale vocale.
- **`/music history`** — Mostra gli ultimi brani già suonati.
- **`/music join`** — Fa entrare il music bot nel tuo canale, senza suonare.
- **`/music loop queue`** — Attiva/disattiva la ripetizione dell'intera coda.
- **`/music loop track`** — Attiva/disattiva la ripetizione della traccia corrente.
- **`/music nonstop off`** — Disattiva il loop continuo.
- **`/music nonstop on`** — Attiva il loop continuo sulla coda attuale.
- **`/music nowplaying`** — Mostra la traccia in riproduzione con una barra di avanzamento.
- **`/music pause`** — Mette in pausa la riproduzione.
- **`/music play`** — Riproduce una canzone o playlist.
- **`/music playlist carica`** — Mette in coda una tua playlist salvata.
- **`/music playlist elenco`** — Le tue playlist salvate.
- **`/music playlist elimina`** — Cancella una tua playlist salvata.
- **`/music playlist esporta`** — Scarica una tua playlist come file.
- **`/music playlist importa`** — Salva una playlist da un file esportato.
- **`/music playlist salva`** — Salva la coda del tuo canale come playlist.
- **`/music previous`** — Torna al brano precedente.
- **`/music queue`** — Mostra la coda di riproduzione.
- **`/music resume`** — Riprende la riproduzione in pausa.
- **`/music shuffle`** — Mescola l'ordine delle tracce in coda.
- **`/music skip`** — Salta la traccia in riproduzione.
- **`/music skipto`** — Salta direttamente al brano numero N della coda.
- **`/music stop`** — Ferma la riproduzione e svuota la coda.
- **`/music suono`** — Fa partire un effetto sonoro nel tuo canale vocale.
- **`/music volume down`** — Diminuisce il volume.
- **`/music volume set`** — Imposta il volume a un valore specifico (0-200).
- **`/music volume up`** — Aumenta il volume.

## Owner

- **`/owner blacklist server-add`** — Blocca globalmente un server (il bot ne uscirà se già presente).
- **`/owner blacklist server-list`** — Mostra i server bloccati globalmente.
- **`/owner blacklist server-remove`** — Rimuove un server dalla blacklist globale.
- **`/owner blacklist utente-add`** — Blocca globalmente un utente dall'uso del bot.
- **`/owner blacklist utente-list`** — Mostra gli utenti bloccati globalmente.
- **`/owner blacklist utente-remove`** — Rimuove un utente dalla blacklist globale.
- **`/owner cog load`** — Carica un'estensione (es. cogs.moderation.actions).
- **`/owner cog reload`** — Ricarica un'estensione, anche aggiornandola da GitHub o da un file.
- **`/owner cog unload`** — Scarica un'estensione.
- **`/owner premium grant`** — Concede il premium a un server, o crea un codice da riscattare.
- **`/owner premium list`** — Mostra lo stato premium di tutti i moduli.
- **`/owner premium panel`** — Pannello interattivo per attivare/disattivare i moduli premium.
- **`/owner premium revoke`** — Revoca l'abbonamento di un modulo per un server.
- **`/owner premium status-all`** — Mostra lo stato premium di TUTTI i server in cui è presente il bot.
- **`/owner premium subscriptions`** — Mostra gli abbonamenti per modulo attivi su un server.
- **`/owner premium toggle`** — Accende o spegne la natura premium di un modulo.
- **`/owner premium whitelist-add`** — Aggiunge un server alla whitelist premium.
- **`/owner premium whitelist-list`** — Elenca i server nella whitelist premium.
- **`/owner premium whitelist-remove`** — Rimuove un server dalla whitelist premium.
- **`/owner privacy approva`** — Esegue una richiesta di cancellazione e avvisa l'utente.
- **`/owner privacy richieste`** — Elenca le richieste di cancellazione dei dati in attesa.
- **`/owner privacy rifiuta`** — Rifiuta una richiesta di cancellazione e dì all'utente perché.
- **`/owner radio add-local`** — Aggiunge un file dalla cartella inediti alla playlist della radio.
- **`/owner radio add-track`** — Aggiunge una traccia alla playlist della radio.
- **`/owner radio list-tracks`** — Mostra la playlist della radio.
- **`/owner radio remove-track`** — Rimuove una traccia dalla playlist della radio.
- **`/owner radio start`** — Entra nella radio condivisa, nel punto in cui si trova ora.
- **`/owner radio stop`** — Esce dalla radio su questo server.
- **`/owner system announce`** — Manda un annuncio a tutti i server.
- **`/owner system eval`** — Esegue codice Python (con conferma).
- **`/owner system leave-guild`** — Forza il bot a lasciare un server specifico (senza bloccarlo).
- **`/owner system memory-status`** — Mostra il consumo di RAM attuale del processo.
- **`/owner system richieste-canale`** — Imposta il canale delle richieste (solo nel server principale).
- **`/owner system shell`** — Esegue un comando shell (con conferma).
- **`/owner system stats`** — Statistiche globali del bot.

## Ruoli

- **`/ruoli azzera`** — Togli tutti i ruoli a un membro, con conferma.
- **`/ruoli crea`** — Crea un ruolo nuovo.
- **`/ruoli dai`** — Dai uno o più ruoli a un membro, anche per un tempo.
- **`/ruoli diagnosi`** — Scopri perché il bot non riesce a dare un ruolo.
- **`/ruoli massa`** — Dai o togli un ruolo a molti membri insieme, con filtri.
- **`/ruoli massa-ferma`** — Ferma l'operazione di massa in corso.
- **`/ruoli modifica`** — Cambia nome, colore e opzioni di un ruolo.
- **`/ruoli scelta`** — Ruoli che i membri si prendono da soli con /utility ruolo.
- **`/ruoli togli`** — Togli uno o più ruoli a un membro, anche per un tempo.

## Sicurezza

- **`/security escalation disable`** — Disattiva l'escalation ladder.
- **`/security escalation enable`** — Attiva l'escalation ladder.
- **`/security escalation remove-step`** — Rimuove un livello dalla scala personalizzata.
- **`/security escalation reset`** — Azzera il conteggio infrazioni di un membro.
- **`/security escalation set-reset-days`** — Giorni di buona condotta per azzerare il conteggio.
- **`/security escalation set-step`** — Configura l'azione per un livello della scala.
- **`/security escalation status`** — Mostra la scala di escalation configurata.
- **`/security globalban controlla`** — Da quanti server della rete questo utente è stato bannato dalla Spam Trap.
- **`/security globalban disable`** — Abbandona la rete di ban globali.
- **`/security globalban enable`** — Aderisci alla rete di ban globali (propaga e ricevi).
- **`/security globalban status`** — Mostra lo stato e la storia recente del ban globale.
- **`/security heatmap`** — Mostra quali ruoli hanno permessi critici e chi li possiede.
- **`/security panico attiva`** — Accende il panico: blocco totale con le regole d'emergenza.
- **`/security panico configura`** — Scelte del panico: ruoli avvisati, categorie escluse, sblocco, regole.
- **`/security panico stato`** — Mostra se il server e' bloccato e le scelte del panico.
- **`/security panico togli`** — Spegne il panico e riapre il server com'era.
- **`/security score`** — Calcola il punteggio di sicurezza del server con consigli.
- **`/security spamtrap`** — Configura i canali trappola e log dello Spam Trap.
- **`/security verify blacklist-add`** — Aggiungi un utente alla blacklist.
- **`/security verify blacklist-remove`** — Rimuovi un utente dalla blacklist.
- **`/security verify manuale`** — Verifica a mano un membro, senza controlli.
- **`/security verify opzioni`** — Ruolo «non verificato» e ruoli extra.
- **`/security verify panel`** — Pubblica il pannello di verifica.
- **`/security verify setup`** — Configura il Verify.
- **`/security verify statistiche`** — Verifiche riuscite e fallite.
- **`/security verify tempi`** — Promemoria, tempo massimo, azione su chi fallisce, verifica solo ai sospetti.
- **`/security verify tentativi`** — Tentativi di verifica di un utente.
- **`/security verify whitelist-add`** — Aggiungi un utente alla whitelist.
- **`/security verify whitelist-remove`** — Rimuovi un utente dalla whitelist.

## Ticket

- **`/ticket add`** — Aggiungi un utente o un ruolo a questo ticket.
- **`/ticket assistente`** — Risposta dell'assistente AI (per lo staff: bozza e smistamento).
- **`/ticket claim`** — Prendi in carico questo ticket.
- **`/ticket close`** — Chiudi questo ticket.
- **`/ticket dm-chiudi`** — Chiudi questa conversazione ModMail.
- **`/ticket forceclose`** — Chiudi immediatamente questo ticket, senza attesa.
- **`/ticket passa`** — Passa la presa in carico a un collega.
- **`/ticket priority`** — Imposta la priorità di questo ticket.
- **`/ticket remove`** — Rimuovi un utente o un ruolo da questo ticket.
- **`/ticket rename`** — Rinomina questo ticket.
- **`/ticket rilascia`** — Lascia la presa in carico di questo ticket.
- **`/ticket rispondi`** — Rispondi all'utente di questa conversazione ModMail.
- **`/ticket transcript`** — Ricevi il transcript senza chiudere il ticket.

## Utility

- **`/utility ai crea-personaggio`** — Crea un personaggio AI con cui chattare.
- **`/utility ai immagina`** — Genera un'immagine da una descrizione.
- **`/utility ai ingrandisci`** — Ingrandisce e ripulisce un'immagine che carichi.
- **`/utility ai lore`** — Scheda di lore su un nome, un luogo o uno yokai.
- **`/utility ai pacchetto`** — Compra 5 immagini AI in più con le monete del server.
- **`/utility ai personaggio`** — Parla con un personaggio AI del server.
- **`/utility ai riassumi`** — Riassunto degli ultimi messaggi di un canale.
- **`/utility ai spiega`** — Spiega in parole semplici un messaggio (dal suo link).
- **`/utility ai stile`** — Un messaggio nuovo scritto come scrivi tu.
- **`/utility ai traduci`** — Traduce un testo nella lingua che scegli.
- **`/utility editsnipe`** — Mostra l'ultimo messaggio modificato in questo canale.
- **`/utility info`** — Informazioni sul bot: versione, invito e supporto.
- **`/utility lingua`** — Mostra o cambia la tua lingua personale (italiano o inglese).
- **`/utility modulo`** — Compila un modulo o una candidatura di questo server.
- **`/utility ping`** — Controlla se iYokai Main è online e la sua latenza.
- **`/utility politica canali`** — Dove il bot risponde ai comandi.
- **`/utility politica comando`** — Spegne o riaccende un singolo comando.
- **`/utility politica diagnosi`** — Scopre perché un comando non funziona qui.
- **`/utility politica elenco`** — Mostra la politica dei comandi e, se vuoi, azzera un elenco.
- **`/utility politica ignora`** — Il bot ignora un ruolo o un utente.
- **`/utility poll`** — Crea un sondaggio (fino a 10 opzioni).
- **`/utility privacy cancella`** — Chiedi la cancellazione dei tuoi dati personali.
- **`/utility privacy esporta`** — Ricevi una copia dei dati che il bot conserva su di te.
- **`/utility reactionsnipe`** — Mostra l'ultima reazione rimossa in questo canale.
- **`/utility reminder cancel`** — Annulla un promemoria, o tutti i tuoi.
- **`/utility reminder list`** — Mostra i tuoi promemoria in sospeso.
- **`/utility reminder server`** — Per lo staff: i promemoria impostati in questo server.
- **`/utility reminder set`** — Imposta un promemoria.
- **`/utility report`** — Segnala un utente allo staff del server.
- **`/utility richiedi-comando`** — Proponi un nuovo comando per il bot.
- **`/utility ruolo`** — Prendi o lascia i ruoli a scelta del server.
- **`/utility scheda anzianita`** — Account più vecchi o nuovi, primi o ultimi entrati.
- **`/utility scheda canale`** — Scheda di un canale.
- **`/utility scheda membri`** — I membri che hanno un ruolo.
- **`/utility scheda permessi`** — Permessi di un membro o del bot in un canale.
- **`/utility scheda ruoli`** — Tutti i ruoli con ID, membri e colore.
- **`/utility scheda ruolo`** — Scheda di un ruolo: membri, colore, data, permessi.
- **`/utility scheda server`** — Scheda del server: proprietario, data, numeri, boost.
- **`/utility scheda utente`** — Scheda di un membro: ID, date e ruoli.
- **`/utility serverstats`** — Statistiche del server: crescita, attività dei canali e dei membri.
- **`/utility snipe`** — Mostra l'ultimo messaggio cancellato in questo canale.
- **`/utility suggest`** — Proponi un'idea per questo server.
- **`/utility tag`** — Usa un comando personalizzato di questo server.
- **`/utility verifica`** — Verificati in questo server (come il bottone del pannello).

## Vocali

- **`/voice bitrate`** — Imposta la qualità audio del canale (kbps).
- **`/voice claim`** — Prendi il canale se il proprietario non c'è più.
- **`/voice deny`** — Vieta a un utente di entrare nel canale.
- **`/voice invita`** — Manda a un utente un invito al tuo canale.
- **`/voice kick`** — Espelli un utente dal tuo canale.
- **`/voice limit`** — Imposta il limite di utenti del canale.
- **`/voice lock`** — Blocca il canale (nessun nuovo ingresso).
- **`/voice nascondi`** — Nascondi o mostra il canale a chi non è dentro.
- **`/voice permit`** — Permetti a un utente di entrare anche se il canale è bloccato.
- **`/voice rename`** — Rinomina il tuo canale vocale.
- **`/voice stato`** — Scrivi cosa state facendo nel canale (vuoto: toglie).
- **`/voice transfer`** — Trasferisci la proprietà del canale.
- **`/voice unlock`** — Sblocca il canale.
