# Elenco comandi — iYokai

Generato automaticamente da `scripts/generate_command_list.py` il 2026-11-09 13:23 UTC, interrogando l'albero comandi VERO del bot dopo aver caricato ogni cog — non un elenco scritto a mano. Da rigenerare dopo ogni commit che aggiunge, rimuove o rinomina un comando.

**Totale: 774 comandi in 45 categorie.**

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
- **`/admin-ai stato`** — Stato dell'AI nel server: fornitori, scelte e uso del mese.
- **`/admin-ai traduzione`** — Traduce da solo ogni messaggio di un canale in una lingua.
- **`/admin-ai vietate`** — Parole o argomenti che l'AI deve rifiutare.
- **`/admin-ai voce imposta`** — Voce di Yokai: accesa o spenta, tono e canali dei saluti.
- **`/admin-ai voce parla`** — Yokai dice un annuncio a voce in un canale.

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

## Admin: AutoMod

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
- **`/admin-backup elimina`** — Elimina una copia salvata.
- **`/admin-backup esporta`** — Esporta struttura, canali, ruoli, ban o reazioni in un file.
- **`/admin-backup importa`** — Importa la struttura da un file JSON, scegliendo cosa applicare.
- **`/admin-backup lista`** — Le copie salvate di questo server, con la data.
- **`/admin-backup main`** — Registra questo server come 'main' per il Backup System.
- **`/admin-backup modello`** — Modelli: condividi una copia con un codice o carica quella di un altro server.
- **`/admin-backup promuovi`** — Promuove QUESTO server (finora backup) a nuovo main, se il main originale è perso.
- **`/admin-backup registro`** — Chi ha usato backup, modelli e sincronie (ultimi 20, 365 giorni).
- **`/admin-backup ripristino modo`** — Scegli come questo server gestisce il restore utenti via OAuth2.
- **`/admin-backup ripristino utenti`** — Ripristina in QUESTO server gli utenti dell'ultimo snapshot di un altro server.
- **`/admin-backup salva`** — Salva una copia datata della struttura di questo server.
- **`/admin-backup stato`** — Avanzamento dell'ultimo caricamento in questo server.

## Admin: benvenuto

- **`/admin-benvenuto addio`** — Configura il messaggio di addio.
- **`/admin-benvenuto anteprima`** — Mostra un'anteprima di come apparirebbe un messaggio.
- **`/admin-benvenuto boost`** — Configura il messaggio di boost.
- **`/admin-benvenuto extra`** — Benvenuto: DM, varianti, reazioni; messaggi di ban e addio.
- **`/admin-benvenuto immagine`** — Aggiungi al benvenuto un'immagine con avatar, nome e numero del membro.
- **`/admin-benvenuto messaggio`** — Configura il messaggio di benvenuto.

## Admin: impianto del bot

- **`/admin-bot config canale-report`** — Imposta il canale delle segnalazioni.
- **`/admin-bot config canale-suggerimenti`** — Imposta il canale dei suggerimenti.
- **`/admin-bot config export`** — Esporta la configurazione di questo server in un file.
- **`/admin-bot config history`** — Mostra le ultime modifiche alla configurazione.
- **`/admin-bot config import`** — Importa una configurazione da un file esportato con /admin-bot config export.
- **`/admin-bot config nickname-bot`** — Cambia il nome del bot in questo server.
- **`/admin-bot config pulizia`** — Toglie dalla configurazione canali e ruoli che non esistono più.
- **`/admin-bot config reset`** — Azzera la configurazione di questo server.
- **`/admin-bot config rollback`** — Ripristina il valore precedente di una modifica.
- **`/admin-bot config sincronizza`** — Riscrive i permessi dei comandi di questo server.
- **`/admin-bot lingua set`** — Imposta la lingua di questo server.
- **`/admin-bot lingua show`** — Mostra la lingua impostata per questo server.
- **`/admin-bot politica canali`** — Dove il bot risponde ai comandi.
- **`/admin-bot politica comando`** — Spegne o riaccende un singolo comando.
- **`/admin-bot politica diagnosi`** — Scopre perché un comando non funziona qui.
- **`/admin-bot politica elenco`** — Mostra la politica dei comandi e, se vuoi, azzera un elenco.
- **`/admin-bot politica ignora`** — Il bot ignora un ruolo o un utente.
- **`/admin-bot premium aspetto`** — Avatar, banner e descrizione del bot in questo server (premium).
- **`/admin-bot premium marchio`** — Usa un bot con il tuo nome e il tuo avatar (premium).
- **`/admin-bot premium riscatta`** — Riscatta un codice premium per questo server.
- **`/admin-bot premium sblocca`** — Sblocca un modulo premium per 30 giorni con le monete della cassa del server.
- **`/admin-bot premium stato`** — Mostra come è sbloccato il premium in questo server.
- **`/admin-bot setup attiva`** — Attiva o disattiva i moduli del bot, per categoria.
- **`/admin-bot setup wizard`** — Configura passo-passo ruoli e moduli del bot, una categoria alla volta.

