# Catalogo — AutoMod

Ogni riga è un filtro, una condizione, un'azione o un comando dell'AutoMod che i grandi bot hanno e iYokai non ha (❌) o ha solo in parte (🟡).
Bot letti: Carl-bot, YAGPDB, Zeppelin, Wick, MEE6, ProBot, Lawliet. Il canale trappola e i filtri sugli ingressi sono nel file `03-sicurezza-antiraid-antinuke.md`.
Stato di iYokai preso da `SPEC.md` §6 e da `cogs/automod/`: 10 filtri, azioni delete / warn / mute / ban, eccezioni globali per canale e ruolo, scala di escalation.

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| AMD-001 | Filtro **messaggi ripetuti**: lo stesso testo mandato più volte di seguito | YAGPDB "X consecutive identical messages" [YAGPDB]; Zeppelin `max_duplicates` [ZEPPELIN]; Wick, ripetizione [WICK]; MEE6 "Repeated Text" [MEE6]; ProBot "Duplicated Text" [PROBOT] | ❌ manca | Nuovo filtro in `core/automod_advanced_logic.py`; ultimi testi per utente in memoria con `BoundedCache`; soglia e finestra in secondi | nuova |
| AMD-002 | Filtro **troppi a-capo** (muri di testo) | Zeppelin `max_newlines` [ZEPPELIN], Wick [WICK] | ❌ manca | Conta le righe del messaggio; soglia per messaggio | nuova |
| AMD-003 | Filtro **messaggio troppo lungo** o troppi caratteri in poco tempo | YAGPDB "more than x characters" [YAGPDB], Zeppelin `max_characters` [ZEPPELIN], Wick [WICK] | ❌ manca | Soglia di caratteri per messaggio e per finestra di tempo | nuova |
| AMD-004 | Filtro messaggio troppo corto | YAGPDB "less than x characters" [YAGPDB] | ❌ manca | Opzione `min_caratteri`, utile solo in canali scelti (vedi AMD-034) | nuova |
| AMD-005 | Filtro **troppi spoiler** | MEE6 "Excessive Spoilers" [MEE6] | ❌ manca | Conta le coppie di doppie barre verticali dello spoiler e gli allegati segnati spoiler | nuova |
| AMD-006 | Filtro **troppi link in poco tempo** | Carl-bot `/linkspam rate` [CARL], YAGPDB "X user links in Y seconds" [YAGPDB], Zeppelin `max_links` [ZEPPELIN] | 🟡 parziale: il filtro link è solo permesso / vietato, senza conteggio nel tempo | Riusare `core/automod_rate_tracker.py` con una chiave "link" | nuova |
| AMD-007 | **Menzioni contate nel tempo**, su più messaggi | Carl-bot `/mentionspam set` [CARL], YAGPDB "x mentions within y seconds" [YAGPDB], Zeppelin `max_mentions` [ZEPPELIN] | 🟡 parziale: conta solo le menzioni di un singolo messaggio | Finestra mobile sulle menzioni; opzione "conta una volta sola lo stesso utente" | nuova |
| AMD-008 | Soglie **per canale**: troppi messaggi, menzioni, link o allegati nel canale da parte di tutti | YAGPDB "x channel messages in y seconds" e simili [YAGPDB] | ❌ manca | Chiave del contatore per canale invece che per utente; azione consigliata: slowmode (AMD-052) | nuova |
| AMD-009 | Filtro **spostamenti continui tra vocali** | Zeppelin `max_voice_moves` [ZEPPELIN] | ❌ manca | Ascoltare `on_voice_state_update`; soglia e finestra | nuova |
| AMD-010 | Filtro **creazione di thread a raffica** | Zeppelin `thread_create_spam` [ZEPPELIN] | ❌ manca | Ascoltare `on_thread_create`; soglia per utente | nuova |
| AMD-011 | Regole con **espressioni regolari scritte dal server** | YAGPDB "Message matches Regex" e il suo contrario [YAGPDB]; Zeppelin `match_regex` [ZEPPELIN] | ❌ manca | Regola nativa di Discord: 10 espressioni per regola, 260 caratteri l'una; al massimo 6 regole "parole chiave" per server | nuova |
| AMD-012 | Lista di **sole parole permesse** (tutto il resto è bloccato) | YAGPDB "Word allowlist" [YAGPDB] | ❌ manca | Filtro lato bot limitato a canali scelti | nuova |
| AMD-013 | Scelta tra "**solo parola intera**" e "anche dentro altre parole" | ProBot "Match Whole Words Only" [PROBOT], Zeppelin `only_full_words` [ZEPPELIN], Lawliet [LAWLIET] | 🟡 parziale: la parola va scritta con gli asterischi dell'AutoMod nativo, non c'è un'opzione | Opzione `modo` in `/security automod badword-add` che aggiunge gli `*` da sola | nuova |
| AMD-014 | Riconoscere **lettere simili, accenti e spazi** messi per aggirare il filtro | YAGPDB "Also match visually similar characters" [YAGPDB]; Zeppelin `normalize`, `loose_matching` [ZEPPELIN]; Carl-bot (ignora la punteggiatura) [CARL] | ❌ manca | Normalizzazione Unicode (NFKD) e rimozione dei separatori prima del confronto, lato bot | nuova |
| AMD-015 | **Lista pronta** di parolacce da accendere con un clic | YAGPDB (lista predefinita) [YAGPDB] | ❌ manca | Regola nativa "preset" di Discord (volgarità, contenuti sessuali, insulti): 1 per server | nuova |
| AMD-016 | **Più liste con nome** (parole o domini) riusabili in regole diverse | YAGPDB "Lists": 5 gratis, 25 premium, 5000 caratteri l'una [YAGPDB] | ❌ manca: una sola lista di parole e due di domini | Tabella `automod_lists`; tetto per server; elenco oltre 1900 caratteri mandato come file (M 2.4) | nuova |
| AMD-017 | Filtro su **nickname e nome utente** (parole, regex, inviti nel nome) | YAGPDB "Nickname denylist", "Nickname matches regex" [YAGPDB]; Zeppelin `match_nicknames`, `match_usernames` [ZEPPELIN] | 🟡 parziale: solo un controllo sul nome all'ingresso, nell'anti-raid | Regola nativa "profilo del membro" di Discord (1 per server) più controllo su `on_member_update` | nuova |
| AMD-018 | Filtro sullo **stato personalizzato** dell'utente | Zeppelin `match_custom_status` [ZEPPELIN] | ❌ manca | Serve l'intent delle presenze (privilegiato); costo alto: da valutare | nuova |
| AMD-019 | Filtro anche sul testo degli **embed** del messaggio | Zeppelin `match_embeds` [ZEPPELIN] | ❌ manca | Leggere `message.embeds` (titolo, descrizione, campi) nei filtri di testo | nuova |
| AMD-020 | Filtro anche sul testo dei **messaggi inoltrati** | YAGPDB (controlla gli inoltri; condizioni "ignora / solo inoltri") [YAGPDB] | ❌ manca | Leggere `message.message_snapshots`; opzione per ignorarli | nuova |
| AMD-021 | Controllo anche dei messaggi **modificati** | YAGPDB, condizioni "New message" / "Edited message" [YAGPDB] | ❌ manca: i filtri guardano solo i messaggi nuovi | Ascoltare `on_message_edit` e rifare i controlli sul testo | nuova |
| AMD-022 | Lista di **tipi di file** permessi o vietati | Carl-bot `/deletefiles` (solo formati sicuri) [CARL]; Zeppelin `match_attachment_type`, `match_mime_type` [ZEPPELIN] | ❌ manca | Lista di estensioni; controllo su `attachment.filename` e `content_type` | nuova |
| AMD-023 | **Canali solo media**: i messaggi senza immagine o file vengono cancellati | Carl-bot `/automod media` [CARL], ProBot "Image-Only Channels" [PROBOT], YAGPDB "Message without attachments" [YAGPDB] | ❌ manca | `/security automod solo-media canale:`; fino a 25 canali; lo staff è escluso | nuova |
| AMD-024 | Canali dove gli **allegati sono vietati** | YAGPDB "Message with attachments" [YAGPDB] | ❌ manca | Stessa tabella di AMD-023 con modo "solo testo" | nuova |
| AMD-025 | Canali dove sono ammessi **solo link di YouTube** | ProBot "YouTube-Only Channels" [PROBOT] | ❌ manca | Stessa tabella di AMD-023 con una lista di domini permessi per canale | nuova |
| AMD-026 | Inviti: **permettere quelli di server scelti** | Zeppelin `invite_guild_whitelist`, `invite_code_whitelist` [ZEPPELIN] | ❌ manca: il blocco inviti è solo acceso / spento | Lista delle eccezioni della regola nativa (100 voci) con i codici permessi | nuova |
| AMD-027 | Inviti: non bloccare quelli **del proprio server** | YAGPDB [YAGPDB] | ❌ manca | Leggere gli inviti del server (`core/invite_tracker.py`) e metterli tra le eccezioni | nuova |
| AMD-028 | Inviti: riconoscere anche i **siti-vetrina** (discord.me, invite.gg, disboard.org…) | YAGPDB [YAGPDB] | ❌ manca: le regole coprono solo discord.gg e discord.com/invite | Aggiungere i domini alle espressioni della regola (10 per regola) | nuova |
| AMD-029 | Link e inviti: punire **solo chi non ha ruoli** | Carl-bot `/linkspam norole`, `/invitespam norole` [CARL] | ❌ manca | Condizione "senza ruoli" sul filtro | nuova |
| AMD-030 | Link controllati con **Google Safe Browsing** | YAGPDB "Google flagged bad links" [YAGPDB] | ❌ manca | Seconda fonte accanto alla lista di phishing; serve una chiave API con quota: da scrivere in `LIMITI.md` | NF-31 |
| AMD-031 | Blocco di siti con **cattura dell'IP, malware e siti per adulti** | Wick [WICK]; Zeppelin `include_malicious` [ZEPPELIN] | ❌ manca | Liste in più dentro `core/phishing_logic.py` | NF-31 |
| AMD-032 | Regola valida solo per **account giovani** (o solo per account vecchi) | YAGPDB "Account age above / below" [YAGPDB] | ❌ manca | Condizione per filtro: età minima dell'account in minuti | nuova |
| AMD-033 | Regola valida solo per chi è **entrato da poco** nel server | YAGPDB "Server Member duration above / below" [YAGPDB] | ❌ manca | Condizione su `member.joined_at` | nuova |
| AMD-034 | Regola **attiva solo in canali o categorie scelti** | YAGPDB "Active in channels", "Active in Categories" [YAGPDB]; MEE6 [MEE6] | ❌ manca | Lista dei canali per filtro; se vuota vale ovunque | nuova |
| AMD-035 | **Eccezioni diverse per ogni filtro** (ruoli e canali) | YAGPDB (per regola) [YAGPDB], MEE6 (per filtro) [MEE6], ProBot "Disabled Channels / Roles" [PROBOT], Wick (whitelist per tipo) [WICK] | 🟡 parziale: le eccezioni valgono per tutti i filtri insieme | Colonna `filtro` (facoltativa) nella tabella delle eccezioni | nuova |
| AMD-036 | Eccezione per una **categoria intera** | YAGPDB "Ignore Categories" [YAGPDB], Wick [WICK] | ❌ manca | Accettare anche le categorie in `exempt-channel-add` | nuova |
| AMD-037 | Eccezione per **singolo utente** | Lawliet "Excluded Users" [LAWLIET], Wick `whitelist @member` [WICK] | ❌ manca | Tipo "utente" nella tabella delle eccezioni | nuova |
| AMD-038 | Regola valida **solo per chi ha certi ruoli** | YAGPDB "Require Roles" [YAGPDB], MEE6 [MEE6] | ❌ manca | Lista di ruoli richiesti per filtro | nuova |
| AMD-039 | Scelta se applicare la regola **nei thread** | YAGPDB "Active in threads", "Ignore threads" [YAGPDB] | ❌ manca | Interruttore per filtro; il thread eredita le eccezioni del canale padre | nuova |
| AMD-040 | Controllo anche dei messaggi di **webhook e bot** | Wick `heat 6` [WICK]; YAGPDB "Only Bots" [YAGPDB] | ❌ manca: i bot sono sempre ignorati | Interruttore "controlla i webhook"; azione possibile: solo cancellare | nuova |
| AMD-041 | Azione **kick** nei filtri | Carl-bot [CARL], YAGPDB [YAGPDB], Zeppelin [ZEPPELIN] | 🟡 parziale: c'è nella scala di escalation, non in `actions-set` | Aggiungere `kick` a `/security automod actions-set` | nuova |
| AMD-042 | Azione **ban a tempo** | Carl-bot `tempban` [CARL], YAGPDB (durata del ban) [YAGPDB] | ❌ manca | Opzione durata sull'azione ban; sblocco con lo scheduler | nuova |
| AMD-043 | **Durata del mute diversa per ogni filtro** | Carl-bot `tempmute <durata>` [CARL], YAGPDB [YAGPDB], Zeppelin [ZEPPELIN] | 🟡 parziale: una sola durata per tutto (`/automod mute-duration`) | Durata salvata per filtro; massimo 28 giorni | nuova |
| AMD-044 | Azione **mute con ruolo** invece del timeout | Carl-bot `mute` [CARL], YAGPDB "Mute user" [YAGPDB] | ❌ manca: l'azione "mute" è un timeout | Scelta `timeout / ruolo` sull'azione | nuova |
| AMD-045 | Azione **messaggio nel canale** per chi ha violato, che si cancella da solo | Carl-bot `message` [CARL]; YAGPDB "Send Message" (280 caratteri, si cancella entro 3600 s) [YAGPDB]; Zeppelin `reply` [ZEPPELIN] | ❌ manca: scrive solo nel canale di log | Testo per filtro con segnaposto; `delete_after`; al massimo uno ogni pochi secondi per canale | nuova |
| AMD-046 | Azione **DM all'utente** | Carl-bot `dm` [CARL] | ❌ manca | Testo per filtro; `HTTPException` catturata se i DM sono chiusi | nuova |
| AMD-047 | Azione "**decidono i moderatori**": il caso va in un canale e lo staff sceglie | Carl-bot `defer` e "drama channel" (Premium) [CARL] | ❌ manca | Messaggio nel canale staff con bottoni Ignora / Warn / Timeout / Ban; View persistente | nuova |
| AMD-048 | Avviso allo staff con **ping di un ruolo** | Zeppelin `alert` con menzioni [ZEPPELIN]; YAGPDB "Send Alert" [YAGPDB] | 🟡 parziale: embed nel canale di log, senza ping | Ruolo da avvisare per filtro; `allowed_mentions` limitato a quel ruolo | nuova |
| AMD-049 | Avviso in **DM a membri dello staff** scelti | Lawliet "Log Receivers" [LAWLIET] | ❌ manca | Lista di utenti (fino a 10) per filtro | nuova |
| AMD-050 | Azione **dare o togliere un ruolo**, anche a tempo | YAGPDB "Give role", "Remove role" [YAGPDB]; Zeppelin `add_roles`, `remove_roles` [ZEPPELIN] | ❌ manca | `check_role_assignable` quando si configura e quando si esegue | nuova |
| AMD-051 | Azione **cambia nickname** | YAGPDB "Set nickname" [YAGPDB], Zeppelin `change_nickname` [ZEPPELIN] | ❌ manca | Utile con AMD-017; nickname fino a 32 caratteri | nuova |
| AMD-052 | Azione **accendi lo slowmode** nel canale, per un tempo scelto | YAGPDB "Enable Channel slowmode" [YAGPDB], Zeppelin `set_slowmode` [ZEPPELIN] | ❌ manca | `channel.edit(slowmode_delay=…)`; ritorno al valore di prima con lo scheduler | nuova |
| AMD-053 | Azione **cancella anche gli ultimi messaggi** dell'utente, non solo quello che ha fatto scattare la regola | YAGPDB "Delete multiple messages" [YAGPDB], Zeppelin `clean` [ZEPPELIN] | ❌ manca | `purge` con filtro sull'autore, numero e età massima | nuova |
| AMD-054 | Azione **metti in pausa gli inviti** del server | Zeppelin `pause_invites` [ZEPPELIN] | ❌ manca | `guild.edit(invites_disabled=True)`; ripristino a tempo | NF-29 |
| AMD-055 | Azione **cambia i permessi** di un canale o di un ruolo | Zeppelin `change_perms` [ZEPPELIN] | ❌ manca | Solo permessi non pericolosi; stato di prima salvato | nuova |
| AMD-056 | Azioni sui thread: archiviare il thread, aprire un thread sul messaggio | Zeppelin `archive_thread`, `start_thread` [ZEPPELIN] | ❌ manca | Due azioni in più nell'elenco | nuova |
| AMD-057 | **Blocco automatico dei canali** quando arrivano troppe menzioni in pochi secondi | Wick "Auto Lockdown" (gratis; esempio: 50 menzioni in 30 secondi) [WICK] | ❌ manca | Soglia a livello di server che chiama il blocco | NF-29 |
| AMD-058 | **Contatori di violazioni separati per regola**, con nome | YAGPDB "+Violation" con nome [YAGPDB], Zeppelin "Counters" [ZEPPELIN] | 🟡 parziale: un solo conteggio per utente | Colonna `nome` nel conteggio della scala | nuova |
| AMD-059 | Regola "**X violazioni in Y minuti**" con azione propria | YAGPDB "X Violations in y minutes" [YAGPDB]; YAGPDB base (soglie per mute, kick, ban per ogni regola) [YAGPDB] | 🟡 parziale: la scala conta il totale, non una finestra | Finestra in minuti per gradino | nuova |
| AMD-060 | **Scadenza delle violazioni** diversa per ogni regola | YAGPDB base (da 0 a 44.640 minuti) [YAGPDB] | 🟡 parziale: `/escalation set-reset-days` vale per tutto | Scadenza per nome di violazione | nuova |
| AMD-061 | Azione **azzera le violazioni** | YAGPDB "Reset violations" [YAGPDB] | ❌ manca | Azione nell'elenco, per nome | nuova |
| AMD-062 | Comando: **violazioni di un utente**, in pagine | YAGPDB `/automod listviolations` [YAGPDB] | ❌ manca | `/security automod violazioni utente:`; legge `automod_action_log`; 10 per pagina | nuova |
| AMD-063 | Comando: riepilogo delle violazioni di tutto il server, filtrabile per età | YAGPDB `/automod listviolationscount` [YAGPDB] | ❌ manca | `/security automod riepilogo`; conteggi per filtro e per utente | nuova |
| AMD-064 | Comando: **ultime regole scattate** | YAGPDB `/automod logs` [YAGPDB] | 🟡 parziale: c'è solo l'embed nel canale di log | `/security automod ultime` sulle righe di `automod_action_log` | nuova |
| AMD-065 | Comando: cancellare **una singola violazione** | YAGPDB `/automod deleteviolation` [YAGPDB] | ❌ manca | `/security automod violazione-togli numero:` | nuova |
| AMD-066 | Comando: azzerare le violazioni di **tutti**, con filtri per nome ed età | YAGPDB `/automod clearviolations` (fino a 2000 alla volta) [YAGPDB] | 🟡 parziale: `/escalation reset` vale per un membro | Opzione `tutti` con conferma | nuova |
| AMD-067 | **Gruppi di regole** da accendere e spegnere con un comando | YAGPDB "Rulesets", `/automod toggle` [YAGPDB] | ❌ manca | Profili salvati ("normale", "evento", "raid") e `/security automod profilo` | nuova |
| AMD-068 | **Punteggio "calore"**: ogni filtro aggiunge una percentuale, superata la soglia scatta la punizione | Wick "Heat", percentuale per filtro e soglia massima [WICK] | 🟡 parziale: la scala conta le violazioni, senza pesi | Peso per filtro e soglia; valore in memoria, mai su disco | nuova |
| AMD-069 | Il punteggio **cala da solo nel tempo**, con velocità regolabile | Wick `heat 4` [WICK] | ❌ manca: c'è solo l'azzeramento dopo N giorni | Decadimento calcolato alla lettura | nuova |
| AMD-070 | **Timeout che cresce** a ogni ricaduta: durata base, moltiplicatore, tetto di strike | Wick "Auto Timeouts", `heat 5`, `7b`, `7c` [WICK] | 🟡 parziale: durate fisse per gradino | Durata = base × moltiplicatore^strike, entro 28 giorni | nuova |
| AMD-071 | **Modalità panico dell'AutoMod**: se molti utenti sospetti scattano insieme, timeout immediato a ogni loro messaggio | Wick "Heat Panic Mode" (Premium) [WICK] | ❌ manca | Stato temporaneo per server (circa 10 minuti) che abbassa la soglia per gli utenti sospetti | NF-29 |
| AMD-072 | Un messaggio in un **canale fermo da tempo** pesa di più | Wick, "inactivity" [WICK] | ❌ manca | Peso in più se l'ultimo messaggio del canale è vecchio | nuova |
| AMD-073 | **Pulizia automatica di un canale**: i messaggi spariscono dopo un intervallo scelto | Carl-bot `/autopurge set`: da 1 ora a 14 giorni, 15 canali (Premium) [CARL]; Zeppelin "AutoDelete", fino a 5 minuti [ZEPPELIN] | ❌ manca | `/security automod pulizia canale: ogni:`; lavoro periodico; blocchi da 100, non oltre 14 giorni; tetto di canali | nuova |
| AMD-074 | Pulizia automatica **solo di un tipo** di messaggi (persone, bot, link, inviti, allegati) | Carl-bot `autopurge`, `message_type` [CARL] | ❌ manca | Opzione `tipo` sulla stessa regola | nuova |
| AMD-075 | Regole che scattano su **eventi diversi dai messaggi** (ruolo dato o tolto, uscita, warn, mute, nota) | Zeppelin, trigger `role_added`, `member_leave`, `warn`, `mute`, `note` [ZEPPELIN] | ❌ manca | Solo se serve: un piccolo elenco di eventi collegati a un'azione | nuova |

