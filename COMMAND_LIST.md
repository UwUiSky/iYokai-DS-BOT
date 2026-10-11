# Elenco comandi — iYokai

Generato automaticamente da `scripts/generate_command_list.py` il 2026-10-11 20:20 UTC, interrogando l'albero comandi VERO del bot dopo aver caricato ogni cog — non un elenco scritto a mano. Da rigenerare dopo ogni commit che aggiunge, rimuove o rinomina un comando.

**Totale: 248 comandi in 16 categorie.**

## Admin

- **`/admin backup crea`** — Accoda la creazione di un backup per questo server.
- **`/admin backup main`** — Registra questo server come 'main' per il Backup System.
- **`/admin backup promuovi`** — Promuove QUESTO server (finora backup) a nuovo main, se il main originale è perso.
- **`/admin backup restore-modo`** — Scegli come questo server gestisce il restore utenti via OAuth2.
- **`/admin backup restore-utenti`** — Ripristina in QUESTO server gli utenti dell'ultimo snapshot di un altro server.
- **`/admin config canale-report`** — Imposta il canale delle segnalazioni.
- **`/admin config canale-suggerimenti`** — Imposta il canale dei suggerimenti.
- **`/admin config export`** — Esporta la configurazione di questo server in un file.
- **`/admin config history`** — Mostra le ultime modifiche alla configurazione.
- **`/admin config import`** — Importa una configurazione da un file esportato con /admin config export.
- **`/admin config reset`** — Azzera la configurazione di questo server.
- **`/admin config rollback`** — Ripristina il valore precedente di una modifica.
- **`/admin lingua set`** — Imposta la lingua di questo server.
- **`/admin lingua show`** — Mostra la lingua impostata per questo server.
- **`/admin messaggi annulla`** — Annulla un messaggio programmato.
- **`/admin messaggi programma`** — Programma un messaggio.
- **`/admin messaggi programmati`** — Mostra i messaggi programmati di questo server.
- **`/admin messaggi sticky-set`** — Imposta lo sticky message di un canale.
- **`/admin messaggi sticky-togli`** — Rimuove lo sticky message di un canale.
- **`/admin setup attiva`** — Attiva o disattiva i moduli del bot, per categoria.
- **`/admin setup wizard`** — Configura passo-passo i moduli principali del bot.

## Aiuto (primo livello)

- **`/-cerca-comando`** — Cerca un comando per descrizione.
- **`/-chiedi`** — Chiedi aiuto: ti mostro i comandi giusti.

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
- **`/automod filtri invites`** — Attiva o disattiva il blocco automatico degli inviti Discord.
- **`/automod log-channel`** — Imposta il canale dove pubblicare il log delle azioni AutoMod avanzate.
- **`/automod mute-duration`** — Imposta la durata del timeout usato dall'azione 'mute' dell'AutoMod.
- **`/automod parole add`** — Aggiunge una parola vietata.
- **`/automod parole list`** — Mostra le parole vietate configurate.
- **`/automod parole remove`** — Rimuove una parola vietata.
- **`/automod status`** — Mostra la configurazione attuale dei filtri AutoMod avanzati.
- **`/automod sync`** — Forza una sincronizzazione manuale delle regole AutoMod.

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

## Divertimento

- **`/fun 8ball`** — Fai una domanda alla palla magica 8.
- **`/fun animal`** — Mostra un'immagine casuale di un animale.
- **`/fun blur`** — Applica una sfocatura a un'immagine.
- **`/fun coinflip`** — Lancia una moneta: testa o croce.
- **`/fun dice`** — Tira un dado.
- **`/fun fact`** — Mostra una curiosità a caso.
- **`/fun grayscale`** — Trasforma un'immagine in scala di grigi.
- **`/fun invert`** — Inverte i colori di un'immagine.
- **`/fun joke`** — Racconta una barzelletta a caso.
- **`/fun meme`** — Genera un meme con testo sopra/sotto.
- **`/fun pixelate`** — Pixela un'immagine.
- **`/fun quote`** — Mostra una citazione a caso.
- **`/fun rate`** — Valuta qualcosa da 0 a 10.
- **`/fun rps`** — Carta, forbici, sasso contro il bot.
- **`/fun search-image`** — Cerca un'immagine SFW su Pixabay.
- **`/fun ship`** — Calcola la compatibilità tra due utenti.

