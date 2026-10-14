# Memoria di dev-ai

## Aggiornata
14/10/2026 · ramo `feat/r6ai` · giro r6 (motore AI + funzioni)

## In corso
- Previsione giro r6: 5 voci. (1) motore e servizio; (2) gruppo /ai di
  configurazione; (3) /utility ai (riassumi, traduci, immagina, personaggi,
  stile); (4) -chiedi con AI, menzione, traduzione automatica e bandiere,
  moderazione e ticket; (5) documenti (SPEC, COMMAND_LIST, VERIFICA_LIVE).
- Prossimo passo: voce 2, `cogs/ai/config.py` (gruppo `/ai`, D26).

## Fatto
- r6 voce 1: motore (`core/ai_providers.py`, `ai_router.py`,
  `ai_servizio.py`, `ai_cache_logic.py`, `ai_cost_logic.py`,
  `ai_guardrail_logic.py`, `ai_testi_logic.py`), repo `ai_repo.py`,
  migrazione 0140, registro dati, test `tests/test_ai_*`.

## Cose imparate
- I moduli chiamano solo `servizio_ai().richiedi(RichiestaAI(...))`;
  `AINonDisponibile.testo` è la risposta locale pronta.
- Fornitori dal `.env` (`AI_FORNITORI`, `AI_*_<NOME>`), formato compatibile
  OpenAI; senza `AI_ADDESTRA_<NOME>=no` il fornitore si scarta (D19).
- Tetto di spesa 0 = solo fornitori gratuiti (D13).
- Test: `tests/support/ai_finto.py` (trasporto finto, chiavi costruite a
  runtime); DB vero con `clean_db` + `AiRepository(lambda: clean_db)`.
- Nel worktree esporta l'ambiente e fai `cd` prima di pytest.

## Aperto
- #139: risposte standard imparate nei ticket (parte AI).
- #140: funzione richiesta → pull request in bozza.
