# CLAUDE.md — Istruzioni per chi lavora su questo repository

> **PROPOSTA del 04/10/2026, non ancora in vigore.** Questo è il testo
> nuovo per `CLAUDE.md` nella cartella principale. Va applicato solo
> con l'approvazione dell'owner. Per applicarlo: copiare questo file al
> posto di `CLAUDE.md` e togliere questo riquadro.

Bot Discord multi-tenant **iYokai** (Python 3.11, discord.py 2.7.1,
PostgreSQL/asyncpg, wavelink/Lavalink). Owner: iYokai.

## File da leggere, in ordine di priorità

1. `CLAUDE_MANDATORY_TEST_RULES.md` — segreti e test live. **Vincolante,
   prevale su tutto il resto.**
2. `revisione/02-piano/PRIORITA.md` — cosa fare e in che ordine. È la
   tua lista di lavoro: segui le fasi nell'ordine scritto lì.
3. `revisione/02-piano/DECISIONI.md` — le scelte già fatte.
4. `revisione/01-analisi/LIMITI.md` — i limiti di Discord e la lista di
   controllo.
5. `revisione/02-piano/MODIFICHE_ESISTENTE.md` e `NUOVE_FUNZIONI.md` —
   il "come" di ogni voce.
6. `revisione/01-analisi/REVIEW.md` — il dettaglio di ogni problema
   (codici SEC-, BUG-, LC-, GDPR-, DB-, PERF-).
7. `SPEC.md` (cosa deve fare il bot), `PROGRESS.md` (storico),
   `COMMAND_LIST.md` (comandi), `BACKLOG.md` (proposte valutate).

L'indice di tutto è `revisione/README.md`.

## Lingua

Tutto in **italiano**: testi per gli utenti, docstring, commenti,
messaggi di commit, documentazione, commenti sulle issue. Frasi brevi
e parole semplici.

## Regole di fondo

- **Non omettere mai una funzione richiesta.** Se la piattaforma lo
  impedisce, proponi e pianifica l'alternativa più vicina che funziona.
  Niente "fuori scope", niente voci parcheggiate.
- **Prima di progettare una funzione o un'interfaccia, controlla
  `revisione/01-analisi/LIMITI.md`** (lista di controllo, Parte 4).
- **Le decisioni sono in `revisione/02-piano/DECISIONI.md`.** Se ne
  serve una nuova, scegli l'opzione consigliata, scrivila lì con la
  data e avvisa l'owner. Non lasciare una voce ferma in attesa.
- Questa è una revisione, non una riscrittura: cambia solo quello che
  serve per la voce su cui stai lavorando.
- Codice semplice e leggibile: nomi chiari, funzioni corte, niente
  astrazioni che non servono subito.
- Se trovi un problema nuovo, scrivilo in `REVIEW.md` (o in `LIMITI.md`
  se è un limite) con un codice nuovo e in `PRIORITA.md` nella fase
  giusta. Sistemalo subito solo se è piccolo, nello stesso file che
  stai già toccando, e con un test.

## Ciclo obbligatorio per ogni voce

1. Leggi la voce in `PRIORITA.md`, il suo "come" in
   `MODIFICHE_ESISTENTE.md` o `NUOVE_FUNZIONI.md`, e l'issue.
2. Scrivi il test **prima** del fix. Eseguilo e controlla che fallisca
   **per il motivo giusto**.
3. Fai il fix.
4. Esegui il test nuovo, poi la **suite completa due volte**:
   `python3 -m pytest -q`. Devono essere verdi entrambe.
5. Aggiorna:
   - `PRIORITA.md`: `[x]` con lo SHA del commit;
   - `SPEC.md`: simbolo della voce e conteggio in cima. `[x]` solo se
     la funzione è completa, testata e senza problemi aperti; scrivi
     "(da verificare live)" se serve la prova su Discord;
   - `PROGRESS.md`: una riga su cosa è cambiato;
   - `COMMAND_LIST.md` se cambiano i comandi;
   - `revisione/03-verifica/VERIFICA_LIVE.md` se il fix va provato su
     Discord, sul database reale o su Lavalink.
6. Commit: un codice (o un piccolo gruppo legato) per commit.
   - autore: `Yokai Bot Dev <dev@yokai-bot.local>`;
   - messaggio in italiano;
   - in fondo le righe di attribuzione indicate dal sistema per la
     sessione corrente.
7. `git push`, poi verifica che lo SHA locale e quello remoto
   coincidano.

## Issue

- Un'issue si **chiude quando il fix è unito con i suoi test**.
- Alla chiusura si lascia un commento con il commit.
- Se serve ancora una prova su Discord, si mette l'etichetta
  `verifica-live`. L'owner la toglie dopo la prova.
- Mai segreti e mai log con token nei commenti.

## Test

- Database locale di test: `postgresql://postgres:testpass@127.0.0.1:5432/iyokai_test`
  (impostato da `tests/conftest.py`). Se i test danno "connection
  refused": `service postgresql start`.
- Albero comandi completo nei test: `tests/support/full_tree.py`. Usa
  `importlib.import_module` + `setup(bot)`, **non** `bot.load_extension`.
- Oggetti finti: quelli fedeli di `tests/support/discord_fakes.py`
  (costruiti con `create_autospec`), non finti scritti a mano.
- Un test non deve mai preparare da solo i dati che il codice di
  produzione dovrebbe scrivere.
- Test "cricchetto" (`KNOWN_*`): quando sistemi un problema togli il
  nome dall'insieme nello stesso commit. Non aggiungere mai nomi per
  far passare un test.
- Un test verde **non** è una verifica live. Non scrivere mai
  "verificato su Discord" senza l'esito della prova dell'owner.

## Divieti

- Nessun segreto nel repository, nei commit, nelle issue o nei log:
  token Discord, `DATABASE_URL`, password Lavalink, chiavi OAuth o di
  cifratura. Nei file di esempio solo segnaposto.
- Non committare `.env` né file in `logs/`.
- Non aggiungere comandi di primo livello prima della fase F7 (siamo a
  97 su 100) e non aggiungere sotto-comandi a `/owner` (è a 25 su 25).
  Dopo F7: mai comandi di primo livello nuovi, al massimo 25 figli per
  gruppo.
- Non riscrivere la storia git (`push --force`, `rebase` su commit già
  pubblicati) senza richiesta esplicita dell'owner.

## Docstring in testa ai file

Formato fisso, breve:
```
percorso/del/file.py
====================
A cosa serve (1–2 frasi).
Funzioni coperte: SPEC §x.y
Dipende da: … (solo se non ovvio)
```
Niente cronache di sessioni, niente "perché abbiamo scelto", niente
nomi di altre AI. Quando tocchi un file, sistema anche la sua docstring.
