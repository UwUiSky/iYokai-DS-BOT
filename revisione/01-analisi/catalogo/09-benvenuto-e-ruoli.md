# Catalogo — Benvenuto e ruoli

Messaggi di benvenuto, addio e ban; ruoli automatici; ruoli ridati a chi
rientra; ruoli a tempo; menu dei ruoli (reazioni, bottoni, tendina);
comandi per gestire i ruoli. 113 voci. Bot letti: Carl-bot, YAGPDB,
Lawliet, ProBot, Arcane, MEE6, Mimu, Red-DiscordBot, Sapphire.

Legenda: ❌ manca · 🟡 parziale. "Scheda": NF-xx = scheda di
`NUOVE_FUNZIONI.md`; M x.y = riga di `MODIFICHE_ESISTENTE.md`;
"nuova" = non c'è ancora in nessun piano.

iYokai oggi (per confronto): `/greetings welcome-setup|goodbye-setup|boost-setup|preview`
(solo testo, segnaposto `{user} {username} {server} {membercount}`, DM
facoltativo con lo stesso testo); `/rolemenu create|add-option|remove-option|delete`
(reazioni, bottoni grigi, tendina; `toggle`; `max_selectable` solo sulla
tendina); `/mute-role`. Nessun comando per dare o togliere ruoli.

