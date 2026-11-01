# Memoria di dev-ai

## Aggiornata
01/11/2026 · ramo `feat/r12ai` · giro r12 (agente r12ai)

## In corso
- Giro r12 chiuso nel lotto: nessuna voce `[~]`/`[ ]` in §25 tranne 25.21 (`[✗]`, D52). Resta da fare: rapporto, smoke
  e suite completa dell'orchestratore (migrazioni 0420-0429, main.py e user_app_bot toccati).

## Fatto
- r12: assistente, boss, dungeon, misteri, spirito, tema/nomi a tema, segnalazioni, `/ai staff`, ricerca web, riepilogo
  a orario e avvisi, ticket AI (bottone, prima risposta, risposte standard durevoli), voce (`cogs/ai/voce.py`,
  `core/voice_*`, vocale raw in `core/discord_raw.py`), trascrizione (`core/trascrizione.py`), traduzione unita 25.77,
  bozze di codice 25.100 (`cogs/ai/bozze.py`), richieste di cancellazione 25.84, `/ai modello` 25.82/25.94, app
  (`/trova`, `/assistente`, «Trascrivi vocale»), pannello (`core/web_panel_ai.py`), stile con permesso 25.36.
  Migrazioni 0420-0429. Decisioni D42-D44, D52.

## Cose imparate
- Helper di cog senza `setup`: nome con `_` iniziale (la scoperta li salta).
- `CogConGruppi` con `cog_load` proprio: chiamare `super().cog_load()`.
- Dopo `defer()` le risposte vanno con `followup.send`; `interaction_check` ridefinito chiama `super()`.
- Il guardrail scarta testi con "ignora le istruzioni". clean_db non svuota tutto: guild diversi nei test.
- Menu sul messaggio: non nel bot principale (i test dell'albero non li ammettono); vanno in `cogs/user_app/`, con il
  modulo in `MODULI_COG` di `core/user_app_bot.py`.
- Stringhe che iniziano con `/` nel codice sono lette come comandi citati (test_riferimenti_comandi).
- `ai_globale` ha un CHECK sulle chiavi (0428). Opzioni di testo: sempre `Range[str, 1, N]`.
- Pesi: `/ai` ~5950 (21 figli), `/utility` ~6590 (limite 6800), `/automod` e `/owner` pieni.

## Aperto
- Voce e trascrizione spente finché mancano `VOCE_MODELLO_DIR` (+ sherpa-onnx) e `VOCE_TRASCRIZIONE_URL`.
- Musica e video senza trasporto AI (D52). Testi AI solo in italiano. Card PNG di `/level` senza nomi a tema.
