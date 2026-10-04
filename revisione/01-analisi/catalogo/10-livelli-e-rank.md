# Catalogo — Livelli e rank

Come si guadagna XP, annunci di level-up, ruoli premio, moltiplicatori,
esclusioni, rank card, classifiche, gestione dell'XP da parte dello
staff, punti reputazione. 91 voci. Bot letti: Arcane, MEE6, Carl-bot,
ProBot, Lurkr, YAGPDB (reputazione), Tatsu, AmariBot.

Legenda: ❌ manca · 🟡 parziale. "Scheda": NF-xx = scheda di
`NUOVE_FUNZIONI.md`; M x.y = riga di `MODIFICHE_ESISTENTE.md`;
"nuova" = non c'è ancora in nessun piano.

iYokai oggi (per confronto): XP da messaggi (pausa di 60 secondi) e da
vocale (con anti-farm), valori fissi nel codice; `/rank [membro]` come
riquadro di testo; `/leaderboard` (XP o monete, mese o sempre);
`/level-roles add|remove|list` solo ad accumulo; level-up annunciato
sempre nel canale dove avviene; `/monthly-winners` (podio del mese).

## 1. Come si guadagna XP

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| LIV-001 | XP minimo e massimo per messaggio scelti dal server | Arcane (premium) [ARCANE], Carl-bot (da 15 a 100) [CARL] | ❌ manca | `/admin economia livelli xp`; valori con minimo e massimo nello schema unico (`core/config_schema.py`) | NF-15 |
| LIV-002 | Pausa tra due guadagni di XP scelta dal server | Arcane (in secondi) [ARCANE], Carl-bot ("level rate") [CARL] | 🟡 parziale: pausa fissa di 60 secondi | Opzione `pausa` (da 10 a 3600 secondi) | NF-15 |
| LIV-003 | Velocità generale dei livelli regolabile con un solo valore | MEE6 ("XP Rate") [MEE6], Arcane ("Multiplier" sulla formula) [ARCANE], Lurkr (moltiplicatore globale) [LURKR] | ❌ manca | Moltiplicatore del server (da 0,25 a 5) applicato a ogni guadagno | NF-15 |
| LIV-004 | Scelta della formula dei livelli: lineare, esponenziale, costante | Arcane [ARCANE] | ❌ manca | Tre formule in `core/leveling_logic.py`; il cambio ricalcola i livelli dall'XP totale | nuova |
| LIV-005 | Livello massimo raggiungibile | Arcane ("Max Level") [ARCANE] | ❌ manca | Opzione `livello-massimo`; oltre il tetto l'XP non sale | nuova |
| LIV-006 | XP "a parola": più XP per i messaggi più lunghi | Arcane (modo "Per Word", parole da 3 lettere in su) [ARCANE] | ❌ manca | Serve `message_content`; tetto di parole contate per messaggio | nuova |
| LIV-007 | Bonus "impegno": più XP per messaggi lunghi e con immagini | Arcane ("Effort Booster") [ARCANE] | ❌ manca | Piccolo bonus fisso se il messaggio ha un allegato o supera N caratteri | nuova |
| LIV-008 | XP per le reazioni messe | Arcane [ARCANE] | ❌ manca | Evento `on_raw_reaction_add`; pausa propria (Arcane: 5 minuti) | nuova |
| LIV-009 | XP per le reazioni ricevute sui propri messaggi | Arcane [ARCANE] | ❌ manca | Come LIV-008, accredito all'autore del messaggio; mai su se stessi | nuova |
| LIV-010 | XP vocale: valori e pausa scelti dal server | Arcane (premium; pausa di 3 minuti) [ARCANE], Carl-bot (acceso/spento) [CARL] | 🟡 parziale: XP vocale presente, valori fissi | Opzioni `xp-vocale` e interruttore, nello stesso comando di LIV-001 | NF-15 |
| LIV-011 | XP vocale solo se nel canale ci sono almeno N persone | Arcane ("Minimum Members") [ARCANE] | 🟡 parziale: l'anti-farm scarta chi è solo, soglia fissa | Rendere la soglia un'impostazione (da 1 a 10) | NF-15 |
| LIV-012 | Anti-AFK vocale che si può spegnere | Arcane [ARCANE] | 🟡 parziale: anti-farm sempre acceso | Interruttore `anti-farm` per server | NF-15 |
| LIV-013 | Livelli di testo e di vocale separati, con due classifiche | ProBot (`top text`, `top voice`) [PROBOT] | 🟡 parziale: l'XP di testo e vocale finisce in un solo totale | Due colonne di XP e scelta `tipo` in `/level leaderboard` | nuova |
| LIV-014 | XP nei thread: acceso o spento | Arcane [ARCANE], Lurkr [LURKR] | ❌ manca | Interruttore; il thread eredita le regole del canale padre | NF-15 |
| LIV-015 | XP nei post dei forum: acceso o spento | Arcane [ARCANE] | ❌ manca | Interruttore | NF-15 |
| LIV-016 | XP per i messaggi scritti nella chat dei canali vocali: acceso o spento | Arcane [ARCANE] | ❌ manca | Interruttore | NF-15 |
| LIV-017 | XP per l'uso dei comandi slash: acceso o spento | Arcane [ARCANE] | ❌ manca | Interruttore; default spento | nuova |
| LIV-018 | Messaggi che iniziano con il prefisso di altri bot non danno XP | Lurkr ("Ignored Bot Prefixes") [LURKR] | ❌ manca | Elenco di prefissi (max 10); serve `message_content` | nuova |
| LIV-019 | Bonus XP per chi vota il bot | Arcane (+10% per 12 ore; si spegne con il premium) [ARCANE] | ❌ manca | Solo se iYokai sarà su un elenco di bot; webhook del voto | nuova |