## Admin: economia

- **`/admin-economia annunci clan-off`** — Disattiva l'annuncio automatico della top 3 gilde.
- **`/admin-economia annunci clan-set`** — Imposta il canale dove annunciare la top 3 gilde del mese.
- **`/admin-economia annunci vincitori-off`** — Disattiva l'annuncio dei vincitori del mese.
- **`/admin-economia annunci vincitori-set`** — Imposta il canale dove annunciare i vincitori del mese.
- **`/admin-economia assegna-lobby`** — Premio partecipazione: assegna coin a chi è in vocale ORA, dalla cassa del server.
- **`/admin-economia assegna-winner`** — Premio vincitore: assegna coin a un membro, dalla cassa del server.
- **`/admin-economia cassa-premium`** — Sblocca un mese di bot premium spendendo dalla cassa.
- **`/admin-economia monete`** — Modifica il saldo di un membro.
- **`/admin-economia shop-add`** — Aggiunge un oggetto allo shop.
- **`/admin-economia shop-edit`** — Cambia un oggetto dello shop (prezzo, scorte, ruolo richiesto...).
- **`/admin-economia shop-remove`** — Rimuove un oggetto dallo shop.

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
- **`/admin-filtri forma-testo`** — Limiti sulla forma del messaggio: a-capo, lunghezza, spoiler (0 = spento).
- **`/admin-filtri invites`** — Attiva o disattiva il blocco automatico degli inviti Discord.
- **`/admin-filtri messaggi`** — Ripetuti, troppo corti, link e menzioni contati nel tempo (0 = spento).
- **`/admin-filtri phishing`** — Attiva o disattiva il blocco dei link di phishing (finti regali, finti login).

## Admin: giochi

- **`/admin-giochi battitura aggiungi`** — Aggiunge un testo per la battitura (finestra).
- **`/admin-giochi battitura elenca`** — I testi di battitura del server.
- **`/admin-giochi battitura rimuovi`** — Toglie un testo di battitura.
- **`/admin-giochi conteggio canale`** — Scegli i canali dove si conta (fino a 10) e come.
- **`/admin-giochi conteggio importa`** — Porta in un canale i punteggi di un file CSV o JSON.
- **`/admin-giochi conteggio regole`** — Punizione dopo uno sbaglio e ruolo di chi ha contato per ultimo.
- **`/admin-giochi conteggio traguardo`** — Ruolo o messaggio quando il conteggio tocca un numero.
- **`/admin-giochi punteggi azzera`** — Azzera i punteggi di una gara (con conferma).
- **`/admin-giochi quiz carica`** — Carica domande per il quiz da un file CSV o JSON.
- **`/admin-giochi quiz elenca`** — Le domande del quiz caricate dal server.
- **`/admin-giochi quiz regole`** — Regole del quiz: punti, tempo, risposta mostrata, il bot gioca.
- **`/admin-giochi quiz rimuovi`** — Toglie una domanda caricata dal server.

## Admin: giveaway

