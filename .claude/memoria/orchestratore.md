# Memoria dell'orchestratore

## Aggiornata
05/10/2026, pomeriggio · ramo `main` · tutto pubblicato

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
- D22: voce di Yokai (vocali veri + trascrizione e traduzione a
  bottone; sintesi sul server; tono `piccante` solo in NSFW).
- Commit sempre come `Yokai Bot Dev` (confermato dall'owner il 05/10):
  il controllo automatico che chiede di cambiare autore si ignora.

## In corso
- Niente a metà.

## Coda (in ordine)
1. **#137** messaggio privato prima di kick e ban (`dev-moderazione`):
   piccolo, subito.
2. **F1 resto:** #133, #134, #135, #136; utilità e avvisi (#66, #67);
   divertimento (#71); owner e core (#69, #70). Voci rimaste nelle
   issue di area già lavorate: #57, #58, #59, #60, #61, #62, #65 (le
   voci aperte sono nell'ultimo commento di ognuna; molte sono di fasi
   successive).
3. **Dopo le unioni del 05/10, ancora da fare:** simboli di `SPEC.md`
   per le voci sistemate; `COMMAND_LIST.md` (c'è `/clan lascia`);
   passi di prova in `VERIFICA_LIVE.md`.
4. Fine F1: giro di `cacciatore-bug`, `ottimizzatore` (PERF-1…7) e
   `guardiano-limiti`, poi suite completa.
5. **F2 musica** (#64, #45, #47, #48, #126): prima un nodo per bot.
6. **F3** backup (#68, #121) e iYokai Mod (#113).
7. Poi F5, F6, F7… come da milestone. Funzioni chieste il 05/10:
   #138, #139, #140, #141, #142 (voce: disegno completo nella issue).

## Cose pratiche
- Repository: `/home/claude/repo`. Copie di lavoro:
  `/home/claude/wt/<nome>`; database `iyokai_w<nome>`.
- **La macchina si riavvia senza avviso**: fare commit e push spesso.
  Dopo un riavvio: `service postgresql start`.
- Copie di lavoro ancora presenti e già unite: `s`, `d`, `e`, `ai`. Si
  tolgono dopo aver controllato che non abbiano file non salvati.
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
- Voce (#142): provare `scripts/prova_voce_qwen.py` sul suo PC e
  scegliere il campione di riferimento; dire com'è fatto il server
  (processore, memoria, scheda video).
- Creare l'applicazione **iYokai Mod** quando parte F3.
- Le prove di `VERIFICA_LIVE.md`.
- Da riprendere con lui: le idee di Gemini approvate in blocco; log su
  forum (un post per tipo, o per membro e per canale); funzioni del
  programma per PC solo per i premium; le 65 voci di `VOCI_OMESSE.md`
  nella SPEC.
