# Regole comuni a tutti gli agenti

Ogni agente legge **questo file, la sua memoria e la sua scheda**. Poi
lavora. Il resto si apre solo quando serve alla voce in corso.

## 1. Spendere pochi token

1. **All'avvio leggi solo:** questo file → `.claude/memoria/<tuo nome>.md`
   → la scheda dell'orchestratore. Niente giro del progetto.
2. **Cerca, poi leggi.** Prima `Grep`/`Glob` per trovare il punto, poi
   `Read` con `offset` e `limit` su quel pezzo. Un file oltre 300 righe
   non si legge intero.
3. **Non rileggere** un file già letto in questa sessione, né dopo una
   modifica riuscita.
4. **Documenti grossi: solo la riga che serve.** Si cerca il codice
   (`M 3.14`, `NF-24`, `LIM-8`, `§25.3`, `AI-R-026`) con `Grep`. Mai
   interi: `SPEC.md`, `REVIEW.md`, `MODIFICHE_ESISTENTE.md`,
   `NUOVE_FUNZIONI.md`, `FUNZIONI_AI.md`. Mai aperti senza un motivo
   scritto in scheda: `revisione/01-analisi/catalogo/`, `revisione/archivio/`.
5. **Uscite corte.** `pytest -q -x --no-header <file>` solo sui test
   della voce; `git diff --stat` prima del diff; `| tail -20` sui
   comandi lunghi. Mai la suite completa (la decide l'orchestratore).
6. **Letture indipendenti nello stesso passo**, non una alla volta.
7. **Un dubbio = una domanda di una riga all'orchestratore**, non
   un'esplorazione.
8. **Non lanciare altri agenti.** Lo fa solo l'orchestratore.
9. **Ciò che un test può controllare, lo controlla un test.** Un
   limite o una regola diventati test non costano più token a nessuno.
10. **Rapporto finale: 40 righe al massimo.** Riferimenti `file:riga` e
    numeri di commit; niente riassunti del codice.

## 2. Memoria compressa

Ogni agente ha **un file suo**: `.claude/memoria/<nome>.md`. È separato
dalle istruzioni (`.claude/agents/<nome>.md`), che non si toccano
mentre si lavora.

- **Tetto: 60 righe** (120 per l'orchestratore). La memoria si
  **riscrive**, non si allunga: quando è piena si comprime il vecchio.
- **Sezioni fisse**, in quest'ordine (modello in `_MODELLO.md`):
  `Aggiornata` · `In corso` · `Fatto` · `Cose imparate` · `Aperto`.
- `In corso` dice il **prossimo passo esatto** (file, funzione, test da
  far passare): chi riprende non deve capire, deve solo continuare.
- `Fatto`: una riga per voce con il commit. I giri più vecchi degli
  ultimi due diventano una riga sola.
- `Cose imparate`: le trappole dell'area che valgono anche domani (al
  massimo 15). È la parte che fa risparmiare di più: si cura.
- Niente segreti, niente pezzi di codice, niente cronaca.

**Quando si scrive:**
1. dopo **ogni voce chiusa**, nello stesso commit della voce;
2. **prima di fermarsi**, sempre (vedi sotto);
3. quando si scopre una trappola nuova.

## 3. Fermarsi bene

Un agente non vede quanto gli resta: può essere interrotto in ogni
momento. Per questo la memoria si salva a ogni voce, non alla fine.

- **All'inizio fai la previsione** e scrivila in `In corso`: quante
  voci conti di chiudere in questo giro (di norma **da 3 a 6**) e a
  quale ti fermi.
- **Fermati da solo**, salvando la memoria e chiudendo con il rapporto,
  quando succede una di queste cose:
  - hai finito le voci previste;
  - la conversazione è stata compattata (segno che il contesto è pieno);
  - sei oltre 60 passi dall'ultimo salvataggio della memoria;
  - la stessa prova fallisce per la terza volta: scrivi cosa hai
    provato e chiedi all'orchestratore.
- Meglio tre voci chiuse e salvate che sei a metà.

## 4. Riprendere

Leggi la memoria, poi `git log --oneline -5` e `git status --short`
della tua copia di lavoro. Continua dal "prossimo passo". Non
ricominciare, non rileggere ciò che la memoria già dice.

## 5. Quaderni dei rilievi

Gli agenti di controllo scrivono ciò che trovano, **mentre lavorano**,
in `.claude/rapporti/<quaderno>.md`: una riga per rilievo (data,
`file:riga`, cosa, gravità, stato). Un rilievo confermato diventa una
**issue** e nella riga va il numero. Le righe risolte da più di un giro
si tolgono (restano nella storia di git).

## 6. Regole del progetto (in breve)

- Tutto in **italiano**, frasi brevi.
- Test prima del codice; oggetti finti fedeli
  (`tests/support/discord_fakes.py`) o veri.
- Prima di disegnare un comando o un'interfaccia: lista di controllo di
  `revisione/01-analisi/LIMITI.md` Parte 4 (o si chiede al
  `guardiano-limiti`).
- Mai omettere una funzione chiesta dall'owner (D18).
- Nessun segreto in file, commit, issue, memoria o rapporti.
- Commit: autore `Yokai Bot Dev <dev@yokai-bot.local>`, messaggio in
  italiano con `Refs #N`, righe di attribuzione in fondo. **Mai push**:
  lo fa l'orchestratore.
- Si toccano solo i file della scheda, più la propria memoria e il
  proprio quaderno.
