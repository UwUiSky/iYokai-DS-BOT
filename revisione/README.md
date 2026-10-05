# revisione/ — L'analisi di iYokai, in ordine

Qui c'è **l'analisi dettagliata** del bot: cosa non va nel codice, quali
limiti di Discord contano, come si confronta con gli altri bot, cosa
cambiare e cosa aggiungere. Non c'è niente che il bot esegue.

Il **lavoro da fare** non sta in questi file: sta nelle
[issue di GitHub](https://github.com/UwUiSky/iYokai-DS-BOT/issues), una
[milestone](https://github.com/UwUiSky/iYokai-DS-BOT/milestones) per
fase. Ogni issue rimanda qui per il dettaglio.

## Cosa c'è

```
revisione/
  SPEC.md                      cosa deve fare il bot e stato di ogni voce
  01-analisi/
    REVIEW.md                  i problemi trovati nel codice (SEC, BUG, LC, GDPR, DB, PERF)
    LIMITI.md                  limiti di Discord, librerie e servizi (LIM) + lista di controllo
    CONFRONTO_BOT.md           iYokai a confronto con gli altri bot
    APP_UTENTE_E_DESKTOP.md    cosa offrire dove il bot non c'è e con il programma per PC
    FUNZIONI_AI.md             tutte le funzioni AI discusse, con la fonte e come farle (AI-R)
    VOCI_OMESSE.md             funzioni non AI discusse e assenti da ogni lista (OM)
    catalogo/                  ogni funzione degli altri bot che a iYokai manca, voce per voce
  02-piano/
    DECISIONI.md               le scelte già fatte (D1…D18)
    MODIFICHE_ESISTENTE.md     cosa cambiare in ciò che esiste, area per area (M x.y)
    NUOVE_FUNZIONI.md          le funzioni da aggiungere e i file da creare (NF)
    VOCE_YOKAI.md              la voce del bot: specifica dell'owner e note per realizzarla
  03-verifica/
    VERIFICA_LIVE.md           le prove da fare con il bot vero, passo per passo
    CLAUDE_MANDATORY_TEST_RULES.md   regole su segreti e prove live (vincolanti)
  archivio/                    documenti vecchi, solo storico
```

## In che ordine leggere

| Se vuoi sapere… | Leggi |
|---|---|
| A che punto siamo | `.claude/memoria/orchestratore.md` e le milestone |
| Cosa è stato deciso | [`02-piano/DECISIONI.md`](02-piano/DECISIONI.md) |
| Cosa deve fare il bot e cosa fa oggi | [`SPEC.md`](SPEC.md) (in cima c'è il conteggio) |
| Perché una cosa non funziona | [`01-analisi/REVIEW.md`](01-analisi/REVIEW.md) |
| Quali limiti rispettare | [`01-analisi/LIMITI.md`](01-analisi/LIMITI.md) |
| Cosa hanno gli altri bot | [`01-analisi/CONFRONTO_BOT.md`](01-analisi/CONFRONTO_BOT.md) e `01-analisi/catalogo/` |
| Cosa si può fare senza il bot nel server, o da PC | [`01-analisi/APP_UTENTE_E_DESKTOP.md`](01-analisi/APP_UTENTE_E_DESKTOP.md) |
| Quali funzioni AI sono state discusse e dove sono finite | [`01-analisi/FUNZIONI_AI.md`](01-analisi/FUNZIONI_AI.md) |
| Quali funzioni discusse non stanno in nessuna lista | [`01-analisi/VOCI_OMESSE.md`](01-analisi/VOCI_OMESSE.md) |
| Come si sistema una cosa che esiste | [`02-piano/MODIFICHE_ESISTENTE.md`](02-piano/MODIFICHE_ESISTENTE.md) |
| Come si aggiunge una funzione nuova | [`02-piano/NUOVE_FUNZIONI.md`](02-piano/NUOVE_FUNZIONI.md) |
| Cosa provare su Discord | [`03-verifica/VERIFICA_LIVE.md`](03-verifica/VERIFICA_LIVE.md) |

## Le fasi (milestone su GitHub)

| Fase | Contenuto |
|---|---|
| F1 | Bug e limiti: ogni funzione che esiste fa ciò che dice |
| F2 | Musica: i 5 bot musicali suonano davvero, radio, Lavalink |
| F3 | Backup con il Creator che tiene aggiornato il server; bot iYokai Mod |
| F5 | Dati e GDPR |
| F6 | Router dei canali, log dei messaggi, snipe |
| F7 | Nuova struttura dei comandi, permessi e visibilità |
| F8 | Lingue e ricerca dei comandi |
| F9 | Funzioni nuove, primo gruppo |
| F10 | Pannello web |
| F11 | NSFW |
| F12 | Motore AI |
| F13 | Funzioni nuove, secondo gruppo; app utente; Desktop |
| F14 | Idee rimandate |

(F4, "SPEC onesta", è fatta.)

## I codici

| Codice | Vuol dire | Dove è spiegato |
|---|---|---|
| SEC-n, BUG-n, LC-n, GDPR-n, DB-n, PERF-n | problemi nel codice | `01-analisi/REVIEW.md` |
| LIM-n | limite superato o ignorato | `01-analisi/LIMITI.md` Parte 3 |
| M x.y | modifica a ciò che esiste | `02-piano/MODIFICHE_ESISTENTE.md` |
| NF-n | funzione nuova | `02-piano/NUOVE_FUNZIONI.md` |
| AI-R-n | funzione AI discussa (voce di `SPEC.md` §25) | `01-analisi/FUNZIONI_AI.md` |
| OM-n | funzione non AI discussa e assente dalle liste | `01-analisi/VOCI_OMESSE.md` |
| D-n | decisione | `02-piano/DECISIONI.md` |
| F-n | fase | milestone su GitHub |

## Regole di questa cartella

- Un problema nuovo o una funzione nuova diventa **una issue**, non un
  file. Qui si aggiunge solo l'analisi che serve a capirlo.
- Una decisione nuova si scrive in `02-piano/DECISIONI.md`.
- Mai segreti: niente token, password o indirizzi di database.