## 1. Benvenuto, addio, ban

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| RUO-001 | Benvenuto dentro un embed (titolo, colore, immagine) invece che testo semplice | Arcane [ARCANE], Lawliet [LAWLIET], Mimu (embed "greet") [MIMU] | ❌ manca | `/admin benvenuto` con opzione `embed:<nome>` che usa un embed salvato; limiti embed controllati al salvataggio | NF-17 |
| RUO-002 | Immagine di benvenuto generata con avatar e nome del nuovo membro | ProBot [PROBOT], Arcane [ARCANE], Lawliet ("Generated Banners") [LAWLIET] | ❌ manca | `/admin benvenuto immagine`; Pillow fuori dal ciclo principale; file sotto 10 MiB | NF-11 |
| RUO-003 | Sfondo caricabile per l'immagine di benvenuto | ProBot (sotto 3 MB, jpg/png) [PROBOT], Arcane (premium, 1200×500) [ARCANE], Lawliet [LAWLIET] | ❌ manca | Allegato nel comando; regole di `core/safe_image.py` (16 megapixel, 2048 px) | NF-11 |
| RUO-004 | Opacità dello sfondo regolabile | Arcane [ARCANE] | ❌ manca | Opzione numerica 0–100 nello stesso comando | NF-11 |
| RUO-005 | Sfondo trasparente con larghezza e altezza a scelta | ProBot [PROBOT] | ❌ manca | Due opzioni con minimo e massimo; tetto 2048 px | NF-11 |
| RUO-006 | Avatar tondo o quadrato, con posizione e misura a scelta | ProBot [PROBOT] | ❌ manca | Nei modelli pronti: scelta "tondo/quadrato"; coordinate libere solo nel pannello web | NF-11 |
| RUO-007 | Nome utente sull'immagine con posizione, misura, colore e allineamento | ProBot [PROBOT] | ❌ manca | Colore e allineamento via comando; coordinate nel pannello web | NF-11 |
| RUO-008 | Testo libero sull'immagine con posizione, misura e colore | ProBot [PROBOT] | ❌ manca | Opzione `testo` (max 100 caratteri) con gli stessi segnaposto del messaggio | NF-11 |
| RUO-009 | Titolo del banner personalizzabile | Lawliet ("Banner Title") [LAWLIET] | ❌ manca | Opzione `titolo` (max 50 caratteri) | NF-11 |
| RUO-010 | Ordine tra immagine e testo: insieme, immagine prima, solo immagine | ProBot [PROBOT] | ❌ manca | Scelta a 3 valori nel comando immagine | NF-11 |
| RUO-011 | Ripristino dello sfondo predefinito del banner | Lawliet [LAWLIET] | ❌ manca | Opzione `sfondo: predefinito` | NF-11 |
| RUO-012 | Immagini proprie allegate al benvenuto, una scelta a caso ogni volta | Lawliet (tipo allegato "Images") [LAWLIET] | ❌ manca | Elenco di massimo 10 immagini salvate per server; scelta casuale all'invio | nuova |
| RUO-013 | Messaggio in DM all'ingresso con testo diverso da quello del canale | Carl-bot (`dmjoin`) [CARL], YAGPDB [YAGPDB], Lawliet [LAWLIET], ProBot [PROBOT] | 🟡 parziale: il DM manda lo stesso testo del canale | Secondo testo `messaggio-dm` nella stessa tabella; DM sospesi durante un raid (M 10.16) | nuova |
| RUO-014 | DM di benvenuto anche con embed e immagini | Lawliet [LAWLIET] | ❌ manca | Stesse opzioni di RUO-001 e RUO-012 sul DM | nuova |
| RUO-015 | Addio con embed e immagine allegata | Lawliet [LAWLIET], Arcane [ARCANE], Mimu (embed "leave") [MIMU] | ❌ manca | Come RUO-001, sul messaggio di addio | NF-17 |
| RUO-016 | Messaggio pubblico quando un membro viene bannato | Carl-bot (`banmsg`) [CARL] | ❌ manca | Terzo tipo in `/admin benvenuto`; evento `on_member_ban`; canale dal router (NF-01) | nuova |
| RUO-017 | Testo scelto a caso tra più varianti | Carl-bot (`{random: a ~ b}`) [CARL] | ❌ manca | Segnaposto `{casuale: a ~ b}` in `core/template_renderer.py`; lunghezza controllata sul caso più lungo | nuova |
| RUO-018 | Segnaposto "sei il membro numero 1.234º" (ordinale) | Carl-bot (`{ord:}`) [CARL] | 🟡 parziale: c'è `{membercount}` senza ordinale | Segnaposto `{posizione}` nel renderer | nuova |
| RUO-019 | Segnaposto con l'ID dell'utente | Carl-bot [CARL], Arcane [ARCANE] | ❌ manca | `{user_id}` nel renderer | nuova |
| RUO-020 | Segnaposto "nome visualizzato" distinto dal nome utente | Lawliet (`%Display_Name`) [LAWLIET] | ❌ manca | `{display_name}` nel renderer | nuova |
| RUO-021 | Segnaposto con ID del server | Arcane (`{guild.id}`) [ARCANE] | ❌ manca | `{server_id}` nel renderer | nuova |
| RUO-022 | Calcoli dentro il messaggio | Carl-bot (`{math:}`) [CARL] | ❌ manca | Solo somma e sottrazione su numeri interi; mai `eval` | nuova |
| RUO-023 | Il bot mette da solo una o più reazioni sul messaggio di benvenuto | Arcane [ARCANE] | ❌ manca | Opzione `reazioni` (max 5 emoji); una chiamata per reazione: pausa tra le richieste | nuova |
| RUO-024 | Il bot mette una reazione sul primo messaggio scritto dal nuovo membro | Arcane [ARCANE] | ❌ manca | Segno "primo messaggio" per membro, in memoria breve; basta l'evento del messaggio, non serve leggerne il testo | nuova |
| RUO-025 | Reazione di benvenuto scelta a caso da un elenco | Arcane [ARCANE] | ❌ manca | Variante di RUO-023: `modo: tutte/una a caso` | nuova |
| RUO-026 | Benvenuto con logica: condizioni, ruoli dati, dati salvati (script) | YAGPDB (modelli dei comandi personalizzati nei messaggi di ingresso) [YAGPDB] | ❌ manca | Solo condizioni semplici nel renderer (se ha ruolo, se account nuovo); niente linguaggio di script | nuova |
| RUO-027 | Avviso in un canale quando cambia l'argomento (topic) di un canale | YAGPDB ("Topic change message") [YAGPDB] | ❌ manca | Nuovo tipo di uscita nel router (NF-01); evento `on_guild_channel_update` | nuova |

