# Catalogo — Statistiche

Statistiche di messaggi, vocale e attività; grafici; classifiche;
ruoli per attività; canali contatore; analisi di ingressi e uscite;
esportazioni. 61 voci. Bot letti: Statbot, ServerStats, Arcane,
Invite Tracker, Lawliet, NadekoBot, YAGPDB, MEE6.

Legenda: ❌ manca · 🟡 parziale. "Scheda": NF-xx = scheda di
`NUOVE_FUNZIONI.md`; M x.y = riga di `MODIFICHE_ESISTENTE.md`;
"nuova" = non c'è ancora in nessun piano.

iYokai oggi (per confronto): `/serverstats` (numeri del server e
grafico a barre della crescita giornaliera, che dipende dal modulo dei
log); storico eventi consultabile (`/logs user|channel|export`);
`/ticket-stats`; `/owner stats`. Nessun conteggio di messaggi o minuti
in vocale per canale o per membro, nessun canale contatore.

## 1. Statistiche di attività

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| STA-001 | Panoramica del server: messaggi, minuti in vocale, membri, in un periodo | Statbot (`/server`) [STATBOT] | 🟡 parziale: `/serverstats` mostra solo membri e crescita | `/utility serverstats`; conteggi aggregati per giorno | NF-25 |
| STA-002 | Statistiche dei messaggi del server | Statbot (`/messages`) [STATBOT], Invite Tracker (`/messages`, `/leaderboard messages`) [INVTR] | ❌ manca | Contatore per (server, canale, membro, giorno); non serve leggere il testo | NF-25 |
| STA-003 | Statistiche del vocale del server | Statbot (`/voice`) [STATBOT] | ❌ manca | Minuti per (server, canale, membro, giorno) dall'evento vocale già ascoltato | NF-25 |
| STA-004 | Statistiche di un canale | Statbot (`/channel`) [STATBOT] | ❌ manca | `/utility serverstats canale:…` | NF-25 |
| STA-005 | Statistiche di un membro (e le proprie) | Statbot (`/user`, `/me`) [STATBOT] | ❌ manca | `/utility statistiche [membro]`; dato personale (NF-04) | NF-25 |
| STA-006 | Tempo in vocale diviso per stato: muto, sordo, AFK | Statbot (filtri "Voice State") [STATBOT] | ❌ manca | L'anti-farm distingue già questi stati: salvarli come colonne | nuova |
| STA-007 | A cosa giocano i membri: le 10 attività più viste | Statbot (`/activity`, a pagamento) [STATBOT], NadekoBot (`.whosplaying`) [NADEKO] | ❌ manca | Serve l'intent delle presenze (approvazione da 10.000 utenti): bassa priorità | nuova |
| STA-008 | Numero di membri online, assenti, non disturbare nel tempo | Statbot (`/chart status`) [STATBOT] | ❌ manca | Come STA-007: intent delle presenze | nuova |
| STA-009 | Periodo a scelta ("lookback"): 7, 14, 30 giorni o più | Statbot (14 giorni gratis, di più a pagamento) [STATBOT], Invite Tracker (7/30 giorni gratis; 90 giorni, 1 anno, sempre premium) [INVTR] | ❌ manca | Opzione `periodo`; conservazione limitata (regola di pulizia, NF-04) | NF-25 |
| STA-010 | Bottoni sotto la risposta: aggiorna, passa al grafico, cambia periodo | Statbot (bottoni persistenti) [STATBOT] | ❌ manca | Vista persistente; 5 bottoni per riga | nuova |
| STA-011 | Statistiche di un canale o di un utente dal menu "tasto destro" | Statbot ("See channel's stats", "See user's stats") [STATBOT] | ❌ manca | Voci del menu contestuale (15 per tipo) | nuova |
| STA-012 | Statistiche pubbliche del server su una pagina web | YAGPDB (`/stats`, "public stats") [YAGPDB], Statbot (pannello) [STATBOT] | ❌ manca | Pagina del pannello web, con interruttore "pubblica" | NF-20 |
| STA-013 | Chi può vedere le statistiche, scelto per ruolo | Statbot ("Dashboard Access Control", "Command Access Level") [STATBOT] | ❌ manca | Con gli slash: delega dalle Integrazioni; nel pannello: ruoli ammessi | NF-20 |

