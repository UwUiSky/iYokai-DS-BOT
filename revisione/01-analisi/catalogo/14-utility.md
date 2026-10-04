# Catalogo — Utility

Comandi personalizzati e risposte automatiche, embed, sondaggi,
promemoria, messaggi ripetuti, giveaway, suggerimenti, starboard,
messaggi fissi, compleanni, inviti, conteggio, strumenti personali,
informazioni, ricerche, configurazione del bot. 229 voci. Bot letti:
Carl-bot, YAGPDB, NadekoBot, Arcane, Red-DiscordBot, Lawliet, Mimu,
ProBot, GiveawayBot, Giveaway Boat, EasyPoll, Invite Tracker, Countr,
Reminder Bot, MEE6.

Legenda: ❌ manca · 🟡 parziale. "Scheda": NF-xx = scheda di
`NUOVE_FUNZIONI.md`; M x.y = riga di `MODIFICHE_ESISTENTE.md`;
"nuova" = non c'è ancora in nessun piano.

iYokai oggi (per confronto): `/poll` (sondaggio nativo, 5 opzioni,
durata, scelta multipla), `/reminder set|list|cancel` (una volta, in
DM), `/schedule-message set|list|cancel` (una volta), `/giveaway`
(premio, durata, vincitori, livello minimo, ruolo richiesto),
`/suggest` con bottoni approva/rifiuta, `/sticky set|remove`,
`/reactionsnipe`, rilevamento dei ghost ping, `/serverstats`,
`/request-custom-command` (richiesta all'owner), `/config …`.

Non ripetute qui (già in `APP_UTENTE_E_DESKTOP.md`): note personali,
liste di cose da fare, fusi orari, conversioni e calcolatrice, AFK,
parole chiave personali, traduzione, storico dei ping.

## 1. Comandi personalizzati (tag)

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| UTL-001 | Creare un comando del server con una risposta di testo | Carl-bot (`tag create`) [CARL], YAGPDB [YAGPDB], Red (`customcom create simple`) [RED], Lawliet (`customconfig`) [LAWLIET], Arcane (5 gratis, 100 premium) [ARCANE], MEE6 (premium, 500) [MEE6] | ❌ manca: si può solo chiedere un comando all'owner | `/admin comandi crea`; uso con `/utility tag <nome>`; testo ≤ 2000; tetto per server | NF-09 |
| UTL-002 | Modificare un tag | Carl-bot (`tag edit`) [CARL], Red (`customcom edit`) [RED] | ❌ manca | `/admin comandi modifica` (modulo con il testo attuale) | NF-09 |
| UTL-003 | Aggiungere testo in coda a un tag | Carl-bot (`tag append`) [CARL] | ❌ manca | Opzione del comando di modifica | NF-09 |
| UTL-004 | Cancellare un tag | Carl-bot (`tag delete`) [CARL], Red (`customcom delete`) [RED] | ❌ manca | `/admin comandi elimina` | NF-09 |
| UTL-005 | Elenco dei tag del server | Carl-bot (`tag list`) [CARL], Red (`customcom list`) [RED], YAGPDB (`/customcommands list`) [YAGPDB] | ❌ manca | `/admin comandi elenco`, a pagine; autocompletamento in `/utility tag` (25 voci) | NF-09 |
| UTL-006 | Cercare un tag per nome o contenuto | Red (`customcom search`) [RED], NadekoBot (`.exprsearch`) [NADEKO] | ❌ manca | Autocompletamento che filtra mentre scrivi | NF-09 |
| UTL-007 | Vedere il testo "grezzo" di un tag, senza formattazione | Carl-bot (`tag raw`) [CARL], Red (`customcom raw`, `customcom show`) [RED] | ❌ manca | Opzione `grezzo` in elenco | NF-09 |
| UTL-008 | Scheda del tag: chi l'ha creato e quante volte è stato usato | Carl-bot (`tag info`) [CARL], YAGPDB (numero di esecuzioni, ultima esecuzione) [YAGPDB] | ❌ manca | Contatore di usi nella tabella | NF-09 |
| UTL-009 | Nome alternativo (alias) per un tag | Carl-bot (`tag alias`) [CARL] | ❌ manca | Colonna `alias` (max 3 per tag) | NF-09 |
| UTL-010 | Risposta scelta a caso tra più testi | Red (`customcom create random`) [RED], Carl-bot (blocco `random`) [CARL], Arcane (`{choose:}`) [ARCANE] | ❌ manca | Segnaposto `{casuale: a ~ b}` del renderer comune | NF-09 |
| UTL-011 | Risposte casuali con pesi diversi | Mimu ("weighted choices") [MIMU] | ❌ manca | Sintassi `3×testo` dentro `{casuale:}` | nuova |
| UTL-012 | Pausa tra un uso e l'altro, per utente, canale o server | Red (`customcom cooldown`) [RED], Carl-bot [CARL] | ❌ manca | Colonna `pausa` e `ambito` | NF-09 |
| UTL-013 | Tag usabile solo da certi ruoli o in certi canali | Carl-bot (blocco `require`) [CARL], Arcane (`{require_role:}`, `{require_channel:}`) [ARCANE], YAGPDB [YAGPDB] | ❌ manca | Elenco di ruoli e canali ammessi | NF-09 |
| UTL-014 | Tag vietato a certi ruoli, canali o utenti | Carl-bot (blocco `blacklist`) [CARL], Arcane (`{deny_role:}`, `{deny_channel:}`, `{deny_user:}`) [ARCANE] | ❌ manca | Elenco di esclusi | NF-09 |
| UTL-015 | Tag che richiede un permesso Discord a chi lo usa | Arcane (`{require_permission:}`) [ARCANE] | ❌ manca | Scelta tra pochi permessi (es. "Gestire messaggi") | nuova |
| UTL-016 | Tag che dà o toglie un ruolo a chi lo usa | Arcane (`{addrole:}`, `{removerole:}`) [ARCANE], Mimu [MIMU] | ❌ manca | Colonne ruolo dato e tolto; `check_role_assignable` | NF-09 |
| UTL-017 | Tag che agisce su un altro utente indicato | Arcane (`{target.add_role()}`) [ARCANE], Carl-bot (`{target}`) [CARL], Mimu (`.roleadd [utente] [ruolo]`) [MIMU] | ❌ manca | Solo per chi può già gestire quel ruolo: rischio di scalata dei permessi | nuova |
| UTL-018 | Risposta del tag dentro un embed | Carl-bot (blocchi `embed`, embed dal pannello) [CARL], Arcane (`{embed.title:}` e simili) [ARCANE], Lawliet (immagine nell'embed) [LAWLIET] | ❌ manca | Collegare un embed salvato | NF-09 |
| UTL-019 | Il messaggio che ha attivato il tag viene cancellato | Carl-bot (blocco `delete`) [CARL], Arcane (`{delete}`) [ARCANE], NadekoBot (`.exprad`) [NADEKO], Lawliet (`triggerdelete`) [LAWLIET] | ❌ manca | Vale solo per l'uso con prefisso; serve "Gestire messaggi" | nuova |
| UTL-020 | Risposta mandata in privato | Carl-bot (blocco `dm`) [CARL], NadekoBot (`.exprdm`) [NADEKO] | ❌ manca | Opzione `dove: canale/privato`; con lo slash basta la risposta effimera | nuova |
| UTL-021 | Risposta mandata in un altro canale | Carl-bot (blocco `redirect`) [CARL], Arcane (`{redirect:}`) [ARCANE] | ❌ manca | Colonna `canale_uscita` | nuova |
| UTL-022 | Il bot mette reazioni sulla risposta | Carl-bot (1 gratis, 5 premium) [CARL], Arcane (`{react:}`) [ARCANE], NadekoBot (`.exprreact`, fino a 3) [NADEKO] | ❌ manca | Fino a 3 emoji | nuova |
| UTL-023 | Risposta che si cancella da sola dopo un tempo | Arcane (`{delete_reply:}`) [ARCANE] | ❌ manca | `delete_after` sull'invio | nuova |
| UTL-024 | Tag che esegue comandi del bot | Carl-bot ("command blocks": 1 gratis, 3 premium) [CARL] | ❌ manca | Rischioso: solo un elenco chiuso di azioni (ruolo, messaggio), mai un comando qualsiasi | nuova |
| UTL-025 | Tag che cancella N messaggi | Arcane (`{purge:}`) [ARCANE] | ❌ manca | Non proporre: meglio `/mod clear` | nuova |
| UTL-026 | Argomenti scritti dall'utente usati nella risposta | Carl-bot (`{args}`) [CARL], Arcane (`{args[0]}`) [ARCANE], Mimu [MIMU] | ❌ manca | Opzione `testo` di `/utility tag`; menzioni spente nella risposta | nuova |
| UTL-027 | Condizioni "se… allora… altrimenti" | Carl-bot (`if`, `any`, `all`) [CARL], Arcane [ARCANE], YAGPDB [YAGPDB] | ❌ manca | Linguaggio di script: solo dopo la versione semplice (B7 in `CONFRONTO_BOT.md`) | nuova |
| UTL-028 | Variabili e liste dentro il tag | Carl-bot [CARL], Arcane [ARCANE] | ❌ manca | Come UTL-027 | nuova |
| UTL-029 | Calcoli e numeri casuali | Carl-bot (`math`, `range`) [CARL], Arcane (`{add:}`, `{range:}`) [ARCANE] | ❌ manca | Come UTL-027 | nuova |
| UTL-030 | Trasformazioni del testo (maiuscole, sostituzioni) | Carl-bot (`upper`, `lower`, `replace`, `urlencode`) [CARL], Arcane [ARCANE] | ❌ manca | Come UTL-027 | nuova |
| UTL-031 | Date e differenze di tempo nel testo | Carl-bot (`strf`, `timedelta`) [CARL] | ❌ manca | Segnaposto `{data}` e `{ora}` in formato Discord | nuova |
| UTL-032 | Dati salvati tra un uso e l'altro (piccolo database del server) | YAGPDB [YAGPDB] | ❌ manca | Come UTL-027; tetto di righe per server | nuova |
| UTL-033 | Tag più lunghi di 2000 caratteri | Carl-bot (`tag ++`, fino a 25.000) [CARL], YAGPDB (10.000, 20.000 premium) [YAGPDB] | ❌ manca | Risposta divisa in più messaggi (max 3) | nuova |
| UTL-034 | Proprietà dei tag: ognuno modifica solo i suoi | Carl-bot (`tag ownership`) [CARL] | ❌ manca | Colonna `autore`; utile se i membri possono creare tag | nuova |
| UTL-035 | Prendersi i tag di chi ha lasciato il server | Carl-bot (`tag claim`) [CARL] | ❌ manca | Dipende da UTL-034 | nuova |
| UTL-036 | Solo i moderatori possono gestire i tag | Carl-bot (`tag modonly`) [CARL] | ❌ manca | È già il default previsto (`/admin comandi`) | NF-09 |
| UTL-037 | Tag usabile solo nei canali NSFW | Carl-bot (`tag nsfw`) [CARL] | ❌ manca | Colonna booleana, controllata a ogni uso | nuova |
| UTL-038 | Risposta deviata nel canale dei bot, con ping all'autore | Carl-bot (`tag restrict`) [CARL] | ❌ manca | Variante di UTL-021 | nuova |
| UTL-039 | Sostituire una parola in tutti i tag | Carl-bot (`tag sub`) [CARL] | ❌ manca | Comando di manutenzione con anteprima | nuova |
| UTL-040 | Condividere i tag con un link, per importarli in un altro server | Carl-bot (`tag share`, `unshare`, `unshareall`) [CARL] | ❌ manca | Meglio l'esportazione su file (UTL-041) | nuova |
| UTL-041 | Esportare e importare i tag come file | NadekoBot (`.exprsexport`, `.exprsimport`) [NADEKO] | 🟡 parziale: `/config export` esporta la configurazione, non i tag | Includere i tag in `/config export` e `import` | nuova |
| UTL-042 | Gruppi di comandi con regole comuni di canale e ruolo | YAGPDB ("Command Groups") [YAGPDB] | ❌ manca | Colonna `gruppo` | nuova |
| UTL-043 | Vedere l'ultimo errore di un comando personalizzato | YAGPDB ("Last Error", "Output errors as command response") [YAGPDB] | ❌ manca | Colonna `ultimo_errore` mostrata in elenco | nuova |
| UTL-044 | Provare un pezzo di script senza salvarlo | YAGPDB (`/customcommands eval`) [YAGPDB] | ❌ manca | Anteprima privata in `/admin comandi crea` | nuova |
| UTL-045 | Comandi slash veri creati dal server, con sotto-comandi | YAGPDB (10 gratis, 50 premium) [YAGPDB], Sapphire [SAPPHIRE] | ❌ manca | Comandi registrati per server: 100 per server e 200 creazioni al giorno. Da valutare dopo F7 | nuova |
| UTL-046 | Voci del menu "tasto destro" create dal server | YAGPDB (5 per tipo gratis, 15 premium) [YAGPDB] | ❌ manca | Come UTL-045; 15 voci per tipo | nuova |
| UTL-047 | Comando che parte quando qualcuno mette o toglie una reazione | YAGPDB (innesco "Reaction") [YAGPDB] | ❌ manca | Innesco in più sui tag | nuova |
| UTL-048 | Comando che parte a intervalli (ogni N minuti o ore), con ore e giorni esclusi | YAGPDB (da 5 minuti a 1 mese) [YAGPDB] | 🟡 parziale: `/schedule-message` manda un testo una volta sola | Vedi UTL-105 | nuova |
| UTL-049 | Comando che parte a orari fissi (sintassi cron) | YAGPDB (innesco "Crontab") [YAGPDB] | ❌ manca | Scelta guidata "ogni giorno alle…", niente cron scritto a mano | nuova |
| UTL-050 | Bottoni e menu che eseguono un comando personalizzato | YAGPDB (innesco "Component") [YAGPDB], Mimu ("button responders") [MIMU], Sapphire [SAPPHIRE] | ❌ manca | Bottone nell'embed salvato che richiama un tag; vista persistente | nuova |
| UTL-051 | Moduli (finestre con domande) che eseguono un comando personalizzato | YAGPDB (innesco "Modal") [YAGPDB] | ❌ manca | Coperto dai moduli di NF-34 | NF-34 |
| UTL-052 | Comando che parte quando un membro riceve o perde un ruolo | YAGPDB (1 gratis, 5 premium) [YAGPDB], Carl-bot (`triggers role`) [CARL] | ❌ manca | Evento `on_member_update`; utile per "benvenuto tra i VIP" | nuova |
| UTL-053 | Comando che parte anche sui messaggi modificati | YAGPDB (premium) [YAGPDB] | ❌ manca | Evento `on_message_edit` | nuova |
| UTL-054 | Far partire subito un comando a intervalli | YAGPDB ("Run Now") [YAGPDB], NadekoBot (`.repeatinvoke`) [NADEKO] | ❌ manca | Bottone "Esegui ora" | nuova |
| UTL-055 | Risposte automatiche valide in tutti i server (decise dall'owner) | NadekoBot (espressioni globali, `.exprtoggleglobal`) [NADEKO] | ❌ manca | `/owner system risposta-globale`; ogni server può spegnerle | nuova |

## 2. Risposte automatiche

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| UTL-056 | Risposta quando il messaggio contiene una parola | Carl-bot (`triggers create`) [CARL], YAGPDB ("Contains") [YAGPDB], NadekoBot (`.exprca`) [NADEKO], Mimu (`/autoresponder add`) [MIMU] | ❌ manca | `/admin comandi risposta-crea`; serve `message_content`; mai rispondere ai bot | NF-10 |
| UTL-057 | Risposta solo se il messaggio è uguale al testo | Carl-bot (`triggers exact`) [CARL], YAGPDB ("Exact Match") [YAGPDB] | ❌ manca | Modo `esatto` | NF-10 |
| UTL-058 | Risposta solo su parole intere in sequenza | Carl-bot (`triggers strict`) [CARL] | ❌ manca | Modo `parola-intera` | NF-10 |
| UTL-059 | Risposta se il messaggio inizia con il testo | Carl-bot (`triggers startswith`) [CARL], YAGPDB ("Starts With") [YAGPDB] | ❌ manca | Modo `inizia` | NF-10 |
| UTL-060 | Risposta se il messaggio finisce con il testo | Carl-bot (`triggers endswith`) [CARL] | ❌ manca | Modo `finisce` | NF-10 |
| UTL-061 | Risposta su espressione regolare | Carl-bot (`triggers regex`) [CARL], YAGPDB ("Regex") [YAGPDB] | ❌ manca | Solo con un tempo massimo di valutazione: una regex lenta blocca il bot | nuova |
| UTL-062 | Scelta tra maiuscole e minuscole contano o no | YAGPDB ("Case Sensitivity") [YAGPDB] | ❌ manca | Opzione booleana | NF-10 |
| UTL-063 | Risposta attiva solo in certi canali | Carl-bot (`triggers channel`) [CARL] | ❌ manca | Elenco di canali | NF-10 |
| UTL-064 | Utenti e canali che non fanno scattare le risposte | Carl-bot (`triggers ignore`, `unignore`) [CARL] | ❌ manca | Elenco di esclusi | NF-10 |
| UTL-065 | Ruoli ammessi o esclusi dalle risposte | Carl-bot (`triggers role_whitelist`, `role_blacklist`) [CARL] | ❌ manca | Due elenchi | NF-10 |
| UTL-066 | Modificare risposta e modo di confronto senza ricreare | Mimu (`/autoresponder editreply`, `editmatchmode`) [MIMU], NadekoBot (`.expredit`) [NADEKO] | ❌ manca | `/admin comandi risposta-modifica` | NF-10 |
| UTL-067 | Elenco e dettaglio delle risposte automatiche | Mimu (`/autoresponder list`, `show`, `showraw`) [MIMU], NadekoBot (`.exprlist`, `.exprshow`) [NADEKO] | ❌ manca | `/admin comandi risposte`, a pagine | NF-10 |
| UTL-068 | Cancellare tutte le risposte automatiche in un colpo | Carl-bot (`triggers clear`) [CARL], NadekoBot (`.exprclear`) [NADEKO], Mimu (`/reset server autoresponders`) [MIMU] | ❌ manca | Comando con conferma | nuova |
| UTL-069 | La risposta accetta testo dopo la parola chiave | NadekoBot (`.exprat`) [NADEKO] | ❌ manca | Opzione booleana | nuova |
| UTL-070 | Canale "scorciatoia": ogni messaggio scritto lì diventa l'argomento di un comando | Lawliet (`ccshortcuts`) [LAWLIET] | ❌ manca | È l'idea del canale richieste musicali (NF-19), estesa ad altri comandi | nuova |
| UTL-071 | Link a un messaggio trasformato in citazione con autore e testo | Lawliet (`autoquote`, `quote`) [LAWLIET] | ❌ manca | Solo per messaggi dello stesso server e canali visibili a chi incolla il link | nuova |
| UTL-072 | Correzione automatica dei link da un dominio a un altro | NadekoBot (`.linkfix`, `.linkfixlist`) [NADEKO] | ❌ manca | Coppie dominio→dominio per server (max 10); serve `message_content` | nuova |

## 3. Embed e messaggi del bot

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| UTL-073 | Embed semplice con un comando (colore, titolo, testo) | Carl-bot (`embed`) [CARL], YAGPDB (`/simpleembed`) [YAGPDB], Mimu (`/embed create`) [MIMU] | ❌ manca | `/admin embed crea` (modulo a 5 campi) | NF-17 |
| UTL-074 | Campi separati: autore, piè di pagina, miniatura, immagine, link, data | ProBot [PROBOT], Mimu (`/embed edit author`, `footer`, `title`, `description`, `thumbnail`, `image`, `color`) [MIMU] | ❌ manca | Sotto-passi del costruttore; limiti 256/4096/1024/25/6000 al salvataggio | NF-17 |
| UTL-075 | Embed scritto in JSON | Carl-bot (`cembed`) [CARL], YAGPDB (`/customembed`) [YAGPDB] | ❌ manca | Opzione `json` (file allegato) con controllo dei campi | nuova |
| UTL-076 | Ottenere il JSON di un embed già pubblicato | Carl-bot (`embedsource`) [CARL] | ❌ manca | `/admin embed esporta` (file) | nuova |
| UTL-077 | Modificare un messaggio già mandato dal bot | Carl-bot (`editembed`, `ecembed`) [CARL], YAGPDB ("Message Creator", azione "Edit") [YAGPDB], ProBot [PROBOT] | ❌ manca | `/admin embed modifica <link>`; solo messaggi del bot | NF-17 |
| UTL-078 | Embed salvati con nome, da riusare altrove | Mimu (`/embed list`, `/embed show`) [MIMU] | ❌ manca | `/admin embed elenco`; base di RUO-001 e UTL-018 | NF-17 |
| UTL-079 | Messaggio con più embed (fino a 10) | YAGPDB [YAGPDB] | ❌ manca | Elenco di embed nello stesso messaggio; somma ≤ 6000 caratteri | nuova |
| UTL-080 | Messaggio con bottoni e menu aggiunti dall'admin | YAGPDB [YAGPDB], Sapphire [SAPPHIRE] | ❌ manca | Solo bottoni-link e bottoni che richiamano un tag (UTL-050) | nuova |
| UTL-081 | Messaggi "Components V2" (testo, immagini e bottoni in un unico blocco) | YAGPDB (fino a 40 componenti) [YAGPDB] | ❌ manca | Da valutare quando discord.py lo supporta bene | nuova |
| UTL-082 | Anteprima dal vivo mentre componi | YAGPDB [YAGPDB], Carl-bot (pannello) [CARL], ProBot [PROBOT] | ❌ manca | Nel pannello web; nei comandi: anteprima privata | NF-20 |
| UTL-083 | Far scrivere al bot un messaggio semplice in un canale | NadekoBot (`.say`) [NADEKO], Lawliet (`say`) [LAWLIET], FredBoat (`say`) [FRED] | ❌ manca | `/admin embed testo`; menzioni spente salvo permesso "Menziona tutti" (D12) | nuova |
| UTL-084 | Colore predefinito di tutti i messaggi del bot nel server | Mimu (`/set custom embedcolor`) [MIMU], NadekoBot (`.servercolorsshow`) [NADEKO], GiveawayBot (`/gsettings set color`) [GABOT] | ❌ manca | Impostazione `colore` usata dal costruttore di embed comune | nuova |
| UTL-085 | Limite di un invio al minuto dal costruttore | YAGPDB [YAGPDB] | ❌ manca | Pausa per server su `/admin embed pubblica` | NF-17 |

## 4. Sondaggi

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| UTL-086 | Fino a 10 opzioni | YAGPDB (`/poll`, 10) [YAGPDB], Lawliet (`vote`, 9) [LAWLIET] | 🟡 parziale: 5 opzioni | Portare a 10 (limite del sondaggio nativo) | M 10.1 |
| UTL-087 | Sondaggio rapido sì/no con reazioni | Carl-bot (`poll`) [CARL] | ❌ manca | `/utility poll` senza opzioni: 👍 👎 sul messaggio | nuova |
| UTL-088 | Voto anonimo | EasyPoll [EASYPOLL] | ❌ manca | Sondaggio proprio con bottoni (il nativo mostra chi vota); voti nel database | nuova |
| UTL-089 | Risultati nascosti fino alla chiusura | EasyPoll ("Reveal at End", "Secret Winner", "Blind Voting") [EASYPOLL] | ❌ manca | Opzione di UTL-088 | nuova |
| UTL-090 | Sondaggio programmato per una data futura | EasyPoll [EASYPOLL] | ❌ manca | Scheduler già esistente | nuova |
| UTL-091 | Modificare domanda, risposte o durata di un sondaggio aperto | EasyPoll (`/editpoll`) [EASYPOLL] | ❌ manca | Solo sui sondaggi propri (UTL-088) | nuova |
| UTL-092 | Chiusura automatica al raggiungimento di N voti | EasyPoll [EASYPOLL] | ❌ manca | Opzione `chiudi-a` | nuova |
| UTL-093 | Voti che pesano di più per certi ruoli | EasyPoll [EASYPOLL] | ❌ manca | Tabella ruolo→peso | nuova |
| UTL-094 | Sondaggio riservato a certi ruoli | EasyPoll [EASYPOLL] | ❌ manca | Elenco di ruoli ammessi | nuova |
| UTL-095 | Thread di discussione creato insieme al sondaggio | EasyPoll [EASYPOLL] | ❌ manca | Opzione `thread: sì` | nuova |
| UTL-096 | Voto tolto a chi lascia il server o viene bannato | EasyPoll [EASYPOLL] | ❌ manca | Eventi `on_member_remove` e `on_member_ban` | nuova |
| UTL-097 | Elenco dei sondaggi, riepilogo dettagliato, chiusura a mano | EasyPoll (`/listpolls`, `/showpoll`, `/closepoll`) [EASYPOLL] | ❌ manca | `/utility poll elenco/mostra/chiudi` | nuova |

## 5. Promemoria, messaggi ripetuti, eventi

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| UTL-098 | Promemoria che si ripete a intervalli | Carl-bot (`reminder repeat`) [CARL], Dank Memer [DANK], Reminder Bot (a pagamento) [REMBOT] | ❌ manca | Opzione `ripeti-ogni`; intervallo minimo 1 ora | nuova |
| UTL-099 | Promemoria pubblicato in un canale invece che in DM | NadekoBot (`.remind here` o canale) [NADEKO], Lawliet (`reminder`) [LAWLIET] | 🟡 parziale: il canale è solo il ripiego se i DM sono chiusi | Opzione `canale`; serve "Gestire messaggi" per usarla | nuova |
| UTL-100 | Iscriversi al promemoria di un altro utente | Carl-bot (`reminder subscribe`) [CARL], Dank Memer [DANK] | ❌ manca | Bottone "Ricordalo anche a me" sul messaggio di conferma | nuova |
| UTL-101 | Dettaglio di un promemoria (quando scatta) | Carl-bot (`reminder when`) [CARL] | 🟡 parziale: `/reminder list` | Orario in formato Discord nell'elenco | M 10.5 |
| UTL-102 | Cancellare tutti i propri promemoria | Carl-bot (`reminder clear`) [CARL] | ❌ manca | Opzione `tutti` in `/reminder cancel` | nuova |
| UTL-103 | Lo staff vede e cancella i promemoria del server | NadekoBot (`.remindlist server`, `.reminddelete server`) [NADEKO], YAGPDB (`/reminder channel`, `/reminder delete`) [YAGPDB], Lawliet (`remindermanage`) [LAWLIET] | ❌ manca | `/admin config promemoria`; solo quelli pubblicati in canale | nuova |
| UTL-104 | Orari scritti in chat convertiti da soli nel fuso di chi legge | YAGPDB (`/timezone toggleconversion`) [YAGPDB] | ❌ manca | Risposta con l'orario in formato Discord (`<t:…>`); serve `message_content` | nuova |
| UTL-105 | Messaggio ripetuto ogni N minuti, ore o giorni | NadekoBot (`.repeat`) [NADEKO], Carl-bot (`autofeeds repeat`) [CARL], Sapphire [SAPPHIRE], Maki (3 gratis) [MAKI] | 🟡 parziale: `/schedule-message` manda una volta sola | Opzione `ripeti-ogni`; tetto per server; minimo 10 minuti | nuova |
| UTL-106 | Messaggio ripetuto ogni giorno a un'ora fissa | NadekoBot (`.repeat` con orario) [NADEKO] | ❌ manca | Opzione `alle`; fuso del server | nuova |
| UTL-107 | Non ripubblicare se l'ultimo messaggio del canale è già quello | NadekoBot (`.repeatredundant`) [NADEKO] | ❌ manca | Controllo dell'ultimo messaggio prima dell'invio | nuova |
| UTL-108 | Saltare la prossima uscita di un messaggio ripetuto | NadekoBot (`.repeatskip`) [NADEKO] | ❌ manca | Opzione in `/schedule-message` | nuova |
| UTL-109 | "Bacheca" con ruolo iscritto: l'annuncio pinga il ruolo solo per un attimo | Carl-bot (`feeds create`, `feeds announce`, `feeds move`, `feeds delete`) [CARL] | ❌ manca | Ruolo non menzionabile; ping permesso solo dal bot (`allowed_mentions`) | nuova |
| UTL-110 | Messaggio programmato con @everyone o @here | Carl-bot (`autofeeds everyone`, `autofeeds here`) [CARL] | 🟡 parziale: i ping nei messaggi programmati oggi sono muti | Solo se chi configura ha "Menziona tutti" (D12) | M 10.6 |
| UTL-111 | Eseguire un comando del bot più tardi | NadekoBot (`.scheduleadd`, `.schedulelist`, `.scheduledelete`: fino a 5) [NADEKO] | ❌ manca | Solo per poche azioni sicure (sblocca canale, togli ruolo) | nuova |
| UTL-112 | Pubblicare da soli i messaggi di un canale annunci | NadekoBot (`.autopublish`) [NADEKO] | ❌ manca | `message.publish()` nei canali scelti; limite di Discord sulle pubblicazioni all'ora | nuova |
| UTL-113 | Eventi con iscrizioni: titolo, ora, posti massimi | YAGPDB (`/events create`, `edit`, `list`, `delete`) [YAGPDB] | ❌ manca | Messaggio con bottoni "Partecipo / Forse / No"; oppure eventi nativi di Discord (permesso `CREATE_EVENTS`) | nuova |

## 6. Giveaway

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| UTL-114 | Chiudere un giveaway prima del tempo | GiveawayBot (`/gend`) [GABOT], Carl-bot (`giveaway end`) [CARL], NadekoBot (`.giveawayend`) [NADEKO], Giveaway Boat (`end`) [GBOAT] | ❌ manca | `/admin economia giveaway chiudi` | NF-28 |
| UTL-115 | Estrarre un nuovo vincitore | GiveawayBot (`/greroll`) [GABOT], Carl-bot [CARL], NadekoBot [NADEKO], Lawliet [LAWLIET], Giveaway Boat [GBOAT] | ❌ manca | `/admin economia giveaway riestrai` | NF-28 |
| UTL-116 | Riestrarre dal menu "tasto destro" sul messaggio | GiveawayBot (App > Reroll Giveaway) [GABOT] | ❌ manca | Voce del menu contestuale (15 posti) | nuova |
| UTL-117 | Annullare un giveaway senza vincitori | GiveawayBot (`/gdelete`) [GABOT], NadekoBot (`.giveawaycancel`) [NADEKO], Giveaway Boat (`delete`) [GBOAT] | ❌ manca | `/admin economia giveaway annulla` | NF-28 |
| UTL-118 | Elenco dei giveaway in corso | GiveawayBot (`/glist`) [GABOT], Carl-bot (`giveaway list`) [CARL], NadekoBot [NADEKO] | ❌ manca | `/admin economia giveaway elenco` | NF-28 |
| UTL-119 | Elenco dei partecipanti | Carl-bot (`giveaway participants`) [CARL] | ❌ manca | File allegato se sono molti | nuova |
| UTL-120 | Riepilogo a fine giveaway con un bottone | GiveawayBot [GABOT] | ❌ manca | Bottone "Riepilogo" sul messaggio chiuso | nuova |
| UTL-121 | Creazione guidata a passi | GiveawayBot (`/gcreate`) [GABOT], Giveaway Boat [GBOAT], Lawliet [LAWLIET] | 🟡 parziale: un solo comando con opzioni | Modulo a 5 campi | NF-28 |
| UTL-122 | Modelli riusabili | Giveaway Boat (`template create`, `edit`, `delete`, `view`) [GBOAT] | ❌ manca | Tabella dei modelli | NF-28 |
| UTL-123 | Giveaway programmato | Giveaway Boat (`schedule`) [GBOAT] | ❌ manca | Scheduler | NF-28 |
| UTL-124 | Requisito "numero di messaggi" | Giveaway Boat (`lock messages`) [GBOAT] | ❌ manca | Dipende dalle statistiche (NF-25) | NF-28 |
| UTL-125 | Ruoli che saltano i requisiti | Giveaway Boat (`bypass role`) [GBOAT] | ❌ manca | Elenco di ruoli | NF-28 |
| UTL-126 | Ruoli che non possono partecipare | Giveaway Boat (`blacklist role`) [GBOAT] | ❌ manca | Elenco di ruoli esclusi | nuova |
| UTL-127 | Più ingressi per certi ruoli | Giveaway Boat [GBOAT] | ❌ manca | Tabella ruolo→ingressi | NF-28 |
| UTL-128 | Modificare un giveaway in corso (durata, vincitori, nome, immagine) | Giveaway Boat (`edit`) [GBOAT], Lawliet [LAWLIET] | ❌ manca | Comando di modifica; titolo ≤ 256 | nuova |
| UTL-129 | Immagine e colore del messaggio del giveaway | Giveaway Boat [GBOAT], Lawliet [LAWLIET], GiveawayBot (colore) [GABOT] | ❌ manca | Due opzioni | nuova |
| UTL-130 | Emoji o testo del bottone di ingresso a scelta | GiveawayBot (`/gsettings set emoji`) [GABOT], Lawliet [LAWLIET] | ❌ manca | Impostazione del server | nuova |
| UTL-131 | Ruoli dati in premio ai vincitori | Lawliet ("Role Prizes") [LAWLIET] | ❌ manca | `check_role_assignable`; ruolo dato all'estrazione | nuova |
| UTL-132 | Messaggi personalizzati di conferma dell'ingresso e DM al vincitore | Giveaway Boat [GBOAT] | ❌ manca | Due testi con segnaposto | nuova |
| UTL-133 | Canale di log dei giveaway | Giveaway Boat (`logger`) [GBOAT] | ❌ manca | Tipo di uscita nel router (NF-01) | nuova |
| UTL-134 | Estrazione di un membro a caso, senza giveaway | NadekoBot (`.raffle`, `.raffleany`) [NADEKO] | ❌ manca | `/utility estrai [ruolo]` | nuova |

## 7. Suggerimenti

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| UTL-135 | Stati in più: "in valutazione" e "realizzato" | Carl-bot (`consider`, `implemented`) [CARL] | 🟡 parziale: solo approva e rifiuta | Due bottoni in più; decisione con `UPDATE … WHERE stato` (M 10.9) | nuova |
| UTL-136 | Motivo scritto dallo staff nella decisione | Carl-bot (`approve`, `deny` con motivo) [CARL], Lawliet (`suggmanage`) [LAWLIET] | ❌ manca | Modulo con un campo | nuova |
| UTL-137 | DM a chi ha proposto, con l'esito | Carl-bot (`suggestion dm`) [CARL] | ❌ manca | Interruttore; `HTTPException` catturata | nuova |
| UTL-138 | Canale separato dove finiscono i suggerimenti decisi | Carl-bot (`suggestion move`) [CARL] | ❌ manca | Secondo canale nel router | nuova |
| UTL-139 | Suggerimenti anonimi, con comando per lo staff per vedere l'autore | Carl-bot (`suggestion anon`, `suggestion who`) [CARL] | ❌ manca | Interruttore; autore sempre salvato nel database | nuova |
| UTL-140 | Colore che cambia quando i voti superano una soglia | Carl-bot (`suggestion limit`) [CARL] | ❌ manca | Soglia numerica | nuova |
| UTL-141 | Suggerimenti accettati solo da un canale | Carl-bot (`suggestion submit`) [CARL] | ❌ manca | Opzione `canale-invio` | nuova |
| UTL-142 | Scelta: l'esito modifica il messaggio originale o ne crea uno nuovo | Carl-bot (`suggestion edit`) [CARL] | ❌ manca | Interruttore | nuova |

## 8. Starboard e messaggi fissi

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| UTL-143 | Canale starboard con soglia di stelle | Carl-bot (`starboard`, `star limit`) [CARL], MEE6 (gratis) [MEE6], ProBot (`starboard`) [PROBOT] | ❌ manca | `/admin starboard imposta`, `soglia` | NF-08 |
| UTL-144 | Permettere o vietare la stella ai propri messaggi | Carl-bot (`star self`) [CARL] | ❌ manca | Interruttore | NF-08 |
| UTL-145 | Canali NSFW: immagini mostrate o nascoste | Carl-bot (`star nsfw`) [CARL] | ❌ manca | Default: esclusi | NF-08 |
| UTL-146 | Canali esclusi dalla starboard | Carl-bot (`star blacklist`, `unblacklist`) [CARL] | ❌ manca | Elenco di canali | NF-08 |
| UTL-147 | Emoji diversa dalla stella | Carl-bot (`star emoji`, premium) [CARL] | ❌ manca | Impostazione | nuova |
| UTL-148 | Statistiche: chi riceve più stelle | Carl-bot (`star stats`) [CARL] | ❌ manca | `/utility stelle` | nuova |
| UTL-149 | Messaggio stellato a caso | Carl-bot (`star random`) [CARL] | ❌ manca | Comando semplice | nuova |
| UTL-150 | Mostrare un messaggio stellato o saltarci | Carl-bot (`star show`, `star jump`) [CARL] | ❌ manca | Link nel messaggio in bacheca | NF-08 |
| UTL-151 | Bloccare la starboard (sola lettura) | Carl-bot (`star lock`) [CARL] | ❌ manca | Interruttore | nuova |
| UTL-152 | Ogni nuovo messaggio di un canale finisce in bacheca da solo | Carl-bot (`star autostar`, premium) [CARL] | ❌ manca | Elenco di canali "sempre in bacheca" | nuova |
| UTL-153 | Riepilogo delle impostazioni e rimozione della starboard | Carl-bot (`star config`, `star remove`) [CARL] | ❌ manca | `/admin starboard stato`, `disattiva` | NF-08 |
| UTL-154 | Elenco dei messaggi fissi del server | Carl-bot (`sticky list`) [CARL] | ❌ manca | `/sticky list` | nuova |
| UTL-155 | Modelli pronti per i messaggi fissi | Carl-bot (`sticky template`) [CARL] | ❌ manca | 2–3 modelli (regole, "leggi prima di scrivere") | nuova |

## 9. Compleanni

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| UTL-156 | Registrare il proprio compleanno (giorno e mese) | Carl-bot (`birthday set`) [CARL], Lawliet (`birthday`) [LAWLIET], MEE6 (premium) [MEE6] | ❌ manca | `/level compleanno imposta`; niente anno | NF-26 |
| UTL-157 | Togliere il proprio compleanno | Carl-bot (`birthday remove`) [CARL] | ❌ manca | `/level compleanno rimuovi` | NF-26 |
| UTL-158 | Lo staff registra il compleanno di un altro membro | Carl-bot [CARL] | ❌ manca | Solo con il consenso dell'interessato: meglio non farlo | nuova |
| UTL-159 | Vedere il compleanno di un membro | Carl-bot (`birthday [membro]`) [CARL] | ❌ manca | Solo se l'utente lo ha reso pubblico | nuova |
| UTL-160 | Elenco dei prossimi compleanni | Carl-bot (`birthday list`) [CARL], Lawliet (`birthdaylist`) [LAWLIET] | ❌ manca | `/level compleanno prossimi`, 10 righe | nuova |
| UTL-161 | Canale degli auguri e ruolo temporaneo | Carl-bot (`birthday channel`) [CARL], Lawliet (`birthdayconfig`) [LAWLIET] | ❌ manca | `/admin compleanni canale`, `ruolo` | NF-26 |
| UTL-162 | Riepilogo della configurazione dei compleanni | Carl-bot (`birthday config`) [CARL] | ❌ manca | `/admin compleanni stato` | NF-26 |

## 10. Inviti

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| UTL-163 | Quante persone ha invitato un membro | Invite Tracker (`/invites`) [INVTR], Lawliet (`invites`) [LAWLIET], MEE6 (premium) [MEE6] | 🟡 parziale: l'invito usato finisce nei log, nessun comando | `/level inviti` | NF-27 |
| UTL-164 | Classifica degli inviti, per periodo e per ruolo | Invite Tracker (`/leaderboard invites`) [INVTR], Lawliet (`invtop`) [LAWLIET] | ❌ manca | `/level leaderboard tipo:inviti` | NF-27 |
| UTL-165 | Chi ha invitato un certo membro | Invite Tracker (`/inviter`, premium) [INVTR] | 🟡 parziale: l'informazione è nel log di ingresso | `/mod caso` o `/level inviti chi` | nuova |
| UTL-166 | Elenco dei membri invitati da una persona o da un codice | Invite Tracker (`/invitedlist`, premium) [INVTR] | ❌ manca | Elenco a pagine | nuova |
| UTL-167 | Elenco dei codici d'invito di un membro, con gli usi | Invite Tracker (`/invitecodes`) [INVTR], NadekoBot (`.invitelist`) [NADEKO] | ❌ manca | Lettura di `guild.invites()`; 1000 inviti per server | nuova |
| UTL-168 | Conteggio "pulito": inviti meno usciti meno finti più bonus | Invite Tracker [INVTR] | ❌ manca | Quattro contatori per membro | NF-27 |
| UTL-169 | Inviti "finti": account più giovani di N giorni non contano | Invite Tracker (3 giorni di default) [INVTR] | ❌ manca | Soglia configurabile; riusa il controllo d'età dell'anti-raid | nuova |
| UTL-170 | Chi rientra conta come invito finto | Invite Tracker [INVTR] | ❌ manca | Interruttore | nuova |
| UTL-171 | Aggiungere o togliere inviti a mano (bonus) | Lawliet (`invmanage`) [LAWLIET], Invite Tracker (inviti "bonus") [INVTR] | ❌ manca | `/admin economia inviti bonus` | nuova |
| UTL-172 | Utenti o ruoli che non possono guadagnare inviti | Invite Tracker (3 gratis, 100 premium; ruoli solo premium) [INVTR] | ❌ manca | Elenco di esclusi | nuova |
| UTL-173 | Nascondere certi utenti dalla classifica | Invite Tracker [INVTR] | ❌ manca | Elenco di nascosti (es. lo staff) | nuova |
| UTL-174 | Etichette sui codici d'invito, con ruolo dato a chi entra da quel link | Invite Tracker ("Invite Labels", 1 gratis) [INVTR] | ❌ manca | Tabella codice→etichetta→ruolo; utile per partner e campagne | nuova |
| UTL-175 | Benvenuto che nomina chi ha invitato e quanti inviti ha | Invite Tracker (`%inviter%`, `%inviter_invites%`, `%invite_code%`) [INVTR] | ❌ manca | Segnaposto `{invitante}` e `{inviti}` in `/admin benvenuto`; l'attribuzione può sbagliare (LC-6) | nuova |
| UTL-176 | Segnaposto "quante volte è entrato e uscito" e date in formato Discord | Invite Tracker (`%member_join_count%`, `%member_created_at_R%`) [INVTR] | ❌ manca | Segnaposto nel renderer | nuova |
| UTL-177 | Canale di log degli inviti, con o senza ping | Lawliet ("Adjust Log Channel", "Ping Members") [LAWLIET] | 🟡 parziale: è nel log generale | Tipo di uscita "inviti" nel router (NF-01) | NF-01 |
| UTL-178 | Statistiche avanzate: ancora nel server, attivi dopo 7 giorni | Lawliet ("Advanced Statistics") [LAWLIET] | ❌ manca | Dipende dalle statistiche di attività (NF-25) | nuova |
| UTL-179 | Riallineare i conteggi con gli inviti reali del server | Invite Tracker (`/syncinvites`) [INVTR] | ❌ manca | Comando di manutenzione | nuova |
| UTL-180 | Cancellare un codice d'invito o molti insieme (per usi o canale) | Invite Tracker (`/deleteinvite`, `/purge-invite-codes`) [INVTR], NadekoBot (`.invitedelete`) [NADEKO] | ❌ manca | `/admin config inviti pulisci`; riusa la pulizia inviti dello spam-trap | nuova |
| UTL-181 | Creare un invito senza scadenza da comando | NadekoBot (`.invitecreate`) [NADEKO], Invite Tracker (`/findlink`) [INVTR] | ❌ manca | `/utility invito` | nuova |
| UTL-182 | Azzerare gli inviti di tutti | Lawliet [LAWLIET] | ❌ manca | Comando con conferma | nuova |
| UTL-183 | Esportare classifica o elenco degli invitati in CSV | Invite Tracker (`/exportleaderboard`, `/exportinvitedlist`, premium) [INVTR] | ❌ manca | File allegato sotto 10 MiB | nuova |
| UTL-184 | Bannare in blocco tutti gli entrati da un invito | Invite Tracker (`/massban`, premium) [INVTR] | ❌ manca | Strumento anti-raid: `/modban` con filtro "codice invito"; pause tra i ban | nuova |

## 11. Conteggio in un canale

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| UTL-185 | Canale dove si conta un numero alla volta | Countr (`/channels new`, `/channels link`) [COUNTR], NadekoBot (`.countup`) [NADEKO] | ❌ manca | `/admin config conteggio`; serve `message_content`; i messaggi sbagliati vengono cancellati | NF-40 |
| UTL-186 | Più canali di conteggio nello stesso server | Countr [COUNTR] | ❌ manca | Una riga per canale | nuova |
| UTL-187 | Altri modi di contare (binario, numeri romani, lettere) | Countr ("Counting Systems") [COUNTR] | ❌ manca | 2–3 sistemi | nuova |
| UTL-188 | Classifica di chi ha contato di più | Countr ("Scores & Leaderboard") [COUNTR] | ❌ manca | `/level leaderboard tipo:conteggio` | nuova |
| UTL-189 | Ruolo all'ultimo che ha contato o a certe posizioni | Countr ("Position Roles") [COUNTR] | ❌ manca | Un ruolo che passa di mano | nuova |
| UTL-190 | Punizione a chi sbaglia: non può contare per un tempo | Countr ("Timeouts") [COUNTR] | ❌ manca | Ruolo a tempo (RUO-042) | nuova |
| UTL-191 | Azioni automatiche a certi traguardi (ogni 100, a un numero preciso) | Countr ("Flows") [COUNTR] | ❌ manca | Regole semplici: ruolo, messaggio, fissa il messaggio | nuova |
| UTL-192 | Filtri su cosa si può scrivere accanto al numero | Countr ("Regex Filters", "Modules") [COUNTR] | ❌ manca | Opzione "solo il numero" o "numero più testo" | nuova |
| UTL-193 | Avviso personale quando il conteggio arriva a un numero | Countr ("Notifications") [COUNTR] | ❌ manca | DM una volta sola | nuova |
| UTL-194 | Importare i punteggi da un altro bot | Countr (`/data import scores`, `/scores fetch`) [COUNTR] | ❌ manca | Import da file JSON | nuova |

## 12. Strumenti, informazioni, ricerche

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| UTL-195 | Scheda di un utente: ruoli, date, ID | Carl-bot (`info`) [CARL], YAGPDB (`/whois`) [YAGPDB], ProBot (`user`) [PROBOT], Arcane (`/userinfo`) [ARCANE], Lawliet [LAWLIET] | ❌ manca | `/utility utente` | nuova |
| UTL-196 | Avatar in grande, globale o del server | Carl-bot (`avatar`) [CARL], ProBot [PROBOT], Arcane [ARCANE], NadekoBot (`.avatar`, `.banner`) [NADEKO] | ❌ manca | `/utility avatar` (nell'app utente è già previsto: B3) | NF-36 |
| UTL-197 | Scheda del server: proprietario, data, numeri, boost | Carl-bot (`serverinfo`) [CARL], ProBot (`server`) [PROBOT], Arcane [ARCANE], Red (`serverinfo`) [RED] | 🟡 parziale: `/serverstats` mostra numeri e grafico | Aggiungere i dati mancanti a `/utility serverstats` | nuova |
| UTL-198 | Scheda di un canale | Lawliet (`channelinfo`) [LAWLIET] | ❌ manca | `/utility canale` | nuova |
| UTL-199 | Classifiche "account più vecchi", "più nuovi", "entrati per primi", "ultimi entrati" | Carl-bot (`oldest`, `youngest`, `oldusers`, `newusers`) [CARL] | ❌ manca | `/utility membri ordina:…`; 25 righe | nuova |
| UTL-200 | Elenco dei membri che hanno un ruolo | NadekoBot (`.inrole`) [NADEKO] | ❌ manca | `/utility membri ruolo:…`, a pagine | nuova |
| UTL-201 | Esportare l'elenco dei membri con filtri e formato a scelta | Carl-bot (`dump`) [CARL] | ❌ manca | File allegato; solo per gli admin; dato personale (NF-04) | nuova |
| UTL-202 | Permessi del bot o di un membro in un canale | Carl-bot (`botpermissions`, `misc permissions`) [CARL], YAGPDB (`/viewperms`) [YAGPDB], Invite Tracker (`/check-permissions`) [INVTR], NadekoBot (`.checkperms`) [NADEKO] | 🟡 parziale: `/permission-heatmap` guarda i ruoli, non i canali | `/admin config permessi <canale>`: cosa manca al bot per funzionare lì | nuova |
| UTL-203 | Informazioni sui caratteri di un testo | Carl-bot (`charinfo`) [CARL] | ❌ manca | Utile contro i nomi con caratteri strani | nuova |
| UTL-204 | Salvare gli ultimi N messaggi di un canale in un file | NadekoBot (`.savechat`, fino a 1000) [NADEKO], YAGPDB (`/logs`) [YAGPDB] | 🟡 parziale: c'è il transcript dei ticket | `/mod esporta-chat`; file sotto 10 MiB | nuova |
| UTL-205 | Messaggi cancellati di recente: ognuno vede i suoi, lo staff tutti | YAGPDB (`/undelete`: 1 ora, 12 premium) [YAGPDB], NadekoBot (`.snipe`) [NADEKO] | ❌ manca | Opzione `utente` in `/utility snipe`; memoria breve | NF-03 |
| UTL-206 | Raccolta di citazioni del server: aggiungi, mostra a caso, cerca | NadekoBot (`.quoteadd`, `.quoteprint`, `.quotesearch`, `.quotelist`, `.quoteshow`, `.quoteedit`, `.quotedelete`) [NADEKO] | ❌ manca | `/utility citazione`; voce "Salva come citazione" nel menu del messaggio | nuova |
| UTL-207 | Esportare e importare le citazioni | NadekoBot (`.quotesexport`, `.quotesimport`) [NADEKO] | ❌ manca | File; `max_length` all'import | nuova |
| UTL-208 | Accorciare un link | ProBot (`short`) [PROBOT] | ❌ manca | Serve un servizio esterno: bassa priorità | nuova |
| UTL-209 | Aggiungere un'emoji o uno sticker al server da comando | NadekoBot (`.emojiadd`, `.emojiremove`, `.stickeradd`) [NADEKO] | ❌ manca | Serve il permesso `CREATE_GUILD_EXPRESSIONS`; 50 emoji e 5 sticker senza boost | nuova |
| UTL-210 | Creare o cancellare un thread da comando | NadekoBot (`.threadcreate`, `.threaddelete`) [NADEKO] | ❌ manca | Discord lo fa già: bassa priorità | nuova |
| UTL-211 | Spostarsi o spostare un membro in un altro canale vocale | ProBot (`moveme`, `move`) [PROBOT] | ❌ manca | `/mod sposta` | nuova |
| UTL-212 | Cronometro | Red (`stopwatch`) [RED] | ❌ manca | Due chiamate dello stesso comando | nuova |
| UTL-213 | Meteo di una città | YAGPDB (`/fun weather`) [YAGPDB], NadekoBot (`.weather`) [NADEKO], FredBoat [FRED] | ❌ manca | Servizio esterno con chiave; cache; `defer()` | nuova |
| UTL-214 | Definizione di una parola (dizionario) | YAGPDB (`/fun dictionary`, `/fun define`) [YAGPDB], NadekoBot (`.define`, `.urbandict`) [NADEKO], Red (`urban`) [RED] | ❌ manca | Dizionario italiano; Urban Dictionary solo nei canali NSFW | nuova |
| UTL-215 | Ricerca su Wikipedia | NadekoBot (`.wiki`) [NADEKO] | ❌ manca | API pubblica di Wikipedia, lingua del server | nuova |
| UTL-216 | Ricerca di un video o "cerca qualsiasi cosa" | NadekoBot (`.youtube`, `.google`, `.image`) [NADEKO], MEE6 ("Search anything", gratis) [MEE6] | 🟡 parziale: solo `/fun search-image` | Dipende da chiavi a quota; con l'AI (NF-24) | NF-24 |
| UTL-217 | Scheda di un film o di una serie | NadekoBot (`.movie`) [NADEKO] | ❌ manca | Servizio esterno con chiave | nuova |
| UTL-218 | Scheda di un gioco su Steam | NadekoBot (`.steam`) [NADEKO] | ❌ manca | Adatta a una community di gioco; API pubblica dello store | nuova |
| UTL-219 | Prezzo di criptovalute e azioni | NadekoBot (`.crypto`, `.coins`, `.stock`) [NADEKO], YAGPDB (`/fun forex`) [YAGPDB] | ❌ manca | Bassa priorità | nuova |
| UTL-220 | Numeri di aiuto per le emergenze, per paese | Mimu (`/hotlines online`, `/hotlines search`) [MIMU] | ❌ manca | Elenco statico curato, in italiano | nuova |
| UTL-221 | Elenco delle novità del bot | Lawliet (`new`) [LAWLIET] | ❌ manca | `/utility novita`: ultime voci del changelog | nuova |
| UTL-222 | Comandi più usati del bot | Lawliet (`commandusages`) [LAWLIET] | ❌ manca | Contatore per comando in `/owner stats` | nuova |

## 13. Configurazione del bot nel server

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| UTL-223 | Canali dove il bot non risponde ai comandi | Carl-bot (`ignore`, `unignore`) [CARL], Lawliet (`whitelist`) [LAWLIET] | 🟡 parziale: si fa dalle Integrazioni di Discord, ma nessuno lo spiega | Guida nel wizard; nessun codice | NF-05 |
| UTL-224 | Spegnere singoli comandi | Carl-bot (`disable`, `enable`, `enable list`) [CARL], Lawliet (`cman`) [LAWLIET], Mimu ("Deny Commands") [MIMU], YAGPDB ("Command Settings") [YAGPDB] | 🟡 parziale: `/setup` spegne interi moduli; i singoli comandi dalle Integrazioni | Come UTL-223 | NF-05 |
| UTL-225 | Risposte dei comandi deviate nel canale dei bot | Carl-bot (`restrict`, `unrestrict`) [CARL] | ❌ manca | Con gli slash basta la risposta effimera fuori dal canale scelto | nuova |
| UTL-226 | Pulizia della configurazione da canali e ruoli cancellati | Carl-bot (`cleanconfig`) [CARL] | ❌ manca | `/admin config pulisci`; il router avvisa già una volta (NF-01) | nuova |
| UTL-227 | Ruolo "moderatore del bot" | Carl-bot (`modrole`, `modrole clear`) [CARL] | ❌ manca | Con gli slash: delega dalle Integrazioni (NF-05) | NF-05 |
| UTL-228 | Azzerare tutti i dati del bot per il server | Mimu (`/reset server all`) [MIMU], UnbelievaBoat (`factory-reset`) [UNB] | 🟡 parziale: `/config reset` azzera la configurazione, non i dati | Opzione "anche i dati" con conferma; usa la cancellazione di NF-04 | NF-04 |
| UTL-229 | Registro di chi ha usato comandi che richiedono permessi speciali | Lawliet (`botlogs`) [LAWLIET] | 🟡 parziale: `/config history` registra solo le modifiche alla configurazione | Log dei comandi di staff nello storico eventi | nuova |

## Fonti

Lette il 4/10/2026.

- `[CARL]` Carl-bot — https://docs.carl.gg/tagstriggers.md · `/utilities.md` · `/misc.md` · `/starboard.md` · `/suggestions.md` · `/embeds.md` · `/feeds.md` · `/config.md` · `/greetings.md`
- `[YAGPDB]` YAGPDB — https://help.yagpdb.xyz/docs/custom-commands/commands/ · `/docs/tools-and-utilities/message-creator/` · `/docs/core/all-commands/` · `/docs/welcome/premium/` (letti dal sorgente ufficiale https://github.com/botlabs-gg/yagpdb-docs-v2)
- `[NADEKO]` NadekoBot — https://nadeko.bot/commands e sorgente ufficiale https://github.com/Kwoth/NadekoBot (`src/NadekoBot/strings/commands/commands.en-US.yml`)
- `[ARCANE]` Arcane — https://docs.arcane.bot/tag-system/reference · https://docs.arcane.bot/plugins/custom-commands · https://docs.arcane.bot/premium
- `[RED]` Red-DiscordBot — https://docs.discord.red/en/stable/cog_guides/customcommands.html · `/general.html` (letti dal sorgente https://github.com/Cog-Creators/Red-DiscordBot)
- `[LAWLIET]` Lawliet — sorgente ufficiale https://github.com/Aninoss/lawliet-bot (`utility_`, `configuration_`, `birthdays_`, `invite_tracking_category_`, `information_en_us.properties`)
- `[MIMU]` Mimu — https://docs.mimu.bot/command-list.md · https://docs.mimu.bot/llms.txt
- `[PROBOT]` ProBot — https://docs.probot.io/docs/modules/embed · https://probot.io/commands
- `[GABOT]` GiveawayBot — sorgente ufficiale https://github.com/jagrosh/GiveawayBot (README) · https://giveawaybot.party
- `[GBOAT]` Giveaway Boat — https://top.gg/bot/530082442967646230
- `[EASYPOLL]` EasyPoll — https://easypoll.com/
- `[INVTR]` Invite Tracker — https://docs.invite-tracker.com/commands/general · `/commands/administration` · `/dashboard/invite-tracking` · `/dashboard/messages/variables`
- `[COUNTR]` Countr — https://countr.xyz/docs/
- `[REMBOT]` Reminder Bot — https://reminder-bot.com
- `[DANK]` Dank Memer — https://top.gg/bot/270904126974590976
- `[FRED]` FredBoat — sorgente ufficiale https://github.com/freyacodes/FredBoat
- `[MEE6]` MEE6 — https://help.mee6.xyz/en/articles/710936-mee6-free-vs-premium-plans-comparison
- `[SAPPHIRE]` Sapphire — https://top.gg/bot/678344927997853742 (solo la scheda)
- `[MAKI]` Maki — https://maki.gg/premium (dato già in `CONFRONTO_BOT.md`)
- `[UNB]` UnbelievaBoat — https://faq.unbelievaboat.com/getting-started/configuring/

Non letti su fonte ufficiale:
- **Dyno** (moduli e comandi: le pagine `docs.dyno.gg` non mostrano il
  contenuto), **Atlas**, **Circle**, **Maki** (comandi), **Sapphire**
  (documentazione): nessuna loro funzione è in tabella oltre a quanto
  indicato.
- **Giveaway Boat**: la documentazione (`docs.giveaway.boats`) è vuota;
  le voci vengono dalla scheda top.gg scritta dagli autori del bot.
- **Countr**, **EasyPoll**: solo la pagina indice; i dettagli di ogni
  modulo non sono stati letti.
- **MEE6**: solo la tabella "gratis contro premium".

## Conteggio

229 righe: 209 ❌ e 20 🟡.
