# Elenco comandi — iYokai

Generato automaticamente da `scripts/generate_command_list.py` il 2026-11-23 16:03 UTC, interrogando l'albero comandi VERO del bot dopo aver caricato ogni cog — non un elenco scritto a mano. Da rigenerare dopo ogni commit che aggiunge, rimuove o rinomina un comando.

**Totale: 1166 comandi in 59 categorie.**

## Admin: AI

- **`/admin-ai attiva`** — Accende o spegne l'AI nel server (serve il consenso).
- **`/admin-ai boss avvia`** — Fa comparire subito il World Boss.
- **`/admin-ai boss imposta`** — Canale, giorni, ora e premi del World Boss.
- **`/admin-ai canale`** — Spegne o riaccende l'AI in un canale.
- **`/admin-ai conoscenza aggiungi`** — Aggiunge una voce alla base di conoscenza.
- **`/admin-ai conoscenza elenco`** — Le voci della base di conoscenza.
- **`/admin-ai conoscenza togli`** — Toglie una voce dalla base di conoscenza.
- **`/admin-ai costruisci`** — L'AI propone ruoli e canali da una descrizione; tu confermi.
- **`/admin-ai dungeon avvia`** — Avvia un dungeon di gruppo in un canale.
- **`/admin-ai dungeon storie`** — Quante storie di dungeon ci sono pronte per il tema del server.
- **`/admin-ai funzioni`** — Accende le funzioni automatiche: risposta alla menzione, bandiere.
- **`/admin-ai interruttore`** — Spegne o riaccende una funzione dell'AI, una per una.
- **`/admin-ai limiti`** — Tetto di spesa e quote: per utente, funzione, immagini.
- **`/admin-ai lore`** — Tono e ambientazione del server per ogni testo dell'AI.
- **`/admin-ai mistero crea`** — Nasconde un mistero con un codice e un premio per il server.
- **`/admin-ai mistero elenco`** — I misteri del server (il codice resta segreto).
- **`/admin-ai mistero togli`** — Toglie un mistero.
- **`/admin-ai moderazione`** — L'AI segnala allo staff i messaggi sospetti di un canale.
- **`/admin-ai personaggio`** — Installa, toglie o cancella un personaggio AI del server.
- **`/admin-ai privacy`** — Messaggi degli utenti all'AI, memoria e lunghezza delle risposte.
- **`/admin-ai riepilogo anteprima`** — Mostra a te il riepilogo di adesso, senza pubblicarlo.
- **`/admin-ai riepilogo imposta`** — Riepilogo del server: canale, ora, frequenza e canali da leggere.
- **`/admin-ai staff cerca-log`** — Cerca nei log con una domanda (chi, cosa, quando).
- **`/admin-ai staff incidente`** — Riassume gli ultimi eventi di sicurezza del server.
- **`/admin-ai staff prima-risposta`** — Accende o spegne la prima risposta automatica dell'AI in un pannello ticket.
- **`/admin-ai staff regola`** — Scrivi cosa vuoi da AutoMod: ti propongo la regola, la attivi tu.
- **`/admin-ai staff riassunto-ticket`** — Accende o spegne il riassunto AI nel log alla chiusura di un ticket.
- **`/admin-ai stato`** — Stato dell'AI nel server: fornitori, scelte e uso del mese.
- **`/admin-ai traduzione`** — Traduce da solo ogni messaggio di un canale in una lingua.
- **`/admin-ai vietate`** — Parole o argomenti che l'AI deve rifiutare.
- **`/admin-ai voce imposta`** — Voce di Yokai: accesa o spenta, tono e canali dei saluti.
- **`/admin-ai voce parla`** — Yokai dice un annuncio a voce in un canale.

## Admin: avvisi social

- **`/admin-alert bluesky`** — Avvisa dei nuovi post di un profilo Bluesky.
- **`/admin-alert diretta`** — Controlla ora se un canale Twitch, Kick o YouTube è in diretta.
- **`/admin-alert eventi-twitch`** — Crea eventi Discord dal calendario di un canale Twitch.
- **`/admin-alert feed-noto`** — Notizie di anime e manga o giochi gratis, da feed già scelti.
- **`/admin-alert ferma-tutti`** — Cancella tutti gli avvisi del server o di un canale (con conferma).
- **`/admin-alert formato`** — Testo o embed, embed salvato come modello, Short di YouTube.
- **`/admin-alert messaggio`** — Cambia il testo di un avviso (anche Twitch, YouTube, Kick).
- **`/admin-alert picarto`** — Avvisa quando un canale Picarto va in diretta.
- **`/admin-alert podcast`** — Cerca un podcast per nome e avvisa dei nuovi episodi.
- **`/admin-alert ruolo-live aggiungi`** — Nuova regola: dà un ruolo a chi va in diretta.
- **`/admin-alert ruolo-live annuncio`** — Annuncia in un canale chi va in diretta.
- **`/admin-alert ruolo-live eccezioni`** — Membri che ricevono il ruolo anche senza le parole o il gioco.
- **`/admin-alert ruolo-live elenco`** — Le regole del ruolo «in diretta» del server.
- **`/admin-alert ruolo-live esclusi`** — Membri o ruoli che non ricevono mai il ruolo di una regola.
- **`/admin-alert ruolo-live filtri`** — Parole del titolo, giochi e ruolo richiesto di una regola.
- **`/admin-alert ruolo-live rimuovi`** — Toglie una regola del ruolo «in diretta».
- **`/admin-alert sposta`** — Sposta un avviso in un altro canale.
- **`/admin-alert subreddit`** — Avvisa dei nuovi post di un subreddit, come testo o embed.
- **`/admin-alert youtube`** — Aggiungi un canale YouTube da qualsiasi link: video, Short, @nome, playlist.

## Admin: anti-nuke

- **`/admin-antinuke canale-allarmi`** — Sceglie dove arrivano gli allarmi dell'Anti-Nuke (canale o forum).
- **`/admin-antinuke casi`** — Registro degli attacchi fermati: elenco o dettaglio di un caso.
- **`/admin-antinuke enable`** — Attiva o disattiva l'Anti-Nuke.
- **`/admin-antinuke guardie`** — Protezioni su azioni singole: permessi dei ruoli, ruoli ai membri, link, bot.
- **`/admin-antinuke limits`** — Configura la soglia di rilevamento per una categoria.
- **`/admin-antinuke punish-action`** — Cosa fare all'autore di un'azione distruttiva di massa.
- **`/admin-antinuke recovery`** — Attiva/disattiva la ricreazione automatica di canali/ruoli cancellati durante un attacco.
- **`/admin-antinuke rilascia`** — Toglie la quarantena all'autore di un caso e gli rimette i ruoli.
- **`/admin-antinuke status`** — Mostra la configurazione attuale dell'Anti-Nuke.
- **`/admin-antinuke trusted-add`** — Esenta un utente, un bot o un webhook dai controlli Anti-Nuke.
- **`/admin-antinuke trusted-list`** — Elenca chi è esentato dai controlli Anti-Nuke e con quali limiti.
- **`/admin-antinuke trusted-remove`** — Rimuove un utente, un bot o un webhook dalla lista fidati Anti-Nuke.

## Admin: anti-raid

- **`/admin-antiraid account-age`** — Età minima dell'account per non essere considerato sospetto.
- **`/admin-antiraid alert-channel`** — Canale dove ricevere gli alert di sicurezza (Anti-Raid + Anti-Nuke).
- **`/admin-antiraid avatar-check`** — Attiva/disattiva il rilevamento avatar assente.
- **`/admin-antiraid elenco`** — File con tutti gli account dei raid nelle ultime ore.
- **`/admin-antiraid enable`** — Attiva o disattiva l'Anti-Raid.
- **`/admin-antiraid filtro-ingresso`** — Azione per un filtro all'ingresso (vale anche fuori da un raid).
- **`/admin-antiraid join-rate`** — Configura il limite di join in un intervallo di tempo.
- **`/admin-antiraid livello`** — Livelli di allerta: normale, allerta, alto, blocco.
- **`/admin-antiraid lockdown-action`** — Cosa fare quando un raid viene rilevato.
- **`/admin-antiraid nomi-vietati`** — Lista di parole o schemi (con *) vietati nei nomi di chi entra.
- **`/admin-antiraid ping-ruoli`** — Ruoli dello staff pingati al primo allarme di un raid (vuoto: nessuno).
- **`/admin-antiraid quarantine-hold`** — Impedisce a chi non è fidato di togliere la quarantena a mano.
- **`/admin-antiraid rilascia`** — Toglie la quarantena a un membro (il modo giusto, col blocco attivo).
- **`/admin-antiraid segnala`** — Segnala a chi gestisce il bot un raid che non è stato riconosciuto.
- **`/admin-antiraid segnali`** — Segnali di raid sugli ultimi ingressi e azione su chi è entrato prima.
- **`/admin-antiraid status`** — Mostra la configurazione attuale dell'Anti-Raid.
- **`/admin-antiraid username-check`** — Attiva/disattiva il rilevamento pattern username sospetti.

## Admin: automazioni

- **`/admin-automazioni inneschi aggiungi`** — Fa partire un tag da solo: reazione, intervallo, orario, bottone, ruolo.
- **`/admin-automazioni inneschi avvia-ora`** — Fa partire un innesco subito, per provarlo.
- **`/admin-automazioni inneschi elenco`** — Gli inneschi del server.
- **`/admin-automazioni inneschi togli`** — Toglie un innesco.
- **`/admin-automazioni programma`** — Programma un'azione sicura per più tardi (ruolo, messaggio, sblocco canale): fino a 5.
- **`/admin-automazioni script errori`** — Gli ultimi 10 errori dello script di un tag.
- **`/admin-automazioni slash elenco`** — I comandi e i menu del server.
- **`/admin-automazioni slash menu`** — Voci del menu col tasto destro (su un utente o un messaggio) che rispondono con un tag.
- **`/admin-automazioni slash pubblica`** — Crea un comando del server che risponde con un tag.
- **`/admin-automazioni slash togli`** — Toglie un comando del server.

## Admin: AutoMod

- **`/admin-automod avviso`** — Avvisa chi si vede cancellare un messaggio dall'AutoMod.
- **`/admin-automod azzera`** — Azzera un contatore delle regole AutoMod.
- **`/admin-automod calore`** — Calore: le regole danno punti che calano col tempo; alla soglia scatta una sanzione.
- **`/admin-automod esenzioni channel-add`** — Esenta un canale da tutti i filtri AutoMod avanzati.
- **`/admin-automod esenzioni channel-remove`** — Rimuove l'esenzione di un canale.
- **`/admin-automod esenzioni role-add`** — Esenta un ruolo da tutti i filtri AutoMod avanzati.
- **`/admin-automod esenzioni role-remove`** — Rimuove l'esenzione di un ruolo.
- **`/admin-automod gruppo`** — Accende o spegne tutte le regole di un gruppo.
- **`/admin-automod immagini`** — Impostazioni del filtro per le immagini sospette.
- **`/admin-automod liste`** — Apre il pannello delle liste con nome: parole e domini.
- **`/admin-automod log-channel`** — Imposta il canale dove pubblicare il log delle azioni AutoMod avanzate.
- **`/admin-automod mute-duration`** — Imposta la durata del timeout usato dall'azione 'mute' dell'AutoMod.
- **`/admin-automod odio base`** — Accende o spegne la lista di base degli insulti d'odio.
- **`/admin-automod odio blocco`** — Blocco preventivo delle frasi d'odio.
- **`/admin-automod odio nomi`** — Controlla nickname e nomi visualizzati all'ingresso e al cambio.
- **`/admin-automod odio parola`** — Aggiunge o toglie una parola propria o una parola lecita.
- **`/admin-automod odio prova`** — Prova un testo contro le parole vietate, senza agire.
- **`/admin-automod odio richiami`** — Richiami per parole d'odio prima del timeout.
- **`/admin-automod odio stato`** — Mostra come sono impostate le parole vietate.
- **`/admin-automod parole add`** — Aggiunge una parola vietata.
- **`/admin-automod parole list`** — Mostra le parole vietate configurate.
- **`/admin-automod parole remove`** — Rimuove una parola vietata.
- **`/admin-automod pulizia`** — Pulisce un canale ogni tanto, per tipo di messaggio.
- **`/admin-automod regole`** — Apre il pannello delle regole AutoMod: condizioni e azioni.
- **`/admin-automod riepilogo`** — Riepilogo delle violazioni AutoMod del server, a pagine.
- **`/admin-automod status`** — Mostra la configurazione attuale dei filtri AutoMod avanzati.
- **`/admin-automod sync`** — Forza una sincronizzazione manuale delle regole AutoMod.
- **`/admin-automod violazione-togli`** — Toglie una violazione dal registro AutoMod.
- **`/admin-automod violazioni`** — Mostra le violazioni AutoMod di un utente, a pagine.

## Admin: backup

