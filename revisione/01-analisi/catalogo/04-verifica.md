# Catalogo — Verifica dei nuovi membri

Ogni riga è una funzione di verifica che i bot specializzati hanno e iYokai non ha (❌) o ha solo in parte (🟡).
Bot letti: Wick, Double Counter, Captcha.bot, YAGPDB. Le protezioni sugli ingressi (filtri e raid) sono nel file `03-sicurezza-antiraid-antinuke.md`.
Stato di iYokai preso da `SPEC.md` §4 e da `cogs/security/verify.py`: pannello con bottone o reazione, captcha a somma scritta, età minima dell'account, server in comune, whitelist, blacklist, log di ogni tentativo.

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| VER-001 | **Captcha a immagine** (lettere storte da ricopiare) | Wick [WICK]; Captcha.bot, metodo "Image" (Premium) [CAPTCHA] | 🟡 parziale: solo una somma scritta, facile per un bot | Opzione `captcha: immagine` in `/security verify setup`; immagine fatta con Pillow fuori dal ciclo principale; risposta in un modulo | NF-18 |
| VER-002 | Captcha con **misura, colori e lunghezza regolabili** | Wick (Premium, solo dal pannello) [WICK] | ❌ manca | Tre impostazioni con minimo e massimo; l'editor visuale arriva con il pannello web | NF-18 |
| VER-003 | Captcha che **si rigenera** dopo un tempo scelto | Wick `v TIME ?set 12` (Premium) [WICK] | ❌ manca | Scadenza del captcha (per esempio 2 minuti) e bottone "nuovo captcha" | NF-18 |
| VER-004 | **Tetto di tentativi** per utente, con azzeramento da parte dello staff | Double Counter (errore "max verification attempts") [DC]; Captcha.bot `/reset` [CAPTCHA] | ❌ manca | Contatore per utente con scadenza; `/security verify azzera utente:` | NF-18 |
| VER-005 | **Verifica su pagina web** con captcha esterno | Wick, modo "Web" (Turnstile) [WICK]; YAGPDB (reCAPTCHA v2) [YAGPDB]; Captcha.bot, metodo "Web" [CAPTCHA]; Double Counter [DC] | ❌ manca | Opzione `modo: web`; link unico legato all'utente, con scadenza | NF-21 |
| VER-006 | **Testo della pagina di verifica** scritto dal server | YAGPDB (pagina in markdown) [YAGPDB] | ❌ manca | Campo di testo nel pannello web, mostrato sopra il captcha; testo ripulito prima di mostrarlo | NF-21 |
| VER-007 | Verifica con **DM automatico**: chi entra riceve un link personale | Double Counter, modo "Automated" [DC]; YAGPDB "Verification DMs" [YAGPDB] | ❌ manca: c'è solo il pannello nel canale | Modo `dm` in `/security verify setup`; un solo DM all'ingresso; `HTTPException` catturata | NF-21 |
| VER-008 | **Promemoria in DM** a chi non si è verificato dopo X minuti | YAGPDB (messaggio di "re-notification") [YAGPDB] | ❌ manca | Un solo promemoria, con lo scheduler; testo con segnaposto | nuova |
| VER-009 | Avviso nel canale di verifica **se i DM sono chiusi**, che sparisce dopo pochi secondi | Double Counter "Notify to open DMs" [DC] | ❌ manca | Messaggio con `delete_after` quando l'invio del DM fallisce | nuova |
| VER-010 | **Comando `/verify`** per l'utente, in alternativa al pannello | Double Counter `/verify` [DC], Captcha.bot `/verify` [CAPTCHA], Wick `w!verify` [WICK] | ❌ manca | `/utility verifica`: risposta effimera con lo stesso bottone del pannello; visibile solo a chi non ha il ruolo | nuova |
| VER-011 | **Tempo massimo** per verificarsi, con kick o ban alla scadenza | Captcha.bot "Time Limits" (fino a 1 ora gratis, 1 giorno Premium) [CAPTCHA]; YAGPDB "Kick After Unverified" [YAGPDB]; Double Counter (2 minuti gratis, 10–60 Pro) [DC]; Wick `v X ?set 5` [WICK] | ❌ manca | `/security verify tempo minuti: azione:`; controllo con lo scheduler; vale solo per chi entra dopo l'attivazione | nuova |
| VER-012 | **Azione su chi non passa** la verifica: quarantena, kick, ban o niente | Wick `v … ?set 2` [WICK] | ❌ manca: il tentativo fallito viene solo scritto nel log | Scelta dell'azione; con "quarantena" l'utente può riprovare | nuova |
| VER-013 | Verifica chiesta **solo agli account sospetti**; gli altri entrano subito | Wick `v X ?set 3` (tutti / sospetti) [WICK] | ❌ manca | Opzione `bersaglio`; "sospetto" usa i controlli dell'anti-raid (età, avatar, nome) | nuova |
| VER-014 | **Ruolo "non verificato"** dato all'ingresso e tolto alla verifica | Double Counter "Unverified role" [DC] | ❌ manca | Opzione `ruolo_non_verificato`; mai `@everyone`; `check_role_assignable`; pausa durante un raid | nuova |
| VER-015 | **Più ruoli** dati alla verifica | Captcha.bot: 1 gratis, 5 Premium [CAPTCHA] | 🟡 parziale: un solo ruolo | Lista di ruoli (fino a 5) | nuova |
| VER-016 | **Verifica a mano** di uno o più membri da parte dello staff | Double Counter `/manverify` [DC]; Wick `w!verify MEMBRI` [WICK]; Double Counter Pro, anche dal menu contestuale [DC] | ❌ manca (la whitelist salta i controlli, ma non dà il ruolo) | `/security verify manuale membro:` e voce del menu contestuale sull'utente; riga nel log | nuova |
| VER-017 | Lo staff **rimanda il messaggio di verifica** a un utente | Double Counter `/force` [DC] | ❌ manca | `/security verify invia membro:`; solo con il modo DM (VER-007) | nuova |
| VER-018 | Ruolo staff che può verificare a mano **senza essere amministratore** | Double Counter "Staff Role" [DC] | ❌ manca | Delega dal menu Integrazioni di Discord sul gruppo `/security` | NF-05 |
| VER-019 | Account troppo giovane: **resta in attesa** finché non ha l'età richiesta, oppure viene espulso | Double Counter "Minimum account age" con "Auto Kick" [DC] | 🟡 parziale: il controllo dell'età c'è, ma il tentativo viene solo rifiutato | Scelta `attesa / kick`; messaggio con la data in cui potrà riprovare | nuova |
| VER-020 | **Modalità "cieca"**: verifica sospesa per un periodo, il ruolo viene dato subito | Double Counter, modo "Blind" [DC] | ❌ manca | Interruttore `sospendi` in `/security verify`; scritto nel log | nuova |
| VER-021 | **Riconoscimento degli account doppi** (IP, cookie, impronta del dispositivo) | Double Counter [DC]; YAGPDB (per IP; spento sul bot ufficiale) [YAGPDB] | ❌ manca | Impronta salvata solo come hash, mai l'IP in chiaro; avviso allo staff | NF-21 |
| VER-022 | Nel log, **elenco degli account collegati** a chi si è appena verificato | YAGPDB "Alt Reporting" [YAGPDB], Double Counter [DC] | ❌ manca | Embed nel canale di log con gli account che condividono l'impronta | NF-21 |
| VER-023 | **Ping di un ruolo** dello staff a ogni rilevazione di account doppio | Double Counter "Ping role" [DC] | ❌ manca | Ruolo da avvisare; `allowed_mentions` limitato | NF-21 |
| VER-024 | **Ban automatico** dell'account doppio di un utente bannato | Double Counter "Auto-ban" [DC], YAGPDB "Alt Banning" [YAGPDB] | ❌ manca | Scelta già presa: nessun ban automatico per gli account doppi. Alternativa: avviso con bottone "Banna" per lo staff | NF-21 |
| VER-025 | Confronto anche con le impronte viste **negli altri server** | Double Counter "Global Detections", "Pro Fingerprinting" [DC] | ❌ manca | Solo avviso allo staff; va scritto nella privacy policy; il server può non partecipare | NF-21 |
| VER-026 | **Blocco di VPN, proxy e Tor** alla verifica, anche come unico controllo | Double Counter "VPN Intrusions", "Only block VPNs" [DC]; Captcha.bot (se attivato) [CAPTCHA] | ❌ manca | Serve una lista esterna di indirizzi di hosting: fonte e quota da scrivere in `LIMITI.md`; lo staff può scavalcare con VER-016 (i falsi allarmi sono frequenti) | NF-21 |
| VER-027 | **Verifica con i "ruoli collegati"** di Discord: captcha fatto, età minima, avatar presente | Captcha.bot "Linked Roles" [CAPTCHA] | ❌ manca | Metadati di collegamento dell'applicazione; serve una pagina web con accesso OAuth | NF-20 |
| VER-028 | **Pannello di verifica personalizzabile**: titolo, colore, testo, emoji del bottone | Captcha.bot "Button Panels" [CAPTCHA]; Double Counter Pro (messaggio personalizzato) [DC] | ❌ manca: testo fisso, in inglese | Opzioni su `/security verify panel` o embed salvato dal costruttore | NF-17 |
| VER-029 | **Log compatto o dettagliato** a scelta | Double Counter Pro "Custom log design" [DC] | ❌ manca | Impostazione `stile_log`; lo stile compatto è una riga di testo | nuova |
| VER-030 | **Statistiche della verifica**: captcha inviati, falliti, completati, ingressi, uscite, espulsi per tempo scaduto | Captcha.bot "Server analytics", `/analytics` [CAPTCHA]; Double Counter "Analytics" [DC] | ❌ manca | `/security verify statistiche`; conteggi dalla tabella `verify_attempts`; grafico come in `/serverstats` | nuova |
| VER-031 | Ricerca nei tentativi **per utente** ed **esportazione in CSV** | Captcha.bot (ricerca per ID o nome; esportazione una volta all'ora) [CAPTCHA] | ❌ manca | `/security verify cerca utente:` e `esporta`; file sotto 10 MiB; conservazione da dichiarare | nuova |

## Fonti

Lette il 4/10/2026.

- **`[WICK]`** Wick (ufficiale): https://docs.wickbot.com/setup/ · https://docs.wickbot.com/intro/features/ · https://docs.wickbot.com/commands/moderation/verify/ · https://docs.wickbot.com/changelog/v5.x/5.3.0/
- **`[DC]`** Double Counter (ufficiale): https://docs.doublecounter.gg/double-counter-en/setup.md · `/configuration.md` · `/configuration-cont..md` · `/additional-commands.md` · `/pro-version.md` · `/alt-detections-and-vpn-intrusions.md` · `/troubleshooting.md` · `/analytics.md`
- **`[CAPTCHA]`** Captcha.bot (ufficiale): https://docs.captcha.bot/reference/command-reference · https://docs.captcha.bot/specific-features/time-limits · `/specific-features/button-panels` · `/specific-features/linked-roles` · https://docs.captcha.bot/logging/server-analytics · https://docs.captcha.bot/premium/premium · https://docs.captcha.bot/reference/faq
- **`[YAGPDB]`** YAGPDB (ufficiale): https://help.yagpdb.xyz/docs/moderation/verification/ (testo letto dal repository https://github.com/botlabs-gg/yagpdb-docs-v2)

Non verificato: la pagina "Double Counter + Onboarding" è stata vista solo nell'indice, non letta; il sito `captcha.bot` e la pagina dei piani di Wick si caricano solo con JavaScript.

## Conteggio

Contato sulle righe della tabella (`grep -c "^| VER-"`).

- Righe totali: **31**
- ❌ manca: **28**
- 🟡 parziale: **3**
