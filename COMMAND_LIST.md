# Elenco comandi — iYokai

Generato automaticamente da `scripts/generate_command_list.py` il 2026-09-27 19:25 UTC, interrogando l'albero comandi VERO del bot dopo aver caricato ogni cog — non un elenco scritto a mano. Da rigenerare dopo ogni commit che aggiunge, rimuove o rinomina un comando.

**Totale: 237 comandi in 10 categorie.**

## AutoMod

- **`/automod actions-set`** — Configura quali azioni eseguire quando un filtro avanzato scatta.
- **`/automod anti-attachment`** — Configura l'anti-attachment-spam (troppi allegati in poco tempo).
- **`/automod anti-caps`** — Configura l'anti-caps (troppo maiuscolo).
- **`/automod anti-link-domain`** — Aggiunge o rimuove un dominio dalla whitelist/blacklist link.
- **`/automod anti-link-mode`** — Imposta la modalità del filtro link.
- **`/automod anti-mention`** — Configura l'anti-mass-mention (troppi utenti taggati in un messaggio).
- **`/automod anti-spam-emoji`** — Configura l'anti-spam emoji (troppe emoji in un messaggio).
- **`/automod anti-spam-messages`** — Configura l'anti-spam messaggi (troppi messaggi in poco tempo).
- **`/automod anti-spam-sticker`** — Configura l'anti-spam sticker (troppi sticker in poco tempo).
- **`/automod anti-zalgo`** — Attiva o disattiva l'anti-zalgo (testo con segni diacritici anomali).
- **`/automod badword-add`** — Aggiunge una parola vietata.
- **`/automod badword-list`** — Mostra le parole vietate configurate.
- **`/automod badword-remove`** — Rimuove una parola vietata.
- **`/automod exempt-channel-add`** — Esenta un canale da tutti i filtri AutoMod avanzati.
- **`/automod exempt-channel-remove`** — Rimuove l'esenzione di un canale.
- **`/automod exempt-role-add`** — Esenta un ruolo da tutti i filtri AutoMod avanzati.
- **`/automod exempt-role-remove`** — Rimuove l'esenzione di un ruolo.
- **`/automod invites`** — Attiva o disattiva il blocco automatico degli inviti Discord.
- **`/automod log-channel`** — Imposta il canale dove pubblicare il log delle azioni AutoMod avanzate.
- **`/automod mute-duration`** — Imposta la durata del timeout usato dall'azione 'mute' dell'AutoMod.
- **`/automod status`** — Mostra la configurazione attuale dei filtri AutoMod avanzati.
- **`/automod sync`** — Forza una sincronizzazione manuale delle regole AutoMod.
- **`/escalation disable`** — [Admin] Disattiva l'escalation ladder.
- **`/escalation enable`** — [Admin] Attiva l'escalation ladder.
- **`/escalation remove-step`** — [Admin] Rimuove un livello dalla scala personalizzata.
- **`/escalation reset`** — [Admin] Azzera il conteggio infrazioni di un membro.
- **`/escalation set-reset-days`** — [Admin] Giorni di buona condotta per azzerare il conteggio.
- **`/escalation set-step`** — [Admin] Configura l'azione per un livello della scala.
- **`/escalation status`** — Mostra la scala di escalation configurata.

## Fun

- **`/rate`** — Valuta qualcosa da 0 a 10.
- **`/ship`** — Calcola la compatibilità tra due utenti.

## Leveling

