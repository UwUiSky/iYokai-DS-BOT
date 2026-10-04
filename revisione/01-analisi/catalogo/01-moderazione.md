# Catalogo — Moderazione

Ogni riga è una funzione o un comando di moderazione manuale che i grandi bot hanno e iYokai non ha (❌) o ha solo in parte (🟡).
Bot letti: Carl-bot, Dyno, YAGPDB, Zeppelin, Wick, ProBot, MEE6, Lawliet. Le cose che iYokai ha già per intero non sono elencate.
Stato di iYokai preso da `SPEC.md` §5, `COMMAND_LIST.md` e dal codice in `cogs/moderation/`. I comandi proposti usano i gruppi futuri `/mod`, `/modban`, `/admin`.

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| MOD-001 | Ban di un utente che **non è nel server**, dato per ID ("hackban") | Carl-bot [CARL], Wick `?h` [WICK], YAGPDB `banid` [YAGPDB], Zeppelin `forceban` [ZEPPELIN] | 🟡 parziale: `/ban` accetta solo un membro presente | `/modban ban` con opzione di tipo Utente (non Membro) e `guild.ban(discord.Object(id))`; motivo fino a 512 caratteri | nuova |
| MOD-002 | Ban di **più utenti in un solo comando** (lista di ID) | Carl-bot `massban`, 2 usi all'ora [CARL]; Zeppelin `massban` [ZEPPELIN]; Wick, più bersagli [WICK] | ❌ manca | `/modban massa`: finestra con un campo di testo (4000 caratteri) per gli ID; `defer()`, pausa tra un ban e l'altro, riepilogo in file; tetto di usi all'ora | nuova |
| MOD-003 | Sban di più utenti in un solo comando | Zeppelin `massunban` [ZEPPELIN] | ❌ manca | Stessa finestra di MOD-002 con scelta "banna / sbanna" | nuova |
| MOD-004 | Kick di più membri in un solo comando | Wick [WICK], Lawliet [LAWLIET] | ❌ manca | Menu di selezione utenti (fino a 25) dopo `/modban kick`, oppure la finestra di MOD-002 | nuova |
| MOD-005 | Timeout o mute di più membri in un solo comando | Zeppelin `massmute` [ZEPPELIN], Wick [WICK], Lawliet [LAWLIET] | ❌ manca | `/mod timeout` con menu di selezione utenti (25 al massimo); un caso per membro | nuova |
| MOD-006 | Warn dato a più membri in un solo comando | Wick [WICK], Lawliet [LAWLIET] | ❌ manca | `/mod warn dai` con menu di selezione utenti; stesso motivo per tutti | nuova |
| MOD-007 | Kick o ban di **tutti i membri entrati negli ultimi X minuti** | Lawliet `newkick`, `newban` [LAWLIET] | ❌ manca | `/modban recenti minuti:` con anteprima del numero e conferma a due passi; `defer()`; utile dopo un raid | nuova |
| MOD-008 | Ban segnato "senza appello" | Dyno, opzione `no_appeal` [DYNO] (terzi) | ❌ manca | Opzione `appello: sì/no` su `/modban ban`, letta dal flusso degli appelli | NF-30 |
| MOD-009 | Tempban con cancellazione dei messaggi recenti | Carl-bot `tempban [days]` [CARL] | 🟡 parziale: `/tempban` non ha l'opzione giorni (c'è solo su `/ban` e `/softban`) | Aggiungere `giorni_messaggi` 0–7 a `/modban tempban` (Discord: massimo 7 giorni) | nuova |
| MOD-010 | Valore **predefinito del server** per i giorni di messaggi cancellati al ban | Wick `misc 2b` [WICK], YAGPDB [YAGPDB], Zeppelin `ban_delete_message_days` [ZEPPELIN] | ❌ manca | Impostazione in `/admin config` usata quando l'opzione non è scritta; valore 0–7 | nuova |
| MOD-011 | Al kick, cancellare gli ultimi N messaggi dell'utente nel canale | YAGPDB, opzione `-cl` e interruttore "ultimi 100" [YAGPDB] | ❌ manca | Opzione `pulisci` su `/modban kick`; `purge` di 100 messaggi al massimo, non più vecchi di 14 giorni | nuova |
| MOD-012 | **Cambiare la durata** di un mute o ban già dato | Dyno `/duration case_id` [DYNO] (terzi); Zeppelin, aggiornamento del mute [ZEPPELIN] | ❌ manca | `/mod caso durata numero: nuova_durata:`; aggiorna la riga dello scheduler; nota nel caso | nuova |
| MOD-013 | Elenco delle **sanzioni a tempo ancora attive** (mute, tempban) | Dyno `/moderations` [DYNO] (terzi), Zeppelin `mutes` [ZEPPELIN] | ❌ manca | `/mod caso attivi`: legge lo scheduler; lista paginata, 10 per pagina | nuova |
| MOD-014 | Mute con ruolo **a tempo** (si toglie da solo) | Carl-bot `mute [duration]` [CARL], YAGPDB [YAGPDB], MEE6 `tempmute` [MEE6], Lawliet [LAWLIET] | 🟡 parziale: `/mute-role` è senza durata | Opzione `durata` su `/mod mute`; rimozione con lo scheduler; tetto di 5 anni (M 1.9) | nuova |
| MOD-015 | "Hardmute": mute che **toglie tutti i ruoli** e li ridà alla fine | Carl-bot `hardmute` [CARL]; YAGPDB "togli ruoli durante il mute" [YAGPDB]; Zeppelin `remove_roles_on_mute`, `restore_roles_on_mute` [ZEPPELIN]; Wick `misc 2i` [WICK] | ❌ manca | Opzione `togli_ruoli` su `/mod mute`; ruoli salvati in tabella; al ripristino `check_role_assignable`; saltare i ruoli gestiti | nuova |
| MOD-016 | Comando manuale di **quarantena / jail**: toglie i ruoli, dà un ruolo "prigione", anche a tempo, con rilascio | Wick `quarantine`, `unquarantine` [WICK]; Lawliet `jail`, `unjail` [LAWLIET] | 🟡 parziale: il ruolo Quarantined esiste ma lo dà solo l'anti-raid | `/mod quarantena metti` e `togli`; riusa il ruolo dell'anti-raid; ruoli tolti salvati per ridarli | M 3.5 |
| MOD-017 | Durata predefinita di timeout e mute quando il moderatore non la scrive | YAGPDB (timeout 10 minuti di default, mute configurabile) [YAGPDB], Wick `misc 2c` [WICK] | ❌ manca: in `/timeout` la durata è obbligatoria | Impostazione in `/admin config`; opzione `durata` facoltativa; massimo 28 giorni per il timeout | nuova |
| MOD-018 | Scegliere un ruolo esistente come ruolo mute, o farlo creare con un nome scelto | Carl-bot `/muterole create`, `/muterole set` [CARL]; Lawliet [LAWLIET] | 🟡 parziale: il ruolo "Muted" nasce da solo, non si sceglie | `/admin config muto ruolo:`; controllare che stia sotto il ruolo del bot | M 1.7 |
| MOD-019 | Riapplicare i permessi del ruolo mute a tutti i canali con un comando | Carl-bot `/muterole update` [CARL]; Lawliet "enforce mute role" [LAWLIET] | ❌ manca: i canali creati dopo restano scoperti | `/admin config muto aggiorna`; `defer()`; fino a 500 canali, con pause | M 1.7 |
| MOD-020 | Il mute blocca anche le reazioni | YAGPDB "Disallow Adding Reactions when muted" [YAGPDB] | ❌ manca | Negare `add_reactions` nel ruolo mute | M 1.7 |
| MOD-021 | Mute che **resta se l'utente esce e rientra** | Zeppelin (ruolo mute riapplicato al rientro; `forcemute` anche su chi non è nel server) [ZEPPELIN] | ❌ manca: nessun controllo all'ingresso | Ascoltare `on_member_join` e ridare il ruolo se c'è un mute attivo in tabella | nuova |
| MOD-022 | Mute e sordina **in vocale** (mute, deafen e i loro contrari) | Dyno `/deafen` [DYNO] (terzi); ProBot `mute voice`, `unmute voice` [PROBOT] | ❌ manca | Sotto-gruppo `/mod voce` con `muta`, `smuta`, `sordina`; `member.edit(mute=…, deafen=…)`; funziona solo se il membro è in vocale | nuova |
| MOD-023 | Scollegare un membro da un canale vocale qualsiasi | ProBot `vkick` [PROBOT], Zeppelin `vcdisconnect` [ZEPPELIN] | 🟡 parziale: `/voice kick` vale solo nel proprio vocale temporaneo | `/mod voce scollega`; `member.move_to(None)` | nuova |
| MOD-024 | Spostare un membro in un altro canale vocale | ProBot `move` [PROBOT], Zeppelin `vcmove` [ZEPPELIN] | ❌ manca | `/mod voce sposta membro: canale:` | nuova |
| MOD-025 | Spostare **tutti** i membri di un vocale in un altro | Zeppelin `vcmoveall` [ZEPPELIN] | ❌ manca | `/mod voce sposta-tutti da: a:`; `defer()`; una chiamata per membro | nuova |
| MOD-026 | Al mute, scollegare dal vocale o spostare in un canale scelto | Zeppelin `kick_from_voice_channel`, `move_to_voice_channel` [ZEPPELIN] | ❌ manca | Due impostazioni lette da `/mod mute` | nuova |
| MOD-027 | **Elenco dei warn** di un membro o di tutto il server | Carl-bot `warns` [CARL], YAGPDB `/warnings list` [YAGPDB], MEE6 `/infractions` [MEE6], ProBot `warnings` [PROBOT], Lawliet `warnlog` [LAWLIET] | 🟡 parziale: i warn si vedono solo dentro `/modcase history` | `/mod warn elenco [membro]`; pagine da 10; righe tagliate (M 1.6) | nuova |
| MOD-028 | **Togliere un singolo warn** | Carl-bot `removewarning` [CARL], Dyno `/delwarn` [DYNO] (terzi), YAGPDB `/warnings delete` [YAGPDB], ProBot `warn_remove` [PROBOT], Lawliet `warnremove` [LAWLIET] | ❌ manca | `/mod warn togli numero:`; il caso resta nello storico, segnato come annullato; aggiorna il conteggio delle soglie | nuova |
| MOD-029 | Azzerare tutti i warn di un membro | Carl-bot `clearwarnings` [CARL], Dyno `/clearwarn` [DYNO] (terzi), YAGPDB `/warnings clear` [YAGPDB], MEE6 `/clear-all-infractions` [MEE6] | ❌ manca (c'è solo `/escalation reset` per l'AutoMod) | `/mod warn azzera membro:` con conferma | nuova |
| MOD-030 | Azzerare i warn di **tutto il server** | MEE6 `/clear-all-infractions` senza membro [MEE6], ProBot `warn_remove` [PROBOT] | ❌ manca | Opzione `tutti` di `/mod warn azzera`, con conferma a due passi | nuova |
| MOD-031 | Classifica dei membri con più warn | YAGPDB `/warnings top` [YAGPDB] | ❌ manca | `/mod warn classifica`; risposta effimera, 10 righe | nuova |
| MOD-032 | **Punizione automatica dopo N warn dati a mano** | Carl-bot `threshold` + `warnpunish` [CARL]; Wick `misc 3b`, `3c` [WICK]; Lawliet auto mute, jail, kick, ban [LAWLIET]; MEE6 [MEE6] | 🟡 parziale: la scala `/escalation` vale solo per l'AutoMod | Estendere la scala ai warn manuali | M 1.10 |
| MOD-033 | Soglie di warn contate **in una finestra di tempo** ("N negli ultimi X giorni") | Lawliet [LAWLIET]; MEE6 (2 in 24 ore, 5 in 7 giorni, 10 in 14 giorni) [MEE6] | ❌ manca: c'è solo l'azzeramento dopo giorni di buona condotta | Colonna `finestra_giorni` per gradino della scala; conteggio con una query sulla data | M 1.10 |
| MOD-034 | Durata scelta per la punizione automatica (mute o ban a tempo, o permanente) | Lawliet [LAWLIET], MEE6 [MEE6] | 🟡 parziale: `/automod mute-duration` è una sola durata per tutto | Durata per gradino in `/security escalation set-step` | M 1.10 |
| MOD-035 | Warn azzerati dopo che la punizione automatica è scattata | Wick [WICK] | ❌ manca | Interruttore nella scala; azzera il conteggio, non i casi | M 1.10 |
| MOD-036 | Avviso allo staff, senza punire, quando si avvisa un utente che ha già N warn | Zeppelin `warn_notify_enabled`, `warn_notify_threshold` [ZEPPELIN] | ❌ manca | Riga in più nella risposta di `/mod warn dai` se il conteggio supera la soglia | nuova |
| MOD-037 | **Modificare il motivo** di un caso o di un warn dopo averlo dato | Carl-bot `/modlog reason` [CARL]; YAGPDB `/reason`, `/warnings edit` [YAGPDB]; Wick `cases ?e ?r` [WICK]; Zeppelin `update` [ZEPPELIN] | ❌ manca | `/mod caso motivo numero: testo:` (3–512 caratteri); aggiorna anche il messaggio nel canale mod-log | nuova |
| MOD-038 | **Prova allegata** (immagine o file) a un caso o a una nota | Wick, opzione `proof:` [WICK]; Zeppelin, allegati su motivo e nota [ZEPPELIN] | ❌ manca | Opzione `prova` di tipo allegato; il file va ricaricato nel canale mod-log (i link degli allegati scadono); file sotto 10 MiB | nuova |
| MOD-039 | Classifica dei moderatori per numero di azioni | Carl-bot `/modlog highscores` [CARL] | ❌ manca | `/mod caso classifica-staff`; effimera; solo conteggi (in `BACKLOG.md` la classifica pubblica dello staff è respinta) | nuova |
| MOD-040 | Statistiche di un singolo moderatore | Dyno `/modstats` [DYNO] (terzi) | ❌ manca | `/mod caso staff moderatore:`; conteggi per tipo e per periodo | nuova |
| MOD-041 | Casi fatti **da un moderatore**, filtrabili per tipo | Wick `modcases` [WICK], Zeppelin `cases -mod` [ZEPPELIN] | ❌ manca | Opzione `moderatore` su `/mod caso storico` | nuova |
| MOD-042 | Storico dei casi di un membro **filtrato per tipo** (ban, kick, warn, mute, note) | Wick `cases ?t` [WICK], Zeppelin, filtri di `cases` [ZEPPELIN] | ❌ manca | Opzione `tipo` con scelte fisse su `/mod caso storico` | nuova |
| MOD-043 | Esportare i casi di un membro in un file di testo | Carl-bot `/modlog export` [CARL] | ❌ manca (`/logs export` esporta gli eventi, non i casi di un membro) | `/mod caso esporta membro:`; file `.txt` sotto 10 MiB | nuova |
| MOD-044 | Eliminare un caso | Zeppelin `deletecase` [ZEPPELIN] | ❌ manca | `/mod caso elimina numero:` con conferma; solo amministratori; riga nel log | nuova |
| MOD-045 | Nascondere un caso (resta in archivio ma non conta) e riattivarlo | Zeppelin `hidecase`, `unhidecase` [ZEPPELIN]; Wick `cases ?e ?off`, `?on` [WICK] | ❌ manca | Colonna `attivo` sul caso; `/mod caso nascondi` e `mostra` | nuova |
| MOD-046 | Aggiungere un caso a mano **senza eseguire l'azione** (per sanzioni date fuori dal bot) | Zeppelin `addcase` [ZEPPELIN] | ❌ manca | `/mod caso aggiungi membro: tipo: motivo:` | nuova |
| MOD-047 | Casi creati anche per ban, kick e timeout fatti **dal menu di Discord o da altri bot** | YAGPDB "External logging" [YAGPDB], Zeppelin `create_cases_for_manual_actions` [ZEPPELIN] | 🟡 parziale: il log registra il ban, ma non nasce un caso | Ascoltare `on_audit_log_entry_create`; creare il caso con il moderatore letto dal registro | nuova |
| MOD-048 | Casi dell'AutoMod che **scadono da soli** dopo un mese | Wick [WICK] | 🟡 parziale: `/escalation set-reset-days` azzera il conteggio, i casi restano attivi | Scadenza per tipo di caso; si appoggia a MOD-045 | nuova |
| MOD-049 | Registrare un'azione "a nome di" un altro moderatore | Zeppelin `can_act_as_other`, opzione `-mod` [ZEPPELIN] | ❌ manca | Opzione `per_conto_di` riservata agli amministratori; nel caso restano tutti e due i nomi | nuova |
| MOD-050 | **Moderazione anonima**: l'utente punito non vede il nome del moderatore | Wick `misc 2d` [WICK] | ❌ manca | Impostazione del server; il nome resta nel caso e nel mod-log | nuova |
| MOD-051 | Insieme al caso, salvare il **registro degli ultimi messaggi del canale** | YAGPDB (log del canale nel mod-log; ultimi 100 messaggi a ogni warn) [YAGPDB] | ❌ manca | File di testo con gli ultimi 100 messaggi allegato al caso; serve `message_content` | NF-02 |
| MOD-052 | Canale mod-log **creato dal bot** | Carl-bot `/modlog create [nome]` [CARL], Wick (crea `#modlogs`) [WICK] | 🟡 parziale: `/mod-log-setup` sceglie solo un canale che esiste già | `/log crea-canali` crea anche il canale moderazione, visibile solo allo staff | NF-01 |
| MOD-053 | Colori e icone dei casi scelti dal server | Zeppelin `case_colors`, `case_icons` [ZEPPELIN] | ❌ manca | Impostazione per tipo di caso; meglio nel pannello web | NF-20 |
| MOD-054 | **Togliere una nota** | Carl-bot `/notes removenote` [CARL], Dyno `/delnote` [DYNO] (terzi), Wick `/notes remove` [WICK] | ❌ manca: esistono solo `add` e `list` | `/mod nota togli numero:` | nuova |
| MOD-055 | Modificare una nota | Dyno `/editnote` [DYNO] (terzi), Wick `new_msg` [WICK] | ❌ manca | `/mod nota modifica numero: testo:` | nuova |
| MOD-056 | Cancellare tutte le note di un membro | Carl-bot `/notes clearnotes` [CARL], Dyno `/clearnotes` [DYNO] (terzi) | ❌ manca | `/mod nota azzera membro:` con conferma | nuova |
| MOD-057 | Scegliere **per tipo di azione** se mandare il DM all'utente | Zeppelin `dm_on_warn`, `dm_on_kick`, `dm_on_ban`, `dm_on_mute` [ZEPPELIN]; Wick `misc 2e` [WICK] | 🟡 parziale: il DM parte sempre | Un interruttore per azione in `/admin config` | nuova |
| MOD-058 | Scegliere **nel singolo comando** se avvisare l'utente in DM | Wick `?dm` [WICK] | ❌ manca | Opzione `avvisa: sì/no` sui comandi di `/mod` e `/modban`; default dall'impostazione MOD-057 | nuova |
| MOD-059 | **Testo del DM personalizzabile** per warn, kick, ban, tempban, mute | Zeppelin `warn_message`, `kick_message`, `ban_message`, `tempban_message`, `mute_message` [ZEPPELIN]; YAGPDB "Moderation DMs" [YAGPDB] | ❌ manca | Testi con segnaposto tramite `core/template_renderer.py`; massimo 2000 caratteri | nuova |
| MOD-060 | Avviso della sanzione scritto **in un canale** invece che in DM | Zeppelin `message_on_warn`, `message_on_kick`, `message_on_ban`, `message_channel` [ZEPPELIN] | ❌ manca | Tipo di uscita "avvisi sanzione" nel router dei canali | NF-01 |
| MOD-061 | Testo sull'appello dentro il DM del ban | Wick `misc 9` e pagina appelli [WICK] | 🟡 parziale: solo per i ban dello spam-trap | Testo configurabile nel DM, con il bottone di appello | NF-30 |
| MOD-062 | Canale dedicato dove arrivano gli appelli | Lawliet "Ban Appeal Log Channel" [LAWLIET] | 🟡 parziale: gli appelli dello spam-trap vanno in un thread di `#spam-log` | Tipo di uscita "appelli" nel router dei canali | NF-30 |
| MOD-063 | Appello anche per i **timeout** | Wick [WICK] | ❌ manca | Stesso flusso di NF-30, con il caso del timeout | NF-30 |
| MOD-064 | **Avviso allo staff quando rientra** un utente che ha casi | Zeppelin `alert_on_rejoin`, `alert_channel` [ZEPPELIN] | ❌ manca | All'ingresso: conta i casi; se ce ne sono, messaggio nel canale allarmi con link allo storico | nuova |
| MOD-065 | Motivo **facoltativo o obbligatorio** a scelta del server | YAGPDB "Reason Optional" [YAGPDB] | 🟡 parziale: il motivo è sempre obbligatorio | Impostazione; l'opzione diventa facoltativa e il controllo si fa nel codice | nuova |
| MOD-066 | Conferma prima di eseguire l'azione, attivabile e disattivabile | Wick `misc 2a` [WICK], Lawliet "Confirmation Messages" [LAWLIET] | ❌ manca | Bottoni Conferma / Annulla con scadenza di 60 secondi; impostazione del server | nuova |
| MOD-067 | Risposte di moderazione **compatte** o che si cancellano dopo un po' | Wick `?p`, `misc 4`, `misc 5` [WICK] | ❌ manca | Impostazione "risposta effimera" per i comandi di moderazione | nuova |
| MOD-068 | Ruoli **immuni** alla moderazione manuale | MEE6 "Immunity roles" [MEE6]; Wick (Extra Owner e Trusted Admin immuni) [WICK] | 🟡 parziale: c'è solo il controllo di gerarchia | Lista di ruoli immuni (fino a 25) controllata da ogni comando | nuova |
| MOD-069 | Clear: solo i messaggi che **contengono** un testo | Carl-bot `purge contains` [CARL], Dyno `purge match` [DYNO] (terzi), Wick `has` [WICK] | ❌ manca | Sotto-gruppo `/mod clear` con opzione `contiene` (massimo 100 caratteri); serve `message_content` | nuova |
| MOD-070 | Clear: messaggi che iniziano con, finiscono con, o sono uguali a un testo | Dyno `startswith`, `endswith` [DYNO] (terzi); Wick `starts`, `equals` [WICK] | ❌ manca | Opzione `modo` con scelte fisse accanto a `contiene` | nuova |
| MOD-071 | Clear: messaggi che **non** contengono un testo | Dyno `purge not` [DYNO] (terzi), YAGPDB `-im` [YAGPDB] | ❌ manca | Scelta "non contiene" in `modo` | nuova |
| MOD-072 | Clear con **espressione regolare** | YAGPDB `-r`, `-i` [YAGPDB]; Zeppelin `-match` [ZEPPELIN] | ❌ manca | Opzione `regex` (massimo 260 caratteri); tempo massimo di esecuzione per evitare blocchi | nuova |
| MOD-073 | Clear: solo messaggi con link | Carl-bot [CARL], Dyno [DYNO] (terzi), Wick [WICK] | ❌ manca | Scelta "link" nell'opzione `tipo` di `/mod clear` | nuova |
| MOD-074 | Clear: solo messaggi con inviti Discord | Dyno `purge invites` [DYNO] (terzi) | ❌ manca | Scelta "inviti" in `tipo` | nuova |
| MOD-075 | Clear: solo messaggi con embed | Carl-bot [CARL], Dyno [DYNO] (terzi), Wick [WICK] | ❌ manca | Scelta "embed" in `tipo` | nuova |
| MOD-076 | Clear: solo messaggi con menzioni | Carl-bot [CARL], Dyno [DYNO] (terzi), Wick [WICK] | ❌ manca | Scelta "menzioni" in `tipo` | nuova |
| MOD-077 | Clear: solo messaggi con emoji | Carl-bot `purge emoji` [CARL], Wick `emojis` [WICK] | ❌ manca | Scelta "emoji" in `tipo` | nuova |
| MOD-078 | Clear: solo messaggi di **persone** (non bot) | Carl-bot `purge human` [CARL], Dyno `purge humans` [DYNO] (terzi) | 🟡 parziale: c'è solo "solo bot" | Scelta "persone" in `tipo` | nuova |
| MOD-079 | Clear: solo messaggi di testo, senza immagini né file | Dyno `purge text` [DYNO] (terzi), Wick `text` [WICK] | ❌ manca | Scelta "solo testo" in `tipo` | nuova |
| MOD-080 | Togliere solo le **reazioni** dagli ultimi messaggi | Carl-bot `purge reactions` [CARL] | ❌ manca | `/mod clear reazioni quanti:`; `message.clear_reactions()`, una chiamata per messaggio | nuova |
| MOD-081 | Clear **dopo, prima o tra** messaggi indicati per ID o link | Dyno `purge after` [DYNO] (terzi); Wick `after`, `before` [WICK]; YAGPDB `-from`, `-to` [YAGPDB]; Zeppelin `-to-id` [ZEPPELIN] | ❌ manca | Opzioni `da_messaggio` e `a_messaggio`; `purge(after=…, before=…)` | nuova |
| MOD-082 | Clear per **età** dei messaggi (più vecchi di, più nuovi di) | YAGPDB `-ma`, `-minage` [YAGPDB]; Lawliet `fullclear` [LAWLIET] | ❌ manca | Opzioni `eta_min` e `eta_max`; mai oltre 14 giorni (limite della cancellazione in blocco) | nuova |
| MOD-083 | Clear dei messaggi di chi ha un certo **ruolo** | Wick [WICK] | ❌ manca | Opzione `ruolo` | nuova |
| MOD-084 | Clear dei messaggi mandati da **webhook** | Wick [WICK] | ❌ manca | Scelta "webhook" in `tipo` (`message.webhook_id`) | nuova |
| MOD-085 | Clear dei messaggi di utenti sospetti: senza avatar, senza ruoli, segnati dal sistema | Wick `suspicious`, `no-avatar`, `no-role` [WICK] | ❌ manca | Scelte in `tipo`; "sospetto" usa i controlli dell'anti-raid | nuova |
| MOD-086 | Clear che **salta i messaggi fissati** | Carl-bot [CARL], YAGPDB `-nopin` [YAGPDB], Lawliet [LAWLIET] | ❌ manca: oggi cancella anche i fissati | `check` che esclude `message.pinned`; attivo di default | nuova |
| MOD-087 | Clear di **più di 200 messaggi** in un comando | Wick, 1000 [WICK]; YAGPDB, cerca negli ultimi 1000 [YAGPDB]; MEE6 dichiara 50.000 [MEE6] | 🟡 parziale: massimo 200 | Portare il tetto a 1000; blocchi da 100; `defer()`; riepilogo alla fine | nuova |
| MOD-088 | Clear in un **altro canale** rispetto a quello del comando | Zeppelin `-channel` [ZEPPELIN] | ❌ manca | Opzione `canale` | nuova |
| MOD-089 | Cancellare solo le **risposte del bot** | Dyno `/clean` [DYNO] (terzi), Carl-bot `cleanup` [CARL] | 🟡 parziale: "solo bot" prende tutti i bot | Scelta "solo iYokai" in `tipo` | nuova |
| MOD-090 | Lock di un canale **a tempo** (si sblocca da solo) | Carl-bot `lockdown [duration]` [CARL], Dyno `/lock duration` [DYNO] (terzi), Lawliet [LAWLIET] | ❌ manca | Opzione `durata` su `/mod lock`; sblocco con lo scheduler; riga di log (M 1.8) | nuova |
| MOD-091 | Lock di **più canali scelti** in un comando | Wick `lockc #a #b` [WICK] | ❌ manca | Menu di selezione canali (fino a 25) | NF-29 |
| MOD-092 | Gruppo di canali **predefinito** da bloccare tutti insieme | Dyno `/lockdown start`, `end` [DYNO] (terzi); Carl-bot `lockdown setup` (Premium) [CARL] | ❌ manca | Lista salvata dei canali; `/mod blocco attiva` e `togli` | NF-29 |
| MOD-093 | Lock di **tutto il server**, anche a tempo | Carl-bot `/lockdown server` [CARL], Wick `serverlock` [WICK] | ❌ manca | `/mod blocco attiva`; stato salvato per riaprire com'era; fino a 500 canali | NF-29 |
| MOD-094 | Blocco "cieco": nasconde i canali e crea un canale di avvisi per i membri | Wick, flag `-b` e `lockupdate` [WICK] | ❌ manca | Opzione `nascondi`; canale `#server-bloccato` creato e tolto dal bot | NF-29 |
| MOD-095 | Durante il blocco, **kick o ban automatico di chi entra** | Wick, modi `k` e `b` [WICK] | ❌ manca | Modo "ingressi" del blocco; si spegne da solo con lo sblocco | NF-29 |
| MOD-096 | Blocco dei **ruoli**: toglie i permessi pericolosi a tutti i ruoli sotto il bot | Wick, modo `r` (Premium) [WICK] | ❌ manca | Salvare i permessi di prima; ripristino allo sblocco; mai toccare i ruoli sopra il bot | NF-29 |
| MOD-097 | Vedere quali blocchi sono attivi | Wick `w!lock` [WICK] | ❌ manca | `/mod blocco stato` | NF-29 |
| MOD-098 | Slowmode su **più canali** in un comando | Wick [WICK] | ❌ manca | Menu di selezione canali su `/mod slowmode` | nuova |
| MOD-099 | Slowmode **gestito dal bot**, anche oltre le 6 ore di Discord | Zeppelin, modo `bot` [ZEPPELIN] | ❌ manca | Il bot cancella i messaggi troppo ravvicinati e tiene i tempi in memoria; serve "Gestisci messaggi" | nuova |
| MOD-100 | Elenco dei canali con slowmode attivo | Zeppelin `slowmode list` [ZEPPELIN] | ❌ manca | `/mod slowmode` senza valori mostra l'elenco | nuova |
| MOD-101 | Cambiare o azzerare il **nickname** di un membro | Carl-bot `setnick` [CARL], ProBot `setnick` [PROBOT], Zeppelin `nickname`, `nickname reset` [ZEPPELIN] | ❌ manca | `/mod nick imposta` e `azzera`; nickname fino a 32 caratteri; riga di log | nuova |
| MOD-102 | **Ripulire i nickname** con simboli strani o messi per salire in cima alla lista | Wick `sanitize` / `dehoist`, anche su più membri [WICK] | ❌ manca | `/mod nick pulisci`; normalizzazione Unicode; rispettare la gerarchia dei ruoli | nuova |
| MOD-103 | Storico dei nomi e nickname di un utente | Zeppelin `names` [ZEPPELIN] | ❌ manca | `/mod info nomi utente:`; tabella con scadenza, dichiarata nel registro dei dati personali | NF-04 |
| MOD-104 | Nickname e mute vocale **ridati a chi rientra** | Zeppelin `persist_nicknames`, `persist_voice_mutes` [ZEPPELIN] | ❌ manca | Estendere i "ruoli ridati a chi rientra" | NF-07 |
| MOD-105 | Segnalazione di un **messaggio** con link diretto e contesto del canale | Carl-bot `report` (link al messaggio) [CARL], YAGPDB `report` (log del canale) [YAGPDB] | 🟡 parziale: `/report` prende solo membro e motivo | Comando del menu contestuale "Segnala messaggio" (15 per tipo); link e testo nel canale segnalazioni | nuova |
| MOD-106 | **Scheda utente per lo staff**: data dell'account, ingresso, ruoli, casi attivi, sospetto o no; anche per ID di chi non è nel server | Wick `info` [WICK], Zeppelin `user` [ZEPPELIN], Carl-bot `/members info` [CARL], YAGPDB `whois` [YAGPDB], MEE6 `/user-info` [MEE6] | ❌ manca | `/mod info utente`; unisce casi, note e controlli dell'anti-raid; effimera | nuova |
| MOD-107 | Cercare tra gli utenti **bannati** | Zeppelin `bansearch` [ZEPPELIN] | ❌ manca | `/modban cerca testo:`; `guild.bans()` è paginato (1000 per pagina) | nuova |
| MOD-108 | Cercare membri con filtri (nome, ruolo, in vocale, bot, regex) ed esportare l'elenco | Zeppelin `search` [ZEPPELIN] | ❌ manca | `/mod info cerca`; risultato paginato o in file | nuova |
| MOD-109 | Elenco degli account più giovani e degli ultimi entrati | Carl-bot `/members youngest`, `/members newusers` (fino a 25) [CARL] | ❌ manca | `/mod info recenti tipo:`; 25 righe | nuova |
| MOD-110 | Informazioni su un invito (chi l'ha creato, server, usi) | Dyno `/inviteinfo` [DYNO] (terzi), Zeppelin `invite` [ZEPPELIN] | ❌ manca | `/mod info invito codice:`; `fetch_invite` | nuova |
| MOD-111 | Vedere i permessi effettivi di un membro in un canale | Carl-bot `/misc permissions` [CARL], YAGPDB `/viewperms` [YAGPDB] | ❌ manca (`/permission-heatmap` lavora per ruolo) | `/mod info permessi membro: canale:` | nuova |
| MOD-112 | Sapere in quale vocale si trova un utente e ricevere un avviso quando entra | Zeppelin `where`, `follow` [ZEPPELIN] | ❌ manca | `/mod voce dove` e `segui`; avvisi con scadenza | nuova |

## Fonti

Lette il 4/10/2026.

- **`[CARL]`** Carl-bot (ufficiale): https://docs.carl.gg/moderation.md · https://docs.carl.gg/logging.md · https://docs.carl.gg/config.md · https://docs.carl.gg/utilities.md · https://docs.carl.gg/misc.md
- **`[DYNO]`** Dyno: https://discordbotlist.com/bots/dyno/commands (**terzi**: elenco comandi pubblicato su un sito esterno; mostra solo i comandi dalla A alla R). Le pagine ufficiali `docs.dyno.gg` e `dyno.gg/commands` non sono leggibili da qui (si caricano solo con JavaScript).
- **`[YAGPDB]`** YAGPDB (ufficiale): https://help.yagpdb.xyz/docs/moderation/moderation-tools/ · https://help.yagpdb.xyz/docs/core/all-commands/ (testo letto dal repository della documentazione, https://github.com/botlabs-gg/yagpdb-docs-v2)
- **`[ZEPPELIN]`** Zeppelin (ufficiale, codice sorgente): https://github.com/ZeppelinBot/Zeppelin — cartelle `backend/src/plugins/ModActions`, `Mutes`, `Cases`, `Slowmode`, `Utility`, `Persist`, `NameHistory`, `LocateUser`. Il sito `zeppelin.gg` non è leggibile da qui.
- **`[WICK]`** Wick (ufficiale): https://docs.wickbot.com/setup/ · https://docs.wickbot.com/commands/moderation/ban/ · `/kick/` · `/lockdown/` · `/notes/` · `/purge/` · `/quarantine/` · `/sanitize/` · `/slowmode/` · `/timeout/` · `/warn/` · https://docs.wickbot.com/commands/utility/cases/ · `/modcases/` · `/info/`
- **`[PROBOT]`** ProBot (ufficiale): https://probot.io/commands
- **`[MEE6]`** MEE6 (ufficiale): https://wiki.mee6.xyz/plugins/moderator
- **`[LAWLIET]`** Lawliet (ufficiale, codice sorgente): https://github.com/Aninoss/lawliet-bot — `src/main/resources/moderation_en_us.properties`

Non letti su fonte ufficiale per questa area: Dyno (solo terzi), Sapphire, Atlas, Maki (siti che si caricano solo con JavaScript). I comandi di Dyno dalla S alla Z (per esempio softban, unban, warn) non compaiono nell'elenco letto e non sono stati usati.

## Conteggio

Contato sulle righe della tabella (`grep -c "^| MOD-"`).

- Righe totali: **112**
- ❌ manca: **91**
- 🟡 parziale: **21**