- **`/admin-giveaway avvia`** — Avvia un giveaway.
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
- **`/admin-livelli card`** — Mostra o nascondi in questo server gli sfondi con immagine di card e profili.
- **`/admin-livelli escludi`** — Un canale, una categoria o un ruolo non dà XP (rifallo per toglierlo).
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
- **`/admin-log ignora`** — Cosa i log non registrano (canali, utenti, ruoli; testi solo per i messaggi).
- **`/admin-log stato`** — Mostra dove vanno i log del server.
- **`/admin-log vista-forum`** — Un forum con un post per canale o per caso. Senza forum, la vista si spegne.
- **`/admin-log webhook`** — Manda i log da un webhook del canale, raggruppati, con limiti suoi.

## Admin: messaggi

- **`/admin-messaggi auto`** — Automatismi: citazioni, correzione link, pubblicazione annunci, accorciatore.
- **`/admin-messaggi embed bottoni`** — Aggiungi o togli i bottoni di un embed (link o mostra tag).
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
- **`/admin-messaggi risposte crea`** — Crea una risposta automatica.
- **`/admin-messaggi risposte elenco`** — Mostra le risposte automatiche del server.
- **`/admin-messaggi risposte elimina`** — Elimina una risposta automatica.
- **`/admin-messaggi scrivi`** — Fai scrivere un messaggio al bot in un canale.
- **`/admin-messaggi tag crea`** — Crea un comando personalizzato.
- **`/admin-messaggi tag elenco`** — Mostra i comandi personalizzati del server.
- **`/admin-messaggi tag elimina`** — Elimina un comando personalizzato.
- **`/admin-messaggi tag modifica`** — Cambia un comando personalizzato.
- **`/admin-messaggi tag prefisso`** — Scegli il prefisso per usare i comandi scrivendo nel canale.

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
- **`/admin-moduli compleanni canale`** — Scegli il canale degli auguri (vuoto per spegnerli).
- **`/admin-moduli compleanni membro`** — Registra il compleanno di un membro (solo giorno e mese).
- **`/admin-moduli compleanni ruolo`** — Un ruolo per 24 ore a chi compie gli anni (vuoto per toglierlo).
- **`/admin-moduli contatori crea`** — Crea un canale che mostra un numero.
- **`/admin-moduli contatori elenco`** — Mostra i contatori del server.
- **`/admin-moduli contatori elimina`** — Smetti di aggiornare un contatore (il canale resta).
- **`/admin-moduli starboard disattiva`** — Spegni la bacheca.
- **`/admin-moduli starboard imposta`** — Scegli il canale della bacheca e la soglia di stelle.
- **`/admin-moduli starboard soglia`** — Cambia quante stelle servono per finire in bacheca.
- **`/admin-moduli statistiche diagnosi`** — Perché le statistiche non si contano?
- **`/admin-moduli statistiche elenco`** — Mostra regole ed esclusioni delle statistiche.
- **`/admin-moduli statistiche impostazioni`** — Escludi canali o ruoli dalle statistiche.
- **`/admin-moduli statistiche ruolo-aggiungi`** — Dai un ruolo a chi è attivo e toglilo a chi smette.
- **`/admin-moduli statistiche ruolo-elimina`** — Elimina una regola dei ruoli per attività.

## Admin: musica

- **`/admin-musica canale-richieste`** — Canale dove si scrive un titolo per metterlo in coda, con il player.
- **`/admin-musica impostazioni`** — Cambia le impostazioni musicali del server.
- **`/admin-musica riepilogo`** — Mostra tutte le impostazioni musicali del server.

## Admin: ruoli

- **`/admin-ruoli auto aggiungi`** — Aggiungi un ruolo dato in automatico a chi entra.
- **`/admin-ruoli auto elenco`** — Mostra i ruoli automatici del server.
- **`/admin-ruoli auto ricorda`** — Ridai i ruoli a chi esce e rientra entro un certo tempo.
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
- **`/admin-ticket modmail attiva`** — Accendi o spegni il ModMail (ticket in DM).
- **`/admin-ticket modmail blocca`** — Blocca o sblocca un utente dal ModMail.
- **`/admin-ticket panel`** — Pubblica il pannello per l'apertura dei ticket in questo canale.
- **`/admin-ticket pannelli crea`** — Crea un pannello di ticket.
- **`/admin-ticket pannelli elenco`** — Elenca i pannelli di ticket del server.
- **`/admin-ticket pannelli modulo-aggiungi`** — Aggiungi una domanda al modulo (max 5).
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
- **`/admin-vocali generatore`** — Altri canali generatori con regole proprie.
- **`/admin-vocali opzioni`** — Nome dei nuovi canali, blocco, registro, copia, pannello.
- **`/admin-vocali panel`** — Pubblica il pannello per la creazione manuale di un vocale.
- **`/admin-vocali piattaforme`** — Configura i ruoli informativi PC/Console/Mobile per i vocali temporanei.
- **`/admin-vocali setup`** — Configura il canale generatore e la categoria dei vocali temporanei.