## Gestione

- **`/gestione benvenuto addio`** — Configura il messaggio di addio.
- **`/gestione benvenuto anteprima`** — Mostra un'anteprima di come apparirebbe un messaggio.
- **`/gestione benvenuto benvenuto`** — Configura il messaggio di benvenuto.
- **`/gestione benvenuto boost`** — Configura il messaggio di boost.
- **`/gestione economia assegna-lobby`** — Premio partecipazione: assegna coin a chi è in vocale ORA, dalla cassa del server.
- **`/gestione economia assegna-winner`** — Premio vincitore: assegna coin a un membro, dalla cassa del server.
- **`/gestione economia cassa-premium`** — Sblocca un mese di bot premium spendendo dalla cassa.
- **`/gestione economia giveaway`** — Avvia un giveaway.
- **`/gestione economia shop-add`** — Aggiunge un oggetto allo shop.
- **`/gestione economia shop-remove`** — Rimuove un oggetto dallo shop.
- **`/gestione economia vincitori-off`** — Disattiva l'annuncio dei vincitori del mese.
- **`/gestione economia vincitori-set`** — Imposta il canale dove annunciare i vincitori del mese.
- **`/gestione ruoli livello-add`** — Assegna un ruolo a chi raggiunge un livello.
- **`/gestione ruoli livello-list`** — Mostra i ruoli-premio configurati su questo server.
- **`/gestione ruoli livello-remove`** — Rimuove un ruolo-premio configurato.
- **`/gestione ruoli menu-aggiungi`** — Aggiungi un'opzione a un role menu.
- **`/gestione ruoli menu-crea`** — Crea un nuovo role menu.
- **`/gestione ruoli menu-elimina`** — Elimina un role menu.
- **`/gestione ruoli menu-togli`** — Rimuovi un'opzione da un role menu.
- **`/gestione ticket categoria-add`** — Aggiungi (o aggiorna) una categoria di ticket.
- **`/gestione ticket categoria-list`** — Elenca le categorie di ticket configurate.
- **`/gestione ticket categoria-remove`** — Rimuovi una categoria di ticket.
- **`/gestione ticket panel`** — Pubblica il pannello per l'apertura dei ticket in questo canale.
- **`/gestione ticket ruolo-add`** — Aggiungi un ruolo di supporto.
- **`/gestione ticket ruolo-list`** — Elenca i ruoli di supporto configurati.
- **`/gestione ticket ruolo-remove`** — Rimuovi un ruolo di supporto.
- **`/gestione ticket setup`** — Configura la categoria (e opzionalmente il ruolo di supporto) per i ticket.
- **`/gestione ticket stats`** — Statistiche del sistema di ticket.
- **`/gestione voice cap`** — Imposta il numero massimo di vocali temporanei per categoria.
- **`/gestione voice panel`** — Pubblica il pannello per la creazione manuale di un vocale.
- **`/gestione voice piattaforme`** — Configura i ruoli informativi PC/Console/Mobile per i vocali temporanei.
- **`/gestione voice setup`** — Configura il canale generatore e la categoria dei vocali temporanei.

## Livelli

- **`/level balance`** — Mostra i tuoi coin.
- **`/level cassa`** — Mostra il saldo della cassa del server.
- **`/level daily`** — Riscuoti la ricompensa giornaliera.
- **`/level impostazioni annuncio`** — Dove e quando annunciare i level-up.
- **`/level impostazioni escludi`** — Un canale, una categoria o un ruolo non dà XP (rifallo per toglierlo).
- **`/level impostazioni moltiplicatore`** — XP moltiplicati in un canale o per un ruolo (fattore 1 = toglie la regola).
- **`/level impostazioni mostra`** — Mostra le impostazioni dei livelli di questo server.
- **`/level impostazioni premi`** — Ruoli-premio: tienili tutti o tieni solo quello più alto.
- **`/level impostazioni xp`** — Quanti XP e coin si guadagnano, e come si sommano i moltiplicatori.
- **`/level leaderboard`** — Mostra la classifica del server.
- **`/level pay`** — Trasferisci coin a un altro utente.
- **`/level rank`** — Mostra la rank card: livello, XP, posizione e coin.
- **`/level shop buy`** — Acquista un oggetto dello shop.
- **`/level shop list`** — Mostra gli oggetti disponibili nello shop.
- **`/level work`** — Lavora per guadagnare qualche coin.

