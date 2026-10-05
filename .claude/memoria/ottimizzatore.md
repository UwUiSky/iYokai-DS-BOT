# Memoria di ottimizzatore

## Aggiornata
05/10/2026 · ramo `main` · ultimo commit `3dc9031`

## In corso
- Niente a metà. Nessun giro ancora fatto con questa struttura.

## Fatto
- Punto di partenza: i sette rilievi PERF-1…7 di
  `revisione/01-analisi/REVIEW.md` (riga 573 e seguenti), riportati nel
  quaderno come "da misurare".

## Cose imparate
- Esistono già `core/bounded_cache.py` (cache con tetto) e
  `core/memory_guard.py`: si usano quelli, non se ne scrivono altri.
- Immagini: tetto di 16 MP in `core/safe_image.py`.
- La scheda video non è usata: l'AI passa da servizi esterni.

## Aperto
- Misurare PERF-1…7 e trasformare in issue quelli confermati.
- La configurazione della verifica viene letta a ogni ingresso (#133).