## 2. Ruoli automatici, ruoli ridati, ruoli a tempo

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| RUO-028 | Uno o più ruoli dati a chi entra | Carl-bot (`autorole add`) [CARL], Arcane (1 gratis, 10 premium) [ARCANE], Lawliet [LAWLIET], YAGPDB (un solo ruolo) [YAGPDB], Sapphire [SAPPHIRE] | ❌ manca | `/admin ruoli auto aggiungi`; `check_role_assignable`; niente ruoli ai bot | NF-07 |
| RUO-029 | Togliere un ruolo dall'elenco dei ruoli automatici | Carl-bot (`autorole remove`) [CARL] | ❌ manca | `/admin ruoli auto rimuovi` | NF-07 |
| RUO-030 | Vedere i ruoli automatici attivi e se il "ridare i ruoli" è acceso | Carl-bot (`autorole`) [CARL] | ❌ manca | `/admin ruoli auto elenco` | NF-07 |
| RUO-031 | Ruolo dato solo dopo N minuti di permanenza nel server | YAGPDB [YAGPDB], Carl-bot (`timedrole add`) [CARL] | ❌ manca | Opzione `ritardo` su ogni ruolo automatico; lavoro nello scheduler, che sopravvive al riavvio | NF-07 |
| RUO-032 | Elenco dei ruoli dati con ritardo | Carl-bot (`timedrole`) [CARL] | ❌ manca | Stesso elenco di RUO-030, con la colonna "ritardo" | NF-07 |
| RUO-033 | Togliere un ruolo a ritardo annulla anche le assegnazioni in attesa | Carl-bot (`timedrole remove`) [CARL] | ❌ manca | Alla rimozione: cancellare i lavori pendenti nello scheduler | NF-07 |
| RUO-034 | Ruolo automatico solo a chi ha già uno di certi ruoli | YAGPDB [YAGPDB] | ❌ manca | Colonna "ruoli richiesti" sulla regola | nuova |
| RUO-035 | Ruolo automatico saltato per chi ha certi ruoli | YAGPDB [YAGPDB] | ❌ manca | Colonna "ruoli esclusi" sulla regola | nuova |
| RUO-036 | Scelta: il ruolo automatico viene ridato se qualcuno lo toglie, oppure solo all'ingresso | YAGPDB [YAGPDB] | ❌ manca | Opzione `solo-ingresso: sì/no`; se "no", ascolto di `on_member_update` | nuova |
| RUO-037 | Ruolo automatico solo dopo che il membro ha accettato le regole di Discord (Membership Screening) | YAGPDB [YAGPDB] | ❌ manca | Aspettare `member.pending == False` (`on_member_update`); va d'accordo con Verify | nuova |
| RUO-038 | Dare i ruoli automatici a tutti i membri già presenti (scansione) | YAGPDB (premium) [YAGPDB], Lawliet (Pro, "Sync All Auto Roles") [LAWLIET] | ❌ manca | `/admin ruoli auto sincronizza`; lavoro lungo: `defer()`, pause tra le richieste, una sola scansione alla volta | nuova |
| RUO-039 | Ruoli ridati a chi esce e rientra | Carl-bot (entro 30 giorni) [CARL], Lawliet ("Sticky Roles") [LAWLIET] | ❌ manca | `/admin ruoli ricorda`; ruoli salvati all'uscita; dato personale nel registro (NF-04) | NF-07 |
| RUO-040 | Scegliere quali ruoli sono "ricordati" (elenco di ruoli ammessi) | Lawliet [LAWLIET] | ❌ manca | Elenco di ruoli ammessi nella stessa tabella | NF-07 |
| RUO-041 | Elenco di ruoli da non ridare mai al rientro | Carl-bot (`autorole blacklist`, `unblacklist`) [CARL] | ❌ manca | Elenco di ruoli esclusi; il ruolo di mute resta sempre ridato | NF-07 |
| RUO-042 | Ruolo dato a un membro per un tempo, poi tolto da solo | Carl-bot (`temprole add`) [CARL] | ❌ manca | `/admin ruoli temporaneo`; scadenza nello scheduler; motivo ≤ 512 | nuova |
| RUO-043 | Dare e togliere più ruoli insieme per un tempo | Carl-bot (`temprole custom +a -b`) [CARL] | ❌ manca | Variante di RUO-042 con più ruoli; alla scadenza si torna allo stato di prima | nuova |
| RUO-044 | Ruolo dato a chi è in un canale vocale e tolto quando esce | YAGPDB ("Voice Roles": 1 gratis, 10 premium) [YAGPDB] | ❌ manca | `/admin ruoli vocale`; evento `on_voice_state_update`; pulizia all'avvio | nuova |
| RUO-045 | Ruolo personale che il membro gestisce da solo (nome e colore) | Lawliet (`customroleadd`, `customrolemanage`) [LAWLIET] | ❌ manca | `/admin ruoli personale` (lo staff lo concede), `/utility ruolo-mio`; tetto 250 ruoli per server | nuova |
| RUO-046 | Colore del nome scelto dal membro da una tavolozza del server | ProBot (`color`, `colors`) [PROBOT] | ❌ manca | Menu "unique" di ruoli colore (RUO-054) con comando rapido `/utility colore` | nuova |

