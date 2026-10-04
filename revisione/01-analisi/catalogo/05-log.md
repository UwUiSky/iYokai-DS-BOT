# Catalogo — Log

Ogni riga è un evento registrato o un'impostazione dei log che i grandi bot hanno e iYokai non ha (❌) o ha solo in parte (🟡).
Bot letti: Carl-bot, Zeppelin, YAGPDB, MEE6, Wick, Beemo. I log della moderazione legati ai casi sono in `01-moderazione.md`.
Stato di iYokai preso da `SPEC.md` §8 e §18 e da `cogs/logging/`: ingressi, uscite, ban, ruoli e nickname dei membri, ruoli, canali, inviti, voce, webhook, emoji, sticker, soundboard, thread, impostazioni del server; un solo canale; storico consultabile con `/logs`.

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| LOG-001 | Log dei **messaggi cancellati**, con autore, canale e testo | Carl-bot `delete` [CARL], Zeppelin `MESSAGE_DELETE` [ZEPPELIN], MEE6 [MEE6], Wick [WICK] | ❌ manca | `cogs/logging/message_logs.py`; testo tagliato a 1024 per campo; cache dei messaggi limitata | NF-02 |
| LOG-002 | Log dei **messaggi modificati**, con testo di prima e di dopo | Carl-bot `edit` [CARL], Zeppelin `MESSAGE_EDIT` [ZEPPELIN], MEE6 [MEE6], Wick [WICK] | ❌ manca | Stesso modulo; saltare le modifiche senza cambio di testo (anteprime dei link) | NF-02 |
| LOG-003 | Log delle **cancellazioni in blocco**: un solo riepilogo con un file | Carl-bot `purge` [CARL], Zeppelin `MESSAGE_DELETE_BULK` [ZEPPELIN], Wick [WICK] | ❌ manca | Un messaggio con file di testo sotto 10 MiB | NF-02 |
| LOG-004 | Nel log del messaggio cancellato restano anche **allegati ed embed** | YAGPDB (indirizzo dell'allegato ed embed salvati) [YAGPDB] | ❌ manca | Ricaricare l'allegato nel canale di log se sta sotto 10 MiB (i link scadono); altrimenti solo il nome del file | NF-02 |
| LOG-005 | Log degli **inviti Discord scritti nei messaggi** | Carl-bot, evento `discord` [CARL]; MEE6 "invite posted" [MEE6] | ❌ manca | Evento a parte in `message_logs.py`, con le espressioni del blocco inviti | nuova |
| LOG-006 | Log dei messaggi **fissati e tolti dai fissati** | Wick 5.3 [WICK] | ❌ manca | Ascoltare `on_guild_channel_pins_update` e la voce del registro di controllo | nuova |
| LOG-007 | Log del **cambio di avatar** di un membro | Carl-bot `avatar` [CARL], MEE6 "profile updated" [MEE6] | ❌ manca | Ascoltare `on_user_update`; un evento per ogni server in comune: usare la cache dei membri, senza chiamate in più | nuova |
| LOG-008 | Log del **cambio di nome utente** (non solo del nickname) | Carl-bot `name` [CARL] | 🟡 parziale: registra solo il nickname del server | Stesso ascolto di LOG-007 su nome e nome visualizzato | nuova |
| LOG-009 | Log dei **timeout dati e tolti**, anche fatti dal menu di Discord | Carl-bot `timeout`, `removetimeout` [CARL] | ❌ manca: `on_member_update` guarda solo ruoli e nickname | Confrontare `timed_out_until` prima e dopo; autore dal registro di controllo | nuova |
| LOG-010 | Log della **scadenza** di mute e ban a tempo | Zeppelin `MEMBER_MUTE_EXPIRED`, `MEMBER_TIMED_UNBAN` [ZEPPELIN]; YAGPDB (sban scritto a nome del bot) [YAGPDB] | ❌ manca | Riga di log scritta dallo scheduler alla scadenza | M 1.8 |
| LOG-011 | Log di **lock, slowmode e clear** | Wick (slowmode e purge nel canale dei log) [WICK], Zeppelin `CLEAN` [ZEPPELIN] | ❌ manca: questi comandi non lasciano traccia | Evento di moderazione scritto tramite il router dei canali | M 1.8 |
| LOG-012 | Log di chi **scollega o sposta a forza** un membro in vocale | Zeppelin `VOICE_CHANNEL_FORCE_DISCONNECT`, `VOICE_CHANNEL_FORCE_MOVE` [ZEPPELIN] | 🟡 parziale: registra lo spostamento, non chi l'ha fatto | Leggere le voci `member_move` e `member_disconnect` del registro di controllo | nuova |
| LOG-013 | Log degli eventi dei **palchi** (stage): apertura, modifica, chiusura | Zeppelin `STAGE_INSTANCE_CREATE`, `UPDATE`, `DELETE` [ZEPPELIN] | ❌ manca | Ascoltare `on_stage_instance_create`, `update`, `delete` | nuova |
| LOG-014 | **Canali separati per gruppo** di eventi: messaggi, membri, ingressi e uscite, server, voce | Carl-bot `/log message_channel`, `member_channel`, `join_channel`, `server_channel`, `voice_channel` [CARL] | ❌ manca: un solo canale per tutto | `/log canale tipo: canale:`; tabella `output_channels` | NF-01 |
| LOG-015 | Un comando che **crea la categoria e i canali** dei log già divisi | Carl-bot `/log aio` [CARL] | ❌ manca | `/log crea-canali`; canali visibili solo allo staff; tetti di 50 canali per categoria e 500 per server | NF-01 |
| LOG-016 | **Qualsiasi evento verso qualsiasi canale**, con liste "includi" ed "escludi" per canale | Zeppelin, mappa `channels` con `include` e `exclude` [ZEPPELIN] | ❌ manca | Il router accetta un canale per singolo tipo di evento, non solo per gruppo | NF-01 |
| LOG-017 | **Accendere o spegnere ogni singolo evento**, con le scelte rapide "tutto", "niente", "predefinito" | Carl-bot `/log config [evento]`, 28 eventi più `everything`, `nothing`, `default` [CARL] | 🟡 parziale: si accendono solo due blocchi (log base e log avanzati) | `/log eventi`: menu a scelta multipla (25 voci per menu, più menu se servono) | nuova |
| LOG-018 | **Ignorare canali** nei log dei messaggi | Carl-bot `/log ignore` [CARL], Zeppelin `excluded_channels` [ZEPPELIN] | ❌ manca | `/log ignora canale:` | NF-01 |
| LOG-019 | **Ignorare utenti** nei log dei messaggi | Carl-bot `/log ignore` [CARL], Zeppelin `excluded_users` [ZEPPELIN] | ❌ manca | `/log ignora utente:` | NF-01 |
| LOG-020 | Ignorare i messaggi che **iniziano con un prefisso** (comandi di altri bot) | Carl-bot `/log prefix` [CARL] | ❌ manca | `/log ignora prefisso:` (massimo 10 caratteri) | NF-01 |
| LOG-021 | Ignorare **categorie intere e thread** | Zeppelin `excluded_categories`, `excluded_threads` [ZEPPELIN] | ❌ manca | Accettare categorie e thread in `/log ignora canale:` | nuova |
| LOG-022 | Ignorare chi ha certi **ruoli** | Zeppelin `excluded_roles` [ZEPPELIN] | ❌ manca | `/log ignora ruolo:` | nuova |
| LOG-023 | Ignorare tutti i **bot** | Zeppelin `exclude_bots` [ZEPPELIN] | ❌ manca | Interruttore `/log ignora bot:` | nuova |
| LOG-024 | Ignorare i messaggi che corrispondono a un'**espressione regolare** | Zeppelin `excluded_message_regexes` [ZEPPELIN] | ❌ manca | Opzione avanzata; lunghezza massima e tempo massimo di esecuzione | nuova |
| LOG-025 | **Raggruppare più eventi** vicini in un solo messaggio di log | Zeppelin `batched`, `batch_time` [ZEPPELIN] | ❌ manca: ogni evento è un messaggio (lo spostamento di un canale ne genera molti) | Coda per canale svuotata ogni pochi secondi; rispetta il limite di 10 embed e 6000 caratteri per messaggio | M 5.6 |
| LOG-026 | **Testo di ogni tipo di log scritto dal server**, con segnaposto e formato della data | Zeppelin `format`, `timestamp_format` [ZEPPELIN] | ❌ manca | Modelli con `core/template_renderer.py`; meglio dal pannello web | NF-20 |
| LOG-027 | **Istantanea su richiesta** degli ultimi messaggi di un canale, compresi quelli appena cancellati | YAGPDB `/logs` (cancellati dell'ultima ora, 12 ore con premium) [YAGPDB] | ❌ manca | `/log istantanea canale: quanti:`; file HTML come il transcript dei ticket; serve la cache di NF-02 | nuova |
| LOG-028 | Istantanee **consultabili online**, con scelta di chi può vederle (ruoli, o chiunque abbia il link) | YAGPDB "Access Control" [YAGPDB] | ❌ manca | Pagina del pannello web con accesso tramite Discord; mai visibili a tutti per impostazione predefinita | NF-20 |
| LOG-029 | **Archivio dei messaggi di un utente** negli ultimi 3 giorni, con modifiche e cancellazioni; creato da solo a ogni sanzione | Beemo `/archive` e archivi automatici [BEEMO] | ❌ manca | `/log archivio utente:`; file allegato al caso; serve la cache di NF-02; conservazione da dichiarare nel registro dei dati personali | nuova |
| LOG-030 | **Archivio di un intero canale** in un file | Zeppelin `archive_channel` [ZEPPELIN] | ❌ manca | `/log esporta-canale`; `channel.history()` a blocchi di 100; `defer()`; più file sotto 10 MiB | nuova |

## Fonti

Lette il 4/10/2026.

- **`[CARL]`** Carl-bot (ufficiale): https://docs.carl.gg/logging.md · https://docs.carl.gg/faq.md
- **`[ZEPPELIN]`** Zeppelin (ufficiale, codice sorgente): https://github.com/ZeppelinBot/Zeppelin — `backend/src/plugins/Logs/types.ts`, `backend/src/plugins/ChannelArchiver`
- **`[YAGPDB]`** YAGPDB (ufficiale): https://help.yagpdb.xyz/docs/moderation/logging/ · https://help.yagpdb.xyz/docs/moderation/moderation-tools/ (testo letto dal repository https://github.com/botlabs-gg/yagpdb-docs-v2)
- **`[MEE6]`** MEE6 (ufficiale): https://wiki.mee6.xyz/plugins/moderator
- **`[WICK]`** Wick (ufficiale): https://docs.wickbot.com/changelog/v5.x/5.3.0/ · https://docs.wickbot.com/commands/moderation/slowmode/ · https://docs.wickbot.com/commands/moderation/purge/
- **`[BEEMO]`** Beemo (ufficiale): https://docs.beemo.gg/moderation/archives.html

Non letto su fonte ufficiale: Dyno (`docs.dyno.gg/en/modules/actionlog` si carica solo con JavaScript: nessuna riga viene da Dyno). ProBot, Sapphire, Atlas e Maki non hanno una pagina dei log leggibile da qui.

## Conteggio

Contato sulle righe della tabella (`grep -c "^| LOG-"`).

- Righe totali: **30**
- ❌ manca: **27**
- 🟡 parziale: **3**