- **`/assegna-lobby`** — [Admin] Premio partecipazione: assegna coin a chi è in vocale ORA, dalla cassa del server.
- **`/assegna-winner`** — [Admin] Premio vincitore: assegna coin a un membro, dalla cassa del server.
- **`/balance`** — Mostra i tuoi coin.
- **`/cassa saldo`** — Mostra il saldo della cassa del server.
- **`/cassa sblocca-premium`** — [Admin] Sblocca un mese di bot premium spendendo dalla cassa.
- **`/clan bacheca disable`** — [Admin] Disattiva l'annuncio automatico della top 3 gilde.
- **`/clan bacheca set`** — [Admin] Imposta il canale dove annunciare la top 3 gilde del mese.
- **`/clan boost gilda`** — [Capo/Admin Clan] Acquista un boost ×2 per 24h per TUTTI i membri, dalla tesoreria.
- **`/clan boost individuale`** — Acquista un boost personale ×2 per 24h sul tuo tick vocale di gilda.
- **`/clan classifica`** — Classifica delle gilde per XP (mensile o totale).
- **`/clan compra-canale`** — [Capo/Admin Clan] Sblocca un nuovo canale extra per la tua gilda.
- **`/clan crea`** — Crea una nuova gilda/clan.
- **`/clan espelli`** — [Capo/Admin Clan] Espelli un membro dalla tua gilda.
- **`/clan info`** — Mostra le informazioni di una gilda.
- **`/clan invita`** — [Capo/Admin Clan] Invita un membro nella tua gilda.
- **`/clan membri`** — Mostra i membri di una gilda.
- **`/clan promuovi`** — [Capo Clan] Cambia il ruolo di un membro della tua gilda.
- **`/clan sciogli`** — [Capo Clan] Sciogli la tua gilda.
- **`/clan tesoreria dona`** — Dona coin personali alla tesoreria della tua gilda.
- **`/clan tesoreria trasferisci`** — [Capo Clan] Trasferisci coin dalla tesoreria a un'altra TUA gilda (anche su un altro server).
- **`/daily`** — Riscuoti la ricompensa giornaliera.
- **`/giveaway`** — [Admin] Avvia un giveaway.
- **`/leaderboard`** — Mostra la classifica del server.
- **`/level-roles add`** — [Admin] Assegna un ruolo a chi raggiunge un livello.
- **`/level-roles list`** — [Admin] Mostra i ruoli-premio configurati su questo server.
- **`/level-roles remove`** — [Admin] Rimuove un ruolo-premio configurato.
- **`/monthly-winners disable`** — [Admin] Disattiva l'annuncio dei vincitori del mese.
- **`/monthly-winners set`** — [Admin] Imposta il canale dove annunciare i vincitori del mese.
- **`/pay`** — Trasferisci coin a un altro utente.
- **`/rank`** — Mostra il tuo livello e i tuoi coin.
- **`/shop add-item`** — [Admin] Aggiunge un oggetto allo shop.
- **`/shop buy`** — Acquista un oggetto dello shop.
- **`/shop list`** — Mostra gli oggetti disponibili nello shop.
- **`/shop remove-item`** — [Admin] Rimuove un oggetto dallo shop.
- **`/work`** — Lavora per guadagnare qualche coin.

## Logging

- **`/logs channel`** — [Admin] Mostra lo storico eventi di un canale.
- **`/logs export`** — [Admin] Esporta lo storico eventi completo del server come file JSON.
- **`/logs user`** — [Admin] Mostra lo storico eventi di un utente.
- **`/logs-setup`** — [Admin] Imposta il canale dei log del server.
- **`/logs-status`** — Mostra il canale di log configurato.

## Moderazione

- **`/ban`** — Banna permanentemente un membro.
- **`/clear`** — Cancella un numero di messaggi, con filtri opzionali.
- **`/kick`** — Espelle un membro dal server.
- **`/lock`** — Blocca la possibilità di scrivere in un canale.
- **`/mod-log-setup`** — [Admin] Imposta il canale dove arriva il log di ogni sanzione.
- **`/modcase history`** — Mostra lo storico casi di un membro.
- **`/modcase view`** — Mostra i dettagli di un singolo caso.
- **`/modnote add`** — Aggiunge una nota su un utente.
- **`/modnote list`** — Elenca le note su un utente.
- **`/mute-role`** — Silenzia un membro con un ruolo dedicato (alternativa al timeout).
- **`/report`** — Segnala un utente allo staff del server.
- **`/report-setup`** — [Admin] Imposta il canale delle segnalazioni.
- **`/slowmode`** — Imposta lo slowmode su un canale.
- **`/softban`** — Banna e sbanna subito un membro, per cancellarne i messaggi recenti.
- **`/tempban`** — Banna un membro per una durata definita.
- **`/timeout`** — Mette in timeout un membro (max 28 giorni).
- **`/unban`** — Rimuove il ban da un utente.
- **`/unlock`** — Sblocca la possibilità di scrivere in un canale.
- **`/unmute-role`** — Rimuove il ruolo mute da un membro.
- **`/untimeout`** — Rimuove il timeout da un membro.
- **`/warn`** — Assegna un warn a un membro.

## Music

