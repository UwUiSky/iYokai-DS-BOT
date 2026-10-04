# Catalogo — Backup e restore

Ogni riga è un comando o una funzione di backup che i bot specializzati hanno e iYokai non ha (❌) o ha solo in parte (🟡).
Bot letti: Xenon (ogni pagina della documentazione), Wick (backup Premium). RestoreCord non è leggibile: le sue voci vengono dal sito di Xenon, che è un concorrente, e sono segnate (terzi).
Stato di iYokai preso da `SPEC.md` §11: il backup va rifatto secondo la decisione D8 (snapshot come dati, server creato da un admin). Oggi esistono solo `/define-main`, `/define-backup` (che fallisce), `/promuovi-backup`, `/restore-users`, `/configura-restore`; `/config export` esporta la configurazione del bot, non la struttura del server.
**Voci in questo file: 41** (❌ mancano: 38 · 🟡 parziali: 3).

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| BKP-001 | **Creare un backup** di canali, categorie, ruoli, permessi e impostazioni del server, salvato come dati | Xenon `/backup create` [XENON]; Wick `/backups create` (Premium) [WICK] | ❌ manca: il flusso di oggi prova a creare un server e fallisce | `/admin backup crea`; snapshot in database; saltare i canali `___hidden___` (LIM-38) | M 12.1 |
| BKP-002 | Nel backup anche **thread e post dei forum** | Xenon (Premium) [XENON] | ❌ manca | Leggere thread attivi e archiviati per canale; solo struttura e ultimi messaggi | M 12.17 |
| BKP-003 | **Caricare un backup** su un server che esiste già, senza espellere i membri | Xenon `/backup load backup_id` [XENON]; Wick `/backups load` [WICK] | ❌ manca | `/admin backup carica`; `defer()` e riepilogo nel canale; mappa per nome per non creare doppioni (M 12.3) | M 12.1 |
| BKP-004 | **Scegliere cosa caricare**: impostazioni, canali, ruoli, ban, membri, messaggi fissati; e se cancellare o no canali e ruoli che ci sono già | Xenon, opzioni `settings`, `channels`, `delete-channels`, `roles`, `delete-roles`, `bans`, `members`, `pins` [XENON] | ❌ manca | Menu a scelta multipla prima del caricamento; di default **non** cancellare niente | M 12.17 |
| BKP-005 | **Elenco dei backup**, i più nuovi per primi, con quelli automatici segnati | Xenon `/backup list [page]` [XENON]; Wick `/backups view` (ultimi 10) [WICK] | ❌ manca | `/admin backup elenco`; 10 per pagina | M 12.17 |
| BKP-006 | **Vedere cosa contiene** un backup senza caricarlo | Xenon `/backup info` [XENON] | ❌ manca | `/admin backup info`: conteggi di canali, ruoli, messaggi e data | M 12.17 |
| BKP-007 | **Eliminare un backup**, o tutti | Xenon `/backup delete` [XENON]; Wick `/backups delete`, `/backups purge` [WICK] | ❌ manca | `/admin backup elimina` con conferma | M 12.17 |
| BKP-008 | **Backup automatici a intervalli**, con più copie conservate | Xenon `/backup interval on` (24 ore gratis, fino a 4 ore; da 1 a 8 copie) [XENON]; Wick (ogni 3 ore, Premium) [WICK] | ❌ manca | `/admin backup intervallo ore:`; lavoro periodico; il più vecchio viene sovrascritto | M 12.17 |
| BKP-009 | **Stato di avanzamento** di un caricamento in corso | Xenon `/backup status` [XENON] | ❌ manca | Stato salvato in database e aggiornato a ogni passo | nuova |
| BKP-010 | **Annullare un caricamento** in corso | Xenon `/backup cancel` [XENON] | ❌ manca | Segnale di stop controllato tra un passo e l'altro; ciò che è già fatto resta | nuova |
| BKP-011 | **Ultimi N messaggi per canale** salvati nel backup | Xenon: 50, 100 o 250 secondo il piano [XENON]; RestoreCord: da 50 a 2000 [RESTORECORD] (terzi) | ❌ manca | Colonna messaggi nello snapshot; N per piano; serve `message_content` | M 12.17 |
| BKP-012 | Messaggi **ripubblicati con nome e avatar dell'autore** tramite webhook | Xenon (Premium) [XENON] | 🟡 parziale: il mirror in tempo reale è scritto ma non ha mai una destinazione | Un webhook per canale, un invio alla volta; nome senza "discord" o "clyde" (M 12.7); al massimo 15 webhook per canale | M 12.6 |
| BKP-013 | **Allegati** ripristinati insieme ai messaggi | Xenon (solo entro 24 ore e sotto 8 MB, perché salva i link) [XENON] | ❌ manca | Ricaricare il file al momento del mirror (sotto 10 MiB); dopo, il link scade | nuova |
| BKP-014 | **Nickname e ruoli di ogni membro** salvati e ridati | Xenon, opzione `members` (Premium) [XENON] | ❌ manca | Tabella per membro nello snapshot; ruoli ridati per nome con `check_role_assignable`; dato personale da dichiarare | nuova |
| BKP-015 | **Lista dei ban** salvata e ricaricata | Xenon, opzione `bans` (Premium) [XENON] | ❌ manca | `guild.bans()` a pagine da 1000; ricarica con pause; motivo fino a 512 caratteri | nuova |
| BKP-016 | **Messaggi fissati** rimessi al loro posto | Xenon, opzione `pins` [XENON] | ❌ manca | Serve il permesso `PIN_MESSAGES` | nuova |
| BKP-017 | Backup **legato all'account** di chi l'ha fatto: resta anche se il server sparisce e si carica su un altro server | Xenon [XENON] | ❌ manca | Snapshot legato al server d'origine più un codice di collegamento con scadenza | M 12.1 |
| BKP-018 | **Chi può creare e chi può caricare**: tre livelli (admin tutto; admin solo creare; solo l'owner) | Xenon `/settings permissions level` [XENON]; Wick (solo owner ed extra owner) [WICK] | ❌ manca | Impostazione con default "gli admin creano, solo l'owner carica" | nuova |
| BKP-019 | **Registro di chi ha usato** backup, modelli e sincronie, tenuto 365 giorni | Xenon `/audit logs` [XENON] | ❌ manca | Riga nello storico eventi per ogni comando di backup | nuova |
| BKP-020 | **Caricare un modello di server** da un nome, un codice o un link `discord.new` | Xenon `/template load` con opzioni [XENON] | ❌ manca | `/admin backup modello carica`; stesso motore del caricamento | NF-39 |
| BKP-021 | **Elenco e scheda** dei modelli dentro Discord | Xenon `/template list`, `/template info` [XENON] | ❌ manca | `/admin backup modello elenco` e `info` | NF-39 |
| BKP-022 | **Raccolta pubblica di modelli** con categorie, ricerca, lingua, voti | Xenon, 5.730 modelli [XENON] | ❌ manca | Si parte con pochi modelli pronti nel bot; la raccolta pubblica vive nel pannello web | NF-39 |
| BKP-023 | **Pubblicare un proprio modello**, con revisione prima che compaia | Xenon [XENON] | ❌ manca | Invio dal pannello web; approvazione dell'owner | NF-39 |
| BKP-024 | **Copiare un canale** con i suoi permessi; per una categoria, anche i canali dentro | Xenon `/clone channel` [XENON] | ❌ manca | `/admin backup copia-canale`; tetti di 50 per categoria e 500 per server | nuova |
| BKP-025 | **Copiare un ruolo** con i suoi permessi e, a scelta, i permessi nei canali | Xenon `/clone role` [XENON] | ❌ manca | `/admin backup copia-ruolo`; tetto di 250 ruoli | nuova |
| BKP-026 | **Salvare gli ultimi messaggi di un canale** (fino a 1000) per ricaricarli dopo | Xenon `/chatlog create [message_count] [before]`, `/chatlog list`, `/chatlog delete` (Premium) [XENON] | ❌ manca | `/admin backup canale salva`; tetto per piano | nuova |
| BKP-027 | **Ricaricare i messaggi salvati** in un canale, anche diverso | Xenon `/chatlog load` [XENON] | ❌ manca | Stesso invio tramite webhook di BKP-012 | nuova |
| BKP-028 | **Sincronia dei messaggi tra due canali**, in una o in due direzioni | Xenon `/sync messages` (Premium) [XENON] | 🟡 parziale: il mirror va solo dal server principale a quello di backup | Direzione configurabile; protezione contro i cicli (ignorare i propri webhook) | NF-39 |
| BKP-029 | **Sincronia dei ban tra due server**, con i ban già esistenti | Xenon `/sync bans` [XENON] | ❌ manca | Solo tra server dello stesso proprietario | NF-39 |
| BKP-030 | **Sincronia di un ruolo tra due server**: chi lo riceve in uno lo riceve nell'altro | Xenon `/sync roles` [XENON] | ❌ manca | Coppie ruolo A ↔ ruolo B; `check_role_assignable` | NF-39 |
| BKP-031 | **Elenco delle sincronie** attive e loro eliminazione | Xenon `/sync list`, `/sync delete` [XENON] | ❌ manca | `/admin backup sincronia elenco` e `togli` | NF-39 |
| BKP-032 | **Esportare la struttura del server** in un file JSON (impostazioni, canali, ruoli, emoji, sticker) | Xenon `/export guild` [XENON] | ❌ manca | `/admin backup esporta`; file sotto 10 MiB | nuova |
| BKP-033 | Esportare **l'elenco dei canali o dei ruoli**, o uno solo con i permessi, in JSON o CSV | Xenon `/export channels`, `/export roles`, `/export channel`, `/export role` [XENON] | ❌ manca | Opzioni `cosa` e `formato` sullo stesso comando | nuova |
| BKP-034 | Esportare la **lista dei ban con i motivi** | Xenon `/export bans` [XENON] | ❌ manca | Scelta "ban" in `cosa`; contiene ID di utenti: solo per gli admin | nuova |
| BKP-035 | Esportare **un messaggio** con embed e allegati | Xenon `/export message` [XENON] | ❌ manca | Utile per riusare un embed nel costruttore | NF-17 |
| BKP-036 | Esportare **chi ha reagito** a un messaggio | Xenon `/export reactions` [XENON] | ❌ manca | Scelta "reazioni"; lettura a pagine | nuova |
| BKP-037 | **Importare la struttura** da un file JSON, scegliendo cosa applicare | Xenon `/import guild` (Premium) [XENON] | ❌ manca | Stesso motore del caricamento; file validato con uno schema prima di toccare il server | nuova |
| BKP-038 | **Ritorno dei membri** dopo la perdita del server, per chi ha dato il consenso | RestoreCord [RESTORECORD] (terzi) | 🟡 parziale: scritto, ma senza coppia di server non parte; token mai rinnovati | Rinnovo dei token, pause e gestione dei 429, invito in DM solo a chi ha acconsentito | M 12.10 |
| BKP-039 | Pagina di consenso su un **indirizzo web proprio** del server | RestoreCord [RESTORECORD] (terzi) | ❌ manca | Solo con il pannello web e il bot con marchio proprio | NF-38 |
| BKP-040 | **Regole di ammissione** alla pagina di consenso per paese, rete o VPN | RestoreCord [RESTORECORD] (terzi) | ❌ manca | iYokai non raccoglie IP nel restore: l'alternativa è il controllo VPN della verifica web (VER-026) | NF-21 |
| BKP-041 | **Gestione dei backup dal pannello web**: vedere, caricare, eliminare | Wick [WICK] | ❌ manca | Pagina del pannello che chiama le stesse funzioni dei comandi | NF-20 |

## Fonti

Lette il 4/10/2026.

- **`[XENON]`** Xenon (ufficiale): https://xenon.bot/docs · https://xenon.bot/docs/backups · https://xenon.bot/docs/templates · https://xenon.bot/docs/clone · https://xenon.bot/docs/chatlog · https://xenon.bot/docs/sync · https://xenon.bot/docs/export · https://xenon.bot/docs/import · https://xenon.bot/docs/settings · https://xenon.bot/docs/audit · https://xenon.bot/docs/premium · https://xenon.bot/docs/faq · https://xenon.bot/docs/help/attachment-limitations · https://xenon.bot/backups · https://xenon.bot/premium · https://xenon.bot/templates
- **`[WICK]`** Wick (ufficiale): https://docs.wickbot.com/commands/utility/backups/ · https://docs.wickbot.com/intro/features/
- **`[RESTORECORD]`** RestoreCord — sito ufficiale non leggibile (errore 403). Fonti usate: https://xenon.bot/blog/xenon-vs-restorecord e https://xenon.bot/compare/backups (**terzi**: Xenon è un concorrente).

Non verificato su fonte ufficiale: tutto ciò che riguarda RestoreCord (righe BKP-011, BKP-038, BKP-039, BKP-040).

## Conteggio

Contato sulle righe della tabella (`grep -c "^| BKP-"`).

- Righe totali: **41**
- ❌ manca: **38**
- 🟡 parziale: **3**
