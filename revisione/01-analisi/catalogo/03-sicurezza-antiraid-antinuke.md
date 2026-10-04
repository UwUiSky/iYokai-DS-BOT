# Catalogo — Sicurezza: anti-nuke, anti-raid, filtri all'ingresso, canale trappola

Ogni riga è una protezione o un'impostazione di sicurezza che i bot specializzati hanno e iYokai non ha (❌) o ha solo in parte (🟡).
Bot letti: Wick (la fonte più ricca), Beemo, Carl-bot, Zeppelin, YAGPDB, Captcha.bot, Double Counter. La verifica dei nuovi membri è nel file `04-verifica.md`; il blocco del server è in `01-moderazione.md` (MOD-090…097).
Stato di iYokai preso da `SPEC.md` §7 e da `cogs/security/`: anti-nuke con una soglia per categoria, anti-raid sugli ingressi, canale trappola con appello, rete di ban, punteggio di sicurezza.
**Voci in questo file: 46** (❌ mancano: 33 · 🟡 parziali: 13).

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| SIC-001 | Anti-nuke con **due soglie** per ogni azione: al minuto e all'ora | Wick [WICK] | 🟡 parziale: una sola soglia con una finestra | Seconda coppia soglia/finestra in `/security antinuke limits`; copre anche l'attacco lento | M 3.5 |
| SIC-002 | **Quarantena** come punizione dell'anti-nuke: l'autore resta nel server senza poteri, in attesa di controllo | Wick [WICK] | 🟡 parziale: le punizioni sono "togli i ruoli" o "ban" | Terza scelta `quarantena` in `/security antinuke punish-action`, come default; per i bot con ruolo gestito: kick (M 3.2) | M 3.5 |
| SIC-003 | Sorveglianza dei membri in quarantena: avviso se qualcuno prova a **toglierli dalla quarantena o a ridare ruoli** | Wick "Quarantine Hold" [WICK] | ❌ manca | Ascoltare `on_member_update`; se chi cambia i ruoli non è fidato: annulla e avvisa | nuova |
| SIC-004 | Il **ruolo di quarantena non può ricevere permessi pericolosi** (il bot li toglie) | Wick, "Enforce Quarantine permissions" `misc 6` [WICK] | ❌ manca | Ascoltare `on_guild_role_update` sul ruolo Quarantined e rimettere i permessi a zero | M 3.8 |
| SIC-005 | "Strict mode": blocco dei **permessi pericolosi aggiunti a un ruolo qualsiasi** | Wick `an 5b` (Premium) [WICK] | ❌ manca | Ascoltare `on_guild_role_update`; se l'autore non è fidato: riportare i permessi di prima e avvisare; autore letto dal registro con più tentativi (M 3.3) | nuova |
| SIC-006 | Controllo dei permessi pericolosi dati a **@everyone e ai ruoli pubblici** | Wick `an 5c` "Monitor Public Roles" [WICK] | ❌ manca | Stesso ascolto di SIC-005, limitato a `@everyone` e ai ruoli dati a tutti | nuova |
| SIC-007 | Controllo dei cambi ai **permessi dei canali** | Wick "Monitor Channel Permissions" [WICK] | ❌ manca | Ascoltare `on_guild_channel_update` sulle modifiche dei permessi; soglia come per le altre categorie | nuova |
| SIC-008 | Azione automatica quando un membro riceve un **ruolo con permessi pericolosi** | Wick `an 5e` "Strict Member Role Addition" [WICK] | 🟡 parziale: oggi parte solo un DM all'owner | Opzione "togli il ruolo e avvisa" se chi lo ha dato non è fidato | nuova |
| SIC-009 | Protezione del **link personalizzato** del server (vanity URL) | Wick `an 5d` [WICK] | ❌ manca | Ascoltare `on_guild_update` sul codice vanity; il ripristino richiede che il server abbia ancora il livello di boost necessario | nuova |
| SIC-010 | Rilevamento della **"pulizia" di massa dei membri** (prune) | Wick `an 4a` (Premium) [WICK] | ❌ manca | Voce `member_prune` del registro di controllo; conta come azione di ban/kick di massa | nuova |
| SIC-011 | **Modalità panico** dell'anti-nuke: a un attacco rapido il server viene bloccato da solo | Wick `anpanic 1`, `anp 3` (Premium) [WICK] | ❌ manca | L'anti-nuke chiama il blocco del server quando più autori superano le soglie insieme | NF-29 |
| SIC-012 | Durante il panico **solo l'owner e il bot hanno poteri**; i comandi di moderazione sono bloccati per gli altri | Wick `anp 7` [WICK] | ❌ manca | Stato "panico" letto dai gruppi `/mod` e `/modban`; solo l'owner e i fidati passano | NF-29 |
| SIC-013 | Durante il panico vengono **avvisati con un ping** i ruoli scelti | Wick `anp 5` "Warned Roles" [WICK] | ❌ manca | Lista di ruoli da avvisare nel canale allarmi; `allowed_mentions` limitato | NF-29 |
| SIC-014 | **Categorie escluse** dal blocco del panico | Wick `anp 6` [WICK] | ❌ manca | Lista di categorie (fino a 25) che il blocco salta | NF-29 |
| SIC-015 | Fine del panico con **sblocco automatico**, attivabile o no | Wick `anp 4` [WICK] | ❌ manca | Interruttore; lo sblocco usa lo stato salvato dal blocco | NF-29 |
| SIC-016 | **Ripristino dopo l'attacco da una copia** del server presa ogni 3 ore | Wick "Restore System" con backup (Premium) [WICK] | 🟡 parziale: ricrea solo canali di testo, senza posizione, da ciò che il bot ricorda | Usare l'ultimo snapshot del backup (D8) come fonte per ricreare canali, ruoli e permessi | M 3.4 |
| SIC-017 | **Registro degli attacchi** con numero: chi è stato fermato, cosa è stato cancellato o creato | Wick `ncases` [WICK] | ❌ manca | Tabella `nuke_cases`; `/security antinuke casi [numero]`; lista paginata | nuova |
| SIC-018 | **Due livelli di fiducia**: "extra owner" (come l'owner) e "trusted admin" (immune, ma non tocca l'anti-nuke) | Wick [WICK] | 🟡 parziale: una sola lista di fidati | Colonna `livello` nella lista; solo l'owner aggiunge gli extra owner | nuova |
| SIC-019 | Fiducia **limitata a un tipo di azione o a una categoria** (esempio: il bot dei ticket può creare e cancellare canali solo nella sua categoria) | Wick, whitelist per tipo e per categoria [WICK] | ❌ manca: un fidato è esente da tutto | Colonne `tipo_azione` e `categoria` nella lista dei fidati | nuova |
| SIC-020 | Esenzione di un **webhook** dai controlli | Wick `whitelist webhook-id` [WICK] | ❌ manca | Tipo "webhook" nella lista dei fidati | nuova |
| SIC-021 | **Chiave di soccorso**: codice dato all'owner per riprendere il controllo del bot se perde l'account | Wick "rescue key" con QR [WICK] | ❌ manca | Codice mostrato una volta sola, salvato come hash; l'uso passa da `/owner` con controllo a mano | nuova |
| SIC-022 | Avviso se il **ruolo del bot o quello di quarantena sono troppo in basso** per funzionare | Wick (guida e domande frequenti) [WICK] | ❌ manca: `/security-score` non controlla la posizione | Controllo in più nel punteggio di sicurezza e all'attivazione dei moduli | nuova |
| SIC-023 | Filtri all'ingresso con **azione scelta per ogni filtro** (timeout, kick, ban) | Wick "Join Gate" `jg … ?set` [WICK] | 🟡 parziale: una sola azione per tutto, e solo quarantena o livello di verifica | Azione per filtro in `/security antiraid`; i filtri lavorano anche fuori da un raid (BUG-12) | nuova |
| SIC-024 | Account troppo giovane: **DM che spiega il requisito** prima dell'azione | Wick `jg 3d` [WICK] | ❌ manca | Testo configurabile; `HTTPException` catturata | nuova |
| SIC-025 | Filtro su **chi aggiunge bot**: solo le persone autorizzate | Wick `jg 4a` "Bot Addition Filter" [WICK] | ❌ manca | In `on_member_join` di un bot: leggere chi l'ha aggiunto dal registro; se non è fidato: kick del bot e avviso | M 3.5 |
| SIC-026 | Filtro sui **bot non verificati da Discord** | Wick `jg 6a` [WICK] | ❌ manca | `member.public_flags.verified_bot`; azione configurabile | nuova |
| SIC-027 | Filtro sui **nomi pubblicitari** (invito Discord nel nome o nel profilo) | Wick `jg 5a` [WICK], YAGPDB "Join username invite" [YAGPDB] | ❌ manca | Le stesse espressioni del blocco inviti applicate a nome e nome visualizzato | nuova |
| SIC-028 | Filtro sui nomi con **lista di parole o schemi scelti dal server** | Wick `jg 8` (esatto o con jolly) [WICK]; YAGPDB "Join username word denylist", "matches regex" [YAGPDB] | 🟡 parziale: uno schema fisso (lettere più cifre finali) | Lista per server (fino a 100 voci) con jolly `*` | nuova |
| SIC-029 | Raid contato **solo sugli account sospetti** invece che su tutti gli ingressi | Wick `jr 4c` (Premium) [WICK] | ❌ manca | Opzione `tipo: tutti / sospetti` in `/security antiraid join-rate` | nuova |
| SIC-030 | Segnale di raid: **account creati a poca distanza l'uno dall'altro** | Wick "ID Flag" `jr 8a–8d` [WICK] | ❌ manca | Confronto delle date di creazione degli ultimi ingressi; margine e numero minimo configurabili | nuova |
| SIC-031 | Segnale di raid: **nomi simili** tra gli ultimi entrati | Wick "String Flag" [WICK] | ❌ manca | Confronto dei nomi normalizzati degli ultimi N ingressi | nuova |
| SIC-032 | Al raid: **kick o ban** degli account coinvolti | Wick `jr 2` [WICK]; Beemo (ban dei sospetti) [BEEMO] | 🟡 parziale: solo quarantena o livello di verifica più alto | Scelte `kick` e `ban` in `/security antiraid lockdown-action`; pause tra le chiamate | nuova |
| SIC-033 | Al raid: azione anche su chi è **entrato poco prima** che la soglia scattasse | Wick [WICK], Beemo [BEEMO] | ❌ manca: agisce solo su chi entra dopo | Tenere in memoria gli ingressi della finestra e applicare l'azione a tutti | nuova |
| SIC-034 | Allarme raid con **ping dei ruoli** dello staff | Wick `jr 3` "Warned Roles" [WICK] | ❌ manca: DM all'owner e canale, senza ping | Lista di ruoli; un solo allarme per episodio (M 3.7) | nuova |
| SIC-035 | **Elenco completo degli account** del raid, consultabile dopo | Wick (log con link all'elenco) [WICK] | ❌ manca | File di testo con ID, nome e data di creazione allegato all'allarme; sotto 10 MiB | nuova |
| SIC-036 | **Livelli di allerta con nome**, impostati a mano o da una regola, che cambiano le regole attive | Zeppelin `antiraid_level`, `set_antiraid_level` [ZEPPELIN] | ❌ manca | `/security antiraid livello`; ogni livello accende un profilo dell'AutoMod (AMD-067) | nuova |
| SIC-037 | Riconoscimento dei raid **condiviso tra tutti i server**, senza configurare niente | Beemo [BEEMO] | 🟡 parziale: la rete condivide solo i ban del canale trappola | Segnale "stesso account entra in molti server in pochi minuti"; solo avviso allo staff: niente punteggio globale (respinto in `BACKLOG.md` §9) | nuova |
| SIC-038 | Comando per **segnalare un raid non riconosciuto** a chi gestisce il bot | Beemo `/report-raid` [BEEMO] | ❌ manca | `/security antiraid segnala`; invia all'owner l'elenco degli ultimi ingressi | nuova |
| SIC-039 | **Più canali trappola** nello stesso server | Carl-bot "honeypot": 1 gratis, 5 Premium [CARL] | 🟡 parziale: un solo canale | Tabella con più canali; tetto per server | nuova |
| SIC-040 | Canale trappola con **punizione a scelta** (cancella, decide lo staff, mute, kick, ban) | Carl-bot `/honeypot punishment` [CARL] | 🟡 parziale: la sequenza è fissa e finisce con il ban | Scelta dell'azione in `/security spamtrap`; con "decide lo staff" si usa AMD-047 | nuova |
| SIC-041 | Phishing: **azione in più** oltre alla cancellazione (timeout, kick o ban) | Captcha.bot [CAPTCHA] | ❌ manca | Azione configurabile sul filtro phishing | NF-31 |
| SIC-042 | Phishing: riconoscere **inviti a server per adulti, finti siti Steam, accorciatori di link** | Captcha.bot [CAPTCHA] | ❌ manca | Categorie in più nella lista; ognuna si accende o si spegne | NF-31 |
| SIC-043 | Phishing: **canale di log dedicato** | Captcha.bot [CAPTCHA] | ❌ manca | Tipo di uscita "phishing" nel router dei canali | NF-01 |
| SIC-044 | Scheda su un utente con i **ban ricevuti negli altri server** della rete | Double Counter "Lens" [DC] | 🟡 parziale: `/global-ban status` mostra solo la storia recente del server | `/security globalban controlla utente:`; mostra solo i ban del canale trappola; niente punteggio di comportamento (respinto in `BACKLOG.md` §9) | nuova |
| SIC-045 | L'utente può **togliersi dalla raccolta di rete** | Double Counter `/privacy`, "Opt-in/out of Lens" [DC] | ❌ manca | Voce nel comando privacy; i ban di sicurezza restano (D6) | NF-04 |
| SIC-046 | Il server può **non contribuire** ai dati di rete pur usando il bot | Double Counter (interruttore Lens nel pannello) [DC] | 🟡 parziale: `/global-ban disable` spegne sia l'invio sia la ricezione | Due interruttori separati: "ricevi" e "invia" | nuova |

## Fonti

Lette il 4/10/2026.

- **`[WICK]`** Wick (ufficiale): https://docs.wickbot.com/intro/what-is-wick/ · https://docs.wickbot.com/intro/features/ · https://docs.wickbot.com/setup/ · https://docs.wickbot.com/faq/ · https://docs.wickbot.com/commands/utility/ncases/ · https://docs.wickbot.com/commands/moderation/quarantine/ · https://docs.wickbot.com/changelog/v5.x/5.0.0/
- **`[BEEMO]`** Beemo (ufficiale): https://beemo.gg · https://docs.beemo.gg
- **`[CARL]`** Carl-bot (ufficiale): https://docs.carl.gg/automod.md
- **`[ZEPPELIN]`** Zeppelin (ufficiale, codice sorgente): https://github.com/ZeppelinBot/Zeppelin — `backend/src/plugins/Automod/triggers/antiraidLevel.ts`, `Automod/actions/setAntiraidLevel.ts`
- **`[YAGPDB]`** YAGPDB (ufficiale): https://help.yagpdb.xyz/docs/moderation/advanced-automoderator/triggers/
- **`[CAPTCHA]`** Captcha.bot (ufficiale): https://docs.captcha.bot/specific-features/anti-phishing
- **`[DC]`** Double Counter (ufficiale): https://docs.doublecounter.gg/double-counter-en/lens.md · https://docs.doublecounter.gg/double-counter-en/doogle.md

Non verificato: la pagina `wickbot.com/premium` non mostra l'elenco dei piani (si carica con JavaScript); le voci "(Premium)" di Wick vengono dalle pagine della documentazione. Sapphire, Atlas e Maki non sono leggibili da qui.

## Conteggio

Contato sulle righe della tabella (`grep -c "^| SIC-"`).

- Righe totali: **46**
- ❌ manca: **33**
- 🟡 parziale: **13**