## 2. Grafici e classifiche

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| STA-014 | Grafico dei messaggi nel tempo | Statbot (`/chart messages`) [STATBOT] | ❌ manca | Pillow, come il grafico di `/serverstats`; `defer()` | NF-25 |
| STA-015 | Grafico del vocale nel tempo | Statbot (`/chart voice`) [STATBOT] | ❌ manca | Stesso disegno | NF-25 |
| STA-016 | Grafico di un canale | Statbot (`/chart channel`) [STATBOT] | ❌ manca | Stesso disegno | NF-25 |
| STA-017 | Grafico di un utente | Statbot (`/chart user`) [STATBOT] | ❌ manca | Stesso disegno | NF-25 |
| STA-018 | Grafico del numero di membri | Statbot (`/chart member`) [STATBOT] | 🟡 parziale: c'è la crescita giornaliera a barre | Aggiungere la linea del totale | NF-25 |
| STA-019 | Grafico di ingressi, uscite e dei due insieme | Invite Tracker (`/stats joins`, `/stats leaves`, `/stats combined`) [INVTR] | 🟡 parziale: solo la crescita netta | Due serie nello stesso grafico | nuova |
| STA-020 | Classifica dei membri per messaggi | Statbot (`/top`, pagina "Top Message Users") [STATBOT], Invite Tracker [INVTR] | ❌ manca | `/level leaderboard tipo:messaggi` | NF-25 |
| STA-021 | Classifica dei membri per tempo in vocale | Statbot (pagina "Top Voice Users") [STATBOT] | ❌ manca | `/level leaderboard tipo:vocale` | NF-25 |
| STA-022 | Classifica dei canali più attivi (testo e vocale) | Statbot (pagine "Top Message Channels", "Top Voice Channels") [STATBOT] | ❌ manca | `/utility serverstats classifica:canali` | NF-25 |
| STA-023 | Classifica limitata a un ruolo | Invite Tracker (opzione `@role`) [INVTR] | ❌ manca | Filtro `ruolo` | nuova |
| STA-024 | Classifica per ore del giorno e giorni della settimana | Statbot ("by hour, day, week, month") [STATBOT] | ❌ manca | Aggregazione per ora: tabella più grande, da valutare | nuova |

## 3. Filtri e privacy

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| STA-025 | Canali esclusi dalle statistiche (o solo alcuni inclusi), anche per categoria | Statbot (`/filter channels add`, `remove`, `type whitelist`, `type blacklist`) [STATBOT] | ❌ manca | `/admin statistiche canali`; stessa logica di LIV-020 | NF-25 |
| STA-026 | Membri esclusi dalle statistiche | Statbot (`/filter members add`, `remove`) [STATBOT] | ❌ manca | Elenco di esclusi (es. i bot) | NF-25 |
| STA-027 | Ruoli inclusi o esclusi dalle statistiche | Statbot (`/filter roles whitelist`, `blacklist`; a pagamento) [STATBOT] | ❌ manca | Due elenchi | nuova |
| STA-028 | Ogni utente può rendersi anonimo nelle statistiche | Statbot (`/privacy`: vale anche per i dati passati) [STATBOT] | ❌ manca | `/utility privacy statistiche`; nelle classifiche compare "utente anonimo" | NF-04 |
| STA-029 | Diagnosi: perché le statistiche non si contano | Statbot (`/diag`) [STATBOT], ServerStats (`/check`, `/debug`) [SSTATS] | ❌ manca | `/admin statistiche diagnosi`: permessi mancanti, canali esclusi, modulo spento | nuova |

## 4. Ruoli per attività

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| STA-030 | Ruolo dato a chi supera una soglia di attività in un periodo | Statbot ("Statroles") [STATBOT] | ❌ manca | `/admin statistiche ruolo`; lavoro orario; `check_role_assignable` | NF-25 |
| STA-031 | Ruolo tolto a chi smette di essere attivo | Statbot [STATBOT] | ❌ manca | Stesso lavoro: ricalcolo sul periodo mobile | NF-25 |
| STA-032 | Soglie su messaggi, su minuti in vocale o su tutti e due | Statbot ("customizable conditions") [STATBOT] | ❌ manca | Regola con più condizioni | NF-25 |

