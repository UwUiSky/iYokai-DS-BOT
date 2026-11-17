# Istruzioni operative

Per chiunque riprenda il lavoro su iYokai: l'owner, un agente Sonnet, un Opus,
un'altra versione di Claude. Leggi questo file per primo: ti dice cosa fare,
in che ordine, e quando una cosa è finita.

## 1. In due minuti

- **Cosa è:** bot Discord multi-server (Python 3.11, discord.py, PostgreSQL,
  Lavalink) con pannello web, app installabile sull'utente e programma per PC.
- **Obiettivo dell'owner:** bot **finito**, non parziale: stabile, sicuro,
  protetto. Poi verifica completa e messa in linea.
- **Dove siamo:** `.claude/memoria/orchestratore.md` (prima sezione).
- **Cosa manca del catalogo:** `revisione/01-analisi/catalogo/STATO.md`
  (generato; si aggiorna con `python3 scripts/stato_catalogo.py`).
- **Regole vincolanti:** `.claude/CLAUDE.md`, `.claude/regole/COMUNI.md`,
  `.claude/regole/SICUREZZA.md`.

## 2. Chi fa cosa (regola dell'owner, 16/11/2026)

| Ruolo | Modello | Compito |
|---|---|---|
| Sviluppo | Sonnet (agenti `dev-*`) | Scrive codice e test di un blocco |
| Revisione finale | Opus o superiore (sessione principale) | Legge tutto il diff: funziona, bug, sicurezza, injection. Corregge i difetti piccoli |
| Owner | persona | Decide, prova su Discord, mette in linea |

- Si risparmiano richieste: un agente alla volta per area, schede brevi, niente
  riletture del progetto, niente suite completa durante lo sviluppo.
- La revisione **non si salta mai**, anche se il blocco è piccolo.

## 3. Preparare la macchina (una volta per sessione)

```bash
cd /percorso/iYokai-DS-BOT
uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r requirements.lock pytest pytest-asyncio
pg_ctlcluster 16 main start        # oppure: service postgresql start
su postgres -c "psql -c \"ALTER USER postgres PASSWORD 'testpass'\""
su postgres -c "createdb iyokai_w<nome>"     # un database per ramo
git config user.name "Yokai Bot Dev" && git config user.email "dev@yokai-bot.local"
```

- In **ogni** comando di test: `export DATABASE_URL=postgresql://postgres:testpass@127.0.0.1:5432/iyokai_w<nome>`.
- Un ramo per blocco, in una copia a parte: `git worktree add ../wt-<nome> -b feat/<nome> main`.
- La macchina può riavviarsi: commit e push spesso; dopo un riavvio riaccendere PostgreSQL.
- Per le conversioni servono `ffmpeg` e `ffprobe`.

## 4. Il giro di un blocco

1. **Scegli** il blocco: un'area con l'issue aperta in `STATO.md`, 4–6 voci
   vicine tra loro. Leggi le righe del catalogo e la memoria dell'area
   (`.claude/memoria/dev-<area>.md`).
2. **Disegna** in dieci righe: comandi, opzioni, tetti, permessi, tabelle. Passa
   la lista di controllo di `revisione/01-analisi/LIMITI.md` (Parte 4) e
   `.claude/regole/SICUREZZA.md`.
3. **Scheda breve** all'agente di sviluppo (Sonnet): ambiente, disegno, test da
   lanciare, cosa consegnare. Modello di scheda: §7.
4. **Sviluppo:** prima il test che fallisce, poi il codice. Ogni impostazione dal
   punto unico (`SETTINGS_SCHEMA`, `core/config_impostazioni.py`). Testi in
   `locales/it` e `locales/en-US`; descrizioni inglesi dei comandi in
   `locales/en-US/comandi.json`. Il codice della voce (es. `MUS-030`) va in un
   commento o nel nome di un test: è così che `STATO.md` la vede fatta.