## 2. Esclusioni e moltiplicatori

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| LIV-020 | Canali senza XP (lista nera) | MEE6 [MEE6], ProBot [PROBOT], Arcane [ARCANE], Carl-bot [CARL] | ❌ manca | `/admin economia livelli escludi-canale`; elenco a pagine | NF-15 |
| LIV-021 | XP solo in alcuni canali (lista bianca) | Arcane ("XP Channels") [ARCANE] | ❌ manca | Modo `solo-questi` sullo stesso elenco | nuova |
| LIV-022 | Ruoli senza XP | MEE6 [MEE6], ProBot [PROBOT], Arcane [ARCANE], Carl-bot [CARL] | ❌ manca | `/admin economia livelli escludi-ruolo` | NF-15 |
| LIV-023 | Togliere un canale o un ruolo dall'elenco degli esclusi | Carl-bot ("unblacklist") [CARL] | ❌ manca | Azione `togli` dei due comandi sopra | NF-15 |
| LIV-024 | Moltiplicatore di XP per ruolo | Arcane (1 gratis) [ARCANE], Lurkr [LURKR], Maki [MAKI] | ❌ manca | `/admin economia livelli boost-ruolo`; valore da 0,1 a 5 | NF-15 |
| LIV-025 | Moltiplicatore di XP per canale | Arcane (1 gratis) [ARCANE], Lurkr [LURKR], Maki [MAKI] | ❌ manca | `/admin economia livelli boost-canale` | NF-15 |
| LIV-026 | Scelta: i moltiplicatori si sommano oppure vale solo il più alto | Arcane ("Stack Boosters") [ARCANE] | ❌ manca | Opzione `somma: sì/no` | nuova |
| LIV-027 | Elenco pubblico dei moltiplicatori attivi | Arcane (`/boosters`) [ARCANE] | ❌ manca | `/level boost` (sola lettura) | nuova |