## Aiuto (primo livello)

- **`/Apri ticket`** — Menu «App» (tasto destro)
- **`/Orari nel mio fuso`** — Menu «App» (tasto destro)
- **`/Riestrai giveaway`** — Menu «App» (tasto destro)
- **`/Scheda moderazione`** — Menu «App» (tasto destro)
- **`/Segnala messaggio`** — Menu «App» (tasto destro)
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
- **`/assistente spiega`** — Spiega in parole semplici un messaggio (dal suo link).
- **`/assistente spirito`** — Il tuo spirito Yokai: cresce con la tua attività.
- **`/assistente stile`** — Un messaggio nuovo scritto come scrivi tu (o come chi lo permette).
- **`/assistente traduci`** — Traduce un testo nella lingua che scegli.

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

## Founder (proprietario del server)

- **`/founder backup permessi`** — Chi può creare e chi può caricare i backup (solo l'owner).
- **`/founder backup sincronia`** — Tieni uguali ban e ruoli con un altro tuo server.
- **`/founder moderazione immuni`** — Ruoli che la moderazione manuale non tocca (solo il proprietario).

## Divertimento

- **`/fun 8ball`** — Fai una domanda alla palla magica 8.
- **`/fun casuale`** — Preferiresti, argomento, consiglio, oggetto magico, classe.
- **`/fun coinflip`** — Lancia una moneta: testa o croce.
- **`/fun dice`** — Tira un dado.
- **`/fun fact`** — Mostra una curiosità a caso.
- **`/fun joke`** — Racconta una barzelletta a caso.
- **`/fun misura`** — Misura da 0 a 100% quanto c'è di una cosa a tua scelta.
- **`/fun numero`** — Un numero a caso in un intervallo.
- **`/fun quote`** — Mostra una citazione a caso.
- **`/fun rate`** — Valuta qualcosa da 0 a 10.
- **`/fun scegli`** — Scelgo a caso tra le opzioni che scrivi.
- **`/fun scherzo`** — Uno scherzo innocuo verso un utente.
- **`/fun ship`** — Calcola la compatibilità tra due utenti.
- **`/fun testo`** — Scrivi un testo in uno stile speciale.

## Gif

- **`/gif azione`** — Una GIF di azione verso un utente: abbraccio, bacio, schiaffo...
- **`/gif privacy`** — Scegli chi può farti le azioni con le GIF.
- **`/gif reazione`** — Una GIF di reazione: piangi, balli, ridi...

## Giochi

- **`/giochi acronimi`** — Inventa frasi che seguono le lettere date e vota la migliore.
- **`/giochi battitura`** — Gara di battitura: copia il testo mostrato nell'immagine.
- **`/giochi conteggio avvisami`** — Ti avviso nel canale quando il conteggio arriva a un numero.
- **`/giochi conteggio classifica`** — Chi ha contato più numeri giusti.
- **`/giochi dado`** — Un tiro al giorno da 1 a 100 e la classifica del server.
- **`/giochi gioca`** — Gioca le tue coin: monetina, dadi o slot.
- **`/giochi mazzo`** — Un mazzo di 52 carte per il server: pesca, rimescola, controlla.
- **`/giochi minato`** — Campo minato: tocca gli spoiler ed evita le mine.
- **`/giochi quiz avvia`** — Avvia un quiz a domande nel canale.
- **`/giochi quiz classifica`** — Classifica del quiz: questa settimana o di sempre.
- **`/giochi rps`** — Carta, forbici, sasso contro il bot.
- **`/giochi spinner`** — Fai girare lo spinner: vince chi lo fa girare più a lungo.

## Immagini

- **`/immagini animal`** — Mostra immagini casuali di animali (fino a 5).
- **`/immagini blur`** — Applica una sfocatura a un'immagine.
- **`/immagini effetto`** — Effetto sull'avatar: arcobaleno, R.I.P., ricercato, pingato, sepia, neon...
- **`/immagini foto`** — Una foto bella da vedere: cibo o buonumore.
- **`/immagini grayscale`** — Trasforma un'immagine in scala di grigi.
- **`/immagini invert`** — Inverte i colori di un'immagine.
- **`/immagini meme`** — Genera un meme con testo sopra/sotto.
- **`/immagini pixelate`** — Pixela un'immagine.
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
- **`/level premi`** — Mostra i ruoli-premio dei livelli e i moltiplicatori di XP attivi.
- **`/level profilo`** — Mostra il profilo di un membro; con «presentazione» cambi il tuo.
- **`/level progressi`** — Missioni, serie, traguardi e pass di 90 giorni, in un menu.
- **`/level rank`** — Mostra la rank card: livello, XP, posizione e coin.
- **`/level stelle caso`** — Un messaggio a caso dalla bacheca.
- **`/level stelle classifica`** — Chi ha ricevuto più stelle in bacheca.

## Mod: ban

- **`/mod-ban appelli canale`** — Sceglie il canale staff per gli appelli (vuoto per spegnerli).
- **`/mod-ban appelli elenco`** — Mostra gli ultimi appelli del server.
- **`/mod-ban ban`** — Banna permanentemente un membro.
- **`/mod-ban cerca`** — Cerca tra i ban del server per nome, ID o motivo.
- **`/mod-ban kick`** — Espelle un membro dal server.
- **`/mod-ban massa ban`** — Banna più utenti insieme, anche fuori dal server (ID o menzioni).
- **`/mod-ban massa entrati`** — Banna o espelle chi è entrato negli ultimi minuti (dopo una conferma).
- **`/mod-ban massa kick`** — Espelle più membri insieme (ID o menzioni).
- **`/mod-ban massa unban`** — Toglie il ban a più utenti insieme (ID).
- **`/mod-ban softban`** — Banna e sbanna subito un membro, per cancellarne i messaggi recenti.
- **`/mod-ban tempban`** — Banna un membro per una durata definita.
- **`/mod-ban unban`** — Rimuove il ban da un utente.

## Mod: canali

- **`/mod-canali blocco attiva`** — Blocca tutti i canali, gli inviti e gli ingressi del server.
- **`/mod-canali blocco togli`** — Riapre il server com'era prima del blocco.
- **`/mod-canali clear`** — Cancella un numero di messaggi, con filtri opzionali.
- **`/mod-canali lock`** — Blocca la possibilità di scrivere in un canale.
- **`/mod-canali reazioni`** — Toglie le reazioni dagli ultimi messaggi di un canale, senza cancellarli.
- **`/mod-canali slowmode`** — Slowmode di un canale o di una categoria. Senza valori: mostra i canali con slowmode.
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
- **`/mod-casi nota aggiungi`** — Aggiunge una nota su un utente.
- **`/mod-casi nota elenca`** — Elenca le note su un utente.
- **`/mod-casi nota modifica`** — Cambia il testo di una nota.
- **`/mod-casi nota rimuovi`** — Toglie una nota (il numero è nell'elenco delle note).
- **`/mod-casi nota svuota`** — Cancella tutte le note di un membro (serve «Gestire il server»).
- **`/mod-casi rischio`** — Punteggio di rischio di un membro, con i motivi. Solo un aiuto per decidere.
- **`/mod-casi scheda`** — La scheda di un utente: date, casi, note e rischio (anche fuori dal server).

## Mod: sanzioni

- **`/mod-sanzioni applica`** — Dà la sanzione di un motivo pronto, che puoi cambiare prima di confermare.
- **`/mod-sanzioni massa timeout`** — Mette in timeout più membri insieme (max 28 giorni).
- **`/mod-sanzioni massa warn`** — Assegna un warn a più membri insieme.
- **`/mod-sanzioni mute`** — Silenzia un membro con un ruolo dedicato (alternativa al timeout).
- **`/mod-sanzioni nick`** — Cambia o azzera il soprannome di un membro.
- **`/mod-sanzioni opzioni dm`** — Sceglie se l'utente riceve un DM per un tipo di azione.
- **`/mod-sanzioni opzioni imposta`** — Messaggi al ban, timeout, casi esterni, avvisi. Vuoto: mostra le opzioni.
- **`/mod-sanzioni timeout`** — Mette in timeout un membro (max 28 giorni).
- **`/mod-sanzioni unmute`** — Rimuove il ruolo mute da un membro.
- **`/mod-sanzioni untimeout`** — Rimuove il timeout da un membro.
- **`/mod-sanzioni warn`** — Assegna un warn a un membro.

## Monete

- **`/monete attese`** — Quando potrai di nuovo usare daily e work.
- **`/monete balance`** — Mostra i tuoi coin.
- **`/monete cassa`** — Mostra il saldo della cassa del server.
- **`/monete daily`** — Riscuoti la ricompensa giornaliera.
- **`/monete pay`** — Trasferisci coin a un altro utente.
- **`/monete shop buy`** — Acquista un oggetto dello shop.
- **`/monete shop list`** — Mostra gli oggetti disponibili nello shop.
- **`/monete work`** — Lavora per guadagnare qualche coin.

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
- **`/owner system storico-vpn`** — Solo proprietario: server che l'hanno lasciata passare e IP della persona (VPN/proxy).

## Sondaggi

- **`/sondaggi crea`** — Crea un sondaggio (fino a 10 opzioni).

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
- **`/ticket remove`** — Rimuovi un utente o un ruolo da questo ticket.
- **`/ticket rename`** — Rinomina questo ticket.
- **`/ticket reperibile`** — Entra o esci dallo staff avvisato a ogni nuovo ticket.
- **`/ticket riapri`** — Riapri questo ticket chiuso (se il pannello tiene il canale).
- **`/ticket rilascia`** — Lascia la presa in carico di questo ticket.
- **`/ticket rispondi`** — Rispondi all'utente di questa conversazione ModMail.
- **`/ticket transcript`** — Ricevi il transcript senza chiudere il ticket.

## Utility

- **`/utility info`** — Informazioni sul bot: versione, invito e supporto.
- **`/utility lingua`** — Mostra o cambia la tua lingua personale (italiano o inglese).
- **`/utility mie-sanzioni`** — Le sanzioni che hai ricevuto in questo server (solo tu le vedi).
- **`/utility modulo`** — Compila un modulo o una candidatura di questo server.
- **`/utility novita`** — Le ultime novità del bot.
- **`/utility ping`** — Controlla se iYokai Main è online e la sua latenza.
- **`/utility privacy cancella`** — Chiedi la cancellazione dei tuoi dati personali.
- **`/utility privacy esporta`** — Ricevi una copia dei dati che il bot conserva su di te.
- **`/utility reminder cancel`** — Annulla un promemoria, o tutti i tuoi.
- **`/utility reminder list`** — Mostra i tuoi promemoria in sospeso.
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
- **`/utility snipe messaggio`** — Mostra l'ultimo messaggio cancellato in questo canale.
- **`/utility snipe modifica`** — Mostra l'ultimo messaggio modificato in questo canale.
- **`/utility snipe reazione`** — Mostra l'ultima reazione rimossa in questo canale.
- **`/utility strumenti caratteri`** — Nome, codice e categoria Unicode dei caratteri di un testo.
- **`/utility strumenti cronometro`** — Un cronometro con i bottoni Giro e Ferma.
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

## Web

- **`/web accorcia`** — Accorcia un link (se il server ha acceso il comando).
- **`/web dizionario`** — Il significato di una parola, da Wikizionario.
- **`/web emergenza`** — I numeri di emergenza di un paese.
- **`/web film`** — Informazioni su un film o una serie TV.
- **`/web gioco`** — Un gioco di Steam: prezzo, data e generi.
- **`/web meteo`** — Il meteo di una città: adesso e i prossimi giorni.
- **`/web prezzo`** — Il prezzo di una criptovaluta.
- **`/web wiki`** — Il riassunto di una voce di Wikipedia.
