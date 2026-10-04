# CLAUDE.md — Istruzioni per chi lavora su questo repository

Bot Discord multi-tenant **iYokai** (Python 3.11, discord.py 2.7.1,
PostgreSQL/asyncpg, wavelink/Lavalink). Owner: iYokai.

## Da dove si parte

1. `.claude/orchestratore/STATO.md` — **la memoria del lavoro**: cosa è
   fatto, cosa è in corso, cosa viene dopo. Si legge per primo.
2. Le **issue di GitHub** — il lavoro da fare. Una milestone per fase
   (F1, F2, …), etichette per area e tipo. Non si tengono file di piano.
3. `CLAUDE_MANDATORY_TEST_RULES.md` — segreti e test live. Vincolante.
4. `revisione/02-piano/DECISIONI.md` — le scelte già fatte.
5. `revisione/01-analisi/LIMITI.md` — limiti di Discord e delle
   librerie, con la lista di controllo.
6. Il dettaglio, quando serve: `revisione/02-piano/MODIFICHE_ESISTENTE.md`,
   `revisione/02-piano/NUOVE_FUNZIONI.md`, `revisione/01-analisi/REVIEW.md`,
   `SPEC.md`.

## Come si lavora: orchestratore e agenti

La sessione principale fa da **orchestratore**
(`.claude/agents/orchestratore.md`). Gli altri agenti sono in
`.claude/agents/`: `correttore`, `cacciatore-bug`, `revisore`.

- L'orchestratore sceglie le issue, prepara per ogni agente una
  **scheda breve** (issue, file da toccare, regole che contano) e
  tiene aggiornato `STATO.md`. Un agente non rilegge tutto il progetto:
  parte dalla scheda e, se gli manca qualcosa o viene interrotto,
  **chiede all'orchestratore** da dove riprendere.
- Ogni agente lavora in una sua copia (`git worktree`) con un suo
  database di test. Mai due agenti sugli stessi file.
- **Niente arriva su `main` senza la revisione dell'orchestratore**:
  legge il diff, controlla la lista di `LIMITI.md`, fa lo smoke test.
- Al massimo 3 agenti insieme (2 CPU, e il limite di sessione).

## Test: smoke mirato, suite completa solo quando serve

- **Mentre si lavora a una voce:** solo i test di quella voce.
- **A gruppo chiuso o dopo un fix grosso:** smoke test sulle funzioni
  toccate: `python3 scripts/smoke.py` (sceglie da solo i test legati ai
  file cambiati, più i controlli sull'albero dei comandi).
- **Suite completa** (`python3 -m pytest -q`, circa 6 minuti): a fine
  fase, dopo modifiche a `core/database.py`, alle migrazioni, a
  `main.py` o a `tests/conftest.py`, e prima di un rilascio. Non a ogni
  commit.
- Prima il test che fallisce (per il motivo giusto), poi il fix.
- Database di test: `postgresql://postgres:testpass@127.0.0.1:5432/iyokai_test`
  (da `tests/conftest.py`; si cambia con `DATABASE_URL`). Se dà
  "connection refused": `service postgresql start`.
- Oggetti finti: quelli fedeli di `tests/support/discord_fakes.py`
  (`create_autospec`). Dove un finto nasconderebbe il problema si usano
  oggetti veri (un `commands.Bot` non collegato, un processo vero).
- Albero comandi completo: `tests/support/full_tree.py`
  (`importlib.import_module` + `setup(bot)`, mai `bot.load_extension`).
- Un test non prepara da solo i dati che dovrebbe scrivere il codice di
  produzione.
- Test "cricchetto" (`KNOWN_*`): quando sistemi un problema togli il
  nome dall'insieme. Non aggiungerne mai per far passare un test.
- Regole per gli smoke test: `tests/SMOKE_RULES.md`.
- Un test verde **non** è una verifica live: i passi da provare su
  Discord vanno in `revisione/03-verifica/VERIFICA_LIVE.md`.

## Regole di fondo

- **Non omettere mai una funzione richiesta dall'owner** (D18). Se
  Discord la impedisce così com'è, si realizza l'alternativa più vicina
  e lo si dice chiaramente. Niente "fuori scope".
- **Prima di progettare una funzione o un'interfaccia** si passa la
  lista di controllo di `revisione/01-analisi/LIMITI.md` (Parte 4):
  liste paginate o con tetto a 25, `max_length` sui testi liberi,
  `defer()` prima del lavoro lento, embed troncati, motivi ≤ 512.
- **Ogni impostazione passa da un solo punto del codice**, usato sia
  dai comandi sia dal futuro pannello web (D16).
- Le decisioni sono in `DECISIONI.md`. Se ne serve una nuova: si
  sceglie l'opzione consigliata, la si scrive lì con la data, si avvisa
  l'owner. Non si lascia una voce ferma.
- Revisione, non riscrittura: si cambia solo ciò che serve alla voce.
- Codice semplice: nomi chiari, funzioni corte, niente astrazioni che
  non servono subito.
- Un problema nuovo diventa **una issue** (etichette giuste, milestone
  della fase). Si sistema subito solo se è piccolo e con il suo test.

## Lingua

Tutto in **italiano**: testi per gli utenti, docstring, commenti,
commit, documentazione, issue. Frasi brevi e parole semplici.

## Commit, push e issue

- Autore: `Yokai Bot Dev <dev@yokai-bot.local>`. Messaggio in italiano,
  con `Refs #N`. In fondo le righe di attribuzione della sessione.
- Un codice (o un piccolo gruppo legato) per commit.
- Dopo il push: lo SHA locale e quello remoto devono coincidere.
- Un'issue si **chiude quando il fix è unito con i suoi test**, con un
  commento che dice il commit. Se serve ancora la prova su Discord si
  mette l'etichetta `verifica-live`; la toglie l'owner dopo la prova.
- Si aggiornano insieme al codice: `SPEC.md` (simbolo della voce),
  `COMMAND_LIST.md` se cambiano i comandi, `VERIFICA_LIVE.md` se serve
  una prova live, `STATO.md` a fine gruppo.

## Divieti

- Nessun segreto nel repository, nei commit, nelle issue o nei log
  (token, `DATABASE_URL`, password Lavalink, chiavi OAuth). Nei file di
  esempio solo segnaposto. Non committare `.env` né file in `logs/`.
- Nessun comando di primo livello nuovo prima della fase F7 (97 su 100)
  e nessun sotto-comando nuovo in `/owner` (25 su 25). Dopo F7: mai
  comandi di primo livello nuovi, al massimo 25 figli per gruppo.
- Non riscrivere la storia git senza richiesta esplicita dell'owner.
- Niente automazione di account utente (selfbot): viola le regole di
  Discord. Per le funzioni di quel tipo vale l'alternativa regolare
  descritta in `revisione/01-analisi/APP_UTENTE_E_DESKTOP.md`.

## Docstring in testa ai file

```
percorso/del/file.py
====================
A cosa serve (1–2 frasi).
Funzioni coperte: SPEC §x.y
Dipende da: … (solo se non ovvio)
```
Niente cronache di sessioni, niente "perché abbiamo scelto", niente nomi
di altre AI. Quando tocchi un file, sistema anche la sua docstring.