- **`/clear-queue`** — Svuota la coda, senza toccare la traccia in riproduzione.
- **`/disconnect`** — Disconnette il music bot dal canale vocale.
- **`/loop queue`** — Attiva/disattiva la ripetizione dell'intera coda.
- **`/loop track`** — Attiva/disattiva la ripetizione della traccia corrente.
- **`/nonstop off`** — Disattiva il loop continuo.
- **`/nonstop on`** — Attiva il loop continuo sulla coda attuale.
- **`/nonstop-main add-local`** — [Admin] Aggiunge un file dalla cartella inediti alla playlist della radio.
- **`/nonstop-main add-track`** — [Admin] Aggiunge una traccia alla playlist della radio.
- **`/nonstop-main list-tracks`** — [Admin] Mostra la playlist della radio.
- **`/nonstop-main remove-track`** — [Admin] Rimuove una traccia dalla playlist della radio.
- **`/nonstop-main start`** — [Admin] Entra nella radio condivisa, nel punto in cui si trova ora.
- **`/nonstop-main stop`** — [Admin] Esce dalla radio su questo server.
- **`/nowplaying`** — Mostra la traccia in riproduzione con una barra di avanzamento.
- **`/pause`** — Mette in pausa la riproduzione.
- **`/play`** — Riproduce una canzone o playlist.
- **`/queue`** — Mostra la coda di riproduzione.
- **`/resume`** — Riprende la riproduzione in pausa.
- **`/shuffle`** — Mescola l'ordine delle tracce in coda.
- **`/skip`** — Salta la traccia in riproduzione.
- **`/stop`** — Ferma la riproduzione e svuota la coda.
- **`/volume down`** — Diminuisce il volume.
- **`/volume set`** — Imposta il volume a un valore specifico (0-200).
- **`/volume up`** — Aumenta il volume.

## Sicurezza

- **`/anti-nuke enable`** — Attiva o disattiva l'Anti-Nuke.
- **`/anti-nuke limits`** — Configura la soglia di rilevamento per una categoria.
- **`/anti-nuke punish-action`** — Cosa fare all'autore di un'azione distruttiva di massa.
- **`/anti-nuke recovery`** — Attiva/disattiva la ricreazione automatica di canali/ruoli cancellati durante un attacco.
- **`/anti-nuke status`** — Mostra la configurazione attuale dell'Anti-Nuke.
- **`/anti-nuke trusted-add`** — Esenta un utente/bot fidato da tutti i controlli Anti-Nuke.
- **`/anti-nuke trusted-remove`** — Rimuove un utente/bot dalla lista fidati Anti-Nuke.
- **`/anti-raid account-age`** — Età minima dell'account per non essere considerato sospetto.
- **`/anti-raid alert-channel`** — Canale dove ricevere gli alert di sicurezza (Anti-Raid + Anti-Nuke).
- **`/anti-raid avatar-check`** — Attiva/disattiva il rilevamento avatar assente.
- **`/anti-raid enable`** — Attiva o disattiva l'Anti-Raid.
- **`/anti-raid join-rate`** — Configura il limite di join in un intervallo di tempo.
- **`/anti-raid lockdown-action`** — Cosa fare quando un raid viene rilevato.
- **`/anti-raid status`** — Mostra la configurazione attuale dell'Anti-Raid.
- **`/anti-raid username-check`** — Attiva/disattiva il rilevamento pattern username sospetti.
- **`/global-ban disable`** — Abbandona la rete di ban globali.
- **`/global-ban enable`** — Aderisci alla rete di ban globali (propaga e ricevi).
- **`/global-ban status`** — Mostra lo stato e la storia recente del ban globale.
- **`/permission-heatmap`** — [Admin] Mostra quali ruoli hanno permessi critici e chi li possiede.
- **`/security-score`** — Calcola il punteggio di sicurezza del server con consigli.
- **`/spamtrap-setup`** — [Admin] Configura i canali trappola e log dello Spam Trap.
- **`/verify blacklist-add`** — [Admin] Aggiungi un utente alla blacklist.
- **`/verify blacklist-remove`** — [Admin] Rimuovi un utente dalla blacklist.
- **`/verify panel`** — [Admin] Pubblica il pannello di verifica.
- **`/verify setup`** — [Admin] Configura il Verify.
- **`/verify whitelist-add`** — [Admin] Aggiungi un utente alla whitelist.
- **`/verify whitelist-remove`** — [Admin] Rimuovi un utente dalla whitelist.

## Ticket

