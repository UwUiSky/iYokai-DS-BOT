# Collaudo: le prove dal vivo, una alla volta

Lo strumento `scripts/collaudo.py` ti propone le prove di
`revisione/03-verifica/VERIFICA_LIVE.md`, segna quelle superate e apre
un'issue su GitHub per ogni errore.

## Come si usa

1. Avvia il bot e apri un **altro terminale** nella cartella del progetto.
2. Lancia `python scripts/collaudo.py`.
3. Per ogni prova rispondi: «Hai fatto la prova?» (s / n = salta / e = esci),
   poi «Ci sono stati errori?» (s / n). Se sì, descrivi l'errore in una riga.
4. Una prova superata non torna più e la sua riga nel file diventa `- [x]`.
   Una prova con errore non torna finché non usi `--ripeti`. Le saltate tornano.

Con `COLLAUDO=1` nel `.env`, il bot all'avvio ti ricorda questo comando (solo se
c'è un terminale). Non lancia nulla da solo: vedi D109.

## Opzioni

| Opzione | Effetto |
|---|---|
| `--sezione "Musica"` | solo le prove di quella sezione |
| `--stato` | riepilogo: fatte, errori, da fare, per sezione |
| `--storico` | elenco degli errori |
| `--ripeti CODICE` | rimette in coda una prova |
| `--invia-in-sospeso` | crea le issue degli errori salvati senza internet o token |
| `--non-modificare` | non spunta le righe di `VERIFICA_LIVE.md` |

## Cosa serve nel `.env`

- `COLLAUDO_REPO=owner/repo`
- `GITHUB_TOKEN=...`: un token **solo con il permesso Issues: Read and write**
  sul repository. Mai altri permessi. Non viene mai stampato né salvato.
- `COLLAUDO=1` (facoltativo, per l'avviso all'avvio del bot).

Stato e storico stanno in `collaudo/` (fuori da git).
