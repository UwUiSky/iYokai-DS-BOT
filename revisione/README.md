# revisione/ — La revisione di iYokai, in ordine

Questa cartella contiene **tutti** i documenti della revisione del
bot. È separata dal codice: qui non c'è niente che il bot esegue.

## Stato in 10 righe (04/10/2026)

1. Il bot è in **zero server**. Niente è ancora stato provato su Discord vero.
2. Fatte le fasi di correzione R-T, R0, DB, metà di R1 e tutta R1-bis. Suite: 2614 test verdi.
3. `SPEC.md` ora dice la verità: 97 voci fatte, 143 parziali, 126 da fare, 7 scartate (373 in tutto).
4. L'intent `message_content` è acceso nel codice. **L'owner deve attivarlo nel Developer Portal.**
5. Il **backup** com'era pensato è impossibile (Discord non lascia creare server ai bot). Si rifà senza il bot Creator: decisione D8.
6. I 5 **bot musicali** quasi certamente non suonano: usano la sessione del bot principale. Si corregge con la decisione D10.
7. Trovati **57 punti** dove il codice supera un limite di Discord o di un servizio esterno (codici LIM).
8. Mancano funzioni che gli altri bot hanno: pannello web, ruolo automatico, starboard, comandi personalizzati, immagini di benvenuto e di livello. Sono 41 schede (codici NF).
9. **Nessuna funzione richiesta è stata tolta dal piano.** Anche il motore AI e il confronto con gli altri bot sono dentro.
10. Il bot non va invitato in server veri prima delle fasi F1, F5 e F7.

## In che ordine leggere

| # | File | A cosa serve |
|---|---|---|
| 1 | [`02-piano/PRIORITA.md`](02-piano/PRIORITA.md) | **Parti da qui.** Cosa fare e in che ordine (fasi F1–F14). |
| 2 | [`02-piano/DECISIONI.md`](02-piano/DECISIONI.md) | Le scelte già fatte (D1–D14). Non vanno richieste di nuovo. |
| 3 | [`01-analisi/LIMITI.md`](01-analisi/LIMITI.md) | I limiti da rispettare e la lista di controllo prima di scrivere una funzione. |
| 4 | [`02-piano/MODIFICHE_ESISTENTE.md`](02-piano/MODIFICHE_ESISTENTE.md) | Cosa cambiare in ciò che esiste già, area per area. |
| 5 | [`02-piano/NUOVE_FUNZIONI.md`](02-piano/NUOVE_FUNZIONI.md) | Le funzioni da aggiungere, con i file da creare. |
| 6 | [`01-analisi/REVIEW.md`](01-analisi/REVIEW.md) | Il dettaglio di ogni problema trovato (codici SEC, BUG, LC, GDPR, DB, PERF). |
| 7 | [`01-analisi/CONFRONTO_BOT.md`](01-analisi/CONFRONTO_BOT.md) | iYokai a confronto con gli altri bot Discord. |
| 8 | [`03-verifica/VERIFICA_LIVE.md`](03-verifica/VERIFICA_LIVE.md) | Le prove da fare con il bot vero, passo per passo. |

Fuori da questa cartella, nella cartella principale:

| File | A cosa serve |
|---|---|
| [`../SPEC.md`](../SPEC.md) | Cosa deve fare il bot e lo stato di ogni voce. In cima c'è il conteggio. |
| [`../CLAUDE.md`](../CLAUDE.md) | Istruzioni per chi lavora sul repository. |
| [`../CLAUDE_MANDATORY_TEST_RULES.md`](../CLAUDE_MANDATORY_TEST_RULES.md) | Regole su segreti e prove live. Prevale su tutto. |
| [`../COMMAND_LIST.md`](../COMMAND_LIST.md) | Elenco dei comandi di oggi. |
| [`../BACKLOG.md`](../BACKLOG.md) | Proposte di altre AI, valutate. |
| [`../PROGRESS.md`](../PROGRESS.md) | Cronologia del progetto. |

## Cosa c'è in ogni cartella

