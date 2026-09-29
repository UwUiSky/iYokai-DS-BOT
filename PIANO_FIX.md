# PIANO_FIX.md — Ordini di lavoro per la correzione di iYokai

Questo file dice **cosa** sistemare, **in che ordine** e **come**. Il
*perché* e i dettagli di ogni problema stanno in `REVIEW.md` (i codici
SEC-/BUG-/LC-/GDPR-/DB-/PERF- rimandano lì). Le issue GitHub sono
indicate con `#N`.

Regole di processo: `CLAUDE.md`. Regole sui test live e sui segreti:
`CLAUDE_MANDATORY_TEST_RULES.md` (vincolante, prevale su tutto).

Stato delle voci:
- `[ ]` da fare
- `[x]` fatto e testato offline (scrivi accanto lo SHA del commit)
- `[B]` bloccato da una decisione dell'owner (vedi §D)

Una voce `[x]` **non** è verificata live: quella verifica si traccia
in `VERIFICA_LIVE.md` (§V).

---

## 0. Analisi incrociata: REVIEW.md contro le 53 issue

Le issue #1–#35 sono lo stesso elenco di REVIEW.md, trovato in modo
indipendente. Le #36–#53 aggiungono decisioni e tre problemi nuovi.
Controllato di nuovo sul codice il 28/09:

| Punto | Esito |
|---|---|
| Moduli registrati | **32**, non ~37 come dicono #38/#43: le issue contano le righe `registry.register(`, alcune registrano lo stesso nome. REVIEW.md è corretto. |
| `/owner` | 25 sotto-comandi su 25 (L2). Non aggiungere niente a `/owner` prima di R5. |
| `automod` | 22 sotto-comandi su 25. |
| Top-level | 97 su 100. Non aggiungere comandi top-level prima di R5: usa sotto-comandi di gruppi esistenti. |
| BUG-17 / #33 (drop cliccato due volte) | **Probabile falso positivo.** In `cogs/leveling/leveling.py` tra `if self.claimed_by is not None` e `self.claimed_by = …` non c'è nessun `await`, quindi in asyncio il blocco è atomico. Si conferma con un test (fase R1), non con un fix. |
| #36 "log cancellati/modificati correttamente disattivati" | Superato dalla decisione dell'owner: `message_content` si accende e quei log vanno costruiti (R4). |
| #42 fix proposto "`asyncio.sleep(10)` poi `delete()`" | Va bene, ma dentro un task separato con log degli errori, non bloccando la risposta (vedi R1). |
| #47 `application.yml` | Le versioni dei plugin nell'issue vanno ricontrollate sulle pagine ufficiali al momento di scriverlo. Il percorso dei file locali è quello **dentro il container Lavalink** (`/audio/local`), non quello della macchina del bot (vedi BUG-10). |
| #50 (AI), #52 (confronto con altri bot) | Fuori scope di questo piano. Non aprire lavori su questi. |
| Bot senza utenti (regole live §2.4) | Nessun server reale usa il bot: **non serve retrocompatibilità** dei nomi comandi (decisione D4 raccomandata "nessuna") e la sicurezza sulla superficie dei comandi (SEC-1) si risolve una volta sola in R5 invece di decorare 97 comandi due volte. |

**Cambio d'ordine rispetto a REVIEW.md §17:** le migrazioni versionate
(DB-1) passano **prima** di R1, perché diversi fix di R1 aggiungono
vincoli `UNIQUE` o colonne a tabelle esistenti, e oggi lo schema sa
solo "crea se non esiste" / "aggiungi colonna se non esiste".

Ordine finale:

```
R-T  rete di test (resto)
R0   sicurezza lato logica
DB   migrazioni versionate
R1   bug che rompono funzioni
R1b  SPEC onesta
R2   dati e GDPR
R3   router dei canali
R4   message_content e log dei messaggi
R5   nuova struttura comandi (+ permessi e visibilità)
R6   lingue e /cerca-comando
R7   NSFW
Continuo: docstring, codice morto, prestazioni
```

---

**NOTA RESTORE:** contenuto completo in `git show 585d1450:PIANO_FIX.md`.
Questo file è stato ripristinato; se il body risultasse tronca, rieseguire:
`git show 585d14509685385d4db1f15ef90a80c920f766f4:PIANO_FIX.md > PIANO_FIX.md`