## 3. Menu dei ruoli (reazioni, bottoni, tendina)

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| RUO-047 | Creazione guidata a passi (il bot chiede canale, testo, emoji e ruoli) | Carl-bot (`rr make`) [CARL], YAGPDB (`/rolemenu create`) [YAGPDB], Lawliet [LAWLIET] | 🟡 parziale: `create` e poi `add-option` una alla volta | Wizard con bottoni e moduli; `defer()`; 5 campi per modulo | nuova |
| RUO-048 | Menu completo in un solo comando | Carl-bot (`rr aio`) [CARL] | ❌ manca | Opzione testo "emoji ruolo; emoji ruolo" con `max_length` | nuova |
| RUO-049 | Aggiungere più coppie emoji-ruolo in un comando | Carl-bot (`rr addmany`) [CARL] | ❌ manca | Come RUO-048, su un menu esistente | nuova |
| RUO-050 | Elenco dei menu del server con ID, canale e opzioni | Carl-bot (`rr list`) [CARL], YAGPDB (`/rolemenu listgroups`) [YAGPDB], Lawliet [LAWLIET] | ❌ manca | `/admin ruoli menu elenco`, a pagine | nuova |
| RUO-051 | Modificare titolo e descrizione di un menu già pubblicato | Carl-bot (`rr edit`) [CARL], Lawliet [LAWLIET] | ❌ manca | `/admin ruoli menu modifica`; titolo 256, descrizione 2000 (M 10.7) | nuova |
| RUO-052 | Cambiare il colore del messaggio del menu | Carl-bot (`rr color`) [CARL] | ❌ manca | Opzione `colore` in esadecimale | nuova |
| RUO-053 | Immagine dentro il messaggio del menu | Lawliet ("Included Image") [LAWLIET] | ❌ manca | Allegato o indirizzo; regole di `core/safe_image.py` | nuova |
| RUO-054 | Modalità "unique": un solo ruolo alla volta dal menu | Carl-bot [CARL], YAGPDB (gruppo "Single") [YAGPDB], Lawliet [LAWLIET] | 🟡 parziale: solo `max_selectable=1` sulla tendina | Modalità per menu, valida per reazioni e bottoni | NF-14 |
| RUO-055 | Modalità "verify": il ruolo si prende e non si toglie | Carl-bot [CARL], ProBot (modo "Give") [PROBOT], Lawliet (rimozione spenta) [LAWLIET] | 🟡 parziale: `toggle=False` esiste ma è ignorato | Rispettare `toggle=False` (M 10.7), poi la modalità | NF-14 |
| RUO-056 | Modalità "drop": il menu toglie soltanto | Carl-bot [CARL], ProBot (modo "Take") [PROBOT] | ❌ manca | Modalità per menu | NF-14 |
| RUO-057 | Modalità "reversed": reagire toglie, togliere la reazione dà | Carl-bot [CARL], MEE6 ("Reverse mode") [MEE6] | ❌ manca | Modalità per menu | NF-14 |
| RUO-058 | Modalità "binding": una scelta sola, per sempre | Carl-bot [CARL] | ❌ manca | Modalità per menu; scelta salvata nel database | NF-14 |
| RUO-059 | Modalità "lock": menu congelato, nessuno prende ruoli | Carl-bot [CARL] | ❌ manca | Interruttore per menu | NF-14 |
| RUO-060 | Modalità "temp": il ruolo preso dal menu scade dopo un tempo | Carl-bot (premium) [CARL] | ❌ manca | Scadenza nello scheduler, come RUO-042 | NF-14 |
| RUO-061 | Tornare alla modalità normale | Carl-bot (`rr normal`) [CARL] | ❌ manca | Valore "normale" della scelta modalità | NF-14 |
| RUO-062 | Numero massimo di ruoli che un membro può prendere dal menu | Carl-bot (`rr limit`) [CARL], YAGPDB (gruppo "Multiple") [YAGPDB], ProBot [PROBOT] | 🟡 parziale: solo sulla tendina | Estendere `max_selectable` a reazioni e bottoni | NF-14 |
| RUO-063 | Numero minimo di ruoli: almeno uno resta sempre | YAGPDB ("Require 1 role in group", minimo del gruppo) [YAGPDB] | ❌ manca | Opzione `min` sul menu; rifiuto con messaggio privato | nuova |
| RUO-064 | Togliere da solo il ruolo precedente quando se ne sceglie un altro | YAGPDB (opzione del gruppo) [YAGPDB] | ❌ manca | Comportamento della modalità "unique" | NF-14 |
| RUO-065 | Tetto di membri per un ruolo del menu (posti limitati) | Carl-bot (`rr maxroles`) [CARL] | ❌ manca | Colonna `max_membri` sull'opzione; conteggio al clic | NF-14 |
| RUO-066 | Solo chi ha certi ruoli può usare il menu | Carl-bot (`rr whitelist`) [CARL], YAGPDB ("Require roles") [YAGPDB], Lawliet ("Role Requirements") [LAWLIET] | ❌ manca | Elenco "ruoli ammessi" per menu | NF-14 |
| RUO-067 | Chi ha certi ruoli non può usare il menu | Carl-bot (`rr blacklist`) [CARL], YAGPDB ("Ignore roles") [YAGPDB] | ❌ manca | Elenco "ruoli esclusi" per menu | NF-14 |
| RUO-068 | Togliere o svuotare le liste di ruoli ammessi ed esclusi | Carl-bot (`rr unwl`, `unblacklist`, `clearwl`, `clearbl`) [CARL] | ❌ manca | Sotto-comandi `ammessi`/`esclusi` con azione aggiungi, togli, svuota | NF-14 |
| RUO-069 | Più messaggi collegati: un solo ruolo tra tutti i menu del gruppo | Carl-bot (`rr link`, `rr unlink`, `rr links`) [CARL], YAGPDB (gruppi di ruoli su più menu) [YAGPDB] | ❌ manca | Tabella "gruppo di menu"; serve per superare 20 reazioni o 25 bottoni | nuova |
| RUO-070 | Menu che si cancella da solo dopo un tempo | Carl-bot (`rr selfdestruct`) [CARL] | ❌ manca | Opzione `scade-tra`; lavoro nello scheduler | nuova |
| RUO-071 | Canale per i ruoli creato dal bot con i permessi giusti | Carl-bot (`rr channel`) [CARL] | ❌ manca | Passo del wizard (M 10.14); 50 canali per categoria, 500 per server | nuova |
| RUO-072 | Agganciare il menu a un messaggio già scritto da qualcuno | Carl-bot (`rr add <id messaggio>`) [CARL], YAGPDB (`-m`) [YAGPDB] | ❌ manca | Solo per le reazioni (bottoni e tendina vivono solo su messaggi del bot) | nuova |
| RUO-073 | Spostare un menu su un altro messaggio | Carl-bot (`rr move`) [CARL] | ❌ manca | Aggiornare `message_id` e rimettere le reazioni | nuova |
| RUO-074 | Rimettere le reazioni del bot se qualcuno le ha tolte | Carl-bot (`rr fix`) [CARL], YAGPDB (`/rolemenu resetreactions`) [YAGPDB] | ❌ manca | `/admin ruoli menu ripara`; una richiesta per reazione, con pause | nuova |
| RUO-075 | Usare emoji di server dove il bot non c'è | Carl-bot (`rr fixforeign`) [CARL] | ❌ manca | L'admin mette la reazione, il bot la riconosce dall'evento | nuova |
| RUO-076 | Cambiare l'emoji di un'opzione senza rifare il menu | YAGPDB (`/rolemenu editoption`) [YAGPDB], Lawliet ("Edit Slot") [LAWLIET] | ❌ manca | `/admin ruoli menu opzione modifica` | nuova |
| RUO-077 | Scegliere la posizione di un'opzione nel menu | Lawliet ("Adjust Position") [LAWLIET] | ❌ manca | Colonna `ordine` sull'opzione | nuova |
| RUO-078 | Aggiornare il menu quando si aggiungono ruoli al gruppo | YAGPDB (`/rolemenu update`, `/rolemenu complete`) [YAGPDB] | 🟡 parziale: `add-option` ripubblica il menu, ma può dire "fatto" anche se fallisce | Sistemare con M 10.7 | M 10.7 |
| RUO-079 | Staccare il menu dal messaggio senza cancellare il messaggio | YAGPDB (`/rolemenu remove`) [YAGPDB] | 🟡 parziale: `delete` cancella il menu | Opzione `tieni-messaggio` su `delete` | nuova |
| RUO-080 | Cancellare in un colpo tutti i menu di un messaggio o del server | Carl-bot (`rr purge`) [CARL] | ❌ manca | `/admin ruoli menu svuota` con conferma | nuova |
| RUO-081 | Conferma in privato dei ruoli dati o tolti, che si può spegnere | YAGPDB (`-nodm`) [YAGPDB], ProBot ("Notify"/"Silent") [PROBOT] | 🟡 parziale: risposta privata solo per bottoni e tendina, non per le reazioni; non si spegne | Opzione `avvisa: sì/no` per menu | nuova |
| RUO-082 | Testo della conferma personalizzabile, con menzione del ruolo | ProBot (segnaposto `{0}`) [PROBOT] | ❌ manca | Campo `risposta` (max 200 caratteri) con `{ruolo}` | nuova |
| RUO-083 | Più ruoli dati da una sola opzione | ProBot (premium) [PROBOT], Lawliet (slot con più ruoli ed etichetta) [LAWLIET] | ❌ manca | Tabella opzione→ruoli; ogni ruolo passa da `check_role_assignable` | nuova |
| RUO-084 | Numero di membri di ogni ruolo mostrato nell'etichetta | Lawliet ("Show role counters") [LAWLIET] | ❌ manca | Aggiornamento del messaggio al massimo ogni pochi minuti | nuova |
| RUO-085 | Bottoni con colore a scelta (blu, grigio, verde, rosso) | MEE6 [MEE6], ProBot [PROBOT] | 🟡 parziale: bottoni sempre grigi | Opzione `colore` su `add-option` | nuova |
| RUO-086 | Tendina con testo-guida e descrizione sotto ogni opzione | MEE6 [MEE6], ProBot [PROBOT] | 🟡 parziale: testo-guida fisso in inglese, nessuna descrizione | Campi `segnaposto` (150) e `descrizione` (100) | nuova |
| RUO-087 | Voce "togli tutti i ruoli" nella tendina | Lawliet (`<Reset All Roles>`) [LAWLIET] | ❌ manca | Opzione fissa in fondo alla tendina (conta nelle 25) | nuova |
| RUO-088 | Cambiare tipo di un menu esistente (reazioni, bottoni, tendina) | Lawliet ("Adjust Component Type") [LAWLIET] | ❌ manca | Ripubblicare il messaggio con il nuovo tipo, tenendo le opzioni | nuova |
| RUO-089 | Modelli pronti di menu ("Verifica", "Notifiche") | MEE6 [MEE6] | ❌ manca | 3–4 modelli nel wizard | nuova |
| RUO-090 | Ruoli a scelta con un comando: `/role <nome>` dà o toglie un ruolo ammesso | Carl-bot (`rank`) [CARL], YAGPDB (`/role`) [YAGPDB], Red (`selfrole`) [RED] | ❌ manca | `/utility ruolo`; autocompletamento limitato a 25 ruoli ammessi | nuova |
| RUO-091 | Elenco dei ruoli che ci si può dare da soli | Carl-bot (`ranks`) [CARL], Red (`selfrole list`) [RED] | ❌ manca | `/utility ruolo` senza argomenti mostra l'elenco | nuova |
| RUO-092 | Lo staff sceglie quali ruoli sono auto-assegnabili | Carl-bot (`rank addrank`, `removerank`) [CARL], Red (`selfroleset add`, `remove`, `clear`) [RED] | ❌ manca | `/admin ruoli scelta aggiungi/rimuovi/svuota` | nuova |
| RUO-093 | Prendere e lasciare più ruoli a scelta in un comando | Carl-bot (`rank custom +a -b`) [CARL] | ❌ manca | Opzioni `aggiungi` e `togli` nello stesso comando | nuova |