```
revisione/
  README.md                 questo indice
  CLAUDE.proposto.md        nuova versione di CLAUDE.md, da approvare (vedi sotto)
  01-analisi/
    REVIEW.md               revisione del codice del 28/09 e del 04/10
    LIMITI.md               limiti di Discord, librerie e servizi; codici LIM-1…LIM-57
    CONFRONTO_BOT.md        confronto con gli altri bot (issue #52)
  02-piano/
    PRIORITA.md             ordine di lavoro, fasi F0–F14
    MODIFICHE_ESISTENTE.md  cosa cambiare in ciò che esiste
    NUOVE_FUNZIONI.md       funzioni da aggiungere, codici NF-01…NF-41
    DECISIONI.md            decisioni D1…D14
    PIANO_FIX.md            vecchio piano (storico)
  03-verifica/
    VERIFICA_LIVE.md        prove da fare su Discord vero
  archivio/                 documenti vecchi, non più da usare
    HANDOFF_GROK.md
    ISSUE_CLOSURES_ADVISOR.md
    RESTORE_MD_INSTRUCTIONS.md
    backup-md/
```

## I codici, in breve

| Codice | Vuol dire | Dove è spiegato |
|---|---|---|
| SEC-n | problema di sicurezza | `01-analisi/REVIEW.md` |
| BUG-n | funzione rotta | `01-analisi/REVIEW.md` |
| LC-n | problema di interazioni, listener o cicli | `01-analisi/REVIEW.md` §15 |
| GDPR-n, DB-n, PERF-n | dati, database, prestazioni | `01-analisi/REVIEW.md` §14, §10 |
| RT-n | rete di test | `02-piano/PIANO_FIX.md` |
| LIM-n | limite superato o ignorato | `01-analisi/LIMITI.md` Parte 3 |
| NF-n | funzione nuova | `02-piano/NUOVE_FUNZIONI.md` |
| D-n | decisione presa | `02-piano/DECISIONI.md` |
| F-n | fase di lavoro | `02-piano/PRIORITA.md` |
| → M x.y | riga di una modifica | `02-piano/MODIFICHE_ESISTENTE.md` |

## Dove sono finiti i file di prima

| Prima (cartella principale) | Adesso |
|---|---|
| `REVIEW.md` | `revisione/01-analisi/REVIEW.md` |
| `PIANO_FIX.md` | `revisione/02-piano/PIANO_FIX.md` (storico; vale `PRIORITA.md`) |
| `VERIFICA_LIVE.md` | `revisione/03-verifica/VERIFICA_LIVE.md` |
| `HANDOFF_GROK.md`, `ISSUE_CLOSURES_ADVISOR.md`, `RESTORE_MD_INSTRUCTIONS.md`, `backup-md/` | `revisione/archivio/` |

I nomi dei file non sono cambiati: i commenti nel codice che citano
`REVIEW.md`, `PIANO_FIX.md` o `VERIFICA_LIVE.md` restano validi.

## Una cosa da approvare: `CLAUDE.md`

`CLAUDE.md` (cartella principale) **non è stato modificato** in questa
riorganizzazione: è il file di istruzioni del repository, e va cambiato
solo con l'approvazione diretta dell'owner. Per questo cita ancora
`PIANO_FIX.md` e i vecchi percorsi.

La versione nuova, già pronta, è in
[`CLAUDE.proposto.md`](CLAUDE.proposto.md). Per applicarla basta
copiarla al posto di `CLAUDE.md`. Finché non viene applicata, vale la
tabella "Dove sono finiti i file di prima" qui sopra.

## Regole di questa cartella

- Un problema nuovo si scrive in `01-analisi/REVIEW.md` (o in
  `LIMITI.md` se è un limite) con un codice nuovo, e in
  `02-piano/PRIORITA.md` nella fase giusta.
- Una decisione nuova si scrive in `02-piano/DECISIONI.md`.
- Quando una voce è fatta: `[x]` con lo SHA in `PRIORITA.md`, simbolo
  aggiornato in `SPEC.md`, e i passi di prova in `VERIFICA_LIVE.md` se
  serve Discord.
- Mai segreti qui dentro: niente token, password o indirizzi di
  database.
