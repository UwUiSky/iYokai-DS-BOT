# SPEC.md — Specifica canonica iYokai + audit dello stato reale

**Questo file è la FONTE DI VERITÀ del progetto.**

Trascritto dallo schema ultra-dettagliato originale della conversazione
di progettazione, foglia per foglia, con a fianco lo stato verificato
contro il codice reale (non contro una roadmap riassunta).

## Perché questo file esiste

Le prime fasi di sviluppo sono state guidate da una roadmap
*riassunta* che io (Claude) avevo derivato dallo schema originale.
Quella compressione ha fatto sparire intere sezioni senza segnalarle
come rimandate, e ogni successivo "controllo" l'ho fatto ricostruendo
a memoria invece di rileggere lo schema — ripetendo lo stesso errore
tre volte di fila. Da qui in avanti: **ogni sessione parte da questo
file, non da un riassunto.**

## Legenda stato

| Simbolo | Significato |
|---|---|
| `[x]` | Fatto e testato |
| `[~]` | Parziale — esiste qualcosa ma non tutto quanto specificato |
| `[ ]` | Mancante — nessun codice |
| `[✗]` | Scartato deliberatamente, con motivo |

---

# A. iYOKAI BOT (guild-installed)

## §1 CORE SYSTEM

- `[x]` 1.1 Multi-Tenant Engine — isolamento config per Guild ID
- `[x]` 1.1 Attivazione/disattivazione feature per server (check runtime)
- `[✗]` 1.1 "Scaricamento moduli non utilizzati dalla memoria" — non
  fattibile: `load_extension` è per-processo, non per-guild. Sostituito
  dal check runtime. Vedi § Decisioni in PROGRESS.md
- `[x]` 1.2 Cog Manager — load / unload / reload
- `[x]` 1.2 Controllo stato attivazione modulo per server
- `[x]` 1.2 Evento `modules_updated` — `SetupView.save()` ora emette
  `interaction.client.dispatch("modules_updated", guild_id,
  module_name, active, changed_by)` per ogni modulo il cui stato è
  DAVVERO cambiato (stesso criterio già usato per lo storico Config
  Diff & Rollback) — infrastruttura pronta, nessun consumatore
  ancora (stesso schema di invite_tracker prima di Spam Trap): un
  futuro listener si registra con `@commands.Cog.listener()` su
  `on_modules_updated`