- **`/ticket add`** — Aggiungi un utente a questo ticket.
- **`/ticket claim`** — Prendi in carico questo ticket.
- **`/ticket close`** — Chiudi questo ticket.
- **`/ticket forceclose`** — [Staff] Chiudi immediatamente questo ticket, senza attesa.
- **`/ticket priority`** — Imposta la priorità di questo ticket.
- **`/ticket remove`** — Rimuovi un utente da questo ticket.
- **`/ticket rename`** — Rinomina questo ticket.
- **`/ticket-category add`** — [Admin] Aggiungi (o aggiorna) una categoria di ticket.
- **`/ticket-category list`** — [Admin] Elenca le categorie di ticket configurate.
- **`/ticket-category remove`** — [Admin] Rimuovi una categoria di ticket.
- **`/ticket-panel`** — [Admin] Pubblica il pannello per l'apertura dei ticket in questo canale.
- **`/ticket-setup`** — [Admin] Configura la categoria (e opzionalmente il ruolo di supporto) per i ticket.
- **`/ticket-stats`** — [Admin] Statistiche del sistema di ticket.
- **`/ticket-support-role add`** — [Admin] Aggiungi un ruolo di supporto.
- **`/ticket-support-role list`** — [Admin] Elenca i ruoli di supporto configurati.
- **`/ticket-support-role remove`** — [Admin] Rimuovi un ruolo di supporto.

## Utility

