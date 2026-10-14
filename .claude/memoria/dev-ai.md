# Memoria di dev-ai

## Aggiornata
14/10/2026 · ramo `feat/r6ai` · giro r6

## In corso
- Giro r6 chiuso (5 voci su 5). Prossimo passo: esito dello smoke
  (`scripts/smoke.py --base main`), poi le voci rimaste di §25 (vedi Aperto).

## Fatto
- r6 voce 1 (79e28cc): motore `core/ai_providers.py`, `ai_router.py`,
  `ai_servizio.py`, `ai_cache_logic.py`, `ai_cost_logic.py`,
  `ai_guardrail_logic.py`, `ai_testi_logic.py`, `ai_immagini_logic.py`;
  repo `ai_repo.py`; migrazione 0140; registro dati.
- r6 voci 2–4 (6add30a): gruppo `/ai` (D26), `/utility ai`, `-chiedi` con
  l'AI, `/ticket assistente`, menzione, traduzioni, moderazione, chiavi.
- r6 voce 5: SPEC §25 (45 x, 15 ~), COMMAND_LIST, VERIFICA_LIVE, registro.

## Cose imparate
- I moduli chiamano solo `servizio_ai().richiedi(RichiestaAI(...))` o
  `cogs/ai/_comune.chiedi()`; `AINonDisponibile.testo` è la risposta locale.
- Fornitori dal `.env` (`AI_FORNITORI`, `AI_*_<NOME>`), formato compatibile
  OpenAI; senza `AI_ADDESTRA_<NOME>=no` il fornitore si scarta (D26).
- Tetto di spesa 0 = solo fornitori gratuiti (D13). Fascia: `testo` e
  `giudizio` partono da "media", serve un fornitore di quella fascia.
- Autocomplete sotto `@comando_di_gruppo`: funzione definita prima e
  `@app_commands.autocomplete(nome=funz)`, non `@cmd.autocomplete`.
- Opzioni str sempre `Range[str, a, b]` (test invarianti); niente "/parola"
  nei testi (test_riferimenti_comandi: "€/mese", "/models").
- I metodi dei repo devono avere `.nome(` in produzione: niente @property.
- Test: `tests/support/ai_finto.py`; cog con `monkeypatch.setattr(ai_repo,
  "_pool_provider", lambda: clean_db)` e `imposta_servizio_ai(...)`.
- test_forget_user fallisce a caso con pytest-randomly anche sulla base
  (ordine dei test): non è dell'AI.
- Nel worktree esporta l'ambiente e fai `cd` prima di pytest.

## Aperto
- §25 non fatte: World Boss e dungeon (con dev-economia), riepiloghi del
  server, ricerca nei log, classificazione segnalazioni, AutoMod assistito,
  prima risposta automatica nei ticket, app utente, pannello, voce,
  processo separato, coda, prova premium, embedding (`confronto`).
- Testi AI solo in italiano (non passano da `core/i18n.t`).
- #139: parte AI delle risposte standard. #140: PR in bozza.