## 4. Gestione dei ruoli da parte dello staff

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| RUO-094 | Dare o togliere un ruolo a un membro con un comando | Carl-bot (`role add`, `role remove`, `role`) [CARL], YAGPDB (`/giverole`, `/removerole`) [YAGPDB], ProBot (`role`) [PROBOT], Red (`addrole`, `removerole`) [RED], Arcane (`/role`) [ARCANE] | ❌ manca | `/mod ruolo dai/togli`; controllo della gerarchia; motivo ≤ 512; riga nel log | nuova |
| RUO-095 | Dare e togliere più ruoli a un membro in un comando | Carl-bot (`role custom +a -b`) [CARL] | ❌ manca | Opzioni multiple nello stesso comando | nuova |
| RUO-096 | Togliere tutti i ruoli a un membro | Carl-bot (`role removeall`) [CARL] | ❌ manca | `/mod ruolo azzera` con conferma; ruoli salvati per poterli ridare | nuova |
| RUO-097 | Dare un ruolo a tutti i membri | Carl-bot (`role all`) [CARL], Lawliet (`assignroles`) [LAWLIET], YAGPDB ("Bulk Role", premium) [YAGPDB] | ❌ manca | `/admin ruoli massa`; lavoro lungo con pause; una sola operazione alla volta per server | nuova |
| RUO-098 | Dare un ruolo solo agli umani | Carl-bot (`role humans`) [CARL], YAGPDB [YAGPDB] | ❌ manca | Filtro `chi: umani` di RUO-097 | nuova |
| RUO-099 | Dare un ruolo solo ai bot | YAGPDB [YAGPDB] | ❌ manca | Filtro `chi: bot` | nuova |
| RUO-100 | Dare un ruolo a chi ha già un certo ruolo | Carl-bot (`role in`) [CARL], YAGPDB ("Has specific roles", tutti o almeno uno) [YAGPDB] | ❌ manca | Filtro `con-ruolo` | nuova |
| RUO-101 | Dare un ruolo a chi non ha certi ruoli | YAGPDB ("Missing specific roles") [YAGPDB] | ❌ manca | Filtro `senza-ruolo` | nuova |
| RUO-102 | Dare un ruolo a chi è entrato prima o dopo una data | YAGPDB [YAGPDB] | ❌ manca | Filtri `entrato-prima`/`entrato-dopo` | nuova |
| RUO-103 | Togliere un ruolo in massa: a tutti, agli umani, ai bot, a chi ha un ruolo | Carl-bot (`role rall`, `rhumans`, `rbots`, `rin`) [CARL], Lawliet (`revokeroles`) [LAWLIET], YAGPDB [YAGPDB] | ❌ manca | Azione `togli` di RUO-097 con gli stessi filtri | nuova |
| RUO-104 | Fermare un'operazione di massa in corso | Carl-bot (`role bulk-cancel`) [CARL], YAGPDB [YAGPDB] | ❌ manca | `/admin ruoli massa annulla`; segnale letto a ogni giro | nuova |
| RUO-105 | Avviso in un canale a fine operazione di massa (o in caso di errore) | YAGPDB [YAGPDB] | ❌ manca | Messaggio nel canale scelto, con il conto di riusciti e falliti | nuova |
| RUO-106 | Stima del tempo di un'operazione di massa | Carl-bot [CARL] | ❌ manca | Nel messaggio di avvio: membri × pausa | nuova |
| RUO-107 | Creare un ruolo da comando (nome, colore, menzionabile, separato) | Carl-bot (`role create`) [CARL] | ❌ manca | `/admin ruoli crea`; tetto 250 ruoli | nuova |
| RUO-108 | Cambiare il colore di un ruolo | Carl-bot (`role color`) [CARL], ProBot (`setcolor`) [PROBOT], Red (`editrole color`) [RED] | ❌ manca | `/admin ruoli colore` | nuova |
| RUO-109 | Rinominare un ruolo | Red (`editrole name`) [RED] | ❌ manca | `/admin ruoli rinomina`; nome ≤ 100 | nuova |
| RUO-110 | Scheda di un ruolo: membri, colore, data di creazione | Carl-bot (`role info`) [CARL] | ❌ manca | `/utility ruolo-info` | nuova |
| RUO-111 | Elenco di tutti i ruoli con numero di membri | Carl-bot (`role allroles`) [CARL], ProBot (`roles`) [PROBOT] | ❌ manca | `/utility ruoli`, a pagine | nuova |
| RUO-112 | Elenco dei ruoli con ID, colore e chi può menzionare @everyone | YAGPDB (`/listroles`) [YAGPDB] | 🟡 parziale: `/permission-heatmap` mostra i permessi critici | Aggiungere ID e colore all'elenco di RUO-111 | nuova |
| RUO-113 | Diagnosi: perché il bot non riesce a dare un ruolo | Carl-bot (`role diagnose`) [CARL], YAGPDB (`/roledbg`) [YAGPDB] | ❌ manca | `/admin ruoli diagnosi <ruolo>`: gerarchia, permesso "Gestire ruoli", ruolo gestito | nuova |

