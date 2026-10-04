# Catalogo — Economia e giochi

Moneta del server, banca, modi di guadagnare, negozio e inventario,
giochi con le monete, animali, pesca, progressione. 161 voci. Bot letti:
UnbelievaBoat, Dank Memer, Mimu, Lawliet, NadekoBot, Red-DiscordBot,
Tatsu, YAGPDB.

Legenda: ❌ manca · 🟡 parziale. "Scheda": NF-xx = scheda di
`NUOVE_FUNZIONI.md`; M x.y = riga di `MODIFICHE_ESISTENTE.md`;
"nuova" = non c'è ancora in nessun piano.

iYokai oggi (per confronto): `/daily` (200 monete, senza serie),
`/work` (ogni ora, importo fisso), `/pay`, `/balance`, monete dal
vocale, drop casuali nei canali (0,5% per messaggio, vince il primo
che clicca), `/shop add-item|remove-item|list|buy` (nome, prezzo,
ruolo, descrizione), cassa del server, tesoreria dei clan. Nessuna
banca, nessun inventario, nessun gioco con puntata.

**Regola da tenere a mente:** Discord vieta di monetizzare il gioco
d'azzardo. Le monete usate nei giochi di questa pagina non si devono
mai comprare con soldi veri (vedi NF-40).

## 1. Moneta, banca e impostazioni

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| ECO-001 | Nome o simbolo della moneta scelto dal server | UnbelievaBoat (`set-currency`) [UNB], Mimu (`/set currency`) [MIMU], Lawliet (`fisherycurrencies`) [LAWLIET] | ❌ manca | `/admin economia moneta`; testo o emoji, max 20 caratteri | nuova |
| ECO-002 | Saldo di partenza per i nuovi membri | UnbelievaBoat (`set-start-balance`) [UNB], Mimu (`/set currency start`) [MIMU] | ❌ manca | Impostazione numerica; accredito al primo ingresso, una volta sola | nuova |
| ECO-003 | Tetto massimo al saldo | UnbelievaBoat (`maximum-balance`, contanti e banca) [UNB] | ❌ manca | Impostazione numerica controllata a ogni accredito | nuova |
| ECO-004 | Banca: contanti e conto separati, con deposito e prelievo | UnbelievaBoat (`deposit`, `withdraw`) [UNB], NadekoBot (`.bank deposit`, `withdraw`, `balance`) [NADEKO], Red (`bank`) [RED] | ❌ manca | `/level banca deposita/preleva`; solo i contanti sono a rischio nei furti (ECO-031) | nuova |
| ECO-005 | Deposito vincolato: blocchi le monete una settimana e ricevi il 10% | Lawliet (`bank`) [LAWLIET] | ❌ manca | Scadenza nello scheduler; un deposito alla volta per utente | nuova |
| ECO-006 | Canale con il registro di tutti i movimenti di monete | UnbelievaBoat (`money-audit-log`) [UNB] | ❌ manca | Nuovo tipo di uscita nel router dei canali (NF-01) | nuova |
| ECO-007 | Storico personale dei propri movimenti | Dank Memer (`/currencylog`) [DANK], NadekoBot (`.curtrs`, `.curtr`) [NADEKO] | ❌ manca | `/level movimenti`, a pagine; tabella con scadenza (NF-04) | nuova |
| ECO-008 | Statistiche dell'economia del server (monete in giro, distribuzione) | UnbelievaBoat (`economy-stats`) [UNB] | 🟡 parziale: `/cassa saldo` mostra solo la cassa | `/admin economia statistiche` | nuova |
| ECO-009 | Lo staff aggiunge o toglie monete a un membro | UnbelievaBoat (`add-money`, `remove-money`) [UNB], Mimu (`/modifybal add`, `remove`) [MIMU], NadekoBot (`.award`, `.take`) [NADEKO], Red (`bank set`) [RED] | 🟡 parziale: `/assegna-winner` dà monete solo prendendole dalla cassa | `/admin economia monete aggiungi/togli`; riga nel log; `Range` sull'importo | nuova |
| ECO-010 | Aggiungere o togliere monete a tutti i membri di un ruolo | UnbelievaBoat (`add-money-role`, `remove-money-role`) [UNB], NadekoBot [NADEKO] | ❌ manca | Opzione `ruolo` del comando sopra; una sola transazione | nuova |
| ECO-011 | Azzerare il saldo di un membro | UnbelievaBoat (`reset-money`) [UNB], Mimu (`/reset user balance`) [MIMU] | ❌ manca | Comando con conferma | nuova |
| ECO-012 | Azzerare l'economia di tutto il server | UnbelievaBoat (`reset-economy`) [UNB], Mimu (`/reset server balances`) [MIMU] | ❌ manca | Conferma con il nome del server scritto a mano | nuova |
| ECO-013 | Togliere dalla classifica chi ha lasciato il server | UnbelievaBoat (`clean-leaderboard`) [UNB] | ❌ manca | Filtro "solo membri presenti" in `/level leaderboard` | nuova |
| ECO-014 | Scelta: il saldo di chi esce viene tenuto o cancellato | Mimu (`/set currency onleave`) [MIMU] | ❌ manca | Impostazione; va d'accordo con la conservazione dei dati (NF-04) | nuova |
| ECO-015 | Limiti e tassa sui trasferimenti tra utenti | Mimu (`/set currency transfer`) [MIMU] | 🟡 parziale: `/pay` senza limiti né tassa | Minimo, massimo e percentuale; la tassa va alla cassa del server | nuova |
| ECO-016 | Posizione in classifica mostrata insieme al saldo | UnbelievaBoat (`money`) [UNB], Dank Memer (posto mondiale per patrimonio) [DANK] | ❌ manca | Una riga in più in `/level balance` | nuova |
| ECO-017 | Saldo come immagine ("wallet card") | Tatsu [TATSU] | ❌ manca | Variante della rank card | NF-40 |
| ECO-018 | Due monete: una globale dell'utente e una del server | Tatsu [TATSU], Mimu (monete del server, più "tickets" e "stars" globali) [MIMU] | ❌ manca | Portafoglio globale separato; le due monete non si convertono | NF-40 |
| ECO-019 | Pausa dei comandi di guadagno scelta dal server | UnbelievaBoat (`set-cooldown`) [UNB], Mimu (`/set currency pet`, `snuggle`, `clickcake`) [MIMU] | ❌ manca | Impostazione per comando, con minimo e massimo | nuova |
| ECO-020 | Vedere in un colpo tutte le proprie pause attive | Lawliet (`cooldowns`) [LAWLIET] | ❌ manca | `/level pause` (risposta privata) | nuova |
| ECO-021 | Puntata minima e massima dei giochi | Mimu (`/set currency bet`) [MIMU], Red (`economyset slotmin`, `slotmax`) [RED] | ❌ manca | Due impostazioni usate da tutti i giochi (sezione 4) | NF-40 |
| ECO-022 | Pausa tra una partita e l'altra scelta dal server | UnbelievaBoat (`set-game-cooldown`) [UNB], Red (`economyset slottime`) [RED] | ❌ manca | Impostazione per gioco | NF-40 |
| ECO-023 | Riepilogo di tutte le impostazioni dell'economia | Red (`economyset showsettings`) [RED], Mimu (`/settings`) [MIMU] | ❌ manca | `/admin economia stato` | nuova |