## 3. Annuncio del level-up

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| LIV-028 | Annuncio spento | MEE6 [MEE6], Carl-bot [CARL], Arcane [ARCANE] | ❌ manca | `/admin economia livelli annuncio modo:spento` | NF-15 |
| LIV-029 | Annuncio in messaggio privato | MEE6 [MEE6], Carl-bot [CARL] | ❌ manca | Modo `dm`; `HTTPException` catturata se i DM sono chiusi | NF-15 |
| LIV-030 | Annuncio in un canale scelto | MEE6 [MEE6], Carl-bot [CARL], Arcane [ARCANE] | ❌ manca | Modo `canale`; canale dal router (NF-01) | NF-15 |
| LIV-031 | Testo dell'annuncio personalizzabile con segnaposto (utente, livello, XP) | MEE6 [MEE6], Arcane [ARCANE], AmariBot [AMARI] | ❌ manca | Testo ≤ 1800 con `{user} {level} {xp}`; renderer comune | NF-15 |
| LIV-032 | Annuncio dentro un embed | Arcane (con il sistema dei tag) [ARCANE] | ❌ manca | Opzione `embed:<nome>` (embed salvato) | NF-17 |
| LIV-033 | Immagine di level-up allegata all'annuncio | Arcane ("Include levelup image") [ARCANE] | ❌ manca | Variante piccola della rank card; Pillow fuori dal ciclo principale | NF-12 |
| LIV-034 | Parte di testo mostrata solo se il livello dà un ruolo premio, con nome o menzione del ruolo | Arcane (`{earned:…}`, `{name}`, `{mention}`) [ARCANE], AmariBot (`{role}`) [AMARI] | ❌ manca | Segnaposto `{ruolo_premio}` e blocco condizionale nel renderer | nuova |
| LIV-035 | Annuncio solo sopra un certo livello | Carl-bot ("announcement limit") [CARL] | ❌ manca | Opzione `da-livello` | nuova |
| LIV-036 | Annuncio solo ogni N livelli (5, 10, 15…) | Carl-bot ("announcement modulo") [CARL] | ❌ manca | Opzione `ogni` | nuova |
| LIV-037 | Annuncio solo per i livelli che danno un ruolo premio | Carl-bot [CARL] | ❌ manca | Opzione `solo-premi: sì/no` | nuova |
| LIV-038 | Prova dell'annuncio in un canale a scelta | Arcane [ARCANE] | ❌ manca | `/admin economia livelli annuncio prova`; pausa di qualche minuto | nuova |
| LIV-039 | Registro degli ultimi 25 level-up del server | Carl-bot ("level log") [CARL] | ❌ manca | `/level ultimi`; dati già nello storico eventi | nuova |

## 4. Ruoli premio

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| LIV-040 | Premi "togli i precedenti": resta solo il ruolo più alto | MEE6 [MEE6], Arcane ("Stack Rewards" spento) [ARCANE], Carl-bot [CARL], ProBot ("Remove with a higher level") [PROBOT] | 🟡 parziale: solo ad accumulo | Opzione `modo: accumula/sostituisci` | NF-15 |
| LIV-041 | Togliere il ruolo premio a chi perde XP e scende sotto il livello | MEE6 [MEE6] | ❌ manca | Controllo dei premi anche quando l'XP cala (LIV-064) | nuova |
| LIV-042 | Più ruoli premio sullo stesso livello | Arcane (1 gratis, 3 premium) [ARCANE] | ❌ manca: un solo ruolo per livello (vincolo unico su server e livello) | Vincolo unico su (server, livello, ruolo); tetto di 3 ruoli per livello | nuova |
| LIV-043 | Premi ricontrollati quando l'utente usa `/rank` o rientra nel server | Arcane [ARCANE] | ❌ manca | Chiamare la sincronizzazione dei premi in `/level rank` e in `on_member_join` | nuova |
| LIV-044 | Ruolo "primo in classifica", aggiornato a intervalli | Arcane (ogni 24 ore gratis, ogni ora premium) [ARCANE] | ❌ manca | Lavoro orario; un solo membro alla volta ha il ruolo | nuova |
| LIV-045 | Ruoli dati in base alla posizione in classifica | Tatsu ("automatic role assignment by score") [TATSU] | ❌ manca | Fasce (top 1, top 3, top 10) aggiornate dal lavoro di LIV-044 | nuova |
| LIV-046 | Ruolo premio che chiede insieme livello di testo e livello vocale | ProBot [PROBOT] | ❌ manca | Dipende da LIV-013; due soglie sulla stessa regola | nuova |
| LIV-047 | Avviso in DM quando si riceve un ruolo premio | ProBot ("DM Member") [PROBOT] | ❌ manca | Opzione sul premio; DM con `HTTPException` catturata | nuova |
| LIV-048 | Elenco pubblico dei ruoli premio | Arcane (`/rewards`) [ARCANE] | 🟡 parziale: `/level-roles list` è solo per gli admin | Rendere l'elenco visibile a tutti in `/level premi` | nuova |