## Log

- **`/log canale`** — Imposta il canale (o il forum) dei log del server.
- **`/log cerca canale`** — Mostra lo storico eventi di un canale.
- **`/log cerca utente`** — Mostra lo storico eventi di un utente.
- **`/log crea-canali`** — Crea una categoria privata con un canale per ogni tipo di log.
- **`/log crea-forum`** — Crea un forum privato per i log: un post per ogni tipo.
- **`/log esporta`** — Esporta lo storico eventi completo del server come file JSON.
- **`/log ignora`** — Sceglie cosa il log dei messaggi non registra (canali, utenti, prefissi).
- **`/log stato`** — Mostra dove vanno i log del server.

## Moderazione

- **`/mod avvisi azzera`** — Toglie tutti i warn attivi di un membro (serve «Gestire il server»).
- **`/mod avvisi classifica`** — I membri con più warn attivi.
- **`/mod avvisi togli`** — Toglie un singolo warn (per numero di caso).
- **`/mod caso classifica-staff`** — Classifica dei moderatori per numero di azioni, o casi di uno solo.
- **`/mod caso elimina`** — Elimina un caso (serve «Gestire il server»).
- **`/mod caso motivo`** — Cambia il motivo di un caso già registrato.
- **`/mod caso storico`** — Mostra lo storico casi di un membro.
- **`/mod caso vedi`** — Mostra i dettagli di un singolo caso.
- **`/mod clear`** — Cancella un numero di messaggi, con filtri opzionali.
- **`/mod lock`** — Blocca la possibilità di scrivere in un canale.
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

- **`/modban ban`** — Banna permanentemente un membro.
- **`/modban kick`** — Espelle un membro dal server.
- **`/modban softban`** — Banna e sbanna subito un membro, per cancellarne i messaggi recenti.
- **`/modban tempban`** — Banna un membro per una durata definita.
- **`/modban unban`** — Rimuove il ban da un utente.

## Moduli

- **`/moduli alert elenco`** — Mostra i feed seguiti da questo server.
- **`/moduli alert feed`** — Segui un feed RSS/Atom (YouTube, Reddit, o qualsiasi altro).
- **`/moduli alert rimuovi`** — Rimuove una sottoscrizione feed, Twitch o un webhook.
- **`/moduli alert twitch`** — Notifica quando uno streamer Twitch va live/offline.
- **`/moduli alert webhook`** — Crea un webhook custom: servizi terzi possono pubblicare in un canale.
- **`/moduli alert youtube-live`** — Notifica quando un canale YouTube va live (richiede YOUTUBE_API_KEY sul bot).

## Musica

- **`/music clear-queue`** — Svuota la coda, senza toccare la traccia in riproduzione.
- **`/music disconnect`** — Disconnette il music bot dal canale vocale.
- **`/music loop queue`** — Attiva/disattiva la ripetizione dell'intera coda.
- **`/music loop track`** — Attiva/disattiva la ripetizione della traccia corrente.
- **`/music nonstop off`** — Disattiva il loop continuo.
- **`/music nonstop on`** — Attiva il loop continuo sulla coda attuale.
- **`/music nowplaying`** — Mostra la traccia in riproduzione con una barra di avanzamento.
- **`/music pause`** — Mette in pausa la riproduzione.
- **`/music play`** — Riproduce una canzone o playlist.
- **`/music queue`** — Mostra la coda di riproduzione.
- **`/music resume`** — Riprende la riproduzione in pausa.
- **`/music shuffle`** — Mescola l'ordine delle tracce in coda.
- **`/music skip`** — Salta la traccia in riproduzione.
- **`/music stop`** — Ferma la riproduzione e svuota la coda.
- **`/music volume down`** — Diminuisce il volume.
- **`/music volume set`** — Imposta il volume a un valore specifico (0-200).
- **`/music volume up`** — Aumenta il volume.

## Sicurezza

