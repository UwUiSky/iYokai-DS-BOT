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
- Suite completa lanciata (log nello scratchpad `suite.log`) dopo l'unione
  di #146 (migrazione 0020): `suite3.log` nello scratchpad. La precedente: 3198 passati.

## Coda (in ordine)
1. Fatti e chiusi (con `verifica-live`): #137, #133, #135, #136, #134
   (unito `a3004ee`). Nuove: #144 voice kick gerarchia/unlock, #145 cache
   premium 60 s.
2. Prossimo gruppo: #144 (`dev-log-ticket`), #66/#67 (`dev-utilita`), #71, #69/#70.
3. Utilità/avvisi #66, #67; fun #71; owner/core #69, #70; voci rimaste in
   #57–#62, #65 (ultimo commento di ognuna).
4. Dopo le unioni: simboli SPEC (M 10.16 = fatto), `COMMAND_LIST.md`
   (`/clan lascia`), prove live da agenti S/D/E in `VERIFICA_LIVE.md`.
5. Fine F1: `cacciatore-bug` + `ottimizzatore` (PERF-1…7) +
   `guardiano-limiti`, poi suite completa.
6. F2 musica (#64, #45, #47, #48, #126; un nodo per bot), F3 backup
   (#68, #121) e iYokai Mod (#113), poi F5, F6, F7; richieste del
   05/10: #138–#142.
7. Boost clan per tipo: fatto (#146, D23, unito `c5d88f6`, migrazione 0020).
   Il cumulo di 48 h non c'è più.

## Cose pratiche
- Repository: `/home/claude/repo`. Copie di lavoro:
  `/home/claude/wt/<nome>`; database `iyokai_w<nome>`.
- **La macchina si riavvia senza avviso**: fare commit e push spesso.
  Dopo un riavvio: `service postgresql start`.
- Copia `b146` unita: toglierla se pulita. Database `iyokai_wcaccia` e
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
