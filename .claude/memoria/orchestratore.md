# Memoria dell'orchestratore

## Aggiornata
05/10/2026, sera · ramo `main` · tutto pubblicato

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
- **F7 (D24) in corso.** Fatto: quadro unito (`core/command_groups.py`,
  `core/command_access.py`, test dell'albero; 16 gruppi + `/cerca-comando`
  e `/chiedi` di primo livello). Mappa: `revisione/02-piano/MAPPA_COMANDI_F7.md`.
  **Prossimo: spostare i comandi per area** (un agente alla volta o due su cog
  diversi), poi passo di `/setup` per i ruoli admin/mod/modban
  (`imposta_ruolo`), pannello di `/cerca-comando` (D24), `COMMAND_LIST.md`,
  SPEC, suite completa. Un `Group` semplice sotto un gruppo protetto fallisce:
  usare `GruppoYokai`. Autocomplete sotto gruppi protetti: `autocomplete_protetto`.
- Suite completa dopo F7 da lanciare con `nohup`.

## Coda (in ordine)
1. Fatti e chiusi: #137, #133, #135, #136, #134, #146, #144.
2. **F7 spostamento comandi** (sopra), poi #66/#67 (utilità), #71, #69/#70.
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
