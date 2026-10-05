# STATO.md — Memoria dell'orchestratore

Aggiornato: **05/10/2026, mattina**. Si aggiorna a ogni gruppo chiuso.
Breve apposta: il dettaglio sta nelle issue e in `revisione/`.

## Dove siamo

- Il bot è in **zero server**. Nessuna prova live fatta: tutte le voci
  di `revisione/03-verifica/VERIFICA_LIVE.md` sono aperte.
- `main` è verde: 2676 test (ultima suite completa: 05/10).
- **Fatto:** rete di test (R-T), sicurezza lato logica (R0), migrazioni
  versionate, prima metà dei bug gravi (R1), tutta R1-bis (BUG-19…25,
  27, 30…33, SEC-18…22), intent `message_content` acceso, SPEC
  riallineata, documenti riordinati, issue e milestone create.
- **Superati dal nuovo disegno del backup (D8):** BUG-26, BUG-28,
  BUG-29. La pulizia dei server del Creator è disattivata apposta.

## Decisioni da ricordare (dettaglio in `revisione/02-piano/DECISIONI.md`)

- D8: il server di backup lo crea un admin; il **Creator resta** e lo
  porta e tiene allo stato corrente (messaggi in ordine via webhook, un
  invio alla volta).
- D15: nuovo bot **iYokai Mod** per log e moderazione, con sostituzione
  reciproca.
- D16: pannello web dopo il bot; ogni impostazione passa da un solo
  punto del codice.
- D17: il lavoro si traccia sulle issue. D18: nessuna funzione omessa.
- D2: `/mod` e `/modban` separati. D1: nomi comandi con traduzione
  nativa. D4: niente vecchi nomi. D5: YouTube via RSS.

## In corso

Niente a metà: tutto ciò che è stato fatto è su `main` e pubblicato.

## Fatto nell'ultimo giro (04–05/10)

- **F1, voci rapide (17):** limiti di `/poll`, `/report`, `/search`,
  sticky, heatmap, log dei ruoli, `badword-list`; l'anti-nuke non conta
  il bot; anti-raid, benvenuto e XP ignorano bot e messaggi di sistema;
  `/voice transfer`; `/security-score` effimero; durate oltre 5 anni;
  ID di `/alerts`; `OWNER_ID` non numerico; `NSFW_TOKEN` facoltativo.
- **Catalogo** delle funzioni mancanti: 1.452 voci in 18 file
  (`revisione/01-analisi/catalogo/`); le 939 non ancora in piano hanno
  una issue per area (#115–#132).
- **Scheletri** dei file per le funzioni nuove (102 file in `cogs/` e
  `core/`, con la nota su cosa scriverci) e nota "DA FARE" con il numero
  di issue in testa a 72 file esistenti.
- Issue: 56 create dal piano (#57–#112), più #113 (iYokai Mod); chiuse
  quelle risolte, con etichetta `verifica-live`.

## Coda (in ordine)

1. **F1 resto**, per area, tre agenti alla volta su file diversi:
   - sicurezza + automod: #58, #59, #30, #16;
   - moderazione + ticket + vocali + log: #57, #62, #63, #61, #34;
   - livelli ed economia: #65, #18, #23, #33, #35;
   - utility + feed + fun: #66, #67, #71;
   - core + owner: #69, #70.
   Dentro ogni issue le voci già fatte sono scritte nei commenti.
2. A fine F1: giro di `cacciatore-bug` sulle aree toccate, poi suite
   completa.
3. **F2 musica** (#64, #45, #47, #48, #126): prima il nodo wavelink per
   bot.
4. **F3** backup (#68, #121) e iYokai Mod (#113).
5. Poi F5, F6, F7… come da milestone.

## Cose pratiche

- Repository: `/home/claude/repo`. Copie di lavoro: `/home/claude/wt/<nome>`
  (`git worktree add`). Database per copia: `iyokai_w<nome>`.
- Postgres si ferma tra una sessione e l'altra: `service postgresql start`.
- Migrazioni: l'ultima è la `0004`. I file scheletro non contengono migrazioni: si creano quando si scrive la funzione. Riservare i numeri agli agenti
  prima di lanciarli (due agenti non devono usare lo stesso numero).
- 2 CPU: al massimo 3 agenti insieme; la suite completa dura 6 minuti da
  sola, molto di più con altri agenti al lavoro.
- Il limite di sessione può fermare gli agenti a metà: devono committare
  spesso. Un agente fermato si riprende con `git log` e `git status`
  della sua copia; non si rimuove una copia di lavoro prima di aver
  controllato che non abbia file non salvati.
- Da questo ambiente Discord, Aiven e Lavalink non sono raggiungibili:
  niente prove live qui.
- GitHub: `gh api repos/UwUiSky/iYokai-DS-BOT/...` (lettura e scrittura
  di issue, etichette e milestone funzionano).

## Serve dall'owner

- Accendere **Message Content Intent** nel Developer Portal (bot
  principale): senza, il bot non si collega.
- Nel `.env`: `ENVIRONMENT=development` oppure `production` (ora è
  obbligatoria).
- Creare l'applicazione **iYokai Mod** quando parte la fase F3.
- Le prove di `VERIFICA_LIVE.md`.
