# Elenco comandi — iYokai

Generato automaticamente da `scripts/generate_command_list.py` il 2026-09-21 03:30 UTC, interrogando l'albero comandi VERO del bot dopo aver caricato ogni cog — non un elenco scritto a mano. Da rigenerare dopo ogni commit che aggiunge, rimuove o rinomina un comando.

**Totale: 120 comandi in 9 categorie.**

## AutoMod

- **`/automod badword-add`** — Aggiunge una parola vietata.
- **`/automod badword-list`** — Mostra le parole vietate configurate.
- **`/automod badword-remove`** — Rimuove una parola vietata.
- **`/automod invites`** — Attiva o disattiva il blocco automatico degli inviti Discord.
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

- **`/balance`** — Mostra i tuoi coin.
- **`/daily`** — Riscuoti la ricompensa giornaliera.
- **`/leaderboard`** — Mostra la classifica del server.
- **`/pay`** — Trasferisci coin a un altro utente.
- **`/rank`** — Mostra il tuo livello e i tuoi coin.
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

## Sicurezza

- **`/permission-heatmap`** — [Admin] Mostra quali ruoli hanno permessi critici e chi li possiede.
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
- **`/ticket priority`** — Imposta la priorità di questo ticket.
- **`/ticket remove`** — Rimuovi un utente da questo ticket.
- **`/ticket rename`** — Rinomina questo ticket.
- **`/ticket-panel`** — [Admin] Pubblica il pannello per l'apertura dei ticket in questo canale.
- **`/ticket-setup`** — [Admin] Configura la categoria (e opzionalmente il ruolo di supporto) per i ticket.

## Utility

- **`/alerts add`** — [Admin] Segui un feed RSS/Atom (YouTube, Reddit, o qualsiasi altro).
- **`/alerts list`** — [Admin] Mostra i feed seguiti da questo server.
- **`/alerts remove`** — [Admin] Rimuove una sottoscrizione feed.
- **`/config history`** — [Admin] Mostra le ultime modifiche alla configurazione.
- **`/config rollback`** — [Admin] Ripristina il valore precedente di una modifica.
- **`/custom-command-requests-setup`** — [Owner] Imposta il canale delle richieste (solo nel server principale).
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
- **`/owner premium-list`** — [OWNER] Mostra lo stato premium di tutti i moduli.
- **`/owner premium-panel`** — [OWNER] Pannello interattivo per attivare/disattivare i moduli premium.
- **`/owner premium-toggle`** — [OWNER] Accende o spegne la natura premium di un modulo.
- **`/owner shell`** — [OWNER] Esegue un comando shell (con conferma).
- **`/owner stats`** — [OWNER] Statistiche globali del bot.
- **`/owner whitelist-add`** — [OWNER] Aggiunge un server alla whitelist premium.
- **`/owner whitelist-remove`** — [OWNER] Rimuove un server dalla whitelist premium.
- **`/ping`** — Controlla se iYokai Main è online e la sua latenza.
- **`/poll`** — Crea un sondaggio (fino a 5 opzioni).
- **`/reminder cancel`** — Annulla un promemoria.
- **`/reminder list`** — Mostra i tuoi promemoria in sospeso.
- **`/reminder set`** — Imposta un promemoria.
- **`/request-custom-command`** — Proponi un nuovo comando per il bot.
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
- **`/voicetemp-panel`** — [Admin] Pubblica il pannello per la creazione manuale di un vocale.
- **`/voicetemp-setup`** — [Admin] Configura il canale generatore e la categoria dei vocali temporanei.