## 5. Rank card

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| LIV-049 | Rank card come immagine (avatar, livello, barra, posizione) | MEE6 [MEE6], Arcane [ARCANE], Carl-bot [CARL], ProBot (`rank`) [PROBOT], Lurkr [LURKR], Tatsu [TATSU] | ❌ manca: `/rank` è un riquadro di testo | `/level rank`; `defer()` prima di disegnare | NF-12 |
| LIV-050 | Colore della barra dell'XP scelto dall'utente | Carl-bot [CARL], MEE6 (colori pronti o creatore) [MEE6] | ❌ manca | `/level profilo colore`; esadecimale controllato | NF-12 |
| LIV-051 | Colore di testo e bordi della card | Carl-bot ("text accent") [CARL] | ❌ manca | Seconda opzione colore | NF-12 |
| LIV-052 | Sfondo personale caricato dall'utente | Carl-bot (934×282) [CARL], MEE6 (premium) [MEE6], Arcane (800×200, premium) [ARCANE] | ❌ manca | Allegato; regole di `core/safe_image.py`; dato personale (NF-04) | NF-12 |
| LIV-053 | Sfondi pronti tra cui scegliere | MEE6 (premium) [MEE6] | ❌ manca | 5–10 sfondi nel repository | NF-12 |
| LIV-054 | Opacità del velo sopra lo sfondo | Carl-bot (0–100) [CARL] | ❌ manca | Opzione numerica | NF-12 |
| LIV-055 | Sfondo predefinito del server per tutte le card | Carl-bot ("server background") [CARL] | ❌ manca | `/admin economia livelli card-sfondo` | NF-12 |
| LIV-056 | Colore predefinito del server per tutte le card | Lurkr (esadecimale, media dell'icona o del banner del server) [LURKR] | ❌ manca | `/admin economia livelli card-colore`; "auto" calcola il colore dall'icona | NF-12 |
| LIV-057 | Segnalazione di una card con immagine non adatta | Arcane (segnalazione al supporto, blocco di chi abusa) [ARCANE] | ❌ manca | Bottone "Segnala" che usa il flusso di `/report`; lo staff può azzerare lo sfondo | nuova |

## 6. Classifiche

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| LIV-058 | Classifica settimanale | Arcane (beta) [ARCANE] | 🟡 parziale: solo mese e sempre | Terzo periodo con la stessa tecnica `period_key` | nuova |
| LIV-059 | Classifica per tempo in vocale | Arcane [ARCANE], ProBot (`top voice`) [PROBOT] | ❌ manca | Scelta `tipo: vocale`; i minuti si contano già per l'anti-farm | NF-25 |
| LIV-060 | Classifica per reazioni | Arcane [ARCANE] | ❌ manca | Dipende da LIV-008 | nuova |
| LIV-061 | Top 10 della settimana pubblicata da sola in un canale | Arcane ("Highlights", verso mezzanotte UTC) [ARCANE] | 🟡 parziale: c'è il podio del mese (`/monthly-winners`) | Stesso lavoro del mensile, con periodo settimanale e 10 righe | nuova |
| LIV-062 | Classifica su pagina web, con indirizzo breve scelto dal server | MEE6 (`/levels`, vanity URL premium) [MEE6], Arcane ("Vanity URL") [ARCANE] | ❌ manca | Pagina pubblica del pannello web; nome breve unico | NF-20 |
| LIV-063 | Classifica fino a 100 posizioni | Arcane (top 10 e top 100) [ARCANE] | 🟡 parziale: solo le prime 10 righe | Pagine con bottoni; 10 righe per pagina | nuova |

## 7. Gestione dell'XP da parte dello staff

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| LIV-064 | Aggiungere o togliere XP a un membro | Arcane (`/xp add`, `/xp remove`) [ARCANE], MEE6 (`/give-xp`, `/remove-xp`) [MEE6], Carl-bot (da 1 a 1000) [CARL], ProBot (`setxp`) [PROBOT] | ❌ manca | `/admin economia xp aggiungi/togli`; `Range` sull'importo; riga nel log | nuova |
| LIV-065 | Impostare il livello di un membro | Arcane (`/xp set level`) [ARCANE], Carl-bot (da 1 a 100) [CARL], ProBot (`setlevel`) [PROBOT] | ❌ manca | `/admin economia xp livello` | nuova |
| LIV-066 | Impostare l'XP dentro il livello corrente | Arcane (`/xp set xp`) [ARCANE] | ❌ manca | Opzione dello stesso comando | nuova |
| LIV-067 | Azzerare XP e livello di un membro | Arcane (`/xp reset member`) [ARCANE], Carl-bot [CARL], ProBot (`reset`) [PROBOT] | ❌ manca | `/admin economia xp azzera membro` con conferma | nuova |
| LIV-068 | Azzerare tutta la classifica del server | Arcane (`/xp reset server`) [ARCANE], ProBot (`reset` testo, voce o inviti) [PROBOT] | ❌ manca | `/admin economia xp azzera server`; conferma con il nome del server scritto a mano | nuova |
| LIV-069 | Copia di sicurezza automatica prima dell'azzeramento, con ripristino | Carl-bot ("reset all" e "restore") [CARL] | ❌ manca | Tabella di copia con scadenza (30 giorni) e comando `ripristina` | nuova |
| LIV-070 | Azzeramento automatico dei livelli di chi esce o viene bannato | Arcane ("Auto Reset") [ARCANE], Lurkr (uscita, ban o entrambi) [LURKR] | ❌ manca | Opzione `azzera-su: uscita/ban/entrambi`; va d'accordo con la conservazione dei dati (NF-04) | nuova |
| LIV-071 | Bloccare i comandi di XP a tutti tranne il proprietario del server | Arcane ("Disable /xp command", "Disable leaderboard reset") [ARCANE] | ❌ manca | Due interruttori; controllo `guild.owner_id` | nuova |
| LIV-072 | Importare i livelli da un altro bot | Carl-bot (da MEE6, stessa curva) [CARL], Lurkr (da MEE6, Amari, Polaris) [LURKR] | ❌ manca | Lettura della classifica pubblica dell'altro bot solo se le sue condizioni d'uso lo permettono; altrimenti import da file | nuova |
| LIV-073 | Vedere tutte le impostazioni dei livelli in un riepilogo | Carl-bot ("configuration") [CARL] | ❌ manca | `/admin economia livelli stato` | NF-15 |
| LIV-074 | Calcolatore: quanti messaggi mancano a un livello | Lurkr (pagina "Level Calculator") [LURKR] | ❌ manca | `/level calcola <livello>`; solo matematica | nuova |
| LIV-075 | Strumento di diagnosi "perché non prendo XP" | Arcane (pagina "Debugging") [ARCANE] | ❌ manca | `/admin economia livelli diagnosi <membro>`: canale escluso, ruolo escluso, pausa, modulo spento | nuova |

## 8. Reputazione e profilo

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| LIV-076 | Punto reputazione dato a un altro utente | YAGPDB (`/rep give`) [YAGPDB], ProBot (`rep`, una volta ogni 24 ore) [PROBOT] | ❌ manca | `/level rep dai`; pausa per utente; mai a se stessi né ai bot | nuova |
| LIV-077 | Togliere reputazione a un utente | YAGPDB (`/rep take`) [YAGPDB] | ❌ manca | `/level rep togli`; stesso limite | nuova |
| LIV-078 | Reputazione data scrivendo "grazie @utente" | YAGPDB [YAGPDB] | ❌ manca | Serve `message_content`; interruttore per server | nuova |
| LIV-079 | Vedere reputazione e posizione di un utente | YAGPDB (`/rep check`) [YAGPDB] | ❌ manca | `/level rep vedi` | nuova |
| LIV-080 | Classifica della reputazione | YAGPDB (`/rep top`) [YAGPDB] | ❌ manca | Scelta `tipo: reputazione` in `/level leaderboard` | nuova |
| LIV-081 | Registro di chi ha dato o tolto reputazione a un utente | YAGPDB (`/rep log`) [YAGPDB] | ❌ manca | Tabella dei movimenti; dato personale (NF-04) | nuova |
| LIV-082 | Lo staff imposta o cancella la reputazione di un utente | YAGPDB (`/rep set`, `/rep delete`) [YAGPDB] | ❌ manca | `/admin economia rep imposta/cancella` | nuova |
| LIV-083 | Nome dei punti reputazione scelto dal server | YAGPDB [YAGPDB] | ❌ manca | Impostazione di testo (max 20 caratteri) | nuova |
| LIV-084 | Pausa e massimo di punti per comando | YAGPDB [YAGPDB] | ❌ manca | Due impostazioni numeriche | nuova |
| LIV-085 | Ruoli che possono (o non possono) dare e ricevere reputazione | YAGPDB (quattro elenchi di ruoli) [YAGPDB] | ❌ manca | Ruolo richiesto ed escluso, per dare e per ricevere | nuova |
| LIV-086 | Ruoli premio per soglie di reputazione | YAGPDB (5 gratis, 25 premium) [YAGPDB] | ❌ manca | Stessa tabella dei ruoli premio, con `tipo: reputazione` | nuova |
| LIV-087 | Azzerare la reputazione di tutto il server | YAGPDB [YAGPDB] | ❌ manca | Comando con conferma | nuova |
| LIV-088 | Punti dati a mano dai moderatori, con classifica propria | ProBot (`points`) [PROBOT] | ❌ manca | Si può coprire con la reputazione (LIV-082) | nuova |
| LIV-089 | Profilo globale come immagine, uguale in tutti i server | ProBot (`profile`) [PROBOT], Tatsu ("Profile Cards") [TATSU] | ❌ manca | `/level profilo`; immagine con badge e sfondo | NF-40 |
| LIV-090 | Titolo o frase personale sul profilo | ProBot (`title`) [PROBOT] | ❌ manca | Testo ≤ 60 caratteri; passa dal filtro delle parole vietate | NF-40 |
| LIV-091 | XP e livello globali, validi in tutti i server | Tatsu ("level up across all of Discord") [TATSU] | ❌ manca | Somma degli XP per utente; solo dati positivi (NF-41) | NF-41 |

## Fonti

Lette il 4/10/2026.

- `[ARCANE]` Arcane — https://docs.arcane.bot/plugins/leveling · `/setup/xp-options` · `/setup/levelup-message` · `/setup/role-rewards` · `/setup/xp-boosters` · `/setup/highlights` · `/setup/xp-management` · `/setup/leaderboard` · `/setup/restrictions` · https://docs.arcane.bot/plugins/leveling/card · https://docs.arcane.bot/plugins/leveling/management · https://docs.arcane.bot/core/commands/list · https://docs.arcane.bot/premium
- `[MEE6]` MEE6 — https://wiki.mee6.xyz/en/plugins/levels · https://help.mee6.xyz/en/articles/710936-mee6-free-vs-premium-plans-comparison
- `[CARL]` Carl-bot — https://docs.carl.gg/levels.md
- `[PROBOT]` ProBot — https://docs.probot.io/docs/modules/level_system · https://probot.io/commands
- `[LURKR]` Lurkr — https://lurkr.gg · https://docs.lurkr.gg/guides/leveling-automation
- `[YAGPDB]` YAGPDB — https://help.yagpdb.xyz/docs/fun/reputation/ · https://help.yagpdb.xyz/docs/core/all-commands/ (letti dal sorgente ufficiale https://github.com/botlabs-gg/yagpdb-docs-v2)
- `[TATSU]` Tatsu — https://tatsu.gg (solo la pagina principale: il centro assistenza `support.tatsu.gg` mostra le categorie ma non gli articoli)
- `[AMARI]` AmariBot — https://docs.amaribot.com
- `[MAKI]` Maki — https://maki.gg/premium (dato già in `CONFRONTO_BOT.md`; la pagina dei comandi non è leggibile)

Non letti su fonte ufficiale: i comandi di **Tatsu** e di **Maki**
(pagine che si caricano solo con JavaScript) e i moduli di **Dyno**.

## Conteggio

91 righe: 81 ❌ e 10 🟡.