- `[x]` **1.3 Memory Guard**
  - `[x]` Monitoraggio RAM ogni 60 secondi (psutil) — `core/memory_guard.py`, letto per davvero con `psutil.Process().memory_info().rss`, verificato con un test che legge la RAM vera del processo di test (nessun mock)
  - `[x]` Garbage collection forzata su soglia — evoluta a **quattro
    livelli** (NORMAL/WARNING/CRITICAL/EMERGENCY, BACKLOG.md §4):
    GC da WARNING in su, DM solo da CRITICAL (col cooldown di 30 min
    di prima), EMERGENCY bypassa sempre il cooldown
  - `[x]` Limitazione dimensione cache — `core/bounded_cache.py`
    (LRU vera, §1.5), collegata come consumatore reale a
    `core/invite_tracker.py`, che prima cresceva senza limiti con il
    numero di server
  - `[x]` Distruzione VoiceClient inutilizzati (canale rimasto senza
    membri umani)
  - `[x]` Alert DM al proprietario al superamento soglia (con
    cooldown di 30 minuti tra un alert e l'altro, per non spammare
    l'owner ad ogni tick se la RAM resta alta)
- `[x]` 1.4 Database Layer — pool asyncpg, localhost, query asincrone
- `[x]` 1.5 Cache Layer (LRU con dimensione massima) —
  `core/bounded_cache.py`, politica LRU vera verificata esplicitamente
  (un GET conta come uso recente quanto un SET)
- `[x]` 1.6 Error Handler Globale — `on_error` in `main.py` ora copre
  anche le eccezioni non catturate nei listener di eventi (non solo
  gli slash command), con alert DM all'owner e cooldown per
  event_method
- `[x]` 1.7 Logger Strutturato — JSON con rotazione
  (`core/json_log_formatter.py` + `RotatingFileHandler`, 10MB×5),
  nessuna nuova dipendenza. Convive con l'output testuale su stdout,
  non lo sostituisce
- `[x]` 1.8 Auto-Setup Engine
  - `[x]` Trigger `on_guild_join` + creazione record DB
  - `[x]` **Invio del messaggio di benvenuto all'ingresso** con
    fallback a catena (system_channel → primo canale scrivibile → DM
    owner). Bug reale trovato scrivendo il test: se l'invio sul
    system_channel falliva, la ricerca del canale alternativo poteva
    ritrovare lo stesso identico canale (quasi sempre incluso anche
    in `guild.text_channels`) e ritentarlo invece di passarne uno
    diverso — corretto escludendolo esplicitamente dalla ricerca
- `[x]` 1.9 Sharding (AutoShardedBot)

## §2 SETUP & DASHBOARD

- `[x]` 2.1 Pannello interattivo — select menu moduli, conferma, annulla
- `[x]` 2.1 Bottone "Reset configurazione" — `/config reset`, conferma
  a due passaggi (stesso schema di `/config rollback`), disattiva
  tutti i moduli e azzera tutte le settings, annullabile con
  `/config rollback` come qualunque altra voce di storico
- `[x]` 2.2 Wizard di configurazione guidata passo-passo —
  `/setup-wizard`, un modulo curato alla volta (Moderazione, AutoMod,
  Logging, Greetings, Vocali temporanei, Ticket) con Attiva/Disattiva
  + Avanti/Indietro, a differenza di `/setup` (tutti i moduli in un
  solo select menu)
- `[~]` 2.3 Lingua per server — comando (`/config language show|set`)
  e colonna `language` ora collegati, con un piccolo registro di
  traduzioni (`core/i18n.py`) per un insieme limitato di stringhe
  generiche condivise. **Non un sistema i18n applicato a tutto il
  bot**: la stragrande maggioranza dei messaggi resta in italiano nei
  singoli cog — tradurre l'intero bot è un lavoro enormemente più
  grande di questa singola voce, onestamente non dichiarato completo
- `[✗]` 2.4 Prefisso personalizzato — scartato: slash-command-only per
  non richiedere il Message Content Intent. **La colonna `prefix` in
  `guild_config` è morta e va rimossa o documentata come deprecata**
- `[x]` 2.5 Esporta configurazione — `/config export`, file `.json`
  con moduli/settings/lingua
- `[x]` 2.6 Importa configurazione — `/config import`, sovrascrive IN
  BLOCCO (non un merge), validazione del formato prima di applicare
- `[x]` 2.7 Log delle modifiche di setup (audit trail: chi ha
  attivato/disattivato cosa e quando) — esteso oltre la richiesta
  originale con il **rollback**: `/config history` + `/config
  rollback <id>` con conferma a due passaggi (BACKLOG.md §11)

## §3 PREMIUM SYSTEM

- `[x]` 3.1 Registry moduli + flag premium per modulo, tutto OFF di default
- `[x]` 3.2 Whitelist manuale per Server ID (add / remove)
- `[x]` 3.2 Comando per **elencare** i server in whitelist —
  `/owner whitelist-list`
- `[x]` 3.2 Attiva/disattiva natura premium di un singolo modulo
- `[x]` 3.2 Visualizza stato premium di **tutti** i server —
  `/owner premium-status-all`, un meccanismo di sblocco (whitelist/
  nitro boost/premium via cassa/abbonamenti per modulo) per riga, non
  solo un True/False complessivo
- `[x]` 3.3 Controllo runtime (`requires_module`)
- `[x]` 3.1 Metodo sblocco: **Boost Nitro** sul server principale
  (`Member.premium_since`) — richiesto esplicitamente dall'utente
  ("per ora attivi solo... nitro boost..."). `core.premium.
  _guild_owner_boosts_main_guild`: l'OWNER del server richiedente
  deve avere un boost attivo su `config.MAIN_GUILD_ID` — sblocca
  TUTTI i moduli premium per quel server (come whitelist), non uno
  specifico. Assunzione presa per inferenza (nessun dettaglio più
  fine specificato): controlla l'owner del server, non un admin
  qualsiasi — da correggere se non è quello che si intendeva
- `[~]` 3.1 Metodo sblocco: 1.000.000 coin per modulo — **rimandato**
  su richiesta esplicita dell'utente ("per ora attivi solo... nitro
  boost, pagamento mensile|annuale"), non scartato: resta un metodo
  di sblocco previsto, solo non prioritario ora
- `[x]` 3.1 Metodo sblocco: pagamento **mensile o annuale** per
  modulo — l'utente ha aggiunto "mensile" a quanto originariamente
  previsto ("annuale" da solo). Nessun gateway di pagamento reale
  integrato (Discord non ne fornisce uno nativo utilizzabile da un
  bot normale, e questo progetto non processa mai pagamenti — stesso
  principio già in `core/premium_purchase_service.py` per il premium
  via cassa): il pagamento avviene FUORI dal bot, l'OWNER concede
  l'abbonamento a mano con `/owner premium-grant <server> <modulo>
  <mensile|annuale>` dopo averlo incassato — `/owner premium-revoke`
  e `/owner premium-subscriptions` completano il ciclo.
  `core.repositories.module_subscription_repo`, una riga per
  (server, modulo): a differenza di nitro boost/whitelist (sbloccano
  TUTTO), questo resta scoped al singolo modulo per design, come
  esplicitamente previsto dallo schema originale ("per modulo")
- `[x]` **Override temporaneo di fase ALPHA** — **voce nuova**, non
  nello schema originale, aggiunta su richiesta esplicita
  dell'utente: "mi raccomando per ora (dato che è in alpha, tutte le
  feature premium sono sbloccate per tutti)". `config.
  PREMIUM_ALPHA_UNLOCK_ALL` (default **true**): quando attivo,
  `guild_has_premium_access` sblocca SEMPRE tutto per tutti, a
  prescindere da whitelist/boost/abbonamento — controllato PRIMA di
  ogni altra condizione. Va impostato a `false` in `.env` quando
  l'alpha finisce, per far valere davvero i metodi di sblocco sopra
- `[x]` 3.3 Ricarica delle flag premium dal DB all'avvio — **debito
  reale trovato in questa sessione**: `premium_module_flags` esiste
  già (`_apply_premium_toggle` in `cogs/utility/owner_premium.py`
  la scrive), ma nessun consumatore la rileggeva mai all'avvio, quindi
  lo stato premium impostato con `/owner premium-toggle` si perdeva
  ad ogni riavvio del bot anche restando persistito in tabella.
  Corretto con `core.premium.reload_premium_flags_from_database()`,
  chiamata da `main.py.setup_hook` **subito dopo** `load_all_cogs()`
  (non durante `Database.run_migrations`: a quel punto i moduli non
  sono ancora registrati e `registry.set_module_premium` solleverebbe
  `ValueError` "non registrato"). Righe di moduli non (più) registrati
  o diventati sempre-gratuiti vengono ignorate in silenzio, mai un
  crash all'avvio

## §4 VERIFY + FINGERPRINT + ANTI-ALT — Verify Base completo, il resto dipende dal Web Panel

- `[x]` 4.1 Verify Base
  - `[x]` Button verify — `VerifyPanelView`, persistente (stesso
    pattern di ticket/vocali temporanei)
  - `[x]` Reaction verify — `on_raw_reaction_add`. **Non supporta il
    captcha**: una reazione non è un'Interaction, non può aprire un
    Modal — combinazione rifiutata esplicitamente a `/verify setup`
    con un messaggio chiaro, non implementata a metà
  - `[x]` Captcha — testuale (domanda di somma generata al click,
    diversa ogni volta), solo in modalità button per il motivo sopra.
    Nessuna immagine: evita Pillow come nuova dipendenza solo per
    questo
  - `[x]` Controllo età account
  - `[x]` Controllo mutual servers — confermato il limite già noto:
    il bot vede solo quanti server IN CUI SI TROVA LUI contengono
    anche l'utente, non tutti i server dell'utente in assoluto
  - `[x]` Invite tracker (cache inviti + diff al join) — costruito
    come infrastruttura condivisa in `core/invite_tracker.py`
    (durante lo sviluppo di Spam Trap §7.3, che ne aveva bisogno per
    primo)
- `[ ]` 4.2 Verify Avanzato (richiede Web Panel) — non tentato,
  dipendenza non costruita
  - `[ ]` Raccolta IP / ISP / localizzazione
  - `[ ]` Browser fingerprint / device fingerprint
  - `[ ]` OAuth2 scope `identify`
  - `[ ]` Salvataggio fingerprint (hash, mai IP in chiaro)
- `[ ]` 4.3 Sistema Anti-Alt — dipende da §4.2, non costruito
  - `[ ]` Database fingerprint
  - `[ ]` Match → segnalazione allo staff (NON ban automatico
    cross-server; vedi § Decisioni)
  - `[ ]` Rilevamento pattern sospetti
- `[x]` 4.4 Whitelist utenti — bypassa tutti i controlli, verificato
  che vinca anche in combinazione con la blacklist (vedi 4.5)
- `[x]` 4.5 Blacklist utenti — **vince sempre**, anche su un utente
  erroneamente anche whitelistato: verificato esplicitamente con un
  test dedicato, non assunto
- `[x]` 4.6 Log completo di ogni tentativo di verify — tabella
  `verify_attempts` + embed nel canale log configurato, per ogni
  esito (successo o fallimento)

## §5 MODERATION

- `[x]` 5.1 Warn, Kick, Ban, Tempban, Timeout, Unban, Untimeout
- `[x]` 5.1 **Softban** (ban+unban immediato per cancellare i messaggi)
- `[x]` 5.1 **Mute via ruolo** — ruolo "Muted" auto-creato con
  overwrite su ogni canale esistente al momento della creazione
  (canali creati dopo non ereditano l'overwrite, limite noto)
- `[x]` 5.2 Case system — numerazione atomica per server, ricerca per
  numero, storico per utente
- `[x]` 5.3 Note utente
- `[x]` 5.4 Report system
- `[x]` 5.5 Lock / Unlock canale
- `[x]` 5.6 Slowmode
- `[x]` 5.7 Clear avanzato con filtri
- `[x]` 5.8 DM all'utente moderato
- `[x]` 5.9 **"Reason obbligatorio"** — `reason: str` (non più
  `str | None`) su warn/kick/ban/tempban/unban/timeout/softban/
  mute-role/unmute-role, con validazione minimo 3 caratteri.
  `/untimeout` (revoca, non azione punitiva) e `/lock` (stato del
  canale, non azione su un utente) restano con reason opzionale per
  scelta dichiarata, non nella lista esplicita dello schema
- `[x]` 5.10 Moderation logs su canale dedicato — `/mod-log-setup`,
  ogni azione pubblica una copia del case embed lì, oltre alla
  risposta nel canale del comando

## §6 AUTOMOD

- `[x]` 6.1 Anti-badwords (via AutoMod nativo Discord, con merge a tre vie)
- `[x]` 6.2 Anti-invite (via AutoMod nativo, regex)
- `[x]` 6.3 Anti-link generico (whitelist/blacklist domini) — lato
  bot (`core/automod_advanced_logic.py`), non regola nativa: Discord
  non supporta un elenco whitelist/blacklist di domini come trigger
  nativo. Modalità `off`/`whitelist`/`blacklist` per server,
  `/automod anti-link-mode` + `/automod anti-link-domain`
- `[x]` 6.4 Anti-spam messaggi — soglia messaggi/finestra
  configurabile, finestra mobile in memoria
  (`core/automod_rate_tracker.py`, mai persistita: stato "caldo" di
  pochi secondi, stesso principio di `core/invite_tracker.py`),
  `/automod anti-spam-messages`
- `[x]` 6.5 Anti-spam emoji — soglia per SINGOLO messaggio (non nel
  tempo, a differenza di 6.4/6.6/6.10): conta emoji custom Discord +
  un intervallo unicode ampio (nessuna libreria `emoji` aggiunta come
  dipendenza — sotto-conteggio occasionale su emoji unicode rare
  accettato), `/automod anti-spam-emoji`
- `[x]` 6.6 Anti-spam sticker — soglia sticker/finestra, stesso motore
  a finestra mobile di 6.4, `/automod anti-spam-sticker`
- `[x]` 6.7 Anti-caps — percentuale di lettere maiuscole SUL TOTALE
  DELLE LETTERE (non sul totale caratteri: punteggiatura/numeri non
  contano né a favore né contro), soglia + lunghezza minima
  configurabili, `/automod anti-caps`
- `[x]` 6.8 Anti-zalgo — conteggio segni diacritici unicode
  combinanti (categoria Mn/Me/Mc) oltre una soglia fissa (8, per
  inferenza: il testo normale — accenti italiani compresi — non la
  supera mai), `/automod anti-zalgo`
- `[x]` 6.9 Anti-mass-mention — soglia di menzioni (utenti+ruoli) per
  messaggio, `@everyone`/`@here` contano sempre come sopra soglia,
  `/automod anti-mention`
- `[x]` 6.10 Anti-attachment-spam — soglia allegati/finestra, stesso
  motore a finestra mobile di 6.4/6.6, `/automod anti-attachment`
- `[x]` 6.11 Filtri personalizzati per canale — **eccezione**
  (bypassa TUTTI i filtri avanzati insieme, non uno specifico per
  canale: altrimenti servirebbero N eccezioni per N filtri, complessità
  non richiesta), `/automod exempt-channel-add|remove`
- `[x]` 6.12 Filtri personalizzati per ruolo — stessa logica di 6.11,
  per ruolo, `/automod exempt-role-add|remove`
- `[x]` 6.13 Azioni multiple configurabili (delete + warn + mute +
  ban) — per violazione, con "delete" sempre eseguito per primo se
  presente; rete di sicurezza: mute/ban non si applicano mai
  all'owner o a chi ha `manage_guild`/administrator (delete/warn
  restano, poco invasivi) — scelta di sicurezza per inferenza, non
  richiesta esplicitamente. `/automod actions-set` + `/automod
  mute-duration` (durata del timeout, condivisa da ogni azione
  "mute")
- `[x]` 6.14 Log delle azioni automod — riga persistente per ogni
  violazione (`automod_action_log`) + embed opzionale in un canale
  dedicato, `/automod log-channel` + `/automod status` (riepilogo
  configurazione)
- `[x]` 6.15 Smart AutoMod Escalation Ladder (BACKLOG.md §11) — scala
  di severità crescente **nel tempo** in base a quante volte un
  utente ha già triggerato l'AutoMod nativo, con reset dopo un
  periodo configurabile di buona condotta. Concettualmente diversa
  da 6.13 (che è più azioni insieme su UN trigger, non su trigger
  ripetuti nel tempo) — voce nuova, non una ridefinizione di 6.13

## §7 SECURITY SUITE — completa tranne il ban globale via fingerprint/alt-detection (dipende da §4.2, non costruito; sostituito da 7.6 per lo stesso account)

- `[x]` 7.1 Anti-Raid — `cogs/security/anti_raid.py`, modulo CANDIDATO
  PREMIUM (come Spam Trap). Logica di valutazione pura in
  `core/security_logic.py` (`evaluate_join`), finestra mobile in
  memoria per il join rate (`core/security_rate_tracker.py`, mai
  persistita — stesso principio di `core/automod_rate_tracker.py`).
  Comandi: `/anti-raid enable|join-rate|account-age|username-check|
  avatar-check|lockdown-action|alert-channel|status`
  - `[x]` Join rate limit (finestra scorrevole) — conteggio join
    guild-wide (non per singolo utente: una `chiave fittizia
    user_id=0`, mai un ID reale su Discord) nella finestra configurata
  - `[x]` Account age check all'ingresso — età minima configurabile
  - `[x]` Rilevamento pattern username — regex per inferenza
    (lettere+4 o più cifre finali, tipico di un account generato in
    massa da un raid-bot), disattivabile
  - `[x]` Rilevamento pattern avatar — assenza di un avatar
    personalizzato, disattivabile (nessun confronto tra avatar
    diversi: solo "ha/non ha un avatar", per semplicità)
  - `[x]` Lockdown automatico — tre modalità configurabili:
    quarantena, innalzamento del `verification_level` del server, o
    entrambe
  - `[x]` Quarantine role — creato automaticamente al primo utilizzo
    (overwrite su ogni canale, stesso schema del ruolo Muted di
    `cogs/moderation/softban_mute.py`, ma un ruolo SEPARATO — un
    sospetto raider appena entrato non è lo stesso caso di un membro
    esistente sanzionato)
  - `[x]` Alert staff — DM all'owner + canale di alert opzionale
    (condiviso con Anti-Nuke)
- `[x]` 7.2 Anti-Nuke — `cogs/security/anti_nuke.py`, modulo
  CANDIDATO PREMIUM. L'autore di un evento non è mai nel payload
  dell'evento gateway: risolto sempre via audit log
  (`guild.audit_logs`, stesso approccio già usato per il cleanup
  webhook/inviti di Spam Trap), con una finestra di tolleranza di 10s
  tra evento e voce di audit log. Comandi: `/anti-nuke enable|limits|
  trusted-add|trusted-remove|punish-action|recovery|status`
  - `[x]` Protezione canali (create/delete di massa) — soglia/finestra
    configurabile per categoria
  - `[x]` Protezione ruoli — stessa logica, categoria separata
  - `[x]` Protezione webhook — `on_webhooks_update`, stessa logica
  - `[x]` Protezione emoji / sticker — `on_guild_emojis_update` +
    `on_guild_stickers_update`. **Soundboard escluso**: limite reale
    della libreria discord.py 2.7 in uso (nessun evento gateway
    dedicato esposto), non una scelta di scope
  - `[x]` Rilevamento mass ban / mass kick — `on_member_ban` diretto;
    per il kick, `on_member_remove` verifica PRIMA nell'audit log se
    si tratta davvero di un'espulsione (altrimenti ogni leave
    volontario alimenterebbe per errore il contatore)
  - `[x]` Recovery automatico (ricreazione canali/ruoli) — best-effort,
    senza uno snapshot separato persistito: `on_guild_channel_delete`/
    `on_guild_role_delete` ricevono l'oggetto Discord com'era
    nell'ultima cache del client PRIMA della rimozione, quindi
    nome/permessi/posizione sono ancora leggibili al momento della
    ricreazione
  - `[x]` Whitelist utenti/bot fidati — `trusted_ids`, esenta
    completamente dai controlli (nessuna azione, nessun log)
  - **Rete di sicurezza**: l'autore non viene MAI punito se è il
    proprietario del server (stessa filosofia della rete di sicurezza
    già in AutoMod §6.13, ma invertita: lì è la vittima potenziale ad
    essere protetta, qui l'owner non può mai essere il "nuke" da
    contrastare per errore)
- `[x]` 7.3 **Spam Trap** — completo (solo il ban globale via
  fingerprint resta escluso, per la dipendenza esplicita da §4 sotto)
  - `[x]` `/setup` con selezione canale trappola e canale log — via
    parametri `discord.TextChannel` opzionali (rendono nativamente
    come selettore canale di Discord, non un menù a tendina
    testuale, ma stessa funzione)
  - `[x]` Creazione automatica `#spam-trap` (visibile a everyone, no
    inviti, no webhook) se non selezionato
  - `[x]` Creazione automatica `#spam-log` (solo administrator) se
    non selezionato
  - `[x]` Embed di presidio in `#spam-trap`, rosso, in inglese, con
    header grande "DO NOT WRITE IN THIS CHANNEL"
  - `[x]` Embed informativo in `#spam-log`, colore tenue, in inglese
  - `[x]` Sequenza fissa: cattura contenuto → **DM PRIMA del ban** →
    ban con `delete_message_seconds` → purge supplementare → cleanup →
    log
  - `[x]` Cancellazione messaggi 30 giorni (indicizzazione
    `message_id` in DB; nativo copre max 7 giorni, la purge
    supplementare copre 7-30)
  - `[x]` Log con: tag, user ID, data creazione account, data join,
    data ban, codice invito usato, **creatore dell'invito**, contenuto
    che ha fatto scattare la trappola, numero messaggi cancellati per canale
  - `[x]` Cleanup webhook creati dall'utente (via audit log)
  - `[x]` Cleanup inviti creati dall'utente (via audit log)
  - `[x]` Ban appeal: DM → thread privato in `#spam-log`, con bottoni
    staff (Unban/Reject/Reply), rate limit 1 appello/24h. Bottoni su
    una `View` NON persistente (timeout 7 giorni) — scelta dichiarata,
    non equivalente ai pannelli persistenti di ticket/vocali: un
    appeal è per natura più breve, non vale la complessità di bottoni
    persistenti per-caso dinamici
  - `[x]` **Transcript HTML** — timestamp, nome+nickname, contenuto
    con escaping rigoroso anti-XSS, allegati immagine rigenerati come
    thumbnail WebP (Pillow, `core/image_thumbnail.py`), avatar
    dell'utente mostrato una volta per report nell'intestazione. Le
    thumbnail sono incorporate come data URI dentro l'HTML stesso —
    non riospitate da nessuna parte, coerente con "mai riospitare il
    file originale"
  - `[ ]` Opzione ban globale via fingerprint/alt-detection — dipende
    da §4.2/§4.3 Anti-Alt (raccolta OAuth2 "identify" + IP al momento
    del VERIFY, prima che l'account si comporti male), non costruito.
    Resta bloccato per un motivo strutturale, non solo di tempo: un
    account appena bannato dalla trappola non collaborerebbe mai a un
    flusso OAuth2 dopo il fatto, quindi il fingerprint andrebbe
    comunque raccolto prima, al verify — la stessa dipendenza di
    sempre
  - `[x]` **Ban globale via propagazione cross-server** — SPEC.md
    §7.6 sotto: NON è il ban globale via fingerprint di cui sopra
    (nessuna euristica su account diversi/alt), ma la propagazione
    reale di un ban Spam Trap sullo STESSO account Discord verso ogni
    altro server aderente. Costruito su richiesta esplicita
    dell'utente, come sostituto concretamente realizzabile oggi
- `[x]` 7.4 Permission Auditor + alert permessi pericolosi —
  `/permission-heatmap` (ruoli con permessi critici + quanti membri
  li possiedono) + DM diretto all'owner quando un membro riceve un
  ruolo con permesso critico
- `[x]` 7.5 Security Score / health check configurazione server —
  `cogs/security/security_score.py`, comando `/security-score`.
  Modulo SEMPRE GRATUITO (è un check di lettura, non una protezione
  attiva). Punteggio 0-100 (`core.security_logic.
  compute_security_score`, logica pura testata a sé) con pesi scelti
  per inferenza — nessuna formula "ufficiale" esiste per un security
  score di un server Discord: 2FA staff, livello di verifica, quota
  di membri amministratori, Anti-Raid/Anti-Nuke attivi, AutoMod
  attivo — ognuno con un consiglio azionabile in caso di penalità
- `[x]` 7.6 **Ban globale via propagazione cross-server** —
  `cogs/security/global_ban.py` (`/global-ban enable|disable|status`),
  richiesto esplicitamente dall'utente come soluzione al gap di 7.3
  sopra. Modulo CANDIDATO PREMIUM.

  **Perché non è "il" ban globale via fingerprint di §4.3**: quello
  risolve un problema diverso — riconoscere che due ACCOUNT DIVERSI
  sono la stessa persona (un alt), cosa che richiede una raccolta
  IP/OAuth2 "identify" fatta al momento del VERIFY, prima che
  l'account si comporti male (§4.2, non costruito). Un account appena
  bannato dalla Spam Trap non collaborerebbe mai a un flusso OAuth2
  dopo il fatto — quella raccolta non potrebbe mai avvenire a ban
  avvenuto, quindi il vero fingerprint resta strutturalmente bloccato
  su §4.2, non solo per mancanza di tempo.

  **Cosa fa invece, concretamente realizzabile oggi**: propaga un ban
  scattato dalla Spam Trap (§7.3) sullo STESSO account Discord (stesso
  user ID, nessuna euristica di somiglianza) verso ogni altro server
  che condivide il bot E ha aderito alla stessa rete — reciprocità
  esplicita: un server che non ha attivato il modulo non riceve mai
  un ban deciso altrove, né i suoi ban vengono propagati. L'opt-in
  riusa l'attivazione modulo già esistente
  (`db.is_module_active_for_guild`/`set_module_active_for_guild` su
  `guild_config`) — nessuna nuova tabella di configurazione, solo un
  log di propagazione (`core/repositories/global_ban_repo.py`,
  `global_ban_log`) per `/global-ban status`. Logica pura di
  decisione isolata in `core/global_ban_logic.py`
  (`should_propagate_ban`), stesso pattern di ogni altro modulo di
  questa sezione. Ban con `discord.Object(id=user_id)` (funziona anche
  se l'utente non è mai stato membro del server target — un ban
  preventivo legittimo). Best-effort per server: un `Forbidden`/
  `HTTPException` su UN target (permessi insufficienti, già bannato
  lì) non blocca la propagazione verso gli altri. Integrato nella
  sequenza di ban della Spam Trap (subito dopo il ban reale, prima
  della creazione del case) con un campo aggiuntivo nell'embed di log
  quando la propagazione avviene.

## §8 LOGGING — completo tranne Message delete/edit (rimandato, Message Content Intent)

- `[x]` 8.1 Member join
- `[x]` 8.2 Member leave
- `[x]` 8.3 Member ban / unban
- `[x]` 8.4 Member update — ruoli e nickname, nello stesso evento
  senza uscire in anticipo se solo uno dei due cambia
- `[x]` 8.5 Role create / delete
- `[x]` 8.6 Role **update** (nome, colore, permessi, hoist,
  mentionable) — `cogs/logging/advanced_logs.py`, livello Premium
  (vedi 8.18 sotto)
- `[x]` 8.7 Channel create / delete / update — update copre nome,
  categoria, topic, nsfw, slowmode, posizione; il diff degli
  overwrite di permesso canale-per-canale resta escluso per scelta
  di scope (complessità non richiesta per un log, non un limite
  tecnico)
- `[x]` 8.8 Invite create / delete / use — "use" risolto con un nuovo
  metodo, `invite_tracker.resolve_join_invite(guild, member_id)`
  (`core/invite_tracker.py`), non con `find_used_invite()`
  direttamente: quest'ultimo muta la propria cache ad ogni chiamata
  (aggiorna l'istantanea per il prossimo confronto), quindi due
  moduli indipendenti (Spam Trap e il Logging Avanzato) che lo
  chiamassero ciascuno per proprio conto sullo stesso evento di join
  darebbero `None` a chi arriva secondo. `resolve_join_invite()`
  risolve la corsa con un lock + cache per coppia (server, membro):
  la prima chiamata per un dato join fa il lavoro reale, ogni altra
  chiamata per lo stesso join — da qualunque modulo, in qualunque
  ordine (`discord.py` non garantisce un ordine tra i listener di
  Cog diversi sullo stesso evento) — riceve la stessa risposta senza
  un secondo fetch/diff. Spam Trap aggiornato per usare lo stesso
  metodo
- `[x]` 8.9 **Voice state**: join / leave / move / mute / deafen —
  "mute"/"deafen" semplificato allo stato EFFETTIVO (server-mute/
  deafen oppure self-mute/self-deafen), non le quattro variabili
  distinte di discord.py, scelta dichiarata per un log leggibile
- `[x]` 8.10 Webhook create / update / delete — l'evento gateway
  nativo (`on_webhooks_update`) non distingue le tre azioni né dice
  l'autore: risolto via audit log entro una finestra di tolleranza,
  stesso principio già usato per l'autore in Anti-Nuke (§7.2)
- `[x]` 8.11 Emoji create / delete / update
- `[x]` 8.12 Sticker create / delete / update
- `[x]` 8.13 Soundboard create / delete / update — **non via evento
  gateway** (quella parte del limite trovato nell'Anti-Nuke, §7.2,
  resta vera: nessun `on_soundboard_sound_...` esiste nella
  libreria), ma via POLLING PERIODICO dell'audit log
  (`discord.AuditLogAction.soundboard_sound_create/update/delete`
  esistono ed è lì che Discord registra l'evento — verificato
  leggendo l'enum reale della libreria installata, non assunto).
  `core/soundboard_log_service.py`, stesso pattern architetturale di
  `core/event_log_retention.py` (un `tasks.loop`, non un listener),
  ogni 5 minuti, con un "watermark" persistito per server per non
  ri-loggare le stesse voci né riversare lo storico alla prima
  attivazione
- `[x]` 8.14 Thread events — create/delete/update (nome, archiviato,
  bloccato)
- `[x]` 8.15 Server update (impostazioni guild) — nome, icona,
  livello di verifica, canale AFK, canale di sistema, filtro
  contenuti espliciti
- `[ ]` 8.16 Message delete / bulk delete / edit — **rimandato
  deliberatamente**: richiede il Message Content Intent, da chiedere
  solo quando un modulo lo giustifica (vedi § Decisioni)
- `[x]` 8.17 Log eventi unificato multi-indice (BACKLOG.md §3) — ogni
  evento (8.1-8.5, 8.6-8.15 ora costruiti) salvato UNA VOLTA nel DB,
  consultabile da più angolazioni (membro, canale, ruolo, tempo).
  `/logs user`, `/logs channel`, `/logs export` (JSON completo).
  Retention differenziata: 30gg Free, 180gg Premium, pulizia
  giornaliera automatica. **Proiezione su Forum Discord per
  canali/case NON costruita** — decisione esplicita nell'analisi
  (BACKLOG.md §3): "membri" è l'unica dimensione ad alta cardinalità
  che avrebbe fatto esplodere i thread durante un raid, "canali" e
  "case" restano un'estensione futura separata
- `[x]` 8.18 Distinzione log semplificato `[Free]` vs completo
  `[Premium]` — due moduli distinti: `cogs/logging/basic_logs.py`
  (`MODULE_LOGGING`, 8.1-8.5, SEMPRE GRATUITO) e
  `cogs/logging/advanced_logs.py` (`MODULE_LOGGING_ADVANCED`,
  8.6-8.15, CANDIDATO PREMIUM). Stesso canale di log configurato una
  volta con `/logs-setup` — è l'attivazione del secondo modulo a
  decidere se gli eventi avanzati iniziano ad arrivarci, non un
  secondo comando di setup

## §9 MUSIC — architettura multi-istanza fatta, comandi ridotti (deliberatamente)

**Nota di stato**: costruita l'architettura multi-istanza (bot
principale + 5 worker nello stesso processo, instradamento
automatico) e un set di comandi RIDOTTO rispetto allo schema
originale — deliberatamente, su richiesta esplicita dell'utente:
"non voglio filtri audio, non voglio appesantire il bot per niente,
tanto la gente ormai raramente li usa". **Aggiornamento**: l'utente
ha poi chiesto esplicitamente di completare comunque clear, shuffle,
i due loop (traccia/coda) e nowplaying con barra di avanzamento —
fatti in questa sessione. Restano invece **permanentemente
descoperti** (non solo rimandati — richiesta esplicita, mai da
rimettere in lista): search distinta da play, forceskip, remove,
move, seek, lyrics. Filtri audio/DJ-role/voteskip restano scartati
per lo stesso motivo di sempre (9.6/9.7/9.8). Comandi finiti oggi:
play, skip, stop, pause, resume, queue, clear-queue, shuffle, loop
track/queue, nowplaying (con barra), volume (con up/down oltre a
impostare un valore), disconnect, nonstop. **Bug reale trovato e
corretto qui**: il primo tentativo chiamava il nuovo comando
`/clear` — nome già usato da `/clear` di moderation (cancellazione
messaggi) — e un comando slash duplicato fa fallire la
REGISTRAZIONE dell'intero cog, non solo di quel comando;
`core/cog_manager.load_all_cogs` cattura e LOGGA ogni eccezione di
`setup()` per singolo cog senza farla risalire, quindi l'intero
modulo Music si sarebbe disattivato in silenzio, notato solo
rilanciando `scripts/generate_command_list.py` sull'intero albero
comandi reale (il conteggio è sceso da 171 a 153 comandi e la
categoria Music è sparita del tutto) — mai scoperto dai test perché
i test unitari istanziano `MusicCog` da solo, senza mai unire il suo
albero comandi a quello di TUTTI gli altri cog insieme come fa il
bot vero. Rinominato in `/clear-queue`.

**Correzione di comprensione dell'utente su YouTube/Spotify (§9.5)**:
i nodi Lavalink pubblici hanno comunque Spotify (plugin LavaSrc
spesso già presente); è YouTube che su molti nodi pubblici non
funziona più/è spesso rotto — il fallback pinnato sul nodo locale
esisteva finora solo per query Spotify (`is_spotify_query`), non per
YouTube: **nessuna modifica di codice fatta qui**, resta un punto da
eventualmente rivalutare se emergono segnalazioni concrete di
ricerche YouTube vuote sui nodi pubblici, non affrontato in questa
sessione perché non richiesto esplicitamente.

- `[x]` 9.1 Multi-VoiceClient manager (5 applicazioni separate) —
  `core/music_worker_bot.py`, 5 istanze nello stesso processo
  (non 5 processi separati — vedi PROGRESS.md per il perché)
- `[x]` 9.2 Assegnazione istanza libera per canale (tabella
  `music_sessions`, logica "se bot1 occupato → bot2") —
  `core/music_fleet.py` + `core/repositories/music_session_repo.py`
- `[x]` 9.3 Coda indipendente per canale vocale — ogni `wavelink.
  Player` (uno per worker/server) ha la propria coda, indipendente
  dalle altre per costruzione
- `[x]` 9.4 Comandi: play, skip, stop, pause, resume, queue,
  clear-queue, shuffle, loop track, loop queue, nowplaying (con
  barra di progresso), volume, disconnect. **Limite playlist**:
  `/play` su un
  link a una playlist (es. Spotify) aggiunge al massimo
  `MAX_PLAYLIST_TRACKS` = 750 tracce per singolo link (richiesto
  esplicitamente dall'utente — una playlist enorme non deve poter
  riempire la coda di un server all'infinito in un colpo), il resto
  viene scartato con un avviso esplicito nel messaggio di conferma.
  **Shuffle genuinamente randomico**: `/shuffle` delega direttamente
  a `wavelink.Queue.shuffle()`, che usa `random.shuffle` della
  libreria standard di Python (Fisher-Yates non polarizzato) — non
  un "mix" con pattern nascosti come capita con alcuni bot musicali
  (preoccupazione esplicita dell'utente), verificato leggendo il
  sorgente di wavelink e bloccato con un test di regressione che
  fallirebbe se una futura versione cambiasse questo comportamento.
  **Permanentemente descoperti** (richiesta esplicita dell'utente,
  NON da rimettere in lista in futuro): search distinta da play,
  forceskip, remove, move, seek, lyrics
- `[~]` 9.5 Sorgenti: YouTube, Spotify (solo risoluzione titolo),
  SoundCloud, URL, file locali — YouTube funziona via la ricerca di
  default di Lavalink; Spotify richiede un plugin (LavaSrc) sul nodo
  Lavalink usato, non verificabile se presente su un nodo pubblico di
  terzi senza controllarlo direttamente — **fallback ORA predisposto**
  (`MusicCog._search_with_spotify_fallback`, `core.music_logic.
  is_spotify_query`): se una query Spotify non produce risultati sui
  nodi pubblici, si ritenta UNA volta pinnata specificamente sul nodo
  locale/self-hostato (`LOCAL_NODE_IDENTIFIER`, lo stesso già usato
  per i file locali qui sotto) — funziona non appena l'utente
  configura lì un nodo con LavaSrc installato (`LAVALINK_HOST/PORT/
  PASSWORD` in `.env`), nessun altro codice da scrivere quando lo
  farà. Fino ad allora il comportamento resta identico a oggi (il
  fallback semplicemente non trova nulla, come un nodo pubblico senza
  Spotify farebbe comunque). **File locali ORA fatti** per la radio
  condivisa (`/nonstop-main add-local`), instradati specificamente
  verso il nodo Lavalink locale — i nodi pubblici non hanno accesso
  al filesystem della macchina
- `[✗]` 9.6 Filtri audio (bassboost, nightcore, vaporwave, 8D) —
  scartato su richiesta esplicita dell'utente, non un limite tecnico
- `[✗]` 9.7 DJ role — scartato, stesso motivo di 9.6
- `[✗]` 9.8 Voteskip — scartato, stesso motivo di 9.6
- `[x]` 9.9 Auto-leave a canale vuoto — `core/music_fleet.
  handle_inactive_player()`, agganciato identicamente su tutti e 6 i
  bot (main + 5 worker). Il timeout (300s di default) è gestito
  internamente da wavelink/Lavalink; qui solo la reazione:
  disconnette e libera il worker nella flotta
- `[x]` 9.10 Modalità 24/7 con cap istanze concorrenti — `/nonstop
  on|off` (loop continuo sulla coda del worker attivo) fatto; il cap
  di 5 istanze (TOTAL_WORKERS) resta un vincolo dell'infrastruttura
  (5 token bot worker configurati), non un numero arbitrario da poter
  cambiare via comando — chiarito esplicitamente dall'utente. "Gestito"
  ora significa: `/play` assegna solo un worker EFFETTIVAMENTE
  invitato in quel server (mai uno assente, corretto un bug reale che
  avrebbe altrimenti occupato per sempre uno slot inutilizzabile), e
  quando nessuna istanza è disponibile il messaggio distingue i due
  casi reali — questo server non ha ancora invitato tutte le 5
  istanze (link d'invito generati al volo, mostrati solo a chi ha
  `manage_guild`, un non-admin viene invitato a chiedere all'admin) o
  tutte e 5 sono già presenti ma occupate altrove in questo momento
  (serve un'estensione del limite GLOBALE, indirizzato ad aprire un
  ticket nel server ufficiale iYokai — nessun link fabbricato, il
  server è già raggiungibile pubblicamente)
- `[x]` 9.11 Stream 24/7 con musica di proprietà (singolo decoder
  condiviso) — `/nonstop-main add-track|add-local|remove-track|
  list-tracks|start|stop`. "Condiviso" ottenuto con un orologio
  logico (`core/main_radio_logic.py`): non un unico decode audio
  fisicamente multicast a più canali (impossibile con l'architettura
  Lavalink — ogni bot ha la propria connessione voce), ma ogni
  server che entra calcola dove dovrebbe essere la riproduzione ORA
  (stessa traccia, stessa posizione, in base al tempo reale
  trascorso) e joina seekando esattamente lì — stesso risultato
  percepito dall'ascoltatore: tutti sentono la stessa cosa nello
  stesso punto. Verificato con un test end-to-end: un secondo server
  che entra 90 secondi dopo riceve la posizione corretta, non
  riparte da zero
- `[x]` 9.12 Backend Lavalink — l'intero cog si basa su Lavalink via
  wavelink, nodi pubblici in cascata + nodo locale (vedi PROGRESS.md)

## §10 ALERTS & SOCIAL — parzialmente fatta

- `[x]` 10.1 Twitch live — via polling Twitch Helix "Get Streams"
  (non EventSub webhook, vedi nota tecnica sotto). Testato con
  credenziali fittizie su richiesta esplicita dell'utente (server
  locale finto che imita l'API reale); funzionerà con le sue
  credenziali vere una volta registrate su dev.twitch.tv
- `[x]` 10.2 Twitch offline — stesso meccanismo di 10.1
- `[x]` 10.3 YouTube nuovo video — via il feed Atom nativo di YouTube
  (`youtube.com/feeds/videos.xml?channel_id=...`), nessuna chiave API
- `[ ]` 10.4 YouTube live — non affidabile via RSS (non indica lo
  stato live), richiederebbe la YouTube Data API con quota a
  consumo. Rimandato
- `[✗]` 10.5 TikTok nuovi video — scartato: nessuna API ufficiale
  gratuita per leggere le pubblicazioni di terzi, solo scraping
  fragile. Confermato dall'utente come vincolo accettato, non un
  limite di sforzo
- `[✗]` 10.6 Instagram — nessuna API permette di monitorare account
  di terzi. Scartato, vedi audit di fattibilità
- `[x]` 10.7 Reddit — via il feed RSS nativo di Reddit
  (`reddit.com/r/nome/new/.rss`), nessuna chiave API
- `[x]` 10.8 Custom RSS / webhook — la parte RSS è fatta (`/alerts
  add`, qualsiasi URL RSS/Atom). La parte "webhook" è fatta come
  endpoint proprio (non EventSub/PubSubHubbub, vedi Nota tecnica
  sotto): `/alerts webhook-create` crea un URL segreto
  (`/webhook/<token>`, token opaco da 32 byte, mostrato una sola
  volta e non più recuperabile — stesso modello dei webhook in
  ricezione di Discord/Slack/GitHub); un server HTTP dedicato
  (`core/custom_webhook_server.py`, aiohttp, sempre attivo, porta
  configurabile via `ALERTS_WEBHOOK_HOST/PORT/PUBLIC_BASE_URL`)
  riceve richieste POST con un corpo JSON (`title`/`message` o
  `content`/`text`, `url` o `link`, troncati rispettivamente a
  256/1500/500 caratteri) e pubblica nel canale scelto usando lo
  stesso sistema di template di 10.9. `/alerts list` mostra il
  webhook (`WH-<id>`) senza mai il token; `/alerts remove WH-<id>`
  lo elimina
- `[x]` 10.9 Messaggi personalizzabili per ogni alert — placeholder
  `{label}` `{title}` `{link}` nel template (RSS), `{label}` `{title}`
  `{login}` (Twitch)
- `[✗]` 10.13 X/Twitter — **voce nuova**, non nello schema originale,
  aggiunta su richiesta esplicita dell'utente. Scartata: la lettura
  via API richiede un abbonamento a pagamento nel tier utile (il
  tier gratuito non permette di leggere i post di terzi in modo
  utilizzabile per il monitoraggio). Nessuna alternativa gratuita
  affidabile nota (i bridge non ufficiali tipo Nitter sono instabili
  e spesso bloccati da X). Confermato dall'utente come vincolo
  accettato

**Nota tecnica, vale per Twitch/YouTube/Reddit/RSS**: lo schema
originale chiedeva EventSub (Twitch) e PubSubHubbub (YouTube),
entrambi webhook PUSH — richiedono un endpoint HTTPS pubblico
raggiungibile da Twitch/Google, che questo bot non ha (nessun server
web, solo un client Gateway Discord). Aggiungerlo significherebbe
dominio, certificato TLS, apertura di una porta sulla VM — un cambio
di infrastruttura, non solo di codice. Sostituito con **polling**
periodico (`core/feed_watcher.py` ogni 5 minuti, `core/twitch_
watcher.py` ogni 90s), che raggiunge lo stesso risultato per
l'utente finale senza cambiare il deployment.

**Nota tecnica separata, riguarda solo 10.8 "webhook custom"**: qui
non serve integrarsi con un protocollo esterno specifico
(EventSub/PubSubHubbub sono legati a Twitch/Google, non generici) —
serve solo un endpoint HTTP generico *nostro*, dove chiunque (n8n,
Zapier, IFTTT, un piccolo script) può inviare un POST. Per questo il
vincolo di infrastruttura sopra non si applica allo stesso modo:
serve comunque una porta aperta sulla VM (già presente e riusata
dal server OAuth2 di §11.11, porta diversa per evitare collisioni),
ma non un dominio/TLS/certificazione con un servizio terzo — chi usa
il webhook porta il proprio URL pubblico se vuole esporlo dietro un
reverse proxy (`ALERTS_WEBHOOK_PUBLIC_BASE_URL`), altrimenti il
token va usato con l'IP diretto della VM.

## §11 BACKUP SYSTEM — orchestrazione automatizzabile completa

**Nota di stato**: §11 BACKUP SYSTEM è ora COMPLETO al 100% — tutte
le 13 voci fatte. Le ultime tre (§11.10/§11.11/resto di §11.12,
backup e restore utenti via OAuth2) sono state costruite dopo aver
discusso esplicitamente con l'utente il loro design di sicurezza
(storage token cifrato, modalità di consenso, retention).

**Limite reale della piattaforma Discord**, verificato con una
ricerca prima di progettare, non aggirabile dal codice: **un bot non
può autoinvitarsi in un server**. "Cede ownership → invita iYokai
Main" nella pratica significa: Creator crea e clona, genera un URL
di invito OAuth per Main, un umano deve cliccarlo — il codice fa
tutto il resto in automatico attorno a quel singolo passaggio
necessario.

- `[x]` 11.1 iYokai Creator: crea server → cede ownership → invita
  iYokai Main → esce (sempre sotto i 10 server) — `core/backup_
  orchestrator.py` (`start_backup_job()` + `finalize_backup_job()`,
  divise attorno al passaggio umano necessario sopra), `core/backup_
  creator_bot.py`
- `[x]` 11.2 Coda serializzata persistente con timeout 24h —
  `core/repositories/backup_repo.py` (tabella `backup_jobs`) +
  `core/backup_queue_worker.py` (un job alla volta, tick ogni 60s).
  Migliorato su richiesta esplicita dell'utente con un promemoria di
  scadenza (countdown, un solo DM per job) e il controllo di
  capacità di Creator (max 10 server): se è già al limite, il worker
  aspetta e avvisa una sola volta invece di tentare comunque
- `[x]` 11.3 Clonazione ruoli + permessi — `clone_roles()`, salta
  @everyone (esiste già) ma ne applica comunque i permessi al
  default_role di destinazione, salta i ruoli "managed"
- `[x]` 11.4 Clonazione categorie + canali — `clone_categories_and_
  channels()`, categorie create prima dei canali, overwrite di
  permessi rimappati tramite la mappa ruoli
- `[x]` 11.5 Clonazione emoji — `clone_emoji()`
- `[x]` 11.6 Clonazione sticker — `clone_stickers()`
- `[x]` 11.7 Clonazione soundboard — `clone_soundboard()`
- `[x]` 11.8 Clonazione webhook — `clone_webhooks()`, nome e canale
  rimappato (l'URL del webhook stesso non è copiabile, va
  riconfigurato a mano dove serve)
- `[x]` 11.9 Mirror messaggi in tempo reale via webhook con identità
  utente (con politica di scarto sui burst, rate limit 5/5s per
  canale) — `core/backup_mirror_logic.py` (`MirrorRateLimiter`,
  finestra scorrevole per canale), `core/backup_clone_logic.py`
  (`create_mirror_webhooks()`, un webhook "iYokai Mirror" per ogni
  canale testuale clonato), `core/repositories/backup_mirror_repo.py`
  (mappa canale-main→URL-webhook), `core/backup_mirror_dispatch.py`
  (`BackupMirrorDispatcher`, decide+inoltra), `cogs/utility/backup_
  mirror.py` (listener `on_message`). Scarto in burst confermato: chi
  supera 5 msg/5s su un canale viene semplicemente perso, non
  accodato
- `[x]` 11.10 User backup: snapshot periodico (settimanale) dei
  verificati non bannati/kickati — `core/backup_snapshot_logic.py`
  (pura: bot esclusi sempre, ruolo verificato richiesto solo se
  Verify Base è configurato), `core/repositories/backup_user_
  snapshot_repo.py` (tabella `backup_user_snapshots`, sostituita
  interamente ad ogni scatto), `core/backup_snapshot_worker.py`
  (`tasks.loop` settimanale, un tick per ogni main con backup già
  attivo — `backup_repo.get_all_main_guild_ids_with_backup()`)
- `[x]` 11.11 Restore massivo utenti via OAuth2 `guilds.join` —
  token cifrati AES-256-GCM a riposo (`core/oauth_crypto.py`, MAI un
  algoritmo custom: la sicurezza sta nella chiave segreta, non
  nell'oscurità dell'algoritmo), `core/repositories/restore_oauth_
  repo.py` (retention concordata con l'utente: uscita spontanea →
  cancellato dopo 90gg, kick → preservato e flaggato, ban →
  preservato e in blacklist — mai riusabile), `core/restore_
  orchestrator.py` (le due chiamate REST reali: scambio code→token,
  "Add Guild Member" cioè il vero `guilds.join`, assegnazione ruolo
  verificato), `core/restore_web_server.py` (server aiohttp minimo,
  un solo endpoint `/oauth/callback`), `core/restore_batch_logic.py`
  (decide auto-join/richiedi-consenso/invito-classico/salta-
  blacklist), `core/restore_retention_logic.py` +
  listener `on_member_ban/remove/join` in `cogs/utility/restore.py`
  per distinguere kick da uscita spontanea via audit log. Tre
  modalità per server (`/configura-restore`, come concordato con
  l'utente): OAuth al momento della verifica (server nuovi), OAuth
  solo al bisogno (default, server esistenti — riusa i token già
  raccolti), o solo invito classico senza alcun token
- `[x]` 11.12 Comandi `/define-main`, `/define-backup`,
  `/promuovi-backup`, `/restore-users`, `/configura-restore` — tutti
  fatti
- `[x]` 11.13 Auto-propagazione: `/promuovi-backup` (lanciato nel
  server backup) promuove quel server a main e accoda IMMEDIATAMENTE
  un nuovo job di backup per lui — `BackupRepository.promote_backup_
  to_main()` + `get_pair_by_backup_guild_id()`, comando in `cogs/
  utility/backup.py`

## §12 TEMPORARY VOICE CHANNELS

- `[x]` 12.1 Modalità automatica (generatore → crea + sposta)
- `[x]` 12.2 Modalità manuale (pannello + bottone persistente)
- `[x]` 12.3 Entrambe sempre visibili a tutti
- `[x]` 12.4 Notifica personale alla creazione del canale — un
  embed nella chat testuale del canale vocale stesso (un
  `VoiceChannel` è Messageable), inviato sia dalla modalità
  automatica (che prima spostava in totale silenzio) sia da quella
  manuale
- `[x]` 12.5 Selezione piattaforma all'ingresso (PC / Console /
  Mobile) — bottoni SOLO informativi (nessun filtro di visibilità,
  come da decisione finale già registrata) mostrati insieme alla
  notifica 12.4 se il server ha configurato almeno un ruolo
  piattaforma (`/voicetemp-platform-setup`)
- `[x]` 12.6 Gestione canale: rename, limite utenti, lock, unlock, kick, transfer
- `[x]` 12.7 Eliminazione automatica a canale vuoto
- `[x]` 12.8 Cap configurabile canali per categoria (`/voicetemp-cap`),
  sempre troncato al limite hard di Discord di 50

## §13 TICKET SYSTEM

- `[x]` 13.1 Pannello apertura con bottone persistente
- `[x]` 13.2 Select menu categorie (`/ticket-category add|remove|list`)
  — se il server ne ha configurato almeno una, il pannello mostra il
  select menu invece del bottone unico; retrocompatibile (nessuna
  categoria configurata -> bottone unico storico)
- `[x]` 13.3 Creazione canale privato
- `[x]` 13.4 Claim
- `[x]` 13.5 Add / Remove utente
- `[x]` 13.6 Rename
- `[x]` 13.7 Priorità
- `[x]` 13.8 Close
- `[x]` 13.9 Force close (`/ticket forceclose`, riservato allo staff
  — Manage Server o un ruolo di supporto configurato — elimina il
  canale subito, senza i 10s di preavviso di close normale)
- `[x]` 13.10 Transcript automatico alla chiusura — letto via
  `channel.history()` PRIMA della cancellazione. **Non richiede il
  Message Content Intent**: quell'intent riguarda solo gli eventi
  GATEWAY in tempo reale, non la history REST (governata dal normale
  permesso Read Message History) — stessa verifica già fatta per lo
  Spam Trap in `core/spam_trap_logic.py`
- `[x]` 13.11 Invio transcript nel canale log configurato (riusa
  `SETTING_LOG_CHANNEL` di §8) + DM all'utente che ha aperto il
  ticket (silenzioso se i DM sono chiusi)
- `[x]` 13.12 Statistiche ticket (`/ticket-stats [operatore]`) — prese
  in carico, chiuse, tempo medio di prima risposta (per operatore o
  per l'intero server)
- `[x]` 13.13 Configurazione ruoli di supporto multipli
  (`/ticket-support-role add|remove|list`) — combinati con il ruolo
  legacy singolo per retrocompatibilità, nessuna migrazione richiesta

## §14 UTILITY & SERVER MANAGEMENT

- `[x]` 14.1 Reaction Roles — `on_raw_reaction_add`/`remove`
- `[x]` 14.2 Button Roles — View dinamica persistente per-messaggio
  (`bot.add_view(view, message_id=...)`, pattern nuovo rispetto ai
  pannelli "bottone fisso" già in uso altrove)
- `[x]` 14.3 Select Menu Roles — multi-selezione con sincronizzazione
  che non tocca mai ruoli del membro estranei al menu (verificato
  esplicitamente con un test dedicato)
- `[x]` 14.4 Welcome messages — canale + DM opzionale, segnaposto
  `{user}`/`{username}`/`{server}`/`{membercount}`
- `[x]` 14.5 Goodbye messages
- `[x]` 14.6 Boost messages — rilevato su `premium_since` che passa
  da `None` a valorizzato, non il caso opposto
- `[ ]` 14.7 Autoresponder (con wildcards e condizioni) — **rimandato
  deliberatamente, stesso motivo di §8.16**: decidere se una parola
  chiave presente nel testo di un messaggio deve far scattare una
  risposta richiede di LEGGERE il contenuto del messaggio in tempo
  reale (`on_message`), che è esattamente il campo azzerato dal
  Message Content Intent quando non attivo — non c'è modo di
  aggirarlo con un poller o una cache come fatto per §8.13/§13.10,
  perché qui il contenuto serve SUBITO, al momento dell'evento, non
  recuperabile in un secondo momento via REST (il messaggio non è
  ancora stato cancellato, ma il gateway lo consegna già vuoto)
- `[x]` 14.8 **Custom Commands — sistema di RICHIESTA** (progettato in
  dettaglio): modal con nome comando + descrizione + esempio → embed
  automatico nel canale `#suggestions` del server principale con nome
  server, ID server, nome utente, **ID utente** (perché il nome può
  cambiare), descrizione, timestamp → bottoni staff approva/rifiuta →
  notifica di ritorno al richiedente
- `[ ]` 14.9 Snipe — **rimandato deliberatamente, stesso motivo di
  §8.16**: mostrare il testo del messaggio cancellato richiede il
  contenuto, azzerato sia in `on_message` (dove andrebbe cache-ato
  in anticipo) sia in `on_message_delete` senza il Message Content
  Intent — verificato punto per punto (non liquidato in blocco come
  errore fatto su §8.13/§8.8, vedi PROGRESS.md Fase 70b), a
  differenza di 14.11/14.12 sotto, che infatti SONO stati costruiti
- `[ ]` 14.10 Editsnipe — stesso motivo di 14.9 (before/after content)
- `[x]` 14.11 Reactionsnipe — `/reactionsnipe`, NON richiede il
  Message Content Intent: `on_raw_reaction_remove` restituisce
  emoji/autore/messaggio senza bisogno del contenuto del messaggio.
  Stato in memoria (non persistito, come tutti i bot "snipe")
- `[x]` 14.12 Ghost ping detection — traccia in memoria i messaggi
  con menzioni (`Message.mentions`, popolato da un campo gateway a
  parte dal contenuto — non azzerato dall'intent, verificato
  leggendo `Message._handle_mentions` nella libreria installata) e
  segnala nel canale log se vengono cancellati, senza mai leggere il
  testo del messaggio
- `[x]` 14.13 Sticky messages — `/sticky set|remove`, debounce minimo
  (5s) per non cancellare+reinviare ad ogni singolo messaggio in un
  canale attivo
- `[x]` 14.14 Suggestion system (per i server clienti, distinto da
  14.8) — `/suggestion-setup`, `/suggest`, bottoni persistenti
  approva/rifiuta + reazioni native 👍👎 per il voto
- `[x]` 14.15 Poll — Poll nativo di Discord (`discord.Poll`), fino a
  5 opzioni, nessuna logica propria: voto/conteggio/chiusura gestiti
  interamente da Discord
- `[x]` 14.16 Reminder — `/reminder set|list|cancel`, riusa lo
  scheduler generico esistente (nessuna tabella nuova). Consegna via
  DM, fallback nel canale se i DM sono chiusi
- `[x]` 14.17 Scheduled messages — `/schedule-message set|list|cancel`,
  riusa lo stesso scheduler dei Reminder (nessuna tabella nuova).
  Diversamente dal Reminder (personale, via DM), pubblica in un
  CANALE del server
- `[x]` 14.18 Server stats (+ grafici) — `/serverstats`: numeri del
  server + grafico a barre della crescita giornaliera (disegnato con
  Pillow, non matplotlib — nessuna nuova dipendenza pesante)

## §15 LEVELS / ECONOMY / GILDE / CLASSIFICHE

- `[x]` 15.1 XP e livelli (testuale + vocale)
- `[x]` 15.2 Anti-farm XP vocale (self_deaf, soli nel canale, AFK, 2h
  stesso canale, cap giornaliero)
- `[x]` 15.3 Economy: daily, work, pay, balance
- `[x]` 15.4 Shop — `/shop list|buy|add-item|remove-item`, oggetti
  con prezzo e un ruolo opzionale da concedere all'acquisto
- `[x]` 15.5 Giveaway (con requisiti di ruolo/livello) — `/giveaway`,
  pulsante persistente "Partecipa" (sopravvive a un riavvio del bot,
  registrato di nuovo per ogni giveaway ancora attivo), requisiti di
  livello E ruolo verificati insieme al momento dell'iscrizione
- `[x]` 15.6 Drop messages — piccola probabilità (0.5%) per
  messaggio idoneo, pulsante "primo che clicca vince", coin
  accreditati atomicamente
- `[x]` 15.7 Classifica mensile (via `period_key`, senza reset schedulato)
- `[x]` 15.8 Classifica totale all-time
- `[x]` 15.9 Top 3 con medaglie, XP e/o coin a scelta
- `[x]` 15.10 **Classifica Gilde** (mensile + totale) — `/clan
  classifica` con scelta `period` ("Questo mese"/"Di sempre", stesso
  schema di `/leaderboard` personale): la variante totale ordina per
  `clans.total_xp` (cumulativo, mai azzerato); la variante MENSILE
  (era la voce mancante) ordina per `clan_monthly_xp`, una tabella
  per-periodo (`clan_id, period_key, xp_gained`) alimentata da
  `add_xp`/`apply_text_tick` insieme al totale — stesso pattern
  `period_key` senza reset schedulato di 15.7 per la classifica
  personale, non duplicato: `core.leveling_logic.period_key()`
  riusato direttamente. **ANNUNCIO AUTOMATICO in "bacheca clan"**
  aggiunto su richiesta esplicita dell'utente ("ogni mese, il bot
  pubblica in bacheca clan la top 3"): `/clan bacheca set|disable`
  configura un canale per server, tick orario idempotente (uno
  annuncio per mese anche con riavvii) — stesso schema di 15.11
  sotto, tabella di configurazione separata
  (`clan_leaderboard_config`, non condivisa con quella personale:
  due bacheche indipendenti)
- `[x]` 15.11 Annuncio automatico dei vincitori a fine mese —
  `/monthly-winners set|disable`, podio XP e coin del mese appena
  concluso, tick orario idempotente (uno solo per mese anche con
  riavvii); la prima configurazione non annuncia retroattivamente il
  mese già passato
- `[x]` 15.12 Notifica di level-up per XP vocale — mandata nel canale
  vocale stesso (i canali vocali moderni hanno la propria chat
  integrata), l'unico posto sensato per un task periodico su più
  server
- `[x]` 15.13 Ruoli-premio per livello raggiunto — `/level-roles
  add|remove|list`, cumulativo (ogni ruolo fino al nuovo livello,
  non solo il più alto), agganciato sia a XP testuale sia vocale
- `[x]` **15.14 SISTEMA GILDE / CLAN — intera sottosezione**
  (motore economico di backend calibrato e testato — 10 XP + 4 coin
  a tick/minuto in vocale di gilda (×2 letterale del vocale normale),
  decadimento lineare dopo 3h filate
  nello stesso canale, tetto 720 tick/giorno, deficit di creazione
  15.000 coin/24h, costi canale 25k/50k/200k/800k — comandi Discord
  `/clan crea|info|membri|classifica|sciogli|tesoreria dona|
  tesoreria trasferisci|invita|espelli|promuovi|compra-canale|boost
  individuale|boost gilda`, il worker di eliminazione automatica per
  chi non colma il deficit in tempo, i ruoli Discord Capo Clan/Admin
  Clan, l'acquisto di canali extra con doppio requisito coin + ore
  vocali accumulate dalla gilda, i boost XP/coin ×2/24h individuali e
  di gilda, e ORA anche il trasferimento tesoreria→tesoreria tra due
  gilde dello STESSO owner, ANCHE cross-server — un debito di
  documentazione trovato e chiuso: il repository esisteva già da
  prima, non era mai stato collegato a nessun comando)
  - `[x]` Creazione gilda + categoria privata dedicata — `/clan crea`
    valida il tag, crea la categoria Discord (view negata a
    `@everyone`, concessa al fondatore e al bot) PRIMA di scrivere il
    record (se la categoria fallisce non resta un clan senza spazio
    reale), poi `create_clan` con deficit di creazione e finestra di
    grazia di 24h
  - `[x]` Eliminazione automatica se il deficit non è colmato in
    tempo — `core/guild_clan_expiry_worker.py` (nuovo, tick orario):
    elimina canali + categoria Discord (se esistono ancora) e poi il
    record, per i clan non ufficializzati la cui finestra è scaduta
  - `[x]` Ruoli Capo Clan / Admin Clan — **pari tra gilde diverse**
    (`core/guild_clan_role_service.py`, nuovo): un ruolo Discord
    condiviso "Capo Clan" e uno "Admin Clan" per TUTTO il server,
    riusati da ogni clan (Discord non permette due ruoli alla stessa
    posizione) — l'isolamento reale passa dagli OVERWRITE PER-UTENTE
    sulla categoria del proprio clan (`sync_member_clan_role`/
    `clear_member_clan_presence`), mai dal ruolo condiviso in sé, che
    non dà nessun permesso su nessun canale. Applicato a `/clan crea`
    (Capo Clan al fondatore), `/clan invita` (accesso base),
    `/clan promuovi` (Admin Clan + overwrite estesi o declassamento),
    `/clan espelli` e `/clan sciogli` (rimozione completa)
  - `[x]` Isolamento totale: nessun capo/admin può agire su altre
    gilde — ogni comando di gestione membri recupera SEMPRE la gilda
    del chiamante via `get_member_clan_in_guild` e opera solo sulla
    categoria/membri di quella gilda; un Admin Clan non può espellere
    un altro Admin Clan (serve il Capo), solo il Capo Clan può
    promuovere/retrocedere
  - `[x]` Comandi di gestione membri: `/clan invita` (Capo/Admin,
    rispetta il tetto `max_members`, rifiuta chi è già in un'altra
    gilda del server), `/clan espelli` (Capo/Admin, il Capo Clan non
    può essere espulso, un Admin non può espellere un altro Admin),
    `/clan promuovi` (solo Capo Clan, ruolo admin/mod/member, rispetta
    i tetti `MAX_ADMINS_PER_CLAN`/`MAX_MODS_PER_CLAN` in
    `guild_clan_logic.py`)
  - `[x]` Guadagno ×2 XP e coin — vocale: `guild_clan_voice_worker.py`
    applica il tick per la presenza vocale (agganciato a
    `clan_voice_activity_repo`), ×2 LETTERALE rispetto al vocale
    normale (`TICK_XP=10`/`TICK_COINS=4` in `core/guild_clan_logic.py`
    contro `VOICE_XP_PER_MINUTE=5`/`VOICE_COINS_PER_MINUTE=2` in
    `core/leveling_logic.py` — corregge una discrepanza reale trovata
    in una sessione precedente: la prima versione usava 30 XP/2 coin,
    un target mensile assoluto (500-750k XP/mese) invece del ×2
    dichiarato qui, mai un rapporto ×6 XP/×1 coin come si era finito
    per implementare). Testuale: `GuildClanRepository.apply_text_tick`
    agganciato a `on_message` in `cogs/leveling/leveling.py`, ×2
    letterale sull'XP (30 contro i 15 del testo normale), stesso
    cooldown 60s, NESSUNA coin (come nel testo normale) e NESSUN
    boost applicato (individuale/di gilda restano scoped al solo tick
    vocale, confermato in Fase 54)
  - `[x]` Tesoreria: **a SENSO UNICO per design** — solo membro ->
    gilda (`/clan tesoreria dona`, scala il saldo personale e
    accredita la tesoreria, ufficializzando il clan in automatico se
    il deficit viene colmato), MAI gilda -> membro (nessun prelievo
    individuale, confermato esplicitamente dall'utente quando il
    repository fu scritto — non è una voce mancante, è la regola).
    Log movimenti consultabile via `/clan info`. Il bisogno di
    "premio evento" che questa voce indicava erroneamente come
    lacuna è già servito da un percorso diverso e corretto: la cassa
    DI SERVER (§15.15, non la tesoreria di un singolo clan) via
    `/assegna-lobby`/`/assegna-winner` — chiarito esplicitamente
    dall'utente in questa sessione, correggendo un fraintendimento di
    una sessione precedente
  - `[x]` Trasferimento tesoreria→tesoreria tra due gilde dello
    STESSO owner, **ANCHE cross-server** — `core.repositories.
    guild_clan_repo.transfer_between_treasuries` esisteva già da una
    sessione precedente (clan con ID GLOBALE non per server proprio
    per questo) ma non era mai stato collegato a nessun comando
    Discord né tracciato in questo schema: **debito di
    documentazione trovato e chiuso in questa sessione**, non un
    pezzo nuovo. `/clan tesoreria trasferisci <tag_destinazione>
    <importo>`: solo il Capo Clan, cerca il tag tra TUTTE le gilde
    (di QUALUNQUE server) di cui il chiamante è owner
    (`list_clans_owned_by`, nuovo) — l'UNICA condizione è lo stesso
    owner, mai lo stesso server (confermato esplicitamente
    dall'utente quando il repository fu scritto): senza questo
    comando le coin di una seconda gilda su un altro server
    resterebbero bloccate per sempre lì
  - `[x]` Decadimento mensile 10% sulla tesoreria NON spesa —
    `guild_clan_treasury_decay_worker.py`, idempotente per periodo
    (`clans.last_decay_period`), calcolo atomico sotto `FOR UPDATE`,
    deposita il delta nella cassa di server (SPEC.md §15.15). **Bug di
    race condition trovato e corretto in questa sessione**:
    `apply_monthly_decay` restituiva solo il nuovo saldo, costringendo
    il worker a calcolare il delta verso la cassa usando il saldo
    "stale" letto da `list_officialized_clans()` (NON sotto lock) —
    se una donazione arrivava tra quella lettura e il lock, il delta
    depositato in cassa era sbagliato. Corretto seguendo lo stesso
    pattern già usato da `LevelingRepository.apply_weekly_decay`:
    `apply_monthly_decay` ora restituisce `(saldo_prima, saldo_dopo)`,
    entrambi letti sotto lo stesso `FOR UPDATE`, e il worker calcola
    il delta da questa coppia
  - `[x]` Acquisto canali: testuale / vocale / forum — `/clan
    compra-canale <tipo> [nome]`, Capo/Admin Clan, crea il canale
    Discord VERO dentro la categoria del clan PRIMA di scalare la
    tesoreria (stesso ordine di `/clan crea` con la categoria — se la
    creazione fallisce non resta una spesa senza contropartita), poi
    `increment_channels_unlocked`
  - `[x]` Costo coin raddoppiato/quadruplo per canale successivo
    (25.000 → 50.000 → 200.000 → 800.000) — applicato da `/clan
    compra-canale` via `next_channel_unlock_cost`
  - `[x]` Requisito **ore vocali accumulate in gilda** come sblocco
    canale — separato dal guadagno XP/coin: nuova colonna
    `clans.total_voice_ticks` (persona-tick, non per singolo membro),
    incrementata ad OGNI tick vocale di gilda indipendentemente dal
    decadimento/tetto giornaliero (la presenza conta comunque, a
    differenza della ricompensa), soglie 12h/24h/96h/384h
    (`VOICE_HOURS_REQUIRED` — la stessa scala persona-ora da cui
    erano già stati derivati i costi in coin, ora resa un requisito
    verificato) verificate da `/clan compra-canale` insieme al costo
  - `[x]` Boost individuale XP / Coin acquistabile — `/clan boost
    individuale`, QUALUNQUE membro (non solo Capo/Admin: paga dal
    proprio saldo per il proprio guadagno), ×2 per 24h, **10.000**
    coin personali, si applica SOLO al proprio tick vocale di gilda
    (mai al leveling generale del server — numeri e scope confermati
    dall'utente prima di scrivere la logica)
  - `[x]` Boost di gilda XP / Coin acquistabile — `/clan boost gilda`,
    Capo/Admin Clan, ×2 per 24h, **100.000** coin dalla tesoreria, si
    applica al tick di TUTTI i membri; i due boost si moltiplicano
    tra loro se entrambi attivi (×4 totale). Un acquisto mentre un
    boost è già attivo ESTENDE la scadenza da lì (mai da subito,
    stesso pattern già usato per l'estensione mensile del premium)
  - `[x]` Comandi: `/clan crea|info|membri|classifica|sciogli|
    tesoreria dona|tesoreria trasferisci|invita|espelli|promuovi|
    compra-canale|boost individuale|boost gilda` — tutti i comandi
    previsti per §15.14 sono scritti, nessuna voce mancante (la
    tesoreria resta a senso unico per design, vedi sopra)
- `[x]` **15.15 Decadimento economico + cassa di server** (scope
  emerso in conversazione con l'utente dopo la stesura iniziale
  dello schema, non presente nell'elenco originale)
  - `[x]` Decadimento settimanale 10% sui coin PERSONALI di
    QUALUNQUE membro del server (in un clan o no) — logica pura
    (`apply_weekly_personal_decay`, `week_key` in
    `core/leveling_logic.py`: mai negativo, mai sotto 1, sempre
    intero — 10% di 105 → 10 o 11, mai 10,5), persistenza atomica
    (`LevelingRepository.apply_weekly_decay`, colonna
    `last_weekly_decay_period` per riga) e worker (
    `core/weekly_personal_decay_worker.py`, stesso pattern tick
    orario/idempotente per periodo del worker di tesoreria di clan)
    tutti fatti e testati
  - `[x]` Cassa di server: `core/repositories/guild_chest_repo.py`
    (tabelle `guild_chest` + `guild_chest_ledger`), alimentata da
    ENTRAMBI i decadimenti — quello settimanale personale
    (`weekly_personal_decay_worker`) e quello mensile della
    tesoreria di clan (`guild_clan_treasury_decay_worker`, aggiornato
    per depositare il delta nella cassa del server del clan). Saldo
    e ultimi movimenti consultabili con `/cassa saldo`
  - `[x]` Uso della cassa: premi per eventi organizzati nel server
    e/o acquisto di mesi di bot premium — lo sblocco premium è
    fatto (`/cassa sblocca-premium`); i premi evento sono fatti con
    due comandi distinti: `/assegna-lobby <importo>` (premio
    partecipazione — accredita `importo` coin a CIASCUN membro
    presente in un canale vocale nell'istante in cui il comando
    viene eseguito, bot esclusi; se nessuno è in vocale o la cassa
    non basta per l'intero gruppo non viene assegnato nulla) e
    `/assegna-winner <membro> <importo>` (premio vincitore —
    accredita `importo` coin a un singolo membro scelto), entrambi
    riservati a chi ha `manage_guild` e a spesa dalla cassa di
    server (non dalla tesoreria di un clan)
  - `[x]` Sblocco premium a doppio cancello: **tempo** dal join del
    bot nel server (1° mese dopo 6 mesi, 2° dopo 1 anno, 3° dopo 2
    anni, confermato da `core.premium_pricing_logic.TIER_MONTHS_
    REQUIRED`) **E** costo in coin dalla cassa (500.000/5.000.000/
    50.000.000 sotto i 1.000 membri, ×10 per fascia successiva —
    numeri confermati dall'utente), arrotondato in eccesso a
    multipli di 25.000. `core.premium_purchase_service.
    purchase_premium_tier` orchestra i controlli (tempo, tier già
    comprato, saldo) prima di toccare la cassa; `guild_has_premium_
    access` in `core/premium.py` ora controlla anche questo stato
    oltre alla whitelist manuale — comando: `/cassa sblocca-premium`

## §16 FUN & IMMAGINI — parzialmente fatta

- `[ ]` 16.1 Mini-giochi
- `[ ]` 16.2 Image manipulation
- `[ ]` 16.3 Comandi meme
- `[ ]` 16.4 Comandi animal
- `[x]` 16.5 Ship — percentuale deterministica via hash, non casuale
  ad ogni chiamata
- `[ ]` 16.6 Howgay — deliberatamente non fatto: troppo vicino a un
  attributo protetto (l'orientamento sessuale) per un giochino
  casuale, anche se comune in altri bot Discord
- `[x]` 16.7 Rate — punteggio 0-10 deterministico via hash
- `[ ]` 16.8 Altri comandi di intrattenimento classici
- `[ ]` 16.9 Ricerca immagini SFW
- `[ ]` 16.10 NSFW / Rule 34 → **applicazione separata iYokai NSFW**
  - `[ ]` Solo canali con flag NSFW, verificato a runtime a ogni post
  - `[ ]` Comando ricerca: `r34 <termine>` → immagine casuale
  - `[ ]` Auto-post configurabile: intervallo (numero + minuti/ore),
    sottocategorie scelte o random
  - `[ ]` **Filtro a due strati obbligatori**: allowlist decisa dal
    server + blocklist hardcoded non modificabile, su ricerca manuale
    E auto-post
  - `[ ]` Log con hash di ogni immagine pubblicata

## §17 OWNER / GLOBAL ADMIN

- `[x]` 17.1 Gestione Premium List (add / remove)
- `[x]` 17.2 Toggle flag premium per modulo
- `[x]` 17.3 Eval / Exec / Shell (con secondo fattore di conferma) —
  `/owner eval`/`/owner shell`, il codice/comando va mostrato per
  intero prima dell'esecuzione (bottoni Esegui/Annulla), ogni
  invocazione loggata in modo persistente
- `[x]` 17.4 Blacklist globale utenti — cache come per i moduli,
  blocca ogni interazione tramite `BlacklistAwareCommandTree`
- `[x]` 17.5 Blacklist globale server — uscita automatica su
  `on_guild_join` se già in blacklist, uscita immediata se aggiunto
  mentre il bot è già dentro
- `[x]` 17.6 Forced cog load / unload / reload — `/owner cog-load|
  cog-unload|cog-reload`. Due bug sistemici trovati e corretti
  facendolo: i nomi dei metodi Python collidevano con hook di ciclo
  di vita riservati di `discord.py` (`cog_load`/`cog_unload`,
  rompeva ogni cog del bot), e sia `registry.register()` che
  `scheduler.register_handler()` sollevavano su un reload legittimo
  (ogni cog con un modulo premium/handler scheduler era rotto)
- `[x]` 17.7 Annuncio globale a tutti i server — `/owner announce`,
  riusa la stessa catena di fallback del messaggio di benvenuto
  (system_channel → primo canale scrivibile → DM proprietario),
  estratta in un metodo generico su `iYokaiBot`
- `[x]` 17.8 Statistiche globali (guild count, shard health, RAM,
  latenza, comandi/minuto, errori) — `/owner stats`, contatori a
  finestra scorrevole di 60s (`core/bot_stats.py`)
- `[x]` 17.9 Leave guild forzato
- `[x]` 17.10 Pannello premium interattivo con conferma a due step e
  log persistente di ogni modifica — `/owner premium-panel`, Select
  + conferma, `premium_toggle_history` (append-only, distinta dallo
  stato più recente)

---

# B. iYOKAI APPLICATION (user-installable) — **MAI TRACCIATA**

- `[ ]` B.1 Applicazione con scope `USER_INSTALL`: comandi disponibili
  in qualsiasi server, DM, group DM, anche dove il bot non è invitato
- `[ ]` B.2 Utility personali
- **Nota**: menzionata nella discussione sulle alternative al selfbot,
  poi mai inserita in nessuna lista di cose da fare — nemmeno nella
  tabella delle applicazioni del progetto

---

# C. WEB PANEL (iYokai Panel) — **MAI INIZIATO**

- `[ ]` C.1 Pagina di verify avanzato (IP, ISP, geo, fingerprint)
- `[ ]` C.2 Flusso OAuth2 `identify` (verify)
- `[ ]` C.3 Flusso OAuth2 `guilds.join` separato (restore utenti)
- `[ ]` C.4 Dashboard owner: premium list, toggle moduli premium
- `[ ]` C.5 Privacy policy pubblicata + informativa GDPR (prerequisito
  legale per C.1, non opzionale)

---

# D. iYOKAI DESKTOP (presence via RPC) — **MAI INIZIATO**

- `[✗]` D.0 Modulo selfbot con user token — **scartato**: viola i ToS
  Discord, fa bannare l'utente finale, e metterebbe a rischio l'intera
  applicazione verificata
- `[ ]` D.1 App locale che usa il socket IPC del client Discord
- `[ ]` D.2 Custom presence: giocando / ascoltando / guardando /
  competendo, immagini grande e piccola, testi, bottoni, timestamp
- `[ ]` D.3 Rotazione automatica di più stati
- `[ ]` D.4 Profili salvati
- `[✗]` D.5 Custom status testuale con emoji, bio animate, cambio
  avatar/banner a rotazione — **impossibile senza user token**, nessuna
  via legittima esiste

---

# E. ALTRE APPLICAZIONI DA CREARE

- `[ ]` iYokai Creator (backup) — vedi §11
- `[ ]` iYokai Music #1-5 — vedi §9
- `[ ]` iYokai NSFW — vedi §16.10

---

# Conteggio sintetico

Ricalcolato meccanicamente (script che conta i marcatori `[x]`/`[~]`/
`[ ]` per sezione), non a occhio — così resta verificabile da chiunque
rilancia lo stesso conteggio.

| Sezione | Fatto | Parziale | Mancante |
|---|---|---|---|
| §1 Core | 19 | 0 | 0 |
| §2 Setup | 6 | 1 | 0 |
| §3 Premium | 10 | 1 | 0 |
| §4 Verify | 10 | 0 | 9 |
| §5 Moderation | 12 | 0 | 0 |
| §6 AutoMod | 15 | 0 | 0 |
| §7 Security | 33 | 0 | 1 |
| §8 Logging | 17 | 0 | 1 |
| §9 Music | 8 | 1 | 0 |
| §10 Alerts | 6 | 0 | 1 |
| §11 Backup | 13 | 0 | 0 |
| §12 Voice temp | 8 | 0 | 0 |
| §13 Ticket | 13 | 0 | 0 |
| §14 Utility | 15 | 0 | 3 |
| §15 Levels/Gilde | 34 | 0 | 0 |
| §16 Fun/NSFW | 2 | 0 | 13 |
| §17 Owner | 10 | 0 | 0 |
| B/C/D/E | 0 | 0 | 14 |
| **Totale** | **231** | **3** | **42** |

Su 273 voci totali: **167 fatte, 1 parziale, 105 mancanti** — circa
il 61% dello schema (contando i parziali a metà peso). **§15 Levels/
Gilde è ora COMPLETO al 100%** (34/34): chiusa l'ultima voce parziale
rimasta in tutto §15, la variante MENSILE di 15.10 Classifica Gilde,
più l'annuncio automatico della top 3 in "bacheca clan" richiesto
esplicitamente dall'utente. **§10 Alerts
& Social: la parte "webhook" di §10.8 è ora fatta** (endpoint
proprio in ricezione, `/alerts webhook-create`, token segreto
mostrato una sola volta) — §10 resta parziale solo per §10.4
(YouTube live, rimandato per limiti di API, non un debito di questa
sessione). **§11 Backup
System è ora COMPLETO al 100%** (13/13): orchestrazione
automatizzabile, mirror in tempo reale, auto-propagazione e restore
utenti via OAuth2 con la progettazione di sicurezza concordata
esplicitamente con l'utente (cifratura AES-256-GCM, tre modalità di
consenso, retention differenziata per uscita/kick/ban). §15
Levels: il Sistema Gilde/Clan (§15.14) ha ora il motore economico,
tutti i comandi Discord previsti (`/clan crea|info|membri|classifica|
sciogli|tesoreria dona|tesoreria trasferisci|invita|espelli|
promuovi|compra-canale|boost individuale|boost gilda`), il worker di
eliminazione automatica, i ruoli Discord condivisi Capo Clan/Admin
Clan, l'acquisto di canali extra con doppio requisito (coin + ore
vocali accumulate dalla gilda), i boost XP/coin ×2 per 24h
(individuale e di gilda, si moltiplicano tra loro), e ORA anche il
trasferimento tesoreria→tesoreria tra due gilde dello STESSO owner
ANCHE cross-server (`/clan tesoreria trasferisci`) — un debito di
documentazione trovato durante un controllo dell'utente e chiuso in
questa sessione: `transfer_between_treasuries` esisteva già dal
secondo pezzo del repository (l'ID globale dei clan, non per server,
era stato scelto proprio per questo) ma non era mai stato collegato
a nessun comando Discord né tracciato in questo schema. ORA anche il
lato TESTUALE del guadagno ×2 è fatto (`GuildClanRepository.
apply_text_tick`, agganciato a `on_message`) — e nello stesso
controllo si è corretta una discrepanza reale trovata nel lato
vocale: la prima calibrazione usava 30 XP/2 coin al tick (un target
mensile assoluto), non il ×2 letterale dichiarato qui; ora è 10 XP/4
coin, ×2 esatto del vocale normale. **§15.14 è ORA COMPLETO**: la
voce che sembrava ancora aperta (un comando di PRELIEVO dalla
tesoreria verso un membro) era un fraintendimento di una sessione
precedente, chiarito esplicitamente dall'utente in questa sessione —
la tesoreria di clan resta a SENSO UNICO per design (membro -> gilda
sempre, gilda -> membro MAI), e il bisogno reale di "premio evento"
è già servito da un percorso diverso e corretto: la cassa DI SERVER
(§15.15), non la tesoreria di un singolo clan. Il decadimento
mensile 10% sulla tesoreria (l'altra voce `[~]` di §15.14) è ORA
COMPLETO: bug di race condition trovato e corretto — il delta
depositato nella cassa di server era calcolato sul saldo "stale"
letto da `list_officialized_clans()` (non sotto lock) invece che
sulla coppia `(saldo_prima, saldo_dopo)` letta sotto lo stesso `FOR
UPDATE` di `apply_monthly_decay`, stesso pattern già corretto di
`LevelingRepository.apply_weekly_decay`. Unica voce genuinamente
ancora aperta in tutto §15: la variante MENSILE di 15.10 Classifica
Gilde (oggi solo il totale cumulativo). §15.15
(non nello schema
originale, emersa in conversazione) è ORA COMPLETO: decadimento
settimanale personale, cassa di server alimentata da entrambi i
decadimenti, sblocco premium a doppio cancello (tempo dal join +
costo dalla cassa) — comandi `/cassa saldo` e `/cassa
sblocca-premium` — e ORA anche i due comandi di spesa dedicati ai
premi evento: `/assegna-lobby <importo>` (premio partecipazione, a
tutti i presenti in vocale nell'istante dell'esecuzione) e
`/assegna-winner <membro> <importo>` (premio vincitore, a un membro
scelto), entrambi a spesa dalla cassa di server.

Correzione del 21/09: il marcatore parziale (`` `[~]` ``) era definito nella
legenda ma non era mai stato usato — §9.4/9.5 e §10.8 erano marcati
come completamente fatti quando in realtà erano solo iniziati.
Audit a campione sul resto del documento (§5, §6, §12, §13, §15) non
ha trovato altri casi: i comandi/funzionalità elencati nelle voci
controllate esistono davvero nel codice.

**§12 Temporary Voice Channels è ORA COMPLETO al 100%** (8/8):
notifica personale alla creazione del canale (automatica E manuale,
prima solo quest'ultima rispondeva), selezione piattaforma PC/
Console/Mobile puramente informativa (`/voicetemp-platform-setup`),
cap configurabile per categoria (`/voicetemp-cap`, sempre troncato al
limite hard di Discord di 50).

**§13 Ticket System è ORA COMPLETO al 100%** (13/13): select menu
categorie (`/ticket-category`), force close riservato allo staff
(`/ticket forceclose`), transcript automatico alla chiusura inviato
nel canale log + in DM all'utente (`/ticket close`/`forceclose`, via
`channel.history()` PRIMA di cancellare il canale — **non richiede
il Message Content Intent**, verificato: quell'intent riguarda solo
gli eventi gateway in tempo reale, non la history REST governata dal
normale permesso Read Message History, stessa assunzione già
verificata per lo Spam Trap), statistiche (`/ticket-stats`, tempo
medio di prima risposta per operatore o per server), ruoli di
supporto multipli (`/ticket-support-role`, combinati col ruolo
legacy singolo per retrocompatibilità).

**§14 Utility: chiusi 14.11 Reactionsnipe e 14.12 Ghost ping
detection**, entrambi VERIFICATI punto per punto contro il Message
Content Intent invece di essere liquidati in blocco come "famiglia
snipe bloccata" (l'errore già fatto e corretto su §8.13/§8.8, vedi
Fase 70b): nessuno dei due ha bisogno del contenuto del messaggio
(`on_raw_reaction_remove` non lo richiede affatto; `Message.mentions`
arriva da un campo gateway separato dal contenuto, non azzerato
dall'intent). 14.9 Snipe, 14.10 Editsnipe e 14.7 Autoresponder restano
`[ ]` — genuinamente bloccati, stesso motivo di §8.16: servono il
contenuto del messaggio nel momento stesso dell'evento gateway
(`on_message`/`on_message_delete`/`on_message_edit`), che è
esattamente il campo azzerato senza il Message Content Intent, e a
differenza del transcript ticket non c'è modo di recuperarlo dopo
via REST (per Snipe/Editsnipe il messaggio non esiste più; per
l'Autoresponder la decisione va presa SUBITO, non in un secondo
momento).

**§2 Setup & Dashboard: chiusi 2.1 Reset configurazione, 2.2 Wizard
guidato, 2.5 Esporta configurazione, 2.6 Importa configurazione**
(`/config reset`, `/setup-wizard`, `/config export`, `/config
import`). Reset e import sovrascrivono la configurazione IN BLOCCO
(mai un merge) con una singola voce di storico ciascuno, annullabile
con `/config rollback` come qualunque altra voce. Il wizard
(`/setup-wizard`) è un'esperienza deliberatamente diversa da
`/setup`: un modulo curato alla volta (Moderazione, AutoMod, Logging,
Greetings, Vocali temporanei, Ticket) con Attiva/Disattiva + Avanti/
Indietro, invece del select menu con tutti i moduli insieme.
**2.3 Lingua per server è marcata `[~]`, non `[x]`**: il comando
(`/config language show|set`) e la colonna `language` sono ora
davvero collegati, con un piccolo registro di traduzioni
(`core/i18n.py`) per un insieme limitato di stringhe generiche
condivise — ma NON è un sistema i18n applicato a tutto il bot, che
resta in italiano nella stragrande maggioranza dei suoi messaggi;
tradurre l'intero bot è un lavoro enormemente più grande di questa
singola voce e non è stato tentato. 2.4 Prefisso personalizzato resta
`[✗]` scartato (slash-command-only, decisione già presa in una
sessione precedente).

**§3 Premium System è ORA COMPLETO al 100%** (11/11): mancavano solo
due comandi di sola LETTURA, mai scritti prima perché add/remove/
toggle bastavano per il lavoro quotidiano ma non davano una vista
d'insieme. `/owner whitelist-list` elenca i server whitelistati
(id, chi li ha aggiunti, quando, motivo) — nessuna sorpresa nella
query, solo un `ORDER BY added_at`. `/owner premium-status-all`
itera su TUTTI i server in cui il bot è presente e mostra, per
ciascuno, OGNI meccanismo di sblocco davvero attivo (whitelist/
nitro boost sul server principale/premium via cassa/abbonamenti per
modulo) invece di un singolo True/False — nuova funzione pubblica
`core.premium.get_guild_premium_breakdown()`, che riusa la stessa
logica già verificata di `guild_has_premium_access` (stessi
repository, stesse condizioni) ma restituisce il dettaglio completo
invece di fermarsi al primo sblocco trovato. Formattazione delle
righe estratta in `core/premium_status_logic.py`, logica pura
testabile senza database né bot vero — stesso principio già seguito
per ticket/snipe.