5. **Revisione finale** (Opus): tutto il diff, con le domande di
   `SICUREZZA.md` §9. Difetto = test che fallisce + correzione.
6. **Unione:** `git merge --no-ff` in `main` con messaggio
   `Merge <ramo>: … (Refs #N)`, poi i test delle parti toccate, poi push.
   Lo SHA locale e quello remoto devono coincidere.
7. **Carte:** `revisione/SPEC.md`, `COMMAND_LIST*.md`
   (`scripts/generate_command_list.py`), `VERIFICA_LIVE.md`, la memoria
   dell'area, la memoria dell'orchestratore, `REGISTRO_RISOLTE.md`,
   `python3 scripts/stato_catalogo.py`. Issue chiusa solo a lavoro unito.

## 5. Quando una voce è finita

- Fa ciò che dice il catalogo, o l'alternativa più vicina scritta chiaramente.
- Ha test che fallivano prima e passano dopo, anche per i casi storti.
- Passa `SICUREZZA.md` e i limiti di Discord (`tests/test_command_tree_invariants.py`).
- Testi in italiano e inglese; `tests/test_i18n*.py` e
  `tests/test_command_translator.py` verdi.
- Documenti aggiornati (punto 7 del giro) e prova live scritta in `VERIFICA_LIVE.md`.
- Unita in `main` e pubblicata.

## 6. Ordine del lavoro rimasto

1. Chiudere ciò che è aperto: #160 (allegati), #165, punti aperti della musica B3.
2. Sicurezza: issue #150 (comandi che eseguono codice, voci della revisione).
3. Catalogo, aree con l'issue aperta, dalla più usata: benvenuto e ruoli (#123),
   livelli (#124), musica (#126), log (#119), vocali (#127), alert (#129),
   statistiche (#130), configurazione e pannello (#122), economia e giochi (#125),
   sicurezza (#117).
4. Issue fuori catalogo: #142 voce, #94 NSFW, #77 lingue, #91 pannello, #151
   premium, #157, #70, #67, #154.
5. Aree con l'issue chiusa: controllare a mano le voci «non trovate» di `STATO.md`.
6. Alla fine, una volta sola: suite completa (`python3 -m pytest -q`, con
   `nohup`), correzioni, `cacciatore-bug` e `revisore-capo` su tutto, poi prove
   live dell'owner e messa in linea.

## 7. Modello di scheda per l'agente di sviluppo

```
SCHEDA — issue #N, blocco «…» (codici …).
Leggi .claude/regole/COMUNI.md, .claude/regole/SICUREZZA.md e la tua memoria. Non rileggere il progetto.
AMBIENTE: copia /…/wt-<nome>, ramo feat/<nome>; Python …/.venv/bin/python;
  DATABASE_URL=…/iyokai_w<nome> in ogni comando. Solo i test della voce. Niente push, niente unione.
DISEGNO: comandi, opzioni con tetti, permessi, impostazioni, tabelle e numero di migrazione.
REGOLE: prima il test che fallisce; scelta non coperta = la più prudente, scritta in DECISIONI.
CONSEGNA: commit, file, test lanciati con l'esito esatto, non fatto, dubbi di sicurezza.
```

## 8. Errori già visti (non ripeterli)

- Salvare o rimandare l'originale di un allegato «perché è un'immagine pulita».
- Mostrare un nome di file senza pulirlo: accenti gravi e parentesi scrivono link nei log.
- Uccidere un processo figlio e poi aspettarlo senza svuotare il tubo: resta appeso.
- Accendere uno stato prima del controllo che può fallire (mescola fisso).
- Togliere brani dalla coda e dimenticare lo storico con il loop acceso.
- Dimenticare le descrizioni inglesi dei comandi nuovi.
- Modello `.env` in modalità sviluppo: accende `eval` e sblocca il premium.
- Fidarsi di un elenco vuoto (membri del canale, risultati): un vuoto da errore
  non deve far cancellare tutto.