## 5. Canali contatore

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| STA-033 | Canale che mostra il numero di membri | ServerStats [SSTATS], Arcane [ARCANE], Statbot ("Statdocks") [STATBOT], Lawliet (`%Members`) [LAWLIET], MEE6 (premium) [MEE6] | ❌ manca | `/admin contatori crea`; rinomina al massimo ogni 10 minuti (LIM-3) | NF-16 |
| STA-034 | Solo gli utenti veri, senza i bot | Arcane ("Users") [ARCANE], Lawliet (`%Users`) [LAWLIET] | ❌ manca | Tipo di contatore | NF-16 |
| STA-035 | Numero di bot | Arcane [ARCANE], Lawliet (`%Bots`) [LAWLIET] | ❌ manca | Tipo di contatore | NF-16 |
| STA-036 | Numero di boost e livello di boost | Arcane ("Nitro Boosts", "Nitro Boost Tier") [ARCANE], Lawliet (`%Boosts`) [LAWLIET] | ❌ manca | Tipo di contatore | NF-16 |
| STA-037 | Membri online (stima) e offline | Arcane ("Estimated Online", "Estimated Offline") [ARCANE] | ❌ manca | `approximate_presence_count` del server: non serve l'intent delle presenze | NF-16 |
| STA-038 | Membri che hanno (o non hanno) un certo ruolo | Arcane ("Members with Role", "Members without Role") [ARCANE] | ❌ manca | Tipo con parametro `ruolo` | nuova |
| STA-039 | Numero di ruoli, canali (per tipo) ed emoji | Arcane (ruoli, canali di testo, vocali, categorie, annunci, palco, emoji) [ARCANE] | ❌ manca | Tipi semplici, letti dalla memoria del bot | nuova |
| STA-040 | Contatore "obiettivo": 950 su 1000, con traguardi successivi | Arcane (premium; traguardi separati da virgola) [ARCANE], ServerStats (`/goal`) [SSTATS], Statbot [STATBOT] | ❌ manca | Segnaposto `{obiettivo}`; elenco di traguardi | NF-16 |
| STA-041 | Testo libero intorno al numero | Arcane (`{count}`) [ARCANE], Lawliet ("Name Mask") [LAWLIET], ServerStats (basta rinominare il canale) [SSTATS], NadekoBot (`.livechadd` con modello) [NADEKO] | ❌ manca | Modello con `{numero}`; nome ≤ 100 caratteri | NF-16 |
| STA-042 | Numeri abbreviati (1,21K) o per esteso (1.211) | ServerStats [SSTATS] | ❌ manca | Opzione `formato` | nuova |
| STA-043 | Canale di sola scritta, senza numero | Arcane ("Static") [ARCANE] | ❌ manca | Tipo "testo fisso" (serve da titolo della categoria) | nuova |
| STA-044 | Orologio o conto alla rovescia nel nome del canale | Statbot ("Clock counters", "countdowns") [STATBOT] | ❌ manca | Aggiornamento ogni 10 minuti al massimo: mostrare solo ore e minuti a scatti di 10 | nuova |
| STA-045 | Contatori "social": iscritti YouTube, follower Twitch… | ServerStats (`/social`) [SSTATS], MEE6 ("Social channel stats counters", premium) [MEE6], Statbot [STATBOT] | ❌ manca | Twitch e YouTube con le chiavi già usate dagli alert; quote da rispettare | nuova |
| STA-046 | Contatori "gioco": giocatori online di un server di gioco | ServerStats (`/game`) [SSTATS] | ❌ manca | Adatto a una community di gioco; dipende dal gioco (protocollo di query) | nuova |
| STA-047 | Contatori dei ticket (aperti, chiusi) | ServerStats ("ticket stats") [SSTATS] | ❌ manca | Dati già in `/ticket-stats` | nuova |
| STA-048 | Più contatori in un solo canale | Statbot [STATBOT] | ❌ manca | Modello con più segnaposto | nuova |
| STA-049 | Categoria dei contatori creata e gestita dal bot | ServerStats (`/category`, `/setup` con modelli) [SSTATS], Arcane (creazione in blocco "Members & Users") [ARCANE], Statbot (`/counter Setup Quick`) [STATBOT] | ❌ manca | Passo del wizard; canali vocali bloccati a tutti; 50 canali per categoria | NF-16 |
| STA-050 | Elenco, modifica e cancellazione dei contatori | ServerStats (`/counter`) [SSTATS], Statbot (`/counter Manage`) [STATBOT], NadekoBot (`.livechlist`, `.livechremove`) [NADEKO] | ❌ manca | `/admin contatori elenco`, `elimina` | NF-16 |
| STA-051 | Azzerare tutti i contatori in un colpo | ServerStats (`/reset`) [SSTATS] | ❌ manca | Comando con conferma | nuova |
| STA-052 | Canale di benvenuto come contatore ("ultimo arrivato: …") | ServerStats (`/welcome`) [SSTATS] | ❌ manca | Tipo "ultimo membro entrato" | nuova |