## 2. Modi di guadagnare

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| ECO-024 | Premio periodico con importo e frequenza scelti dal server | NadekoBot (`.timely`, `.timelyset`) [NADEKO], Red (`economyset paydayamount`, `paydaytime`) [RED] | 🟡 parziale: `/daily` con valori fissi | Due impostazioni in `/admin economia` | NF-15 |
| ECO-025 | Premio giornaliero con serie di giorni: più giorni di fila, più monete | Dank Memer (`/daily`) [DANK] | ❌ manca | Contatore di serie; un giorno saltato la riduce | NF-41 |
| ECO-026 | Premi settimanale e mensile | Dank Memer (comandi a calendario; il mensile si sblocca) [DANK] | ❌ manca | `/level settimanale`, `/level mensile`; stesso schema anti-doppio di `/daily` (M 9.1) | nuova |
| ECO-027 | "Vacanza": la serie resta ferma fino a 90 giorni, a pagamento | Dank Memer (`/vacation`, oggetto "streak freeze") [DANK] | ❌ manca | Costo in monete; dipende da ECO-025 | NF-41 |
| ECO-028 | Lavoro con paga minima e massima scelte dal server | UnbelievaBoat (`work`) [UNB] | 🟡 parziale: `/work` con importo fisso | Due impostazioni | NF-15 |
| ECO-029 | Lavori diversi con ore al giorno, promozioni e licenziamento | Dank Memer (`/work`, `/work list`) [DANK] | ❌ manca | Elenco di lavori nel codice; promozione dopo N turni | NF-41 |
| ECO-030 | Colpo rischioso: paga alta ma multa se va male | UnbelievaBoat (`crime`: fallisce il 60%, paga 250–700, multa 20–40% del patrimonio) [UNB], Dank Memer [DANK] | ❌ manca | `/fun gioca colpo`; percentuali come impostazioni; il saldo non scende sotto zero | NF-40 |
| ECO-031 | Furto ai danni di un altro membro (solo i contanti) | UnbelievaBoat (`rob`: probabilità legata al patrimonio, pausa di 4 ore) [UNB], Dank Memer [DANK] | ❌ manca | Solo se il server lo accende; chi è derubato riceve un avviso; mai sulla banca | NF-40 |
| ECO-032 | Secondo comando di guadagno a rischio, con paga e rischio propri | UnbelievaBoat (`slut`) [UNB] | ❌ manca | Stesso motore di ECO-030 con nome neutro | NF-40 |
| ECO-033 | Monete per ogni messaggio, solo nei canali scelti | UnbelievaBoat ("chat money": 5–15 a messaggio, pausa di 1 minuto) [UNB], Mimu (`/set activity channels`, `settings`) [MIMU], Lawliet (pesci per messaggio) [LAWLIET] | ❌ manca: i messaggi danno solo XP | Stesso ascolto dell'XP; elenco di canali; pausa per utente | NF-15 |
| ECO-034 | Stipendio per ruolo, da riscuotere con un comando | UnbelievaBoat (`collect-income`; i ruoli si sommano) [UNB], Red (`economyset rolepaydayamount`) [RED] | ❌ manca | `/admin economia stipendio`; `/level riscuoti`; pausa per ruolo | nuova |
| ECO-035 | Stipendio per ruolo accreditato da solo, senza comando | UnbelievaBoat (ruolo @everyone e "slot" a pagamento) [UNB] | ❌ manca | Lavoro giornaliero, una query per server | nuova |
| ECO-036 | "Tassa" per ruolo: importo tolto a ogni giro | UnbelievaBoat [UNB] | ❌ manca | Stipendio con importo negativo; mai sotto zero | nuova |
| ECO-037 | Ora esatta di pagamento dello stipendio | UnbelievaBoat (premium) [UNB] | ❌ manca | Opzione `ora` (fuso del server) | nuova |
| ECO-038 | Stipendio versato in contanti o in banca | UnbelievaBoat [UNB] | ❌ manca | Opzione; dipende da ECO-004 | nuova |
| ECO-039 | Comandi di guadagno creati dal server | UnbelievaBoat (premium, 10 comandi) [UNB], Mimu (autorisponditori che danno monete: `.bake`, `.harvest`) [MIMU] | ❌ manca | Tag (NF-09) con azione "dà da X a Y monete" e pausa | NF-09 |
| ECO-040 | Chiedere l'elemosina: piccola cifra casuale, a volte niente | Dank Memer (`beg`) [DANK] | ❌ manca | `/fun gioca elemosina`; frasi in italiano | NF-40 |
| ECO-041 | Cercare monete scegliendo tra tre luoghi | Dank Memer (`search`) [DANK] | ❌ manca | Tre bottoni; esito casuale | NF-40 |
| ECO-042 | Scavare per trovare monete o oggetti | Dank Memer (`dig`) [DANK] | ❌ manca | Serve l'inventario (ECO-058) | NF-40 |
| ECO-043 | Gratta e vinci | Dank Memer (`scratch`) [DANK] | ❌ manca | Griglia di bottoni (5 per riga) | NF-40 |
| ECO-044 | Guadagnare "pubblicando meme" | Dank Memer (`postmemes`) (terzi) [DANK-T] | ❌ manca | Scelta tra tipi di meme, esito casuale | NF-40 |
| ECO-045 | "Diretta": gioco a serie giornaliera che paga monete | Dank Memer (`/stream`) [DANK] | ❌ manca | Dipende da ECO-025 | NF-41 |
| ECO-046 | Coccolare il bot per avere monete | Mimu (`/pet`, `/snuggle`) [MIMU] | ❌ manca | Variante leggera di `/work` | NF-40 |
| ECO-047 | Cliccare un bersaglio entro un tempo per guadagnare | Mimu (`/clickcake`) [MIMU] | ❌ manca | Bottone che compare dopo un'attesa casuale | NF-40 |
| ECO-048 | Monete a chi vota il bot su un elenco di bot | Dank Memer (`/vote`) [DANK], Lawliet (`claim`) [LAWLIET], NadekoBot (`.vote`) [NADEKO] | ❌ manca | Solo se iYokai sarà in un elenco; webhook del voto | nuova |
| ECO-049 | Riscatto automatico del premio del voto | Lawliet (`autoclaim`) [LAWLIET] | ❌ manca | Opzione personale; dipende da ECO-048 | nuova |
| ECO-050 | Il bot "lavora" da solo ogni 4 ore per l'utente | Lawliet (`autowork`, a pagamento) [LAWLIET] | ❌ manca | Opzione premium; lavoro nello scheduler | nuova |
| ECO-051 | Sondaggio periodico: chi vota può vincere monete | Lawliet (`survey`) [LAWLIET] | ❌ manca | Sondaggio settimanale dell'owner | nuova |
| ECO-052 | Lasciare monete in un canale: le prende chi arriva prima | Mimu (`/drop`, `/pick`) [MIMU], NadekoBot (`.plant`, `.pick`) [NADEKO] | 🟡 parziale: i drop sono solo automatici | `/level lascia <importo>`; stesso bottone dei drop | nuova |
| ECO-053 | Drop automatici regolabili: canali, importi, velocità, uno o più vincitori | Mimu (`/set pick channels`, `settings`) [MIMU], NadekoBot (`.gencurrency`, `.gencurlist`) [NADEKO] | 🟡 parziale: probabilità e importo fissi, in tutti i canali | Impostazioni in `/admin economia drop` | nuova |
| ECO-054 | Drop che si prendono scrivendo un codice | Mimu (difficoltà "codice richiesto") [MIMU] | ❌ manca | Modulo con un campo; il codice è sull'immagine o nel testo | nuova |
| ECO-055 | Lo staff fa comparire forzieri in un canale | Lawliet (`treasure`) [LAWLIET] | ❌ manca | `/admin economia forziere <quanti> <canale>` | nuova |
| ECO-056 | Potenziamenti a tempo che compaiono in chat | Lawliet (`powerup`) [LAWLIET] | ❌ manca | Bonus temporaneo (es. ×2 per un'ora) a chi lo prende | nuova |
| ECO-057 | Evento di monete in un canale, avviato e chiuso dallo staff | Mimu (`/event start`, `/event end`) [MIMU], NadekoBot (`.eventstart`) [NADEKO] | ❌ manca | `/admin economia evento`; tetto di monete distribuite | nuova |

## 3. Negozio, inventario, oggetti

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| ECO-058 | Inventario: gli oggetti comprati restano all'utente | UnbelievaBoat (`inventory`) [UNB], Dank Memer (`/inventory`) [DANK], Mimu [MIMU], Tatsu [TATSU] | ❌ manca: l'acquisto dà solo un ruolo | `/level inventario`; tabella utente-oggetto-quantità | NF-40 |
| ECO-059 | Usare un oggetto dell'inventario | UnbelievaBoat (`use-item`) [UNB], Mimu (`/shop use`) [MIMU] | ❌ manca | `/level usa <oggetto>` | NF-40 |
| ECO-060 | Più azioni per oggetto (dà un ruolo, toglie un ruolo, dà monete, manda un messaggio) | UnbelievaBoat (2 azioni gratis, 5 premium) [UNB], Mimu (`role`, `removerole`, `reply`) [MIMU] | 🟡 parziale: una sola azione, "dà un ruolo" | Tabella delle azioni; tetto per oggetto | NF-40 |
| ECO-061 | Requisiti per comprare (ruolo richiesto, altro) | UnbelievaBoat (2 gratis, 5 premium) [UNB], Mimu (`requirerole`) [MIMU], NadekoBot (`.shopreq`) [NADEKO] | ❌ manca | Colonna `ruolo_richiesto`; poi livello minimo | nuova |
| ECO-062 | Scorte limitate | Mimu (`stock`, 0 = infinito) [MIMU] | ❌ manca | Colonna `scorte`; scalata dentro la transazione d'acquisto (M 9.2) | nuova |
| ECO-063 | Ruolo comprato che scade dopo un tempo | UnbelievaBoat ("time limit") [UNB] | ❌ manca | Scadenza nello scheduler | nuova |
| ECO-064 | Modificare un oggetto già in vendita (nome, prezzo, scorte, ruoli) | Mimu (`/shop edit …`) [MIMU], NadekoBot (`.shopchangeprice`, `.shopchangename`) [NADEKO] | ❌ manca: solo aggiungi e rimuovi | `/level shop modifica` | nuova |
| ECO-065 | Ordine degli oggetti nel negozio | NadekoBot (`.shopswap`, `.shopmove`) [NADEKO] | ❌ manca | Colonna `posizione` | nuova |
| ECO-066 | Categorie nel negozio | UnbelievaBoat ("shop categories") [UNB] | ❌ manca | Colonna `categoria` e menu a tendina (25 voci) | nuova |
| ECO-067 | Oggetto "a elenco": ogni acquisto consegna una riga diversa (codici, chiavi) | NadekoBot (`.shoplistadd`) [NADEKO] | ❌ manca | Righe consegnate in DM; ognuna una volta sola | nuova |
| ECO-068 | Testo di risposta personalizzato dopo l'acquisto o l'uso | Mimu (`reply`) [MIMU] | ❌ manca | Campo testo ≤ 500 | nuova |
| ECO-069 | Conferma prima dell'acquisto, che si può spegnere | Mimu (`/set currency confirmbuy`) [MIMU] | ❌ manca | Bottone "Conferma" | nuova |
| ECO-070 | Regalare un oggetto a un altro utente | Mimu (`/give item`) [MIMU], Dank Memer (amici) [DANK], Tatsu [TATSU] | ❌ manca | `/level regala`; transazione con righe bloccate in ordine di ID (M 9.16) | NF-40 |
| ECO-071 | Oggetto che non si può regalare | Mimu (`disablegive`) [MIMU] | ❌ manca | Colonna booleana | NF-40 |
| ECO-072 | Vendere oggetti e ricevere monete | Tatsu [TATSU], Lawliet (`sell`) [LAWLIET] | ❌ manca | Prezzo di rivendita fisso (es. 50%) | NF-40 |
| ECO-073 | Scheda di un oggetto con descrizione e valore | Dank Memer (`/item`) [DANK] | 🟡 parziale: `/shop list` mostra nome e prezzo | `/level shop info` | NF-40 |
| ECO-074 | Mercato tra giocatori: annunci, offerte, scadenza | Dank Memer (`/market`, `/market view`, `/market accept`) [DANK], Tatsu [TATSU] | ❌ manca | Solo dentro il server; nessun soldo vero | NF-40 |
| ECO-075 | Negozio con oggetti che ruotano a caso | Dank Memer [DANK] | ❌ manca | Rotazione giornaliera | NF-40 |
| ECO-076 | Offerte lampo: oggetto in vendita per poco, con bottone | Dank Memer ("drops") [DANK] | ❌ manca | Messaggio con bottone e scadenza | NF-40 |
| ECO-077 | Casse a sorpresa con contenuto casuale | Dank Memer ("lootbox") [DANK] | ❌ manca | Solo comprate con monete di gioco, mai con soldi veri | NF-40 |
| ECO-078 | Creare oggetti da altri oggetti (ricette) | Dank Memer ("crafting") [DANK] | ❌ manca | Tabella delle ricette | NF-40 |
| ECO-079 | Tabella "cosa si può trovare" per ogni comando di guadagno | Dank Memer (`/table`) [DANK] | ❌ manca | Elenco statico generato dal codice | NF-40 |
| ECO-080 | Negozio sfogliabile anche dal sito | Tatsu [TATSU] | ❌ manca | Pagina del pannello web | NF-20 |
| ECO-081 | Attrezzatura che aumenta i guadagni, a livelli | Lawliet (`buy`, `gear`) [LAWLIET] | 🟡 parziale: esistono solo i boost dei clan | Potenziamenti personali a livelli, costo crescente | NF-40 |
| ECO-082 | Cambio del giorno: il valore di ciò che vendi varia ogni giorno | Lawliet (`exch`, `sell`) [LAWLIET] | ❌ manca | Tasso giornaliero dentro una fascia | NF-40 |
| ECO-083 | Vendita automatica quando il cambio supera una soglia | Lawliet (`autosell`) [LAWLIET] | ❌ manca | Opzione personale; dipende da ECO-082 | NF-40 |
| ECO-084 | Borsa finta: comprare e vendere azioni virtuali | Lawliet (`stocks`) [LAWLIET] | ❌ manca | Prezzi inventati dal bot | NF-40 |
| ECO-085 | Ordini automatici in borsa a soglia | Lawliet (`autostocks`) [LAWLIET] | ❌ manca | Dipende da ECO-084 | NF-40 |
| ECO-086 | Azzerare inventari o negozio del server | Mimu (`/reset user inventory`, `/reset server inventories`, `/reset server shop`) [MIMU] | ❌ manca | Comandi con conferma | nuova |
| ECO-087 | Casa personale da arredare con mobili | Tatsu (oltre 1.000 mobili) [TATSU] | ❌ manca | Immagine composta con Pillow | NF-40 |

## 4. Giochi con le monete

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| ECO-088 | Blackjack | UnbelievaBoat [UNB], Lawliet [LAWLIET], NadekoBot (`.blackjack`, `.hit`, `.stand`, `.double`) [NADEKO], Dank Memer [DANK] | ❌ manca | `/fun gioca blackjack`; bottoni; saldo mai negativo | NF-40 |
| ECO-089 | Blackjack con raddoppio, divisione e resa | Dank Memer [DANK] | ❌ manca | Estensione di ECO-088 | NF-40 |
| ECO-090 | Roulette con puntate su colore, pari o dispari, dozzine, colonne, numero | UnbelievaBoat (paga da 2× a 36×) [UNB] | ❌ manca | `/fun gioca roulette` | NF-40 |
| ECO-091 | Roulette a più giocatori con conto alla rovescia | UnbelievaBoat [UNB] | ❌ manca | Una partita per canale | NF-40 |
| ECO-092 | Slot machine | UnbelievaBoat [UNB], Mimu (`/slots`) [MIMU], Red (`slot`) [RED], Lawliet [LAWLIET], NadekoBot [NADEKO] | ❌ manca | `/fun gioca slot` | NF-40 |
| ECO-093 | Roulette russa a più giocatori | UnbelievaBoat [UNB] | ❌ manca | Tema delicato: nome e grafica neutri | NF-40 |
| ECO-094 | "Più alto o più basso" | UnbelievaBoat [UNB] | ❌ manca | Due bottoni; il premio cresce a ogni risposta giusta | NF-40 |
| ECO-095 | Testa o croce con puntata | Mimu (`/coinflip`) [MIMU], Lawliet [LAWLIET], NadekoBot (`.betflip`) [NADEKO] | 🟡 parziale: `/fun coinflip` senza puntata | Opzione `puntata` | NF-40 |
| ECO-096 | Dadi con puntata e moltiplicatore | Mimu (`/rolldice`) [MIMU], NadekoBot (`.betroll`) [NADEKO] | 🟡 parziale: `/fun dice` senza puntata | Opzione `puntata` | NF-40 |
| ECO-097 | Sasso-carta-forbici con puntata | NadekoBot (`.rps`) [NADEKO] | 🟡 parziale: `/fun rps` senza puntata | Opzione `puntata` | NF-40 |
| ECO-098 | "Torre": alzi il moltiplicatore finché non crolla | Lawliet (`tower`) [LAWLIET] | ❌ manca | Due bottoni: alza o incassa | NF-40 |
| ECO-099 | "Scala fortunata" | NadekoBot (`.luckyladder`) [NADEKO] | ❌ manca | Estrazione di un gradino con moltiplicatore | NF-40 |
| ECO-100 | Scommessa sulla carta estratta (colore e valore) | NadekoBot (`.betdraw`) [NADEKO] | ❌ manca | Mazzo virtuale | NF-40 |
| ECO-101 | Combattimento tra galli comprati al negozio | UnbelievaBoat (`chicken-fight`: forza 50–70%, +1% a vittoria) [UNB] | ❌ manca | Meglio una creatura di fantasia | NF-40 |
| ECO-102 | Corse di animali: compri, nutri, alleni e fai correre | UnbelievaBoat (`animals store`, `buy`, `inventory`; `provisions`; `animal-race`) [UNB] | ❌ manca | Statistiche di età, salute, energia, esperienza | NF-40 |
| ECO-103 | Corsa di animali a cui ci si unisce con una puntata | NadekoBot (`.race`, `.joinrace`) [NADEKO] | ❌ manca | Una corsa per canale, iscrizione a tempo | NF-40 |
| ECO-104 | Duello tra utenti con posta in monete o oggetti | Dank Memer (`/fight quick`, 7 modalità) [DANK] | ❌ manca | Turni con bottoni | NF-40 |
| ECO-105 | Combattimento a più giocatori con regole su misura | Dank Memer (`/fight create`, fino a 6) [DANK] | ❌ manca | Estensione di ECO-104 | NF-40 |
| ECO-106 | Classifica e storico dei duelli | Dank Memer (`/fight ranking`, `/fight history`) [DANK] | ❌ manca | Tabella degli esiti | NF-40 |
| ECO-107 | Forza 4 tra utenti, anche con puntata | NadekoBot (`.connect4`) [NADEKO], Dank Memer [DANK] | ❌ manca | Griglia di bottoni (5 righe da 5: campo ridotto) o immagine | NF-40 |
| ECO-108 | Tris tra utenti | Dank Memer [DANK], NadekoBot (`.tictactoe`) [NADEKO] | ❌ manca | 9 bottoni | NF-40 |
| ECO-109 | Stesso gioco in due versioni: per divertimento o con scommessa | Dank Memer (`/game`, `/wager`) [DANK] | ❌ manca | Opzione `puntata` facoltativa su ogni gioco | NF-40 |
| ECO-110 | "Bomba": taglia il filo giusto, l'ultimo rimasto vince tutto | Lawliet (`bomb`) [LAWLIET] | ❌ manca | Bottoni colorati | NF-40 |
| ECO-111 | Gioco di carte a turni (stesso valore o colore) | Lawliet (`matchingcards`) [LAWLIET] | ❌ manca | Mano mostrata in privato | NF-40 |
| ECO-112 | Bingo tra membri | Lawliet (`bingo`) [LAWLIET] | ❌ manca | Cartella come immagine | NF-40 |
| ECO-113 | Impiccato | Lawliet (`hangman`) [LAWLIET], NadekoBot (`.hangman`, con categorie) [NADEKO] | ❌ manca | Parole in italiano | NF-40 |
| ECO-114 | Quiz a tempo con premio in monete | Lawliet (`quiz`, `animequiz`: 15 secondi) [LAWLIET], Red (`triviaset payout`) [RED] | ❌ manca | Domande in italiano; bottoni A–D | NF-40 |
| ECO-115 | Statistiche personali di vincite e perdite | Lawliet (`casinostats`) [LAWLIET], NadekoBot (`.betstats`, `.gamblestats`) [NADEKO] | ❌ manca | Conteggi per gioco | NF-40 |
| ECO-116 | Classifica delle vincite più grosse | NadekoBot (`.winlb`) [NADEKO] | ❌ manca | Tabella delle 10 migliori | NF-40 |
| ECO-117 | Rimborso di una piccola parte delle puntate perse | NadekoBot (`.rakeback`) [NADEKO] | ❌ manca | Percentuale accumulata da riscuotere | NF-40 |
| ECO-118 | Lotteria a estrazione periodica | Dank Memer (lotteria mondiale ogni ora) [DANK] | ❌ manca | Estrazione giornaliera per server | NF-40 |
| ECO-119 | Eventi del server: rapine di gruppo, riffe, partite amichevoli | Dank Memer (`/serverevents`) [DANK] | ❌ manca | Il premio viene dalla cassa del server | nuova |
| ECO-120 | Donare monete o oggetti al "fondo premi" del server | Dank Memer (`/serverevents donate`) [DANK] | 🟡 parziale: si dona solo alla tesoreria del clan | `/level cassa dona` | nuova |
| ECO-121 | Registro pubblico degli eventi, per controllarne la correttezza | Dank Memer (`/serverevents logs`) [DANK] | ❌ manca | Storico degli ultimi eventi | nuova |

## 5. Animali, pesca, progressione

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| ECO-122 | Animale virtuale da comprare | Dank Memer (`/pets buy`) [DANK], Tatsu (oltre 100) [TATSU], Mimu (`/votes shop`) [MIMU] | ❌ manca | `/level animale`; immagini proprie | NF-40 |
| ECO-123 | Cura dell'animale: fame, igiene, gioco, livello | Dank Memer (`/pets care`) [DANK], Mimu (`/feed`, `/play`) [MIMU], Tatsu [TATSU] | ❌ manca | Valori che calano col tempo, calcolati alla lettura | NF-40 |
| ECO-124 | Più animali, con posti da sbloccare | Dank Memer (fino a 3) [DANK] | ❌ manca | Tetto per utente | NF-40 |
| ECO-125 | "Pet sitter" a pagamento quando non hai tempo | Dank Memer (`/pets sitter`) [DANK] | ❌ manca | Costo giornaliero | NF-40 |
| ECO-126 | Due animali possono fare un cucciolo | Dank Memer [DANK] | ❌ manca | Probabilità giornaliera | NF-40 |
| ECO-127 | Lotte tra animali | Dank Memer [DANK] | ❌ manca | Motore dei duelli (ECO-104) | NF-40 |
| ECO-128 | Adottare animali abbandonati da altri | Dank Memer (`/search`) [DANK] | ❌ manca | Coda di adozione | NF-40 |
| ECO-129 | Incontro tra gli animali di due utenti | Mimu (`/playdate`, `/cozy`) [MIMU] | ❌ manca | Comando a due | NF-40 |
| ECO-130 | Attività con l'animale (riporto, nuoto, canto…) | Mimu (13 `/activity …`) [MIMU], Dank Memer (riporto, passeggiata) [DANK] | ❌ manca | 3–4 attività per iniziare | NF-40 |
| ECO-131 | L'animale dà un bonus ai guadagni | Mimu [MIMU] | ❌ manca | Percentuale per specie | NF-40 |
| ECO-132 | Pesca come mini-gioco con attrezzi, esche e luoghi | Dank Memer (`/fish catch`) [DANK], NadekoBot (`.fish`, `.fishspot`) [NADEKO] | ❌ manca | `/fun gioca pesca` | NF-40 |
| ECO-133 | Deposito dei pesci, da vendere o rinominare | Dank Memer (`/fish buckets`) [DANK], NadekoBot (`.fishinv`) [NADEKO] | ❌ manca | Parte dell'inventario | NF-40 |
| ECO-134 | Guida con tutte le specie trovate | Dank Memer (`/fish guide`) [DANK], NadekoBot (`.fishlist`) [NADEKO] | ❌ manca | Collezione con percentuale | NF-40 |
| ECO-135 | Abilità da sbloccare con le sfide | Dank Memer (`/fish skills`) [DANK] | ❌ manca | Albero semplice | NF-41 |
| ECO-136 | Pass stagionale con premi gratis e a pagamento | Dank Memer (`/fish season`) [DANK] | ❌ manca | Solo traccia gratuita all'inizio | NF-41 |
| ECO-137 | Negozio di attrezzi con moneta dedicata | Dank Memer (`/fish shop`) [DANK], NadekoBot (`.fishshop`, `.fishbuy`, `.fishuse`) [NADEKO] | ❌ manca | Categoria del negozio | NF-40 |
| ECO-138 | Classifica giornaliera di pesca | Dank Memer (`/fish leaderboard`) [DANK], NadekoBot (`.fishlb`) [NADEKO] | ❌ manca | Classifica con periodo giornaliero | NF-40 |
| ECO-139 | Acquario personale da mostrare | Dank Memer (`/fish tank`) [DANK] | ❌ manca | Immagine | NF-40 |
| ECO-140 | Pesca automatica mentre sei via | Dank Memer (`/fish idle`) [DANK] | ❌ manca | Calcolo alla riscossione | NF-40 |
| ECO-141 | Storico di tutto il pescato e venduto | Dank Memer (`/fish log`) [DANK] | ❌ manca | Parte di ECO-007 | NF-40 |
| ECO-142 | Personaggi che danno missioni e regali | Dank Memer (6 NPC) [DANK] | ❌ manca | Missioni a testo | NF-41 |
| ECO-143 | Registro delle missioni attive | NadekoBot (`.questlog`) [NADEKO] | ❌ manca | `/level missioni` | NF-41 |
| ECO-144 | Eventi casuali a tempo che cambiano le regole | Dank Memer [DANK] | ❌ manca | Evento scelto dall'owner o a caso | NF-41 |
| ECO-145 | Evento raro nel server, annunciato in un canale scelto | Dank Memer (pesce mitico) [DANK] | ❌ manca | Canale dal router (NF-01) | NF-41 |
| ECO-146 | Fattoria: coltivi e vendi il raccolto | Dank Memer [DANK] | ❌ manca | Tempi di crescita calcolati alla lettura | NF-40 |
| ECO-147 | Avventure a scelte, con una storia | Dank Memer (`/adventure`) [DANK] | ❌ manca | Storia a bottoni | NF-41 |
| ECO-148 | "Prestigio": ricominci da capo in cambio di bonus permanenti | Dank Memer (`/advancements prestige`, `omega`) [DANK] | ❌ manca | Azzeramento volontario con moltiplicatore | NF-41 |
| ECO-149 | Potenziamenti permanenti dell'account | Dank Memer (`/advancements upgrades`) [DANK] | ❌ manca | Acquisti una tantum | NF-41 |
| ECO-150 | Elenco dei premi di ogni livello | Dank Memer (`/advancements levels`) [DANK] | ❌ manca | Vedi LIV-048 | NF-41 |
| ECO-151 | Medaglie per i traguardi | Dank Memer [DANK], Tatsu [TATSU], MEE6 ("Achievements", gratis) [MEE6] | ❌ manca | Tabella dei traguardi | NF-41 |
| ECO-152 | Profilo: scegliere quali righe mostrare e in che ordine | Dank Memer (`/profile`) [DANK] | ❌ manca | Opzioni del profilo | NF-40 |
| ECO-153 | Matrimonio tra utenti, da "mantenere" con attività | Dank Memer (`/marriage view`) [DANK] | ❌ manca | Richiesta con bottone Accetta | NF-40 |
| ECO-154 | Lista amici: regali senza tassa | Dank Memer (`/friend add`) [DANK] | ❌ manca | Richiesta con conferma | NF-40 |
| ECO-155 | Bloccare un utente: niente richieste, regali o inviti da lui | Dank Memer [DANK] | ❌ manca | Lista personale controllata da ogni comando a due | nuova |
| ECO-156 | Avvisi del bot (sei stato derubato, hai perso un oggetto) | Dank Memer (`/notifications view`) [DANK] | ❌ manca | Casella personale | NF-40 |
| ECO-157 | Promemoria quando un comando è di nuovo disponibile | Dank Memer (`/settings`) [DANK] | ❌ manca | Usa lo scheduler dei promemoria | nuova |
| ECO-158 | Controllo anti-automazione nei comandi di guadagno | Dank Memer (captcha dentro Discord) [DANK] | ❌ manca | Controllo casuale con bottone | nuova |
| ECO-159 | Azzerare da soli i propri dati di gioco | Dank Memer (`/resetmydata`) [DANK] | ❌ manca | Parte di `/utility privacy cancella` | NF-04 |
| ECO-160 | Sospensione dal gioco con richiesta di revisione | Dank Memer (ban a tempo o fisso, un appello) [DANK] | 🟡 parziale: `/owner blacklist-user-add` blocca tutto il bot, senza appello | Blocco limitato all'economia, con bottone di appello | NF-30 |
| ECO-161 | Durata massima al giorno conteggiata in vocale, scelta dal server | Lawliet (`vctime`) [LAWLIET] | 🟡 parziale: tetto giornaliero fisso | Impostazione | NF-15 |

## Fonti

Lette il 4/10/2026.

- `[UNB]` UnbelievaBoat — https://unbelievaboat.com/commands (leggibile solo la categoria "Economy"; delle altre si vede solo il numero di comandi) · https://unbelievaboat.com/premium · https://faq.unbelievaboat.com/getting-started/configuring/ · https://faq.unbelievaboat.com/income-sources/overview · `/income-sources/role-income` · `/income-sources/chat-money` · `/income-sources/custom-income` · `/income-sources/rob` · `/income-sources/crime` · https://faq.unbelievaboat.com/games/overview · `/games/roulette` · `/games/chicken-fight` · `/games/animal-racing` · https://faq.unbelievaboat.com/role-income-slots/overview · https://faq.unbelievaboat.com/premium/features · https://top.gg/bot/292953664492929025
- `[DANK]` Dank Memer — https://dankmemer.lol/tutorial · https://dankmemer.lol/blogs/rewrite-changelog · https://dankmemer.lol/blogs/grinding-2 · https://dankmemer.lol/blogs/empowering-your-servers · https://top.gg/bot/270904126974590976
- `[DANK-T]` Dank Memer (terzi) — https://dank-memer.fandom.com/wiki/Dank_Memer
- `[MIMU]` Mimu — https://docs.mimu.bot/command-list.md · `/settings/getting-started/activity-+-pick-spawn.md` · `/currency-system/setting-up-a-server-shop.md` · `/global-currency/tickets/pets.md` · `/global-currency/stars/activity-classes.md`
- `[LAWLIET]` Lawliet — sorgente ufficiale https://github.com/Aninoss/lawliet-bot (`fishery_category_en_us.properties`, `fishery_settings_category_en_us.properties`, `casino_en_us.properties`)
- `[NADEKO]` NadekoBot — https://nadeko.bot/commands
- `[RED]` Red-DiscordBot — https://docs.discord.red/en/stable/cog_guides/economy.html · `/trivia.html` (letti dal sorgente https://github.com/Cog-Creators/Red-DiscordBot)
- `[TATSU]` Tatsu — https://tatsu.gg
- `[MEE6]` MEE6 — https://help.mee6.xyz/en/articles/710936-mee6-free-vs-premium-plans-comparison

Non letti su fonte ufficiale:
- **UnbelievaBoat**: i nomi dei comandi delle categorie Income (19),
  Games (12), Animals (4), Items (11) non sono leggibili sulla pagina
  dei comandi. Le voci in tabella vengono dalle pagine FAQ ufficiali.
- **Dank Memer**: la pagina `dankmemer.lol/commands` si carica solo con
  JavaScript. Le voci vengono dal tutorial e dal blog ufficiali; una
  sola (`postmemes`) da un wiki di terzi.
- **OwO Bot** (`owobot.com/commands`): pagina non leggibile, non usato.
- **Tatsu**: solo la pagina principale.

## Conteggio

161 righe: 145 ❌ e 16 🟡.
