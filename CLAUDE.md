# CLAUDE.md — Istruzioni per chi lavora su questo repository

Bot Discord multi-tenant **iYokai** (Python 3.11, discord.py 2.7.1,
PostgreSQL/asyncpg, wavelink/Lavalink). Owner: iYokai.

## File da leggere, in ordine di priorità

1. `CLAUDE_MANDATORY_TEST_RULES.md` — segreti e test live. **Vincolante,
   prevale su tutto il resto.**
2. `PIANO_FIX.md` — cosa fare, in che ordine e come. È la tua lista di
   lavoro: segui le fasi nell'ordine scritto lì.
3. `REVIEW.md` — il dettaglio di ogni problema (codici SEC-, BUG-, LC-,
   GDPR-, DB-, PERF-). Prima di sistemare una voce, rileggi la sua
   descrizione qui e l'issue GitHub collegata.
4. `SPEC.md` (cosa deve fare il bot), `PROGRESS.md` (storico),
   `COMMAND_LIST.md` (comandi), `BACKLOG.md` (cose rimandate).

## Lingua

Tutto in **italiano**: testi per gli utenti, docstring, commenti,
messaggi di commit, documentazione, commenti sulle issue.

## Metodo: questa è una revisione, non una riscrittura

- Il codice esiste e in gran parte funziona. Cambia solo quello che
  serve per la voce su cui stai lavorando.
- Codice semplice e leggibile: nomi chiari, funzioni corte, niente
  astrazioni che non servono subito. Deve capirlo anche chi è alle
  prime armi.
- Se trovi un bug nuovo, aggiungilo a `REVIEW.md` con un codice nuovo e
  a `PIANO_FIX.md` nella fase giusta. Sistemalo subito solo se è piccolo,
  nello stesso file che stai già toccando, e con un test.
- Se una voce è `[B]` (serve una decisione dell'owner, vedi
  `PIANO_FIX.md` §D), chiedi all'owner e passa alla voce successiva.
  Non decidere al suo posto.

## Ciclo obbligatorio per ogni voce

1. Leggi la voce in `PIANO_FIX.md`, in `REVIEW.md` e nell'issue.
2. Scrivi il test **prima** del fix. Eseguilo e controlla che fallisca
   **per il motivo giusto** (non per un import o una fixture rotta).
3. Fai il fix.
4. Esegui il test nuovo, poi la **suite completa due volte**:
   `python3 -m pytest -q`. Devono essere verdi entrambe.
5. Aggiorna:
   - `PIANO_FIX.md`: `[x]` con lo SHA del commit;
   - `SPEC.md`: `[x]` solo se la funzione è davvero completa e testata;
     se serve la prova su Discord scrivi "(da verificare live)";
   - `PROGRESS.md`: una riga su cosa è cambiato;
   - `COMMAND_LIST.md` se cambiano i comandi;
   - `VERIFICA_LIVE.md` se il fix va provato su Discord, sul database
     reale o su Lavalink.
6. Commit: un codice REVIEW (o un piccolo gruppo legato) per commit.
   - autore: `Yokai Bot Dev <dev@yokai-bot.local>`;
   - messaggio in italiano, con `Refs #N` per le issue collegate;
   - **mai** `Closes #N` o `Fixes #N`: le issue si chiudono solo dopo il
     test live, dall'owner;
   - in fondo le righe di attribuzione indicate dal sistema per la
     sessione corrente.
7. `git push`, poi verifica che lo SHA locale e quello remoto
   coincidano (`git rev-parse HEAD` e `git ls-remote origin main`).
8. Se vuoi, commenta l'issue con lo SHA e i passi della verifica live
   (mai segreti, mai log con token).

## Test

- Database locale di test: `postgresql://postgres:testpass@127.0.0.1:5432/iyokai_test`
  (impostato da `tests/conftest.py`). Se i test danno "connection
  refused", il servizio si è fermato: `service postgresql start`.
- Albero comandi completo nei test: `tests/support/full_tree.py`. Usa
  `importlib.import_module` + `setup(bot)`, **non** `bot.load_extension`
  (ri-esegue i moduli e rompe i singleton degli altri test).
- Oggetti finti: usa quelli fedeli di `tests/support/discord_fakes.py`
  (costruiti con `create_autospec`), non finti scritti a mano. Un finto
  scritto a mano accetta anche chiamate sbagliate: così BUG-1 è rimasto
  nascosto.
- Un test non deve mai preparare da solo i dati che il codice di
  produzione dovrebbe scrivere (così BUG-3 è rimasto nascosto).
- Test "cricchetto" (`KNOWN_*`): quando sistemi un problema togli il
  nome dall'insieme nello stesso commit. Non aggiungere mai nomi per
  far passare un test.
- Un test verde **non** è una verifica live. Non scrivere mai "verificato
  su Discord", "funziona in produzione" o simili senza l'esito del test
  live dell'owner.

## Divieti

- Nessun segreto nel repository, nei commit, nelle issue o nei log:
  token Discord, `DATABASE_URL`, password Lavalink, chiavi OAuth o di
  cifratura. Nei file di esempio solo segnaposto.
- Non committare `.env` né file in `logs/`.
- Non aggiungere comandi top-level prima della fase R5 (siamo a 97 su
  100) e non aggiungere sotto-comandi a `/owner` (è a 25 su 25).
- Non riscrivere la storia git (`push --force`, `rebase` su commit già
  pubblicati) senza richiesta esplicita dell'owner.
- Fuori scope: motore AI (#50) e confronto con altri bot (#52).

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
