# Memoria di custode-ai

## Aggiornata
05/10/2026 · ramo `main` · ultimo commit `3dc9031`

## In corso
- In attesa dell'elenco dei servizi AI dall'owner.
- Prossimo passo che non dipende dall'elenco: la logica pura dello
  snodo in `core/ai_router.py` (scelta per tipo, fascia e quota), con
  `tests/test_ai_router.py` e servizi finti.

## Fatto
- Solo gli scheletri: `core/ai_router.py`, `ai_cache_logic.py`,
  `ai_cost_logic.py`, `ai_guardrail_logic.py`.
- Disegno dello snodo scritto in `.claude/agents/custode-ai.md`
  (AI-R-101, 102, 103; D19).

## Cose imparate
- iYokai usa servizi esistenti, non addestra (D19).
- I messaggi degli utenti vanno solo ai servizi segnati "può ricevere
  messaggi".
- Le chiavi stanno solo nel `.env` dell'owner.
- Voce (D22): scelta finale dell'owner **Piper, voce Paola**, con
  filtro e profili per contesto, locale e dentro il bot. Dettaglio in
  `revisione/02-piano/VOCE_YOKAI.md`; prototipo in
  `scripts/prova_voce.py`. Per lo snodo è un fornitore di tipo
  `audio`, senza quota e senza chiave.
- Scartati alla prova: Kokoro (R moscia), Dii (non commerciale),
  Qwen3-TTS e Chatterbox (server senza scheda video: 2 OCPU, 12 GB).
- Da fare prima della produzione: controllare la licenza di Paola.

## Aperto
- Elenco dei servizi e delle chiavi (nomi delle variabili) dall'owner.
- Issue: #95 (snodo), #50, #139, #140.