- **`/security antinuke casi`** — Registro degli attacchi fermati: elenco o dettaglio di un caso.
- **`/security antinuke enable`** — Attiva o disattiva l'Anti-Nuke.
- **`/security antinuke guardie`** — Protezioni su azioni singole: permessi dei ruoli, ruoli ai membri, link, bot.
- **`/security antinuke limits`** — Configura la soglia di rilevamento per una categoria.
- **`/security antinuke punish-action`** — Cosa fare all'autore di un'azione distruttiva di massa.
- **`/security antinuke recovery`** — Attiva/disattiva la ricreazione automatica di canali/ruoli cancellati durante un attacco.
- **`/security antinuke rilascia`** — Toglie la quarantena all'autore di un caso e gli rimette i ruoli.
- **`/security antinuke status`** — Mostra la configurazione attuale dell'Anti-Nuke.
- **`/security antinuke trusted-add`** — Esenta un utente, un bot o un webhook dai controlli Anti-Nuke.
- **`/security antinuke trusted-list`** — Elenca chi è esentato dai controlli Anti-Nuke e con quali limiti.
- **`/security antinuke trusted-remove`** — Rimuove un utente, un bot o un webhook dalla lista fidati Anti-Nuke.
- **`/security antiraid account-age`** — Età minima dell'account per non essere considerato sospetto.
- **`/security antiraid alert-channel`** — Canale dove ricevere gli alert di sicurezza (Anti-Raid + Anti-Nuke).
- **`/security antiraid avatar-check`** — Attiva/disattiva il rilevamento avatar assente.
- **`/security antiraid enable`** — Attiva o disattiva l'Anti-Raid.
- **`/security antiraid join-rate`** — Configura il limite di join in un intervallo di tempo.
- **`/security antiraid lockdown-action`** — Cosa fare quando un raid viene rilevato.
- **`/security antiraid quarantine-hold`** — Impedisce a chi non è fidato di togliere la quarantena a mano.
- **`/security antiraid rilascia`** — Toglie la quarantena a un membro (il modo giusto, col blocco attivo).
- **`/security antiraid status`** — Mostra la configurazione attuale dell'Anti-Raid.
- **`/security antiraid username-check`** — Attiva/disattiva il rilevamento pattern username sospetti.
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
- **`/security score`** — Calcola il punteggio di sicurezza del server con consigli.
- **`/security spamtrap`** — Configura i canali trappola e log dello Spam Trap.
- **`/security verify blacklist-add`** — Aggiungi un utente alla blacklist.
- **`/security verify blacklist-remove`** — Rimuovi un utente dalla blacklist.
- **`/security verify panel`** — Pubblica il pannello di verifica.
- **`/security verify setup`** — Configura il Verify.
- **`/security verify whitelist-add`** — Aggiungi un utente alla whitelist.
- **`/security verify whitelist-remove`** — Rimuovi un utente dalla whitelist.

## Ticket

- **`/ticket add`** — Aggiungi un utente a questo ticket.
- **`/ticket claim`** — Prendi in carico questo ticket.
- **`/ticket close`** — Chiudi questo ticket.
- **`/ticket forceclose`** — Chiudi immediatamente questo ticket, senza attesa.
- **`/ticket priority`** — Imposta la priorità di questo ticket.
- **`/ticket remove`** — Rimuovi un utente da questo ticket.
- **`/ticket rename`** — Rinomina questo ticket.

## Utility

- **`/utility editsnipe`** — Mostra l'ultimo messaggio modificato in questo canale.
- **`/utility ping`** — Controlla se iYokai Main è online e la sua latenza.
- **`/utility poll`** — Crea un sondaggio (fino a 10 opzioni).
- **`/utility reactionsnipe`** — Mostra l'ultima reazione rimossa in questo canale.
- **`/utility reminder cancel`** — Annulla un promemoria.
- **`/utility reminder list`** — Mostra i tuoi promemoria in sospeso.
- **`/utility reminder set`** — Imposta un promemoria.
- **`/utility report`** — Segnala un utente allo staff del server.
- **`/utility richiedi-comando`** — Proponi un nuovo comando per il bot.
- **`/utility serverstats`** — Mostra le statistiche del server, con grafico di crescita.
- **`/utility snipe`** — Mostra l'ultimo messaggio cancellato in questo canale.
- **`/utility suggest`** — Proponi un'idea per questo server.

## Vocali

- **`/voice kick`** — Espelli un utente dal tuo canale.
- **`/voice limit`** — Imposta il limite di utenti del canale.
- **`/voice lock`** — Blocca il canale (nessun nuovo ingresso).
- **`/voice rename`** — Rinomina il tuo canale vocale.
- **`/voice transfer`** — Trasferisci la proprietà del canale.
- **`/voice unlock`** — Sblocca il canale.