- **`/alerts add`** — [Admin] Segui un feed RSS/Atom (YouTube, Reddit, o qualsiasi altro).
- **`/alerts add-twitch`** — [Admin] Notifica quando uno streamer Twitch va live/offline.
- **`/alerts list`** — [Admin] Mostra i feed seguiti da questo server.
- **`/alerts remove`** — [Admin] Rimuove una sottoscrizione feed, Twitch o un webhook.
- **`/alerts webhook-create`** — [Admin] Crea un webhook custom: servizi terzi possono pubblicare in un canale.
- **`/config export`** — [Admin] Esporta la configurazione di questo server in un file.
- **`/config history`** — [Admin] Mostra le ultime modifiche alla configurazione.
- **`/config import`** — [Admin] Importa una configurazione da un file esportato con /config export.
- **`/config language set`** — [Admin] Imposta la lingua di questo server.
- **`/config language show`** — Mostra la lingua impostata per questo server.
- **`/config reset`** — [Admin] Azzera la configurazione di questo server.
- **`/config rollback`** — [Admin] Ripristina il valore precedente di una modifica.
- **`/configura-restore`** — [Admin] Scegli come questo server gestisce il restore utenti via OAuth2.
- **`/custom-command-requests-setup`** — [Owner] Imposta il canale delle richieste (solo nel server principale).
- **`/define-backup`** — [Admin] Accoda la creazione di un backup per questo server.
- **`/define-main`** — [Admin] Registra questo server come 'main' per il Backup System.
- **`/greetings boost-setup`** — [Admin] Configura il messaggio di boost.
- **`/greetings goodbye-setup`** — [Admin] Configura il messaggio di addio.
- **`/greetings preview`** — Mostra un'anteprima di come apparirebbe un messaggio.
- **`/greetings welcome-setup`** — [Admin] Configura il messaggio di benvenuto.
- **`/owner announce`** — [OWNER] Manda un annuncio a tutti i server.
- **`/owner blacklist-guild-add`** — [OWNER] Blocca globalmente un server (il bot ne uscirà se già presente).
- **`/owner blacklist-guild-list`** — [OWNER] Mostra i server bloccati globalmente.
- **`/owner blacklist-guild-remove`** — [OWNER] Rimuove un server dalla blacklist globale.
- **`/owner blacklist-user-add`** — [OWNER] Blocca globalmente un utente dall'uso del bot.
- **`/owner blacklist-user-list`** — [OWNER] Mostra gli utenti bloccati globalmente.
- **`/owner blacklist-user-remove`** — [OWNER] Rimuove un utente dalla blacklist globale.
- **`/owner cog-load`** — [OWNER] Carica un'estensione (es. cogs.moderation.actions).
- **`/owner cog-reload`** — [OWNER] Ricarica un'estensione già caricata.
- **`/owner cog-unload`** — [OWNER] Scarica un'estensione.
- **`/owner eval`** — [OWNER] Esegue codice Python (con conferma).
- **`/owner leave-guild`** — [OWNER] Forza il bot a lasciare un server specifico (senza bloccarlo).
- **`/owner memory-status`** — [OWNER] Mostra il consumo di RAM attuale del processo.
- **`/owner premium-grant`** — [OWNER] Concede un abbonamento mensile/annuale a un modulo per un server.
- **`/owner premium-list`** — [OWNER] Mostra lo stato premium di tutti i moduli.
- **`/owner premium-panel`** — [OWNER] Pannello interattivo per attivare/disattivare i moduli premium.
- **`/owner premium-revoke`** — [OWNER] Revoca l'abbonamento di un modulo per un server.
- **`/owner premium-status-all`** — [OWNER] Mostra lo stato premium di TUTTI i server in cui è presente il bot.
- **`/owner premium-subscriptions`** — [OWNER] Mostra gli abbonamenti per modulo attivi su un server.
- **`/owner premium-toggle`** — [OWNER] Accende o spegne la natura premium di un modulo.
- **`/owner shell`** — [OWNER] Esegue un comando shell (con conferma).
- **`/owner stats`** — [OWNER] Statistiche globali del bot.
- **`/owner whitelist-add`** — [OWNER] Aggiunge un server alla whitelist premium.
- **`/owner whitelist-list`** — [OWNER] Elenca i server nella whitelist premium.
- **`/owner whitelist-remove`** — [OWNER] Rimuove un server dalla whitelist premium.
- **`/ping`** — Controlla se iYokai Main è online e la sua latenza.
- **`/poll`** — Crea un sondaggio (fino a 5 opzioni).
- **`/promuovi-backup`** — [Admin] Promuove QUESTO server (finora backup) a nuovo main, se il main originale è perso.
- **`/reactionsnipe`** — Mostra l'ultima reazione rimossa in questo canale.
- **`/reminder cancel`** — Annulla un promemoria.
- **`/reminder list`** — Mostra i tuoi promemoria in sospeso.
- **`/reminder set`** — Imposta un promemoria.
- **`/request-custom-command`** — Proponi un nuovo comando per il bot.
- **`/restore-users`** — [Admin] Ripristina in QUESTO server gli utenti dell'ultimo snapshot di un altro server.
- **`/rolemenu add-option`** — [Admin] Aggiungi un'opzione a un role menu.
- **`/rolemenu create`** — [Admin] Crea un nuovo role menu.
- **`/rolemenu delete`** — [Admin] Elimina un role menu.
- **`/rolemenu remove-option`** — [Admin] Rimuovi un'opzione da un role menu.
- **`/schedule-message cancel`** — [Admin] Annulla un messaggio programmato.
- **`/schedule-message list`** — [Admin] Mostra i messaggi programmati di questo server.
- **`/schedule-message set`** — [Admin] Programma un messaggio.
- **`/search`** — Cerca un comando per descrizione.
- **`/serverstats`** — Mostra le statistiche del server, con grafico di crescita.
- **`/setup`** — [Admin] Attiva o disattiva i moduli del bot su questo server.
- **`/setup-wizard`** — [Admin] Configura passo-passo i moduli principali del bot.
- **`/sticky remove`** — [Admin] Rimuove lo sticky message di un canale.
- **`/sticky set`** — [Admin] Imposta lo sticky message di un canale.
- **`/suggest`** — Proponi un'idea per questo server.
- **`/suggestion-setup`** — [Admin] Imposta il canale dei suggerimenti.

## Canali Vocali Temporanei

- **`/voice kick`** — Espelli un utente dal tuo canale.
- **`/voice limit`** — Imposta il limite di utenti del canale.
- **`/voice lock`** — Blocca il canale (nessun nuovo ingresso).
- **`/voice rename`** — Rinomina il tuo canale vocale.
- **`/voice transfer`** — Trasferisci la proprietà del canale.
- **`/voice unlock`** — Sblocca il canale.
- **`/voicetemp-cap`** — [Admin] Imposta il numero massimo di vocali temporanei per categoria.
- **`/voicetemp-panel`** — [Admin] Pubblica il pannello per la creazione manuale di un vocale.
- **`/voicetemp-platform-setup`** — [Admin] Configura i ruoli informativi PC/Console/Mobile per i vocali temporanei.
- **`/voicetemp-setup`** — [Admin] Configura il canale generatore e la categoria dei vocali temporanei.