- **`/admin-backup annulla`** — Ferma il caricamento in corso (ciò che è già fatto resta).
- **`/admin-backup carica`** — Ricarica in questo server una copia salvata, scegliendo le parti.
- **`/admin-backup chat carica`** — Ricarica una chat salvata in un canale, anche diverso.
- **`/admin-backup chat salva`** — Salva gli ultimi messaggi di un canale (fino a 1000) per ricaricarli dopo.
- **`/admin-backup collega`** — Collega QUESTO server come backup, con il codice ricevuto dal server principale.
- **`/admin-backup copia canale`** — Copia un canale con i permessi; una categoria con i suoi canali.
- **`/admin-backup copia ruolo`** — Copia un ruolo con i permessi e, a scelta, i permessi nei canali.
- **`/admin-backup crea`** — Prepara il backup: codice di collegamento e link per il nuovo server.
- **`/admin-backup elimina`** — Elimina una copia salvata, o tutte (con conferma).
- **`/admin-backup esporta`** — Esporta struttura, canali, ruoli, ban o reazioni in un file.
- **`/admin-backup importa`** — Importa la struttura da un file JSON, scegliendo cosa applicare.
- **`/admin-backup lista`** — Le copie salvate, con la data; con un numero, cosa contiene una copia.
- **`/admin-backup main`** — Registra questo server come 'main' per il Backup System.
- **`/admin-backup modello`** — Modelli: pronti, tuoi o di Discord. Elenco, scheda, uso e condivisione.
- **`/admin-backup promuovi`** — Promuove QUESTO server (finora backup) a nuovo main, se il main originale è perso.
- **`/admin-backup registro`** — Chi ha usato backup, modelli e sincronie (ultimi 20, 365 giorni).
- **`/admin-backup ripristino modo`** — Scegli come questo server gestisce il restore utenti via OAuth2.
- **`/admin-backup ripristino utenti`** — Ripristina in QUESTO server gli utenti dell'ultimo snapshot di un altro server.
- **`/admin-backup salva`** — Salva una copia datata della struttura di questo server.
- **`/admin-backup stato`** — Avanzamento dell'ultimo caricamento in questo server.

## Admin: benvenuto

- **`/admin-benvenuto addio`** — Configura il messaggio di addio.
- **`/admin-benvenuto anteprima`** — Mostra un'anteprima di come apparirebbe un messaggio.
- **`/admin-benvenuto avviso-topic`** — Avvisa in un canale quando cambia l'argomento di un canale.
- **`/admin-benvenuto boost`** — Configura il messaggio di boost.
- **`/admin-benvenuto embed`** — Usa un embed salvato per il benvenuto, il DM o l'addio.
- **`/admin-benvenuto extra`** — Benvenuto: DM, varianti, reazioni; messaggi di ban e addio.
- **`/admin-benvenuto immagine`** — Aggiungi al benvenuto un'immagine con avatar, nome e numero del membro.
- **`/admin-benvenuto immagini`** — Immagini proprie del benvenuto (al massimo 10): a ogni ingresso se ne sceglie una a caso.
- **`/admin-benvenuto messaggio`** — Configura il messaggio di benvenuto.

## Admin: impianto del bot

- **`/admin-bot config canale-report`** — Imposta il canale delle segnalazioni.
- **`/admin-bot config canale-suggerimenti`** — Imposta il canale dei suggerimenti.
- **`/admin-bot config export`** — Esporta la configurazione di questo server in un file.
- **`/admin-bot config history`** — Mostra le ultime modifiche alla configurazione.
- **`/admin-bot config import`** — Importa una configurazione da un file esportato con /admin-bot config export.
- **`/admin-bot config nickname-bot`** — Cambia il nome del bot in questo server.
- **`/admin-bot config permessi`** — Mostra il livello di permesso di un membro e perché.
- **`/admin-bot config pulisci`** — Canali e ruoli cancellati: cosa si pulirà dalla configurazione e quando (dopo 7 giorni).
- **`/admin-bot config reset`** — Azzera la configurazione di questo server (e, a richiesta, tutti i dati dopo 30 giorni).
- **`/admin-bot config risposte`** — Risposte del bot: private, cancellate dopo un po', colori.
- **`/admin-bot config rollback`** — Ripristina il valore precedente di una modifica.
- **`/admin-bot config sincronizza`** — Riscrive i permessi dei comandi di questo server.
- **`/admin-bot config staff`** — Ruoli admin, mod e ban del bot: elenco e scelta.
- **`/admin-bot lingua set`** — Imposta la lingua di questo server.
- **`/admin-bot lingua show`** — Mostra la lingua impostata per questo server.
- **`/admin-bot politica canali`** — Dove il bot risponde ai comandi.
- **`/admin-bot politica comando`** — Spegne o riaccende un singolo comando.
- **`/admin-bot politica diagnosi`** — Scopre perché un comando non funziona qui.
- **`/admin-bot politica elenco`** — Mostra la politica dei comandi e, se vuoi, azzera un elenco.
- **`/admin-bot politica ignora`** — Il bot ignora un ruolo o un utente.
- **`/admin-bot politica ruolo-richiesto`** — Chi usa un comando deve avere un certo ruolo.
- **`/admin-bot premium aspetto`** — Avatar, banner e descrizione del bot in questo server (premium).
- **`/admin-bot premium assegna`** — Metti uno dei tuoi posti premium su questo server.
- **`/admin-bot premium marchio`** — Usa un bot con il tuo nome e il tuo avatar (premium).
- **`/admin-bot premium riscatta`** — Riscatta un codice premium per questo server.
- **`/admin-bot premium sblocca`** — Sblocca un modulo premium per 30 giorni con le monete della cassa del server.
- **`/admin-bot premium stato`** — Mostra come è sbloccato il premium in questo server.
- **`/admin-bot premium togli-posto`** — Togli il tuo posto premium da questo server.
- **`/admin-bot setup attiva`** — Attiva o disattiva i moduli del bot, per categoria.
- **`/admin-bot setup identita-bot`** — Nome e logo degli altri bot di iYokai in questo server.
- **`/admin-bot setup wizard`** — Configura passo-passo ruoli e moduli del bot, una categoria alla volta.

## Admin: economia

- **`/admin-economia annunci clan-off`** — Disattiva l'annuncio automatico della top 3 gilde.
- **`/admin-economia annunci clan-set`** — Imposta il canale dove annunciare la top 3 gilde del mese.
- **`/admin-economia annunci vincitori-off`** — Disattiva l'annuncio dei vincitori del mese.
- **`/admin-economia annunci vincitori-set`** — Imposta il canale dove annunciare i vincitori del mese.
- **`/admin-economia assegna-lobby`** — Premio partecipazione: assegna coin a chi è in vocale ORA, dalla cassa del server.
- **`/admin-economia assegna-winner`** — Premio vincitore: assegna coin a un membro, dalla cassa del server.
- **`/admin-economia azzera`** — Azzera i saldi di tutto il server (scrivi il nome del server).
- **`/admin-economia azzera-inventari`** — Svuota gli inventari di tutto il server (scrivi il nome del server).
- **`/admin-economia cassa-premium`** — Sblocca un mese di bot premium spendendo dalla cassa.
- **`/admin-economia drop`** — Drop casuali: probabilità, importi, pausa e canale.
- **`/admin-economia forziere`** — Fai comparire dei forzieri di monete in un canale.
- **`/admin-economia limiti`** — Saldo di partenza, tetto al saldo, puntate dei giochi e saldo di chi esce.
- **`/admin-economia monete`** — Modifica il saldo di un membro.
- **`/admin-economia premi`** — Premio giornaliero, serie di giorni, settimanale, mensile e lavoro.
- **`/admin-economia regalabile`** — Decidi se un oggetto del negozio si può regalare.
- **`/admin-economia ruolo`** — Aggiungi o togli monete a tutti i membri di un ruolo.
- **`/admin-economia shop-add`** — Aggiunge un oggetto allo shop.
- **`/admin-economia shop-edit`** — Cambia un oggetto dello shop (prezzo, scorte, ruolo richiesto...).
- **`/admin-economia shop-remove`** — Rimuove un oggetto dallo shop.
- **`/admin-economia statistiche`** — Monete in giro nel server e come sono distribuite.
- **`/admin-economia stato`** — Tutte le regole dell'economia in un colpo.

## Admin: filtri

- **`/admin-filtri actions-set`** — Configura quali azioni eseguire quando un filtro avanzato scatta.
- **`/admin-filtri anti-attachment`** — Configura l'anti-attachment-spam (troppi allegati in poco tempo).
- **`/admin-filtri anti-caps`** — Configura l'anti-caps (troppo maiuscolo).
- **`/admin-filtri anti-link-domain`** — Aggiunge o rimuove un dominio dalla whitelist/blacklist link.
- **`/admin-filtri anti-link-mode`** — Imposta la modalità del filtro link.
- **`/admin-filtri anti-mention`** — Configura l'anti-mass-mention (troppi utenti taggati in un messaggio).
- **`/admin-filtri anti-spam-emoji`** — Configura l'anti-spam emoji (troppe emoji in un messaggio).
- **`/admin-filtri anti-spam-messages`** — Configura l'anti-spam messaggi (troppi messaggi in poco tempo).
- **`/admin-filtri anti-spam-sticker`** — Configura l'anti-spam sticker (troppi sticker in poco tempo).
- **`/admin-filtri anti-zalgo`** — Attiva o disattiva l'anti-zalgo (testo con segni diacritici anomali).
- **`/admin-filtri canale-media`** — Canale solo media, senza allegati o normale.
- **`/admin-filtri contenuto`** — Embed e inoltri controllati dai filtri; tipi di file vietati.
- **`/admin-filtri emergenza`** — Blocco dei canali per troppe menzioni e modalità panico dell'AutoMod.
- **`/admin-filtri forma-testo`** — Limiti sulla forma del messaggio: a-capo, lunghezza, spoiler (0 = spento).
- **`/admin-filtri invites`** — Attiva o disattiva il blocco automatico degli inviti Discord.
- **`/admin-filtri messaggi`** — Ripetuti, troppo corti, link e menzioni contati nel tempo (0 = spento).
- **`/admin-filtri phishing`** — Attiva o disattiva il blocco dei link di phishing (finti regali, finti login).

## Admin: giochi

- **`/admin-giochi auto togli-foto`** — Toglie la foto di un'auto di un membro (una o tutte).
- **`/admin-giochi battitura aggiungi`** — Aggiunge un testo per la battitura (finestra).
- **`/admin-giochi battitura elenca`** — I testi di battitura del server.
- **`/admin-giochi battitura rimuovi`** — Toglie un testo di battitura.
- **`/admin-giochi carte pacchetti`** — Quali pacchetti di carte sono accesi nel server.
- **`/admin-giochi conteggio canale`** — Scegli i canali dove si conta (fino a 10) e come.
- **`/admin-giochi conteggio importa`** — Porta in un canale i punteggi di un file CSV o JSON.
- **`/admin-giochi conteggio regole`** — Punizione dopo uno sbaglio e ruolo di chi ha contato per ultimo.
- **`/admin-giochi conteggio traguardo`** — Ruolo o messaggio quando il conteggio tocca un numero.
- **`/admin-giochi evento avvia`** — Avvia l'evento: chi scrive nel canale riceve monete.
- **`/admin-giochi evento chiudi`** — Chiudi l'evento di monete in corso.
- **`/admin-giochi evento riffa`** — Una riffa pagata dalla cassa del server: chi clicca può vincere il premio.
- **`/admin-giochi oggetto-azione`** — Cosa fa un oggetto del negozio quando lo si usa: monete o un ruolo.
- **`/admin-giochi punteggi azzera`** — Azzera i punteggi di una gara (con conferma).
- **`/admin-giochi quiz carica`** — Carica domande per il quiz da un file CSV o JSON.
- **`/admin-giochi quiz elenca`** — Le domande del quiz caricate dal server.
- **`/admin-giochi quiz regole`** — Regole del quiz: punti, tempo, risposta mostrata, il bot gioca.
- **`/admin-giochi quiz rimuovi`** — Toglie una domanda caricata dal server.
- **`/admin-giochi servizi`** — Accende o spegne i servizi esterni: immagini Lemmy e ricerca di GIF.
- **`/admin-giochi sospensione`** — Sospendi una persona dal gioco, riabilitala o decidi sulla sua richiesta di revisione.
- **`/admin-giochi stipendi auto`** — Paga gli stipendi da solo a un'ora (UTC) e scegli le monete per messaggio.
- **`/admin-giochi stipendi elenco`** — Gli stipendi e le tasse per ruolo, e le regole dei messaggi.
- **`/admin-giochi stipendi imposta`** — Stipendio (positivo) o tassa (negativo) per un ruolo.
- **`/admin-giochi stipendi lotteria`** — Prezzo della lotteria e quota di perdite rimborsata.
- **`/admin-giochi stipendi toglie`** — Toglie lo stipendio o la tassa di un ruolo.
- **`/admin-giochi tela azzera`** — Svuota tutta la tela di pixel del server.
- **`/admin-giochi tela blocca`** — Blocca una persona dalla tela di pixel.
- **`/admin-giochi tela impostazioni`** — Pausa, costo per saltarla e pagina pubblica della tela.
- **`/admin-giochi tela sblocca`** — Toglie il blocco dalla tela di pixel a una persona.
- **`/admin-giochi tela togli-utente`** — Toglie dalla tela tutti i pixel messi da una persona.
- **`/admin-giochi telefono blocca`** — Blocca o sblocca una persona o un altro server dal telefono.
- **`/admin-giochi telefono canale`** — Il canale del telefono del server.
- **`/admin-giochi telefono consenso`** — Accende o spegne il telefono: spento di base.
- **`/admin-giochi telefono registro`** — Le ultime chiamate del server: solo server, ora e durata.
- **`/admin-giochi voto`** — Il premio che il server dà a chi vota il bot (senza valori: lo stato).

## Admin: giveaway

- **`/admin-giveaway annulla`** — Annulla un giveaway in corso, senza vincitori.
- **`/admin-giveaway avvia`** — Avvia un giveaway.
- **`/admin-giveaway chiudi`** — Chiude un giveaway prima del tempo ed estrae i vincitori.
- **`/admin-giveaway elenco`** — I giveaway in corso nel server.
- **`/admin-giveaway modello`** — Modelli di giveaway: salva, elenca, elimina, avvia.
- **`/admin-giveaway modifica`** — Cambia durata, vincitori, premio o immagine di un giveaway.
- **`/admin-giveaway opzioni`** — Aspetto, messaggi, log e ruoli esclusi dei giveaway.
- **`/admin-giveaway partecipanti`** — Chi partecipa a un giveaway, a pagine da 20.
- **`/admin-giveaway programmati`** — Giveaway programmati: elenca (anche quelli in errore) o annulla.

## Admin: inviti

