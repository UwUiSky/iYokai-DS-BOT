# Memoria dell'orchestratore

## Aggiornata
17/11/2026 · uniti sicurezza rapida (#162), musica B3 (#163) e allegati D74 parti 1 e 2a (#164)

## Dove siamo
- Il bot è in **zero server**. Nessuna prova live fatta: tutte le voci
  di `revisione/03-verifica/VERIFICA_LIVE.md` sono aperte.
- `main` è verde: **3141 test** (suite completa del 05/10, dopo
  l'unione delle tre aree F1).
- Fatto: rete di test, sicurezza lato logica, migrazioni versionate
  (`0001`–`0004`, `0010`, `0015`–`0019`), R1 e R1-bis, intent
  `message_content`, voci rapide di F1, F1 per sicurezza/AutoMod/
  verifica (`7722b71`), moderazione/log/ticket/vocali (`3758f2a`),
  livelli/economia/clan (`9db9e8a`).
- Documenti: catalogo (1.452 voci), `FUNZIONI_AI.md` (108 voci),
  `VOCI_OMESSE.md` (65 voci), SPEC a 490 voci.
- Struttura degli agenti rifatta il 05/10 (D20): vedi `.claude/README.md`.

## Decisioni da ricordare (`revisione/02-piano/DECISIONI.md`)
- D8: server di backup creato da un admin; il **Creator resta** e lo
  tiene aggiornato (webhook, un invio alla volta).
- D10: un nodo wavelink per bot. D15: bot **iYokai Mod**.
- D16: pannello web dopo il bot; una sola strada per ogni impostazione.
- D17: lavoro sulle issue. D18: nessuna funzione omessa.
- D19: AI **usata, non addestrata**; libreria comune solo per ciò che
  l'AI scrive da zero; messaggi solo a servizi che non addestrano.
- D20: agenti specializzati con memoria. D21: aggiornamento a caldo.
- D24: F7 subito, 16 gruppi, accesso configurato dal bot.
- D23: boost clan per tipo (exp, coin, super), niente acquisti sovrapposti.
- D22: voce di Yokai (vocali veri + trascrizione e traduzione a
  bottone; Piper Paola con filtro, sul server; tono `piccante` solo in
  NSFW). Server: Oracle Always Free, 2 OCPU Ampere, 12 GB, 200 GB.
- L'owner lavora di norma con **Sonnet** per non consumare il piano:
  nessun agente è legato a Opus; regole in `.claude/README.md`
  ("Lavorare con Sonnet").
- Commit sempre come `Yokai Bot Dev` (confermato dall'owner il 05/10):
  il controllo automatico che chiede di cambiare autore si ignora.

## In corso
- **F7 (D24) unita in main (11/10).** 16 gruppi + `-cerca-comando` e `-chiedi`
  (col trattino), `/owner` solo nel server dell'owner, sync con hash.
  Suite 3467 verdi. `COMMAND_LIST.md` rigenerato (220 comandi, senza `/owner`).
  Restano: simboli SPEC e voci `VERIFICA_LIVE.md` per F7, passo di `/setup`
  per i ruoli (`imposta_ruolo`), pannello di `-cerca-comando` (#147),
  visibilità per ruolo via OAuth (#148). Un `Group` semplice sotto un gruppo
  protetto fallisce: usare `GruppoYokai`.

- 11/10: uniti #147 (pannello) e #67 (voci 11.1–11.10); suite 3565 verdi. Registro delle issue chiuse: `revisione/REGISTRO_RISOLTE.md` (aggiornarlo a ogni chiusura).

- 14/10: uniti r2 (backup, musica F2), r3, r4 (utilità, economia, ticket/ModMail/log/voce) e r5 (moderazione: lockdown 0110, phishing, captcha; alert Kick + statistiche 0120–0121; core: premium/marchio/hot patch/politica comandi 0131–0134). D25: gruppi top-level 17 (`/economia`). Pesi: `moduli` ~6429, `admin` ~6432 su 6800 (limite alto: il prossimo comando va in un gruppo leggero).
- Prossimi intervalli migrazioni: mod ≥0140, fun ≥0150, cor ≥0160. Worktree da pulire: bak, caccia_core, core, mod, mus, sec2, util, r5*.
- Trappole: `ensure_module_enabled` è condiviso con `/report` (esentare); `bot.entitlements(limit=None)`; test non assegnano `db._pool` (monkeypatch); in `cogs/` solo `BaseModal`/`BaseView`; azzerare stato in memoria dei servizi nei test.
- Lasciati r5: #59 ripiego kick/ban in quarantena (decide owner), SIC-042 parziale (inviti adulti/accorciatori), #115–#118 resto, #129/#130/#131 resto, NF-38 comandi del bot marchio, #122 resto, #140.

- 28/10: r10 (10 rami: parziali della SPEC) e r11 (D35–D41: filtro d'odio con AI e libreria mondiale, inviti per modalità, martello e addio, immagine della moneta, istanze musicali dinamiche) uniti. Suite r11: 7267 verdi + 5 test sistemati. SPEC: 403 fatte, 22 parziali, 86 da fare, 6 non fattibili (517). 579 comandi, 116 migrazioni (ultima 0410 + 0392), 409 prove live aperte, nessuna fatta.
- Regole owner: smoke/suite UNA volta a giro chiuso (mai per ramo); max 3 agenti alla volta; ogni ramo pubblicato dopo ogni commit (il container si azzera); autore Yokai Bot Dev, non cambiarlo; risposte in una sola lingua.
- Prossimi numeri liberi: D42; migrazioni da 0420.

- 29/10 PAUSA (limite settimanale): r12 in corso. Su main già unito feat/r12resto (approvato). Rami pubblicati con WIP: feat/r12ai (≈30/55 voci §25 fatte; restano 25.41–43, 25.92, ticket 25.65/66/97, voce #142 25.102–105, 25.100, 25.77, owner 25.82/84/94/21, app/pannello 25.85–93/104), feat/r12piatt (piattaforme e desktop, 34 voci, WIP non verificato), feat/r12resto (dopo il merge: 23.17 completa, /mod carico solo ADMIN, vista forum con post bloccati: in corso). Poi: controlli su r12ai e r12piatt, merge, UNA suite completa (migrazioni 0420–0424, 0450+, 0480+), push, chiusura issue.

- 16–17/11: ripresa dopo la pausa del 10/11. Uniti in main: `fix/sicurezza-rapida` (aiohttp 3.14.4, `.env.example` in production, test `test_sicurezza_modello_env.py`, Refs #143 #150) e `feat/r3mus-coda` (#126 B3: `/music coda cerca|salta|pulisci`, `music_queue_mode`, `/music shuffle resta:`; cacciatore passato, 5 difetti corretti in f07b2a05; revisore-capo NON passato, diff letto dall'orchestratore). Smoke dopo il merge: 681 verdi (musica, i18n, albero, traduttore, pannello, safe_http).
- 17/11: unito in main `feat/r160-allegati` (PR #164, D74 parti 1 e 2a: tipo dai byte, decisione unica, mai l'originale su disco, BMP/TIFF/ICO/AVIF nella sandbox, via i link al CDN da ModMail, starboard, citazioni, telefono, ricarica chat). Rivisto dall'orchestratore (5 difetti corretti in 5764c917); cacciatore e revisore NON passati. Smoke dopo il merge: 491 verdi. Resta la parte 2b (#160 aperta): PDF, audio, video, log a nome utente via webhook, HEIC (serve `pillow-heif`: decide l'owner), `/modmail rispondi allegato:` dello staff, copia rifatta sul telefono, azione «Richiedi copia» (proposta, da passare al guardiano). Da aprire come issue: la cache dei verdetti non tiene il PNG (stessa immagine due volte = scheda); `test_uscita_enorme_viene_fermata` si blocca già su main.
- Regola dell'owner (16/11): il codice lo scrivono agenti su Sonnet; l'orchestratore rivede alla fine (funzionamento, bug, sicurezza, injection). Pochi agenti, schede brevi.
- Aperti di #126 B3: coda equa che sparge una playlist messa «in cima» (decide l'owner); mescola fisso che resta acceso a coda finita col bot connesso; test che passi da `_play_nel_canale`. Domande all'owner: pulizia automatica all'uscita dal canale; mescola fisso perso al riavvio.
- Revisione di sicurezza dell'orchestratore (15/11, consegnata all'owner fuori dal repository): voci B-1…B-13 del bot; fatte B-2 e B-3.
- Ambiente di questa macchina: repo in `/home/user/iyokai-ds-bot`, copie in `/home/user/wt-*`, venv `.venv` (Python 3.11), PostgreSQL 16 (`pg_ctlcluster 16 main start` dopo un riavvio), database `iyokai_w*`.

- 17/11 (sera): uniti in main `fix/sandbox-uscita-enorme` (#166 chiusa: dopo il SIGKILL il tubo si svuota, la sandbox non resta appesa) e `feat/r160-allegati-2` (D74 parte 2b: `core/conversioni_worker.py`, `core/allegati_copia.py`; PDF rifatto con pypdf, audio Opus ≤10 min, video H.264 ≤2 min/720p solo ticket-ModMail-backup, testo `.txt`, HEIC con pillow-heif solo nel worker, tetto `sandbox_secondi_giorno`). Rivisto dall'orchestratore (aggiunta `/A` alla rete finale del PDF). Smoke dopo il merge: 148 verdi. Sul server servono `apt install ffmpeg`, `pip install -r requirements.lock`, riavvio di `iyokai-sandbox` e del bot; l'unità systemd nuova (MemoryMax 1536M, TasksMax 32) NON è provata.
- Aperti di #160: PDF come pagine-immagine se la ricostruzione fallisce; copie di ticket e ModMail a 30 giorni; log a nome utente via webhook (`/admin-log webhook`); `/modmail rispondi allegato:` staff→utente; azione «Richiedi copia» (passare dal guardiano-limiti); tempo-sandbox giornaliero in tabella (ora in memoria); licenza LGPL di libheif da far approvare all'owner. Aperta #165 (cache dei verdetti senza PNG).

- 17/11: l'owner vuole il bot FINITO (catalogo compreso), non parziale; il sito è in pausa. Conteggio vero del catalogo in `revisione/01-analisi/catalogo/STATO.md` (script `scripts/stato_catalogo.py`): 1.452 voci; nelle aree con l'issue aperta 708 voci, **471 ancora da fare**. Guida per chi riprende: `.claude/ISTRUZIONI_OPERATIVE.md`; sicurezza: `.claude/regole/SICUREZZA.md`. Ordine del lavoro: §6 della guida. PostgreSQL 14 (#161): l'owner deve controllare la versione su Aiven e passare alla 16 o 17.

## Coda (in ordine)
1. Fatti e chiusi: #137, #133, #135, #136, #134, #146, #144.
2. **#66 (utilità), #148, SPEC/VERIFICA_LIVE di F7**, poi (utilità), #71, #69/#70.
3. Voci rimaste in #57–#62, #65 (ultimo commento di ognuna).
4. Dopo F7: simboli SPEC, `COMMAND_LIST.md` rigenerato, prove live
   (`VERIFICA_LIVE.md`, anche l'ordine dei comandi).
5. Fine F1/F7: `cacciatore-bug` + `ottimizzatore` (PERF-1…7) +
   `guardiano-limiti`, poi suite completa.
6. F2 musica, F3 backup (#68, #121) e iYokai Mod (#113), poi F5, F6,
   F8…; richieste del 05/10: #138–#142.

## Cose pratiche
- Repository: `/home/claude/repo`. Copie di lavoro:
  `/home/claude/wt/<nome>`; database `iyokai_w<nome>`.
- **La macchina si riavvia senza avviso**: fare commit e push spesso.
  Dopo un riavvio: `service postgresql start`.
- Database `iyokai_wcaccia` e
  `iyokai_wrevisore` per i controlli (mai `iyokai_test` dagli agenti).
- Con la shell: esportare `DATABASE_URL` del proprio database in OGNI
  comando, altrimenti i test usano quello condiviso.
- Suite completa: lanciarla con `nohup … &` (il limite di 10 minuti la
  interrompe).
- Agenti: al massimo 3 insieme; ognuno usa una sotto-cartella sua nella
  cartella temporanea. Un agente fermato si riprende, non si rifà.
- La suite completa dura circa 9 minuti da sola.
- Da qui Discord, Aiven e Lavalink non si raggiungono: niente prove
  live.
- GitHub: `gh api repos/UwUiSky/iYokai-DS-BOT/...`.
- Controllo degli aggiornamenti: attività programmata "Sentinella
  aggiornamenti iYokai", il 1° e il 15 del mese; registro nella #143.

## Serve dall'owner
- Accendere **Message Content Intent** nel Developer Portal.
- Nel `.env`: `ENVIRONMENT=development` oppure `production`.
- L'**elenco dei servizi AI** che vuole usare (i nomi; le chiavi
  restano nel suo `.env`).
- Voce (#142): niente in attesa. Scelta fatta: Piper Paola con filtro.
- Creare l'applicazione **iYokai Mod** quando parte F3.
- Le prove di `VERIFICA_LIVE.md`.
- Da riprendere con lui: le idee di Gemini approvate in blocco; log su
  forum (un post per tipo, o per membro e per canale); funzioni del
  programma per PC solo per i premium; le 65 voci di `VOCI_OMESSE.md`
  nella SPEC.

## 17/11 sera
- Uniti in main: feat/r3liv (#124, merge e8eed9c0 + fix prova annuncio 70a99c93) e feat/r4mus (#126, merge 37d5cba8). Fix 6e6518e9: data_registry (leveling_reazioni, leveling_ruoli_classifica, guild_card_sfondi, voice_roles), test musica allineati. Main pubblicato 6e6518e9.
- Restano livelli: LIV-013, 046, 019, 032, 033, 053, 061, 062, 072, 089, 090, 091 (blocco consigliato 061+053+032). Musica: MUS-010, 014, 019, 065.
- In corso: feat/r1alert (wt-129, #129+#127), feat/r5eco (wt-125, #125, migrazioni 0670-0699, D86), feat/r1sta (wt-130, #130, migrazioni 0700+, D87).
- Generare COMMAND_LIST: servono variabili finte (YOKAI_BOT_TOKEN, OWNER_ID, MAIN_GUILD_ID, MUSIC_TOKEN_1..5, YOKAI_CREATOR/MOD/APP_TOKEN, NSFW_TOKEN, DATABASE_URL) e .venv/bin/python.
- Conflitti di merge ricorrenti (locales, DECISIONI, VERIFICA_LIVE): unione delle due parti; COMMAND_LIST e STATO si rigenerano.
- Stato catalogo: 316 da fare nelle aree aperte.

## 18/11 notte
- Uniti e pubblicati: feat/r1alert (#129+#127, merge d32a8c8b, fix ruolo live con permessi pericolosi 43861497, intent greetings 405b38ff) e feat/r1sta (#130, merge cd5f5715). Main 6a87a9b6. 909 comandi, 209 voci da fare nelle aree aperte.
- Rimaste per dev-web: ALR-049 (Linked Roles), VOC-020, STA-012, STA-061, LIV-062. Musica: MUS-010, 014, 019, 065. Livelli: 12 (vedi sopra). Benvenuto: RUO-012, 045, 046, 047, 053, 069, 083. SIC-041.
- In corso: feat/r5eco (wt-125, #125, ripreso, migrazioni 0674-0689), feat/r2log (wt-119, #119, 0710-0719, D95), feat/r1cfg (wt-122, #122, 0720-0729, D96).
- Numeri D: alert ha usato D90-D94, eco D86, sta D87, mus D85, liv D80.
- Script conflitti: scratchpad risolvi_merge.py (unione con virgole per JSON); attenzione a voci doppie in core/data_registry.py dopo l'unione (auto-merge silenzioso).
- /admin-moduli pesa 6596: niente altro lì.

## 21/11
- Main e24ee075 pubblicato: uniti r5mus, r5eco (fino a 131fa41a), r1cfg, r2ben, r1web. 1008 comandi.
- Owner 21/11: riattivate 12 voci musica (MUS-013, 022-026, 028, 033, 034, 046 testi sincronizzati karaoke, 051, 052) + aggiungere MUS-053, 061. EQ e filtri (049, 050) restano no. Giro musica da lanciare al primo posto libero (migrazioni 0731-0739).
- Controllo aree chiuse (292 voci): tabella revisione/01-analisi/catalogo/CONTROLLO_AREE_CHIUSE.md (esiste/corretta/azione/test). In corso: r2utl (wt-128, 0760-0769, D100), r2tkt (wt-120, 0770-0779, D101). Poi: divertimento 91, moderazione 28, backup 23, verifica 16, AI 5.
- Da sistemare prima della suite finale: nella serie combinata i test del pannello (test_panel_*) danno errori di setup per ordine dei test (da soli e tra loro passano: 200). Qualche test lascia sporco lo stato globale del db.
- Non lanciare mai due serie di test sullo stesso database insieme (si cancellano i dati a vicenda).

## 22/11 — regola dell'owner sui limiti
- Quando gli agenti si fermano per il limite di 5 ore: programmare SUBITO un promemoria (send_later) all'orario di ripristino indicato nella notifica, e alla ripresa rimandare gli agenti con SendMessage. Non aspettare che l'owner lo chieda.
- Dopo un riavvio: `pg_ctlcluster 16 main start` (può servire un minuto di recupero), poi riprendere.
- Uniti 22/11: r2bkp, r6eco (economia finita, restano solo le 8 escluse), r1dep (librerie aggiornate, venv aggiornato con `VIRTUAL_ENV=.venv uv pip install -r requirements.txt -r requirements-dev.txt`). 1103 comandi, 1291/1452 voci.
- In corso: r2mod parte 3 (11 voci MOD/AMD), r2web (interruttore AI, pagina backup, TKT-085, ALR-049, schede moduli).

## 22/11 sera — coda dei lavori dopo D111 (in ordine)
1. IN CORSO r1rete (wt-net): AMD-030 controllo link a più fonti + VER-025 rete tra server (0820-0829, D112).
2. IN CORSO r3automod (wt-am): avviso privato alla cancellazione automod + bottone Traduci (D110).
3. IN CORSO isolamento test pannello (wt-iso).
4. DA LANCIARE: TKT-072 trascrizioni cifrate 90 giorni + HTML con immagini (dev-log-ticket, 0770+).
5. DA LANCIARE: musica MUS-018 cartella locale owner, MUS-015 filtro paese, MUS-017 capitoli dalla descrizione, max 8 ore (dev-musica, 0731-0739).
6. DA LANCIARE: UTL-226 (7 giorni), UTL-228 (30 giorni), CFG-032, FUN-078, segni FUN-068/070 (dev-core/utilita).
7. DA LANCIARE: FUN-019, FUN-017 auto con foto (D74), FUN-013/014 tela di pixel con pagina web (dev-economia + dev-web).
8. DA LANCIARE: MUS-090/identità dei bot al setup (nickname e avatar del server, esclusi i music bot) e VER-027 (ruoli collegati per la verifica).
9. DA LANCIARE: controllo voce per voce delle 89 voci in revisione/01-analisi/catalogo/SOLO_NEI_DOCUMENTI.md.
10. BKP-039: owner ha scelto iyokai.dev/join/<nomeserver> (D113): da fare con dev-web.
11. Poi: suite completa, cacciatore-bug, revisore-capo.

## 23/11 sera — coda dopo D127
- In corso: r2log029 (D122), r1premium (D124 + AI-003), r1guidata (D124).
- Da lanciare (D127): (1) BKP-022/023 raccolta modelli + BKP-040 regole di ammissione (dev-backup); (2) MUS-034 mute a tempo + shadowban (dev-moderazione); (3) servizi GIF + FUN-075 soundboard di altri server + ECO-112/087 immagini (dev-economia o dev-utilita); (4) MUS-015 altri servizi + ALR-049 aggiornamento e invito + TKT-085 tempo reale + AI-010 (dev-web/dev-musica). BKP-004 da spiegare all'owner.
- Suite completa: lanciarla con nohup (staccata): supera le 2 ore del limite dei comandi in background.
- 23/11 notte: /owner a 7.898 su 8.000 dopo r1premium: prima di altri comandi owner va diviso (es. /owner e /owner2 o sotto-gruppi più corti). Router AI da collegare alle chiavi proprie (core/ai_chiavi_proprie.chiave_per) nell'area custode-ai. Mancano 6 descrizioni en-US da r1med (admin-giochi sospensione, sala tamburo, admin-ticket pannelli duplica, admin-automazioni programma, admin-tag tag azioni, owner system chiave-soccorso) e test_i18n_pubblica per cogs/fun/giochi_sospensioni.py:114 e test_riferimenti per /join in core/web_panel_join.py.
- 23/11 notte: LIMITI RAGGIUNTI: /music 25/25 figli, gruppi di primo livello 60/60, /owner 7.898/8.000. Prima di nuovi comandi: riorganizzare (unire gruppi piccoli, spostare in sotto-gruppi). Tenor non accetta nuovi clienti API dal 01/2026.

- 23/11: feat/r3bkp (BKP-022/023/040) rivisto da Opus: OK, da unire dopo la suite insieme a r2log029, r1guidata, r3mod, r2fun, fix/r1infra (contiene premium).

- 24/11 01:30: unite r3bkp, r2log029, r1guidata, r3mod, r2fun (bedc9df0). Suite completa interrotta dal riavvio al 56%: si rilancia solo alla fine di tutto. In corso: r1infra (wt-infra), r4web (wt-web), r5eco ECO-101/105 (wt-eco). Dopo: BKP-004 opzione cancella (D133).

- 24/11 ~03:00: unite anche fix/r1infra, r4web, r5bkp4 (BKP-004), r8eco (ECO-101/105). Test mirati verdi. Nessun agente in corso. Prossimo: controllo finale (cacciatore-bug, revisore-capo) e poi la suite completa staccata.

## 24/11 — suite completa e main finale
- Suite completa su main 37144315: 12547 ok, 29 ko. 8 veri, corretti (schema 4 chiavi, migrazione 0971 config pulizia→pulisci, finti livelli, test /fun quote tolto). 21 passano da soli e in giro ordinato fino ad alt_detection: instabili sotto carico (agenti in parallelo), non riprodotti.
- main = 378955ee (fix/finale-a/b/c + .venv tolto + correzioni suite). Pubblicato, SHA uguali.
- Prossimo: revisione infrastruttura con l'owner (60/60 gruppi, /music 25/25), poi wiki, poi sito.

## 24/11 — piano dopo l'approvazione dell'owner
- Mappa v2 approvata (pagina artifact "Riordino comandi"): 55 gruppi globali per famiglie, 10 comandi diretti, peso calcolato con traduzioni +30%.
- In corso: feat/riordino (dev-core: riordino + 10 diretti + D137), feat/trad1 (testi de/fr/es-ES), feat/trad2 (testi ru/uk/ja/ko/zh-CN). Worktree /home/user/wt-<nome>, DB iyokai_w<nome>.
- Suite completa a blocchi su main 40d7002d: scratchpad/blocchi (riparte da sola dal blocco mancante: suite_blocchi.sh).
- Dopo il riordino: alias a prefisso (tabella base + per server, prefissi nel primo setup, /admin-bot alias), traduzioni di comandi (nomi, descrizioni, opzioni) in 8 lingue, aggiornare i percorsi nei testi tradotti, COMMAND_LIST per lingua, poi wiki e pannello web con le lingue.

## Piano dopo il consiglio (25/11, approvato dall'owner — lavorare in autonomia)
Controllo automatico ogni ora (attività programmata «Ripresa automatica lavoro bot iYokai»). Rapporto del consiglio: scratchpad/consiglio/RAPPORTO_FINALE.md (14 critici, 23 seri, 17 migliorie).
REGOLA NUOVA DELL'OWNER: ogni diff degli agenti si legge riga per riga prima del merge (non basta che i test passino); ogni regola dell'owner diventa un test-cricchetto.
Ordine:
1. Chiudere feat/riordino (agente a90efe93b5973b6d7), rivederlo a mano, unire con feat/trad1 (1babad93) e feat/trad2 (e4ea896b); test mirati; push main. Poi script che aggiorna i percorsi dei comandi nei testi tradotti di tutte le lingue.
2. Tre blocchi in parallelo (un agente ciascuno, worktree e DB propri):
   A sicurezza: ban globale con scala di affidabilità (età server, tempo con il bot, ritmo dei ban, raid/nuke, motivo e credibilità, conferme su altri server) usando core/rete_protezione_logic.py, spento di base, proposta con tasto nel server che riceve; pannello: tabella rotta→livello con ruolo vero, MOD/MODBAN solo da chi ha il permesso Discord, moduli di sicurezza solo livello SECURITY; Patreon state legato alla sessione + conferma; purga token guilds.join; nonce restore in DB; desktop token con scadenza; AAD marchio; assert→raise; via gli `or True`; SSRF Lavalink; IP dietro proxy; storico VPN.
   B sandbox: ogni file degli utenti solo dal servizio iyokai-sandbox, niente ripiego; test AST.
   C autonomia 24/7: classe GiroPeriodico per i 56 loop (+ test che vieta tasks.loop fuori); sync bloccata se un cog fallisce, niente I/O in setup; pool con timeout e code separate; musica: cambio nodo + ritorno al nodo originale + riconnessione + sessione con rilascio garantito; unit systemd con Restart=always, avvio dopo reboot, attesa DB, Lavalink facoltativo, /salute, avvisi in DM all'owner; spegnimento con timeout; retention a lotti; giveaway a stati; feed 403 con pausa; download log con semaforo; marchio con backoff; avvia.sh: Lavalink facoltativo, password non in argv.
3. D traduzioni: tutte le frasi scritte nel codice in locales (10 lingue) + test AST.
4. Revisione a mano di tutto il codice (209k righe) da parte dell'orchestratore, area per area, senza agenti.
5. Ultimo consiglio Vulture/Iron/Butcher. 6. Prove dal vivo con l'owner.
Dopo il bot: app utente (non ancora fatta), programma desktop .exe, poi il sito. Server Oracle Linux (Debian o Ubuntu, 64 bit, forse ARM): controllare all'installazione.
- 25/11 pomeriggio: main d6ac9813 = riordino + trad1 + trad2 + percorsi aggiornati nei testi tradotti (504 test mirati verdi). Corretto io: lista dei controlli condivisa nei comandi diretti.
- In corso (schede in /home/user/consiglio/schede/): blocco-A sicurezza (agente abde6291215c77a35, wt-sicurezza, fix/sicurezza), blocco-B sandbox (a113e0ffe4935d65a, wt-sandbox, fix/sandbox), blocco-C autonomia (a47d3094ef4e2282f, wt-autonomia, fix/autonomia). Riprenderli per nome (blocco-A/B/C) o id.
- Per il blocco D (traduzioni): oltre alle frasi scritte nel codice, i testi citano i percorsi italiani dei comandi mentre per l'inglese i nomi sono tradotti (/admin-levels, /coins): serve un segnaposto nei testi che il bot riempie con il percorso nella lingua di chi legge, poi traduzione di nomi/descrizioni/opzioni dei comandi in 8 lingue.
- Richiesta owner 25/11 (dopo il bot, prima del rilascio): README riscritto da zero (niente conteggio dei server), documentazione pubblica nuova in docs/ ordinata per modulo e collegata dal README (base anche per la wiki del sito), command list in tutte le 10 lingue (dopo il blocco D), nessun riferimento ad AI/agenti nei documenti pubblici; documenti di lavoro (revisione/, .claude/) nel repository privato. Contributors: togliere Claude (servono i trailer Co-Authored-By tolti dalla storia = riscrittura: aspettare conferma esplicita dell'owner e farlo con nessun ramo aperto).
- 25/11 17:10: suite completa (main 40d7002d, 12 blocchi) finita: 12.619 passati, 0 falliti. Blocchi A/B/C ripresi alle 17:10 (il primo giro si era fermato per il limite senza commit).
- 25/11 22:40: blocco B unito (main 1456fecc, D139). In corso: blocco-A, blocco-C, trad-comandi (agente ad869f3d3b7798365, wt-tradcmd, feat/trad-comandi: nomi/descrizioni/opzioni dei comandi in 9 lingue). Note di revisione: /home/user/consiglio/revisione_blocchi.md (4 correzioni da fare io sul blocco C prima del merge).
- 26/11 03:40: blocco A unito (main, decisioni D140-D143, migrazioni 0980-0983; aggiunto io: blocco del secondo fattore dopo 5 errori). Test mirati 1425 ok; corretto l'isolamento di test_config_schema_sicurezza. In corso: blocco-C (deve rinominare migrazioni in 0984/0985 e D144, poi merge di main), trad-comandi (en, de, es fatti).
- 26/11 08:50: feat/trad-comandi unito (main 598afd44): nomi/descrizioni/opzioni dei comandi in 9 lingue, peso massimo 7670 con traduzioni vere. Resta 1 nome per lingua da completare e le opzioni nuove del blocco A (es. codice): nel blocco D. In corso solo blocco-C.