## Fonti

Lette il 4/10/2026.

- **`[CARL]`** Carl-bot (ufficiale): https://docs.carl.gg/automod.md · https://docs.carl.gg/faq.md
- **`[YAGPDB]`** YAGPDB (ufficiale): https://help.yagpdb.xyz/docs/moderation/basic-automoderator/ · https://help.yagpdb.xyz/docs/moderation/advanced-automoderator/overview/ · `/triggers/` · `/conditions/` · `/effects/` · https://help.yagpdb.xyz/docs/core/all-commands/ (testo letto dal repository https://github.com/botlabs-gg/yagpdb-docs-v2)
- **`[ZEPPELIN]`** Zeppelin (ufficiale, codice sorgente): https://github.com/ZeppelinBot/Zeppelin — `backend/src/plugins/Automod/triggers`, `Automod/actions`, `Censor`, `Spam`, `AutoDelete`, `Counters`
- **`[WICK]`** Wick (ufficiale): https://docs.wickbot.com/intro/features/ · https://docs.wickbot.com/setup/
- **`[MEE6]`** MEE6 (ufficiale): https://wiki.mee6.xyz/plugins/moderator
- **`[PROBOT]`** ProBot (ufficiale): https://docs.probot.io/docs/modules/automod
- **`[LAWLIET]`** Lawliet (ufficiale, codice sorgente): https://github.com/Aninoss/lawliet-bot — `src/main/resources/moderation_en_us.properties`

Non letti su fonte ufficiale per questa area: Dyno (`docs.dyno.gg/en/modules/automod` si carica solo con JavaScript: nessuna riga viene da Dyno), Sapphire, Atlas, Maki.

## Conteggio

Contato sulle righe della tabella (`grep -c "^| AMD-"`).

- Righe totali: **75**
- ❌ manca: **60**
- 🟡 parziale: **15**