- **`/admin-inviti azzera`** — Cancella lo storico degli inviti e i bonus del server.
- **`/admin-inviti bonus`** — Aggiungi o togli inviti a un membro (punti dello staff).
- **`/admin-inviti cancella`** — Cancella inviti: uno, quelli poco usati o quelli di un canale.
- **`/admin-inviti codici`** — I codici d'invito creati da un membro, a pagine da 10.
- **`/admin-inviti crea`** — Crea un invito senza scadenza, con nome e ruolo.
- **`/admin-inviti escludi`** — Nascondi membri o ruoli dalla classifica degli inviti.
- **`/admin-inviti esporta`** — Esporta ingressi, classifica o codici in un file.
- **`/admin-inviti etichetta`** — Dai un nome a un codice, con un ruolo per chi entra.
- **`/admin-inviti impostazioni`** — Registro degli inviti, link personale e ingressi non contati.
- **`/admin-inviti riallinea`** — Rileggi gli inviti da Discord e confrontali con gli ingressi salvati.
- **`/admin-inviti statistiche`** — Quanti membri portati dagli inviti restano e sono attivi.

## Admin: livelli e XP

- **`/admin-livelli annuncio`** — Dove e quando annunciare i level-up.
- **`/admin-livelli azzera auto`** — Azzera chi esce o viene bannato; blocca XP e azzeramenti al proprietario.
- **`/admin-livelli azzera importa`** — Carica gli XP da un file JSON o CSV esportato da un altro bot.
- **`/admin-livelli azzera ripristina`** — Rimette gli XP di una copia di sicurezza (valida 30 giorni).
- **`/admin-livelli azzera server`** — Azzera gli XP di tutto il server (prima fa una copia di sicurezza).
- **`/admin-livelli card`** — Mostra o nascondi in questo server gli sfondi con immagine di card e profili.
- **`/admin-livelli classifica-ruoli`** — Un ruolo al primo della classifica XP, ai primi 3 o ai primi 10 (aggiornato ogni ora).
- **`/admin-livelli diagnosi`** — Spiega perché un membro non prende XP in un canale.
- **`/admin-livelli escludi`** — Un canale, una categoria o un ruolo non dà XP (rifallo per toglierlo).
- **`/admin-livelli guadagno canali`** — Dà XP in tutti i canali tranne gli esclusi, oppure solo in quelli dell'elenco.
- **`/admin-livelli guadagno comandi`** — Accende o spegne l'XP per l'uso dei comandi slash (di base spento).
- **`/admin-livelli guadagno contesti`** — Se thread, post dei forum e chat dei canali vocali danno XP.
- **`/admin-livelli guadagno formula`** — Sceglie la curva dei livelli e ricalcola i livelli di tutti.
- **`/admin-livelli guadagno messaggi`** — XP per messaggio: fisso o a parola, più il bonus per messaggi lunghi o con immagini.
- **`/admin-livelli guadagno prefissi`** — Prefissi di altri bot: i messaggi che iniziano così non danno XP.
- **`/admin-livelli guadagno reazioni`** — XP per le reazioni messe e ricevute (di base spento).
- **`/admin-livelli guadagno vocale`** — XP in vocale: persone minime nel canale e controllo anti-farm.
- **`/admin-livelli membro`** — Modifica XP e livello di un membro.
- **`/admin-livelli moltiplicatore`** — XP moltiplicati in un canale o per un ruolo (fattore 1 = toglie la regola).
- **`/admin-livelli mostra`** — Mostra le impostazioni dei livelli di questo server.
- **`/admin-livelli negozio`** — Chiedi conferma prima di ogni acquisto nel negozio (si può spegnere).
- **`/admin-livelli premi`** — Ruoli-premio: tienili tutti o tieni solo quello più alto.
- **`/admin-livelli progressi`** — Accende o spegne missioni, serie, traguardi e pass, e fissa l'obiettivo del server.
- **`/admin-livelli xp`** — Quanti XP e coin si guadagnano, e come si sommano i moltiplicatori.

## Admin: log

- **`/admin-log archivio-canale`** — Scarica in un file gli ultimi messaggi di un canale, anche quelli appena cancellati.
- **`/admin-log canale`** — Imposta il canale (o il forum) dei log del server.
- **`/admin-log cerca canale`** — Mostra lo storico eventi di un canale.
- **`/admin-log cerca ruolo`** — Mostra lo storico eventi di un ruolo.
- **`/admin-log cerca utente`** — Mostra lo storico eventi di un utente.
- **`/admin-log crea-canali`** — Crea una categoria privata con un canale per ogni tipo di log.
- **`/admin-log crea-forum`** — Crea un forum privato per i log: un post per ogni tipo.
- **`/admin-log esporta`** — Esporta lo storico eventi completo del server come file JSON.
- **`/admin-log eventi`** — Accendi o spegni ogni singolo evento dei log.
- **`/admin-log formato`** — Scrivi tu il testo di un evento di log, con i segnaposto. Senza testo, torna al testo di prima.
- **`/admin-log ignora`** — Cosa i log non registrano (canali, utenti, ruoli; testi solo per i messaggi).
- **`/admin-log istantanea`** — Un canale in una pagina web privata che scade. Crea, elenca o togli.
- **`/admin-log rotta`** — Manda un solo tipo di evento in un canale tutto suo. Senza canale, torna al canale del gruppo.
- **`/admin-log stato`** — Mostra dove vanno i log del server.
- **`/admin-log vista-forum`** — Un forum con un post per canale o per caso. Senza forum, la vista si spegne.
- **`/admin-log webhook`** — Manda i log da un webhook del canale, raggruppati, con limiti suoi.

## Admin: menu dei ruoli

- **`/admin-menu-ruoli aggiungi-molti`** — Aggiungi a un menu più coppie emoji-ruolo in un colpo solo.
- **`/admin-menu-ruoli canale`** — Crea un canale per i menu dei ruoli: tutti leggono, scrive solo il bot.
- **`/admin-menu-ruoli colori`** — Usa i ruoli di un menu «unique» come tavolozza dei colori del nome.
- **`/admin-menu-ruoli gruppo`** — Collega più menu: tra tutti si tiene un solo ruolo. Nome vuoto: scollega.
- **`/admin-menu-ruoli guidata`** — Crea un menu dei ruoli a passi: tipo, testo, canale, ruoli ed emoji.
- **`/admin-menu-ruoli immagine`** — Metti un'immagine dentro il messaggio del menu (allegato o indirizzo).
- **`/admin-menu-ruoli modello`** — Crea un menu da un modello pronto: verifica, notifiche, colori, interessi.
- **`/admin-menu-ruoli opzione`** — Cambia emoji, etichetta, descrizione, colore o posto di un'opzione di un menu.
- **`/admin-menu-ruoli personale`** — Concedi o togli a un membro il ruolo personale (nome e colore scelti da lui).
- **`/admin-menu-ruoli ripara`** — Rimetti le reazioni del bot su un menu a reazioni se qualcuno le ha tolte.
- **`/admin-menu-ruoli ruoli-extra`** — Una opzione di un menu dà anche altri ruoli (al massimo 5 in tutto).
- **`/admin-menu-ruoli sposta`** — Aggancia o sposta un menu a reazioni su un messaggio già scritto.
- **`/admin-menu-ruoli svuota`** — Elimina tutti i menu di ruoli del server, o di un canale.

## Admin: messaggi

- **`/admin-messaggi auto`** — Automatismi: citazioni, correzione link, pubblicazione annunci, accorciatore.
- **`/admin-messaggi embed bottoni`** — Aggiungi o togli i bottoni di un embed (link o mostra tag).
- **`/admin-messaggi embed colore`** — Il colore predefinito dei tuoi embed (vuoto per toglierlo).
- **`/admin-messaggi embed crea`** — Crea un embed e guarda l'anteprima.
- **`/admin-messaggi embed elenco`** — Mostra gli embed salvati.
- **`/admin-messaggi embed elimina`** — Elimina un embed salvato (il messaggio pubblicato resta).
- **`/admin-messaggi embed json`** — Importa un embed da un JSON o esportalo in un file.
- **`/admin-messaggi embed modifica`** — Cambia un embed salvato (e il messaggio già pubblicato).
- **`/admin-messaggi embed pubblica`** — Manda un embed salvato in un canale.
- **`/admin-messaggi fissi elenco`** — Elenca i messaggi fissi del server.
- **`/admin-messaggi fissi imposta`** — Imposta lo sticky message di un canale.
- **`/admin-messaggi fissi togli`** — Rimuove lo sticky message di un canale.
- **`/admin-messaggi programmati annulla`** — Annulla un messaggio programmato.
- **`/admin-messaggi programmati crea`** — Programma un messaggio.
- **`/admin-messaggi programmati elenco`** — Mostra i messaggi programmati di questo server.
- **`/admin-messaggi programmati salta`** — Salta il prossimo giro di un messaggio che si ripete.
- **`/admin-messaggi promemoria`** — Per lo staff: i promemoria impostati in questo server.
- **`/admin-messaggi scrivi`** — Fai scrivere un messaggio al bot in un canale.

## Admin: moduli

- **`/admin-moduli alert elenco`** — Elenca gli avvisi del server.
- **`/admin-moduli alert feed`** — Segui un feed RSS/Atom.
- **`/admin-moduli alert guida-social`** — Avvisi per TikTok, Instagram e X.
- **`/admin-moduli alert kick`** — Avvisa quando un canale Kick va in diretta.
- **`/admin-moduli alert opzioni`** — Opzioni di un avviso: ruolo, fine diretta, bottone.
- **`/admin-moduli alert rimuovi`** — Rimuove un avviso o un webhook.
- **`/admin-moduli alert ruolo-live`** — Ruolo dato a chi è in diretta.
- **`/admin-moduli alert twitch`** — Avvisa quando uno streamer Twitch va live.
- **`/admin-moduli alert webhook`** — Crea un webhook per pubblicare da servizi esterni.
- **`/admin-moduli alert youtube-live`** — Avvisa quando un canale YouTube va live.
- **`/admin-moduli candidature crea`** — Crea un modulo o una candidatura.
- **`/admin-moduli candidature elenco`** — I moduli di questo server.
- **`/admin-moduli candidature elimina`** — Elimina un modulo e le sue risposte.
- **`/admin-moduli citazioni azione`** — Esporta, importa o elimina le citazioni (JSON).
- **`/admin-moduli compleanni canale`** — Scegli il canale degli auguri (vuoto per spegnerli).
- **`/admin-moduli compleanni membro`** — Registra il compleanno di un membro (solo giorno e mese).
- **`/admin-moduli compleanni ruolo`** — Un ruolo per 24 ore a chi compie gli anni (vuoto per toglierlo).
- **`/admin-moduli compleanni stato`** — Come sono impostati gli auguri di compleanno.
- **`/admin-moduli contatori azzera`** — Smetti di aggiornare tutti i contatori (i canali restano).
- **`/admin-moduli contatori categoria`** — Crea una categoria con i contatori più usati.
- **`/admin-moduli contatori crea`** — Crea un canale che mostra un numero.
- **`/admin-moduli contatori elenco`** — Mostra i contatori del server.
- **`/admin-moduli contatori elimina`** — Smetti di aggiornare un contatore (il canale resta).
- **`/admin-moduli contatori modifica`** — Cambia l'etichetta o l'obiettivo di un contatore.
- **`/admin-moduli sondaggi pesi`** — Dai un peso al voto di un ruolo nei sondaggi (max 25 ruoli).
- **`/admin-moduli starboard disattiva`** — Spegni la bacheca.
- **`/admin-moduli starboard esclusi`** — Canali che non finiscono mai in bacheca (al massimo 25).
- **`/admin-moduli starboard imposta`** — Scegli il canale della bacheca e la soglia di stelle.
- **`/admin-moduli starboard soglia`** — Cambia quante stelle servono per finire in bacheca.
- **`/admin-moduli starboard stato`** — Come è impostata la bacheca.
- **`/admin-moduli statistiche diagnosi`** — Perché le statistiche non si contano?
- **`/admin-moduli statistiche elenco`** — Mostra regole ed esclusioni delle statistiche.
- **`/admin-moduli statistiche esporta`** — Esporta in un file ZIP le statistiche, i contatori e le regole del server.
- **`/admin-moduli statistiche impostazioni`** — Filtri delle statistiche: canali, membri, ruoli, chi le vede.
- **`/admin-moduli statistiche ruolo-aggiungi`** — Dai un ruolo a chi è attivo e toglilo a chi smette.
- **`/admin-moduli statistiche ruolo-elimina`** — Elimina una regola dei ruoli per attività.

## Admin: musica

- **`/admin-musica canale-richieste`** — Canale dove si scrive un titolo per metterlo in coda, con il player.
- **`/admin-musica impostazioni`** — Cambia le impostazioni musicali del server.
- **`/admin-musica riepilogo`** — Mostra tutte le impostazioni musicali del server.
- **`/admin-musica suono-ruoli`** — Chi può usare un suono: ruoli consentiti o vietati.

## Admin: negozio avanzato

- **`/admin-negozio evento bonus`** — Lascia in chat un bonus a tempo: il primo che lo prende guadagna di più per un po'.
- **`/admin-negozio evento casuali`** — Accendi o spegni gli eventi casuali del server in un canale.
- **`/admin-negozio evento codice`** — Lancia un codice in chat: chi lo scrive per primo vince le monete.
- **`/admin-negozio evento server`** — Bonus a tempo per tutto il server, subito (lavoro e premio).
- **`/admin-negozio fondo dai`** — Dai a un membro un oggetto donato al fondo premi.
- **`/admin-negozio guadagno crea`** — Crea un comando di guadagno: chi lo usa riceve monete, con una pausa.
- **`/admin-negozio guadagno elimina`** — Elimina un comando di guadagno del server.
- **`/admin-negozio offerta chiudi`** — Chiude subito l'offerta lampo di un oggetto.
- **`/admin-negozio offerta lampo`** — Lancia un'offerta lampo a tempo con il bottone per comprare.
- **`/admin-negozio ricetta crea`** — Crea una ricetta: certi oggetti diventano un altro oggetto.
- **`/admin-negozio ricetta elimina`** — Elimina una ricetta.
- **`/admin-negozio rotazione oggetto`** — Mette un oggetto tra quelli che ruotano (o lo toglie).
- **`/admin-negozio rotazione quanti`** — Quanti oggetti a rotazione sono in vetrina ogni giorno (0 = spenta).