## Fonti

Lette il 4/10/2026.

- `[CARL]` Carl-bot — https://docs.carl.gg/roles.md · https://docs.carl.gg/greetings.md · https://docs.carl.gg/_sidebar.md
- `[YAGPDB]` YAGPDB — https://help.yagpdb.xyz/docs/roles/autorole/ · https://help.yagpdb.xyz/docs/roles/self-assignable-roles/ · https://help.yagpdb.xyz/docs/roles/voice-roles/ · https://help.yagpdb.xyz/docs/roles/bulk-role/ · https://help.yagpdb.xyz/docs/notifications/general/ · https://help.yagpdb.xyz/docs/core/all-commands/ (letti dal sorgente ufficiale https://github.com/botlabs-gg/yagpdb-docs-v2)
- `[LAWLIET]` Lawliet — sorgente ufficiale https://github.com/Aninoss/lawliet-bot (`src/main/resources/configuration_en_us.properties`, `utility_en_us.properties`)
- `[PROBOT]` ProBot — https://docs.probot.io/docs/modules/welcome · https://docs.probot.io/docs/modules/self-assignable-roles · https://probot.io/commands
- `[ARCANE]` Arcane — https://docs.arcane.bot · https://docs.arcane.bot/plugins/welcomer/setup · https://docs.arcane.bot/plugins/roles · https://docs.arcane.bot/core/commands/list
- `[MEE6]` MEE6 — https://wiki.mee6.xyz/en/plugins/reaction-roles · https://help.mee6.xyz/en/articles/710936-mee6-free-vs-premium-plans-comparison
- `[MIMU]` Mimu — https://docs.mimu.bot/command-list.md · https://docs.mimu.bot/settings/getting-started/greet-leave-boost-messages.md · https://docs.mimu.bot/llms.txt
- `[RED]` Red-DiscordBot — https://docs.discord.red/en/stable/cog_guides/admin.html (letto dal sorgente https://github.com/Cog-Creators/Red-DiscordBot, `docs/cog_guides/admin.rst`)
- `[SAPPHIRE]` Sapphire — https://top.gg/bot/678344927997853742 (solo la scheda: il sito della documentazione non è leggibile)

Non letti su fonte ufficiale: **Dyno** (le pagine `docs.dyno.gg/en/modules/autoroles`
e `/welcome` non mostrano il contenuto) e la pagina "welcome" del wiki di
**MEE6** (errore 404). Le loro funzioni di benvenuto e autorole non
sono in tabella.

## Conteggio

113 righe: 101 ❌ e 12 🟡.