## 6. Ingressi, uscite, esportazioni

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| STA-053 | Percentuale di membri rimasti dopo l'ingresso ("retention") | Invite Tracker (pannello "Analytics") [INVTR], Lawliet (rimasti attivi dopo 7 giorni) [LAWLIET] | ❌ manca | Calcolo dai log di ingresso e uscita già salvati | nuova |
| STA-054 | Da dove arrivano i nuovi membri: invito, link personalizzato del server, sconosciuto | Invite Tracker ("Join sources") [INVTR] | 🟡 parziale: l'invito usato è nel log, senza riepilogo | Riepilogo per fonte in `/utility serverstats` | nuova |
| STA-055 | Inviti e invitanti migliori del periodo | Invite Tracker ("Top invites", "Top inviters", premium) [INVTR] | ❌ manca | Vedi UTL-164 | NF-27 |
| STA-056 | Esportare le statistiche in CSV | Invite Tracker (premium) [INVTR], Statbot (`/info roles`: membri di un ruolo in CSV) [STATBOT] | 🟡 parziale: `/logs export` esporta gli eventi in JSON | Opzione `formato: csv` | nuova |
| STA-057 | Esportare tutti i dati che il bot ha sul server | ServerStats (`/data`) [SSTATS] | 🟡 parziale: `/config export` e `/logs export` | Unico comando di esportazione | NF-04 |
| STA-058 | Esportare l'elenco dei membri in un file | ServerStats (`/members`) [SSTATS] | ❌ manca | Vedi UTL-201 | nuova |
| STA-059 | Scheda di un invito o di un'emoji | ServerStats (`/inviteinfo`, `/emojiinfo`) [SSTATS] | ❌ manca | `/utility invito-info`, `/utility emoji-info` | nuova |
| STA-060 | ID del server e delle sue risorse | Statbot (`/info id`) [STATBOT], NadekoBot (`.serverid`, `.channelid`, `.roleid`, `.userid`) [NADEKO] | ❌ manca | Discord lo fa già con la modalità sviluppatore: bassa priorità | nuova |
| STA-061 | Accesso ai dati tramite API per altri programmi | Statbot ("Statbot API") [STATBOT] | ❌ manca | Solo dopo il pannello web; chiavi per server | NF-20 |

## Fonti

Lette il 5/10/2026.

- `[STATBOT]` Statbot — https://docs.statbot.net · `/docs/usage/commands/overview` · `/docs/usage/commands/stats` · `/docs/usage/commands/management` · `/docs/guide/welcome` · `/docs/guide/settings` · https://top.gg/bot/491769129318088714
- `[SSTATS]` ServerStats — https://serverstats.bot/ · https://serverstats.bot/commands · https://serverstats.bot/setup
- `[ARCANE]` Arcane — https://docs.arcane.bot/plugins/counters · https://docs.arcane.bot/plugins/counters/setup · https://docs.arcane.bot/premium
- `[INVTR]` Invite Tracker — https://docs.invite-tracker.com/dashboard/analytics · https://docs.invite-tracker.com/commands/general · `/commands/administration`
- `[LAWLIET]` Lawliet — sorgente ufficiale https://github.com/Aninoss/lawliet-bot (`configuration_en_us.properties`, voci `mcdisplays_*` e `invitetracking_*`)
- `[NADEKO]` NadekoBot — sorgente ufficiale https://github.com/Kwoth/NadekoBot
- `[YAGPDB]` YAGPDB — https://help.yagpdb.xyz/docs/core/all-commands/
- `[MEE6]` MEE6 — https://help.mee6.xyz/en/articles/710936-mee6-free-vs-premium-plans-comparison

Non letti su fonte ufficiale:
- **Statbot**: i dettagli delle condizioni degli Statroles e i tipi di
  Statdock non sono elencati nelle pagine lette; i limiti a pagamento
  sono citati solo in parte.
- **ServerStats**: l'elenco dei singoli tipi di contatore (`/counter
  list`) si vede solo dentro Discord.

## Conteggio

61 righe: 55 ❌ e 6 🟡.