## Admin-rep

- **`/admin-rep azzera`** — Azzera la reputazione di tutto il server (serve la parola di conferma).
- **`/admin-rep cancella`** — Porta a zero la reputazione di un membro.
- **`/admin-rep imposta`** — Fissa i punti reputazione di un membro.
- **`/admin-rep impostazioni`** — Accendi la reputazione e scegli nome, pausa, limiti, ruoli e «grazie».
- **`/admin-rep premio`** — Ruoli dati a una soglia di reputazione (senza soglia: l'elenco).

## Admin: ruoli

- **`/admin-ruoli auto aggiungi`** — Aggiungi un ruolo dato in automatico a chi entra.
- **`/admin-ruoli auto elenco`** — Mostra i ruoli automatici del server.
- **`/admin-ruoli auto ricorda`** — Ridai i ruoli a chi esce e rientra entro un certo tempo.
- **`/admin-ruoli auto ricorda-ruoli`** — Scegli quali ruoli si ridanno a chi rientra e quali mai.
- **`/admin-ruoli auto sincronizza`** — Dai i ruoli automatici anche ai membri già nel server.
- **`/admin-ruoli auto togli`** — Togli un ruolo dato in automatico a chi entra.
- **`/admin-ruoli azzera`** — Togli tutti i ruoli a un membro, con conferma.
- **`/admin-ruoli crea`** — Crea un ruolo nuovo.
- **`/admin-ruoli dai`** — Dai uno o più ruoli a un membro, anche per un tempo.
- **`/admin-ruoli diagnosi`** — Scopri perché il bot non riesce a dare un ruolo.
- **`/admin-ruoli massa`** — Dai o togli un ruolo a molti membri insieme, con filtri.
- **`/admin-ruoli massa-ferma`** — Ferma l'operazione di massa in corso.
- **`/admin-ruoli menu accesso`** — Limita un menu a certi ruoli o escludine altri.
- **`/admin-ruoli menu aggiungi`** — Aggiungi un'opzione a un role menu.
- **`/admin-ruoli menu crea`** — Crea un nuovo role menu.
- **`/admin-ruoli menu elenco`** — Mostra i menu di ruoli del server, con gli ID.
- **`/admin-ruoli menu elimina`** — Elimina un role menu.
- **`/admin-ruoli menu modifica`** — Cambia titolo, descrizione o comportamento di un menu già pubblicato.
- **`/admin-ruoli menu togli`** — Rimuovi un'opzione da un role menu.
- **`/admin-ruoli modifica`** — Cambia nome, colore e opzioni di un ruolo.
- **`/admin-ruoli premio aggiungi`** — Assegna un ruolo a chi raggiunge un livello.
- **`/admin-ruoli premio elenco`** — Mostra i ruoli-premio configurati su questo server.
- **`/admin-ruoli premio togli`** — Rimuove un ruolo-premio configurato.
- **`/admin-ruoli scelta`** — Ruoli che i membri si prendono da soli con /utility ruolo.
- **`/admin-ruoli togli`** — Togli uno o più ruoli a un membro, anche per un tempo.
- **`/admin-ruoli vocale`** — Un ruolo per chi è in un canale vocale.

## Admin: sicurezza

- **`/admin-sicurezza alt elenco`** — Gli account doppi trovati dalla verifica web.
- **`/admin-sicurezza escalation disable`** — Disattiva l'escalation ladder.
- **`/admin-sicurezza escalation enable`** — Attiva l'escalation ladder.
- **`/admin-sicurezza escalation remove-step`** — Rimuove un livello dalla scala personalizzata.
- **`/admin-sicurezza escalation reset`** — Azzera il conteggio infrazioni di un membro.
- **`/admin-sicurezza escalation set-reset-days`** — Giorni di buona condotta per azzerare il conteggio.
- **`/admin-sicurezza escalation set-step`** — Configura l'azione per un livello della scala.
- **`/admin-sicurezza escalation status`** — Mostra la scala di escalation configurata.
- **`/admin-sicurezza globalban controlla`** — Da quanti server della rete questo utente è stato bannato dalla Spam Trap.
- **`/admin-sicurezza globalban disable`** — Abbandona la rete di ban globali.
- **`/admin-sicurezza globalban enable`** — Aderisci alla rete di ban globali (propaga e ricevi).
- **`/admin-sicurezza globalban status`** — Mostra lo stato e la storia recente del ban globale.
- **`/admin-sicurezza heatmap`** — Mostra quali ruoli hanno permessi critici e chi li possiede.
- **`/admin-sicurezza panico attiva`** — Accende il panico: blocco totale con le regole d'emergenza.
- **`/admin-sicurezza panico configura`** — Scelte del panico: ruoli avvisati, categorie escluse, sblocco, regole.
- **`/admin-sicurezza panico stato`** — Mostra se il server e' bloccato e le scelte del panico.
- **`/admin-sicurezza panico togli`** — Spegne il panico e riapre il server com'era.
- **`/admin-sicurezza rete ban`** — Rete facoltativa dei ban: aderisci, scegli proposta o automatico, annulla.
- **`/admin-sicurezza rete impostazioni`** — Rete di protezione: avvisi dagli altri server e timeout di sicurezza.
- **`/admin-sicurezza rete timeout-togli`** — Toglie il timeout messo dalla rete per un account compromesso.
- **`/admin-sicurezza score`** — Calcola il punteggio di sicurezza del server con consigli.
- **`/admin-sicurezza spamtrap`** — Configura i canali trappola e log dello Spam Trap.
- **`/admin-sicurezza verify blacklist-add`** — Aggiungi un utente alla blacklist.
- **`/admin-sicurezza verify blacklist-remove`** — Rimuovi un utente dalla blacklist.
- **`/admin-sicurezza verify invia`** — Rimanda a un membro il messaggio per verificarsi.
- **`/admin-sicurezza verify manuale`** — Verifica a mano un membro, senza controlli.
- **`/admin-sicurezza verify opzioni`** — Ruolo «non verificato» e ruoli extra.
- **`/admin-sicurezza verify panel`** — Pubblica il pannello di verifica.
- **`/admin-sicurezza verify setup`** — Configura il Verify.
- **`/admin-sicurezza verify statistiche`** — Ingressi, uscite, captcha e verifiche.
- **`/admin-sicurezza verify tempi`** — Promemoria, tempo massimo, azione su chi fallisce, verifica solo ai sospetti.
- **`/admin-sicurezza verify tentativi`** — Tentativi di verifica di un utente.
- **`/admin-sicurezza verify whitelist-add`** — Aggiungi un utente alla whitelist.
- **`/admin-sicurezza verify whitelist-remove`** — Rimuovi un utente dalla whitelist.

## Admin: tag e risposte

- **`/admin-tag risposte crea`** — Crea una risposta automatica.
- **`/admin-tag risposte elenco`** — Mostra le risposte automatiche del server.
- **`/admin-tag risposte elimina`** — Elimina una risposta automatica.
- **`/admin-tag risposte escludi`** — Utenti, canali e ruoli che non fanno scattare una risposta (10 per elenco).
- **`/admin-tag risposte globali`** — Accendi o spegni le risposte automatiche dell'owner in questo server.
- **`/admin-tag risposte modifica`** — Cambia risposta, modo o limiti di una risposta automatica.
- **`/admin-tag risposte mostra`** — Dettaglio di una risposta automatica, anche il testo grezzo.
- **`/admin-tag risposte svuota`** — Elimina tutte le risposte automatiche del server.
- **`/admin-tag tag alias`** — Nomi alternativi di un tag (al massimo 3).
- **`/admin-tag tag azioni`** — Azioni sicure di un tag: ruolo, messaggio, reazione (fino a 3).
- **`/admin-tag tag crea`** — Crea un comando personalizzato.
- **`/admin-tag tag creatori`** — Scegli il ruolo di chi può creare tag propri con /tag crea.
- **`/admin-tag tag divieti`** — Vieta un tag a un ruolo, un canale o un utente (al massimo 10 per elenco).
- **`/admin-tag tag elenco`** — Mostra i comandi personalizzati del server.
- **`/admin-tag tag elimina`** — Elimina un comando personalizzato.
- **`/admin-tag tag esporta`** — Esporta i tag del server in un codice o in un file.
- **`/admin-tag tag gruppi`** — Regole per gruppo di tag: un solo canale e/o un ruolo richiesto.
- **`/admin-tag tag importa`** — Importa tag da un codice o da un file JSON.
- **`/admin-tag tag info`** — Scheda di un tag: autore, usi, nomi alternativi e testo grezzo.
- **`/admin-tag tag modifica`** — Cambia un comando personalizzato.
- **`/admin-tag tag opzioni`** — Come si comporta un tag: permesso, bersaglio, dove risponde.
- **`/admin-tag tag prefisso`** — Scegli il prefisso per usare i comandi scrivendo nel canale.
- **`/admin-tag tag risposte`** — Dai a un tag fino a 5 risposte, ognuna con il suo peso.
- **`/admin-tag tag sostituisci`** — Cambia un testo in tutti i tag, dopo l'anteprima.

## Admin: ticket

- **`/admin-ticket categoria aggiungi`** — Aggiungi (o aggiorna) una categoria di ticket.
- **`/admin-ticket categoria elenco`** — Elenca le categorie di ticket configurate.
- **`/admin-ticket categoria togli`** — Rimuovi una categoria di ticket.
- **`/admin-ticket chiudi-tutti`** — Chiudi i ticket aperti (fino a 25 alla volta).
- **`/admin-ticket chiusura-auto`** — Chiudi i ticket fermi da N minuti (0 = spenta).
- **`/admin-ticket etichette aggiungi`** — Crea un'etichetta colorata per i ticket (max 25).
- **`/admin-ticket etichette elenco`** — Elenca le etichette dei ticket.
- **`/admin-ticket etichette togli`** — Togli un'etichetta (sparisce dai ticket che la hanno).
- **`/admin-ticket limite`** — Quanti ticket aperti alla volta può avere ogni utente (predefinito 1).
- **`/admin-ticket lista-nera`** — Utenti e ruoli che non possono aprire ticket.
- **`/admin-ticket log`** — Quali azioni sui ticket finiscono nel log, e in quale canale.
- **`/admin-ticket modmail attiva`** — Accendi o spegni il ModMail (ticket in DM).
- **`/admin-ticket modmail blocca`** — Blocca o sblocca un utente dal ModMail.
- **`/admin-ticket modmail opzioni`** — Opzioni del ModMail: risposte anonime, inoltro, conferma.
- **`/admin-ticket panel`** — Pubblica il pannello per l'apertura dei ticket in questo canale.
- **`/admin-ticket pannelli aspetto`** — Colore del bottone, testo del menu e messaggio di apertura di un pannello.
- **`/admin-ticket pannelli crea`** — Crea un pannello di ticket.
- **`/admin-ticket pannelli duplica`** — Duplica un pannello già configurato, o copia una risposta pronta su un altro pannello.
- **`/admin-ticket pannelli elenco`** — Elenca i pannelli di ticket del server.
- **`/admin-ticket pannelli modello`** — Importa un modello pronto di pannello (modulo, motivi, risposte).
- **`/admin-ticket pannelli modulo-aggiungi`** — Aggiungi una domanda al modulo (max 5).
- **`/admin-ticket pannelli modulo-copia`** — Copia il modulo di un pannello su un altro (sostituisce le sue domande).
- **`/admin-ticket pannelli modulo-mostra`** — Mostra le domande del modulo di un pannello.
- **`/admin-ticket pannelli modulo-togli`** — Togli una domanda dal modulo.
- **`/admin-ticket pannelli motivo-aggiungi`** — Aggiungi un motivo pronto al pannello (max 24).
- **`/admin-ticket pannelli motivo-togli`** — Togli un motivo pronto dal pannello (senza numero: li elenca).
- **`/admin-ticket pannelli pubblica`** — Pubblica qui i bottoni di uno o più pannelli.
- **`/admin-ticket pannelli rimuovi`** — Elimina un pannello e il suo modulo.
- **`/admin-ticket risposte articolo`** — Base di conoscenza: nuovo articolo, correggilo o eliminalo.
- **`/admin-ticket risposte elenco`** — Elenca le risposte standard del server.
- **`/admin-ticket risposte elimina`** — Elimina una risposta standard.
- **`/admin-ticket risposte modifica`** — Correggi una risposta standard.
- **`/admin-ticket risposte standard`** — Risposte standard imparate dallo staff.
- **`/admin-ticket ruolo aggiungi`** — Aggiungi un ruolo di supporto.
- **`/admin-ticket ruolo elenco`** — Elenca i ruoli di supporto configurati.
- **`/admin-ticket ruolo togli`** — Rimuovi un ruolo di supporto.
- **`/admin-ticket setup`** — Configura la categoria (e opzionalmente il ruolo di supporto) per i ticket.
- **`/admin-ticket sollecito`** — Sollecito dopo N minuti senza staff (0 = spento).
- **`/admin-ticket sospendi`** — Sospendi l'apertura dei ticket (senza motivo: riprendi).
- **`/admin-ticket stats`** — Statistiche del sistema di ticket.
- **`/admin-ticket voto`** — Voto a stelle in DM alla chiusura.

## Admin: opzioni dei ticket

- **`/admin-ticket-opzioni accesso`** — Chi può aprire: regole per ruolo, lette dall'alto.
- **`/admin-ticket-opzioni attesa`** — Sposta in una categoria i ticket che aspettano l'utente.
- **`/admin-ticket-opzioni avvisi`** — Chi avvisare all'apertura e primo messaggio fissato.
- **`/admin-ticket-opzioni canale`** — Nome del canale, categorie di riserva e ticket come thread privati.
- **`/admin-ticket-opzioni chiusura`** — Conferma, chiusura in due passi, chiusi, nomi.
- **`/admin-ticket-opzioni limiti`** — Tetto di ticket aperti, pausa e ruoli esenti.
- **`/admin-ticket-opzioni messaggi`** — DM all'utente e testi di presa e rilascio.
- **`/admin-ticket-opzioni mostra`** — Tutte le opzioni di un pannello.
- **`/admin-ticket-opzioni orari`** — Orari di apertura e cosa succede fuori orario.
- **`/admin-ticket-opzioni permessi`** — Permessi dell'utente, osservatori, ruoli durante, squadra.
- **`/admin-ticket-opzioni presa`** — Presa in carico: categoria, esclusiva, assegnazione automatica.
- **`/admin-ticket-opzioni regole`** — Regole: se nessuno scrive da N minuti, chiudi, elimina o scrivi.

## Admin: vocali temporanei

- **`/admin-vocali cap`** — Imposta il numero massimo di vocali temporanei per categoria.
- **`/admin-vocali crea`** — Crea la categoria e il canale generatore e configura tutto in un colpo.
- **`/admin-vocali generatore`** — Altri canali generatori con regole proprie.
- **`/admin-vocali opzioni`** — Nome dei nuovi canali, blocco, registro, copia, pannello.
- **`/admin-vocali panel`** — Pubblica il pannello per la creazione manuale di un vocale.
- **`/admin-vocali piattaforme`** — Configura i ruoli informativi PC/Console/Mobile per i vocali temporanei.
- **`/admin-vocali setup`** — Configura il canale generatore e la categoria dei vocali temporanei.

## Aiuto (primo livello)

- **`/Apri ticket`** — Menu «App» (tasto destro)
- **`/Orari nel mio fuso`** — Menu «App» (tasto destro)
- **`/Richiedi copia sicura`** — Menu «App» (tasto destro)
- **`/Riestrai giveaway`** — Menu «App» (tasto destro)
- **`/Salva citazione`** — Menu «App» (tasto destro)
- **`/Scheda moderazione`** — Menu «App» (tasto destro)
- **`/Segnala messaggio`** — Menu «App» (tasto destro)
- **`/Statistiche del canale`** — Menu «App» (tasto destro)
- **`/Statistiche del membro`** — Menu «App» (tasto destro)
- **`/cerca-comando`** — Cerca un comando per descrizione.
- **`/chiedi`** — Chiedi aiuto: ti mostro i comandi giusti.

## iYokai App (app separata, installata sull'utente)

- **`/Citazione come immagine`** — Menu «App» (tasto destro)
- **`/Controlla i link`** — Menu «App» (tasto destro)
- **`/Meme da questa immagine`** — Menu «App» (tasto destro)
- **`/Profilo`** — Menu «App» (tasto destro)
- **`/Ricordamelo`** — Menu «App» (tasto destro)
- **`/Salva come risposta pronta`** — Menu «App» (tasto destro)
- **`/Salva nei segnalibri`** — Menu «App» (tasto destro)
- **`/Segnala alla rete iYokai`** — Menu «App» (tasto destro)
- **`/Spiega o riassumi`** — Menu «App» (tasto destro)
- **`/Stato rete iYokai`** — Menu «App» (tasto destro)
- **`/Testo pulito`** — Menu «App» (tasto destro)
- **`/Traduci`** — Menu «App» (tasto destro)
- **`/Trascrivi vocale`** — Menu «App» (tasto destro)
- **`/assistente`** — Il tuo assistente personale: chiedi come fare una cosa.
- **`/desktop avvisi`** — Accendi o spegni gli avvisi per menzioni e risposte sul programma.
- **`/desktop collega`** — Crea il codice personale per il programma iYokai Desktop.
- **`/desktop parole`** — Le parole chiave che ti avvisano (separate da virgole; vuoto le toglie).
- **`/desktop scollega`** — Revoca il codice: il programma non entra più.
- **`/desktop stato`** — Come è collegato iYokai Desktop e quali avvisi hai.
- **`/divertimento animale`** — Mostra l'immagine di un animale a caso.
- **`/divertimento barzelletta`** — Racconta una barzelletta a caso.
- **`/divertimento casuale`** — Preferiresti, argomento, consiglio, oggetto magico.
- **`/divertimento citazione`** — Mostra una citazione a caso.
- **`/divertimento curiosita`** — Mostra una curiosità a caso.
- **`/divertimento dado`** — Tira un dado, o una formula come 3d6+2.
- **`/divertimento effetto`** — Effetto sull'avatar: arcobaleno, R.I.P., ricercato, triggered.
- **`/divertimento forbici`** — Carta, forbici, sasso contro il bot.
- **`/divertimento immagine`** — Cerca un'immagine adatta a tutti su Pixabay.
- **`/divertimento meme`** — Un meme con testo sopra e sotto, su un'immagine o su un avatar.
- **`/divertimento moneta`** — Lancia una moneta: testa o croce.
- **`/divertimento numero`** — Un numero a caso in un intervallo.
- **`/divertimento palla8`** — Fai una domanda alla palla magica 8.
- **`/divertimento scegli`** — Scelgo a caso tra le opzioni che scrivi.
- **`/divertimento ship`** — Calcola la compatibilità tra due utenti.
- **`/divertimento testo`** — Scrivi un testo in uno stile speciale.
- **`/divertimento valuta`** — Valuta qualcosa da 0 a 10.
- **`/impostazioni dm`** — L'app può scriverti in DM (promemoria, ricordamelo)?
- **`/impostazioni lingua`** — Italiano o inglese per le risposte che vedi solo tu.
- **`/impostazioni mostra`** — Le tue impostazioni di adesso.
- **`/impostazioni profilo`** — Gli altri vedono il tuo profilo globale (livello, clan, medaglie).
- **`/impostazioni risposte`** — Le risposte dei comandi le vedi solo tu, o le vedono tutti.
- **`/impostazioni storico`** — Salvare i tuoi ultimi comandi (spegnere cancella lo storico).
- **`/note aggiungi`** — Aggiunge una nota, o una voce a una lista.
- **`/note elenco`** — Mostra le tue note, o una lista.
- **`/note rimuovi`** — Toglie una nota o una voce di lista.
- **`/playlist aggiungi`** — Aggiunge un brano a una tua playlist.
- **`/playlist crea`** — Crea una playlist vuota.
- **`/playlist elenco`** — Le tue playlist.
- **`/playlist elimina`** — Elimina una tua playlist.
- **`/playlist mostra`** — Mostra i brani di una tua playlist.
- **`/playlist togli`** — Toglie un brano da una tua playlist.
- **`/profilo`** — La scheda di un utente; il tuo profilo globale e la rank card.
- **`/promemoria annulla`** — Annulla un tuo promemoria.
- **`/promemoria crea`** — Ti scrivo in DM tra il tempo che scegli.
- **`/promemoria elenco`** — Mostra i tuoi promemoria in sospeso.
- **`/radio ora`** — Cosa suona adesso nella radio iYokai, con il link per cercare il testo.
- **`/risposta elenco`** — Le tue risposte pronte.
- **`/risposta rimuovi`** — Toglie una risposta pronta.
- **`/risposta salva`** — Salva una risposta pronta (testo, o embed con titolo, colore e immagine).
- **`/risposta usa`** — Scrive una tua risposta pronta come risposta dell'app.
- **`/segnalibri elenco`** — Mostra i tuoi segnalibri, i più recenti prima.
- **`/segnalibri rimuovi`** — Toglie un segnalibro.
- **`/storico azzera`** — Cancella il tuo storico dei comandi.
- **`/storico elenco`** — I tuoi ultimi comandi.
- **`/strumenti calcola`** — Calcola un'espressione, es. (2+3)*4 o sqrt(16).
- **`/strumenti colore`** — Mostra un colore in HEX, RGB e HSL.
- **`/strumenti converti`** — Converte lunghezze, pesi, volumi, velocità, dati e temperature.
- **`/strumenti fuso`** — Che ora è in un altro fuso orario.
- **`/strumenti qr`** — Crea un codice QR da un testo o un link.
- **`/supporto apri`** — Apri una richiesta di assistenza con lo staff di iYokai.
- **`/supporto elenco`** — Le tue ultime richieste di assistenza.
- **`/supporto rispondi`** — Scrivi allo staff nella tua richiesta aperta.
- **`/trova`** — Cerca una funzione di iYokai App: comandi e menu sul messaggio.

## iYokai NSFW (app separata, solo canali vietati ai minori)

- **`/nsfw cerca`** — Pubblica qui un contenuto con un tag permesso dal server.
- **`/nsfw-admin attiva`** — Accende o spegne l'istanza NSFW in questo server.
- **`/nsfw-admin autopost`** — Pubblica da solo in un canale vietato ai minori.
- **`/nsfw-admin autopost-ferma`** — Ferma la pubblicazione automatica (vuoto: tutte).
- **`/nsfw-admin stato`** — Mostra le impostazioni NSFW del server.
- **`/nsfw-admin tag-aggiungi`** — Aggiunge un tag alla lista permessa del server.
- **`/nsfw-admin tag-togli`** — Toglie un tag dalla lista permessa del server.

## Assistente AI

- **`/assistente avviso`** — Segui fino a 3 parole: ti avviso quando se ne parla molto.
- **`/assistente crea-personaggio`** — Crea un personaggio AI con cui chattare.
- **`/assistente frammenti`** — I frammenti di lore che hai raccolto.
- **`/assistente immagina`** — Genera un'immagine da una descrizione.
- **`/assistente ingrandisci`** — Ingrandisce e ripulisce un'immagine che carichi.
- **`/assistente lore`** — Scheda di lore su un nome, un luogo o uno yokai.
- **`/assistente mistero`** — Rispondi a un mistero del server con il codice.
- **`/assistente pacchetto`** — Compra 5 immagini AI in più con le monete del server.
- **`/assistente parla`** — Yokai dice una frase a voce in questo canale.
- **`/assistente personaggio`** — Parla con un personaggio AI del server.
- **`/assistente preferenza`** — Le tue scelte sull'AI: risposte per te e stile imitabile dagli altri.
- **`/assistente riassumi`** — Riassunto degli ultimi messaggi di un canale.
- **`/assistente scrivi`** — Scrive un testo che chiedi: una poesia, una spiegazione, una risposta.
- **`/assistente spiega`** — Spiega in parole semplici un messaggio (dal suo link).
- **`/assistente spirito`** — Il tuo spirito Yokai: cresce con la tua attività.
- **`/assistente stile`** — Un messaggio nuovo scritto come scrivi tu (o come chi lo permette).
- **`/assistente traduci`** — Traduce un testo nella lingua che scegli.

## Auto

- **`/auto catalogo`** — Le auto da collezione che puoi comprare.
- **`/auto compra`** — Compra un'auto da collezione per il tuo garage.
- **`/auto foto`** — Metti la foto della tua auto (solo l'immagine ricodificata si conserva).
- **`/auto foto-togli`** — Toglie la foto di una tua auto.
- **`/auto gara`** — Gara con una tua auto contro il banco o contro un membro, anche con una puntata.
- **`/auto garage`** — Le auto del tuo garage (o di un altro membro).
- **`/auto potenzia`** — Potenzia una parte della tua auto con le monete.
- **`/auto vedi`** — La scheda di un'auto del garage, con la sua foto.

## Clan

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

## Eventi

- **`/eventi annulla`** — Annulla un evento: gli iscritti non possono più cambiare.
- **`/eventi crea`** — Crea un evento con iscrizioni, posti e promemoria.
- **`/eventi elenco`** — I prossimi eventi, o gli iscritti di un evento.
- **`/eventi modifica`** — Cambia titolo, data, posti o descrizione di un evento.

## Founder (proprietario del server)

- **`/founder backup automatico`** — Copie automatiche della struttura a intervalli.
- **`/founder backup permessi`** — Chi può creare e chi può caricare i backup (solo l'owner).
- **`/founder backup sincronia`** — Tieni uguali ban e ruoli con un altro tuo server.
- **`/founder backup sincronia-canali`** — Copia i messaggi tra due canali tuoi, in una o in due direzioni.
- **`/founder moderazione immuni`** — Ruoli che la moderazione manuale non tocca (solo il proprietario).

## Divertimento

- **`/fun 8ball`** — Fai una domanda alla palla magica 8.
- **`/fun animali abbandona`** — Lascia un tuo animale nella coda di adozione del server.
- **`/fun animali adotta`** — Adotta un animale della coda (serve un posto libero).
- **`/fun animali adozioni`** — Gli animali in attesa di una famiglia.
- **`/fun animali attivita`** — Un'attività con un tuo animale in salute: ti porta qualche moneta (ogni 2 ore).
- **`/fun animali compra`** — Compra un animale da accudire.
- **`/fun animali cura`** — Dai da mangiare, pulisci o gioca con un animale (una volta all'ora per tipo).
- **`/fun animali incontro`** — Fai incontrare due animali: giocano insieme e può nascere un cucciolo.
- **`/fun animali lista`** — I tuoi animali: fame, pulizia, gioco e livello.
- **`/fun animali lotta`** — Fai lottare il tuo animale con quello di un altro membro (senza puntata).
- **`/fun animali posto`** — Compra un posto in più per un altro animale (massimo 2 in più).
- **`/fun animali sitter`** — Paga un pet sitter: i bisogni dell'animale restano pieni per i giorni scelti.
- **`/fun casuale`** — Preferiresti, argomento, consiglio, oggetto magico, classe.
- **`/fun citazioni aggiungi`** — Salva una citazione del server.
- **`/fun citazioni caso`** — Mostra una citazione a caso: del server o tra quelle famose.
- **`/fun citazioni cerca`** — Cerca una parola tra le citazioni del server.
- **`/fun citazioni elimina`** — Elimina una citazione che hai salvato tu.
- **`/fun coinflip`** — Lancia una moneta: testa o croce.
- **`/fun dice`** — Tira un dado.
- **`/fun fact`** — Mostra una curiosità a caso.
- **`/fun indovina-canzone`** — Indovina la canzone da un breve estratto, in vocale.
- **`/fun joke`** — Racconta una barzelletta a caso.
- **`/fun misura`** — Misura da 0 a 100% quanto c'è di una cosa a tua scelta.
- **`/fun numero`** — Un numero a caso in un intervallo.
- **`/fun pesca abilita`** — Le abilità di pesca: si sbloccano con i punti delle sfide.
- **`/fun pesca acquario`** — Il tuo acquario: le specie trovate e quanti ne hai.
- **`/fun pesca attrezzi`** — Il negozio di attrezzi: si pagano con le perle che trovi pescando.
- **`/fun pesca classifica`** — I migliori pescatori di oggi.
- **`/fun pesca guida`** — Il tuo deposito di pesci e le specie che hai già trovato.
- **`/fun pesca lancia`** — Getta la lenza in un luogo (ogni 15 minuti).
- **`/fun pesca rete`** — Raccogli i pesci che la tua rete ha preso mentre eri via (un lancio all'ora).
- **`/fun pesca stagione`** — Il pass del mese: ogni 100 punti di pesca un premio (traccia gratuita).
- **`/fun pesca storico`** — Gli ultimi pesci presi e le ultime vendite (30 giorni).
- **`/fun pesca vendi`** — Vendi tutti i pesci del deposito.
- **`/fun rate`** — Valuta qualcosa da 0 a 10.
- **`/fun scegli`** — Scelgo a caso tra le opzioni che scrivi.
- **`/fun scherzo`** — Uno scherzo innocuo verso un utente.
- **`/fun ship`** — Calcola la compatibilità tra due utenti.
- **`/fun telefono chiama`** — Chiama un altro server a caso (spento di base).
- **`/fun telefono riaggancia`** — Chiudi la chiamata in corso.
- **`/fun telefono segnala`** — Segnala la chiamata, blocca l'altro server e riaggancia.
- **`/fun testo`** — Scrivi un testo in uno stile speciale.

## Gif

- **`/gif azione`** — Una GIF di azione verso un utente: abbraccio, bacio, schiaffo...
- **`/gif cerca`** — Cerca una GIF con le parole (spento di base: serve una chiave del bot).
- **`/gif privacy`** — Scegli chi può farti le azioni con le GIF.
- **`/gif reazione`** — Una GIF di reazione: piangi, balli, ridi...

## Giochi

- **`/giochi acronimi`** — Inventa frasi che seguono le lettere date e vota la migliore.
- **`/giochi battitura`** — Gara di battitura: copia il testo mostrato nell'immagine.
- **`/giochi carta`** — Indovina la carta estratta: colore, seme o valore.
- **`/giochi carte avvia`** — Gioco di carte: completa la frase con la carta più divertente.
- **`/giochi conteggio avvisami`** — Ti avviso nel canale quando il conteggio arriva a un numero.
- **`/giochi conteggio classifica`** — Chi ha contato più numeri giusti.
- **`/giochi dado`** — Un tiro al giorno da 1 a 100 e la classifica del server.
- **`/giochi gioca`** — Gioca le tue coin: monetina, dadi o slot.
- **`/giochi mazzo`** — Un mazzo di 52 carte per il server: pesca, rimescola, controlla.
- **`/giochi minato`** — Campo minato: tocca gli spoiler ed evita le mine.
- **`/giochi quiz avvia`** — Avvia un quiz a domande nel canale.
- **`/giochi quiz classifica`** — Classifica del quiz: questa settimana o di sempre.
- **`/giochi record`** — Le 10 vincite più grosse del server.
- **`/giochi roulette`** — Roulette: colore, pari, dozzina, colonna o numero.
- **`/giochi rps`** — Carta, forbici, sasso contro il bot.
- **`/giochi scala`** — Scala fortunata: più sali, più rende.
- **`/giochi sfide alto-basso`** — Più alta o più bassa? Il premio cresce a ogni risposta giusta.
- **`/giochi sfide battaglia`** — Battaglia a turni contro un membro: attacco, difesa e abilità, anche con una puntata.
- **`/giochi sfide battaglie`** — Le battaglie vinte e perse di un membro e i migliori del server.
- **`/giochi sfide blackjack`** — Blackjack contro il banco: carta, stai, raddoppia, arrenditi.
- **`/giochi sfide duelli`** — Classifica dei duelli e i tuoi ultimi.
- **`/giochi sfide duello`** — Sfida un membro a duello: chi vince prende la posta.
- **`/giochi sfide forza4`** — Forza 4 contro un membro, anche con una puntata.
- **`/giochi sfide torre`** — Sali la torre: ogni piano rende di più, ma può crollare.
- **`/giochi sfide tris`** — Tris contro un membro, anche con una puntata.
- **`/giochi smash`** — Smash or pass: un personaggio adulto di AniList (solo canali con limite d'età).
- **`/giochi spinner`** — Fai girare lo spinner: vince chi lo fa girare più a lungo.
- **`/giochi statistiche`** — Le tue partite, vincite e perdite per gioco.

## Immagini

- **`/immagini animal`** — Mostra immagini casuali di animali (fino a 5).
- **`/immagini blur`** — Applica una sfocatura a un'immagine.
- **`/immagini effetto`** — Effetto sull'avatar: arcobaleno, R.I.P., ricercato, pingato, sepia, neon...
- **`/immagini foto`** — Una foto bella da vedere: cibo o buonumore.
- **`/immagini fusione`** — Due Pokémon: il nome fuso e le loro immagini ufficiali affiancate.
- **`/immagini grayscale`** — Trasforma un'immagine in scala di grigi.
- **`/immagini invert`** — Inverte i colori di un'immagine.
- **`/immagini meme`** — Genera un meme con testo sopra/sotto.
- **`/immagini pixelate`** — Pixela un'immagine.
- **`/immagini post`** — Un'immagine da una comunità Lemmy (spento di base: lo accende l'admin).
- **`/immagini search-image`** — Cerca un'immagine SFW su Pixabay.
- **`/immagini xkcd`** — Una vignetta di xkcd: l'ultima o quella col numero che scegli.

## Livelli

- **`/level calcola`** — Quanti messaggi o minuti in vocale mancano per arrivare a un livello.
- **`/level collezione compra`** — Compra un badge o uno sfondo con le tue coin.
- **`/level collezione equipaggia`** — Metti un badge o uno sfondo sul tuo profilo (senza oggetto lo togli).
- **`/level collezione negozio`** — Mostra badge e sfondi in vendita e quelli che hai.
- **`/level compleanno imposta`** — Registra il tuo compleanno (solo giorno e mese).
- **`/level compleanno mostra`** — Mostra il tuo compleanno o quello di un membro.
- **`/level compleanno prossimi`** — I prossimi compleanni del server.
- **`/level compleanno rimuovi`** — Cancella il tuo compleanno.
- **`/level inviti classifica`** — I 10 membri che hanno invitato più persone.
- **`/level inviti codici`** — I tuoi codici d'invito, a pagine da 10.
- **`/level inviti link`** — Il tuo link d'invito personale, che passa dal sito del bot.
- **`/level inviti storico`** — Chi ha invitato un membro e le ultime persone che ha portato.
- **`/level inviti utente`** — Quante persone ha invitato un membro.
- **`/level leaderboard`** — Mostra la classifica del server.
- **`/level livelli-recenti`** — Gli ultimi 25 level-up del server.
- **`/level movimenti`** — Gli ultimi movimenti delle tue monete (si tengono 30 giorni).
- **`/level premi`** — Mostra i ruoli-premio dei livelli e i moltiplicatori di XP attivi.
- **`/level profilo`** — Mostra il profilo di un membro; con «presentazione» cambi il tuo.
- **`/level progressi`** — Missioni, serie, traguardi e pass di 90 giorni, in un menu.
- **`/level rank`** — Mostra la rank card: livello, XP, posizione e coin.
- **`/level righe`** — Scegli quali righe mostrare nel tuo riepilogo e in che ordine.
- **`/level sociale amici`** — I tuoi amici, e togline uno.
- **`/level sociale amico`** — Chiedi a un membro di diventare tuo amico (tra amici i pagamenti non hanno tassa).
- **`/level sociale azzera-dati`** — Cancella i tuoi dati di gioco in questo server (monete, animali, pesci...).
- **`/level sociale blocca`** — Blocca un utente: niente richieste, regali, pagamenti o sfide da lui.
- **`/level sociale divorzia`** — Chiudi il tuo matrimonio.
- **`/level sociale mantieni`** — Mantieni vivo il tuo matrimonio (vale 14 giorni).
- **`/level sociale sblocca`** — Togli un utente dai bloccati (senza nome: l'elenco dei bloccati).
- **`/level sociale sposa`** — Proponi il matrimonio (200 monete a testa alla cassa); va mantenuto.
- **`/level stelle caso`** — Un messaggio a caso dalla bacheca.
- **`/level stelle classifica`** — Chi ha ricevuto più stelle in bacheca.

## Mercato

- **`/mercato accetta`** — Accetta l'offerta di un membro sul tuo annuncio (senza membro: vedi le offerte).
- **`/mercato compra`** — Compra un annuncio al prezzo indicato.
- **`/mercato dona`** — Dona monete o un oggetto al fondo premi del server.
- **`/mercato elenco`** — Gli annunci del mercato (anche solo di un membro).
- **`/mercato fondo`** — Gli oggetti donati al fondo premi del server.
- **`/mercato offri`** — Fai un'offerta più bassa: le monete restano in custodia finché non risponde.
- **`/mercato ritira`** — Ritira un tuo annuncio (o una tua offerta): oggetto e monete tornano a chi spettano.
- **`/mercato vendi`** — Metti un tuo oggetto in vendita agli altri membri.

## Mod: ban

- **`/mod-ban appelli canale`** — Sceglie il canale staff per gli appelli (vuoto per spegnerli).
- **`/mod-ban appelli elenco`** — Mostra gli ultimi appelli del server.
- **`/mod-ban appelli timeout`** — Accende o spegne gli appelli anche per i timeout.
- **`/mod-ban ban`** — Banna permanentemente un membro.
- **`/mod-ban cerca`** — Cerca tra i ban del server per nome, ID o motivo.
- **`/mod-ban kick`** — Espelle un membro dal server.
- **`/mod-ban massa ban`** — Banna più utenti insieme, anche fuori dal server (ID o menzioni).
- **`/mod-ban massa entrati`** — Banna o espelle chi è entrato negli ultimi minuti (dopo una conferma).
- **`/mod-ban massa invito`** — Banna o espelle chi è entrato con un certo invito (dopo una conferma).
- **`/mod-ban massa kick`** — Espelle più membri insieme (ID o menzioni).
- **`/mod-ban massa unban`** — Toglie il ban a più utenti insieme (ID).
- **`/mod-ban softban`** — Banna e sbanna subito un membro, per cancellarne i messaggi recenti.
- **`/mod-ban tempban`** — Banna un membro per una durata definita.
- **`/mod-ban unban`** — Rimuove il ban da un utente.

## Mod: canali

- **`/mod-canali blocco attiva`** — Blocca tutti i canali, gli inviti e gli ingressi del server.
- **`/mod-canali blocco canali`** — Blocca solo alcuni canali (scelti da un menu) o il gruppo salvato.
- **`/mod-canali blocco stato`** — Mostra se c'e' un blocco attivo, da quando e quando finisce.
- **`/mod-canali blocco togli`** — Riapre il server com'era prima del blocco.
- **`/mod-canali clear`** — Cancella un numero di messaggi, con filtri opzionali.
- **`/mod-canali esporta-chat`** — Manda in un file di testo gli ultimi messaggi di un canale (solo a te).
- **`/mod-canali espressione`** — Aggiungi un'emoji o uno sticker al server da un file o da un'emoji.
- **`/mod-canali lock`** — Blocca la possibilità di scrivere in un canale.
- **`/mod-canali reazioni`** — Toglie le reazioni dagli ultimi messaggi di un canale, senza cancellarli.
- **`/mod-canali slowmode`** — Slowmode di un canale o di una categoria. Senza valori: mostra i canali con slowmode.
- **`/mod-canali thread`** — Crea, archivia o elimina un thread.
- **`/mod-canali unlock`** — Sblocca la possibilità di scrivere in un canale.
- **`/mod-canali vocale dove`** — Mostra in quale vocale è un membro, e chiedi un avviso quando entra.
- **`/mod-canali vocale muta`** — Silenzia o riattiva il microfono di un membro in vocale.
- **`/mod-canali vocale scollega`** — Scollega un membro dal vocale.
- **`/mod-canali vocale sordina`** — Sordina o riattiva l'audio di un membro in vocale.
- **`/mod-canali vocale sposta`** — Sposta un membro in un altro vocale.
- **`/mod-canali vocale sposta-tutti`** — Sposta tutti i membri di un vocale in un altro.

## Mod: casi e note

- **`/mod-casi avvisi azzera`** — Toglie tutti i warn attivi di un membro (serve «Gestire il server»).
- **`/mod-casi avvisi azzera-tutti`** — Toglie i warn attivi di tutto il server (serve «Gestire il server»).
- **`/mod-casi avvisi classifica`** — I membri con più warn attivi.
- **`/mod-casi avvisi elenco`** — Tutti i warn attivi del server, a pagine.
- **`/mod-casi avvisi togli`** — Toglie un singolo warn (per numero di caso).
- **`/mod-casi carico`** — Carico dello staff e turni proposti. Solo amministratori, mai pubblico.
- **`/mod-casi caso attive`** — Sanzioni ancora in corso: tempban, timeout, mute, lock a tempo.
- **`/mod-casi caso chat`** — Manda il registro degli ultimi messaggi del canale salvato con un caso.
- **`/mod-casi caso classifica-staff`** — Classifica dei moderatori per numero di azioni, o casi di uno solo.
- **`/mod-casi caso durata`** — Cambia la durata di un tempban, di un timeout o di un mute ancora in corso.
- **`/mod-casi caso elimina`** — Elimina un caso (serve «Gestire il server»).
- **`/mod-casi caso esporta`** — Manda in un file di testo i casi e le note di un membro.
- **`/mod-casi caso motivo`** — Cambia il motivo di un caso già registrato.
- **`/mod-casi caso nascondi`** — Nasconde un caso (non conta in classifiche e avvisi) o lo riattiva.
- **`/mod-casi caso prova`** — Allega una prova (immagine, PDF o TXT) a un caso; senza file mostra quelle già allegate.
- **`/mod-casi caso registra`** — Registra un caso senza eseguire l'azione (sanzione data fuori dal bot).
- **`/mod-casi caso storico`** — Mostra lo storico casi di un membro.
- **`/mod-casi caso vedi`** — Mostra i dettagli di un singolo caso.
- **`/mod-casi invito`** — Mostra cosa c'è dietro un invito: server, canale, chi l'ha creato.
- **`/mod-casi membri`** — Cerca tra i membri del server con dei filtri.
- **`/mod-casi motivi aggiungi`** — Aggiunge un motivo pronto, da richiamare nel campo «motivo» (serve «Gestire il server»).
- **`/mod-casi motivi elenco`** — Mostra i motivi pronti del server.
- **`/mod-casi motivi modifica`** — Cambia testo, severità o sanzione di un motivo pronto (serve «Gestire il server»).
- **`/mod-casi motivi togli`** — Toglie un motivo pronto (serve «Gestire il server»).
- **`/mod-casi nomi`** — Mostra i nomi e i soprannomi che un membro ha avuto.
- **`/mod-casi nota aggiungi`** — Aggiunge una nota su un utente.
- **`/mod-casi nota elenca`** — Elenca le note su un utente.
- **`/mod-casi nota modifica`** — Cambia il testo di una nota.
- **`/mod-casi nota rimuovi`** — Toglie una nota (il numero è nell'elenco delle note).
- **`/mod-casi nota svuota`** — Cancella tutte le note di un membro (serve «Gestire il server»).
- **`/mod-casi rischio`** — Punteggio di rischio di un membro, con i motivi. Solo un aiuto per decidere.
- **`/mod-casi scheda`** — La scheda di un utente: date, casi, note e rischio (anche fuori dal server).

## Mod: sanzioni

- **`/mod-sanzioni applica`** — Dà la sanzione di un motivo pronto, che puoi cambiare prima di confermare.
- **`/mod-sanzioni libera`** — Toglie la quarantena a un membro e gli ridà i ruoli di prima.
- **`/mod-sanzioni massa timeout`** — Mette in timeout più membri insieme (max 28 giorni).
- **`/mod-sanzioni massa warn`** — Assegna un warn a più membri insieme.
- **`/mod-sanzioni mute`** — Silenzia un membro con un ruolo dedicato (alternativa al timeout).
- **`/mod-sanzioni nick`** — Cambia o azzera il soprannome di un membro.
- **`/mod-sanzioni opzioni aspetto`** — Sceglie colore e icona di un tipo di caso nel log di moderazione.
- **`/mod-sanzioni opzioni avvisi`** — Scrive l'avviso delle sanzioni in un canale invece che nel messaggio privato.
- **`/mod-sanzioni opzioni azioni`** — Dà a un ruolo il permesso di una sola azione di moderazione (o lo toglie).
- **`/mod-sanzioni opzioni dm`** — Sceglie se l'utente riceve un DM per un tipo di azione.
- **`/mod-sanzioni opzioni imposta`** — Messaggi al ban, timeout, casi esterni, avvisi. Vuoto: mostra le opzioni.
- **`/mod-sanzioni opzioni memoria`** — Accende lo storico dei nomi e il soprannome e il mute vocale ridati a chi rientra.
- **`/mod-sanzioni opzioni muto`** — Sceglie o crea il ruolo del mute e rimette il blocco su tutti i canali.
- **`/mod-sanzioni quarantena`** — Toglie i ruoli a un membro e gli dà il ruolo di quarantena (anche a tempo).
- **`/mod-sanzioni timeout`** — Mette in timeout un membro (max 28 giorni).
- **`/mod-sanzioni unmute`** — Rimuove il ruolo mute da un membro.
- **`/mod-sanzioni untimeout`** — Rimuove il timeout da un membro.
- **`/mod-sanzioni warn`** — Assegna un warn a un membro.

## Il tuo mondo

- **`/mondo autovendita`** — Vendi un oggetto da solo quando il cambio del giorno arriva alla soglia.
- **`/mondo avventura`** — Una storia a scelte: il finale dà monete (una volta ogni 6 ore).
- **`/mondo borsa ordine`** — Un ordine automatico: compra o vendi quando il prezzo arriva alla soglia.
- **`/mondo borsa ordini`** — I tuoi ordini automatici (con un numero lo annulli).
- **`/mondo borsa prezzi`** — I prezzi della borsa finta e i tuoi titoli.
- **`/mondo borsa scambia`** — Compra o vendi titoli della borsa finta al prezzo di adesso.
- **`/mondo casa`** — La tua casa: arredala con i gettoni (la moneta di tutti i server).
- **`/mondo diretta`** — La tua diretta di oggi: più giorni di fila, più monete.
- **`/mondo fattoria`** — Pianta nel tuo orto e raccogli quando è maturo (3 posti).
- **`/mondo personaggio`** — Parla con un personaggio: una domanda al giorno, un regalo se rispondi bene.
- **`/mondo vacanza`** — Ferma la serie del premio giornaliero mentre sei via.

## Monete

- **`/monete attese`** — Quando potrai di nuovo usare daily e work.
- **`/monete balance`** — Mostra i tuoi coin.
- **`/monete cassa`** — Mostra il saldo della cassa del server.
- **`/monete conto banca`** — La tua banca: vedi, deposita o preleva (i furti toccano solo i contanti).
- **`/monete conto deposito`** — Blocca monete della banca per 7 giorni e ricevi il 10% in più (ECO-005).
- **`/monete conto dimettiti`** — Lascia il lavoro e ricomincia da stagista.
- **`/monete conto guadagni`** — Come si guadagnano monete in questo server.
- **`/monete conto lavoro`** — Il tuo lavoro attuale e quanto manca alla promozione.
- **`/monete conto lotteria`** — Compra biglietti della lotteria di oggi o guarda le ultime estrazioni.
- **`/monete conto portafoglio`** — Il tuo saldo come immagine.
- **`/monete conto potenzia`** — Potenzia il lavoro o il premio periodico: più livelli, più monete.
- **`/monete conto prestigio`** — Ricomincia da capo per un bonus permanente (+5% a lavoro e premio per livello).
- **`/monete conto rimborso`** — Riscuoti una parte delle tue perdite nei giochi, se il server la rimborsa.
- **`/monete conto voto`** — Riscatta il premio per aver votato il bot, o scegli il riscatto automatico.
- **`/monete daily`** — Riscuoti la ricompensa giornaliera.
- **`/monete inventario`** — Gli oggetti che hai comprato.
- **`/monete lascia`** — Lascia delle monete in questo canale: le prende chi arriva prima.
- **`/monete mensile`** — Riscuoti il premio del mese.
- **`/monete oggetto`** — La scheda di un oggetto del negozio.
- **`/monete pay`** — Trasferisci coin a un altro utente.
- **`/monete regala`** — Regala un oggetto del tuo inventario a un altro membro.
- **`/monete rischio avventura`** — Un'uscita a rischio più prudente: paga meno, riesce più spesso.
- **`/monete rischio bersaglio`** — Un bersaglio compare dopo qualche secondo: clicca in tempo.
- **`/monete rischio cerca`** — Cerca monete in un luogo a scelta.
- **`/monete rischio coccole`** — Coccola il bot: ti lascia qualche moneta.
- **`/monete rischio colpo`** — Un colpo rischioso: paga alta se va bene, multa se va male.
- **`/monete rischio elemosina`** — Chiedi l'elemosina: una piccola cifra, a volte niente.
- **`/monete rischio furto`** — Prova a rubare dei contanti a un membro (solo se il server lo permette).
- **`/monete rischio gratta`** — Gratta e vinci: un biglietto da 20 monete, scegli una casella.
- **`/monete rischio guadagna`** — Usa un comando di guadagno creato dal server (senza nome: l'elenco).
- **`/monete rischio meme`** — Pubblica un meme: il tipo che scegli cambia rischio e premio.
- **`/monete rischio scava`** — Scava in cerca di monete (a volte un tesoro).
- **`/monete rischio scrigno`** — Apri uno scrigno a sorpresa per 100 monete.
- **`/monete riscuoti`** — Riscuoti lo stipendio dei tuoi ruoli (e paga le tasse).
- **`/monete settimanale`** — Riscuoti il premio della settimana.
- **`/monete shop buy`** — Acquista un oggetto dello shop.
- **`/monete shop crea`** — Crea un oggetto da altri oggetti con una ricetta.
- **`/monete shop list`** — Mostra gli oggetti disponibili nello shop.
- **`/monete shop ricette`** — Le ricette del server: cosa si crea con cosa.
- **`/monete usa`** — Usa un oggetto del tuo inventario.
- **`/monete vendi`** — Rivendi un oggetto per metà del suo prezzo.
- **`/monete work`** — Lavora per guadagnare qualche coin.

## Musica

- **`/music brano cerca`** — Cerca un brano e scegli tra 10 risultati.
- **`/music brano karaoke`** — Mostra le righe del brano mentre suona, a tempo.
- **`/music brano ricomincia`** — Rifà partire da capo il brano in corso.
- **`/music brano testo`** — Mostra il testo del brano in corso.
- **`/music brano vai-a`** — Va a un punto del brano: 1:30, +0:30 avanti, -0:15 indietro.
- **`/music clear-queue`** — Svuota la coda, senza toccare la traccia in riproduzione.
- **`/music coda anteprime`** — Mette in coda i brani in anteprima dell'owner del bot.
- **`/music coda cerca`** — Cerca un brano nella coda per titolo.
- **`/music coda cima`** — Porta un brano della coda in cima, subito dopo quello in corso.
- **`/music coda miei`** — Toglie dalla coda tutti i tuoi brani.
- **`/music coda pulisci`** — Toglie dalla coda i brani di chi non e' piu' nel canale vocale.
- **`/music coda ripristina`** — Rimette in coda i brani salvati del tuo canale vocale (dopo un riavvio).
- **`/music coda salta`** — Toglie dalla coda un intervallo di posizioni e/o i brani di un utente.
- **`/music coda sposta`** — Sposta un brano della coda in un'altra posizione.
- **`/music coda subito`** — Fa partire subito un brano della coda, saltando quello in corso.
- **`/music coda togli`** — Toglie un brano dalla coda.
- **`/music coda ultimo`** — Toglie l'ultimo brano che hai messo in coda.
- **`/music disconnect`** — Disconnette il music bot dal canale vocale.
- **`/music genere`** — Scegli una playlist per genere dal menu.
- **`/music history`** — Mostra gli ultimi brani già suonati.
- **`/music join`** — Fa entrare il music bot nel tuo canale, senza suonare.
- **`/music loop queue`** — Attiva/disattiva la ripetizione dell'intera coda.
- **`/music loop track`** — Attiva/disattiva la ripetizione della traccia corrente.
- **`/music nonstop off`** — Disattiva il loop continuo.
- **`/music nonstop on`** — Attiva il loop continuo sulla coda attuale.
- **`/music nowplaying`** — Mostra la traccia in riproduzione con una barra di avanzamento.
- **`/music pause`** — Mette in pausa la riproduzione.
- **`/music play`** — Riproduce una canzone o playlist.
- **`/music playlist aggiorna`** — Rilegge il link da cui hai salvato una playlist.
- **`/music playlist aggiungi`** — Aggiunge un brano (o un link) a una tua playlist.
- **`/music playlist carica`** — Mette in coda una tua playlist salvata.
- **`/music playlist collabora`** — Chi può modificare una tua playlist.
- **`/music playlist condividi`** — Crea un codice per condividere una tua playlist.
- **`/music playlist crea`** — Crea una playlist vuota.
- **`/music playlist elenco`** — Le tue playlist salvate, o i brani di una.
- **`/music playlist elimina`** — Cancella una tua playlist salvata.
- **`/music playlist esporta`** — Scarica una tua playlist come file.
- **`/music playlist importa`** — Salva una playlist da un file esportato.
- **`/music playlist ricevi`** — Salva una copia di una playlist condivisa con un codice.
- **`/music playlist rinomina`** — Cambia il nome di una tua playlist.
- **`/music playlist salva`** — Salva la coda del tuo canale come playlist.
- **`/music playlist server-carica`** — Mette in coda una playlist del server.
- **`/music playlist server-elenco`** — Le playlist del server.
- **`/music playlist server-elimina`** — Cancella una playlist del server.
- **`/music playlist server-salva`** — Salva la coda come playlist del server.
- **`/music playlist togli`** — Toglie un brano da una tua playlist.
- **`/music previous`** — Torna al brano precedente.
- **`/music queue`** — Mostra la coda di riproduzione.
- **`/music radio`** — Cerca una radio da tutto il mondo e la mette in coda.
- **`/music resume`** — Riprende la riproduzione in pausa.
- **`/music shuffle`** — Mescola l'ordine delle tracce in coda.
- **`/music skip`** — Salta la traccia in riproduzione.
- **`/music skipto`** — Salta direttamente al brano numero N della coda.
- **`/music stop`** — Ferma la riproduzione e svuota la coda.
- **`/music suono`** — Fa partire un effetto sonoro nel tuo canale vocale.
- **`/music suono-ferma`** — Ferma il suono appena partito nel tuo canale vocale.
- **`/music volume down`** — Diminuisce il volume.
- **`/music volume set`** — Imposta il volume a un valore specifico (0-200).
- **`/music volume up`** — Aumenta il volume.

## Owner

- **`/owner ai boss-rete`** — Solo proprietario: pubblica o chiude il boss di rete.
- **`/owner ai manutenzione`** — Solo proprietario: mette l'AI in manutenzione in tutti i server.
- **`/owner ai modello`** — Solo proprietario: modello, fascia e tipi di un fornitore; tetto di lunghezza.
- **`/owner blacklist server-add`** — Blocca globalmente un server (il bot ne uscirà se già presente).
- **`/owner blacklist server-list`** — Mostra i server bloccati globalmente.
- **`/owner blacklist server-remove`** — Rimuove un server dalla blacklist globale.
- **`/owner blacklist utente-add`** — Blocca globalmente un utente dall'uso del bot.
- **`/owner blacklist utente-list`** — Mostra gli utenti bloccati globalmente.
- **`/owner blacklist utente-remove`** — Rimuove un utente dalla blacklist globale.
- **`/owner cog load`** — Carica un'estensione (es. cogs.moderation.actions).
- **`/owner cog reload`** — Ricarica un'estensione, anche aggiornandola da GitHub o da un file.
- **`/owner cog unload`** — Scarica un'estensione.
- **`/owner immagini-trappola`** — Solo proprietario del bot: libreria delle immagini trappola.
- **`/owner parole-odio`** — Solo proprietario del bot: libreria delle parole.
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
- **`/owner radio blocca-parola`** — Parole vietate nei titoli in tutto il bot.
- **`/owner radio cartella`** — Brani della cartella dell'owner: elenco, rilettura, anteprime.
- **`/owner radio fonti`** — Mostra lo stato delle fonti musicali (accesa, chiavi sì/no, pausa).
- **`/owner radio genere`** — Playlist del menu /music genere.
- **`/owner radio list-tracks`** — Mostra la playlist della radio.
- **`/owner radio log`** — Scarica la coda del log del Lavalink locale (ripulita dalle chiavi).
- **`/owner radio nodi`** — Mostra i nodi Lavalink di ogni bot musicale (senza password).
- **`/owner radio paese`** — Paese globale delle ricerche musicali (di base nessun limite).
- **`/owner radio remove-track`** — Rimuove una traccia dalla playlist della radio.
- **`/owner radio riconnetti`** — Riprova subito a collegare i nodi Lavalink non collegati.
- **`/owner radio sorgente`** — Accende o spegne una fonte musicale a bot acceso.
- **`/owner radio start`** — Entra nella radio condivisa, nel punto in cui si trova ora.
- **`/owner radio stato`** — Quanti player musicali stanno suonando ora.
- **`/owner radio stop`** — Esce dalla radio su questo server.
- **`/owner rete`** — Solo proprietario del bot: blocca i server che segnalano in modo scorretto.
- **`/owner system announce`** — Manda un annuncio a tutti i server.
- **`/owner system chiave-soccorso`** — Chiave di soccorso: per riprendere il controllo se perdi l'account.
- **`/owner system eval`** — Esegue codice Python (con conferma).
- **`/owner system leave-guild`** — Forza il bot a lasciare un server specifico (senza bloccarlo).
- **`/owner system memory-status`** — Mostra il consumo di RAM attuale del processo.
- **`/owner system richieste-canale`** — Imposta il canale delle richieste (solo nel server principale).
- **`/owner system risposte-globali`** — Risposte automatiche comuni a tutti i server (massimo 20).
- **`/owner system shell`** — Esegue un comando shell (con conferma).
- **`/owner system stats`** — Statistiche globali del bot.
- **`/owner system storico-vpn`** — Solo proprietario: server che l'hanno lasciata passare e IP della persona (VPN/proxy).

## Rep

- **`/rep classifica`** — Classifica della reputazione del server.
- **`/rep dai`** — Dai punti reputazione a un membro.
- **`/rep mostra`** — Reputazione e posizione di un membro (senza nome: la tua).
- **`/rep registro`** — Chi ha dato o tolto reputazione (la tua; lo staff può vedere quella di altri).
- **`/rep togli`** — Togli punti reputazione a un membro (solo chi ha il ruolo scelto dal server).

## Sala giochi

- **`/sala bingo`** — Bingo tra membri: completa una riga della cartella per vincere il piatto.
- **`/sala bomba`** — Taglia il filo giusto: chi fa esplodere la bomba esce, l'ultimo vince.
- **`/sala carte`** — Carte a turni: stesso colore o stesso numero, chi finisce le carte vince.
- **`/sala corsa`** — Corsa di animali: chi arriva primo prende il piatto.
- **`/sala impiccato`** — Impiccato di gruppo: indovinate la parola insieme e vincete un premio.
- **`/sala lotta`** — Lotta fino a 6 con il tuo animale: l'ultimo in piedi prende il piatto.
- **`/sala quiz`** — Quiz a tempo con premio in monete: cinque domande, quattro risposte.
- **`/sala roulette`** — Roulette a più giocatori: una puntata uguale per tutti, un solo giro.
- **`/sala tamburo`** — Un tamburo con una sfera rossa: chi la trova esce, l'ultimo prende il piatto.

## Sondaggi

- **`/sondaggi bottoni`** — Crea un sondaggio a bottoni (fino a 20 opzioni).
- **`/sondaggi crea`** — Crea un sondaggio (fino a 10 opzioni).
- **`/sondaggi gestisci`** — Elenco, riepilogo o chiusura dei sondaggi a bottoni.
- **`/sondaggi modifica`** — Cambia domanda, opzioni o durata di un sondaggio a bottoni aperto.

## Tag

- **`/tag crea`** — Crea un tag tuo (serve il ruolo scelto dal server).
- **`/tag elimina`** — Elimina un tag che hai creato tu.
- **`/tag modifica`** — Cambia il testo di un tag che hai creato tu.
- **`/tag prendi`** — Prendi un tag il cui autore ha lasciato il server.
- **`/tag prova`** — Prova uno script di tag: non salva niente e non scrive i dati veri.
- **`/tag usa`** — Usa un comando personalizzato di questo server.

## Tela

- **`/tela colora`** — Colora un pixel della tela (c'è una pausa tra un pixel e l'altro).
- **`/tela pixel`** — Chi ha colorato un pixel e quando.
- **`/tela stato`** — La tua pausa, i tuoi pixel e quanto costa saltarla.
- **`/tela vedi`** — Guarda la tela di pixel del server, o una zona ingrandita.

## Ticket

- **`/ticket add`** — Aggiungi un utente o un ruolo a questo ticket.
- **`/ticket apri`** — Apri un ticket (lo staff anche per un utente o da un messaggio).
- **`/ticket assistente`** — Risposta dell'assistente AI (per lo staff: bozza e smistamento).
- **`/ticket azzera-pausa`** — Togli la pausa tra due ticket a un utente.
- **`/ticket chiedi-chiusura`** — Chiedi all'utente se il ticket si può chiudere.
- **`/ticket claim`** — Prendi in carico questo ticket.
- **`/ticket close`** — Chiudi questo ticket.
- **`/ticket dm-chiudi`** — Chiudi questa conversazione ModMail.
- **`/ticket forceclose`** — Chiudi immediatamente questo ticket, senza attesa.
- **`/ticket note`** — Thread privato dello staff per parlare del ticket.
- **`/ticket passa`** — Passa la presa in carico a un collega.
- **`/ticket priority`** — Imposta la priorità di questo ticket.
- **`/ticket pronta`** — Scrivi nel ticket una risposta pronta (articolo approvato).
- **`/ticket remove`** — Rimuovi un utente o un ruolo da questo ticket.
- **`/ticket rename`** — Rinomina questo ticket.
- **`/ticket reperibile`** — Entra o esci dallo staff avvisato a ogni nuovo ticket.
- **`/ticket riapri`** — Riapri questo ticket chiuso (se il pannello tiene il canale).
- **`/ticket rilascia`** — Lascia la presa in carico di questo ticket.
- **`/ticket rispondi`** — Rispondi all'utente di questa conversazione ModMail.
- **`/ticket tieni-aperto`** — Escludi questo ticket dalla chiusura automatica (o rimettilo).
- **`/ticket transcript`** — Ricevi il transcript senza chiudere il ticket.

## Utility

- **`/utility identita colore`** — Scegli il colore del tuo nome dalla tavolozza del server.
- **`/utility identita ruolo-mio`** — Cambia nome e colore del tuo ruolo personale (se lo staff te l'ha concesso).
- **`/utility info`** — Informazioni sul bot: versione, invito e supporto.
- **`/utility lingua`** — Mostra o cambia la tua lingua personale (italiano o inglese).
- **`/utility mie-sanzioni`** — Le sanzioni che hai ricevuto in questo server (solo tu le vedi).
- **`/utility modulo`** — Compila un modulo o una candidatura di questo server.
- **`/utility novita`** — Le ultime novità del bot.
- **`/utility ping`** — Controlla se iYokai Main è online e la sua latenza.
- **`/utility privacy cancella`** — Chiedi la cancellazione dei tuoi dati personali.
- **`/utility privacy esporta`** — Ricevi una copia dei dati che il bot conserva su di te.
- **`/utility privacy statistiche`** — Mostra il tuo nome nelle classifiche delle statistiche, o resta anonimo.
- **`/utility reminder cancel`** — Annulla un promemoria, o tutti i tuoi.
- **`/utility reminder list`** — Mostra i tuoi promemoria in sospeso.
- **`/utility reminder set`** — Imposta un promemoria.
- **`/utility report`** — Segnala un utente allo staff del server.
- **`/utility richiedi-comando`** — Proponi un nuovo comando per il bot.
- **`/utility ruolo`** — Prendi o lascia i ruoli a scelta del server.
- **`/utility scheda anzianita`** — Account più vecchi o nuovi, primi o ultimi entrati.
- **`/utility scheda canale`** — Scheda di un canale.
- **`/utility scheda emoji`** — Scheda di un'emoji: ID, data, animata, immagine.
- **`/utility scheda invito`** — Scheda di un invito: server, canale, membri, scadenza.
- **`/utility scheda membri`** — I membri che hanno un ruolo, o tutti in un file.
- **`/utility scheda permessi`** — Permessi di un membro o del bot in un canale.
- **`/utility scheda ruoli`** — Tutti i ruoli con ID, membri e colore.
- **`/utility scheda ruolo`** — Scheda di un ruolo: membri, colore, data, permessi.
- **`/utility scheda server`** — Scheda del server: proprietario, data, numeri, boost.
- **`/utility scheda utente`** — Scheda di un membro: ID, date e ruoli.
- **`/utility serverstats`** — Statistiche del server: crescita, attività dei canali e dei membri.
- **`/utility snipe messaggio`** — Mostra l'ultimo messaggio cancellato in questo canale.
- **`/utility snipe modifica`** — Mostra l'ultimo messaggio modificato in questo canale.
- **`/utility snipe reazione`** — Mostra l'ultima reazione rimossa in questo canale.
- **`/utility strumenti avatar`** — L'avatar di un membro in grande, del server o globale.
- **`/utility strumenti caratteri`** — Nome, codice e categoria Unicode dei caratteri di un testo.
- **`/utility strumenti cronometro`** — Un cronometro con i bottoni Giro e Ferma.
- **`/utility suggest`** — Proponi un'idea per questo server.
- **`/utility verifica`** — Verificati in questo server (come il bottone del pannello).

## Vocali

- **`/voice bitrate`** — Imposta la qualità audio del canale (kbps).
- **`/voice claim`** — Prendi il canale se il proprietario non c'è più.
- **`/voice deny`** — Vieta a un utente o a un ruolo di entrare nel canale.
- **`/voice invita`** — Manda a un utente un invito al tuo canale.
- **`/voice kick`** — Espelli un utente dal tuo canale.
- **`/voice limit`** — Imposta il limite di utenti del canale.
- **`/voice lock`** — Blocca il canale (nessun nuovo ingresso).
- **`/voice nascondi`** — Nascondi o mostra il canale a chi non è dentro.
- **`/voice permit`** — Permetti a un utente o a un ruolo di entrare anche se il canale è bloccato.
- **`/voice rename`** — Rinomina il tuo canale vocale.
- **`/voice stato`** — Scrivi cosa state facendo nel canale (vuoto: toglie).
- **`/voice transfer`** — Trasferisci la proprietà del canale.
- **`/voice unlock`** — Sblocca il canale.
- **`/voice vai`** — Spostati in un vocale dove puoi entrare.

## Web

- **`/web accorcia`** — Accorcia un link (se il server ha acceso il comando).
- **`/web dizionario`** — Il significato di una parola, da Wikizionario.
- **`/web emergenza`** — I numeri di emergenza di un paese.
- **`/web film`** — Informazioni su un film o una serie TV.
- **`/web gioco`** — Un gioco di Steam: prezzo, data e generi.
- **`/web meteo`** — Il meteo di una città: adesso e i prossimi giorni.
- **`/web prezzo`** — Il prezzo di una criptovaluta.
- **`/web scheda`** — La scheda di un Pokémon, anime, carta o giocatore.
- **`/web turni`** — Le rotazioni di Splatoon 3 e il reset settimanale di World of Warcraft.
- **`/web wiki`** — Il riassunto di una voce di Wikipedia.
